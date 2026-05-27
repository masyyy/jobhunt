"""Install Procrastinate schema.

Revision ID: 004
Revises: 003
Create Date: 2026-04-17

Delegates to procrastinate's own schema manager so the DDL stays pinned to
whatever ships with the installed version (see pyproject.toml). No vendored SQL:
on upgrade we call `SchemaManager.get_schema()` and run it through the raw
asyncpg connection (SQLAlchemy's prepared-statement path cannot handle the
multi-statement PL/pgSQL script).

Alembic's version table guarantees this runs exactly once per database, so the
shipped schema's lack of `IF NOT EXISTS` guards is not a concern. When upgrading
procrastinate itself, add a new Alembic revision that applies the relevant
incremental files from `SchemaManager.get_migrations_path()`.
"""

from collections.abc import Sequence
from typing import Any

from procrastinate.schema import SchemaManager

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _run_raw(sql: str) -> None:
    """Execute a multi-statement SQL script via the raw asyncpg connection.

    Bypasses SQLAlchemy's prepared-statement path, which asyncpg rejects for
    scripts containing multiple commands.
    """
    bind = op.get_bind()
    dbapi_conn: Any = bind.connection.connection
    raw_conn: Any = dbapi_conn.driver_connection

    async def _exec() -> None:
        await raw_conn.execute(sql)

    dbapi_conn.await_(_exec())


def upgrade() -> None:
    _run_raw(SchemaManager.get_schema())


def downgrade() -> None:
    _run_raw(
        """
        DROP TABLE IF EXISTS procrastinate_events CASCADE;
        DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE;
        DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
        DROP TABLE IF EXISTS procrastinate_workers CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_to_defer_v1 CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_status CASCADE;

        DO $$
        DECLARE
            f_name text;
        BEGIN
            FOR f_name IN
                SELECT p.oid::regprocedure::text
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE p.proname LIKE 'procrastinate_%'
                  AND n.nspname = current_schema()
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || f_name || ' CASCADE';
            END LOOP;
        END
        $$;
        """
    )
