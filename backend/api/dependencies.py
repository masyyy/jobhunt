"""FastAPI dependency injection functions.

Centralizes all dependency creation so routers never construct
infrastructure objects directly.
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from procrastinate import App as ProcrastinateApp
from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.agents.deps import AgentDeps, DocumentChunkRepoFactory
from backend.core.agents.model_config import MODEL_MAIN, get_model
from backend.core.interfaces.application_assistant import ApplicationAssistant
from backend.core.interfaces.conversation_repository import ConversationRepositoryInterface, RepositoryFactory
from backend.core.interfaces.document_chunk_repository import DocumentChunkRepository
from backend.core.interfaces.ingestion_log import IngestionLogRepositoryInterface
from backend.core.interfaces.job_repository import JobRepoFactory, JobRepositoryInterface
from backend.core.interfaces.job_source import JobSource
from backend.core.interfaces.prompt_loader import PromptLoader
from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.core.interfaces.task_output_repository import TaskOutputRepositoryInterface
from backend.core.interfaces.task_queue import TaskQueue
from backend.core.services.compaction import SUMMARIZATION_AGENT_INSTRUCTIONS, CompactionService
from backend.customer.tasks import TaskDeps, build_task_registry
from backend.infrastructure.data_warehouse.duckdb_warehouse import DuckDBWarehouse
from backend.infrastructure.db.database import AsyncSessionLocal, get_db_session
from backend.infrastructure.db.repositories.conversation_repository import ConversationRepository
from backend.infrastructure.db.repositories.document_chunk_repository import PgDocumentChunkRepository
from backend.infrastructure.db.repositories.ingestion_log_repository import IngestionLogRepository
from backend.infrastructure.db.repositories.job_repository import JobRepository
from backend.infrastructure.db.repositories.task_output_repository import TaskOutputRepository
from backend.infrastructure.embeddings import OpenAIEmbeddingProvider
from backend.infrastructure.filesystem.local import LocalFileSystem
from backend.infrastructure.application_assistant.llm import LlmApplicationAssistant
from backend.infrastructure.job_matcher.llm import LlmJobMatcher
from backend.infrastructure.job_sources.duunitori import DuunitoriSource
from backend.infrastructure.job_sources.kuntarekry import KuntarekrySource
from backend.infrastructure.job_sources.tyomarkkinatori import TyomarkkinatoriSource
from backend.infrastructure.ingestion.local import DeltaIngestionService
from backend.infrastructure.prompts.local import FilePromptLoader
from backend.infrastructure.tasks.local import LocalTaskQueue
from backend.infrastructure.tasks.procrastinate_app import app as procrastinate_app
from backend.infrastructure.tasks.procrastinate_queue import ProcrastinateTaskQueue


def get_prompt_loader() -> PromptLoader:
    """Get prompt loader instance."""
    return FilePromptLoader(prompts_dir=settings.PROMPTS_DIR)


@lru_cache(maxsize=1)
def _get_storage_config() -> DatasetStorageConfig:
    """Build storage config from environment settings."""
    if settings.AZURE_STORAGE_ACCOUNT_NAME:
        datasets_uri = f"az://{settings.AZURE_STORAGE_CONTAINER}"
    else:
        datasets_uri = str(settings.DATASETS_DIR)
    return DatasetStorageConfig(
        datasets_uri=datasets_uri,
        local_cache_dir=settings.DATASETS_DIR,
        azure_account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
    )


@lru_cache(maxsize=1)
def get_warehouse() -> DuckDBWarehouse:
    """Get or create the singleton DuckDB warehouse."""
    return DuckDBWarehouse(storage_config=_get_storage_config())


@lru_cache(maxsize=1)
def _get_embedding_provider() -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider()


def _get_chunk_repo_factory() -> DocumentChunkRepoFactory:
    @asynccontextmanager
    async def _create() -> AsyncIterator[DocumentChunkRepository]:
        async with AsyncSessionLocal() as session:
            yield PgDocumentChunkRepository(session)

    return _create


def get_agent_deps() -> AgentDeps:
    """Get PydanticAI agent dependencies."""
    return AgentDeps(
        fs=LocalFileSystem(root_dir=settings.DOCUMENTS_DIR),
        db=get_warehouse(),
        embedder=_get_embedding_provider(),
        chunk_repo_factory=_get_chunk_repo_factory(),
    )


def get_conversation_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ConversationRepositoryInterface:
    """Get conversation repository instance."""
    return ConversationRepository(session)


def get_repository_factory() -> RepositoryFactory:
    """Get a factory for creating repository instances in background tasks.

    Returns a callable that produces an async context manager yielding
    ConversationRepositoryInterface. Use this for code that runs outside
    request scope (on_complete callbacks, background compaction tasks).
    """

    @asynccontextmanager
    async def _create_repository() -> AsyncIterator[ConversationRepositoryInterface]:
        async with AsyncSessionLocal() as session:
            yield ConversationRepository(session)

    return _create_repository


def get_compaction_service(
    repo_factory: RepositoryFactory = Depends(get_repository_factory),
) -> CompactionService:
    """Get compaction service with injected dependencies."""
    summarize_agent: Agent[None, str] = Agent(
        get_model(MODEL_MAIN),
        instructions=SUMMARIZATION_AGENT_INSTRUCTIONS,
    )
    return CompactionService(repo_factory, summarize_agent)


async def verify_internal_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Verify the X-API-Key header for internal endpoints."""
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.INTERNAL_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def verify_app_password(x_app_password: str | None = Header(default=None)) -> None:
    """Verify the X-App-Password header gating the public app endpoints."""
    if x_app_password is None or not secrets.compare_digest(x_app_password, settings.APP_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid or missing app password")


def get_task_output_repository(
    session: AsyncSession = Depends(get_db_session),
) -> TaskOutputRepositoryInterface:
    """Get task output repository instance."""
    return TaskOutputRepository(session)


def get_job_repository(
    session: AsyncSession = Depends(get_db_session),
) -> JobRepositoryInterface:
    """Get job repository instance."""
    return JobRepository(session)


def get_application_assistant() -> ApplicationAssistant:
    """Get the LLM-backed application assistant (cover letter + how-to-apply)."""
    return LlmApplicationAssistant()


def get_job_repo_factory() -> JobRepoFactory:
    """Get a factory for creating job repositories in background tasks."""

    @asynccontextmanager
    async def _create() -> AsyncIterator[JobRepositoryInterface]:
        async with AsyncSessionLocal() as session:
            yield JobRepository(session)

    return _create


def get_procrastinate_app() -> ProcrastinateApp:
    """Return the module-level Procrastinate App singleton."""
    return procrastinate_app


@lru_cache(maxsize=1)
def _get_procrastinate_queue() -> ProcrastinateTaskQueue:
    return ProcrastinateTaskQueue(procrastinate_app)


def build_job_sources() -> list[JobSource]:
    """Construct the job-source scrapers used by the scrape-jobs task."""
    return [
        DuunitoriSource(),
        TyomarkkinatoriSource(),
        KuntarekrySource(),
    ]


def build_task_deps() -> TaskDeps:
    """Construct TaskDeps wired to the process-wide infrastructure singletons.

    Used by both the local backend (per-request) and the Procrastinate worker
    (populated once at lifespan startup via task_deps_holder.set_task_deps).
    """

    @asynccontextmanager
    async def _task_output_repo() -> AsyncIterator[TaskOutputRepositoryInterface]:
        async with AsyncSessionLocal() as session:
            yield TaskOutputRepository(session)

    @asynccontextmanager
    async def _ingestion_log_repo() -> AsyncIterator[IngestionLogRepositoryInterface]:
        async with AsyncSessionLocal() as session:
            yield IngestionLogRepository(session)

    return TaskDeps(
        task_output_repo_factory=_task_output_repo,
        ingestion_service=DeltaIngestionService(storage_config=_get_storage_config()),
        ingestion_log_repo_factory=_ingestion_log_repo,
        ingestion_allowed_dir=settings.INGESTION_INPUT_DIR,
        on_ingestion_complete=lambda: get_warehouse().refresh(),
        document_fs=LocalFileSystem(root_dir=settings.DOCUMENTS_DIR),
        embedding_provider=_get_embedding_provider(),
        chunk_repo_factory=_get_chunk_repo_factory(),
        job_repo_factory=get_job_repo_factory(),
        job_sources=build_job_sources(),
        job_matcher=LlmJobMatcher(),
    )


def get_task_queue() -> TaskQueue:
    """Get the task queue. Backend is chosen by settings.TASK_BACKEND."""
    if settings.TASK_BACKEND == "procrastinate":
        return _get_procrastinate_queue()
    return LocalTaskQueue(tasks=build_task_registry(build_task_deps()))
