"""Tests for conversation compaction.

Convention (see CLAUDE.md):
- Drive the use-case (`CompactionService.run_compaction`, `load_messages_for_agent`,
  `load_all_messages_for_ui`) at its public entry point.
- Use the real `ConversationRepository` against in-memory SQLite via the
  `conversation_repo` / `repo_factory` fixtures.
- Use `FakeSummarizationAgent` for the LLM collaborator (no cheap real backing).
- Assert on observable behavior (loaded messages, persisted summaries) — never
  `assert_called_with`.

The `prune_tool_outputs_processor` and `extract_text_from_message` tests below
are kept as the carve-out for pure functions that enforce silent invariants:
both run on LLM-produced content, and a regression silently corrupts the
context the agent sees.
"""

import json
from datetime import datetime, timedelta
from typing import cast

import pytest
import pytest_asyncio
from pydantic_ai import Agent, ModelMessage
from pydantic_ai.messages import (
    BinaryContent,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from backend.core.entities.conversation import Message
from backend.core.interfaces.conversation_repository import (
    ConversationRepositoryInterface,
    RepositoryFactory,
)
from backend.core.services.compaction import (
    KEEP_RECENT_MESSAGES,
    TOOL_OUTPUT_PLACEHOLDER,
    CompactionService,
    extract_text_from_message,
    load_all_messages_for_ui,
    load_messages_for_agent,
    prune_tool_outputs_processor,
)
from tests.fakes.agent import FakeSummarizationAgent

# --- helpers -----------------------------------------------------------------

BASE_TS = datetime(2024, 1, 1, 12, 0, 0)


def _user_message_json(text: str) -> str:
    return json.dumps([{"kind": "request", "parts": [{"part_kind": "user-prompt", "content": text}]}])


async def _seed_messages(
    repo: ConversationRepositoryInterface,
    conversation_id: str,
    count: int,
    *,
    token_count: int = 25_000,
    start_idx: int = 0,
) -> list[Message]:
    """Seed `count` user messages with strictly-increasing timestamps. Returns saved entities."""
    saved: list[Message] = []
    for i in range(count):
        idx = start_idx + i
        msg = Message(
            conversation_id=conversation_id,
            kind="request",
            content_json=_user_message_json(f"message {idx}"),
            token_count=token_count,
            created_at=BASE_TS + timedelta(seconds=idx),
        )
        saved.append(await repo.add_message(msg))
    return saved


def _as_agent(fake: FakeSummarizationAgent) -> Agent[None, str]:
    """The fake duck-types Agent. Cast for the type checker."""
    return cast(Agent[None, str], fake)


@pytest_asyncio.fixture
async def conversation_id(conversation_repo: ConversationRepositoryInterface) -> str:
    """A persisted, empty conversation ready to be seeded."""
    conv = await conversation_repo.create_conversation(toolbox="sales", user_id=None)
    assert conv.id is not None
    return conv.id


# --- pure-function carve-outs -------------------------------------------------


class TestExtractTextFromMessage:
    """Parser for LLM-produced ModelMessages. Subtle edge cases around attachments
    where a regression would silently lose user prompts. Justified pure-function test."""

    def test_extract_user_text_from_request(self) -> None:
        msg = ModelRequest(parts=[UserPromptPart(content="Hello, AI!")])
        assert extract_text_from_message(msg) == ("Hello, AI!", None)

    def test_extract_assistant_text_from_response(self) -> None:
        msg = ModelResponse(parts=[TextPart(content="Hello, human!")])
        assert extract_text_from_message(msg) == (None, "Hello, human!")

    def test_extract_from_empty_message(self) -> None:
        assert extract_text_from_message(ModelRequest(parts=[])) == (None, None)

    def test_extract_text_with_image_attachment(self) -> None:
        msg = ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        ImageUrl(url="https://example.com/photo.png", media_type="image/png"),
                        "What is in this image?",
                    ]
                )
            ]
        )
        assert extract_text_from_message(msg) == ("What is in this image?", None)

    def test_extract_text_with_binary_attachment(self) -> None:
        msg = ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        BinaryContent(data=b"%PDF-1.4 fake content", media_type="application/pdf"),
                        "Summarize this PDF",
                    ]
                )
            ]
        )
        assert extract_text_from_message(msg) == ("Summarize this PDF", None)

    def test_extract_text_file_only_no_text(self) -> None:
        msg = ModelRequest(parts=[UserPromptPart(content=[BinaryContent(data=b"fake bytes", media_type="image/png")])])
        assert extract_text_from_message(msg) == (None, None)

    def test_extract_text_multiple_text_parts_with_files(self) -> None:
        msg = ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "Compare these two images:",
                        ImageUrl(url="https://example.com/a.png", media_type="image/png"),
                        ImageUrl(url="https://example.com/b.png", media_type="image/png"),
                        "Which one is better?",
                    ]
                )
            ]
        )
        assert extract_text_from_message(msg) == ("Compare these two images: Which one is better?", None)


class TestPruneToolOutputsProcessor:
    """History processor invoked by Agent.history_processors at runtime. Regressions
    silently corrupt tool-call structure the LLM sees. Justified pure-function test."""

    def test_no_pruning_below_threshold(self) -> None:
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi")]),
        ]
        assert prune_tool_outputs_processor(messages) == messages

    def test_no_pruning_empty_messages(self) -> None:
        assert prune_tool_outputs_processor([]) == []

    def test_pruning_exactly_at_threshold(self) -> None:
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Message {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]
        assert prune_tool_outputs_processor(messages) == messages

    def test_pruning_replaces_tool_output_but_preserves_structure(self) -> None:
        old: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="What time is it?")]),
            ModelResponse(parts=[ToolCallPart(tool_name="get_time", args={"a": 1}, tool_call_id="call-1")]),
            ModelRequest(
                parts=[ToolReturnPart(tool_name="get_time", content="2024-01-15 10:30:00", tool_call_id="call-1")]
            ),
            ModelResponse(parts=[TextPart(content="The time is 10:30 AM")]),
        ]
        recent: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Recent {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]

        result = prune_tool_outputs_processor(old + recent)

        assert len(result) == len(old) + len(recent)
        pruned = cast(ToolReturnPart, result[2].parts[0])
        assert pruned.content == TOOL_OUTPUT_PLACEHOLDER
        assert pruned.tool_name == "get_time"
        assert pruned.tool_call_id == "call-1"
        assert result[-KEEP_RECENT_MESSAGES:] == recent

    def test_pruning_preserves_user_prompts_in_old_messages(self) -> None:
        old: list[ModelMessage] = [ModelRequest(parts=[UserPromptPart(content="Important user context")])]
        recent: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Recent {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]
        result = prune_tool_outputs_processor(old + recent)
        user_part = cast(UserPromptPart, result[0].parts[0])
        assert user_part.content == "Important user context"

    def test_pruning_preserves_response_messages_by_reference(self) -> None:
        old: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Original response text")]),
        ]
        recent: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Recent {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]
        result = prune_tool_outputs_processor(old + recent)
        assert result[1] is old[1]  # response objects pass through unchanged

    def test_pruning_with_mixed_parts_in_request(self) -> None:
        old: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    UserPromptPart(content="User asked something"),
                    ToolReturnPart(tool_name="tool1", content="Large output", tool_call_id="call-1"),
                ]
            )
        ]
        recent: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Recent {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]
        result = prune_tool_outputs_processor(old + recent)
        old_request = result[0]
        user_part = old_request.parts[0]
        assert isinstance(user_part, UserPromptPart)
        assert user_part.content == "User asked something"
        tool_part = old_request.parts[1]
        assert isinstance(tool_part, ToolReturnPart)
        assert tool_part.content == TOOL_OUTPUT_PLACEHOLDER

    def test_processor_does_not_mutate_input(self) -> None:
        original_part = ToolReturnPart(tool_name="tool1", content="Original", tool_call_id="call-1")
        old: list[ModelMessage] = [ModelRequest(parts=[original_part])]
        recent: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=f"Recent {i}")]) for i in range(KEEP_RECENT_MESSAGES)
        ]
        prune_tool_outputs_processor(old + recent)
        assert original_part.content == "Original"  # input untouched


# --- use-case tests: CompactionService ---------------------------------------


class TestCheckNeedsCompaction:
    @pytest.mark.asyncio
    async def test_returns_false_below_threshold_with_no_summary(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=3, token_count=10_000)
        service = CompactionService(repo_factory, _as_agent(FakeSummarizationAgent()))

        assert await service.check_needs_compaction(conversation_id) is False

    @pytest.mark.asyncio
    async def test_returns_true_above_threshold_with_no_summary(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=5, token_count=30_000)  # 150k > 100k
        service = CompactionService(repo_factory, _as_agent(FakeSummarizationAgent()))

        assert await service.check_needs_compaction(conversation_id) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_summary_covers_recent_messages(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        # 30 messages * 5k tokens = 150k total (above threshold) triggers initial compaction.
        # After compaction, the 10-message tail is 50k tokens (below threshold) so a
        # subsequent check_needs_compaction must return False.
        await _seed_messages(conversation_repo, conversation_id, count=30, token_count=5_000)
        service = CompactionService(repo_factory, _as_agent(FakeSummarizationAgent()))
        assert await service.run_compaction(conversation_id) is not None

        assert await service.check_needs_compaction(conversation_id) is False


class TestRunCompaction:
    @pytest.mark.asyncio
    async def test_generates_and_persists_summary(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        num_messages = KEEP_RECENT_MESSAGES + 5
        seeded = await _seed_messages(conversation_repo, conversation_id, count=num_messages)
        fake = FakeSummarizationAgent(output="This is a generated summary.")
        service = CompactionService(repo_factory, _as_agent(fake))

        result = await service.run_compaction(conversation_id)

        assert result is not None
        assert result.id is not None
        assert result.conversation_id == conversation_id
        assert "generated summary" in result.summary_text
        assert result.message_count == num_messages - KEEP_RECENT_MESSAGES
        assert result.covers_until_message_id == seeded[num_messages - KEEP_RECENT_MESSAGES - 1].id

        persisted = await conversation_repo.get_latest_summary(conversation_id)
        assert persisted is not None
        assert persisted.id == result.id

        assert len(fake.calls) == 1
        assert len(fake.calls[0].message_history) > 0

    @pytest.mark.asyncio
    async def test_skips_when_not_needed(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=2, token_count=10_000)
        fake = FakeSummarizationAgent()
        service = CompactionService(repo_factory, _as_agent(fake))

        assert await service.run_compaction(conversation_id) is None
        assert fake.calls == []
        assert await conversation_repo.get_latest_summary(conversation_id) is None

    @pytest.mark.asyncio
    async def test_skips_when_not_enough_messages_to_summarize(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        # Above token threshold but only KEEP_RECENT_MESSAGES messages exist — nothing to summarize.
        await _seed_messages(conversation_repo, conversation_id, count=KEEP_RECENT_MESSAGES, token_count=15_000)
        fake = FakeSummarizationAgent()
        service = CompactionService(repo_factory, _as_agent(fake))

        assert await service.run_compaction(conversation_id) is None
        assert fake.calls == []
        assert await conversation_repo.get_latest_summary(conversation_id) is None

    @pytest.mark.asyncio
    async def test_returns_none_and_persists_nothing_when_llm_fails(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=KEEP_RECENT_MESSAGES + 5)
        fake = FakeSummarizationAgent(raises=RuntimeError("LLM API error"))
        service = CompactionService(repo_factory, _as_agent(fake))

        assert await service.run_compaction(conversation_id) is None
        assert await conversation_repo.get_latest_summary(conversation_id) is None

    @pytest.mark.asyncio
    async def test_combines_with_existing_summary(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        # First compaction produces "First summary."
        await _seed_messages(conversation_repo, conversation_id, count=KEEP_RECENT_MESSAGES + 5)
        first_agent = FakeSummarizationAgent(output="First summary.")
        first_service = CompactionService(repo_factory, _as_agent(first_agent))
        first = await first_service.run_compaction(conversation_id)
        assert first is not None

        # Add more messages that exceed threshold again, then compact.
        await _seed_messages(
            conversation_repo,
            conversation_id,
            count=KEEP_RECENT_MESSAGES + 5,
            start_idx=KEEP_RECENT_MESSAGES + 5 + 1,
        )
        second_agent = FakeSummarizationAgent(output="Newer activity summary.")
        second_service = CompactionService(repo_factory, _as_agent(second_agent))
        second = await second_service.run_compaction(conversation_id)

        assert second is not None
        assert "[Previous summary context]" in second.summary_text
        assert "First summary." in second.summary_text
        assert "[Recent activity]" in second.summary_text
        assert "Newer activity summary." in second.summary_text


# --- use-case tests: load_messages_for_agent / load_all_messages_for_ui -------


class TestLoadMessagesForAgent:
    @pytest.mark.asyncio
    async def test_loads_all_messages_when_no_summary_exists(
        self,
        conversation_repo: ConversationRepositoryInterface,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=3, token_count=10)

        loaded = await load_messages_for_agent(conversation_id, conversation_repo)

        assert len(loaded) == 3
        assert all(m.kind == "request" for m in loaded)

    @pytest.mark.asyncio
    async def test_loads_summary_then_messages_after_when_summary_exists(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=KEEP_RECENT_MESSAGES + 3)
        service = CompactionService(repo_factory, _as_agent(FakeSummarizationAgent(output="Compacted.")))
        await service.run_compaction(conversation_id)

        loaded = await load_messages_for_agent(conversation_id, conversation_repo)

        # First message is the summary as a system prompt
        first = loaded[0]
        assert first.kind == "request"
        first_part = cast(SystemPromptPart, first.parts[0])
        assert first_part.part_kind == "system-prompt"
        assert "[Previous conversation summary]" in first_part.content
        assert "Compacted." in first_part.content

        # Followed by the KEEP_RECENT_MESSAGES messages that weren't compacted
        assert len(loaded) == 1 + KEEP_RECENT_MESSAGES


class TestLoadAllMessagesForUI:
    @pytest.mark.asyncio
    async def test_returns_all_messages_when_no_summary(
        self,
        conversation_repo: ConversationRepositoryInterface,
        conversation_id: str,
    ) -> None:
        await _seed_messages(conversation_repo, conversation_id, count=4, token_count=10)

        loaded = await load_all_messages_for_ui(conversation_id, conversation_repo)

        assert len(loaded) == 4

    @pytest.mark.asyncio
    async def test_returns_full_history_even_when_summary_exists(
        self,
        conversation_repo: ConversationRepositoryInterface,
        repo_factory: RepositoryFactory,
        conversation_id: str,
    ) -> None:
        total = KEEP_RECENT_MESSAGES + 5
        await _seed_messages(conversation_repo, conversation_id, count=total)
        service = CompactionService(repo_factory, _as_agent(FakeSummarizationAgent()))
        await service.run_compaction(conversation_id)

        ui_loaded = await load_all_messages_for_ui(conversation_id, conversation_repo)
        agent_loaded = await load_messages_for_agent(conversation_id, conversation_repo)

        assert len(ui_loaded) == total  # UI sees everything
        assert len(agent_loaded) == 1 + KEEP_RECENT_MESSAGES  # agent sees summary + tail
        assert agent_loaded[0].parts[0].part_kind == "system-prompt"

    @pytest.mark.asyncio
    async def test_empty_conversation_returns_empty(
        self,
        conversation_repo: ConversationRepositoryInterface,
        conversation_id: str,
    ) -> None:
        assert await load_all_messages_for_ui(conversation_id, conversation_repo) == []
