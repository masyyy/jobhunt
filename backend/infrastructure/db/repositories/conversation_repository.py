import uuid
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.entities.conversation import Conversation, ConversationSummary, Message
from backend.infrastructure.db.models.conversation import Conversation as ConversationModel
from backend.infrastructure.db.models.conversation import ConversationSummary as SummaryModel
from backend.infrastructure.db.models.conversation import Message as MessageModel


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _message_to_entity(self, db_msg: MessageModel) -> Message:
        return Message(
            id=db_msg.id,
            conversation_id=db_msg.conversation_id,
            kind=db_msg.kind,
            content_json=db_msg.content_json,
            token_count=db_msg.token_count,
            created_at=db_msg.created_at,
            user_text=db_msg.user_text,
            assistant_text=db_msg.assistant_text,
        )

    def _summary_to_entity(self, db_summary: SummaryModel) -> ConversationSummary:
        return ConversationSummary(
            id=db_summary.id,
            conversation_id=db_summary.conversation_id,
            summary_text=db_summary.summary_text,
            covers_until_message_id=db_summary.covers_until_message_id,
            message_count=db_summary.message_count,
            token_count=db_summary.token_count,
            created_at=db_summary.created_at,
        )

    def _conversation_to_entity(self, db_conv: ConversationModel) -> Conversation:
        return Conversation(
            id=db_conv.id,
            toolbox=db_conv.toolbox,
            user_id=db_conv.user_id,
            created_at=db_conv.created_at,
            updated_at=db_conv.updated_at,
            messages=[self._message_to_entity(m) for m in db_conv.messages],
            summaries=[self._summary_to_entity(s) for s in db_conv.summaries],
        )

    async def create_conversation(self, *, toolbox: str | None = None, user_id: str | None = None) -> Conversation:
        try:
            now = datetime.now()
            db_conversation = ConversationModel(
                id=str(uuid.uuid4()),
                toolbox=toolbox,
                user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(db_conversation)
            await self.session.commit()
            await self.session.refresh(db_conversation)

            return Conversation(
                id=db_conversation.id,
                toolbox=db_conversation.toolbox,
                user_id=db_conversation.user_id,
                created_at=db_conversation.created_at,
                updated_at=db_conversation.updated_at,
                messages=[],
                summaries=[],
            )
        except Exception:
            await self.session.rollback()
            raise

    async def get_conversation(self, conversation_id: str, *, user_id: str | None = None) -> Conversation | None:
        try:
            stmt = (
                select(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .options(selectinload(ConversationModel.messages), selectinload(ConversationModel.summaries))
            )
            if user_id is not None:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            result = await self.session.execute(stmt)
            db_conversation = result.scalar_one_or_none()

            if not db_conversation:
                return None

            return self._conversation_to_entity(db_conversation)
        except Exception:
            await self.session.rollback()
            raise

    async def get_latest_conversation(
        self, *, toolbox: str | None = None, user_id: str | None = None
    ) -> Conversation | None:
        try:
            stmt = (
                select(ConversationModel)
                .order_by(desc(ConversationModel.updated_at))
                .limit(1)
                .options(selectinload(ConversationModel.messages), selectinload(ConversationModel.summaries))
            )
            if toolbox is not None:
                stmt = stmt.where(ConversationModel.toolbox == toolbox)
            if user_id is not None:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            result = await self.session.execute(stmt)
            db_conversation = result.scalar_one_or_none()

            if not db_conversation:
                return None

            return self._conversation_to_entity(db_conversation)
        except Exception:
            await self.session.rollback()
            raise

    async def add_message(self, message: Message) -> Message:
        try:
            db_message = MessageModel(
                id=message.id or str(uuid.uuid4()),
                conversation_id=message.conversation_id,
                kind=message.kind,
                content_json=message.content_json,
                token_count=message.token_count,
                created_at=message.created_at,
                user_text=message.user_text,
                assistant_text=message.assistant_text,
            )
            self.session.add(db_message)
            await self.session.commit()
            await self.session.refresh(db_message)

            return self._message_to_entity(db_message)
        except Exception:
            await self.session.rollback()
            raise

    async def get_messages(self, conversation_id: str) -> list[Message]:
        try:
            result = await self.session.execute(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at)
            )
            db_messages = result.scalars().all()
            return [self._message_to_entity(m) for m in db_messages]
        except Exception:
            await self.session.rollback()
            raise

    async def get_total_tokens(self, conversation_id: str) -> int:
        try:
            result = await self.session.execute(
                select(func.sum(MessageModel.token_count)).where(MessageModel.conversation_id == conversation_id)
            )
            total = result.scalar()
            return total or 0
        except Exception:
            await self.session.rollback()
            raise

    async def add_summary(self, summary: ConversationSummary) -> ConversationSummary:
        try:
            db_summary = SummaryModel(
                id=summary.id or str(uuid.uuid4()),
                conversation_id=summary.conversation_id,
                summary_text=summary.summary_text,
                covers_until_message_id=summary.covers_until_message_id,
                message_count=summary.message_count,
                token_count=summary.token_count,
                created_at=summary.created_at,
            )
            self.session.add(db_summary)
            await self.session.commit()
            await self.session.refresh(db_summary)

            return self._summary_to_entity(db_summary)
        except Exception:
            await self.session.rollback()
            raise

    async def get_latest_summary(self, conversation_id: str) -> ConversationSummary | None:
        try:
            result = await self.session.execute(
                select(SummaryModel)
                .where(SummaryModel.conversation_id == conversation_id)
                .order_by(desc(SummaryModel.created_at))
                .limit(1)
            )
            db_summary = result.scalar_one_or_none()

            if not db_summary:
                return None

            return self._summary_to_entity(db_summary)
        except Exception:
            await self.session.rollback()
            raise

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages/summaries. Returns True if deleted."""
        try:
            result = await self.session.execute(
                select(ConversationModel).where(ConversationModel.id == conversation_id)
            )
            db_conversation = result.scalar_one_or_none()
            if not db_conversation:
                return False
            await self.session.delete(db_conversation)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            raise

    async def list_conversations(
        self, *, limit: int = 30, toolbox: str | None = None, user_id: str | None = None
    ) -> list[Conversation]:
        """List conversations ordered by updated_at desc, with first user message text for title.

        Uses a single query with a correlated subquery to avoid N+1.
        """
        try:
            # Subquery: earliest user message id per conversation
            first_msg_id_subq = (
                select(MessageModel.id)
                .where(MessageModel.conversation_id == ConversationModel.id)
                .where(MessageModel.user_text.isnot(None))
                .order_by(MessageModel.created_at)
                .limit(1)
                .correlate(ConversationModel)
                .scalar_subquery()
                .label("first_msg_id")
            )

            # Main query: conversations with optional first user message via outer join
            stmt = (
                select(ConversationModel, MessageModel)
                .outerjoin(MessageModel, MessageModel.id == first_msg_id_subq)
                .order_by(desc(ConversationModel.updated_at))
                .limit(limit)
            )
            if toolbox is not None:
                stmt = stmt.where(ConversationModel.toolbox == toolbox)
            if user_id is not None:
                stmt = stmt.where(ConversationModel.user_id == user_id)
            result = await self.session.execute(stmt)
            rows = result.all()

            conversations = []
            for db_conv, first_msg in rows:
                conv = Conversation(
                    id=db_conv.id,
                    toolbox=db_conv.toolbox,
                    user_id=db_conv.user_id,
                    created_at=db_conv.created_at,
                    updated_at=db_conv.updated_at,
                    messages=[self._message_to_entity(first_msg)] if first_msg else [],
                    summaries=[],
                )
                conversations.append(conv)
            return conversations
        except Exception:
            await self.session.rollback()
            raise

    async def get_messages_after(self, conversation_id: str, after_message_id: str) -> list[Message]:
        """Get messages created after the specified message ID."""
        try:
            # First get the created_at of the reference message
            ref_result = await self.session.execute(
                select(MessageModel.created_at).where(MessageModel.id == after_message_id)
            )
            ref_created_at = ref_result.scalar_one_or_none()

            if not ref_created_at:
                return []

            # Get messages after that timestamp
            result = await self.session.execute(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .where(MessageModel.created_at > ref_created_at)
                .order_by(MessageModel.created_at)
            )
            db_messages = result.scalars().all()
            return [self._message_to_entity(m) for m in db_messages]
        except Exception:
            await self.session.rollback()
            raise
