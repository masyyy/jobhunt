"""Tests verifying the agent run is decoupled from the HTTP response.

When a client disconnects mid-stream, the SSE consumer stops reading
from the queue, but the producer task must continue iterating
adapter.run_stream() to completion so on_complete fires and messages
get persisted.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.routers.chat import _run_agent_detached  # pyright: ignore[reportPrivateUsage]
from backend.core.interfaces.conversation_repository import ConversationRepositoryInterface, RepositoryFactory
from backend.core.services.compaction import save_messages_to_db
from backend.infrastructure.db.models.base import Base
from backend.infrastructure.db.repositories.conversation_repository import ConversationRepository


@asynccontextmanager
async def _make_test_repo_factory() -> AsyncIterator[RepositoryFactory]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[ConversationRepositoryInterface]:
        async with session_maker() as session:
            yield ConversationRepository(session)

    try:
        yield _factory
    finally:
        await engine.dispose()


class _FakeResult:
    """Minimal stand-in for AgentRunResult that carries new_messages()."""

    def __init__(self, messages: list[ModelMessage]) -> None:
        self._messages = messages

    def new_messages(self) -> list[ModelMessage]:
        return self._messages


class _FakeAdapter:
    """Stub adapter whose run_stream emits N events with sleeps between them,
    then invokes on_complete with a fake result. Mirrors how VercelAIAdapter's
    transform_stream calls on_complete on AgentRunResultEvent.
    """

    def __init__(self, events: list[str], result_messages: list[ModelMessage], delay: float = 0.05) -> None:
        self._events = events
        self._result_messages = result_messages
        self._delay = delay

    def run_stream(self, *, on_complete: Any, **_kwargs: Any) -> AsyncIterator[Any]:
        events = self._events
        delay = self._delay
        result_messages = self._result_messages

        async def _gen() -> AsyncIterator[Any]:
            for ev in events:
                await asyncio.sleep(delay)
                yield ev
            # After the stream completes, invoke on_complete (mirrors transform_stream).
            result = _FakeResult(result_messages)
            async for extra in on_complete(result):
                yield extra

        return _gen()


def _user_message(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_message(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


@pytest.mark.asyncio
async def test_on_complete_fires_when_consumer_disconnects() -> None:
    """The producer must drive the stream to completion even if nobody
    drains the queue, so on_complete persists messages."""
    async with _make_test_repo_factory() as repo_factory:
        async with repo_factory() as repo:
            conversation = await repo.create_conversation()
        conversation_id = conversation.id
        assert conversation_id is not None

        user_messages = [_user_message("hello")]
        assistant_messages = [_assistant_message("hi there")]

        completed = asyncio.Event()

        async def on_complete(result: Any) -> AsyncIterator[Any]:
            try:
                async with repo_factory() as repo:
                    conv = await repo.get_conversation(conversation_id)
                    if conv is None:
                        return
                    await save_messages_to_db(conversation_id, user_messages + result.new_messages(), repo)
            finally:
                completed.set()
            return
            yield  # make this an async generator

        adapter = _FakeAdapter(
            events=["event-1", "event-2", "event-3"],
            result_messages=assistant_messages,
            delay=0.02,
        )
        queue: asyncio.Queue[Any] = asyncio.Queue()

        task = asyncio.create_task(
            _run_agent_detached(
                adapter,  # type: ignore[arg-type]
                message_history=[],
                deps=None,  # type: ignore[arg-type]
                model_settings=None,
                on_complete=on_complete,
                queue=queue,
                conversation_id=conversation_id,
                user_messages=user_messages,
                repo_factory=repo_factory,
            )
        )

        # Simulate client disconnect: read one event, then stop draining.
        first = await queue.get()
        assert first == "event-1"
        # Do NOT drain further. The producer should still complete and on_complete should fire.

        await asyncio.wait_for(completed.wait(), timeout=2.0)
        await asyncio.wait_for(task, timeout=2.0)

        async with repo_factory() as repo:
            messages = await repo.get_messages(conversation_id)

        assert len(messages) == 2
        kinds = [m.kind for m in messages]
        assert "request" in kinds
        assert "response" in kinds
        user_texts = [m.user_text for m in messages if m.user_text]
        assistant_texts = [m.assistant_text for m in messages if m.assistant_text]
        assert "hello" in user_texts
        assert "hi there" in assistant_texts


@pytest.mark.asyncio
async def test_user_message_persisted_when_agent_raises() -> None:
    """If the agent stream raises before on_complete fires, the user
    message should still be persisted as a fallback so the conversation
    is not silently empty."""
    async with _make_test_repo_factory() as repo_factory:
        async with repo_factory() as repo:
            conversation = await repo.create_conversation()
        conversation_id = conversation.id
        assert conversation_id is not None

        user_messages = [_user_message("question that fails")]

        class _FailingAdapter:
            def run_stream(self, **_: Any) -> AsyncIterator[Any]:
                async def _gen() -> AsyncIterator[Any]:
                    yield "event-1"
                    raise RuntimeError("model exploded")

                return _gen()

        async def on_complete(_: Any) -> AsyncIterator[Any]:
            return
            yield

        queue: asyncio.Queue[Any] = asyncio.Queue()
        task = asyncio.create_task(
            _run_agent_detached(
                _FailingAdapter(),  # type: ignore[arg-type]
                message_history=[],
                deps=None,  # type: ignore[arg-type]
                model_settings=None,
                on_complete=on_complete,
                queue=queue,
                conversation_id=conversation_id,
                user_messages=user_messages,
                repo_factory=repo_factory,
            )
        )

        await asyncio.wait_for(task, timeout=2.0)

        async with repo_factory() as repo:
            messages = await repo.get_messages(conversation_id)

        assert len(messages) == 1
        assert messages[0].user_text == "question that fails"


@pytest.mark.asyncio
async def test_sentinel_is_always_enqueued_for_consumer() -> None:
    """The producer must put a None sentinel in the queue in its finally
    block, so a connected consumer never hangs after the stream ends."""
    async with _make_test_repo_factory() as repo_factory:
        async with repo_factory() as repo:
            conversation = await repo.create_conversation()
        conversation_id = conversation.id
        assert conversation_id is not None

        adapter = _FakeAdapter(events=["e1"], result_messages=[], delay=0.0)
        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def on_complete(_: Any) -> AsyncIterator[Any]:
            return
            yield

        task = asyncio.create_task(
            _run_agent_detached(
                adapter,  # type: ignore[arg-type]
                message_history=[],
                deps=None,  # type: ignore[arg-type]
                model_settings=None,
                on_complete=on_complete,
                queue=queue,
                conversation_id=conversation_id,
                user_messages=[],
                repo_factory=repo_factory,
            )
        )

        collected: list[Any] = []
        while True:
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
            if item is None:
                break
            collected.append(item)

        await asyncio.wait_for(task, timeout=2.0)
        assert collected == ["e1"]


@pytest.mark.asyncio
async def test_bounded_queue_drops_events_but_completes_run() -> None:
    """When the consumer stops draining and the queue fills, the producer
    must drop further events (not block) and still drive on_complete to
    fire. The sentinel must still be deliverable to the consumer."""
    async with _make_test_repo_factory() as repo_factory:
        async with repo_factory() as repo:
            conversation = await repo.create_conversation()
        conversation_id = conversation.id
        assert conversation_id is not None

        user_messages = [_user_message("hi")]
        assistant_messages = [_assistant_message("done")]

        completed = asyncio.Event()

        async def on_complete(result: Any) -> AsyncIterator[Any]:
            try:
                async with repo_factory() as repo:
                    await save_messages_to_db(conversation_id, user_messages + result.new_messages(), repo)
            finally:
                completed.set()
            return
            yield

        # Many more events than the queue can hold.
        adapter = _FakeAdapter(
            events=[f"e{i}" for i in range(50)],
            result_messages=assistant_messages,
            delay=0.0,
        )
        # Tiny queue so the producer hits QueueFull quickly.
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=4)

        task = asyncio.create_task(
            _run_agent_detached(
                adapter,  # type: ignore[arg-type]
                message_history=[],
                deps=None,  # type: ignore[arg-type]
                model_settings=None,
                on_complete=on_complete,
                queue=queue,
                conversation_id=conversation_id,
                user_messages=user_messages,
                repo_factory=repo_factory,
            )
        )

        # Don't drain the queue at all — simulate a fully disconnected client.
        await asyncio.wait_for(completed.wait(), timeout=2.0)
        await asyncio.wait_for(task, timeout=2.0)

        async with repo_factory() as repo:
            messages = await repo.get_messages(conversation_id)
        assert len(messages) == 2

        # Sentinel is reachable — consumer would exit cleanly.
        sentinel_seen = False
        while not queue.empty():
            if queue.get_nowait() is None:
                sentinel_seen = True
        assert sentinel_seen
