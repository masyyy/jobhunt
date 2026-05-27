"""SQLAlchemy implementation of ingestion log repository."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.interfaces.ingestion import IngestionResult
from backend.infrastructure.db.models.ingestion_log import IngestionLogEntry


class IngestionLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, result: IngestionResult, *, source_file: str) -> None:
        try:
            self.session.add(
                IngestionLogEntry(
                    source_file=source_file,
                    delta_table=result.table_name,
                    delta_version=result.delta_version,
                    row_count=result.row_count,
                    schema_snapshot=json.dumps(result.schema),
                )
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
