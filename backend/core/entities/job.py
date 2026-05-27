from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class JobCategory(StrEnum):
    RETAIL = "retail"
    CRAFT = "craft"
    BOOKSTORE = "bookstore"
    LIBRARY = "library"
    MUSEUM = "museum"
    CULTURE = "culture"
    OTHER = "other"


class JobStatus(StrEnum):
    NEW = "new"
    INTERESTED = "interested"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class JobSourceName(StrEnum):
    DUUNITORI = "duunitori"
    TYOMARKKINATORI = "tyomarkkinatori"
    KUNTAREKRY = "kuntarekry"


class ScrapedJob(BaseModel):
    """A job as returned by a source scraper, before persistence.

    ``external_id`` is the source's own stable identifier; together with
    ``source`` it forms the dedup key used on upsert.
    """

    source: JobSourceName
    external_id: str
    title: str
    employer: str | None = None
    location: str | None = None
    url: str
    description: str | None = None
    posted_at: datetime | None = None


class JobVerdict(BaseModel):
    """The outcome of classifying a scraped job: where it fits, how relevant it
    is (0..100), and a short human-readable justification (from the LLM matcher,
    or None when only the keyword pre-filter ran)."""

    category: JobCategory
    relevance_score: int
    match_reason: str | None = None


class Job(BaseModel):
    """A persisted job with classification and user-managed status."""

    id: str
    source: JobSourceName
    external_id: str
    title: str
    employer: str | None = None
    location: str | None = None
    url: str
    description: str | None = None
    posted_at: datetime | None = None
    category: JobCategory
    relevance_score: int
    match_reason: str | None = None
    application_cover_letter: str | None = None
    application_how_to_apply: str | None = None
    status: JobStatus
    first_seen_at: datetime
    last_seen_at: datetime
