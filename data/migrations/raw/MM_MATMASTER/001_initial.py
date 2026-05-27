"""Initial migration for raw table `MM_MATMASTER`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("MAT_NO", PrimitiveType("string"), nullable=True),
        Field("MAT_DESC", PrimitiveType("string"), nullable=True),
        Field("MAT_GRP", PrimitiveType("string"), nullable=True),
        Field("BASE_UOM", PrimitiveType("string"), nullable=True),
        Field("STD_COST", PrimitiveType("double"), nullable=True),
        Field("LIST_PRC", PrimitiveType("double"), nullable=True),
        Field("WEIGHT_KG", PrimitiveType("double"), nullable=True),
        Field("STAT", PrimitiveType("string"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
