# pyright: reportPrivateUsage=false
"""Tests for the semantic views layer in DuckDBWarehouse."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from backend.core.agents.chat_agent import build_schema_instructions
from backend.core.interfaces.data_warehouse import TableInfo
from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.infrastructure.data_warehouse.duckdb_warehouse import (
    DuckDBWarehouse,
    parse_view_file,
)


def _local_storage_config(datasets_dir: Path) -> DatasetStorageConfig:
    return DatasetStorageConfig(
        datasets_uri=str(datasets_dir),
        local_cache_dir=datasets_dir,
    )


@pytest.fixture
def datasets_dir(tmp_path: Path) -> Path:
    return tmp_path / "datasets"


def _write_delta_table(datasets_dir: Path, name: str, df: pl.DataFrame) -> None:
    """Write a polars DataFrame as a Delta Lake table in datasets_dir/{name}/."""
    table_path = datasets_dir / name
    table_path.mkdir(parents=True, exist_ok=True)
    df.write_delta(str(table_path))


def _write_view(datasets_dir: Path, filename: str, sql: str) -> None:
    """Write a .sql view file into datasets_dir/views/."""
    views_dir = datasets_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    (views_dir / filename).write_text(sql)


ORDERS_DF = pl.DataFrame(
    {
        "order_id": [1, 2, 3],
        "customer": ["Acme", "Beta", "Acme"],
        "amount": [100.0, 200.0, 50.0],
    }
)


# -- parse_view_file tests ---------------------------------------------------


class TestParseViewFile:
    def test_extracts_description(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text("-- description: Order totals per customer\nCREATE OR REPLACE VIEW order_totals AS SELECT 1")
        sql, desc, name = parse_view_file(f)
        assert desc == "Order totals per customer"
        assert name == "order_totals"
        assert "CREATE OR REPLACE VIEW" in sql

    def test_no_description(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text("CREATE OR REPLACE VIEW foo AS SELECT 1")
        _, desc, name = parse_view_file(f)
        assert desc is None
        assert name == "foo"

    def test_no_create_view(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.sql"
        f.write_text("DROP TABLE orders")
        _, desc, name = parse_view_file(f)
        assert desc is None
        assert name is None

    def test_view_name_from_sql_not_filename(self, tmp_path: Path) -> None:
        f = tmp_path / "filename_does_not_matter.sql"
        f.write_text("-- description: Real name test\nCREATE OR REPLACE VIEW actual_name AS SELECT 1")
        _, _, name = parse_view_file(f)
        assert name == "actual_name"

    def test_quoted_view_name(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text('CREATE OR REPLACE VIEW "my_view" AS SELECT 1')
        _, _, name = parse_view_file(f)
        assert name == "my_view"

    def test_case_insensitive_create(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text("create or replace view mixed_case AS SELECT 1")
        _, _, name = parse_view_file(f)
        assert name == "mixed_case"

    def test_schema_qualified_name(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text("CREATE OR REPLACE VIEW main.order_totals AS SELECT 1")
        _, _, name = parse_view_file(f)
        assert name == "order_totals"

    def test_schema_qualified_quoted_name(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text('CREATE OR REPLACE VIEW main."order-totals" AS SELECT 1')
        _, _, name = parse_view_file(f)
        assert name == "order-totals"

    def test_quoted_name_with_special_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "v.sql"
        f.write_text('CREATE OR REPLACE VIEW "spare parts ops" AS SELECT 1')
        _, _, name = parse_view_file(f)
        assert name == "spare parts ops"


# -- list_tables integration tests -------------------------------------------


class TestListTablesWithViews:
    def test_views_loaded_and_exposed(self, datasets_dir: Path) -> None:
        """list_tables returns views loaded from .sql files, not raw tables."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)
        _write_view(
            datasets_dir,
            "order_totals.sql",
            "-- description: Order totals per customer\n"
            "CREATE OR REPLACE VIEW order_totals AS\n"
            "SELECT customer, SUM(amount) AS total "
            "FROM _raw_orders GROUP BY customer",
        )

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()

        names = [t.name for t in tables]
        assert "order_totals" in names
        assert "_raw_orders" not in names

        info = tables[0]
        assert info.description == "Order totals per customer"
        assert "customer" in info.columns
        assert "total" in info.columns

    def test_view_name_from_sql_not_filename(self, datasets_dir: Path) -> None:
        """View name in registry comes from SQL, not the .sql filename."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)
        _write_view(
            datasets_dir,
            "misnamed_file.sql",
            "CREATE OR REPLACE VIEW order_totals AS\n"
            "SELECT customer, SUM(amount) AS total "
            "FROM _raw_orders GROUP BY customer",
        )

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()

        names = [t.name for t in tables]
        assert "order_totals" in names
        assert "misnamed_file" not in names

    def test_invalid_view_sql_skipped(self, datasets_dir: Path) -> None:
        """A .sql file without CREATE OR REPLACE VIEW is ignored."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)
        _write_view(datasets_dir, "bad.sql", "SELECT 1")
        _write_view(
            datasets_dir,
            "good.sql",
            "CREATE OR REPLACE VIEW good_view AS SELECT 1 AS x",
        )

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()

        names = [t.name for t in tables]
        assert "good_view" in names
        assert "bad" not in names

    def test_no_views_exposes_raw_tables(self, datasets_dir: Path) -> None:
        """Without views, list_tables falls back to raw tables."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()

        names = [t.name for t in tables]
        assert names == ["_raw_orders"]
        assert "customer" in tables[0].columns

    def test_empty_datasets_returns_empty(self, datasets_dir: Path) -> None:
        """No Delta tables and no views → empty list."""
        datasets_dir.mkdir(parents=True)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()

        assert tables == []


# -- execute_sql through views -----------------------------------------------


class TestExecuteSqlWithViews:
    def test_query_via_view(self, datasets_dir: Path) -> None:
        """execute_sql can query through a view."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)
        _write_view(
            datasets_dir,
            "order_totals.sql",
            "CREATE OR REPLACE VIEW order_totals AS\n"
            "SELECT customer, SUM(amount) AS total "
            "FROM _raw_orders GROUP BY customer",
        )

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        result = wh.execute_sql("SELECT * FROM order_totals ORDER BY customer")

        assert "Acme" in result
        assert "150.0" in result
        assert "Beta" in result
        assert "200.0" in result


# -- Read-only enforcement ----------------------------------------------------


class TestReadOnlyEnforcement:
    """Verify that the query connection rejects DDL/DML at the engine level."""

    def test_multi_statement_drop_blocked(self, datasets_dir: Path) -> None:
        """SELECT 1; DROP VIEW must be rejected by the read-only connection."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        result = wh.execute_sql("SELECT 1; DROP VIEW _raw_orders")
        assert "Error:" in result

        # The view must still be intact
        result = wh.execute_sql("SELECT COUNT(*) AS cnt FROM _raw_orders")
        assert "| 3 |" in result

    def test_drop_view_blocked(self, datasets_dir: Path) -> None:
        """Direct DROP VIEW must be rejected."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        wh.list_tables()
        result = wh.execute_sql("DROP VIEW _raw_orders")
        assert "Error:" in result

    def test_create_table_blocked(self, datasets_dir: Path) -> None:
        """CREATE TABLE must be rejected."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        wh.list_tables()
        result = wh.execute_sql("CREATE TABLE evil (id INT)")
        assert "Error:" in result

    def test_insert_blocked(self, datasets_dir: Path) -> None:
        """INSERT must be rejected."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        wh.list_tables()
        result = wh.execute_sql("INSERT INTO _raw_orders VALUES (99, 'Evil', 0.0)")
        assert "Error:" in result

    def test_external_file_access_blocked(self, datasets_dir: Path) -> None:
        """read_csv_auto on a file outside datasets must be rejected."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        wh.list_tables()
        result = wh.execute_sql("SELECT * FROM read_csv_auto('/etc/hosts') LIMIT 1")
        assert "Error:" in result


# -- Stale view cleanup ------------------------------------------------------


class TestStaleViewCleanup:
    def test_stale_view_dropped_on_refresh(self, datasets_dir: Path) -> None:
        """A view removed from disk is dropped on the next list_tables call."""
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)
        view_file = datasets_dir / "views" / "old_view.sql"
        _write_view(
            datasets_dir,
            "old_view.sql",
            "CREATE OR REPLACE VIEW old_view AS SELECT 1 AS x",
        )

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        tables = wh.list_tables()
        assert any(t.name == "old_view" for t in tables)

        # Remove the view file and trigger explicit refresh (simulates post-ingestion)
        view_file.unlink()
        wh.refresh()
        tables = wh.list_tables()

        # old_view gone; should fall back to raw tables
        names = [t.name for t in tables]
        assert "old_view" not in names
        assert "_raw_orders" in names

        # Confirm the view is actually gone in DuckDB (not just hidden)
        result = wh.execute_sql("SELECT * FROM old_view")
        assert "Table not found" in result


# -- Description in system prompt ---------------------------------------------


class TestSchemaInstructions:
    def test_description_included(self) -> None:
        tables = [
            TableInfo(
                "order_totals",
                {"customer": "VARCHAR", "total": "DOUBLE"},
                "Order totals per customer",
            ),
        ]
        prompt = build_schema_instructions(tables)
        assert "**order_totals** — *Order totals per customer*" in prompt
        assert "customer (VARCHAR)" in prompt

    def test_no_description(self) -> None:
        tables = [
            TableInfo("raw_data", {"id": "INTEGER"}),
        ]
        prompt = build_schema_instructions(tables)
        assert "- **raw_data**: id (INTEGER)" in prompt
        assert "—" not in prompt

    def test_empty_tables(self) -> None:
        assert build_schema_instructions([]) == ""

    def test_mixed_descriptions(self) -> None:
        tables = [
            TableInfo("with_desc", {"a": "INT"}, "Has a description"),
            TableInfo("without_desc", {"b": "INT"}),
        ]
        prompt = build_schema_instructions(tables)
        assert "— *Has a description*" in prompt
        assert "- **without_desc**: b (INT)" in prompt
