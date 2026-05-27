from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.interfaces.document_chunk_repository import (
    ChunkRow,
    DocumentChunkRepository,
    SearchHit,
)
from backend.infrastructure.db.models.document_chunk import DocumentChunk


class PgDocumentChunkRepository(DocumentChunkRepository):
    """Postgres + pgvector implementation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, embedding: list[float], *, limit: int) -> list[SearchHit]:
        try:
            stmt = (
                select(DocumentChunk.file_path, DocumentChunk.page_start, DocumentChunk.page_end)
                .order_by(DocumentChunk.embedding.cosine_distance(embedding))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return [
                SearchHit(file_path=row.file_path, page_start=row.page_start, page_end=row.page_end)
                for row in result.all()
            ]
        except Exception:
            await self.session.rollback()
            raise

    async def replace_for_file(self, file_path: str, chunks: list[ChunkRow]) -> None:
        try:
            await self.session.execute(delete(DocumentChunk).where(DocumentChunk.file_path == file_path))
            for c in chunks:
                self.session.add(
                    DocumentChunk(
                        file_path=c.file_path,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        content_hash=c.content_hash,
                        file_mtime=c.file_mtime,
                        embedding=c.embedding,
                    )
                )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def get_mtimes(self) -> dict[str, datetime]:
        try:
            stmt = select(DocumentChunk.file_path, func.max(DocumentChunk.file_mtime)).group_by(DocumentChunk.file_path)
            result = await self.session.execute(stmt)
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            await self.session.rollback()
            raise

    async def prune_missing(self, present_paths: set[str]) -> int:
        try:
            if present_paths:
                stmt = delete(DocumentChunk).where(DocumentChunk.file_path.notin_(present_paths))
            else:
                stmt = delete(DocumentChunk)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount or 0
        except Exception:
            await self.session.rollback()
            raise
