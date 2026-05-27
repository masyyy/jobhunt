"""Supabase Auth admin client.

Wraps the blocking `supabase` SDK with `asyncio.to_thread` and maps SDK
exceptions to a single typed error so the API layer never depends on the
SDK's exception hierarchy.
"""

import asyncio
import logging

from supabase import create_client
from supabase_auth.types import (
    GenerateInviteOrMagiclinkParams,
    GenerateLinkParamsOptions,
    GenerateLinkParamsWithDataOptions,
    GenerateRecoveryLinkParams,
)

from backend.core.interfaces.supabase_admin import SupabaseAdminError

logger = logging.getLogger(__name__)


class SupabaseAdminClient:
    def __init__(self, url: str, service_role_key: str):
        self._client = create_client(url, service_role_key)

    async def generate_invite_link(self, email: str, *, redirect_to: str) -> str:
        params = GenerateInviteOrMagiclinkParams(
            type="invite",
            email=email,
            options=GenerateLinkParamsWithDataOptions(redirect_to=redirect_to),
        )
        return await asyncio.to_thread(self._generate_link_blocking, params, email)

    async def generate_recovery_link(self, email: str, *, redirect_to: str) -> str:
        params = GenerateRecoveryLinkParams(
            type="recovery",
            email=email,
            options=GenerateLinkParamsOptions(redirect_to=redirect_to),
        )
        return await asyncio.to_thread(self._generate_link_blocking, params, email)

    async def delete_user(self, user_id: str) -> None:
        await asyncio.to_thread(self._delete_user_blocking, user_id)

    def _generate_link_blocking(
        self,
        params: GenerateInviteOrMagiclinkParams | GenerateRecoveryLinkParams,
        email: str,
    ) -> str:
        try:
            result = self._client.auth.admin.generate_link(params)
        except Exception as e:
            logger.exception("Supabase generate_link failed for %s", email)
            raise SupabaseAdminError(f"Failed to generate link: {e}") from e

        action_link = getattr(result.properties, "action_link", None) if result.properties else None
        if not action_link:
            raise SupabaseAdminError("Action link missing in Supabase response")
        return action_link

    def _delete_user_blocking(self, user_id: str) -> None:
        try:
            self._client.auth.admin.delete_user(user_id)
        except Exception as e:
            logger.exception("Supabase delete_user failed for %s", user_id)
            raise SupabaseAdminError(f"Failed to delete user: {e}") from e
