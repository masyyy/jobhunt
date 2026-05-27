import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routers.chat import router as chat_router
from backend.api.routers.data import router as data_router
from backend.api.routers.documents import router as documents_router
from backend.api.routers.health import router as health_router
from backend.api.routers.internal import router as internal_router
from backend.api.routers.jobs import router as jobs_router
from backend.api.routers.task_outputs import router as task_outputs_router
from backend.config import settings
from backend.infrastructure.data_warehouse.duckdb_warehouse import ensure_delta_extension
from backend.infrastructure.db.models.job import (
    Job as _JobModel,  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers model with Base.metadata
)
from backend.infrastructure.db.models.task_output import (
    TaskOutput as _TaskOutputModel,  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers model with Base.metadata
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("backend").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


_INFLIGHT_DRAIN_TIMEOUT_SECONDS = 30.0


async def _drain_inflight_runs(inflight_runs: dict[str, asyncio.Task[None]]) -> None:
    inflight = list(inflight_runs.values())
    if not inflight:
        return
    logger.info("Draining %d inflight agent run(s) on shutdown", len(inflight))
    try:
        async with asyncio.timeout(_INFLIGHT_DRAIN_TIMEOUT_SECONDS):
            await asyncio.gather(*inflight, return_exceptions=True)
        logger.info("All inflight agent runs completed")
    except TimeoutError:
        logger.warning("Timed out draining inflight agent runs; some messages may not have persisted")


_INSECURE_INTERNAL_API_KEYS: frozenset[str] = frozenset({"", "dev-internal-key"})


def _validate_internal_api_key() -> None:
    """Refuse to start in non-DEBUG mode with the dev default INTERNAL_API_KEY.

    /internal/tasks/* enqueues ingestion + signal-generation jobs that run with
    the worker's full DB and storage privileges. A forgotten override in prod
    would leave that surface open to anyone reachable on the network.
    """
    if settings.DEBUG:
        return
    if settings.INTERNAL_API_KEY in _INSECURE_INTERNAL_API_KEYS:
        raise RuntimeError(
            "INTERNAL_API_KEY is unset or uses the dev default. "
            "Set a strong, unique value in the environment before starting in non-DEBUG mode."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize extensions on startup."""
    _validate_internal_api_key()
    ensure_delta_extension(install_azure=settings.AZURE_STORAGE_ACCOUNT_NAME is not None)
    if settings.OPENAI_API_KEY:
        logger.info("Using OpenAI directly")
    elif settings.AZURE_OPENAI_ENDPOINT:
        logger.info(
            "Using Azure OpenAI (endpoint=%s, deployment=%s)",
            settings.AZURE_OPENAI_ENDPOINT,
            settings.AZURE_OPENAI_DEPLOYMENT_NAME,
        )
    else:
        logger.warning("No LLM provider configured: set OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT")

    worker_task: asyncio.Task[None] | None = None
    procrastinate_app_instance = None
    if settings.TASK_BACKEND == "procrastinate":
        import backend.infrastructure.tasks.tasks  # noqa: F401, PLC0415  # pyright: ignore[reportUnusedImport]  # register @app.task shims
        from backend.api.dependencies import build_task_deps  # noqa: PLC0415
        from backend.infrastructure.tasks import task_deps_holder, worker_health  # noqa: PLC0415
        from backend.infrastructure.tasks.procrastinate_app import app as procrastinate_app_instance  # noqa: PLC0415

        task_deps_holder.set_task_deps(build_task_deps())

        await procrastinate_app_instance.open_async()
        worker_task = asyncio.create_task(
            procrastinate_app_instance.run_worker_async(
                concurrency=settings.TASK_WORKER_CONCURRENCY,
                wait=True,
                install_signal_handlers=False,
            )
        )

        def _on_worker_exit(task: asyncio.Task[None]) -> None:
            if task.cancelled():
                worker_health.mark_unhealthy("worker cancelled")
                return
            exc = task.exception()
            if exc is not None:
                logger.exception("Procrastinate worker crashed", exc_info=exc)
                worker_health.mark_unhealthy(f"worker crashed: {exc!r}")
            else:
                worker_health.mark_unhealthy("worker exited unexpectedly")

        worker_task.add_done_callback(_on_worker_exit)
        worker_health.mark_healthy()
        logger.info("Procrastinate worker started (concurrency=%d)", settings.TASK_WORKER_CONCURRENCY)

    inflight_runs: dict[str, asyncio.Task[None]] = {}
    _app.state.inflight_runs = inflight_runs

    try:
        yield
    finally:
        await _drain_inflight_runs(_app.state.inflight_runs)

        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker_task
        if procrastinate_app_instance is not None:
            await procrastinate_app_instance.close_async()

        from backend.core.agents.model_config import cleanup  # noqa: PLC0415

        await cleanup()


app = FastAPI(title="React-Python Template", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(task_outputs_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(internal_router, prefix="/internal")

# Serve static files from frontend build
frontend_build_path = Path("frontend/dist")
if frontend_build_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_build_path / "assets")), name="static")

    @app.get("/{full_path:path}", response_model=None)
    async def serve_frontend(full_path: str) -> FileResponse | None:
        if full_path.startswith("api/") or full_path.startswith("internal/"):
            # Let API/internal routes handle their calls
            return None

        file_path = frontend_build_path / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Serve index.html for all other routes (SPA routing)
        return FileResponse(frontend_build_path / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
