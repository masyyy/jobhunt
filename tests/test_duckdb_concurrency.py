# pyright: reportPrivateUsage=false
"""Test that DuckDBWarehouse handles concurrent access safely (issue #71)."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import polars as pl

from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.infrastructure.data_warehouse.duckdb_warehouse import DuckDBWarehouse


def _local_storage_config(datasets_dir: Path) -> DatasetStorageConfig:
    return DatasetStorageConfig(
        datasets_uri=str(datasets_dir),
        local_cache_dir=datasets_dir,
    )


def _write_delta_table(datasets_dir: Path, name: str, df: pl.DataFrame) -> None:
    table_path = datasets_dir / name
    table_path.mkdir(parents=True, exist_ok=True)
    df.write_delta(str(table_path))


ORDERS_DF = pl.DataFrame(
    {
        "order_id": [1, 2, 3],
        "customer": ["Acme", "Beta", "Acme"],
        "amount": [100.0, 200.0, 50.0],
    }
)


class TestConcurrentExecuteSql:
    """Reproduce issue #71: parallel execute_sql calls must not raise BinderException."""

    def test_concurrent_execute_sql_no_conflict(self, tmp_path: Path) -> None:
        """Multiple threads calling execute_sql simultaneously should all succeed."""
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        # Prime the warehouse so the DB file exists
        wh.list_tables()

        queries = [
            "SELECT * FROM _raw_orders",
            "SELECT customer, SUM(amount) AS total FROM _raw_orders GROUP BY customer",
            "SELECT COUNT(*) AS cnt FROM _raw_orders",
            "SELECT * FROM _raw_orders WHERE customer = 'Acme'",
        ]

        errors: list[Exception] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(wh.execute_sql, q) for q in queries]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    # Each result should be a valid markdown table, not an error
                    assert "Error:" not in result, f"Query returned error: {result}"
                except Exception as exc:
                    errors.append(exc)

        assert not errors, f"Concurrent execute_sql raised errors: {errors}"

    def test_concurrent_list_tables_no_conflict(self, tmp_path: Path) -> None:
        """Multiple threads calling list_tables simultaneously should all succeed."""
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))

        errors: list[Exception] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(wh.list_tables) for _ in range(4)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    tables = future.result()
                    assert len(tables) > 0, "list_tables returned empty"
                except Exception as exc:
                    errors.append(exc)

        assert not errors, f"Concurrent list_tables raised errors: {errors}"

    def test_mixed_concurrent_operations(self, tmp_path: Path) -> None:
        """Mixing list_tables and execute_sql calls concurrently should work."""
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        # Prime the warehouse
        wh.list_tables()

        errors: list[Exception] = []

        def do_list() -> None:
            tables = wh.list_tables()
            assert len(tables) > 0

        def do_query(sql: str) -> None:
            result = wh.execute_sql(sql)
            assert "Error:" not in result, f"Query returned error: {result}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [
                pool.submit(do_list),
                pool.submit(do_query, "SELECT * FROM _raw_orders"),
                pool.submit(do_list),
                pool.submit(do_query, "SELECT COUNT(*) FROM _raw_orders"),
                pool.submit(do_list),
                pool.submit(do_query, "SELECT customer FROM _raw_orders"),
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errors.append(exc)

        assert not errors, f"Mixed concurrent operations raised errors: {errors}"


class TestRefreshPicksUpNewData:
    """Verify that refresh() makes new Delta data visible."""

    def test_new_rows_visible_after_refresh(self, tmp_path: Path) -> None:
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        result = wh.execute_sql("SELECT COUNT(*) AS cnt FROM _raw_orders")
        assert "| 3 |" in result

        # Append more rows to the Delta table
        extra = pl.DataFrame({"order_id": [4, 5], "customer": ["Gamma", "Delta"], "amount": [300.0, 400.0]})
        table_path = datasets_dir / "orders"
        extra.write_delta(str(table_path), mode="append")

        # delta_scan() views read live — new data is visible immediately
        result = wh.execute_sql("SELECT COUNT(*) AS cnt FROM _raw_orders")
        assert "| 5 |" in result

        # refresh() still works (rebuilds connection for new/removed tables)
        wh.refresh()
        result = wh.execute_sql("SELECT COUNT(*) AS cnt FROM _raw_orders")
        assert "| 5 |" in result

    def test_refresh_during_concurrent_queries(self, tmp_path: Path) -> None:
        """refresh() must not crash queries that are running concurrently."""
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        wh = DuckDBWarehouse(_local_storage_config(datasets_dir))
        wh.list_tables()

        errors: list[Exception] = []
        rounds = 20

        def query_loop() -> None:
            for _ in range(rounds):
                result = wh.execute_sql("SELECT * FROM _raw_orders")
                if "Error:" in result:
                    raise AssertionError(f"Query returned error: {result}")

        def refresh_loop() -> None:
            for _ in range(rounds):
                wh.refresh()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(query_loop),
                pool.submit(query_loop),
                pool.submit(query_loop),
                pool.submit(query_loop),
                pool.submit(refresh_loop),
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errors.append(exc)

        assert not errors, f"Concurrent queries during refresh raised errors: {errors}"

    def test_refresh_races_with_first_query(self, tmp_path: Path) -> None:
        """refresh() concurrent with the very first execute_sql must not crash.

        Reproduces the init-vs-refresh race: _ensure_refreshed() and
        refresh() must use the same lock so they never run
        _refresh_tables() simultaneously.
        """
        datasets_dir = tmp_path / "datasets"
        _write_delta_table(datasets_dir, "orders", ORDERS_DF)

        errors: list[Exception] = []

        # Repeat several times — race windows are narrow
        for _ in range(10):
            wh = DuckDBWarehouse(_local_storage_config(datasets_dir))

            def first_query(w: DuckDBWarehouse = wh) -> None:
                result = w.execute_sql("SELECT COUNT(*) FROM _raw_orders")
                if "Error:" in result:
                    raise AssertionError(f"Query returned error: {result}")

            def immediate_refresh(w: DuckDBWarehouse = wh) -> None:
                w.refresh()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(first_query),
                    pool.submit(immediate_refresh),
                ]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        errors.append(exc)

        assert not errors, f"Init-vs-refresh race raised errors: {errors}"
