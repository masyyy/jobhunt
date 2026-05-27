from typing import Protocol


class EmbeddingProvider(Protocol):
    """Generates dense vector embeddings for a batch of texts."""

    async def embed_texts(self, texts: list[str], *, dimensions: int) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input, in order."""
        ...
