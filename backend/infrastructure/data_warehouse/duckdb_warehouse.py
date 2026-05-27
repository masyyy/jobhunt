"""DuckDB-backed data warehouse reading Delta Lake tables via delta_scan().

Security model
--------------
A temporary DuckDB file is built with ``delta_scan()`` views, then
re-opened in **read-only mode** for all query execution.  This gives
two layers of protection:

1. **DuckDB engine enforcement** — the query connection is opened with
   ``read_only=True``, so the engine rejects *any* DDL/DML statement
   (DROP, CREATE, INSERT, ALTER …) including multi-statement payloads
   like ``SELECT 1; DROP VIEW _raw_orders``.

2. **Application-layer gate** — ``is_read_only()`` in the tool layer
   checks that SQL starts with SELECT/WITH before it ever reaches DuckDB,
   giving the LLM a clean error message.

During the *build* phase (writable temp file), both local and Azure
modes apply the same lockdown:

* ``allowed_directories`` — whitelists only the datasets path
  (local absolute path or ``az://<container>/``)
* ``enable_external_access=False`` — blocks all paths not in the
  whitelist (local files, network, other Azure containers)
* ``lock_configuration=True`` — prevents extension loading and config
  changes

On ``refresh()``, a brand-new temp file is built and the read-only
connection is swapped under a write lock so in-flight queries complete
against the old snapshot.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path

import duckdb

from backend.core.interfaces.data_warehouse import QueryResult, TableInfo
from backend.core.interfaces.storage_config import DatasetStorageConfig

logger = logging.getLogger(__name__)

_MAX_ROWS = 200
_RAW_PREFIX = "_raw_"
_DESCRIPTION_RE = re.compile(r"^--\s*description:\s*(.+)", re.IGNORECASE)
# Captures the view name from CREATE OR REPLACE VIEW, handling:
#   plain:            CREATE OR REPLACE VIEW order_totals AS ...
#   quoted:           CREATE OR REPLACE VIEW "order-totals" AS ...
#   schema-qualified: CREATE OR REPLACE VIEW main.order_totals AS ...
#   schema + quoted:  CREATE OR REPLACE VIEW main."order-totals" AS ...
# Group 1 = quoted name, Group 2 = unquoted name (use first non-None).
_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+VIEW\s+"
    r"(?:\w+\.)?"  # optional schema prefix (ignored)
    r'(?:"([^"]+)"|(\w+))',  # quoted name | unquoted name
    re.IGNORECASE,
)


def parse_view_file(path: Path) -> tuple[str, str | None, str | None]:
    """Read a .sql view file and extract the SQL, description, and view name.

    The description starts on the first non-whitespace line, which must begin
    with ``-- description:``.  Any immediately following ``-- `` comment lines
    are appended as continuation lines (whitespace-joined) so multi-line
    descriptions are injected into the agent prompt in full.  The block ends
    at the first non-comment line.

    Returns (sql, description, view_name).  *view_name* is parsed from the
    ``CREATE OR REPLACE VIEW <name>`` statement; ``None`` when the statement
    is missing or unparseable.
    """
    text = path.read_text(encoding="utf-8")
    description: str | None = None
    lines = text.lstrip().split("\n")
    if lines:
        m = _DESCRIPTION_RE.match(lines[0])
        if m:
            parts: list[str] = [m.group(1).strip()]
            for line in lines[1:]:
                stripped = line.lstrip()
                if not stripped.startswith("--"):
                    break
                # Strip the leading "--" and any whitespace, then keep the rest
                cont = stripped[2:].strip()
                if cont:
                    parts.append(cont)
            description = " ".join(parts)

    view_name: str | None = None
    vm = _CREATE_VIEW_RE.search(text)
    if vm:
        view_name = vm.group(1) or vm.group(2)

    return text, description, view_name


def _set_extension_directory(conn: duckdb.DuckDBPyConnection) -> None:
    """Point DuckDB at the pre-cached extension directory when available."""
    ext_dir = os.environ.get("DUCKDB_EXTENSIONS_PATH")
    if ext_dir:
        conn.execute(f"SET extension_directory='{ext_dir}'")


def ensure_delta_extension(*, install_azure: bool = False) -> None:
    """Install the DuckDB delta extension if not already present.

    Call once at application startup (e.g. FastAPI lifespan).  This may
    download the extension on first run, so it should not be in the
    request path.  When ``DUCKDB_EXTENSIONS_PATH`` is set (Docker image),
    extensions are already cached and ``install_extension`` is a no-op.
    """
    conn = duckdb.connect(":memory:")
    try:
        _set_extension_directory(conn)
        conn.install_extension("delta")
        if install_azure:
            conn.install_extension("azure")
    finally:
        conn.close()
    logger.info("DuckDB extensions installed/verified (azure=%s)", install_azure)


def _discover_delta_tables_local(datasets_dir: Path) -> list[tuple[str, str]]:
    """Return (table_name, delta_scan_uri) pairs from a local directory."""
    if not datasets_dir.exists():
        return []
    return [
        (entry.name, str(entry.resolve()))
        for entry in datasets_dir.iterdir()
        if entry.is_dir() and (entry / "_delta_log").is_dir()
    ]


def _discover_delta_tables_azure(config: DatasetStorageConfig) -> list[tuple[str, str]]:
    """Return (table_name, delta_scan_uri) pairs from Azure Blob Storage."""
    from adlfs import AzureBlobFileSystem  # noqa: PLC0415

    if config.azure_account_name is None:
        return []
    fs = AzureBlobFileSystem(account_name=config.azure_account_name)
    container = config.datasets_uri.removeprefix("az://")
    tables: list[tuple[str, str]] = []
    try:
        entries = fs.ls(container, detail=False)
    except Exception:
        logger.warning("Failed to list Azure container %s", container, exc_info=True)
        return tables
    for entry_path in entries:
        # entry_path is "container/table_name"
        table_name = entry_path.rsplit("/", 1)[-1]
        delta_log_path = f"{entry_path}/_delta_log"
        try:
            if fs.isdir(delta_log_path):
                tables.append((table_name, f"az://{entry_path}"))
        except Exception:
            logger.debug("Skipping %s: could not check for _delta_log", entry_path)
            continue
    return tables


def _setup_azure_secret(conn: duckdb.DuckDBPyConnection, account_name: str) -> None:
    """Load the DuckDB Azure extension and register a credential-chain secret."""
    _set_extension_directory(conn)
    conn.install_extension("azure")
    conn.load_extension("azure")
    conn.execute(
        "CREATE SECRET IF NOT EXISTS __azure_datasets ("
        "  TYPE azure,"
        "  PROVIDER credential_chain,"
        f"  ACCOUNT_NAME '{account_name}'"
        ")"
    )


def _remove_db_file(path: str) -> None:
    """Best-effort removal of a temporary DuckDB file and its WAL."""
    for suffix in ("", ".wal"):
        with suppress(OSError):
            Path(path + suffix).unlink()


class _RWLock:
    """Simple readers-writer lock.

    Multiple readers can hold the lock concurrently.  A writer gets
    exclusive access — it waits for in-flight readers to finish and
    blocks new readers until the write is done.
    """

    def __init__(self) -> None:
        self._readers = 0
        self._readers_lock = threading.Lock()
        self._write_lock = threading.Lock()

    @contextmanager
    def read(self) -> Iterator[None]:
        with self._readers_lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()
        try:
            yield
        finally:
            with self._readers_lock:
                self._readers -= 1
                if self._readers == 0:
                    self._write_lock.release()

    @contextmanager
    def write(self) -> Iterator[None]:
        self._write_lock.acquire()
        try:
            yield
        finally:
            self._write_lock.release()


class DuckDBWarehouse:
    """Reads Delta Lake tables from local or Azure storage via DuckDB."""

    def __init__(self, storage_config: DatasetStorageConfig) -> None:
        self._config = storage_config
        self._registered_tables: set[str] = set()
        self._registered_views: set[str] = set()
        self._view_descriptions: dict[str, str] = {}
        self._query_conn: duckdb.DuckDBPyConnection | None = None
        self._db_path: str | None = None
        self._refreshed = False
        self._rwlock = _RWLock()

    def _discover_tables(self) -> list[tuple[str, str]] | None:
        """Discover Delta tables; returns None when local dir doesn't exist."""
        config = self._config
        if config.is_azure:
            return _discover_delta_tables_azure(config)
        local_dir = Path(config.datasets_uri)
        if not local_dir.exists():
            return None
        return _discover_delta_tables_local(local_dir)

    def _build_db(
        self,
        delta_tables: list[tuple[str, str]],
    ) -> tuple[str, duckdb.DuckDBPyConnection, set[str], set[str], dict[str, str]]:
        """Build a temp DuckDB file with views and return a read-only connection.

        Returns (db_path, ro_conn, raw_table_names, view_names, view_descriptions).
        """
        config = self._config

        # mkstemp creates an empty file — remove it so DuckDB can create a fresh DB.
        fd, db_path = tempfile.mkstemp(suffix=".duckdb")
        os.close(fd)
        Path(db_path).unlink()
        conn = duckdb.connect(db_path)
        try:
            _set_extension_directory(conn)
            conn.load_extension("delta")

            if config.is_azure and config.azure_account_name:
                _setup_azure_secret(conn, config.azure_account_name)

            # Create _raw_ views pointing to delta_scan() URIs
            current_tables: set[str] = set()
            for table_name, scan_uri in delta_tables:
                raw_name = f"{_RAW_PREFIX}{table_name}"
                current_tables.add(raw_name)
                conn.execute(
                    f'CREATE VIEW "{raw_name}" AS '  # noqa: S608
                    f"SELECT * FROM delta_scan('{scan_uri}')"
                )

            # Load SQL view definitions (always from local cache dir)
            current_views, view_descriptions = self._load_sql_views(conn)

        finally:
            conn.close()

        # Re-open the temp file as read-only — DuckDB engine rejects all DDL/DML
        ro_conn = duckdb.connect(db_path, read_only=True)

        # Load extensions BEFORE lockdown — delta_scan() views need the delta
        # extension at query time, and enable_external_access=false blocks
        # extension loading.
        _set_extension_directory(ro_conn)
        ro_conn.load_extension("delta")
        if config.is_azure and config.azure_account_name:
            ro_conn.load_extension("azure")

        # Lock down the query connection: SET values are connection-scoped so
        # they must be applied here, not on the build connection.
        # allowed_directories must be set BEFORE enable_external_access=false.
        if config.is_azure:
            azure_root = config.datasets_uri.rstrip("/") + "/"
            ro_conn.execute(f"SET allowed_directories=['{azure_root}']")
        else:
            datasets_path = str(Path(config.datasets_uri).resolve())
            ro_conn.execute(f"SET allowed_directories=['{datasets_path}']")
        ro_conn.execute("SET enable_external_access=false")
        ro_conn.execute("SET lock_configuration=true")

        return db_path, ro_conn, current_tables, current_views, view_descriptions

    def _load_sql_views(self, conn: duckdb.DuckDBPyConnection) -> tuple[set[str], dict[str, str]]:
        """Load SQL view definitions from disk into the connection.

        Views may depend on each other (e.g. a derived view that filters on a
        scope-gate view). Resolve the load order by retrying pending views
        after each successful pass until the set stops shrinking. Any view
        still failing at the fixed point is a real compile error and is
        raised.
        """
        views_dir = self._config.local_cache_dir / "views"
        current_views: set[str] = set()
        view_descriptions: dict[str, str] = {}

        if not views_dir.is_dir():
            return current_views, view_descriptions

        pending: list[tuple[Path, str, str | None, str]] = []
        for sql_file in sorted(views_dir.glob("*.sql")):
            sql, description, view_name = parse_view_file(sql_file)
            if view_name is None:
                logger.warning(
                    "Skipping %s: must contain CREATE OR REPLACE VIEW",
                    sql_file.name,
                )
                continue
            pending.append((sql_file, sql, description, view_name))

        last_error: Exception | None = None
        last_failed: str | None = None
        while pending:
            still_pending: list[tuple[Path, str, str | None, str]] = []
            made_progress = False
            for entry in pending:
                sql_file, sql, description, view_name = entry
                try:
                    conn.execute(sql)
                except Exception as exc:
                    last_error = exc
                    last_failed = sql_file.name
                    still_pending.append(entry)
                    continue
                current_views.add(view_name)
                if description:
                    view_descriptions[view_name] = description
                made_progress = True
            if not made_progress:
                raise RuntimeError(f"Failed to create view from {last_failed}: {last_error}") from last_error
            pending = still_pending

        return current_views, view_descriptions

    def _refresh_tables(self) -> None:
        """Build a temp DB with delta_scan() views, re-open read-only, and swap it in."""
        delta_tables = self._discover_tables()

        if delta_tables is None:
            old_conn = self._query_conn
            old_path = self._db_path
            self._query_conn = None
            self._db_path = None
            self._registered_tables = set()
            self._registered_views = set()
            self._view_descriptions = {}
            if old_conn is not None:
                old_conn.close()
            if old_path is not None:
                _remove_db_file(old_path)
            return

        db_path, ro_conn, current_tables, current_views, view_descriptions = self._build_db(delta_tables)

        # Swap in the new connection
        old_conn = self._query_conn
        old_path = self._db_path
        self._query_conn = ro_conn
        self._db_path = db_path
        self._registered_tables = current_tables
        self._registered_views = current_views
        self._view_descriptions = view_descriptions
        if old_conn is not None:
            old_conn.close()
        if old_path is not None:
            _remove_db_file(old_path)

    def _ensure_refreshed(self) -> None:
        """Refresh tables exactly once (double-checked under write lock)."""
        if self._refreshed:
            return
        with self._rwlock.write():
            if not self._refreshed:
                self._refresh_tables()
                self._refreshed = True

    def refresh(self) -> None:
        """Rebuild the connection to pick up new Delta data.

        Call after ingestion writes new data.  Takes a write lock so
        in-flight queries finish before the connection is swapped.
        """
        with self._rwlock.write():
            self._refresh_tables()
            self._refreshed = True

    def list_tables(self) -> list[TableInfo]:
        """Return available views (or raw tables if no views exist) with column schemas."""
        self._ensure_refreshed()

        with self._rwlock.read():
            if self._query_conn is None:
                return []

            # If views exist, expose only views; otherwise fall back to raw tables
            if self._registered_views:
                exposed = sorted(self._registered_views)
            elif self._registered_tables:
                exposed = sorted(self._registered_tables)
            else:
                return []

            cursor = self._query_conn.cursor()
            try:
                tables: list[TableInfo] = []
                for name in exposed:
                    try:
                        result = cursor.execute(
                            "SELECT column_name, data_type FROM information_schema.columns "
                            "WHERE table_name = ? ORDER BY ordinal_position",
                            [name],
                        ).fetchall()
                        columns = {row[0]: row[1] for row in result}
                        description = self._view_descriptions.get(name)
                        tables.append(TableInfo(name=name, columns=columns, description=description))
                    except duckdb.Error:
                        logger.warning("Failed to read schema for %s", name)

                return tables
            finally:
                cursor.close()

    def execute_sql(self, sql: str) -> str:
        """Execute a SELECT query and return results as a markdown table.

        The query runs on a read-only connection where DDL/DML is rejected
        by the DuckDB engine.  Concurrent calls are safe — each gets its
        own cursor under a read lock that prevents refresh from swapping
        the connection.
        """
        self._ensure_refreshed()

        with self._rwlock.read():
            if self._query_conn is None:
                return "Error: No data tables available."

            error_labels: dict[type, str] = {
                duckdb.CatalogException: "Table not found",
                duckdb.ParserException: "Invalid SQL syntax",
                duckdb.PermissionException: "Operation not permitted",
            }

            cursor = self._query_conn.cursor()
            try:
                result = cursor.execute(sql)
                columns = [desc[0] for desc in result.description]
                all_rows = result.fetchmany(_MAX_ROWS + 1)
            except duckdb.Error as e:
                label = error_labels.get(type(e), "Query failed")
                if label == "Query failed":
                    logger.warning("DuckDB query failed: %s", e)
                return f"Error: {label}. {e}"
            finally:
                cursor.close()

        if not all_rows:
            return "Query returned no results."

        truncated = len(all_rows) > _MAX_ROWS
        display_rows = all_rows[:_MAX_ROWS]

        # Format as markdown table
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in display_rows]

        lines = [header, separator, *rows]
        if truncated:
            lines.append(f"\n*Results truncated to {_MAX_ROWS} rows.*")

        return "\n".join(lines)

    def execute_sql_rows(self, sql: str, params: Sequence[object] = ()) -> QueryResult:
        """Execute a SELECT query and return structured results.

        Use ``?`` placeholders for any user-supplied values and pass them
        via ``params``. The SQL string itself must be hardcoded in source —
        never concatenate or format request data into it.
        """
        self._ensure_refreshed()

        with self._rwlock.read():
            if self._query_conn is None:
                raise RuntimeError("No data tables available.")

            error_labels: dict[type, str] = {
                duckdb.CatalogException: "Table not found",
                duckdb.ParserException: "Invalid SQL syntax",
                duckdb.PermissionException: "Operation not permitted",
            }

            cursor = self._query_conn.cursor()
            try:
                result = cursor.execute(sql, list(params)) if params else cursor.execute(sql)
                columns = [desc[0] for desc in result.description]
                all_rows = result.fetchmany(_MAX_ROWS + 1)
            except duckdb.Error as e:
                label = error_labels.get(type(e), "Query failed")
                if label == "Query failed":
                    logger.warning("DuckDB execute_sql_rows failed: %s", e)
                raise RuntimeError(f"{label}. {e}") from e
            finally:
                cursor.close()

        truncated = len(all_rows) > _MAX_ROWS
        display_rows = all_rows[:_MAX_ROWS]
        return QueryResult(
            columns=columns,
            rows=[dict(zip(columns, row, strict=True)) for row in display_rows],
            truncated=truncated,
        )
