"""The scrape pipeline must drop postings outside the capital region.

Geographic gating happens silently in scrape_jobs before persistence, so a
regression would quietly let non-capital jobs into the dashboard. These cover
the token-matching edge cases that whole-string equality would get wrong.
"""

import pytest

from backend.core.tasks.scrape_jobs import _in_capital_region  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize("location", ["Helsinki", "Espoo", "Vantaa", "Kauniainen"])
def test_capital_municipalities_pass(location: str) -> None:
    assert _in_capital_region(location) is True


@pytest.mark.parametrize("location", ["Lahti", "Tampere", "Turku", "Oulu"])
def test_other_municipalities_dropped(location: str) -> None:
    assert _in_capital_region(location) is False


def test_missing_location_dropped() -> None:
    assert _in_capital_region(None) is False
    assert _in_capital_region("") is False


def test_case_insensitive() -> None:
    assert _in_capital_region("HELSINKI") is True
    assert _in_capital_region("espoo") is True


def test_compound_location_matches_on_token() -> None:
    # Sources sometimes list several municipalities in one string.
    assert _in_capital_region("Helsinki, Vantaa") is True
    assert _in_capital_region("Tampere / Espoo") is True
    assert _in_capital_region("Lahti, Tampere") is False


def test_substring_does_not_falsely_match() -> None:
    # A municipality that merely contains a capital name as a substring
    # must not match — token matching, not substring.
    assert _in_capital_region("Helsingin maalaiskunta") is False
