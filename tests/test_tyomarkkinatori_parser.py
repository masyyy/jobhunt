"""Tyomarkkinatori response parsing — the brittle boundary with the public
full-text search endpoint.

The parser maps a nested, multilingual JSON shape into our flat entity. The
realistic failure modes are a field rename, a missing id/title, or an empty
employer name, so we assert on a captured shape and its edge cases.
"""

from datetime import UTC, datetime

from backend.core.entities.job import JobSourceName
from backend.infrastructure.job_sources.tyomarkkinatori import _to_scraped

# A representative search `content[]` row (field paths captured from the live API).
_SAMPLE = {
    "id": "7e3de763-87bf-4c3e-ac36-8a121eeb552b",
    "title": {"fi": "Myyjä, Tiger Helsinki", "en": "Salesperson"},
    "employer": {"name": "", "ownerName": {"fi": "Flying Tiger Copenhagen"}},
    "location": {
        "municipalities": [
            {"value": "091", "label": {"fi": "Helsinki", "sv": "Helsingfors", "en": "Helsinki"}}
        ],
        "address": {"postOffice": "HELSINKI"},
    },
    "applicationUrl": {"values": {"fi": "https://example.com/apply"}},
    "publishDate": "2026-05-27T09:00:55.969Z",
}


def test_maps_all_fields():
    job = _to_scraped(_SAMPLE)
    assert job is not None
    assert job.source == JobSourceName.TYOMARKKINATORI
    assert job.external_id == "7e3de763-87bf-4c3e-ac36-8a121eeb552b"
    assert job.title == "Myyjä, Tiger Helsinki"  # fi preferred over en
    assert job.employer == "Flying Tiger Copenhagen"  # ownerName, not the empty name
    assert job.location == "Helsinki"  # first municipality, fi label
    assert (
        job.url
        == "https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/tyopaikka/7e3de763-87bf-4c3e-ac36-8a121eeb552b"
    )
    assert job.description is None  # search response carries no description
    assert job.posted_at == datetime(2026, 5, 27, 9, 0, 55, 969000, tzinfo=UTC)


def test_missing_id_is_dropped():
    assert _to_scraped({"title": {"fi": "No id"}}) is None


def test_missing_title_is_dropped():
    assert _to_scraped({"id": "x"}) is None


def test_falls_back_to_employer_name_when_owner_missing():
    job = _to_scraped({**_SAMPLE, "employer": {"name": "Direct Name Oy", "ownerName": {}}})
    assert job is not None
    assert job.employer == "Direct Name Oy"


def test_optional_fields_default_to_none():
    job = _to_scraped({"id": "x", "title": {"fi": "Title only"}})
    assert job is not None
    assert job.employer is None
    assert job.location is None
    assert job.posted_at is None


def test_malformed_date_yields_none_posted_at():
    job = _to_scraped({**_SAMPLE, "publishDate": "not-a-date"})
    assert job is not None
    assert job.posted_at is None
