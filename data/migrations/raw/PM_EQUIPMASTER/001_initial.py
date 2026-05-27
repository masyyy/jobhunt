"""Initial migration for raw table `PM_EQUIPMASTER`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("EQUIP_NO", PrimitiveType("string"), nullable=True),
        Field("WRKCTR_ID", PrimitiveType("string"), nullable=True),
        Field("EQUIP_DESC", PrimitiveType("string"), nullable=True),
        Field("INSTALL_DT", PrimitiveType("date"), nullable=True),
        Field("MFR", PrimitiveType("string"), nullable=True),
        Field("MODEL", PrimitiveType("string"), nullable=True),
        Field("STAT", PrimitiveType("string"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
