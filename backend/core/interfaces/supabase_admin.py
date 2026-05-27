from typing import Protocol


class SupabaseAdminError(Exception):
    """Raised when a Supabase admin API call fails."""


class SupabaseAdminInterface(Protocol):
    async def generate_invite_link(self, email: str, *, redirect_to: str) -> str: ...

    async def generate_recovery_link(self, email: str, *, redirect_to: str) -> str: ...

    async def delete_user(self, user_id: str) -> None: ...
