"""Vercel AI adapter customisations.

PydanticAI represents binary tool returns (e.g. a PDF read by ``read_file``)
as ``BinaryContent`` and feeds them to the model by injecting follow-up
``UserPromptPart`` messages of the form ``["This is file <id>:", <binary>]``.
We keep those in the DB so the model sees the real PDF on subsequent turns
(compaction prunes later) but never ship the bytes to the browser, and we
hide the auto-injected user prompts from the UI — the file is already
documented in the ``read_file`` tool card.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    BuiltinToolReturnPart,
    FilePart,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
)
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai._event_stream import VercelAIEventStream  # pyright: ignore[reportPrivateUsage]
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ToolOutputAvailableChunk

# PydanticAI prefixes auto-injected user prompts for binary tool returns
# with this exact text — see _agent_graph.py:1251 in the installed version.
_AUTO_INJECTED_BINARY_PREFIX = "This is file "

# Vercel AI SDK protocol version. v6 enables tool approval streaming
# (`approval-requested` / `approval-responded` parts) for human-in-the-loop
# workflows. The frontend uses `@ai-sdk/react` v6 with `addToolApprovalResponse`.
SDK_VERSION = 6


def _strip_binary(value: Any) -> Any:
    """Replace BinaryContent (and serialized binary dicts) with metadata-only stubs."""
    if isinstance(value, BinaryContent):
        return {"kind": "binary", "media_type": value.media_type, "identifier": value.identifier}
    if isinstance(value, dict):
        if value.get("kind") == "binary" and "data" in value:
            return {
                "kind": "binary",
                "media_type": value.get("media_type"),
                "identifier": value.get("identifier"),
            }
        return {k: _strip_binary(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_binary(v) for v in value]
    return value


def _contains_binary(value: Any) -> bool:
    if isinstance(value, BinaryContent):
        return True
    if isinstance(value, dict):
        if value.get("kind") == "binary" and "data" in value:
            return True
        return any(_contains_binary(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_binary(v) for v in value)
    return False


def _sanitize_messages_for_ui(messages: Sequence[ModelMessage]) -> list[ModelMessage]:
    """Replace BinaryContent inside ToolReturnPart.content with metadata stubs.

    PydanticAI persists ``BinaryContent`` (e.g. PDFs) in tool-return parts so
    the model can re-read them on subsequent turns. The Vercel adapter renders
    these to the UI by JSON-dumping the content via ``model_response_str``,
    which would otherwise ship the full base64 payload to the browser. We keep
    the originals (LLM context) and only sanitize the copy used for UI dumping.
    """
    sanitized: list[ModelMessage] = []
    for msg in messages:
        if not isinstance(msg, ModelRequest):
            sanitized.append(msg)
            continue
        changed = False
        new_parts = list(msg.parts)
        for i, part in enumerate(new_parts):
            if isinstance(part, ToolReturnPart) and _contains_binary(part.content):
                new_parts[i] = replace(part, content=_strip_binary(part.content))
                changed = True
        sanitized.append(replace(msg, parts=new_parts) if changed else msg)
    return sanitized


def _is_auto_injected_binary_prompt(msg: UIMessage) -> bool:
    """Detect PydanticAI's auto-injected ``This is file X:`` user prompts."""
    if msg.role != "user":
        return False
    has_file = any(isinstance(p, FileUIPart) for p in msg.parts)
    if not has_file:
        return False
    return any(isinstance(p, TextUIPart) and p.text.startswith(_AUTO_INJECTED_BINARY_PREFIX) for p in msg.parts)


class FulcrumVercelEventStream(VercelAIEventStream[Any, Any]):
    """Strips binary payloads from the user-facing UI stream.

    Tool returns flow through ``handle_function_tool_result`` (regular tools)
    and ``handle_builtin_tool_return`` (provider-executed tools); both emit
    ``ToolOutputAvailableChunk`` whose ``output`` may carry ``BinaryContent``
    serialized to a dict with a ``data`` field. We rewrite that field to drop
    the payload before the chunk reaches the browser.
    """

    async def handle_function_tool_result(self, event: FunctionToolResultEvent) -> AsyncIterator[BaseChunk]:
        async for chunk in super().handle_function_tool_result(event):
            yield _scrub_chunk(chunk)

    async def handle_builtin_tool_return(self, part: BuiltinToolReturnPart) -> AsyncIterator[BaseChunk]:
        async for chunk in super().handle_builtin_tool_return(part):
            yield _scrub_chunk(chunk)

    async def handle_file(self, part: FilePart) -> AsyncIterator[BaseChunk]:  # noqa: ARG002
        # The chat agent does not produce model-generated files; suppress
        # any FilePart that slips through to keep base64 out of the UI.
        return
        yield  # pragma: no cover  -- async generator marker


def _scrub_chunk(chunk: BaseChunk) -> BaseChunk:
    if isinstance(chunk, ToolOutputAvailableChunk):
        chunk.output = _strip_binary(chunk.output)
    return chunk


@dataclass
class FulcrumVercelAdapter(VercelAIAdapter[Any, Any]):
    """Vercel adapter that hides PydanticAI's auto-injected binary prompts from the UI."""

    def build_event_stream(self) -> FulcrumVercelEventStream:
        return FulcrumVercelEventStream(
            self.run_input,
            accept=self.accept,
            sdk_version=self.sdk_version,
            server_message_id=self.server_message_id,
        )

    @classmethod
    def dump_messages(cls, messages: Sequence[ModelMessage], sdk_version: int = SDK_VERSION) -> list[UIMessage]:  # type: ignore[override]
        ui_messages = super().dump_messages(_sanitize_messages_for_ui(messages), sdk_version=sdk_version)  # type: ignore[arg-type]
        return [m for m in ui_messages if not _is_auto_injected_binary_prompt(m)]
