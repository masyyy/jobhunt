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

    # Supabase Auth
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ISSUER: str = ""
    INITIAL_ADMIN_EMAILS: str = ""
    SITE_URL: str = "http://localhost:5173"

    # Background task execution backend. "local" = in-process asyncio (dev/tests,
    # no durability). "procrastinate" = Postgres-backed jobs with retries, locks,
    # and persistence (default for anything that isn't a unit test).
    TASK_BACKEND: Literal["local", "procrastinate"] = "procrastinate"
    TASK_WORKER_CONCURRENCY: int = 4

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

    @cached_property
    def supabase_jwks_url(self) -> str:
        if self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @cached_property
    def supabase_jwt_issuer(self) -> str:
        if self.SUPABASE_JWT_ISSUER:
            return self.SUPABASE_JWT_ISSUER
        return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"

    @cached_property
    def initial_admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.INITIAL_ADMIN_EMAILS.split(",") if e.strip())


settings = Settings()
