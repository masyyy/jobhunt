"""Duunitori response parsing — the brittle boundary with an external API.

The parser maps an undocumented JSON shape into our entity; a field rename or a
malformed row are the realistic failure modes, so we assert on a captured shape.
"""

from datetime import datetime

from backend.core.entities.job import JobSourceName
from backend.infrastructure.job_sources.duunitori import _to_scraped

# A representative jobentries result row (field names captured from the live API).
_SAMPLE = {
    "slug": "myyja-helsinki-12345",
    "heading": "Myyjä, Tiger Helsinki",
    "company_name": "Flying Tiger Copenhagen",
    "municipality_name": "Helsinki",
    "descr": "Etsimme iloista myyjää myymäläämme.",
    "date_posted": "2026-05-20",
}


def test_maps_all_fields():
    job = _to_scraped(_SAMPLE)
    assert job is not None
    assert job.source == JobSourceName.DUUNITORI
    assert job.external_id == "myyja-helsinki-12345"
    assert job.title == "Myyjä, Tiger Helsinki"
    assert job.employer == "Flying Tiger Copenhagen"
    assert job.location == "Helsinki"
    assert job.url == "https://duunitori.fi/tyopaikat/tyo/myyja-helsinki-12345"
    assert job.description == "Etsimme iloista myyjää myymäläämme."
    assert job.posted_at == datetime(2026, 5, 20)


def test_missing_slug_is_dropped():
    assert _to_scraped({"heading": "No slug"}) is None


def test_missing_heading_is_dropped():
    assert _to_scraped({"slug": "x"}) is None


def test_optional_fields_default_to_none():
    job = _to_scraped({"slug": "x", "heading": "Title only"})
    assert job is not None
    assert job.employer is None
    assert job.location is None
    assert job.description is None
    assert job.posted_at is None


def test_malformed_date_yields_none_posted_at():
    job = _to_scraped({**_SAMPLE, "date_posted": "not-a-date"})
    assert job is not None
    assert job.posted_at is None
