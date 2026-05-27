"""Conversation compaction service with persistent summaries.

Architecture:
- Lightweight sync history processor: Prunes tool outputs in old messages (no LLM)
- Async compaction service: Runs once when needed, persists summary to DB
- Smart loading: Uses stored summary + messages after it

References:
- https://github.com/sst/opencode (compaction.ts)
- https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a5f
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolReturnPart

from backend.core.entities.conversation import ConversationSummary, Message
from backend.core.interfaces.conversation_repository import ConversationRepositoryInterface, RepositoryFactory

logger = logging.getLogger(__name__)

# Compaction threshold in tokens (trigger compaction when exceeded)
COMPACTION_THRESHOLD_TOKENS = 100_000

# Keep the last N messages uncompacted to preserve immediate context
KEEP_RECENT_MESSAGES = 10

# Placeholder for pruned tool outputs
TOOL_OUTPUT_PLACEHOLDER = "[Output truncated for context efficiency]"

# Summarization prompt inspired by OpenCode's approach
SUMMARIZATION_PROMPT = """Provide a detailed summary for continuing this conversation. The new session will NOT have access to the conversation history above, only this summary.

Include:
1. **What was accomplished**: Key actions taken, files modified, problems solved
2. **Current state**: Where things stand now, any work in progress
3. **What's next**: Planned next steps or pending tasks
4. **Critical context**: User preferences, constraints, important decisions, file paths, or values that will be needed
5. **Errors encountered**: Any issues hit and how they were resolved (to avoid repeating)

Be thorough but concise. Preserve enough detail that the conversation can continue seamlessly."""

# Instructions for the summarization agent (used by dependencies.py to construct it)
SUMMARIZATION_AGENT_INSTRUCTIONS = (
    "You are a conversation summarizer. Create summaries that enable seamless continuation of work."
)

# Lock registry for preventing concurrent compaction per conversation
_compaction_locks: dict[str, asyncio.Lock] = {}


def _get_compaction_lock(conversation_id: str) -> asyncio.Lock:
    """Get or create a lock for the given conversation ID."""
    if conversation_id not in _compaction_locks:
        _compaction_locks[conversation_id] = asyncio.Lock()
    return _compaction_locks[conversation_id]


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 characters per token for English text."""
    return len(text) // 4


def _get_part_content(part: Any) -> str | None:
    """Safely extract text content from a message part, ignoring binary/media parts."""
    if hasattr(part, "content"):
        content = part.content
        if isinstance(content, str):
            return content
        # content may be a list of mixed types (str, BinaryContent, ImageUrl, etc.)
        # when file attachments are present — extract only the text portions.
        if isinstance(content, list | tuple):
            texts = [item for item in content if isinstance(item, str)]
            return " ".join(texts) if texts else None
        return None
    return None


def extract_text_from_message(msg: ModelMessage) -> tuple[str | None, str | None]:
    """Extract user and assistant text from a ModelMessage."""
    user_text = None
    assistant_text = None

    for part in msg.parts:
        content = _get_part_content(part)
        if content is None:
            continue

        part_kind = getattr(part, "part_kind", None)
        if msg.kind == "request" and part_kind == "user-prompt":
            user_text = content
        elif msg.kind == "response" and part_kind == "text":
            assistant_text = content

    return user_text, assistant_text


def prune_tool_outputs_processor(messages: list[ModelMessage]) -> list[ModelMessage]:
    """
    Lightweight sync processor - replaces tool outputs in old messages with placeholder.
    Preserves PydanticAI message structure (ToolReturnPart with same tool_name, tool_call_id).
    Only prunes messages older than KEEP_RECENT_MESSAGES.

    This is designed to be used with Agent(history_processors=[prune_tool_outputs_processor]).
    """
    if len(messages) <= KEEP_RECENT_MESSAGES:
        return messages

    recent_messages = messages[-KEEP_RECENT_MESSAGES:]
    old_messages = messages[:-KEEP_RECENT_MESSAGES]

    pruned_old: list[ModelMessage] = []
    for msg in old_messages:
        if msg.kind == "request":
            # Check for ToolReturnPart in parts
            new_parts = []
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    # Replace content with placeholder, keep structure
                    new_parts.append(
                        ToolReturnPart(
                            tool_name=part.tool_name,
                            content=TOOL_OUTPUT_PLACEHOLDER,
                            tool_call_id=part.tool_call_id,
                            timestamp=part.timestamp,
                        )
                    )
                else:
                    new_parts.append(part)
            pruned_old.append(ModelRequest(parts=new_parts))
        else:
            pruned_old.append(msg)

    return [*pruned_old, *recent_messages]


class CompactionService:
    """Service for managing conversation compaction with persistent summaries."""

    def __init__(self, repo_factory: RepositoryFactory, summarize_agent: Agent[None, str]) -> None:
        self._repo_factory = repo_factory
        self._summarize_agent = summarize_agent

    async def check_needs_compaction(self, conversation_id: str) -> bool:
        """Check if token count exceeds threshold and summary doesn't cover recent messages."""
        async with self._repo_factory() as repo:
            # Get latest summary
            summary = await repo.get_latest_summary(conversation_id)

            if summary:
                # Check tokens in messages after summary
                messages_after = await repo.get_messages_after(conversation_id, summary.covers_until_message_id)
                tokens_after = sum(m.token_count for m in messages_after)
                return tokens_after > COMPACTION_THRESHOLD_TOKENS
            else:
                # No summary - check total tokens
                total = await repo.get_total_tokens(conversation_id)
                return total > COMPACTION_THRESHOLD_TOKENS

    async def run_compaction(self, conversation_id: str) -> ConversationSummary | None:
        """Generate summary via LLM and persist to DB. Uses lock to prevent duplicates."""
        lock = _get_compaction_lock(conversation_id)

        async with lock:
            # Re-check if still needed (another task may have completed)
            if not await self.check_needs_compaction(conversation_id):
                logger.info(f"Compaction no longer needed for {conversation_id}")
                return None

            async with self._repo_factory() as repo:
                # Get latest summary to determine which messages to summarize
                existing_summary = await repo.get_latest_summary(conversation_id)

                if existing_summary:
                    # Get messages after the existing summary
                    all_messages = await repo.get_messages_after(
                        conversation_id, existing_summary.covers_until_message_id
                    )
                else:
                    # No summary - get all messages
                    all_messages = await repo.get_messages(conversation_id)

                if len(all_messages) <= KEEP_RECENT_MESSAGES:
                    logger.info(f"Not enough messages to compact for {conversation_id}")
                    return None

                # Split into messages to summarize and recent messages to keep
                messages_to_summarize = all_messages[:-KEEP_RECENT_MESSAGES]
                last_summarized_message = messages_to_summarize[-1]

                # Parse messages to ModelMessage format for summarization
                model_messages: list[ModelMessage] = []
                for msg_entity in messages_to_summarize:
                    try:
                        parsed = ModelMessagesTypeAdapter.validate_json(msg_entity.content_json)
                        model_messages.extend(parsed)
                    except Exception as e:
                        logger.warning(f"Failed to parse message {msg_entity.id}: {e}")

                if not model_messages:
                    logger.warning(f"No messages to summarize for {conversation_id}")
                    return None

                try:
                    # Generate summary via LLM
                    logger.info(f"Generating summary for {len(model_messages)} messages")
                    result = await self._summarize_agent.run(
                        SUMMARIZATION_PROMPT,
                        message_history=model_messages,
                    )
                    summary_text = str(result.output)

                    # Include previous summary context if exists
                    if existing_summary:
                        summary_text = (
                            f"[Previous summary context]\n{existing_summary.summary_text}\n\n"
                            f"[Recent activity]\n{summary_text}"
                        )

                    # Create summary entity
                    summary = ConversationSummary(
                        conversation_id=conversation_id,
                        summary_text=summary_text,
                        covers_until_message_id=last_summarized_message.id or "",
                        message_count=len(messages_to_summarize),
                        token_count=estimate_tokens(summary_text),
                        created_at=datetime.now(),
                    )

                    # Persist to DB
                    saved_summary = await repo.add_summary(summary)
                    logger.info(f"Compacted {len(messages_to_summarize)} messages into summary for {conversation_id}")

                    return saved_summary

                except Exception as e:
                    logger.error(f"Compaction failed for {conversation_id}: {e}")
                    return None


async def load_messages_for_agent(
    conversation_id: str,
    repo: ConversationRepositoryInterface,
) -> list[ModelMessage]:
    """
    Load messages from database using stored summary if available.

    If a summary exists, returns: [summary_message] + messages_after_summary
    Otherwise, returns all messages.
    """
    summary = await repo.get_latest_summary(conversation_id)

    if summary:
        # Load only messages AFTER the summary
        messages_after = await repo.get_messages_after(conversation_id, summary.covers_until_message_id)

        # Create summary as system message
        summary_message: ModelMessage = ModelRequest(
            parts=[SystemPromptPart(content=f"[Previous conversation summary]\n\n{summary.summary_text}")]
        )

        # Parse messages after summary
        parsed_messages: list[ModelMessage] = []
        for msg_entity in messages_after:
            try:
                parsed = ModelMessagesTypeAdapter.validate_json(msg_entity.content_json)
                parsed_messages.extend(parsed)
            except Exception as e:
                logger.warning(f"Failed to parse message {msg_entity.id}: {e}")

        logger.info(f"Loaded summary + {len(parsed_messages)} messages for {conversation_id}")
        return [summary_message, *parsed_messages]
    else:
        # No summary - load all messages
        return await _load_all_messages(repo, conversation_id)


async def load_all_messages_for_ui(
    conversation_id: str,
    repo: ConversationRepositoryInterface,
) -> list[ModelMessage]:
    """Load ALL messages from database for UI display (ignores compaction summaries)."""
    return await _load_all_messages(repo, conversation_id)


async def _load_all_messages(
    repo: ConversationRepositoryInterface,
    conversation_id: str,
) -> list[ModelMessage]:
    """Load all messages from database without summary."""
    all_entities = await repo.get_messages(conversation_id)
    all_messages: list[ModelMessage] = []
    for msg_entity in all_entities:
        try:
            parsed = ModelMessagesTypeAdapter.validate_json(msg_entity.content_json)
            all_messages.extend(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse message {msg_entity.id}: {e}")

    return all_messages


async def save_messages_to_db(
    conversation_id: str,
    new_messages: list[ModelMessage],
    repo: ConversationRepositoryInterface,
) -> None:
    """
    Save new messages to the database individually.
    Called from on_complete callback after streaming finishes.

    Note: All messages are persisted without compaction.
    Compaction only affects runtime LLM input via history_processors.
    """
    for msg in new_messages:
        # Serialize the message
        msg_json = ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")

        # Extract text for search
        user_text, assistant_text = extract_text_from_message(msg)

        # Estimate tokens
        token_count = estimate_tokens(msg_json)

        message = Message(
            conversation_id=conversation_id,
            kind=msg.kind,
            content_json=msg_json,
            token_count=token_count,
            created_at=datetime.now(),
            user_text=user_text,
            assistant_text=assistant_text,
        )

        await repo.add_message(message)
