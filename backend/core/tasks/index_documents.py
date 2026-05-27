"""Background task: index files under DOCUMENTS_DIR into pgvector.

Walks the document filesystem, chunks PDFs into 2-page windows (whole-file
chunks for plain text), embeds the chunks, and upserts them into the
``document_chunks`` table. Skips files whose mtime hasn't changed since the
last index. Prunes rows for files that have been deleted.
"""

from __future__ import annotations

import hashlib
import io
import logging

from backend.core.agents.deps import DocumentChunkRepoFactory
from backend.core.interfaces.document_chunk_repository import ChunkRow
from backend.core.interfaces.embedding_provider import EmbeddingProvider
from backend.core.interfaces.filesystem import FileInfo, FileSystem

logger = logging.getLogger(__name__)

TASK_NAME = "index-documents"

EMBEDDING_DIM = 1536
PDF_PAGES_PER_CHUNK = 2

INDEXED_TEXT_EXTENSIONS = {".md", ".txt"}
INDEXED_PDF_EXTENSIONS = {".pdf"}
INDEXED_EXTENSIONS = INDEXED_TEXT_EXTENSIONS | INDEXED_PDF_EXTENSIONS


def _suffix(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _extract_pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def _build_pdf_chunks(pages: list[str]) -> list[tuple[int, int, str]]:
    """Return list of (page_start, page_end, text), 1-indexed inclusive ranges."""
    chunks: list[tuple[int, int, str]] = []
    for i in range(0, len(pages), PDF_PAGES_PER_CHUNK):
        window = pages[i : i + PDF_PAGES_PER_CHUNK]
        text = "\n\n".join(p.strip() for p in window if p.strip())
        if not text:
            continue
        chunks.append((i + 1, i + len(window), text))
    return chunks


async def _index_one_file(
    info: FileInfo,
    *,
    fs: FileSystem,
    embedder: EmbeddingProvider,
    repo_factory: DocumentChunkRepoFactory,
) -> int:
    suffix = "." + _suffix(info.path)

    if suffix in INDEXED_PDF_EXTENSIONS:
        data = fs.read_bytes(info.path)
        pages = _extract_pdf_pages(data)
        windows = _build_pdf_chunks(pages)
        if not windows:
            logger.info("index_documents: %s has no extractable text", info.path)
            async with repo_factory() as repo:
                await repo.replace_for_file(info.path, [])
            return 0
        texts = [text for _, _, text in windows]
        embeddings = await embedder.embed_texts(texts, dimensions=EMBEDDING_DIM)
        rows = [
            ChunkRow(
                file_path=info.path,
                page_start=start,
                page_end=end,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                file_mtime=info.mtime,
                embedding=emb,
            )
            for (start, end, text), emb in zip(windows, embeddings, strict=True)
        ]
    else:
        text = fs.read_text(info.path).strip()
        if not text:
            async with repo_factory() as repo:
                await repo.replace_for_file(info.path, [])
            return 0
        embeddings = await embedder.embed_texts([text], dimensions=EMBEDDING_DIM)
        rows = [
            ChunkRow(
                file_path=info.path,
                page_start=None,
                page_end=None,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                file_mtime=info.mtime,
                embedding=embeddings[0],
            )
        ]

    async with repo_factory() as repo:
        await repo.replace_for_file(info.path, rows)
    return len(rows)


async def index_documents(
    *,
    fs: FileSystem,
    embedder: EmbeddingProvider,
    repo_factory: DocumentChunkRepoFactory,
    root: str = "",
) -> None:
    """Reindex all PDFs and text files under ``root``.

    Skips files whose mtime is unchanged from what's stored. Removes rows for
    files that no longer exist on disk under ``root`` (only when ``root`` is
    empty — partial-tree indexing does not prune).
    """
    all_files = [info for info in fs.stat_files(root) if ("." + _suffix(info.path)) in INDEXED_EXTENSIONS]

    async with repo_factory() as repo:
        existing_mtimes = await repo.get_mtimes()

    indexed = 0
    skipped = 0
    chunks_written = 0
    for info in all_files:
        previous = existing_mtimes.get(info.path)
        if previous is not None and previous >= info.mtime:
            skipped += 1
            continue
        try:
            chunks_written += await _index_one_file(
                info,
                fs=fs,
                embedder=embedder,
                repo_factory=repo_factory,
            )
            indexed += 1
        except Exception:
            logger.exception("index_documents: failed for %s", info.path)

    pruned = 0
    if not root:
        present = {info.path for info in all_files}
        async with repo_factory() as repo:
            pruned = await repo.prune_missing(present)

    logger.info(
        "index_documents: indexed=%d skipped=%d chunks=%d pruned=%d (root=%r)",
        indexed,
        skipped,
        chunks_written,
        pruned,
        root,
    )
