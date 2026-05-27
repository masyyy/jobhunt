from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    OPENAI_API_KEY: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/fulcrum"

    # Azure PostgreSQL: if both are set, database_url property uses these instead
    POSTGRES_HOST: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_USER: str = "fulcrumadmin"
    POSTGRES_DB: str = "fulcrum"

    DOCUMENTS_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "documents"
    DATASETS_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "datasets"
    INGESTION_INPUT_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    PROMPTS_DIR: Path = Path(__file__).resolve().parent / "prompts"
    # Internal API key gates /internal/tasks/*. Dev-only default; startup
    # rejects this value (and empty) when DEBUG is off, so production must
    # set a real key via env. See _validate_internal_api_key in main.py.
    INTERNAL_API_KEY: str = "dev-internal-key"

    # Shared password gating the public /api/jobs* endpoints. The frontend sends
    # it in the X-App-Password header. This is a simple single-secret gate, not
    # per-user auth. Override via env in any real deployment.
    APP_PASSWORD: str = "letmein"

    # Background task execution backend. "local" = in-process asyncio (dev/tests,
    # no durability). "procrastinate" = Postgres-backed jobs with retries, locks,
    # and persistence (default for anything that isn't a unit test).
    TASK_BACKEND: Literal["local", "procrastinate"] = "procrastinate"
    TASK_WORKER_CONCURRENCY: int = 4

    # Job scraping
    # Cron schedule for the recurring scrape-jobs task (default: every 6 hours).
    JOB_SCRAPE_CRON: str = "0 */6 * * *"

    # Azure Blob Storage
    AZURE_STORAGE_ACCOUNT_NAME: str | None = None
    AZURE_STORAGE_CONTAINER: str = "datasets"

    # Azure OpenAI (used when OPENAI_API_KEY is not set)
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str | None = None
    # Embedding deployment (Azure deployment name, or OpenAI model name when OPENAI_API_KEY is set)
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME: str | None = None

    # Reasoning effort for OpenAI reasoning models (none/minimal/low/medium/high/xhigh)
    OPENAI_REASONING_EFFORT: str | None = None

    @cached_property
    def database_url(self) -> str:
        if self.POSTGRES_HOST and self.POSTGRES_PASSWORD:
            return (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}/{self.POSTGRES_DB}?ssl=require"
            )
        return self.DATABASE_URL


settings = Settings()
