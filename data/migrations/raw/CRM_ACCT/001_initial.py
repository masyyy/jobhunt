"""Initial migration for raw table `CRM_ACCT`.

Snapshot of the schema as ingested from the seeded CSV. Future schema changes
go in numbered sibling files (e.g. `002_add_<column>.py`) using
`dt.alter.add_columns([...])` rather than editing this file.
"""

from __future__ import annotations

from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

SCHEMA = Schema(
    [
        Field("ACCT_ID", PrimitiveType("string"), nullable=True),
        Field("ACCT_NM", PrimitiveType("string"), nullable=True),
        Field("ST_CD", PrimitiveType("string"), nullable=True),
        Field("TIER_CD", PrimitiveType("string"), nullable=True),
        Field("CRTD_DT", PrimitiveType("date"), nullable=True),
        Field("OWN_REP", PrimitiveType("string"), nullable=True),
        Field("STAT_CD", PrimitiveType("string"), nullable=True),
    ]
)


def upgrade(table_uri: str) -> None:
    DeltaTable.create(
        table_uri,
        schema=SCHEMA,
        mode="error",
    )
