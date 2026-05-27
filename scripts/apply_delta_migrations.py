"""Apply schema migrations for Delta Lake tables.

Schema for each Delta table is declared as numbered Python migration files at:

    data/migrations/raw/<table_name>/001_initial.py
    data/migrations/raw/<table_name>/002_add_column.py
    data/migrations/derived/<table_name>/001_initial.py
    ...

Two roots, mirroring the data layout:

- ``raw/<TABLE>``     → ``<datasets_uri>/<TABLE>``         (customer source tables)
- ``derived/<NAME>``  → ``<datasets_uri>/derived/<NAME>``  (computed by tasks)

Table URIs are resolved through ``DatasetStorageConfig`` so the runner targets
the same storage as the running app — local filesystem when
``AZURE_STORAGE_ACCOUNT_NAME`` is unset, Azure Blob (``az://...``) when it is.
This mirrors how ``DeltaIngestionService`` resolves URIs.

Each migration exports ``upgrade(table_uri: str) -> None``. Migrations are
storage-agnostic: the URI passed in is either a local path or an ``az://``
URI, and the ``deltalake`` library reads Azure credentials from environment
variables (``AZURE_STORAGE_ACCOUNT_NAME`` / ``AZURE_STORAGE_ACCOUNT_KEY`` /
managed identity) automatically when the URI scheme is ``az://``. The runner
tracks applied versions in the Delta table's own configuration under the key
``fulcrum.migration_version``, so state survives table moves and is visible
via ``DeltaTable.metadata().configuration``.

Idempotent: re-running with no pending migrations is a no-op. Runs as part of
deploy lifecycle (entrypoint.sh / start.sh) before the API starts.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError

from backend.config import settings
from backend.core.interfaces.storage_config import DatasetStorageConfig

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "data" / "migrations"

# Migration root → prefix prepended to the table name when resolving its URI.
# ``raw/CRM_ACCT``    → ``<datasets_uri>/CRM_ACCT``
# ``derived/scores``  → ``<datasets_uri>/derived/scores``
_KIND_PREFIXES: dict[str, str] = {
    "raw": "",
    "derived": "derived/",
}

VERSION_KEY = "fulcrum.migration_version"
_FILENAME_RE = re.compile(r"^(\d{3,})_[a-z0-9_]+\.py$")


def _green(msg: str) -> str:
    return f"\033[32m✓ {msg}\033[0m"


def _red(msg: str) -> str:
    return f"\033[31m✗ {msg}\033[0m"


def _yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m"


def _build_storage_config() -> DatasetStorageConfig:
    """Mirror ``backend.api.dependencies._get_storage_config``.

    Kept inline (not imported) so this script can run without bringing up the
    FastAPI dependency graph (DB, etc.) at deploy time.
    """
    if settings.AZURE_STORAGE_ACCOUNT_NAME:
        datasets_uri = f"az://{settings.AZURE_STORAGE_CONTAINER}"
    else:
        datasets_uri = str(settings.DATASETS_DIR)
    return DatasetStorageConfig(
        datasets_uri=datasets_uri,
        local_cache_dir=settings.DATASETS_DIR,
        azure_account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
    )


def _migration_files(table_dir: Path) -> list[tuple[str, Path]]:
    """Return [(version, path), ...] sorted ascending. Skips non-matching files."""
    items: list[tuple[str, Path]] = []
    for entry in sorted(table_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name.startswith("_"):
            continue
        m = _FILENAME_RE.match(entry.name)
        if not m:
            continue
        items.append((m.group(1), entry))
    return items


def _load_upgrade(path: Path) -> Callable[[str], None]:
    """Import the migration module and return its `upgrade` function."""
    spec = importlib.util.spec_from_file_location(f"_dmig_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    upgrade = getattr(module, "upgrade", None)
    if not callable(upgrade):
        raise RuntimeError(f"Migration {path} missing `upgrade(table_uri: str) -> None`")
    return cast(Callable[[str], None], upgrade)


def _current_version(table_uri: str) -> str | None:
    """Return the applied migration version, or None if the table doesn't exist yet."""
    try:
        dt = DeltaTable(table_uri)
    except TableNotFoundError:
        return None
    config = dict(dt.metadata().configuration or {})
    return config.get(VERSION_KEY)


def _stamp_version(table_uri: str, version: str) -> None:
    """Record the applied version on the Delta table itself."""
    dt = DeltaTable(table_uri)
    dt.alter.set_table_properties({VERSION_KEY: version}, raise_if_not_exists=False)


def _apply_table(label: str, table_uri: str, table_dir: Path) -> int:
    """Apply pending migrations for one table. Returns count applied."""
    pending_all = _migration_files(table_dir)
    if not pending_all:
        print(_yellow(f"  {label}: no migration files, skipping"))
        return 0

    applied = _current_version(table_uri)
    if applied is None:
        pending = pending_all
        print(f"  {label}: no table yet, applying from {pending[0][0]}")
    else:
        pending = [(v, p) for v, p in pending_all if v > applied]
        if not pending:
            print(_green(f"  {label}: up-to-date at {applied}"))
            return 0
        print(f"  {label}: applied={applied}, pending={[v for v, _ in pending]}")

    count = 0
    for version, path in pending:
        upgrade = _load_upgrade(path)
        upgrade(table_uri)
        _stamp_version(table_uri, version)
        print(_green(f"    applied {version} ({path.name})"))
        count += 1
    return count


def _apply_kind(
    kind: str,
    config: DatasetStorageConfig,
) -> tuple[int, list[str]]:
    """Apply all migrations under one root. Returns (count, failed_labels)."""
    kind_dir = MIGRATIONS_DIR / kind
    if not kind_dir.exists():
        return 0, []

    tables = sorted(d for d in kind_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
    if not tables:
        return 0, []

    print(f"[{kind}]")
    prefix = _KIND_PREFIXES[kind]

    count = 0
    failures: list[str] = []
    for table_dir in tables:
        label = f"{kind}/{table_dir.name}"
        table_uri = config.table_uri(f"{prefix}{table_dir.name}")
        try:
            count += _apply_table(label, table_uri, table_dir)
        except Exception as exc:
            print(_red(f"  {label}: FAILED — {exc}"))
            failures.append(label)
    return count, failures


def main() -> int:
    if not MIGRATIONS_DIR.exists():
        print(_yellow(f"No migrations directory at {MIGRATIONS_DIR} — nothing to apply"))
        return 0

    config = _build_storage_config()
    target = "Azure" if config.is_azure else "local"
    print(f"Target: {target} ({config.datasets_uri})")

    total = 0
    all_failures: list[str] = []
    saw_any = False
    for kind in _KIND_PREFIXES:
        kind_dir = MIGRATIONS_DIR / kind
        if not kind_dir.exists() or not any(kind_dir.iterdir()):
            continue
        saw_any = True
        count, failures = _apply_kind(kind, config)
        total += count
        all_failures.extend(failures)

    if not saw_any:
        print(_yellow("No migrations registered (raw or derived)"))
        return 0

    print()
    if all_failures:
        print(_red(f"Applied {total} migration(s); {len(all_failures)} table(s) failed: {all_failures}"))
        return 1
    print(_green(f"Applied {total} migration(s)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
