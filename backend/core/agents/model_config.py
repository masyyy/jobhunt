"""Centralized model resolution for PydanticAI agents.

If OPENAI_API_KEY is set, uses regular OpenAI. Otherwise, uses Azure OpenAI
with DefaultAzureCredential (token-based auth).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from backend.config import settings

if TYPE_CHECKING:
    from azure.identity.aio import DefaultAzureCredential
    from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

AZURE_OPENAI_API_VERSION = "2025-04-01-preview"

MODEL_MAIN = "gpt-5.2"
# Cheap, fast model for the per-posting job relevance filter.
MODEL_MATCHER = "gpt-5.4-mini"
# Stronger model for drafting job applications (cover letter + how-to-apply).
MODEL_APPLICATION = "gpt-5.4"

# Module-level reference for cleanup
_credential: DefaultAzureCredential | None = None


def _use_azure() -> bool:
    return not settings.OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT is not None


@lru_cache(maxsize=1)
def _get_azure_client() -> AsyncAzureOpenAI:
    global _credential  # noqa: PLW0603

    from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider  # noqa: PLC0415
    from openai import AsyncAzureOpenAI  # noqa: PLC0415

    _credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(_credential, "https://cognitiveservices.azure.com/.default")
    assert settings.AZURE_OPENAI_ENDPOINT is not None  # noqa: S101
    return AsyncAzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )


def get_model(model_name: str) -> str | Model:
    """Resolve a canonical model name to a PydanticAI model specifier.

    When OPENAI_API_KEY is set, returns an "openai-responses:<model>" string.
    Otherwise, returns an OpenAIResponsesModel backed by Azure OpenAI.
    """
    if not _use_azure():
        if settings.OPENAI_API_KEY:
            os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
        return f"openai-responses:{model_name}"

    if not settings.AZURE_OPENAI_DEPLOYMENT_NAME:
        raise RuntimeError(
            "AZURE_OPENAI_DEPLOYMENT_NAME must be set when using Azure OpenAI (OPENAI_API_KEY is not set)"
        )

    from pydantic_ai.models.openai import OpenAIResponsesModel  # noqa: PLC0415
    from pydantic_ai.providers.azure import AzureProvider  # noqa: PLC0415

    client = _get_azure_client()
    provider = AzureProvider(openai_client=client)
    return OpenAIResponsesModel(
        model_name=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
        provider=provider,
    )


def get_model_settings() -> OpenAIResponsesModelSettings:
    """Return model settings for the Responses API.

    Enables response chaining so OpenAI retains server-side reasoning state
    between turns, and sets reasoning effort from config.
    """
    valid_efforts = ("none", "minimal", "low", "medium", "high", "xhigh")
    effort = settings.OPENAI_REASONING_EFFORT or "medium"
    if effort not in valid_efforts:
        raise ValueError(f"OPENAI_REASONING_EFFORT must be one of {valid_efforts}, got '{effort}'")

    return OpenAIResponsesModelSettings(
        openai_previous_response_id="auto",
        openai_reasoning_effort=effort,  # type: ignore[typeddict-item]
    )


async def cleanup() -> None:
    """Close the Azure credential if it was created."""
    global _credential  # noqa: PLW0603
    if _credential is not None:
        await _credential.close()
        _credential = None
    _get_azure_client.cache_clear()
