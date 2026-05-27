"""Customer eval cases — each toolbox declares its own list, aggregated here.

Customer carveout: forks rewrite these to match their own data and prompts.
The runner / report machinery lives in tests/evals/.
"""

from tests.evals._case import EvalCase

from .production import PRODUCTION_CASES
from .sales import SALES_CASES
from .shared import SHARED_CASES

ALL_CASES: list[EvalCase] = [*SALES_CASES, *PRODUCTION_CASES, *SHARED_CASES]

__all__ = ["ALL_CASES", "PRODUCTION_CASES", "SALES_CASES", "SHARED_CASES"]
