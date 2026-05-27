"""Production toolbox eval cases.

One example case per toolbox is the convention — forks add more as they need
them. References real seeded data (lines L-101..L-105, downtime_events view).
"""

from __future__ import annotations

from backend.customer.toolboxes import Toolbox
from tests.evals._case import EvalCase

PRODUCTION_CASES: list[EvalCase] = [
    EvalCase(
        id="production.equipment_status",
        toolbox=Toolbox.PRODUCTION,
        user_prompt="Which machines have had the most unplanned downtime in the last 90 days?",
        expected_tool_calls=["execute_sql"],
        judge_rubric=(
            "The response must name at least one specific machine ID (e.g. CNC-1A, WELD-3B) from "
            "the data and back the ranking with a concrete number (event count or hours of downtime)."
        ),
    ),
]
