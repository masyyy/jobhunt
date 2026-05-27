from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from backend.core.entities.conversation import Conversation, ConversationSummary, Message

# A callable that returns an async context manager yielding a repository.
# Used by background tasks that outlive request scope.
RepositoryFactory = Callable[[], AbstractAsyncContextManager["ConversationRepositoryInterface"]]


class ConversationRepositoryInterface(Protocol):
    async def create_conversation(self, *, toolbox: str | None = None, user_id: str | None = None) -> Conversation: ...

    async def get_conversation(self, conversation_id: str, *, user_id: str | None = None) -> Conversation | None: ...

    async def get_latest_conversation(
        self, *, toolbox: str | None = None, user_id: str | None = None
    ) -> Conversation | None: ...

    async def add_message(self, message: Message) -> Message: ...

    async def get_messages(self, conversation_id: str) -> list[Message]: ...

    async def get_total_tokens(self, conversation_id: str) -> int: ...

    async def add_summary(self, summary: ConversationSummary) -> ConversationSummary: ...

    async def get_latest_summary(self, conversation_id: str) -> ConversationSummary | None: ...

    async def get_messages_after(self, conversation_id: str, after_message_id: str) -> list[Message]:
        """Get messages created after the specified message ID."""
        ...

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages/summaries. Returns True if deleted."""
        ...

    async def list_conversations(
        self, *, limit: int = 30, toolbox: str | None = None, user_id: str | None = None
    ) -> list[Conversation]:
        """List conversations ordered by updated_at desc, with only the first user message loaded."""
        ...
