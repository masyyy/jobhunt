from datetime import UTC, datetime
from pathlib import Path

from backend.core.interfaces.filesystem import FileInfo

ALLOWED_TEXT_EXTENSIONS: set[str] = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".sh",
    ".sql",
    ".rst",
    ".tex",
}

ALLOWED_BINARY_EXTENSIONS: set[str] = {".pdf"}

ALLOWED_EXTENSIONS: set[str] = ALLOWED_TEXT_EXTENSIONS | ALLOWED_BINARY_EXTENSIONS

MAX_FILE_SIZE: int = 25_000_000  # 25 MB (PDFs are bigger than text)


class LocalFileSystem:
    """Local filesystem backed by a root directory with security constraints."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir.resolve()

    def _resolve_and_validate(self, path: str) -> Path:
        """Resolve a relative path and validate it stays within root.

        Security checks:
        - Reject absolute paths and '..' components
        - Check each unresolved path component for symlinks before resolving
        - Use is_relative_to() for containment (not string prefix matching)
        """
        if path.startswith("/") or path.startswith("\\"):
            raise ValueError("Absolute paths are not allowed. Use a relative path.")

        parts = Path(path).parts
        if ".." in parts:
            raise ValueError("Path traversal ('..') is not allowed.")

        current = self._root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic links are not allowed.")

        target = (self._root / path).resolve()

        if not target.is_relative_to(self._root):
            raise ValueError("Path resolves outside the allowed root directory.")

        return target

    def _validate_readable(self, path: str, *, allowed: set[str]) -> Path:
        target = self._resolve_and_validate(path)

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        if target.suffix.lower() not in allowed:
            raise ValueError(
                f"File type '{target.suffix}' is not supported here. Supported: {', '.join(sorted(allowed))}"
            )

        file_size = target.stat().st_size
        if file_size > MAX_FILE_SIZE:
            raise ValueError(f"File is too large ({file_size:,} bytes). Maximum allowed: {MAX_FILE_SIZE:,} bytes.")

        return target

    def read_text(self, path: str) -> str:
        target = self._validate_readable(path, allowed=ALLOWED_TEXT_EXTENSIONS)
        return target.read_text(encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        target = self._validate_readable(path, allowed=ALLOWED_EXTENSIONS)
        return target.read_bytes()

    def list_files(self, directory: str = "") -> list[str]:
        return [info.path for info in self.stat_files(directory)]

    def stat_files(self, directory: str = "") -> list[FileInfo]:
        target = self._resolve_and_validate(directory) if directory else self._root

        if not target.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        files: list[FileInfo] = []
        for child in sorted(target.rglob("*")):
            if child.is_symlink():
                continue
            resolved = child.resolve()
            if (
                resolved.is_file()
                and resolved.is_relative_to(self._root)
                and resolved.suffix.lower() in ALLOWED_EXTENSIONS
            ):
                stat = resolved.stat()
                files.append(
                    FileInfo(
                        path=str(resolved.relative_to(self._root)),
                        mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    )
                )

        return files
