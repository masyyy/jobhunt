"""Tests for LocalFileSystem security invariants."""

from pathlib import Path

import pytest

from backend.infrastructure.filesystem.local import MAX_FILE_SIZE, LocalFileSystem


@pytest.fixture()
def fs(tmp_path: Path) -> LocalFileSystem:
    """Create a LocalFileSystem rooted in a temp directory with test files."""
    (tmp_path / "hello.md").write_text("hello world")
    (tmp_path / "big.txt").write_text("x" * (MAX_FILE_SIZE + 1))
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.csv").write_text("a,b,c")
    return LocalFileSystem(root_dir=tmp_path)


class TestReadText:
    def test_read_valid_file(self, fs: LocalFileSystem) -> None:
        assert fs.read_text("hello.md") == "hello world"

    def test_read_nested_file(self, fs: LocalFileSystem) -> None:
        assert fs.read_text("sub/nested.csv") == "a,b,c"

    def test_reject_absolute_path(self, fs: LocalFileSystem) -> None:
        with pytest.raises(ValueError, match="Absolute paths"):
            fs.read_text("/etc/passwd")

    def test_reject_traversal(self, fs: LocalFileSystem) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            fs.read_text("../etc/passwd")

    def test_reject_disallowed_extension(self, fs: LocalFileSystem) -> None:
        with pytest.raises(ValueError, match="not supported"):
            fs.read_text("photo.png")

    def test_reject_oversized_file(self, fs: LocalFileSystem) -> None:
        with pytest.raises(ValueError, match="too large"):
            fs.read_text("big.txt")

    def test_file_not_found(self, fs: LocalFileSystem) -> None:
        with pytest.raises(FileNotFoundError):
            fs.read_text("nonexistent.md")

    def test_reject_symlink_escape(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        # Create a sibling directory with a secret file
        outside = tmp_path.parent / "outside_root"
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("leaked")
        # Symlink inside root pointing outside
        link = tmp_path / "escape"
        link.symlink_to(outside)
        with pytest.raises(ValueError, match="Symbolic links"):
            fs.read_text("escape/secret.txt")
        # Cleanup
        link.unlink()
        (outside / "secret.txt").unlink()
        outside.rmdir()

    def test_reject_prefix_neighbor_dir(self, tmp_path: Path) -> None:
        """Root 'documents' must not grant access to 'documents2'."""
        root = tmp_path / "documents"
        neighbor = tmp_path / "documents2"
        root.mkdir()
        neighbor.mkdir()
        (neighbor / "secret.txt").write_text("leaked")

        fs = LocalFileSystem(root_dir=root)
        # Even if somehow crafted, resolved path in neighbor must fail
        with pytest.raises((ValueError, FileNotFoundError)):
            fs.read_text("../documents2/secret.txt")


class TestListFiles:
    def test_list_root(self, fs: LocalFileSystem) -> None:
        files = fs.list_files()
        assert "hello.md" in files
        assert "sub/nested.csv" in files

    def test_list_excludes_disallowed_extensions(self, fs: LocalFileSystem) -> None:
        files = fs.list_files()
        assert not any(f.endswith(".png") for f in files)

    def test_list_skips_symlinks(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside_list"
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("leaked")
        (tmp_path / "link").symlink_to(outside)

        files = fs.list_files()
        assert not any("secret" in f for f in files)

        (tmp_path / "link").unlink()
        (outside / "secret.txt").unlink()
        outside.rmdir()

    def test_list_nonexistent_directory(self, fs: LocalFileSystem) -> None:
        with pytest.raises(FileNotFoundError):
            fs.list_files("nonexistent")
