import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FilePromptLoader:
    """Loads and composes a system prompt from markdown files on the local filesystem.

    Prompt composition: system.md (shared) + {toolbox}.md (toolbox-specific).
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir.resolve()

    def _read_file(self, filename: str) -> str:
        path = self._dir / filename
        if not path.is_file():
            logger.debug("Prompt file not found, skipping: %s", path)
            return ""
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Failed to read prompt file, skipping: %s", path, exc_info=True)
            return ""
        return text

    def load(self, toolbox: str = "") -> str:
        """Load composed prompt: system.md + {toolbox}.md.

        Args:
            toolbox: The toolbox identifier. If empty, only system.md is loaded.
        """
        parts: list[str] = []

        system_text = self._read_file("system.md")
        if system_text:
            parts.append(system_text)

        if toolbox:
            toolbox_text = self._read_file(f"{toolbox}.md")
            if toolbox_text:
                parts.append(toolbox_text)

        return "\n\n".join(parts)

    def load_seed(self, key: str) -> str:
        """Load a seed prompt from ``seeds/{key}.md``.

        Unlike ``load``, missing files raise — once a ``PromptKey`` is
        registered the seed file must exist (``check_customer_config.py``
        validates this).
        """
        path = self._dir / "seeds" / f"{key}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Seed prompt not found: {path}")
        return path.read_text(encoding="utf-8").strip()
