"""Named-query endpoint for customer-registered SQL queries.

Safety
------
- SQL strings are hardcoded in ``backend/customer/queries.py``. Request
  data flows only through DuckDB positional parameter binding (``?``),
  never through string concatenation or formatting.
- Only declared parameter names are read from the query string. Unknown
  query-string keys are rejected — there is no "any kwarg flows through"
  surface.
- Type coercion happens before binding, in :func:`bind_params`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.dependencies import get_warehouse
from backend.core.queries.types import ParamBindError, bind_params
from backend.customer.queries import DASHBOARD_QUERIES, DashboardQuery
from backend.infrastructure.data_warehouse.duckdb_warehouse import DuckDBWarehouse

logger = logging.getLogger(__name__)

router = APIRouter()


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    truncated: bool


@router.get("/data/query/{query_name}")
def run_named_query(
    query_name: str,
    request: Request,
    warehouse: DuckDBWarehouse = Depends(get_warehouse),
) -> QueryResponse:
    """Execute a pre-registered named query and return structured JSON rows."""
    try:
        query_key = DashboardQuery(query_name)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_name}") from e

    query = DASHBOARD_QUERIES.get(query_key)
    if query is None:
        raise HTTPException(status_code=404, detail=f"Unknown query: {query_name}")

    try:
        bound = bind_params(query, dict(request.query_params))
    except ParamBindError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        result = warehouse.execute_sql_rows(query.sql, bound)
    except RuntimeError as e:
        msg = str(e)
        if "No data tables available" in msg:
            raise HTTPException(status_code=503, detail="Data warehouse unavailable") from e
        logger.error("Named query %r failed: %s", query_name, e)
        raise HTTPException(status_code=500, detail="Query execution failed") from e

    return QueryResponse(
        columns=result.columns,
        rows=result.rows,
        truncated=result.truncated,
    )
