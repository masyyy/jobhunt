"""Tests for deferred tool support: HITL approval + client-executed external tools.

Covers two surfaces:
  1. ``_build_deferred_tool_results`` — merges adapter approval extraction with
     our manual scan for client-supplied tool outputs.
  2. ``create_agent`` wiring — registers ExternalToolset / FunctionToolset and
     widens output_type with DeferredToolRequests so pydantic-ai can pause.

The end-to-end test uses TestModel to drive a synthetic deferred-call cycle
without hitting a real LLM.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import ExternalToolset, FunctionToolset
from pydantic_ai.ui.vercel_ai.request_types import (
    DynamicToolOutputAvailablePart,
    TextUIPart,
    ToolOutputAvailablePart,
    UIMessage,
)

from backend.api.routers.chat import _build_deferred_tool_results  # pyright: ignore[reportPrivateUsage]
from backend.core.agents import chat_agent
from backend.core.agents.config import AgentConfig
from backend.customer.toolboxes import Toolbox


def _ask_user_def() -> ToolDefinition:
    return ToolDefinition(
        name="ask_user",
        description="Ask the user a multi-choice question.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question", "options"],
        },
    )


# ---------------------------------------------------------------------------
# _build_deferred_tool_results
# ---------------------------------------------------------------------------


def test_build_deferred_returns_none_when_nothing_to_resume() -> None:
    """No approvals from adapter, no client-supplied outputs → no resume payload."""
    msg = UIMessage(id="m1", role="user", parts=[TextUIPart(text="hi")])

    result = _build_deferred_tool_results(None, [msg])

    assert result is None


def test_build_deferred_passes_through_approvals_when_no_calls() -> None:
    """If the adapter found approvals and the FE supplied no tool outputs, return adapter result verbatim."""
    approvals = DeferredToolResults(approvals={"call-1": True})

    result = _build_deferred_tool_results(approvals, [])

    assert result is approvals


def test_build_deferred_extracts_client_supplied_tool_output() -> None:
    """An ``output-available`` tool part on an FE-posted assistant message becomes a deferred call result."""
    msg = UIMessage(
        id="m1",
        role="assistant",
        parts=[
            ToolOutputAvailablePart(
                type="tool-ask_user",
                tool_call_id="call-xyz",
                state="output-available",
                input={"question": "pick one", "options": ["red", "blue"]},
                output="red",
            )
        ],
    )

    result = _build_deferred_tool_results(None, [msg])

    assert result is not None
    assert result.calls == {"call-xyz": "red"}
    assert result.approvals == {}


def test_build_deferred_handles_dynamic_tool_outputs() -> None:
    """Dynamic-tool variants from pydantic-ai's request_types must also be picked up."""
    msg = UIMessage(
        id="m1",
        role="assistant",
        parts=[
            DynamicToolOutputAvailablePart(
                type="dynamic-tool",
                tool_name="ask_user",
                tool_call_id="call-dyn",
                state="output-available",
                input={"question": "?"},
                output={"choice": "blue"},
            )
        ],
    )

    result = _build_deferred_tool_results(None, [msg])

    assert result is not None
    assert result.calls == {"call-dyn": {"choice": "blue"}}


def test_build_deferred_merges_approvals_and_calls() -> None:
    """Both flavours can arrive on the same resume turn; they share one DeferredToolResults."""
    adapter_results = DeferredToolResults(approvals={"call-approve": True})
    msg = UIMessage(
        id="m1",
        role="assistant",
        parts=[
            ToolOutputAvailablePart(
                type="tool-ask_user",
                tool_call_id="call-output",
                state="output-available",
                input={"question": "?"},
                output="answer",
            )
        ],
    )

    result = _build_deferred_tool_results(adapter_results, [msg])

    assert result is not None
    assert result.approvals == {"call-approve": True}
    assert result.calls == {"call-output": "answer"}


def test_build_deferred_ignores_user_messages() -> None:
    """A user message containing tool parts (theoretical) must not be mined for results."""
    msg = UIMessage(id="m1", role="user", parts=[TextUIPart(text="please answer")])

    result = _build_deferred_tool_results(None, [msg])

    assert result is None


# ---------------------------------------------------------------------------
# create_agent wiring
# ---------------------------------------------------------------------------


def _agent_with_config(monkeypatch: pytest.MonkeyPatch, config: AgentConfig) -> Any:
    """Build an Agent via create_agent against a monkeypatched TOOLBOX_AGENT_CONFIG."""
    monkeypatch.setattr(chat_agent, "TOOLBOX_AGENT_CONFIG", {Toolbox.SALES: config})

    # Avoid the real model resolver hitting OpenAI — swap the model factory.
    def _stub_get_model(_name: str) -> Model:
        return TestModel(call_tools=["ask_user"])

    monkeypatch.setattr(chat_agent, "get_model", _stub_get_model)
    return chat_agent.create_agent(Toolbox.SALES, instructions="test")


def test_create_agent_registers_external_toolset(monkeypatch: pytest.MonkeyPatch) -> None:
    """``external_tools`` must result in an ExternalToolset attached to the agent."""
    config = AgentConfig(tools=[], external_tools=(_ask_user_def(),))

    agent = _agent_with_config(monkeypatch, config)

    external = [ts for ts in agent.toolsets if isinstance(ts, ExternalToolset)]
    assert len(external) == 1
    assert [td.name for td in external[0].tool_defs] == ["ask_user"]


def test_create_agent_widens_output_type_with_deferred_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """When deferred mechanisms are in play, DeferredToolRequests must be in the output union.

    Without this, pydantic-ai raises ``UserError: A deferred tool call was present,
    but DeferredToolRequests is not among output types.``
    """
    config = AgentConfig(tools=[], external_tools=(_ask_user_def(),))

    agent = _agent_with_config(monkeypatch, config)

    # Smoke: the agent runs without raising the UserError above. TestModel
    # auto-calls ``ask_user``, the agent pauses, and we get DeferredToolRequests back.
    result = agent.run_sync("kick off")
    assert isinstance(result.output, DeferredToolRequests)
    assert len(result.output.calls) == 1
    assert result.output.calls[0].tool_name == "ask_user"


def test_create_agent_skips_external_toolset_when_unused(monkeypatch: pytest.MonkeyPatch) -> None:
    """No external_tools and no approval_required_tools → no ExternalToolset, no DeferredToolRequests widening."""
    config = AgentConfig(tools=[])

    agent = _agent_with_config(monkeypatch, config)

    assert not any(isinstance(ts, ExternalToolset) for ts in agent.toolsets)
    assert not any(isinstance(ts, FunctionToolset) and ts.requires_approval for ts in agent.toolsets)


# ---------------------------------------------------------------------------
# End-to-end deferred-call resume
# ---------------------------------------------------------------------------


def test_external_tool_pause_and_resume_round_trip() -> None:
    """The full deferred-call cycle: model calls external tool → agent pauses → FE supplies output → agent resumes."""
    agent = Agent(
        model=TestModel(call_tools=["ask_user"]),
        toolsets=[ExternalToolset([_ask_user_def()])],
        output_type=[str, DeferredToolRequests],
    )

    paused = agent.run_sync("hi")

    assert isinstance(paused.output, DeferredToolRequests)
    assert len(paused.output.calls) == 1
    call_id = paused.output.calls[0].tool_call_id

    # Simulate the FE supplying the user's choice via addToolOutput → BE.
    resumed = agent.run_sync(
        message_history=paused.all_messages(),
        deferred_tool_results=DeferredToolResults(calls={call_id: "red"}),
    )

    # TestModel echoes structured tool output as JSON; the user's pick is in there.
    assert "red" in str(resumed.output)
