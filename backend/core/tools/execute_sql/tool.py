from pydantic_ai import RunContext

from backend.core.agents.deps import AgentDeps

_ALLOWED_PREFIXES = ("SELECT", "WITH")


def is_read_only(sql: str) -> bool:
    """Check that a SQL statement starts with a read-only keyword."""
    upper = sql.upper()
    return any(upper.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def execute_sql(ctx: RunContext[AgentDeps], sql: str) -> str:
    """Execute a DuckDB SQL query against the available data tables.

    Write SELECT queries based on the table schemas in your system prompt.
    Use DuckDB syntax: ILIKE for case-insensitive matching, :: for casts.
    Results are limited to 200 rows unless you specify a different LIMIT.

    Args:
        sql: A SELECT query to run against the data warehouse.
    """
    stripped = sql.strip()
    if not is_read_only(stripped):
        return "Error: Only SELECT queries are allowed."

    return ctx.deps.db.execute_sql(stripped)
