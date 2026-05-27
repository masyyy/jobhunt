from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class FileInfo:
    path: str
    mtime: datetime


class FileSystem(Protocol):
    """Abstract filesystem for tool access to documents."""

    def read_text(self, path: str) -> str:
        """Read a file and return its text content.

        Args:
            path: Relative path to the file within the storage root.

        Raises:
            FileNotFoundError: File does not exist.
            ValueError: Path is invalid (traversal, unsupported type, etc.).
            OSError: Read failure.
        """
        ...

    def read_bytes(self, path: str) -> bytes:
        """Read a file and return its raw bytes.

        Used for binary content (e.g. PDFs) that are passed through to the
        model rather than decoded in-process.

        Raises:
            FileNotFoundError: File does not exist.
            ValueError: Path is invalid or the file type / size is not allowed.
        """
        ...

    def list_files(self, directory: str = "") -> list[str]:
        """List file paths relative to the storage root.

        Args:
            directory: Optional subdirectory to scope the listing.

        Raises:
            FileNotFoundError: Directory does not exist.
            ValueError: Path is invalid.
        """
        ...

    def stat_files(self, directory: str = "") -> list[FileInfo]:
        """Like ``list_files`` but each entry includes the file's mtime."""
        ...
