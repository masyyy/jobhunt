"""LLM-backed job matcher.

A structured PydanticAI call that takes a single posting and returns a yes/no
verdict plus a one-line reason on whether it fits the applicant profile. It is
deliberately recall-leaning: the keyword pre-filter already narrowed the set,
so the LLM's job is only to drop postings that clearly don't make sense for the
profile (B2B sales, managerial roles, office/specialist jobs), not to be picky.

On any LLM error we log and return a permissive result so a flaky matcher never
silently empties the dashboard.
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent

from backend.core.agents.model_config import MODEL_MATCHER, get_model
from backend.core.entities.job import ScrapedJob
from backend.core.interfaces.job_matcher import MatchResult
from backend.core.jobs.profile import APPLICANT_PROFILE

logger = logging.getLogger(__name__)

_INSTRUCTIONS = f"""\
You screen Finnish job postings for one specific applicant. Decide whether a
posting makes sense for her to apply to.

Applicant profile:
{APPLICANT_PROFILE}

Judge generously. The candidate list has already been pre-filtered by keyword,
so you only need to weed out postings that clearly don't make sense for this
profile. When a posting plausibly fits — any ordinary retail/shop/customer
job, or a temporary library/museum role — answer yes. Only answer no when the
posting clearly conflicts with the profile (B2B/commission sales,
managerial/lead roles, or pure office/specialist/technical jobs).

Postings are in Finnish; reason about the Finnish title and any description.
Always give a short (one sentence) reason in English for your decision.
"""


def _format_job(job: ScrapedJob) -> str:
    lines = [f"Title: {job.title}"]
    if job.employer:
        lines.append(f"Employer: {job.employer}")
    if job.location:
        lines.append(f"Location: {job.location}")
    if job.description:
        lines.append(f"Description: {job.description}")
    return "\n".join(lines)


class LlmJobMatcher:
    def __init__(self) -> None:
        self._agent: Agent[None, MatchResult] = Agent(
            get_model(MODEL_MATCHER),
            instructions=_INSTRUCTIONS,
            output_type=MatchResult,
        )

    async def match(self, job: ScrapedJob) -> MatchResult:
        try:
            result = await self._agent.run(_format_job(job))
            return result.output
        except Exception:
            logger.exception("Job matcher failed for %r; keeping it (recall-first)", job.title)
            return MatchResult(relevant=True, reason="Matcher unavailable; kept by default.")
