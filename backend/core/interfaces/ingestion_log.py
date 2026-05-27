"""Interface for ingestion log persistence."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from backend.core.interfaces.ingestion import IngestionResult


class IngestionLogRepositoryInterface(Protocol):
    async def add(self, result: IngestionResult, *, source_file: str) -> None: ...


IngestionLogRepoFactory = Callable[[], AbstractAsyncContextManager[IngestionLogRepositoryInterface]]
