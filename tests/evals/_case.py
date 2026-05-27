"""EvalCase dataclass — the contract between the eval runner and customer cases."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.customer.toolboxes import Toolbox


@dataclass
class EvalCase:
    """One eval case targeting the chat agent.

    Deterministic checks (expected/forbidden tool calls, response substrings,
    response regex) always run. The LLM judge runs only when judge_rubric is set.
    """

    id: str
    toolbox: Toolbox
    user_prompt: str
    expected_tool_calls: list[str] = field(default_factory=list)
    forbidden_tool_calls: list[str] = field(default_factory=list)
    response_contains: list[str] = field(default_factory=list)
    response_regex: list[str] = field(default_factory=list)
    judge_rubric: str | None = None
    judge_threshold: float = 0.7
