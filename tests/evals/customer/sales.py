"""Sales toolbox eval cases.

One example case per toolbox is the convention — forks add more as they need
them. References real seeded data (e.g. quotes / sales_orders views).
"""

from __future__ import annotations

from backend.customer.toolboxes import Toolbox
from tests.evals._case import EvalCase

SALES_CASES: list[EvalCase] = [
    EvalCase(
        id="sales.account_risk",
        toolbox=Toolbox.SALES,
        user_prompt="Which customer accounts look at-risk based on their recent purchase trends?",
        expected_tool_calls=["execute_sql"],
        judge_rubric=(
            "The response must (a) cite at least one specific customer by name or ID from the data, "
            "and (b) describe a concrete risk signal grounded in the returned numbers "
            "(e.g. declining monthly spend, a long-stalled quote, no recent orders)."
        ),
    ),
]
