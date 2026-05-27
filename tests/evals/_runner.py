"""Eval runner — runs a single EvalCase against the real chat agent.

No stubs, no mocks. Uses the real agent, real tools, real model, real data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart

from backend.api.dependencies import get_prompt_loader
from backend.core.agents.chat_agent import create_agent
from backend.core.agents.deps import AgentDeps
from backend.core.agents.model_config import MODEL_MAIN, get_model
from tests.evals._case import EvalCase

__all__ = ["RESULTS", "CaseResult", "EvalCase", "TimelineEvent", "ToolCallRecord", "run_case"]


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]


@dataclass
class TimelineEvent:
    """One step in the agent's chain of work, in execution order."""

    kind: str  # "text" | "tool_call" | "tool_return"
    name: str | None = None  # tool name for tool_call / tool_return
    text: str | None = None  # text content for text events
    args: dict[str, Any] | None = None  # tool call args
    result: Any | None = None  # tool return content
    tool_call_id: str | None = None


@dataclass
class CaseResult:
    case: EvalCase
    response: str
    tool_calls: list[ToolCallRecord]
    timeline: list[TimelineEvent]
    judge_score: float | None
    judge_reasoning: str | None
    passed: bool
    failure_reason: str | None
    error: str | None = None


# Module-level buffer — the report test reads this at the end of the run.
RESULTS: list[CaseResult] = []


class JudgeVerdict(BaseModel):
    """Structured output from the LLM-as-judge."""

    score: float = Field(ge=0.0, le=1.0, description="0 = does not satisfy rubric, 1 = fully satisfies.")
    reasoning: str = Field(description="One or two sentences justifying the score.")


_JUDGE_INSTRUCTIONS = (
    "You evaluate whether an AI assistant's response satisfies a rubric. "
    "You are given the rubric, the user's question, and the assistant's response. "
    "Score strictly: 1.0 only if the response fully satisfies the rubric, "
    "0.0 if it does not satisfy it at all, partial credit otherwise. "
    "Be terse — one or two sentences of reasoning."
)


def _build_judge() -> Agent[None, JudgeVerdict]:
    """Build the judge agent. Reuses the same model resolver as the main agent."""
    return Agent(
        model=get_model(MODEL_MAIN),
        output_type=JudgeVerdict,
        instructions=_JUDGE_INSTRUCTIONS,
    )


def _extract_tool_calls(messages: list[Any]) -> list[ToolCallRecord]:
    """Pull tool calls out of an agent run's message history."""
    calls: list[ToolCallRecord] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    args = part.args if isinstance(part.args, dict) else {"raw": str(part.args)}
                    calls.append(ToolCallRecord(name=part.tool_name, args=args))
    return calls


def _extract_timeline(messages: list[Any]) -> list[TimelineEvent]:
    """Walk the message history and produce an ordered timeline of agent events.

    Skips the initial user prompt and final assistant text — those are shown
    separately in the report. What's left is the agent's chain of work:
    intermediate reasoning, tool calls, and tool returns, in order.
    """
    events: list[TimelineEvent] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    args = part.args if isinstance(part.args, dict) else {"raw": str(part.args)}
                    events.append(
                        TimelineEvent(
                            kind="tool_call",
                            name=part.tool_name,
                            args=args,
                            tool_call_id=part.tool_call_id,
                        )
                    )
                elif isinstance(part, TextPart):
                    text = part.content.strip()
                    if text:
                        events.append(TimelineEvent(kind="text", text=text))
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    events.append(
                        TimelineEvent(
                            kind="tool_return",
                            name=part.tool_name,
                            result=part.content,
                            tool_call_id=part.tool_call_id,
                        )
                    )
    # Drop the trailing assistant text — it's the final response, shown separately.
    while events and events[-1].kind == "text":
        events.pop()
    return events


def _check_deterministic(case: EvalCase, response: str, tool_calls: list[ToolCallRecord]) -> str | None:
    """Return None if all deterministic checks pass, otherwise the failure reason."""
    called_names = {c.name for c in tool_calls}

    missing = [t for t in case.expected_tool_calls if t not in called_names]
    if missing:
        return f"Expected tool calls missing: {missing}. Tools actually called: {sorted(called_names)}"

    forbidden = [t for t in case.forbidden_tool_calls if t in called_names]
    if forbidden:
        return f"Forbidden tool calls were made: {forbidden}"

    for needle in case.response_contains:
        if needle.lower() not in response.lower():
            return f"Response missing substring (case-insensitive): {needle!r}"

    for pattern in case.response_regex:
        if not re.search(pattern, response, re.IGNORECASE | re.DOTALL):
            return f"Response did not match regex: {pattern!r}"

    return None


async def _run_judge(case: EvalCase, response: str) -> tuple[float, str]:
    """Invoke the LLM judge for a case. Returns (score, reasoning)."""
    assert case.judge_rubric is not None
    judge = _build_judge()
    prompt = f"Rubric: {case.judge_rubric}\n\nUser question: {case.user_prompt}\n\nAssistant response:\n{response}"
    result = await judge.run(prompt)
    return result.output.score, result.output.reasoning


async def run_case(case: EvalCase, deps: AgentDeps) -> CaseResult:
    """Run a single case and append the result to RESULTS."""
    try:
        prompt_loader = get_prompt_loader()
        instructions = prompt_loader.load(case.toolbox.value)
        tables = deps.db.list_tables()
        agent = create_agent(case.toolbox, instructions, tables)

        run = await agent.run(case.user_prompt, deps=deps)
        response = run.output
        messages = list(run.new_messages())
        tool_calls = _extract_tool_calls(messages)
        timeline = _extract_timeline(messages)
    except Exception as exc:
        result = CaseResult(
            case=case,
            response="",
            tool_calls=[],
            timeline=[],
            judge_score=None,
            judge_reasoning=None,
            passed=False,
            failure_reason=f"Agent run raised: {type(exc).__name__}: {exc}",
            error=str(exc),
        )
        RESULTS.append(result)
        return result

    failure_reason = _check_deterministic(case, response, tool_calls)
    judge_score: float | None = None
    judge_reasoning: str | None = None

    if failure_reason is None and case.judge_rubric is not None:
        try:
            judge_score, judge_reasoning = await _run_judge(case, response)
        except Exception as exc:
            failure_reason = f"Judge call failed: {type(exc).__name__}: {exc}"
        else:
            if judge_score < case.judge_threshold:
                failure_reason = (
                    f"Judge score {judge_score:.2f} below threshold {case.judge_threshold:.2f}. "
                    f"Reasoning: {judge_reasoning}"
                )

    result = CaseResult(
        case=case,
        response=response,
        tool_calls=tool_calls,
        timeline=timeline,
        judge_score=judge_score,
        judge_reasoning=judge_reasoning,
        passed=failure_reason is None,
        failure_reason=failure_reason,
    )
    RESULTS.append(result)
    return result
