"""Procrastinate App singleton shared by the FastAPI process and the in-process worker.

A single module-level `app` instance is required because Procrastinate tasks are
registered via `@app.task(...)` decorators at import time. Both the producer
(FastAPI routers) and consumer (worker) must see the same registered tasks.
"""

from __future__ import annotations

from procrastinate import App, PsycopgConnector

from backend.config import settings


def _psycopg_dsn() -> str:
    """Convert the app's asyncpg SQLAlchemy URL into a libpq/psycopg DSN."""
    url = settings.database_url
    url = url.removeprefix("postgresql+asyncpg://").removeprefix("postgresql://")
    return f"postgresql://{url}"


_connector = PsycopgConnector(conninfo=_psycopg_dsn())

app = App(
    connector=_connector,
    import_paths=["backend.infrastructure.tasks.tasks"],
)
