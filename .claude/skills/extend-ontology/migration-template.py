"""Initial migration for derived table `<table_name>`.

Creates the empty Delta table with the schema declared in the recipe at
`data/datasets/derived/<table_name>.recipe.md` (`## Output schema` section).

The migration runner (`scripts/apply_delta_migrations.py`) calls `upgrade()` and
records the applied version on the Delta table's own configuration. Re-running
is a no-op once stamped.

Replace the schema below with the recipe's actual output schema. Use Delta's
PrimitiveType names — see https://delta.io/blog/delta-lake-types/ for the list:
  string | integer | long | float | double | boolean | timestamp | date |
  binary | byte | short | decimal(p,s)

For nested types (struct, array, map) import StructType / ArrayType / MapType
from deltalake.schema and use them as the field's type argument.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("entity_id", PrimitiveType("string"), nullable=False),
        Field("score", PrimitiveType("float"), nullable=True),
        Field("computed_at", PrimitiveType("timestamp"), nullable=False),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
