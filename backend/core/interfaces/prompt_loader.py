from typing import Protocol


class PromptLoader(Protocol):
    """Abstract loader that returns a composed system prompt string."""

    def load(self, toolbox: str = "") -> str:
        """Load and return the full system prompt for the given toolbox.

        Args:
            toolbox: The toolbox identifier (e.g. "sales", "production").
                     Used to load toolbox-specific prompt content.

        Returns:
            The composed prompt string. May be empty if no sources are available.
        """
        ...

    def load_seed(self, key: str) -> str:
        """Load a seed prompt by key, used as the first user message of a workshop.

        Args:
            key: The ``PromptKey`` value (e.g. "weekly_review").

        Returns:
            The seed prompt content. Raises ``FileNotFoundError`` if the key
            is registered but the underlying source is missing — seed prompts
            are not optional once a key is declared.
        """
        ...
