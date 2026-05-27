"""Regression tests for FulcrumVercelAdapter binary sanitization."""

from __future__ import annotations

from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from backend.api.vercel_adapter import (
    FulcrumVercelAdapter,
    _sanitize_messages_for_ui,  # pyright: ignore[reportPrivateUsage]
)


def _pdf_bytes() -> bytes:
    # Minimal valid-looking PDF header — content doesn't matter for these tests.
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 64


def test_sanitize_replaces_binary_in_tool_return_with_stub() -> None:
    """If a tool returns BinaryContent directly inside ToolReturnPart.content, sanitize replaces the bytes."""
    binary = BinaryContent(data=_pdf_bytes(), media_type="application/pdf", identifier="doc.pdf")
    req = ModelRequest(
        parts=[
            ToolReturnPart(tool_name="read_file", content=binary, tool_call_id="call-1"),
        ]
    )

    sanitized = _sanitize_messages_for_ui([req])

    assert len(sanitized) == 1
    sanitized_req = sanitized[0]
    assert isinstance(sanitized_req, ModelRequest)
    new_part = sanitized_req.parts[0]
    assert isinstance(new_part, ToolReturnPart)
    assert new_part.content == {
        "kind": "binary",
        "media_type": "application/pdf",
        "identifier": "doc.pdf",
    }
    # Original message left untouched (we work on copies).
    assert isinstance(req.parts[0], ToolReturnPart)
    assert isinstance(req.parts[0].content, BinaryContent)


def test_sanitize_leaves_string_tool_returns_alone() -> None:
    """The common path: PydanticAI auto-wraps BinaryContent so ToolReturnPart.content is just `See file ...`."""
    req = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name="read_file",
                content="See file doc.pdf (10-page PDF)",
                tool_call_id="call-1",
            ),
        ]
    )

    sanitized = _sanitize_messages_for_ui([req])

    # No copy needed — same object identity.
    assert sanitized[0] is req


def test_dump_messages_with_binary_tool_return_does_not_raise() -> None:
    """Regression: ToolReturnPart is a stdlib dataclass; .model_copy would AttributeError.

    The full dump_messages call must succeed end-to-end when a binary lives in a tool return.
    """
    binary = BinaryContent(data=_pdf_bytes(), media_type="application/pdf", identifier="doc.pdf")
    messages = [
        ModelRequest(parts=[UserPromptPart(content="read the pdf")]),
        # Simulate a model response that called the tool.
        # We only need the request side for sanitization; the response's tool call/return pairing
        # is exercised via the full PydanticAI flow elsewhere.
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="read_file", content=binary, tool_call_id="call-1"),
            ]
        ),
    ]

    # Must not raise. We don't assert on the exact UIMessage shape — pydantic_ai internals
    # decide how a bare ToolReturnPart without a paired ToolCallPart is rendered. The point
    # is sanitation runs and dataclass copying works.
    ui_messages = FulcrumVercelAdapter.dump_messages(messages)
    serialized = [m.model_dump(mode="json", by_alias=True) for m in ui_messages]

    # Defense in depth: no base64 PDF magic bytes leaked into the serialized output.
    blob = repr(serialized)
    assert "JVBERi0" not in blob, "base64-encoded PDF header leaked to UI payload"


def test_sanitize_handles_binary_nested_in_list_content() -> None:
    """Tools may return [BinaryContent, ...] — recursively strip."""
    binary = BinaryContent(data=_pdf_bytes(), media_type="application/pdf", identifier="doc.pdf")
    req = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name="read_file",
                content=[binary, "extra text"],
                tool_call_id="call-1",
            ),
        ]
    )

    sanitized = _sanitize_messages_for_ui([req])
    new_part = sanitized[0].parts[0]
    assert isinstance(new_part, ToolReturnPart)
    assert new_part.content == [
        {"kind": "binary", "media_type": "application/pdf", "identifier": "doc.pdf"},
        "extra text",
    ]


def test_sanitize_passes_through_non_request_messages() -> None:
    """ModelResponse messages have no ToolReturnParts to sanitize; pass through unchanged."""
    resp = ModelResponse(parts=[TextPart(content="hello")])
    sanitized = _sanitize_messages_for_ui([resp])
    assert sanitized[0] is resp
