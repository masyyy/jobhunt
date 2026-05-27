from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from backend.core.entities.job import Job, JobCategory, JobSourceName, JobStatus, JobVerdict, ScrapedJob

JobRepoFactory = Callable[[], AbstractAsyncContextManager["JobRepositoryInterface"]]


class JobRepositoryInterface(Protocol):
    async def upsert_many(self, jobs: list[tuple[ScrapedJob, JobVerdict]]) -> int:
        """Insert new jobs or refresh ``last_seen_at`` on existing ones.

        Each tuple is a scraped job plus its classification verdict (category,
        relevance score, and optional match reason). Dedup is on
        ``(source, external_id)``. User-managed ``status`` is never overwritten
        on an existing row. Returns the count of rows newly inserted.
        """
        ...

    async def list(
        self,
        *,
        category: JobCategory | None = None,
        source: JobSourceName | None = None,
        status: JobStatus | None = None,
        search: str | None = None,
        min_relevance: int | None = None,
        limit: int = 200,
    ) -> list[Job]: ...

    async def update_status(self, job_id: str, status: JobStatus) -> Job | None: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def save_application(self, job_id: str, cover_letter: str, how_to_apply: str) -> Job | None:
        """Persist the drafted cover letter + how-to-apply for a job.

        Returns the updated job, or None if no job has that id.
        """
        ...
