"""Customer-owned task registry.

Controls two things:
  - TOOLBOX_TASKS: which tasks each toolbox opts into (surfaces via the
    task outputs API and the chat UI's task triggers).
  - build_task_registry(deps): the name -> callable mapping consumed by
    LocalTaskQueue. Tasks can be template-provided (imported from
    backend/core/tasks) or customer-specific (defined here or elsewhere
    in customer/).

This is the single source of truth for "which tasks exist in this fork".
dependencies.py consumes this registry; it no longer declares tasks itself.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.core.agents.deps import DocumentChunkRepoFactory
from backend.core.interfaces.embedding_provider import EmbeddingProvider
from backend.core.interfaces.filesystem import FileSystem
from backend.core.interfaces.ingestion import IngestionService
from backend.core.interfaces.ingestion_log import IngestionLogRepoFactory
from backend.core.interfaces.job_matcher import JobMatcher
from backend.core.interfaces.job_repository import JobRepoFactory
from backend.core.interfaces.job_source import JobSource
from backend.core.interfaces.task_output_repository import TaskOutputRepoFactory
from backend.core.tasks.generate_signals import generate_signals
from backend.core.tasks.index_documents import index_documents
from backend.core.tasks.ingest_file import ingest_file
from backend.core.tasks.scrape_jobs import scrape_jobs
from backend.customer.toolboxes import Toolbox
from backend.infrastructure.tasks.local import TaskCallable


@dataclass
class TaskDeps:
    """Dependencies tasks may need. Populated by the API layer per request."""

    task_output_repo_factory: TaskOutputRepoFactory
    ingestion_service: IngestionService
    ingestion_log_repo_factory: IngestionLogRepoFactory
    ingestion_allowed_dir: Path
    on_ingestion_complete: Callable[[], None]
    document_fs: FileSystem
    embedding_provider: EmbeddingProvider
    chunk_repo_factory: DocumentChunkRepoFactory
    job_repo_factory: JobRepoFactory
    job_sources: list[JobSource]
    job_matcher: JobMatcher


TOOLBOX_TASKS: dict[Toolbox, list[str]] = {
    Toolbox.JOBHUNT: ["scrape-jobs"],
}


def build_task_registry(deps: TaskDeps) -> dict[str, TaskCallable]:
    """Return the name -> callable mapping for LocalTaskQueue."""

    async def _generate_signals(prompt: str | None = None, toolbox: str | None = None) -> None:
        await generate_signals(repo_factory=deps.task_output_repo_factory, prompt=prompt, toolbox=toolbox)

    async def _ingest_file(file_path: str, table: str | None = None) -> None:
        await ingest_file(
            ingestion_service=deps.ingestion_service,
            log_repo_factory=deps.ingestion_log_repo_factory,
            file_path=file_path,
            table=table,
            allowed_dir=deps.ingestion_allowed_dir,
        )
        deps.on_ingestion_complete()

    async def _index_documents(root: str = "") -> None:
        await index_documents(
            fs=deps.document_fs,
            embedder=deps.embedding_provider,
            repo_factory=deps.chunk_repo_factory,
            root=root,
        )

    async def _scrape_jobs() -> None:
        await scrape_jobs(
            sources=deps.job_sources,
            repo_factory=deps.job_repo_factory,
            matcher=deps.job_matcher,
        )

    return {
        "generate-signals": _generate_signals,
        "ingest-file": _ingest_file,
        "index-documents": _index_documents,
        "scrape-jobs": _scrape_jobs,
    }
