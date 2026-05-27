"""Interface for data ingestion services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class IngestionResult:
    """Result of a successful ingestion run."""

    table_name: str
    delta_version: int
    row_count: int
    schema: dict[str, str]


class IngestionService(Protocol):
    """Ingests tabular files into a Delta Lake table."""

    def ingest(self, source_file: Path, table_name: str) -> IngestionResult: ...
