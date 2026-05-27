"""Relevance classifier — a pure function gating which jobs surface to the user.

Worth testing as a pure function because a silent regression (e.g. a boundary
bug that drops every match to OTHER) would empty the dashboard without error.
"""

from backend.core.entities.job import JobCategory
from backend.core.jobs.relevance import RELEVANCE_THRESHOLD, classify


def test_no_keyword_match_is_other_with_zero_score():
    category, score = classify("Senior Software Engineer", "Build distributed systems")
    assert category == JobCategory.OTHER
    assert score == 0


def test_title_match_assigns_category():
    category, score = classify("Kirjastovirkailija", None)
    assert category == JobCategory.LIBRARY
    assert score >= RELEVANCE_THRESHOLD


def test_title_hit_outranks_description_only_hit():
    title_match = classify("Myyjä, Tiger Helsinki", None)
    desc_match = classify("Avoin tehtävä", "Etsimme henkilöä myymälä-tiimiin")
    assert title_match[1] > desc_match[1]


def test_description_only_match_still_surfaces():
    # Recall-first: a category keyword in the description alone should classify.
    category, score = classify(
        "Avoin tehtävä",
        "Tule töihin kulttuurikeskus Stoaan tapahtumatuotantoon",
    )
    assert category == JobCategory.CULTURE
    assert score >= RELEVANCE_THRESHOLD


def test_negative_office_keyword_reduces_score():
    plain = classify("Myyjä", None)
    with_negative = classify("Myyjä / Myyntipäällikkö", None)
    assert with_negative[1] < plain[1]


def test_word_boundary_avoids_loose_substring():
    # "kirja" must not match an unrelated longer word mid-token.
    category, score = classify("Toimitusjohtajan sihteeri", "Vastaat kalenterista")
    assert category == JobCategory.OTHER
    assert score == 0


def test_retail_english_terms_match():
    category, _ = classify("Sales assistant at Normal store", None)
    assert category == JobCategory.RETAIL
