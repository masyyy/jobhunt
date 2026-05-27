"""Inspect and profile ingested Delta Lake tables.

Standalone CLI — no running backend required.  Subcommands let a coding
agent (or human) explore the warehouse incrementally during ontology creation.

Subcommands:
    schema   List tables/views with column types and row counts.
    profile  Deep-dive one table: sample rows, NULL rates, value distributions.
    query    Run an arbitrary read-only SQL query.

Usage:
    uv run python scripts/warehouse_debug.py schema
    uv run python scripts/warehouse_debug.py profile _raw_SD_SALESORD
    uv run python scripts/warehouse_debug.py profile customers --sample 20
    uv run python scripts/warehouse_debug.py query "SELECT * FROM _raw_SD_SALESORD LIMIT 5"
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import settings
from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.infrastructure.data_warehouse.duckdb_warehouse import DuckDBWarehouse, ensure_delta_extension

_NUMERIC_TYPES = ("int", "float", "double", "decimal", "numeric", "bigint", "smallint", "tinyint", "real", "hugeint")
_TEMPORAL_TYPES = ("date", "timestamp", "time")
_TEXT_TYPES = ("varchar", "char", "text", "utf8")


def _build_warehouse() -> DuckDBWarehouse:
    config = DatasetStorageConfig(
        datasets_uri=str(settings.DATASETS_DIR),
        local_cache_dir=settings.DATASETS_DIR,
        azure_account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
    )
    wh = DuckDBWarehouse(storage_config=config)
    wh.refresh()
    return wh


def _run(wh: DuckDBWarehouse, sql: str) -> str:
    """Run SQL via the warehouse.  Returns the result or prints an error."""
    result = wh.execute_sql(sql)
    if result.startswith("Error:"):
        print(f"  {result}", file=sys.stderr)
        return ""
    return result


def _parse_md_column(result: str, col_index: int = 0) -> list[str]:
    """Extract values from one column of a markdown table."""
    values: list[str] = []
    for line in result.strip().split("\n")[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) > col_index:
            val = cells[col_index].strip()
            if val:
                values.append(val)
    return values


def _get_columns(wh: DuckDBWarehouse, table: str) -> dict[str, str]:
    """Return {column_name: data_type} for a table."""
    result = _run(
        wh,
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table}' ORDER BY ordinal_position",
    )
    if not result:
        return {}
    columns: dict[str, str] = {}
    for line in result.strip().split("\n")[2:]:
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 2:
            columns[parts[0].strip()] = parts[1].strip()
    return columns


def _classify_column(dtype: str) -> str:
    """Classify a DuckDB type string into text/numeric/temporal/other."""
    lower = dtype.lower()
    if any(t in lower for t in _TEMPORAL_TYPES):
        return "temporal"
    if any(t in lower for t in _NUMERIC_TYPES):
        return "numeric"
    if any(t in lower for t in _TEXT_TYPES):
        return "text"
    return "other"


def _row_count(wh: DuckDBWarehouse, table: str) -> str:
    count_result = _run(wh, f'SELECT COUNT(*) AS n FROM "{table}"')
    return _parse_md_column(count_result)[0] if count_result else "?"


def cmd_schema(wh: DuckDBWarehouse, _args: argparse.Namespace) -> None:
    """List all tables and views with schemas and row counts."""
    raw_result = _run(
        wh,
        "SELECT table_name FROM information_schema.tables WHERE table_name LIKE '_raw_%' ORDER BY table_name",
    )
    raw_tables = _parse_md_column(raw_result) if raw_result else []

    view_result = _run(
        wh,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name NOT LIKE '_raw_%' AND table_schema = 'main' "
        "ORDER BY table_name",
    )
    views = _parse_md_column(view_result) if view_result else []

    if not raw_tables and not views:
        print("No tables found. Ingest data first:")
        print("  uv run python scripts/ingest.py --file data/your_file.csv --table my_table")
        return

    all_tables = raw_tables + views

    print(f"Datasets dir: {settings.DATASETS_DIR}")
    print(f"Raw tables:   {len(raw_tables)}")
    print(f"Views:        {len(views)}")

    for table in all_tables:
        kind = "view" if table in views else "raw"
        columns = _get_columns(wh, table)
        rc = _row_count(wh, table)

        print(f"\n{'─' * 60}")
        print(f"{table}  ({kind}, {rc} rows, {len(columns)} cols)")
        print(f"{'─' * 60}")
        for col_name, col_type in columns.items():
            print(f"  {col_name:<40} {col_type}")


def _parse_cardinalities(card_result: str, text_cols: list[str]) -> dict[str, int]:
    """Parse the single-row cardinality result into {col_name: distinct_count}."""
    if not card_result:
        return {}
    lines = card_result.strip().split("\n")
    if len(lines) < 3:
        return {}
    values = [v.strip() for v in lines[2].strip("|").split("|")]
    result: dict[str, int] = {}
    for col, val in zip(text_cols, values, strict=False):
        with contextlib.suppress(ValueError):
            result[col] = int(val.strip())
    return result


_HIGH_CARDINALITY_RATIO = 0.9


def _print_text_top_values(
    wh: DuckDBWarehouse,
    table: str,
    col: str,
    distinct: int,
    row_count: int,
) -> None:
    """Print top values for a text column, or a skip reason."""
    if distinct == 0:
        print(f"\n  {col} — all NULL")
    elif row_count > 0 and distinct >= row_count:
        print(f"\n  {col} — unique (skipping top values)")
    elif row_count > 0 and distinct / row_count > _HIGH_CARDINALITY_RATIO:
        print(f"\n  {col} — near-unique ({distinct}/{row_count}, skipping top values)")
    else:
        result = _run(
            wh,
            f'SELECT "{col}" AS value, COUNT(*) AS n FROM "{table}" '
            f'WHERE "{col}" IS NOT NULL '
            f'GROUP BY "{col}" ORDER BY n DESC LIMIT 10',
        )
        if result:
            print(f"\n  {col} — top values")
            print(result)


def _profile_column_types(
    wh: DuckDBWarehouse,
    table: str,
    columns: dict[str, str],
    row_count: int,
) -> None:
    """Print batched profiling info grouped by column type."""
    text_cols = [c for c, t in columns.items() if _classify_column(t) == "text"]
    numeric_cols = [c for c, t in columns.items() if _classify_column(t) == "numeric"]
    temporal_cols = [c for c, t in columns.items() if _classify_column(t) == "temporal"]

    if text_cols:
        print("\nTEXT COLUMNS — cardinality")
        cardinality_parts = [f'COUNT(DISTINCT "{col}") AS "{col}"' for col in text_cols]
        card_result = _run(wh, f'SELECT {", ".join(cardinality_parts)} FROM "{table}"')
        if card_result:
            print(card_result)

        cardinalities = _parse_cardinalities(card_result, text_cols)
        for col in text_cols:
            _print_text_top_values(wh, table, col, cardinalities.get(col, 0), row_count)

    if numeric_cols:
        print("\nNUMERIC COLUMNS — ranges")
        num_parts: list[str] = []
        for col in numeric_cols:
            num_parts.extend(
                [
                    f'MIN("{col}") AS "{col}_min"',
                    f'MAX("{col}") AS "{col}_max"',
                    f'ROUND(AVG("{col}"::DOUBLE), 2) AS "{col}_avg"',
                ]
            )
        num_result = _run(wh, f'SELECT {", ".join(num_parts)} FROM "{table}"')
        if num_result:
            print(num_result)

    if temporal_cols:
        print("\nTEMPORAL COLUMNS — ranges")
        temp_parts: list[str] = []
        for col in temporal_cols:
            temp_parts.extend(
                [
                    f'MIN("{col}") AS "{col}_min"',
                    f'MAX("{col}") AS "{col}_max"',
                ]
            )
        temp_result = _run(wh, f'SELECT {", ".join(temp_parts)} FROM "{table}"')
        if temp_result:
            print(temp_result)


def cmd_profile(wh: DuckDBWarehouse, args: argparse.Namespace) -> None:
    """Profile a single table: sample, NULL rates, value distributions."""
    table = args.table
    columns = _get_columns(wh, table)
    if not columns:
        print(f"Table '{table}' not found or has no columns.", file=sys.stderr)
        sys.exit(1)

    rc_str = _row_count(wh, table)
    rc = int(rc_str) if rc_str != "?" else 0
    print(f"{table}  ({rc_str} rows, {len(columns)} cols)\n")

    print("SCHEMA")
    for col_name, col_type in columns.items():
        print(f"  {col_name:<40} {col_type}")

    print(f"\nSAMPLE ({args.sample} rows)")
    sample = _run(wh, f'SELECT * FROM "{table}" LIMIT {args.sample}')
    if sample:
        print(sample)

    print("\nNULL RATES")
    parts = [f'ROUND(1.0 - COUNT("{col}")::DOUBLE / NULLIF(COUNT(*), 0), 3) AS "{col}"' for col in columns]
    null_result = _run(wh, f'SELECT {", ".join(parts)} FROM "{table}"')
    if null_result:
        print(null_result)

    _profile_column_types(wh, table, columns, rc)


def cmd_query(wh: DuckDBWarehouse, args: argparse.Namespace) -> None:
    """Run an arbitrary SQL query against the warehouse."""
    result = wh.execute_sql(args.sql)
    print(result)
    if result.startswith("Error:"):
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and profile ingested Delta Lake tables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python scripts/warehouse_debug.py schema\n"
            "  uv run python scripts/warehouse_debug.py profile _raw_SD_SALESORD\n"
            "  uv run python scripts/warehouse_debug.py profile customers --sample 20\n"
            '  uv run python scripts/warehouse_debug.py query "SELECT COUNT(*) FROM _raw_SD_SALESORD"'
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("schema", help="List tables/views with columns and row counts.")

    profile_p = sub.add_parser("profile", help="Profile a single table in detail.")
    profile_p.add_argument("table", help="Table or view name exactly as shown by 'schema'.")
    profile_p.add_argument("--sample", type=int, default=5, metavar="N", help="Sample rows (default: 5).")

    query_p = sub.add_parser("query", help="Run an arbitrary read-only SQL query.")
    query_p.add_argument("sql", help="SQL query string.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    ensure_delta_extension()
    wh = _build_warehouse()

    commands = {
        "schema": cmd_schema,
        "profile": cmd_profile,
        "query": cmd_query,
    }
    commands[args.command](wh, args)


if __name__ == "__main__":
    main()
