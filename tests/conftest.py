"""Shared test fixtures.

Convention: prefer the real production implementation against an in-memory or
temp backing store. Fall back to a hand-written fake (under `tests/fakes/`)
only when no cheap real backing exists (LLM clients, external APIs).
Never use `MagicMock`/`AsyncMock` for `core/interfaces/*`. See CLAUDE.md.
"""

import asyncio
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Importing the model modules registers the tables on Base.metadata.
# We import the conversation models but skip the pgvector-backed
# document_chunks table — SQLite can't create it.
from backend.core.interfaces.conversation_repository import (
    ConversationRepositoryInterface,
    RepositoryFactory,
)
from backend.infrastructure.db.models import (
    conversation as _conversation_models,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from backend.infrastructure.db.models.base import Base
from backend.infrastructure.db.repositories.conversation_repository import ConversationRepository


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory SQLite session per test, with conversation schema applied."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def conversation_repo(db_session: AsyncSession) -> ConversationRepositoryInterface:
    """The real ConversationRepository against the in-memory SQLite session."""
    return ConversationRepository(db_session)


@pytest_asyncio.fixture
async def repo_factory(conversation_repo: ConversationRepositoryInterface) -> RepositoryFactory:
    """RepositoryFactory yielding the in-memory repo. For services that take a factory."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[ConversationRepositoryInterface]:
        yield conversation_repo

    return factory
