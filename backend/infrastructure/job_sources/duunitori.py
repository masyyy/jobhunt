"""Duunitori job source.

Uses Duunitori's public, no-auth JSON API
(``https://duunitori.fi/api/v1/jobentries``). We query a small set of
Finnish search terms relevant to retail/craft/library/museum/culture work
and merge the results, deduplicating on the posting slug.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from backend.core.entities.job import JobSourceName, ScrapedJob

logger = logging.getLogger(__name__)

_API_URL = "https://duunitori.fi/api/v1/jobentries"
_JOB_URL_PREFIX = "https://duunitori.fi/tyopaikat/tyo/"

# Search terms targeting the desired profile. Duunitori `search` matches title
# (and description with search_also_descr=1).
_SEARCH_TERMS: tuple[str, ...] = (
    "myyjä",
    "myymälä",
    "kirjasto",
    "kirjakauppa",
    "museo",
    "askartelu",
    "käsityö",
    "kulttuuri",
    "asiakaspalvelu",
    "painotalo",
    "tulostus",
    "painopalvelu",
)

_MAX_PAGES_PER_TERM = 3
_HEADERS = {"User-Agent": "jobhunt-dashboard/0.1 (personal job search)"}


def _parse_posted(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_scraped(item: dict[str, object]) -> ScrapedJob | None:
    slug = item.get("slug")
    heading = item.get("heading")
    if not isinstance(slug, str) or not isinstance(heading, str):
        return None
    employer = item.get("company_name")
    location = item.get("municipality_name")
    descr = item.get("descr")
    return ScrapedJob(
        source=JobSourceName.DUUNITORI,
        external_id=slug,
        title=heading,
        employer=employer if isinstance(employer, str) else None,
        location=location if isinstance(location, str) else None,
        url=f"{_JOB_URL_PREFIX}{slug}",
        description=descr if isinstance(descr, str) else None,
        posted_at=_parse_posted(item.get("date_posted") if isinstance(item.get("date_posted"), str) else None),
    )


class DuunitoriSource:
    name = JobSourceName.DUUNITORI.value

    def __init__(self, search_terms: tuple[str, ...] = _SEARCH_TERMS) -> None:
        self._search_terms = search_terms

    async def _fetch_term(self, client: httpx.AsyncClient, term: str) -> list[ScrapedJob]:
        jobs: list[ScrapedJob] = []
        page = 1
        while page <= _MAX_PAGES_PER_TERM:
            try:
                resp = await client.get(
                    _API_URL,
                    params={"search": term, "search_also_descr": "1", "page": page},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("Duunitori fetch failed for %r page %d: %s", term, page, e)
                break
            data = resp.json()
            results = data.get("results") or []
            for item in results:
                scraped = _to_scraped(item)
                if scraped is not None:
                    jobs.append(scraped)
            if not data.get("next"):
                break
            page += 1
            await asyncio.sleep(0.5)  # be polite to an undocumented API
        return jobs

    async def fetch(self) -> list[ScrapedJob]:
        by_id: dict[str, ScrapedJob] = {}
        async with httpx.AsyncClient(headers=_HEADERS, timeout=20.0) as client:
            for term in self._search_terms:
                for job in await self._fetch_term(client, term):
                    by_id[job.external_id] = job
                await asyncio.sleep(0.5)
        logger.info("Duunitori: collected %d unique jobs", len(by_id))
        return list(by_id.values())
