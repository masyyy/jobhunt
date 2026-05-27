from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ChunkRow:
    """A chunk to write into the index."""

    file_path: str
    page_start: int | None
    page_end: int | None
    content_hash: str
    file_mtime: datetime
    embedding: list[float]


@dataclass(frozen=True)
class SearchHit:
    file_path: str
    page_start: int | None
    page_end: int | None


class DocumentChunkRepository(ABC):
    """Storage for document chunk embeddings."""

    @abstractmethod
    async def search(self, embedding: list[float], *, limit: int) -> list[SearchHit]: ...

    @abstractmethod
    async def replace_for_file(self, file_path: str, chunks: list[ChunkRow]) -> None:
        """Atomically delete all chunks for ``file_path`` and insert the new ones."""

    @abstractmethod
    async def get_mtimes(self) -> dict[str, datetime]:
        """Return one mtime per indexed file_path (any row's mtime is fine)."""

    @abstractmethod
    async def prune_missing(self, present_paths: set[str]) -> int:
        """Delete chunks for files not in ``present_paths``. Returns rows deleted."""
