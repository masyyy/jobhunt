from typing import Protocol

from backend.core.entities.user import User


class UserDeletedError(Exception):
    """Raised by upsert_from_supabase when the local user row is soft-deleted."""


class UserRepositoryInterface(Protocol):
    async def get_by_id(self, user_id: str) -> User | None: ...

    async def list_active(self) -> list[User]: ...

    async def upsert_from_supabase(self, supabase_id: str, email: str, *, admin_emails: frozenset[str]) -> User:
        """Find or create the local row matching this Supabase identity.

        On first sight: assigns role='admin' if email is in admin_emails,
        else 'regular'. On every call: refreshes email + last_seen_at.
        Returns the upserted user. Raises if the row exists but is soft-deleted.
        """
        ...

    async def soft_delete(self, user_id: str) -> bool:
        """Mark the user row as deleted_at=now. Returns True if a row was updated."""
        ...
