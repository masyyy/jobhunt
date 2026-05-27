"""Initial migration for raw table `PP_DWNTIME_LOG`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("EVT_ID", PrimitiveType("long"), nullable=True),
        Field("WRKCTR_ID", PrimitiveType("string"), nullable=True),
        Field("EQUIP_NO", PrimitiveType("string"), nullable=True),
        Field("DT_START", PrimitiveType("timestamp_ntz"), nullable=True),
        Field("DT_END", PrimitiveType("timestamp_ntz"), nullable=True),
        Field("DUR_MIN", PrimitiveType("long"), nullable=True),
        Field("RSN_CD", PrimitiveType("string"), nullable=True),
        Field("SHIFT_CD", PrimitiveType("string"), nullable=True),
        Field("RPRT_BY", PrimitiveType("string"), nullable=True),
        Field("NOTES", PrimitiveType("string"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
