"""Background task: ingest a tabular file into a Delta Lake table."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.core.interfaces.ingestion import IngestionService
from backend.core.interfaces.ingestion_log import IngestionLogRepoFactory

logger = logging.getLogger(__name__)


async def ingest_file(
    *,
    ingestion_service: IngestionService,
    log_repo_factory: IngestionLogRepoFactory,
    file_path: str,
    table: str | None = None,
    allowed_dir: Path | None = None,
) -> None:
    """Ingest a CSV/Excel file into a Delta table (runs sync I/O in a thread)."""
    source = Path(file_path).resolve()

    if allowed_dir is not None and not source.is_relative_to(allowed_dir.resolve()):
        msg = f"File path '{file_path}' is outside the allowed directory."
        raise ValueError(msg)

    table_name = (table or source.stem).strip()

    if not table_name:
        logger.error("Table name cannot be empty.")
        return

    try:
        result = await asyncio.to_thread(ingestion_service.ingest, source, table_name)

        async with log_repo_factory() as repo:
            await repo.add(result, source_file=str(source))

        logger.info(
            "Ingested %d rows into '%s' (version %d)",
            result.row_count,
            result.table_name,
            result.delta_version,
        )
    except Exception:
        logger.exception("Failed to ingest %s", file_path)
