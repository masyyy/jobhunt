from datetime import datetime

from pydantic import BaseModel


class Message(BaseModel):
    """Individual message entity."""

    id: str | None = None
    conversation_id: str
    kind: str  # 'request' | 'response'
    content_json: str
    token_count: int = 0
    created_at: datetime
    user_text: str | None = None
    assistant_text: str | None = None


class ConversationSummary(BaseModel):
    """Compacted summary entity."""

    id: str | None = None
    conversation_id: str
    summary_text: str
    covers_until_message_id: str
    message_count: int
    token_count: int = 0
    created_at: datetime


class Conversation(BaseModel):
    """Conversation entity with messages and summaries."""

    id: str | None = None
    toolbox: str | None = None
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[Message] = []
    summaries: list[ConversationSummary] = []
