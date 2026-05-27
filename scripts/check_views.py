"""Validate that every SQL view in data/datasets/views/ compiles and returns
at least one row.

Uses the same view-loader as the production DuckDBWarehouse so this check
reflects what the live agent actually sees. If production silently drops a
view (e.g. because of an unresolvable dependency), this script fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.infrastructure.data_warehouse.duckdb_warehouse import (
    DuckDBWarehouse,
    parse_view_file,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "datasets"
VIEWS = DATA / "views"


def main() -> int:
    conn = duckdb.connect()

    # Register _raw_<NAME> views for every Delta table under data/datasets/.
    if not DATA.exists():
        print(f"No datasets directory at {DATA}")
        return 1
    for entry in sorted(DATA.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "_delta_log").is_dir():
            continue
        conn.execute(f"CREATE OR REPLACE VIEW _raw_{entry.name} AS SELECT * FROM delta_scan('{entry}')")
        print(f"  loaded raw {entry.name}")

    # Load views via the production loader's fixed-point algorithm.
    config = DatasetStorageConfig(datasets_uri=str(DATA), local_cache_dir=DATA)
    warehouse = DuckDBWarehouse(config)
    try:
        view_names, _ = warehouse._load_sql_views(conn)  # pyright: ignore[reportPrivateUsage]
    except Exception as exc:
        print(f"\nView load failed: {exc}")
        return 1

    # Confirm every .sql file was loaded (the loader logs skips but returns
    # successfully).
    sql_files = sorted(VIEWS.glob("*.sql"))
    expected: set[str] = set()
    for f in sql_files:
        _, _, view_name = parse_view_file(f)
        if view_name is not None:
            expected.add(view_name)

    missing = expected - view_names
    if missing:
        print(f"\nViews missing after load: {sorted(missing)}")
        return 1

    # Count rows per view so empty views are visible.
    for view in sorted(view_names):
        count = conn.execute(f"SELECT COUNT(*) FROM {view}").fetchall()[0][0]
        print(f"  OK  {view:35s} rows={count}")

    print(f"\nAll {len(view_names)} views compiled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
