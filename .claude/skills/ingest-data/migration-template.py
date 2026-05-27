"""Initial migration for raw table `<TABLE_NAME>`.

Declares the Delta schema for a customer source table. The migration runner
(`scripts/apply_delta_migrations.py`) creates the empty Delta table from this
schema; ingestion appends batches that match it.

Future schema changes live in numbered sibling files (e.g. `002_add_<column>.py`)
using `dt.alter.add_columns([...])`. Do not edit `001_initial.py` once the table
has been created in any environment — write a new migration instead.

Use Delta's PrimitiveType names — see https://delta.io/blog/delta-lake-types/:
  string | integer | long | float | double | boolean | timestamp | date |
  binary | byte | short | decimal(p,s)

Mark required identifiers and join keys `nullable=False`. Keep everything else
nullable by default — upstream systems frequently drop optional fields.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("PRIMARY_KEY", PrimitiveType("string"), nullable=False),
        # Add one Field(...) per column the source system delivers.
        # Use the source-system column names verbatim (uppercase, raw codes);
        # the views layer is responsible for renaming and decoding.
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
