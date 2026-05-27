"""scrape_jobs pipeline — the orchestration that gates which postings persist.

Exercised against the real in-memory JobRepository with a fake source and a
fake matcher (no network, no LLM). Covers the filters a silent regression would
break: 7-day recency, keyword pre-filter, and the matcher's yes/no verdict.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.entities.job import JobSourceName, ScrapedJob
from backend.core.interfaces.job_matcher import MatchResult
from backend.core.tasks.scrape_jobs import scrape_jobs
from backend.infrastructure.db.models import job as _job_models  # noqa: F401
from backend.infrastructure.db.models.base import Base
from backend.infrastructure.db.repositories.job_repository import JobRepository


@pytest_asyncio.fixture
async def repo_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[JobRepository]:
        async with sessionmaker() as session:
            yield JobRepository(session)

    yield _factory
    await engine.dispose()


class _FakeSource:
    name = "fake"

    def __init__(self, jobs: list[ScrapedJob]) -> None:
        self._jobs = jobs

    async def fetch(self) -> list[ScrapedJob]:
        return self._jobs


class _FakeMatcher:
    """Accepts/rejects based on a title->relevant map; records what it saw."""

    def __init__(self, verdicts: dict[str, bool]) -> None:
        self._verdicts = verdicts
        self.seen: list[str] = []

    async def match(self, job: ScrapedJob) -> MatchResult:
        self.seen.append(job.title)
        relevant = self._verdicts.get(job.title, True)
        return MatchResult(relevant=relevant, reason="reason for " + job.title)


def _job(external_id: str, title: str, *, location: str = "Helsinki", age_days: int = 0) -> ScrapedJob:
    return ScrapedJob(
        source=JobSourceName.DUUNITORI,
        external_id=external_id,
        title=title,
        location=location,
        url=f"https://duunitori.fi/tyopaikat/tyo/{external_id}",
        posted_at=datetime.now(UTC) - timedelta(days=age_days),
    )


@pytest.mark.asyncio
async def test_accepts_matched_job_and_stores_reason(repo_factory):
    source = _FakeSource([_job("a", "Myyjä")])
    matcher = _FakeMatcher({"Myyjä": True})

    inserted = await scrape_jobs(sources=[source], repo_factory=repo_factory, matcher=matcher)

    assert inserted == 1
    async with repo_factory() as repo:
        jobs = await repo.list()
    assert len(jobs) == 1
    assert jobs[0].match_reason == "reason for Myyjä"
    assert jobs[0].relevance_score >= 10


@pytest.mark.asyncio
async def test_matcher_rejection_drops_job(repo_factory):
    source = _FakeSource([_job("a", "Myyjä")])
    matcher = _FakeMatcher({"Myyjä": False})

    inserted = await scrape_jobs(sources=[source], repo_factory=repo_factory, matcher=matcher)

    assert inserted == 0
    async with repo_factory() as repo:
        assert await repo.list() == []


@pytest.mark.asyncio
async def test_keyword_prefilter_skips_matcher_for_irrelevant_titles(repo_factory):
    # "Ohjelmistokehittäjä" matches no target keyword -> never reaches the matcher.
    source = _FakeSource([_job("a", "Ohjelmistokehittäjä"), _job("b", "Myyjä")])
    matcher = _FakeMatcher({})

    await scrape_jobs(sources=[source], repo_factory=repo_factory, matcher=matcher)

    assert matcher.seen == ["Myyjä"]


@pytest.mark.asyncio
async def test_old_posting_is_dropped(repo_factory):
    source = _FakeSource([_job("a", "Myyjä", age_days=10)])
    matcher = _FakeMatcher({})

    inserted = await scrape_jobs(sources=[source], repo_factory=repo_factory, matcher=matcher)

    assert inserted == 0
    assert matcher.seen == []


@pytest.mark.asyncio
async def test_out_of_region_posting_is_dropped(repo_factory):
    source = _FakeSource([_job("a", "Myyjä", location="Tampere")])
    matcher = _FakeMatcher({})

    inserted = await scrape_jobs(sources=[source], repo_factory=repo_factory, matcher=matcher)

    assert inserted == 0
    assert matcher.seen == []
