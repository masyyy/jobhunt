"""Scrape Finnish job sites, filter, classify, and upsert into the DB.

Pipeline per scrape:
  1. Fetch from every source independently — one failing source never aborts
     the whole scrape.
  2. Keep only capital-region postings published within the last 7 days.
  3. Keyword pre-filter (cheap, recall-wide): drop postings no target keyword
     matches at all.
  4. LLM match (gpt-5.4-mini): a yes/no verdict + reason per surviving posting,
     judged against the applicant profile. Recall-leaning — only clear
     mismatches are dropped.
  5. Upsert (dedup on source + external_id, user status preserved).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.core.entities.job import JobVerdict, ScrapedJob
from backend.core.interfaces.job_matcher import JobMatcher, MatchResult
from backend.core.interfaces.job_repository import JobRepoFactory
from backend.core.interfaces.job_source import JobSource
from backend.core.jobs.relevance import classify

logger = logging.getLogger(__name__)

TASK_NAME = "scrape-jobs"

# Capital region (pääkaupunkiseutu). Kauniainen is an enclave within Espoo and
# part of the region proper. Lowercased for case-insensitive token matching.
_CAPITAL_REGION = frozenset({"helsinki", "espoo", "vantaa", "kauniainen"})

# Only consider postings published within this window.
_MAX_AGE = timedelta(days=7)

# Relevance score for a posting the LLM matcher accepted. We let the keyword
# pre-filter rank within accepted jobs (bookstore/craft hits score higher), but
# floor it so every accepted posting clears RELEVANCE_THRESHOLD and shows up.
_ACCEPTED_FLOOR = 50

# How many matcher LLM calls to run concurrently. Keeps the scrape fast without
# hammering the model endpoint with hundreds of simultaneous requests.
_MATCH_CONCURRENCY = 8


def _in_capital_region(location: str | None) -> bool:
    """True if the posting's location names a capital-region municipality.

    Sources sometimes pack several municipalities into one string
    (e.g. "Helsinki, Vantaa"), so match on tokens rather than the whole value.
    Jobs with no location are dropped — we can't confirm they're in-region.
    """
    if not location:
        return False
    tokens = {t.strip().lower() for t in location.replace("/", ",").split(",")}
    return bool(tokens & _CAPITAL_REGION)


def _is_recent(posted_at: datetime | None, *, now: datetime) -> bool:
    """True if posted within the last 7 days. Postings with no date are kept —
    we can't prove they're stale, and recall matters more than precision here."""
    if posted_at is None:
        return True
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    return posted_at >= now - _MAX_AGE


async def scrape_jobs(
    *,
    sources: list[JobSource],
    repo_factory: JobRepoFactory,
    matcher: JobMatcher,
) -> int:
    """Fetch from all sources, filter, classify, and upsert. Returns newly-inserted count."""
    results = await asyncio.gather(
        *(_safe_fetch(src) for src in sources),
        return_exceptions=False,
    )

    now = datetime.now(UTC)
    fetched: list[ScrapedJob] = [job for source_jobs in results for job in source_jobs]
    in_region = [
        job for job in fetched if _in_capital_region(job.location) and _is_recent(job.posted_at, now=now)
    ]

    # Keyword pre-filter: keep anything with at least one target-keyword hit.
    pre_filtered: list[tuple[ScrapedJob, int]] = []
    for job in in_region:
        _, score = classify(job.title, job.description)
        if score > 0:
            pre_filtered.append((job, score))

    if not pre_filtered:
        logger.info(
            "scrape-jobs: nothing to classify (fetched=%d in_region_recent=%d)",
            len(fetched),
            len(in_region),
        )
        return 0

    # LLM match each survivor (bounded concurrency); keep only accepted postings.
    semaphore = asyncio.Semaphore(_MATCH_CONCURRENCY)

    async def _match(job: ScrapedJob) -> MatchResult:
        async with semaphore:
            return await matcher.match(job)

    verdicts = await asyncio.gather(*(_match(job) for job, _ in pre_filtered))

    accepted: list[tuple[ScrapedJob, JobVerdict]] = []
    for (job, score), result in zip(pre_filtered, verdicts, strict=True):
        if not result.relevant:
            continue
        category, _ = classify(job.title, job.description)
        accepted.append(
            (
                job,
                JobVerdict(
                    category=category,
                    relevance_score=max(score, _ACCEPTED_FLOOR),
                    match_reason=result.reason,
                ),
            )
        )

    if not accepted:
        logger.info(
            "scrape-jobs: no jobs accepted by matcher (fetched=%d pre_filtered=%d)",
            len(fetched),
            len(pre_filtered),
        )
        return 0

    async with repo_factory() as repo:
        inserted = await repo.upsert_many(accepted)

    logger.info(
        "scrape-jobs: fetched=%d in_region_recent=%d pre_filtered=%d accepted=%d upserted_new=%d",
        len(fetched),
        len(in_region),
        len(pre_filtered),
        len(accepted),
        inserted,
    )
    return inserted


async def _safe_fetch(source: JobSource) -> list[ScrapedJob]:
    try:
        jobs = await source.fetch()
        logger.info("scrape-jobs: source %r returned %d jobs", source.name, len(jobs))
        return jobs
    except Exception:
        logger.exception("scrape-jobs: source %r failed", source.name)
        return []
