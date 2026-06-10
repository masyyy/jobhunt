"""Delete jobs that are stale (no longer on the source) or stale-dismissed.

Two cutoffs:
  - ``stale_after_days``: ``last_seen_at`` older than this means the scraper
    hasn't re-seen the posting; with a daily scrape, a few days is plenty.
  - ``dismissed_after_days``: dismissed jobs older than this get deleted, but
    we keep this longer than the stale window so a freshly-dismissed job can't
    re-surface if the source briefly drops and re-lists it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.core.interfaces.job_repository import JobRepoFactory

logger = logging.getLogger(__name__)

TASK_NAME = "prune-jobs"


async def prune_jobs(
    *,
    repo_factory: JobRepoFactory,
    stale_after_days: int,
    dismissed_after_days: int,
) -> int:
    """Delete stale + stale-dismissed jobs. Returns the number deleted."""
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=stale_after_days)
    dismissed_cutoff = now - timedelta(days=dismissed_after_days)
    async with repo_factory() as repo:
        deleted = await repo.prune_stale(stale_cutoff=stale_cutoff, dismissed_cutoff=dismissed_cutoff)
    logger.info(
        "prune-jobs: deleted=%d stale_after_days=%d dismissed_after_days=%d",
        deleted,
        stale_after_days,
        dismissed_after_days,
    )
    return deleted
