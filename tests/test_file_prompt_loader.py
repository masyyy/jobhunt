"""Tests for FilePromptLoader."""

from pathlib import Path

import pytest

from backend.infrastructure.prompts.local import FilePromptLoader


@pytest.fixture()
def prompts_dir(tmp_path: Path) -> Path:
    (tmp_path / "system.md").write_text("I am an assistant.")
    (tmp_path / "sales.md").write_text("Sales toolbox instructions.")
    (tmp_path / "production.md").write_text("Production toolbox instructions.")
    return tmp_path


class TestLoad:
    def test_composes_system_and_toolbox(self, prompts_dir: Path) -> None:
        result = FilePromptLoader(prompts_dir=prompts_dir).load("sales")
        assert result == "I am an assistant.\n\nSales toolbox instructions."

    def test_different_toolbox(self, prompts_dir: Path) -> None:
        result = FilePromptLoader(prompts_dir=prompts_dir).load("production")
        assert result == "I am an assistant.\n\nProduction toolbox instructions."

    def test_no_toolbox_returns_system_only(self, prompts_dir: Path) -> None:
        result = FilePromptLoader(prompts_dir=prompts_dir).load()
        assert result == "I am an assistant."

    def test_missing_toolbox_file_returns_system_only(self, prompts_dir: Path) -> None:
        result = FilePromptLoader(prompts_dir=prompts_dir).load("nonexistent")
        assert result == "I am an assistant."

    def test_empty_directory_returns_empty_string(self, tmp_path: Path) -> None:
        result = FilePromptLoader(prompts_dir=tmp_path).load()
        assert result == ""

    def test_missing_system_returns_toolbox_only(self, prompts_dir: Path) -> None:
        (prompts_dir / "system.md").unlink()
        result = FilePromptLoader(prompts_dir=prompts_dir).load("sales")
        assert result == "Sales toolbox instructions."
