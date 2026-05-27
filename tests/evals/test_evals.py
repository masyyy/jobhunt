"""Run every EvalCase as its own pytest test."""

from __future__ import annotations

import pytest

from backend.core.agents.deps import AgentDeps
from tests.evals._case import EvalCase
from tests.evals._runner import run_case
from tests.evals.customer import ALL_CASES


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
async def test_eval_case(case: EvalCase, eval_deps: AgentDeps) -> None:
    result = await run_case(case, eval_deps)
    assert result.passed, result.failure_reason
