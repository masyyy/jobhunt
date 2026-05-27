"""Configuration for dataset storage (local filesystem or Azure Blob)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetStorageConfig:
    """Where Delta Lake tables live and how to access them.

    When ``azure_account_name`` is set the app reads/writes Delta tables
    from Azure Blob Storage.  Otherwise it uses the local filesystem.
    """

    datasets_uri: str
    """Root URI for Delta tables — ``az://<container>`` or a local absolute path."""

    local_cache_dir: Path
    """Always-local directory for SQL view definitions."""

    azure_account_name: str | None = None

    @property
    def is_azure(self) -> bool:
        return self.azure_account_name is not None

    @property
    def deltalake_storage_options(self) -> dict[str, str] | None:
        """Return ``storage_options`` for the ``deltalake`` Python library.

        Returns ``None`` in local mode (no extra options needed).
        """
        if not self.is_azure or self.azure_account_name is None:
            return None
        return {
            "account_name": self.azure_account_name,
            "anon": "false",
        }

    def table_uri(self, table_name: str) -> str:
        """Full URI for a Delta table (local path or ``az://`` URI)."""
        if self.is_azure:
            return f"{self.datasets_uri}/{table_name}"
        return str((Path(self.datasets_uri) / table_name).resolve())
