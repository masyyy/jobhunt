from typing import Protocol

from backend.core.entities.job import ScrapedJob
from pydantic import BaseModel


class MatchResult(BaseModel):
    """A matcher's yes/no verdict on a single posting, with a short reason."""

    relevant: bool
    reason: str


class JobMatcher(Protocol):
    async def match(self, job: ScrapedJob) -> MatchResult:
        """Decide whether a single posting fits the applicant profile.

        Implementations should err toward recall — keep anything that
        plausibly fits — and never raise: on any failure return a permissive
        result so a flaky matcher never silently empties the dashboard.
        """
        ...
