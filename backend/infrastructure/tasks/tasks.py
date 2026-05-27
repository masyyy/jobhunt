"""Procrastinate task registrations.

Module-level @app.task decorators (required by Procrastinate) that delegate
to the implementations in backend/core/tasks/. Dependencies are read from
task_deps_holder, which the FastAPI lifespan populates at startup using the
DI helpers in backend.api.dependencies.
"""

from __future__ import annotations

from backend.config import settings
from backend.core.tasks.generate_signals import generate_signals
from backend.core.tasks.index_documents import index_documents
from backend.core.tasks.ingest_file import ingest_file
from backend.core.tasks.scrape_jobs import scrape_jobs
from backend.infrastructure.tasks.procrastinate_app import app
from backend.infrastructure.tasks.task_deps_holder import get_task_deps


@app.task(name="generate-signals", queue="default", pass_context=False)
async def generate_signals_task(prompt: str | None = None, toolbox: str | None = None) -> None:
    deps = get_task_deps()
    await generate_signals(
        repo_factory=deps.task_output_repo_factory,
        prompt=prompt,
        toolbox=toolbox,
    )


@app.task(name="ingest-file", queue="default", pass_context=False)
async def ingest_file_task(file_path: str, table: str | None = None) -> None:
    deps = get_task_deps()
    await ingest_file(
        ingestion_service=deps.ingestion_service,
        log_repo_factory=deps.ingestion_log_repo_factory,
        file_path=file_path,
        table=table,
        allowed_dir=deps.ingestion_allowed_dir,
    )
    deps.on_ingestion_complete()


@app.task(name="index-documents", queue="default", pass_context=False)
async def index_documents_task(root: str = "") -> None:
    deps = get_task_deps()
    await index_documents(
        fs=deps.document_fs,
        embedder=deps.embedding_provider,
        repo_factory=deps.chunk_repo_factory,
        root=root,
    )


@app.task(name="scrape-jobs", queue="default", pass_context=False)
async def scrape_jobs_task() -> None:
    deps = get_task_deps()
    await scrape_jobs(
        sources=deps.job_sources,
        repo_factory=deps.job_repo_factory,
        matcher=deps.job_matcher,
    )


@app.periodic(cron=settings.JOB_SCRAPE_CRON)
@app.task(name="scrape-jobs-periodic", queue="default", pass_context=False)
async def scrape_jobs_periodic(timestamp: int) -> None:
    """Recurring scrape on the JOB_SCRAPE_CRON schedule (default every 6h).

    Procrastinate passes the scheduled ``timestamp``; it deduplicates runs by
    (task, timestamp), so a single worker fires this once per slot.
    """
    deps = get_task_deps()
    await scrape_jobs(
        sources=deps.job_sources,
        repo_factory=deps.job_repo_factory,
        matcher=deps.job_matcher,
    )
