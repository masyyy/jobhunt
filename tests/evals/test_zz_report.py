"""Last test in the eval batch — writes report.html from the results buffer.

The `zz` filename prefix puts this last in pytest's default file collection
order so RESULTS is fully populated by the time we render.
"""

from __future__ import annotations

from pathlib import Path

from tests.evals._report import render
from tests.evals._runner import RESULTS

_REPORT_PATH = Path(__file__).parent / "report.html"


def test_write_eval_report() -> None:
    """Always passes; side-effect is writing report.html."""
    _REPORT_PATH.write_text(render(RESULTS), encoding="utf-8")
