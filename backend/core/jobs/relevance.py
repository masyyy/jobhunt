"""Keyword-based relevance classifier for Finnish job postings.

Targets jobs suited to a creative, non-office worker: retail, crafts,
bookstores, libraries, museums, cultural venues. Scores each posting and
assigns the best-matching category. Pure functions, no I/O.
"""

from __future__ import annotations

import re

from backend.core.entities.job import JobCategory

# Category keyword tables. Finnish (and a few English) terms, lowercased.
# Matching is whole-word/substring case-insensitive against title+description.
_CATEGORY_KEYWORDS: dict[JobCategory, tuple[str, ...]] = {
    JobCategory.LIBRARY: (
        "kirjasto",
        "kirjastovirkailija",
        "kirjastonhoitaja",
        "informaatikko",
        "library",
    ),
    JobCategory.MUSEUM: (
        "museo",
        "museokauppa",
        "näyttely",
        "museum",
        "gallery",
        "galleria",
    ),
    JobCategory.BOOKSTORE: (
        "kirjakauppa",
        "kirjamyyjä",
        "antikvariaatti",
        "bookstore",
    ),
    JobCategory.CRAFT: (
        "askartelu",
        "käsityö",
        "käsityöt",
        "askarteluliike",
        "lankakauppa",
        "kangaskauppa",
        "puuhapaja",
        "craft",
        "hobby",
        "tiimari",
        "painotalo",
        "painopalvelu",
        "painotuote",
        "tulostus",
        "tulostuspalvelu",
        "digipaino",
        "kirjapaino",
        "painaja",
        "printtaus",
    ),
    JobCategory.CULTURE: (
        "kulttuurikeskus",
        "kulttuuri",
        "kulttuuritalo",
        "teatteri",
        "tapahtuma",
        "kulttuurituottaja",
        "culture",
        "cultural",
    ),
    JobCategory.RETAIL: (
        "myyjä",
        "myymälä",
        "myymäläpäällikkö",
        "asiakaspalvelu",
        "kassa",
        "kaupan",
        "vähittäiskauppa",
        "retail",
        "shop assistant",
        "sales assistant",
        "store",
        "tiger",
        "normal",
        "flying tiger",
    ),
}

# Generic office/ambition signals that should pull a job's score down — the
# target user does poorly in pure office roles.
_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "myyntipäällikkö",
    "sales manager",
    "key account",
    "controller",
    "kirjanpitäjä",
    "talouspäällikkö",
    "ohjelmistokehittäjä",
    "software",
    "developer",
    "konsultti",
    "consultant",
    "lakimies",
    "insinööri",
    "myyntineuvottelija",
    "provisiopalkka",
    "buukkari",
    "telemarkkinointi",
)

# Per-keyword-hit score. Category hits add, negative hits subtract.
_HIT_SCORE = 10
_NEGATIVE_SCORE = 8
# A title hit is worth more than a description-only hit.
_TITLE_MULTIPLIER = 2


def _norm(text: str | None) -> str:
    return (text or "").lower()


def _count_hits(haystack: str, keywords: tuple[str, ...]) -> int:
    """Count keywords that appear as a word prefix (tolerating Finnish suffixes).

    Matching on a word boundary at the *start* of the keyword avoids the loose
    substring problem (e.g. "kirja" inside an unrelated longer word) while still
    matching inflected forms like "kirjastossa", "myyjää".
    """
    count = 0
    for kw in keywords:
        if re.search(rf"(?<![\w]){re.escape(kw)}", haystack):
            count += 1
    return count


def classify(title: str, description: str | None = None) -> tuple[JobCategory, int]:
    """Return the best-matching category and a relevance score (0..100).

    Optimized for recall: a category is assigned if its keywords appear in the
    title OR the description. Title hits score much higher (they're the strong
    signal), so a description-only match still surfaces the job but ranks lower.
    Negative office/ambition keywords subtract from the score.

    Score 0 means no target keyword matched anywhere.
    """
    title_norm = _norm(title)
    desc_norm = _norm(description)

    best_category = JobCategory.OTHER
    best_score = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        title_hits = _count_hits(title_norm, keywords)
        desc_hits = _count_hits(desc_norm, keywords)
        if title_hits == 0 and desc_hits == 0:
            continue
        cat_score = title_hits * _HIT_SCORE * _TITLE_MULTIPLIER + desc_hits * _HIT_SCORE
        if cat_score > best_score:
            best_score = cat_score
            best_category = category

    if best_score == 0:
        return JobCategory.OTHER, 0

    neg_title = _count_hits(title_norm, _NEGATIVE_KEYWORDS)
    neg_desc = _count_hits(desc_norm, _NEGATIVE_KEYWORDS)
    penalty = neg_title * _NEGATIVE_SCORE * _TITLE_MULTIPLIER + neg_desc * _NEGATIVE_SCORE

    score = max(0, min(100, best_score - penalty))
    return best_category, score


# Jobs scoring at or above this are considered "relevant" for the default view.
RELEVANCE_THRESHOLD = 10
