"""Delta Lake ingestion: CSV/Excel → Delta Lake (local or Azure).

The Delta table's schema is created up front by a migration (see
``data/migrations/raw/<TABLE>/001_initial.py`` and
``scripts/apply_delta_migrations.py``). Ingestion validates the incoming batch
against that schema, casts where the cast is unambiguous, and appends. Schema
mismatches are explicit errors — fix them by writing a new migration, not by
silently inferring at write time.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import polars as pl
from deltalake import DeltaTable
from polars._typing import PolarsDataType

from backend.core.interfaces.ingestion import IngestionResult
from backend.core.interfaces.storage_config import DatasetStorageConfig

logger = logging.getLogger(__name__)

_SUPPORTED_CSV_SUFFIXES: frozenset[str] = frozenset({".csv", ".tsv"})
_SUPPORTED_EXCEL_SUFFIXES: frozenset[str] = frozenset({".xlsx", ".xls", ".xlsm"})
_TABLE_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# Map Delta PrimitiveType names to Polars dtypes for casting.
_PRIMITIVE_TO_POLARS: dict[str, PolarsDataType] = {
    "string": pl.String,
    "boolean": pl.Boolean,
    "byte": pl.Int8,
    "short": pl.Int16,
    "integer": pl.Int32,
    "long": pl.Int64,
    "float": pl.Float32,
    "double": pl.Float64,
    "date": pl.Date,
    "timestamp": pl.Datetime("us"),
    "timestamp_ntz": pl.Datetime("us"),
    "binary": pl.Binary,
}


def _detect_and_load(file_path: Path) -> pl.DataFrame:
    """Load a CSV or Excel file into a Polars DataFrame."""
    suffix = file_path.suffix.lower()

    if suffix in _SUPPORTED_CSV_SUFFIXES:
        separator = "\t" if suffix == ".tsv" else ","
        return pl.read_csv(
            file_path,
            separator=separator,
            try_parse_dates=True,
            infer_schema_length=10_000,
        )

    if suffix in _SUPPORTED_EXCEL_SUFFIXES:
        return pl.read_excel(file_path, infer_schema_length=10_000)

    supported = sorted(_SUPPORTED_CSV_SUFFIXES | _SUPPORTED_EXCEL_SUFFIXES)
    msg = f"Unsupported file type '{suffix}'. Supported: {', '.join(supported)}"
    raise ValueError(msg)


def _schema_snapshot(df: pl.DataFrame) -> dict[str, str]:
    return {col: str(dtype) for col, dtype in df.schema.items()}


def _validate_table_name(table_name: str) -> None:
    """Validate table name matches allowed pattern."""
    if not _TABLE_NAME_PATTERN.match(table_name):
        msg = f"Invalid table name '{table_name}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]*."
        raise ValueError(msg)


def _validate_local_table_path(table_name: str, datasets_dir: Path) -> None:
    """Validate table path does not escape datasets directory (local mode only)."""
    table_path = (datasets_dir / table_name).resolve()
    if not table_path.is_relative_to(datasets_dir.resolve()):
        msg = f"Table path escapes datasets directory: {table_name}"
        raise ValueError(msg)


def _delta_type_name(field_type: object) -> str:
    """Return the lowercase primitive name for a Delta field type, or '' for non-primitive."""
    s = str(field_type)
    m = re.match(r'PrimitiveType\("([^"]+)"\)', s)
    return m.group(1).lower() if m else ""


def _conform_to_schema(df: pl.DataFrame, table_uri: str, storage_options: dict[str, str] | None) -> pl.DataFrame:
    """Cast df columns to the Delta table's declared types. Raise on schema drift.

    Rules:
      - Every column the Delta schema declares must be present in df (missing → error).
      - Extra columns in df that aren't in the Delta schema → error (write a migration).
      - Each column is cast to the declared Delta type via Polars; cast failure → error.
      - Non-nullable columns may not contain nulls in the batch.
    """
    dt = DeltaTable(table_uri, storage_options=storage_options)
    schema = dt.schema()

    declared = {f.name: f for f in schema.fields}
    df_cols = set(df.columns)

    missing = [name for name in declared if name not in df_cols]
    extra = [name for name in df_cols if name not in declared]
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing in batch: {missing}")
        if extra:
            parts.append(f"extra in batch (not in migrated schema): {extra}")
        msg = (
            f"Schema mismatch for Delta table at {table_uri}. {'; '.join(parts)}. "
            "Write a migration under data/migrations/<kind>/<table>/ to evolve the schema."
        )
        raise ValueError(msg)

    # Cast columns to declared types, preserving the declared column order.
    cast_exprs: list[pl.Expr] = []
    for field in schema.fields:
        name = field.name
        type_name = _delta_type_name(field.type)
        target = _PRIMITIVE_TO_POLARS.get(type_name)
        if target is None:
            # Non-primitive (struct/array/map) or unknown — pass through and let Delta validate.
            cast_exprs.append(pl.col(name))
            continue
        if df.schema[name] == target:
            cast_exprs.append(pl.col(name))
        else:
            cast_exprs.append(pl.col(name).cast(target, strict=True).alias(name))

    try:
        out = df.select(cast_exprs)
    except pl.exceptions.InvalidOperationError as exc:
        msg = (
            f"Cannot cast batch to Delta schema for {table_uri}: {exc}. "
            "Either fix the source data or evolve the schema via a migration."
        )
        raise ValueError(msg) from exc

    # Enforce declared nullability against the batch.
    for field in schema.fields:
        if not field.nullable and out[field.name].null_count() > 0:
            msg = (
                f"Column '{field.name}' is declared NOT NULL in the migrated schema "
                f"for {table_uri}, but the batch contains null values."
            )
            raise ValueError(msg)

    return out


class DeltaIngestionService:
    """Ingests tabular files into Delta Lake tables (local or Azure).

    Requires the target Delta table to already exist (created by an applied
    migration). Validates and casts the batch to the migrated schema, then
    appends. Does **not** create tables on the fly.
    """

    def __init__(self, storage_config: DatasetStorageConfig) -> None:
        self._config = storage_config

    def ingest(self, source_file: Path, table_name: str) -> IngestionResult:
        """Load a file and append it to a migrated Delta table."""
        if not source_file.exists():
            msg = f"Source file not found: {source_file}"
            raise FileNotFoundError(msg)

        _validate_table_name(table_name)
        if not self._config.is_azure:
            _validate_local_table_path(table_name, Path(self._config.datasets_uri))
            Path(self._config.datasets_uri).mkdir(parents=True, exist_ok=True)

        table_uri = self._config.table_uri(table_name)
        storage_options = self._config.deltalake_storage_options

        if not DeltaTable.is_deltatable(table_uri, storage_options=storage_options):
            msg = (
                f"Delta table for '{table_name}' does not exist at {table_uri}. "
                f"Write a migration at data/migrations/raw/{table_name}/001_initial.py "
                "and run `uv run python scripts/apply_delta_migrations.py` first."
            )
            raise FileNotFoundError(msg)

        logger.info("Loading %s", source_file)
        df = _detect_and_load(source_file)

        if df.is_empty():
            msg = f"File {source_file.name} contains no rows."
            raise ValueError(msg)

        df = _conform_to_schema(df, table_uri, storage_options)

        df.write_delta(
            table_uri,
            mode="append",
            storage_options=storage_options,
        )
        dt = DeltaTable(table_uri, storage_options=storage_options)
        version = dt.version()
        logger.info("Appended %d rows to Delta table '%s' (version %d)", len(df), table_name, version)

        return IngestionResult(
            table_name=table_name,
            delta_version=version,
            row_count=len(df),
            schema=_schema_snapshot(df),
        )
