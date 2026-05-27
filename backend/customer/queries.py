"""Customer-defined named queries for the data API.

Each ``DashboardQuery`` member maps to a ``NamedQuery`` in
``DASHBOARD_QUERIES``. Customer forks add entries here to register queries
accessible via ``GET /api/data/query/{query_name}``.

Parameter binding
-----------------
A ``NamedQuery`` may declare typed parameters that are filled from the
request's query string. Use ``?`` positional placeholders in SQL and
declare each placeholder as a :class:`QueryParam`. The router coerces
incoming values via :func:`bind_params` before handing them to DuckDB —
user input never reaches the SQL string itself.
"""

from enum import StrEnum

from backend.core.queries.types import NamedQuery


class DashboardQuery(StrEnum):
    pass  # No default queries in the template


DASHBOARD_QUERIES: dict[DashboardQuery, NamedQuery] = {}
