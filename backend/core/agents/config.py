"""Per-toolbox agent configuration.

Each ``Toolbox`` maps to one ``AgentConfig`` in
``backend/customer/tools/__init__.py`` ``TOOLBOX_AGENT_CONFIG``. The chat
router looks up the config by toolbox and passes ``tools`` and
``output_type`` straight through to ``Agent(...)``.

Workshops (purpose-built workflows) declare:
- ``output_type`` — a Pydantic model for structured output, or ``str`` (default).
- ``accepted_prompt_keys`` — which seed-prompt keys the workshop accepts on its
  first turn via ``POST /api/chat`` ``prompt_key`` field.
- ``approval_required_tools`` — tool function names wrapped in a
  ``FunctionToolset(requires_approval=True)`` for human-in-the-loop gating.
- ``external_tools`` — tool definitions executed by the frontend instead of
  the backend (e.g. multi-choice prompts). Surfaced to the model via an
  ``ExternalToolset``; the FE supplies the result via ``addToolResult`` and
  the chat router resumes the agent with ``DeferredToolResults.calls``.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.tools import ToolDefinition


@dataclass(frozen=True)
class AgentConfig:
    tools: list[Any]
    output_type: type | list[Any] = str
    accepted_prompt_keys: frozenset[str] = field(default_factory=frozenset)
    approval_required_tools: frozenset[str] = field(default_factory=frozenset)
    external_tools: tuple[ToolDefinition, ...] = ()
