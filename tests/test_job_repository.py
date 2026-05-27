"""JobRepository against in-memory SQLite — real implementation, real schema.

Covers the dedup invariant the scraper depends on: re-seeing a posting must
update derived fields and last_seen but never clobber the user's status.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.entities.job import JobCategory, JobSourceName, JobStatus, JobVerdict, ScrapedJob
from backend.infrastructure.db.models import job as _job_models  # noqa: F401
from backend.infrastructure.db.models.base import Base
from backend.infrastructure.db.repositories.job_repository import JobRepository


@pytest_asyncio.fixture
async def job_repo() -> AsyncIterator[JobRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker() as session:
        yield JobRepository(session)
    await engine.dispose()


def _scraped(external_id: str, title: str = "Myyjä") -> ScrapedJob:
    return ScrapedJob(
        source=JobSourceName.DUUNITORI,
        external_id=external_id,
        title=title,
        employer="Tiger",
        location="Helsinki",
        url=f"https://duunitori.fi/tyopaikat/tyo/{external_id}",
        description="Myymälätyötä",
    )


def _verdict(score: int, category: JobCategory = JobCategory.RETAIL) -> JobVerdict:
    return JobVerdict(category=category, relevance_score=score, match_reason="ok")


@pytest.mark.asyncio
async def test_upsert_inserts_new_jobs(job_repo: JobRepository):
    inserted = await job_repo.upsert_many(
        [(_scraped("a"), _verdict(20)), (_scraped("b"), _verdict(20))]
    )
    assert inserted == 2
    jobs = await job_repo.list()
    assert len(jobs) == 2
    assert {j.status for j in jobs} == {JobStatus.NEW}


@pytest.mark.asyncio
async def test_upsert_dedups_on_source_and_external_id(job_repo: JobRepository):
    await job_repo.upsert_many([(_scraped("a"), _verdict(20))])
    inserted = await job_repo.upsert_many([(_scraped("a", title="Myyjä päivitetty"), _verdict(30))])
    assert inserted == 0
    jobs = await job_repo.list()
    assert len(jobs) == 1
    assert jobs[0].title == "Myyjä päivitetty"
    assert jobs[0].relevance_score == 30


@pytest.mark.asyncio
async def test_upsert_preserves_user_status(job_repo: JobRepository):
    await job_repo.upsert_many([(_scraped("a"), _verdict(20))])
    jobs = await job_repo.list()
    await job_repo.update_status(jobs[0].id, JobStatus.APPLIED)

    await job_repo.upsert_many([(_scraped("a"), _verdict(25))])
    refreshed = await job_repo.list()
    assert refreshed[0].status == JobStatus.APPLIED
    assert refreshed[0].relevance_score == 25


@pytest.mark.asyncio
async def test_list_filters_by_min_relevance(job_repo: JobRepository):
    await job_repo.upsert_many(
        [(_scraped("a"), _verdict(5)), (_scraped("b"), _verdict(40))]
    )
    relevant = await job_repo.list(min_relevance=10)
    assert [j.external_id for j in relevant] == ["b"]


@pytest.mark.asyncio
async def test_list_orders_by_relevance_desc(job_repo: JobRepository):
    await job_repo.upsert_many(
        [(_scraped("low"), _verdict(10)), (_scraped("high"), _verdict(90))]
    )
    jobs = await job_repo.list()
    assert [j.external_id for j in jobs] == ["high", "low"]


@pytest.mark.asyncio
async def test_update_status_returns_none_for_unknown_id(job_repo: JobRepository):
    assert await job_repo.update_status("does-not-exist", JobStatus.INTERESTED) is None


@pytest.mark.asyncio
async def test_save_application_persists_draft(job_repo: JobRepository):
    await job_repo.upsert_many([(_scraped("a"), _verdict(50))])
    job = (await job_repo.list())[0]

    saved = await job_repo.save_application(job.id, "Hei, olen kiinnostunut...", "Hae linkin kautta.")
    assert saved is not None
    assert saved.application_cover_letter == "Hei, olen kiinnostunut..."
    assert saved.application_how_to_apply == "Hae linkin kautta."

    fetched = await job_repo.get(job.id)
    assert fetched is not None
    assert fetched.application_cover_letter == "Hei, olen kiinnostunut..."


@pytest.mark.asyncio
async def test_save_application_returns_none_for_unknown_id(job_repo: JobRepository):
    assert await job_repo.save_application("nope", "x", "y") is None
