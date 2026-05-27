"""Semantic file search backed by pgvector (parent-document retrieval).

Chunks are the retrieval primitive but the agent sees only the parent file:
exactly one ``FileHit`` per file, with a ``matched_pages`` hint pointing at
where matches concentrated. The agent then decides how to read — small file:
load whole; large file: skim a few pages, then zoom into matched ranges via
``read_file(path, page_start=..., page_end=...)``.
"""

import io
import logging

from pydantic import BaseModel
from pydantic_ai import RunContext

from backend.core.agents.deps import AgentDeps
from backend.core.interfaces.document_chunk_repository import SearchHit
from backend.core.interfaces.filesystem import FileSystem

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
MAX_LIMIT = 20


class PageRange(BaseModel):
    start: int
    end: int


class FileHit(BaseModel):
    file_path: str
    page_count: int | None = None
    matched_pages: list[PageRange] = []


async def search_files(
    ctx: RunContext[AgentDeps],
    query: str,
    limit: int = 5,
) -> list[FileHit] | str:
    """Find files most relevant to a natural-language query.

    Returns at most one entry per file. ``page_count`` (for PDFs) tells you
    how big the file is; ``matched_pages`` is a soft hint about which pages
    drove the match. Then call ``read_file`` to actually read the content —
    the whole file for small docs, or a specific ``page_start``/``page_end``
    range for big ones.

    Args:
        query: A natural-language description of what you're looking for.
        limit: Max chunk hits to consider (1-20). Defaults to 5. Files are
            deduplicated, so the number of returned files may be smaller.
    """
    if not query.strip():
        return "Error: query must not be empty."
    capped = max(1, min(limit, MAX_LIMIT))
    try:
        embeddings = await ctx.deps.embedder.embed_texts([query], dimensions=EMBEDDING_DIM)
    except RuntimeError as e:
        logger.warning("search_files: embedding failed: %s", e)
        return f"Error: {e}"
    except Exception:
        logger.exception("search_files: embedding failed")
        return "Error: embedding service unavailable."

    try:
        async with ctx.deps.chunk_repo_factory() as repo:
            hits = await repo.search(embeddings[0], limit=capped)
    except Exception:
        logger.exception("search_files: search failed")
        return "Error: search failed."

    return _consolidate_to_file_level(hits, fs=ctx.deps.fs)


def _consolidate_to_file_level(hits: list[SearchHit], *, fs: FileSystem) -> list[FileHit]:
    """Collapse chunk-level hits into one ``FileHit`` per file.

    Preserves first-appearance order (best-ranked file first). Within a file,
    contiguous/overlapping page ranges are merged into the ``matched_pages``
    hint.
    """
    file_order: list[str] = []
    by_file: dict[str, list[SearchHit]] = {}
    for h in hits:
        if h.file_path not in by_file:
            file_order.append(h.file_path)
            by_file[h.file_path] = []
        by_file[h.file_path].append(h)

    result: list[FileHit] = []
    for file_path in file_order:
        group = by_file[file_path]
        ranges = _merge_ranges(
            [(h.page_start, h.page_end) for h in group if h.page_start is not None and h.page_end is not None]
        )
        page_count = _pdf_page_count_safe(file_path, fs) if file_path.lower().endswith(".pdf") else None
        result.append(
            FileHit(
                file_path=file_path,
                page_count=page_count,
                matched_pages=[PageRange(start=s, end=e) for s, e in ranges],
            )
        )
    return result


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge contiguous/overlapping (start, end) page ranges. Inclusive ends."""
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged: list[tuple[int, int]] = [ranges[0]]
    for start, end in ranges[1:]:
        cur_start, cur_end = merged[-1]
        if start <= cur_end + 1:
            merged[-1] = (cur_start, max(cur_end, end))
        else:
            merged.append((start, end))
    return merged


def _pdf_page_count_safe(file_path: str, fs: FileSystem) -> int | None:
    try:
        from pypdf import PdfReader  # noqa: PLC0415

        return len(PdfReader(io.BytesIO(fs.read_bytes(file_path))).pages)
    except Exception:
        logger.exception("search_files: page count lookup failed for %s", file_path)
        return None
