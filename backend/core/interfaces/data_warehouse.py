from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QueryResult:
    """Structured result from execute_sql_rows."""

    columns: list[str]
    rows: list[dict[str, object]]
    truncated: bool


class TableInfo:
    """Metadata about an available table or view."""

    def __init__(
        self,
        name: str,
        columns: dict[str, str],
        description: str | None = None,
    ) -> None:
        self.name = name
        self.columns = columns  # {column_name: column_type}
        self.description = description


class DataWarehouse(Protocol):
    """Abstract warehouse for SQL queries against tabular data."""

    def list_tables(self) -> list[TableInfo]:
        """Return available tables with their column schemas.

        Returns:
            List of TableInfo with table names and column name->type mappings.
        """
        ...

    def execute_sql(self, sql: str) -> str:
        """Execute a SQL query and return results as a markdown table.

        Args:
            sql: A SELECT query to execute.

        Raises:
            ValueError: Query contains disallowed statements (DDL/DML).

        Returns:
            Markdown-formatted table of results, or an error message.
        """
        ...

    def execute_sql_rows(self, sql: str, params: Sequence[object] = ()) -> QueryResult:
        """Execute a SELECT query and return structured results.

        Use ``?`` placeholders for any user-supplied values; pass them via
        ``params``. Never concatenate or format request data into the SQL
        string — the SQL itself must be hardcoded in source.

        Args:
            sql: A SELECT query to execute. May contain ``?`` placeholders.
            params: Positional values for the ``?`` placeholders, in order.

        Returns:
            QueryResult with columns, rows, and truncation flag.

        Raises:
            RuntimeError: Warehouse unavailable or query execution failed.
        """
        ...
