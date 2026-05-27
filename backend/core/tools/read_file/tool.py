import io
import logging
from pathlib import PurePosixPath

from pydantic_ai import BinaryContent, RunContext

from backend.core.agents.deps import AgentDeps

logger = logging.getLogger(__name__)


def _sanitize_error(e: Exception) -> str:
    """Map exceptions to safe user-facing messages."""
    if isinstance(e, FileNotFoundError):
        return "Error: File or directory not found."
    if isinstance(e, ValueError):
        msg = str(e)
        if any(
            phrase in msg
            for phrase in ("Absolute paths", "Path traversal", "Symbolic links", "not supported", "too large")
        ):
            return f"Error: {msg}"
        return "Error: Invalid path."
    return "Error: Could not read file."


def _slice_pdf(data: bytes, start: int, end: int) -> tuple[bytes, int, int, int]:
    """Slice an inclusive 1-indexed page range. Returns (bytes, kept_start, kept_end, total)."""
    from pypdf import PdfReader, PdfWriter  # noqa: PLC0415

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    kept_start = max(1, start)
    kept_end = min(total, end)
    if kept_start > kept_end:
        raise ValueError(f"page range {start}-{end} is outside the document (1-{total}).")
    writer = PdfWriter()
    for i in range(kept_start, kept_end + 1):
        writer.add_page(reader.pages[i - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), kept_start, kept_end, total


def _pdf_total_pages(data: bytes) -> int:
    from pypdf import PdfReader  # noqa: PLC0415

    return len(PdfReader(io.BytesIO(data)).pages)


def read_file(
    ctx: RunContext[AgentDeps],
    file_path: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> str | BinaryContent:
    """Read a file from the documents directory.

    For text files (.md, .txt, .csv, ...) returns the file's text content.
    For PDFs returns the document as binary so the model can read it natively.
    Pass ``page_start`` and ``page_end`` (1-indexed, inclusive) together to
    attach only a contiguous slice — use this for large PDFs to control token
    use; load the whole file when small. Non-contiguous reads need separate
    calls. Both bounds must be provided together or omitted together.

    Args:
        file_path: Relative path to the file (e.g. "report.md", "manuals/foo.pdf").
        page_start: Optional inclusive 1-indexed start page. PDF only.
        page_end: Optional inclusive 1-indexed end page. PDF only.
    """
    try:
        suffix = PurePosixPath(file_path).suffix.lower()
        if suffix == ".pdf":
            data = ctx.deps.fs.read_bytes(file_path)
            if page_start is not None and page_end is not None:
                data, kept_start, kept_end, total = _slice_pdf(data, page_start, page_end)
                identifier = f"{file_path} (pages {kept_start}-{kept_end} of {total})"
            elif page_start is not None or page_end is not None:
                raise ValueError("page_start and page_end must be provided together.")
            else:
                total = _pdf_total_pages(data)
                identifier = f"{file_path} ({total}-page PDF)"
            return BinaryContent(data=data, media_type="application/pdf", identifier=identifier)
        return ctx.deps.fs.read_text(file_path)
    except (FileNotFoundError, ValueError, OSError) as e:
        logger.warning("read_file failed for %r: %s", file_path, e)
        return _sanitize_error(e)


def list_files(ctx: RunContext[AgentDeps], directory: str = "") -> str:
    """List available files in the documents directory.

    Args:
        directory: Optional subdirectory to list (e.g. "reports"). Defaults to root.
    """
    try:
        files = ctx.deps.fs.list_files(directory)
        if not files:
            return "No files found."
        return "\n".join(files)
    except (FileNotFoundError, ValueError, OSError) as e:
        logger.warning("list_files failed for %r: %s", directory, e)
        return _sanitize_error(e)
