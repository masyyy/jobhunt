from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.db.models.base import Base


class IngestionLogEntry(Base):
    """Record of a single file ingestion into a Delta table."""

    __tablename__ = "ingestion_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    delta_table: Mapped[str] = mapped_column(String(255), nullable=False)
    delta_version: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime, default=func.now())
