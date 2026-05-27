"""Kuntarekry job source (public-sector: libraries, museums, culture).

Status: DORMANT. As of 2026-05 Kuntarekry serves its job search from a
JavaScript SPA whose search API sits behind a bot guard
(``/fi/api/search-guard/``). There is no documented RSS, sitemap, or no-auth
JSON endpoint that returns listings without executing JavaScript, so a plain
``httpx`` fetch cannot retrieve postings.

This implementation therefore returns an empty list (logging the reason)
rather than failing the scrape. It is kept as a seam: if Kuntarekry exposes a
feed/API, implement ``fetch`` here and the rest of the pipeline works
unchanged. Much of Kuntarekry's public-sector data is also reachable via the
Tyomarkkinatori aggregate source once a KEHA token is configured.
"""

from __future__ import annotations

import logging

from backend.core.entities.job import ScrapedJob, JobSourceName

logger = logging.getLogger(__name__)


class KuntarekrySource:
    name = JobSourceName.KUNTAREKRY.value

    async def fetch(self) -> list[ScrapedJob]:
        logger.info(
            "Kuntarekry source dormant: search API is JS-rendered and bot-guarded; "
            "no no-JS endpoint available. Public-sector jobs are covered via Tyomarkkinatori."
        )
        return []
