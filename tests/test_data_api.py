"""Tests for GET /api/data/query/{query_name}."""

from collections.abc import Sequence
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from backend.api.dependencies import get_warehouse
from backend.api.routers.data import router
from backend.core.interfaces.data_warehouse import QueryResult
from backend.core.queries.types import NamedQuery, ParamType, QueryParam


class FakeWarehouse:
    """Stub warehouse for testing execute_sql_rows."""

    def __init__(
        self,
        result: QueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result or QueryResult(columns=[], rows=[], truncated=False)
        self._error = error
        self.last_sql: str | None = None
        self.last_params: Sequence[object] | None = None

    def execute_sql_rows(self, sql: str, params: Sequence[object] = ()) -> QueryResult:
        self.last_sql = sql
        self.last_params = params
        if self._error:
            raise self._error
        return self._result

    def list_tables(self) -> list[Any]:
        return []

    def execute_sql(self, _sql: str) -> str:
        return ""


def _build_app(warehouse: FakeWarehouse) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_warehouse] = lambda: warehouse
    return app


def _patch_registry(monkeypatch: pytest.MonkeyPatch, query_name: str, query: NamedQuery) -> None:
    """Register a test query in the router's namespace."""
    monkeypatch.setattr(
        "backend.api.routers.data.DASHBOARD_QUERIES",
        {query_name: query},
    )
    monkeypatch.setattr(
        "backend.api.routers.data.DashboardQuery",
        type("DashboardQuery", (), {"__new__": lambda _cls, v: v}),  # type: ignore[misc]
    )


class TestRunNamedQuery:
    @pytest.mark.asyncio
    async def test_unknown_query_returns_404(self) -> None:
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/nonexistent")

        assert resp.status_code == 404
        assert "Unknown query" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_warehouse_unavailable_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_registry(monkeypatch, "test_q", NamedQuery(sql="SELECT 1"))
        app = _build_app(FakeWarehouse(error=RuntimeError("No data tables available.")))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_query_execution_error_returns_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_registry(monkeypatch, "test_q", NamedQuery(sql="SELECT * FROM missing"))
        app = _build_app(FakeWarehouse(error=RuntimeError("Table not found. missing")))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Query execution failed"

    @pytest.mark.asyncio
    async def test_successful_query_returns_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_registry(monkeypatch, "test_q", NamedQuery(sql="SELECT 1 AS n"))
        result = QueryResult(columns=["n"], rows=[{"n": 1}, {"n": 2}], truncated=False)
        app = _build_app(FakeWarehouse(result=result))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 200
        body = resp.json()
        assert body["columns"] == ["n"]
        assert body["rows"] == [{"n": 1}, {"n": 2}]
        assert body["truncated"] is False

    @pytest.mark.asyncio
    async def test_successful_query_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_registry(monkeypatch, "test_q", NamedQuery(sql="SELECT 1 WHERE false"))
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 200
        body = resp.json()
        assert body["columns"] == []
        assert body["rows"] == []
        assert body["truncated"] is False

    @pytest.mark.asyncio
    async def test_truncated_flag_propagated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_registry(monkeypatch, "test_q", NamedQuery(sql="SELECT 1"))
        result = QueryResult(columns=["n"], rows=[{"n": 1}], truncated=True)
        app = _build_app(FakeWarehouse(result=result))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 200
        assert resp.json()["truncated"] is True


class TestNamedQueryParams:
    @pytest.mark.asyncio
    async def test_missing_required_param_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        query = NamedQuery(
            sql="SELECT * FROM customers WHERE id = ?",
            params=(QueryParam(name="customer_id", type=ParamType.STRING),),
        )
        _patch_registry(monkeypatch, "test_q", query)
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q")

        assert resp.status_code == 400
        assert "customer_id" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bad_int_param_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        query = NamedQuery(
            sql="SELECT * FROM orders WHERE qty > ?",
            params=(QueryParam(name="min_qty", type=ParamType.INT),),
        )
        _patch_registry(monkeypatch, "test_q", query)
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q?min_qty=not-a-number")

        assert resp.status_code == 400
        assert "min_qty" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bad_date_param_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        query = NamedQuery(
            sql="SELECT * FROM orders WHERE created_at >= ?",
            params=(QueryParam(name="since", type=ParamType.DATE),),
        )
        _patch_registry(monkeypatch, "test_q", query)
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q?since=not-a-date")

        assert resp.status_code == 400
        assert "since" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unknown_query_string_key_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        query = NamedQuery(
            sql="SELECT * FROM customers WHERE id = ?",
            params=(QueryParam(name="customer_id", type=ParamType.STRING),),
        )
        _patch_registry(monkeypatch, "test_q", query)
        app = _build_app(FakeWarehouse())

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/data/query/test_q?customer_id=C-1&not_declared=oops")

        assert resp.status_code == 400
        assert "not_declared" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_params_bound_positionally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        query = NamedQuery(
            sql="SELECT * FROM orders WHERE customer_id = ? AND qty > ? AND created_at >= ?",
            params=(
                QueryParam(name="customer_id", type=ParamType.STRING),
                QueryParam(name="min_qty", type=ParamType.INT),
                QueryParam(name="since", type=ParamType.DATE),
            ),
        )
        _patch_registry(monkeypatch, "test_q", query)
        warehouse = FakeWarehouse(result=QueryResult(columns=["id"], rows=[{"id": 1}], truncated=False))
        app = _build_app(warehouse)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Send params in URL order different from declared order; binding
            # must follow declared order.
            resp = await client.get("/api/data/query/test_q?since=2024-01-15&customer_id=C-123&min_qty=5")

        assert resp.status_code == 200
        assert warehouse.last_params == ["C-123", 5, date(2024, 1, 15)]

        # Critical safety property: literal user-supplied values never appear in the SQL string.
        assert warehouse.last_sql is not None
        assert "C-123" not in warehouse.last_sql
        assert "2024-01-15" not in warehouse.last_sql
        assert "5" not in warehouse.last_sql.replace("?", "")
