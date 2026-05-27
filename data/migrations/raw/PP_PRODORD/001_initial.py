"""Initial migration for raw table `PP_PRODORD`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("ORD_NO", PrimitiveType("string"), nullable=True),
        Field("MAT_NO", PrimitiveType("string"), nullable=True),
        Field("WRKCTR_ID", PrimitiveType("string"), nullable=True),
        Field("PLANNED_QTY", PrimitiveType("long"), nullable=True),
        Field("ACTUAL_QTY", PrimitiveType("long"), nullable=True),
        Field("SCRAP_QTY", PrimitiveType("long"), nullable=True),
        Field("UOM", PrimitiveType("string"), nullable=True),
        Field("ORD_STATUS", PrimitiveType("string"), nullable=True),
        Field("SCHED_START", PrimitiveType("date"), nullable=True),
        Field("SCHED_END", PrimitiveType("date"), nullable=True),
        Field("ACT_START", PrimitiveType("date"), nullable=True),
        Field("ACT_END", PrimitiveType("date"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
