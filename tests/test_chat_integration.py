"""Integration tests for chat functionality and message persistence.

Architecture:
- Persistence: All messages saved individually to DB (no compaction)
- Runtime: Agent's history_processors compacts before sending to LLM
"""

from datetime import datetime

import pytest
from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart

from backend.api.routers.chat import extract_new_user_message
from backend.core.entities.conversation import Message
from backend.core.interfaces.conversation_repository import ConversationRepositoryInterface


class TestConversationRepository:
    """Tests for ConversationRepository."""

    @pytest.mark.asyncio
    async def test_create_conversation(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test creating a new conversation."""
        conversation = await conversation_repo.create_conversation()

        assert conversation.id is not None
        assert conversation.created_at is not None
        assert conversation.messages == []

    @pytest.mark.asyncio
    async def test_get_latest_conversation(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test getting the latest conversation."""
        await conversation_repo.create_conversation()
        conv2 = await conversation_repo.create_conversation()

        latest = await conversation_repo.get_latest_conversation()

        assert latest is not None
        assert latest.id == conv2.id

    @pytest.mark.asyncio
    async def test_add_message(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test adding a message to a conversation."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        message = Message(
            conversation_id=conversation.id,
            kind="request",
            content_json='[{"kind": "request", "parts": []}]',
            token_count=10,
            created_at=datetime.now(),
            user_text="Hello",
        )

        saved_message = await conversation_repo.add_message(message)

        assert saved_message.id is not None
        assert saved_message.conversation_id == conversation.id
        assert saved_message.kind == "request"
        assert saved_message.user_text == "Hello"

    @pytest.mark.asyncio
    async def test_get_messages(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test retrieving messages for a conversation."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        for i in range(3):
            message = Message(
                conversation_id=conversation.id,
                kind="request" if i % 2 == 0 else "response",
                content_json=f'[{{"kind": "test", "content": "msg{i}"}}]',
                token_count=10 * (i + 1),
                created_at=datetime.now(),
            )
            await conversation_repo.add_message(message)

        messages = await conversation_repo.get_messages(conversation.id)

        assert len(messages) == 3
        for i, msg in enumerate(messages):
            assert msg.token_count == 10 * (i + 1)

    @pytest.mark.asyncio
    async def test_get_total_tokens(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test calculating total tokens for a conversation."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        for _ in range(3):
            message = Message(
                conversation_id=conversation.id,
                kind="request",
                content_json="{}",
                token_count=100,
                created_at=datetime.now(),
            )
            await conversation_repo.add_message(message)

        assert await conversation_repo.get_total_tokens(conversation.id) == 300

    @pytest.mark.asyncio
    async def test_conversation_not_found(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test getting a non-existent conversation."""
        assert await conversation_repo.get_conversation("non-existent-id") is None

    @pytest.mark.asyncio
    async def test_messages_after(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test getting messages after a specific message."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        messages = []
        for i in range(5):
            message = Message(
                conversation_id=conversation.id,
                kind="request",
                content_json=f'{{"index": {i}}}',
                token_count=10,
                created_at=datetime.now(),
            )
            saved = await conversation_repo.add_message(message)
            messages.append(saved)

        after_messages = await conversation_repo.get_messages_after(conversation.id, messages[1].id)

        assert len(after_messages) == 3  # messages 2, 3, 4


class TestDeleteConversation:
    """Tests for delete_conversation repository method and cascade behavior."""

    @pytest.mark.asyncio
    async def test_delete_conversation_removes_it(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Deleting a conversation should remove it and return True."""
        conv = await conversation_repo.create_conversation()
        assert conv.id is not None

        result = await conversation_repo.delete_conversation(conv.id)

        assert result is True
        assert await conversation_repo.get_conversation(conv.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_conversation_returns_false(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Deleting a conversation that doesn't exist should return False."""
        assert await conversation_repo.delete_conversation("nonexistent-id") is False

    @pytest.mark.asyncio
    async def test_delete_cascades_to_messages_and_summaries(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Deleting a conversation should also remove its messages and summaries."""
        conv = await conversation_repo.create_conversation()
        assert conv.id is not None

        for i in range(3):
            await conversation_repo.add_message(
                Message(
                    conversation_id=conv.id,
                    kind="request",
                    content_json=f'{{"msg": {i}}}',
                    token_count=10,
                    created_at=datetime.now(),
                    user_text=f"Message {i}",
                )
            )

        assert len(await conversation_repo.get_messages(conv.id)) == 3

        await conversation_repo.delete_conversation(conv.id)
        assert len(await conversation_repo.get_messages(conv.id)) == 0

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_conversations(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Deleting one conversation should leave others intact."""
        conv1 = await conversation_repo.create_conversation()
        conv2 = await conversation_repo.create_conversation()
        assert conv1.id is not None
        assert conv2.id is not None

        await conversation_repo.add_message(
            Message(
                conversation_id=conv1.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="conv1 message",
            )
        )
        await conversation_repo.add_message(
            Message(
                conversation_id=conv2.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="conv2 message",
            )
        )

        await conversation_repo.delete_conversation(conv1.id)

        assert await conversation_repo.get_conversation(conv2.id) is not None
        messages = await conversation_repo.get_messages(conv2.id)
        assert len(messages) == 1
        assert messages[0].user_text == "conv2 message"


class TestMessagePersistence:
    """Tests for message persistence across sessions."""

    @pytest.mark.asyncio
    async def test_messages_persist_across_queries(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Test that messages persist and can be retrieved."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        message = Message(
            conversation_id=conversation.id,
            kind="request",
            content_json='{"test": "data"}',
            token_count=50,
            created_at=datetime.now(),
            user_text="Test message",
        )
        await conversation_repo.add_message(message)

        retrieved_messages = await conversation_repo.get_messages(conversation.id)

        assert len(retrieved_messages) == 1
        assert retrieved_messages[0].user_text == "Test message"
        assert retrieved_messages[0].content_json == '{"test": "data"}'


class TestPersistenceArchitecture:
    """Tests to verify persistence saves ALL messages without compaction."""

    @pytest.mark.asyncio
    async def test_all_messages_saved_individually(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """All messages should be saved individually to the database."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        for i in range(20):
            message = Message(
                conversation_id=conversation.id,
                kind="request" if i % 2 == 0 else "response",
                content_json=f'{{"message": {i}}}',
                token_count=100,
                created_at=datetime.now(),
            )
            await conversation_repo.add_message(message)

        messages = await conversation_repo.get_messages(conversation.id)
        assert len(messages) == 20

    @pytest.mark.asyncio
    async def test_messages_preserved_with_full_content(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Message content_json should be preserved exactly as stored."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        complex_json = '{"parts": [{"type": "user-prompt", "content": "Hello"}], "kind": "request"}'
        message = Message(
            conversation_id=conversation.id,
            kind="request",
            content_json=complex_json,
            token_count=50,
            created_at=datetime.now(),
        )
        await conversation_repo.add_message(message)

        messages = await conversation_repo.get_messages(conversation.id)
        assert len(messages) == 1
        assert messages[0].content_json == complex_json

    @pytest.mark.asyncio
    async def test_token_counts_preserved(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Token counts should be preserved for each message."""
        conversation = await conversation_repo.create_conversation()
        assert conversation.id is not None

        token_counts = [100, 250, 500, 1000]
        for count in token_counts:
            message = Message(
                conversation_id=conversation.id,
                kind="request",
                content_json="{}",
                token_count=count,
                created_at=datetime.now(),
            )
            await conversation_repo.add_message(message)

        messages = await conversation_repo.get_messages(conversation.id)
        retrieved_counts = [m.token_count for m in messages]
        assert retrieved_counts == token_counts

        assert await conversation_repo.get_total_tokens(conversation.id) == sum(token_counts)


class TestExtractNewUserMessage:
    """Tests for extract_new_user_message from chat.py.

    The chat endpoint extracts the last message from the request and only
    persists it if it's a valid user prompt (ModelRequest with UserPromptPart).
    """

    def test_extracts_valid_user_prompt(self) -> None:
        """Should extract a valid user prompt as the last message."""
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi!")]),
            ModelRequest(parts=[UserPromptPart(content="New message")]),
        ]
        result = extract_new_user_message(messages)
        assert len(result) == 1
        part = result[0].parts[0]
        assert isinstance(part, UserPromptPart)
        assert part.content == "New message"

    def test_rejects_response_as_last_message(self) -> None:
        """Should not persist if the last message is a ModelResponse."""
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi!")]),
        ]
        assert extract_new_user_message(messages) == []

    def test_rejects_request_without_user_prompt_part(self) -> None:
        """Should not persist a ModelRequest that has no UserPromptPart."""
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="You are a helpful assistant")]),
        ]
        assert extract_new_user_message(messages) == []

    def test_handles_empty_messages(self) -> None:
        """Should return empty list for empty input."""
        assert extract_new_user_message([]) == []


class TestListConversations:
    """Tests for the list_conversations repository method."""

    @pytest.mark.asyncio
    async def test_list_conversations_returns_ordered_by_updated_at(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Conversations should be ordered by updated_at descending."""
        conv1 = await conversation_repo.create_conversation()
        conv2 = await conversation_repo.create_conversation()
        conv3 = await conversation_repo.create_conversation()

        result = await conversation_repo.list_conversations()

        assert len(result) == 3
        assert result[0].id == conv3.id
        assert result[1].id == conv2.id
        assert result[2].id == conv1.id

    @pytest.mark.asyncio
    async def test_list_conversations_includes_first_user_message(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Each conversation should include its first user message for title derivation."""
        conv = await conversation_repo.create_conversation()
        assert conv.id is not None

        await conversation_repo.add_message(
            Message(
                conversation_id=conv.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="First user message",
            )
        )
        await conversation_repo.add_message(
            Message(
                conversation_id=conv.id,
                kind="response",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                assistant_text="Response",
            )
        )
        await conversation_repo.add_message(
            Message(
                conversation_id=conv.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="Second user message",
            )
        )

        result = await conversation_repo.list_conversations()

        assert len(result) == 1
        assert len(result[0].messages) == 1
        assert result[0].messages[0].user_text == "First user message"

    @pytest.mark.asyncio
    async def test_list_conversations_empty_conversation_has_no_messages(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """A conversation with no user messages should have an empty messages list."""
        await conversation_repo.create_conversation()

        result = await conversation_repo.list_conversations()

        assert len(result) == 1
        assert result[0].messages == []

    @pytest.mark.asyncio
    async def test_list_conversations_respects_limit(self, conversation_repo: ConversationRepositoryInterface) -> None:
        """Should only return up to `limit` conversations."""
        for _ in range(5):
            await conversation_repo.create_conversation()

        result = await conversation_repo.list_conversations(limit=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_conversations_multiple_with_titles(
        self, conversation_repo: ConversationRepositoryInterface
    ) -> None:
        """Multiple conversations should each get their own first user message."""
        conv1 = await conversation_repo.create_conversation()
        assert conv1.id is not None
        await conversation_repo.add_message(
            Message(
                conversation_id=conv1.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="Hello from conv1",
            )
        )

        conv2 = await conversation_repo.create_conversation()
        assert conv2.id is not None
        await conversation_repo.add_message(
            Message(
                conversation_id=conv2.id,
                kind="request",
                content_json="{}",
                token_count=10,
                created_at=datetime.now(),
                user_text="Hello from conv2",
            )
        )

        result = await conversation_repo.list_conversations()

        assert len(result) == 2
        assert result[0].messages[0].user_text == "Hello from conv2"
        assert result[1].messages[0].user_text == "Hello from conv1"
