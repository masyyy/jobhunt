"""Eval fixtures — reuse production DI so evals hit the real local data."""

from __future__ import annotations

import pytest

from backend.api.dependencies import get_agent_deps
from backend.core.agents.deps import AgentDeps


@pytest.fixture(scope="session")
def eval_deps() -> AgentDeps:
    """Real production AgentDeps — points at settings.DATASETS_DIR / DOCUMENTS_DIR."""
    return get_agent_deps()
