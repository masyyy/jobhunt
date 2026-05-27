from typing import Protocol

from backend.core.entities.job import ScrapedJob


class JobSource(Protocol):
    """A source that fetches job postings over HTTP.

    Implementations are responsible for their own pagination, parsing, and
    normalization into :class:`ScrapedJob`. They must not raise on an empty
    result; a source that is unavailable (e.g. missing API token) should log
    and return an empty list so one bad source never fails the whole scrape.
    """

    name: str

    async def fetch(self) -> list[ScrapedJob]: ...
