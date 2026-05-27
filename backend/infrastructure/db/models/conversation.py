from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.db.models.base import Base


class Conversation(Base):
    """Conversation with message history."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    toolbox: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    summaries: Mapped[list[ConversationSummary]] = relationship(
        "ConversationSummary", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """Individual PydanticAI message for queryability and compaction."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'request' | 'response'
    content_json: Mapped[str] = mapped_column(Text, nullable=False)  # Full ModelMessage as JSON
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Extracted fields for search (nullable)
    user_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_created_at", "created_at"),
    )


class ConversationSummary(Base):
    """Compacted summaries created by history processor."""

    __tablename__ = "conversation_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Which message this summary covers up to (messages before this were summarized)
    covers_until_message_id: Mapped[str] = mapped_column(String(36), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)  # How many messages were summarized
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Tokens in the summary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationship
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="summaries")

    __table_args__ = (Index("ix_conversation_summaries_conversation_id", "conversation_id"),)
