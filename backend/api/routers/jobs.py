"""Jobs API: list scraped job postings and update their status."""

import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.api.dependencies import (
    get_application_assistant,
    get_job_repository,
    verify_app_password,
)
from backend.core.entities.job import Job, JobCategory, JobSourceName, JobStatus
from backend.core.interfaces.application_assistant import ApplicationAssistant
from backend.core.interfaces.job_repository import JobRepositoryInterface
from backend.core.jobs.relevance import RELEVANCE_THRESHOLD

router = APIRouter(dependencies=[Depends(verify_app_password)])

# Sliding-window rate limit for the LLM-backed apply endpoint, keyed on
# client IP. The app uses a shared password so there's no per-user id;
# IP is the only identity available. In-memory: a single Procrastinate
# worker shares the FastAPI process. If the API ever runs multi-replica
# this needs to move to Redis.
_APPLY_RATE_LIMIT = 10  # requests
_APPLY_RATE_WINDOW = 1.0  # second
_apply_request_times: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_apply(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - _APPLY_RATE_WINDOW
    times = _apply_request_times[client]
    while times and times[0] < window_start:
        times.popleft()
    if len(times) >= _APPLY_RATE_LIMIT:
        retry_after = max(0.0, _APPLY_RATE_WINDOW - (now - times[0]))
        raise HTTPException(
            status_code=429,
            detail="Too many application drafts. Slow down.",
            headers={"Retry-After": f"{retry_after:.2f}"},
        )
    times.append(now)


@router.get("/auth/check")
async def auth_check() -> dict[str, bool]:
    """Validate the app password (router dependency does the check)."""
    return {"ok": True}


class JobResponse(BaseModel):
    id: str
    source: str
    title: str
    employer: str | None
    location: str | None
    url: str
    posted_at: datetime | None
    category: str
    relevance_score: int
    match_reason: str | None
    application_cover_letter: str | None
    application_how_to_apply: str | None
    status: str

    @classmethod
    def from_entity(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            source=job.source.value,
            title=job.title,
            employer=job.employer,
            location=job.location,
            url=job.url,
            posted_at=job.posted_at,
            category=job.category.value,
            relevance_score=job.relevance_score,
            match_reason=job.match_reason,
            application_cover_letter=job.application_cover_letter,
            application_how_to_apply=job.application_how_to_apply,
            status=job.status.value,
        )


class UpdateStatusRequest(BaseModel):
    status: JobStatus


@router.get("/jobs")
async def list_jobs(
    category: JobCategory | None = Query(default=None),
    source: JobSourceName | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    relevant_only: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    repo: JobRepositoryInterface = Depends(get_job_repository),
) -> list[JobResponse]:
    """List jobs, newest/most-relevant first. Defaults to relevant matches only."""
    jobs = await repo.list(
        category=category,
        source=source,
        status=status,
        search=search,
        min_relevance=RELEVANCE_THRESHOLD if relevant_only else None,
        limit=limit,
    )
    return [JobResponse.from_entity(j) for j in jobs]


@router.patch("/jobs/{job_id}")
async def update_job_status(
    job_id: str,
    body: UpdateStatusRequest,
    repo: JobRepositoryInterface = Depends(get_job_repository),
) -> JobResponse:
    """Update a job's status (new / interested / applied / dismissed)."""
    job = await repo.update_status(job_id, body.status)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_entity(job)


class ApplicationResponse(BaseModel):
    cover_letter: str
    how_to_apply: str


@router.post("/jobs/{job_id}/application", dependencies=[Depends(_rate_limit_apply)])
async def draft_application(
    job_id: str,
    regenerate: bool = Query(default=False),
    repo: JobRepositoryInterface = Depends(get_job_repository),
    assistant: ApplicationAssistant = Depends(get_application_assistant),
) -> ApplicationResponse:
    """Return the saved application draft, or generate one with the LLM.

    Generates (and saves) on first request or when ``regenerate`` is true;
    otherwise returns the previously-saved draft.
    """
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if not regenerate and job.application_cover_letter and job.application_how_to_apply:
        return ApplicationResponse(
            cover_letter=job.application_cover_letter,
            how_to_apply=job.application_how_to_apply,
        )

    draft = await assistant.draft(job)
    await repo.save_application(job_id, draft.cover_letter, draft.how_to_apply)
    return ApplicationResponse(cover_letter=draft.cover_letter, how_to_apply=draft.how_to_apply)
