"""Customer eval cases — each toolbox declares its own list, aggregated here.

Customer carveout: forks rewrite these to match their own data and prompts.
The runner / report machinery lives in tests/evals/.

This fork (jobhunt) is a dashboard-only app — the chat backend is retained but
not exercised from the UI. We keep one floor case per toolbox (the config check
requires it), exercising the prompt's stated job-application-drafting behaviour.
"""

from backend.customer.toolboxes import Toolbox
from tests.evals._case import EvalCase

ALL_CASES: list[EvalCase] = [
    EvalCase(
        id="jobhunt-draft-application",
        toolbox=Toolbox.JOBHUNT,
        user_prompt=(
            "Draft a short, warm application message in Finnish for a sales "
            "assistant (myyjä) role at a craft store. Keep it under 80 words."
        ),
        judge_rubric=(
            "The response is a short, warm application message written in Finnish "
            "(not English), suitable for a retail/craft sales-assistant role. It "
            "is concise and friendly, not a generic corporate cover letter."
        ),
    ),
]

__all__ = ["ALL_CASES"]
