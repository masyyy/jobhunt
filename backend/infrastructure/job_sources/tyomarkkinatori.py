"""Job Market Finland (Tyomarkkinatori) job source.

Uses the public full-text search endpoint that the tyomarkkinatori.fi web app
itself calls (``POST /api/jobpostingfulltext/search/v2/search``). It needs no
authentication: the official KEHA retrieval API requires a business-ID-bound
bearer token, but this is the same dataset served to the public site.

We query a small set of Finnish search terms relevant to the desired profile
and constrain results to the capital region server-side via the municipality
filter, then merge and deduplicate on the posting id. The search response
carries no job description, so postings are classified on title alone
downstream (the relevance classifier already handles a missing description).

Status: undocumented internal endpoint. Like the Duunitori source it may
change without notice; on any HTTP error we log and return an empty list so a
single bad source never aborts the whole scrape.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from backend.core.entities.job import JobSourceName, ScrapedJob

logger = logging.getLogger(__name__)

_API_URL = "https://tyomarkkinatori.fi/api/jobpostingfulltext/search/v2/search"
_DETAIL_URL_PREFIX = "https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/tyopaikka/"
_PREFERRED_LANGS = ("fi", "sv", "en")

# Capital-region municipality codes (Tilastokeskus/kuntakoodi): Helsinki,
# Espoo, Vantaa, Kauniainen. Applied as a server-side filter.
_CAPITAL_REGION_CODES = ("091", "049", "092", "235")

# Search terms targeting the desired profile (retail/craft/library/museum/
# culture/customer-service). Mirrors the Duunitori source's term set.
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

_PAGE_SIZE = 50
_MAX_PAGES_PER_TERM = 3
_HEADERS = {
    "User-Agent": "jobhunt-dashboard/0.1 (personal job search)",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _pick_lang(multilingual: object) -> str | None:
    """Pick a string from a {langcode: text} multilingual object."""
    if isinstance(multilingual, str):
        return multilingual
    if not isinstance(multilingual, dict):
        return None
    for lang in _PREFERRED_LANGS:
        val = multilingual.get(lang)
        if isinstance(val, str) and val:
            return val
    for val in multilingual.values():
        if isinstance(val, str) and val:
            return val
    return None


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_municipality(location: object) -> str | None:
    if not isinstance(location, dict):
        return None
    munis = location.get("municipalities")
    if not isinstance(munis, list) or not munis:
        return None
    first = munis[0]
    return _pick_lang(first.get("label")) if isinstance(first, dict) else None


def _to_scraped(item: dict[str, object]) -> ScrapedJob | None:
    external_id = item.get("id")
    title = _pick_lang(item.get("title"))
    if not isinstance(external_id, str) or not title:
        return None

    employer_obj = item.get("employer") if isinstance(item.get("employer"), dict) else {}
    employer = _pick_lang(employer_obj.get("ownerName"))  # type: ignore[union-attr]
    if not employer:
        name = employer_obj.get("name")  # type: ignore[union-attr]
        employer = name if isinstance(name, str) and name else None

    return ScrapedJob(
        source=JobSourceName.TYOMARKKINATORI,
        external_id=external_id,
        title=title,
        employer=employer,
        location=_first_municipality(item.get("location")),
        url=f"{_DETAIL_URL_PREFIX}{external_id}",
        description=None,
        posted_at=_parse_dt(item.get("publishDate")),
    )


class TyomarkkinatoriSource:
    name = JobSourceName.TYOMARKKINATORI.value

    def __init__(self, search_terms: tuple[str, ...] = _SEARCH_TERMS) -> None:
        self._search_terms = search_terms

    async def _fetch_term(self, client: httpx.AsyncClient, term: str) -> list[ScrapedJob]:
        jobs: list[ScrapedJob] = []
        page = 0
        while page < _MAX_PAGES_PER_TERM:
            body = {
                "query": term,
                "filters": {"municipalities": list(_CAPITAL_REGION_CODES)},
                "paging": {"pageNumber": page, "pageSize": _PAGE_SIZE},
                "sorting": "LATEST",
            }
            try:
                resp = await client.post(_API_URL, json=body)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("Tyomarkkinatori fetch failed for %r page %d: %s", term, page, e)
                break
            data = resp.json()
            content = data.get("content")
            if not isinstance(content, list):
                break
            for item in content:
                if isinstance(item, dict):
                    scraped = _to_scraped(item)
                    if scraped is not None:
                        jobs.append(scraped)
            last_page = data.get("lastPage")
            if not isinstance(last_page, int) or page + 1 >= last_page:
                break
            page += 1
            await asyncio.sleep(0.5)  # be polite to an undocumented endpoint
        return jobs

    async def fetch(self) -> list[ScrapedJob]:
        by_id: dict[str, ScrapedJob] = {}
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0) as client:
            for term in self._search_terms:
                for job in await self._fetch_term(client, term):
                    by_id[job.external_id] = job
                await asyncio.sleep(0.5)
        logger.info("Tyomarkkinatori: collected %d unique capital-region jobs", len(by_id))
        return list(by_id.values())
