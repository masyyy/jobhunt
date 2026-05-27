"""Initial migration for raw table `CRM_QUOTES`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("QT_ID", PrimitiveType("string"), nullable=True),
        Field("ACCT_ID", PrimitiveType("string"), nullable=True),
        Field("MAT_NO", PrimitiveType("string"), nullable=True),
        Field("QTY", PrimitiveType("long"), nullable=True),
        Field("UNIT_PRC", PrimitiveType("double"), nullable=True),
        Field("TOT_VAL", PrimitiveType("double"), nullable=True),
        Field("CURR", PrimitiveType("string"), nullable=True),
        Field("QT_STATUS", PrimitiveType("string"), nullable=True),
        Field("CRTD_DT", PrimitiveType("date"), nullable=True),
        Field("LAST_ACT_DT", PrimitiveType("date"), nullable=True),
        Field("SLS_REP", PrimitiveType("string"), nullable=True),
        Field("VALID_UNTIL", PrimitiveType("date"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
