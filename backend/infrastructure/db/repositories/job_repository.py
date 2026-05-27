import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.entities.job import (
    Job,
    JobCategory,
    JobSourceName,
    JobStatus,
    JobVerdict,
    ScrapedJob,
)
from backend.infrastructure.db.models.job import Job as JobModel


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_entity(self, row: JobModel) -> Job:
        return Job(
            id=row.id,
            source=JobSourceName(row.source),
            external_id=row.external_id,
            title=row.title,
            employer=row.employer,
            location=row.location,
            url=row.url,
            description=row.description,
            posted_at=row.posted_at,
            category=JobCategory(row.category),
            relevance_score=row.relevance_score,
            match_reason=row.match_reason,
            application_cover_letter=row.application_cover_letter,
            application_how_to_apply=row.application_how_to_apply,
            status=JobStatus(row.status),
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
        )

    async def upsert_many(self, jobs: list[tuple[ScrapedJob, JobVerdict]]) -> int:
        if not jobs:
            return 0
        try:
            now = _to_naive_utc(datetime.now(UTC))
            inserted = 0
            for scraped, verdict in jobs:
                existing = await self.session.execute(
                    select(JobModel).where(
                        JobModel.source == scraped.source.value,
                        JobModel.external_id == scraped.external_id,
                    )
                )
                row = existing.scalar_one_or_none()
                posted = _to_naive_utc(scraped.posted_at) if scraped.posted_at else None
                if row is None:
                    self.session.add(
                        JobModel(
                            id=str(uuid.uuid4()),
                            source=scraped.source.value,
                            external_id=scraped.external_id,
                            title=scraped.title,
                            employer=scraped.employer,
                            location=scraped.location,
                            url=scraped.url,
                            description=scraped.description,
                            posted_at=posted,
                            category=verdict.category.value,
                            relevance_score=verdict.relevance_score,
                            match_reason=verdict.match_reason,
                            status=JobStatus.NEW.value,
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                    )
                    inserted += 1
                else:
                    # Refresh derived fields + last_seen; never touch user status.
                    row.title = scraped.title
                    row.employer = scraped.employer
                    row.location = scraped.location
                    row.url = scraped.url
                    row.description = scraped.description
                    row.posted_at = posted
                    row.category = verdict.category.value
                    row.relevance_score = verdict.relevance_score
                    row.match_reason = verdict.match_reason
                    row.last_seen_at = now
            await self.session.commit()
            return inserted
        except Exception:
            await self.session.rollback()
            raise

    async def list(
        self,
        *,
        category: JobCategory | None = None,
        source: JobSourceName | None = None,
        status: JobStatus | None = None,
        search: str | None = None,
        min_relevance: int | None = None,
        limit: int = 200,
    ) -> list[Job]:
        try:
            stmt = select(JobModel)
            if category is not None:
                stmt = stmt.where(JobModel.category == category.value)
            if source is not None:
                stmt = stmt.where(JobModel.source == source.value)
            if status is not None:
                stmt = stmt.where(JobModel.status == status.value)
            if min_relevance is not None:
                stmt = stmt.where(JobModel.relevance_score >= min_relevance)
            if search:
                like = f"%{search}%"
                stmt = stmt.where(
                    or_(
                        JobModel.title.ilike(like),
                        JobModel.employer.ilike(like),
                        JobModel.description.ilike(like),
                    )
                )
            stmt = stmt.order_by(
                JobModel.relevance_score.desc(),
                JobModel.posted_at.desc().nullslast(),
            ).limit(limit)
            result = await self.session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            raise

    async def update_status(self, job_id: str, status: JobStatus) -> Job | None:
        try:
            result = await self.session.execute(select(JobModel).where(JobModel.id == job_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.status = status.value
            await self.session.commit()
            await self.session.refresh(row)
            return self._to_entity(row)
        except Exception:
            await self.session.rollback()
            raise

    async def get(self, job_id: str) -> Job | None:
        result = await self.session.execute(select(JobModel).where(JobModel.id == job_id))
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    async def save_application(self, job_id: str, cover_letter: str, how_to_apply: str) -> Job | None:
        try:
            result = await self.session.execute(select(JobModel).where(JobModel.id == job_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.application_cover_letter = cover_letter
            row.application_how_to_apply = how_to_apply
            await self.session.commit()
            await self.session.refresh(row)
            return self._to_entity(row)
        except Exception:
            await self.session.rollback()
            raise
