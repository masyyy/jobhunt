"""OpenAI / Azure OpenAI implementation of the EmbeddingProvider protocol.

Routes through the same Azure / OpenAI selection as ``model_config.py``:
when ``OPENAI_API_KEY`` is set, uses regular OpenAI; otherwise reuses the
DefaultAzureCredential-backed ``AsyncAzureOpenAI`` from
``backend.core.agents.model_config._get_azure_client``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from backend.config import settings
from backend.core.agents.model_config import _get_azure_client, _use_azure  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from openai import AsyncAzureOpenAI, AsyncOpenAI

logger = logging.getLogger(__name__)

# Azure embedding deployments often start at low TPM limits; keep batches
# modest and pause between calls so we don't burn through the per-minute
# bucket on the first few requests.
_BATCH_SIZE = 5
_INTER_BATCH_SLEEP_S = 1.5
_MAX_RETRIES = 6


class OpenAIEmbeddingProvider:
    """``EmbeddingProvider`` backed by OpenAI / Azure OpenAI embeddings."""

    async def embed_texts(self, texts: list[str], *, dimensions: int) -> list[list[float]]:
        if not texts:
            return []

        client = await _get_embeddings_client()
        deployment = _resolve_deployment()

        from openai import APIStatusError, RateLimitError  # noqa: PLC0415

        results: list[list[float]] = []
        total_batches = (len(texts) + _BATCH_SIZE - 1) // _BATCH_SIZE
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            batch_idx = start // _BATCH_SIZE + 1

            response = None
            for attempt in range(_MAX_RETRIES):
                try:
                    response = await client.embeddings.create(
                        model=deployment,
                        input=batch,
                        dimensions=dimensions,
                    )
                    break
                except (RateLimitError, APIStatusError) as exc:
                    status = getattr(exc, "status_code", None) or getattr(
                        getattr(exc, "response", None), "status_code", None
                    )
                    if status != 429 or attempt == _MAX_RETRIES - 1:
                        raise
                    retry_after_header = None
                    resp = getattr(exc, "response", None)
                    if resp is not None:
                        retry_after_header = resp.headers.get("retry-after") if hasattr(resp, "headers") else None
                    try:
                        wait_s = float(retry_after_header) if retry_after_header else 2**attempt + random.random()  # noqa: S311
                    except ValueError:
                        wait_s = 2**attempt + random.random()  # noqa: S311
                    logger.warning(
                        "embed_texts: batch %d/%d hit 429 (attempt %d/%d), sleeping %.1fs",
                        batch_idx,
                        total_batches,
                        attempt + 1,
                        _MAX_RETRIES,
                        wait_s,
                    )
                    await asyncio.sleep(wait_s)

            assert response is not None  # noqa: S101
            results.extend([item.embedding for item in response.data])
            logger.info(
                "embed_texts: batch %d/%d (%d inputs, %d dims)",
                batch_idx,
                total_batches,
                len(batch),
                dimensions,
            )
            if batch_idx < total_batches:
                await asyncio.sleep(_INTER_BATCH_SLEEP_S)

        return results


async def _get_embeddings_client() -> AsyncAzureOpenAI | AsyncOpenAI:
    if _use_azure():
        return _get_azure_client()
    from openai import AsyncOpenAI  # noqa: PLC0415

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("Neither OPENAI_API_KEY nor AZURE_OPENAI_ENDPOINT is set; cannot embed.")
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _resolve_deployment() -> str:
    name = settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME
    if not name:
        raise RuntimeError(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME is required for embedding tasks. "
            "Set it to the Azure deployment name (or the OpenAI model name when using OPENAI_API_KEY)."
        )
    return name
