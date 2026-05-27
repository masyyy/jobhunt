"""Admin-only endpoints: invite users, list users, delete/reinvite users."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from backend.api.auth import require_admin
from backend.api.dependencies import get_supabase_admin, get_user_repository
from backend.api.models.auth import AuthenticatedUser
from backend.config import settings
from backend.core.interfaces.supabase_admin import SupabaseAdminError, SupabaseAdminInterface
from backend.core.interfaces.user_repository import UserRepositoryInterface

logger = logging.getLogger(__name__)

router = APIRouter()


class InviteRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: EmailStr


class InviteResponse(BaseModel):
    email: str
    action_link: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime
    last_seen_at: datetime


def _accept_invite_redirect() -> str:
    return f"{settings.SITE_URL}/accept-invite"


@router.post("/invite")
async def create_invite(
    body: InviteRequest,
    supabase: SupabaseAdminInterface = Depends(get_supabase_admin),
) -> InviteResponse:
    """Generate a Supabase invite link for the given email.

    The link is returned to the admin to share manually (no SMTP wired).
    The invitee's role is assigned at first login by the user repository,
    based on INITIAL_ADMIN_EMAILS — there is no role selection at invite
    time. To promote a user to admin after the fact, update the users
    table directly.
    """
    email = str(body.email)
    # TODO(auth): PoC compromise while email delivery is not wired. Returning
    # Supabase action links to admins lets the admin open the link and establish
    # a session as the target user. Before adding customer admins or handling
    # sensitive production data, send these links directly to the invitee instead.
    try:
        action_link = await supabase.generate_invite_link(email, redirect_to=_accept_invite_redirect())
    except SupabaseAdminError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return InviteResponse(email=email, action_link=action_link)


@router.post("/users/{user_id}/reinvite")
async def reinvite_user(
    user_id: str,
    users: UserRepositoryInterface = Depends(get_user_repository),
    supabase: SupabaseAdminInterface = Depends(get_supabase_admin),
) -> InviteResponse:
    """Generate a fresh password-reset link for an existing user.

    Use this when the original invite expired or the user forgot their password.
    Uses Supabase's `recovery` link type (the `invite` type rejects already-
    registered emails). The link grants a session and routes through the same
    `/accept-invite` page where they set a new password.
    """
    user = await users.get_by_id(user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")

    # TODO(auth): PoC compromise while email delivery is not wired. Returning a
    # recovery link to an admin is equivalent to giving that admin account
    # takeover capability for this user. Replace with direct email delivery
    # before adding customer admins or moving beyond the operator-managed PoC.
    try:
        action_link = await supabase.generate_recovery_link(user.email, redirect_to=_accept_invite_redirect())
    except SupabaseAdminError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return InviteResponse(email=user.email, action_link=action_link)


@router.get("/users")
async def list_users(
    users: UserRepositoryInterface = Depends(get_user_repository),
) -> list[UserResponse]:
    """List all active application users."""
    rows = await users.list_active()
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            role=u.role,
            created_at=u.created_at,
            last_seen_at=u.last_seen_at,
        )
        for u in rows
    ]


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    users: UserRepositoryInterface = Depends(get_user_repository),
    supabase: SupabaseAdminInterface = Depends(get_supabase_admin),
    current: AuthenticatedUser = Depends(require_admin),
) -> None:
    """Soft-delete a user locally, then delete from Supabase Auth.

    Order matters for security: the local tombstone is set and committed
    *first*. require_auth rejects any token whose subject has a non-null
    deleted_at, so once the tombstone lands the user is locked out
    regardless of token expiry. Supabase deletion is a follow-up cleanup;
    if it fails we surface 502 so the admin knows the Supabase row is
    orphaned and needs manual cleanup, but the user is already locked out.
    """
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = await users.get_by_id(user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")

    if not await users.soft_delete(user_id):
        # Lost a race with another admin deleting the same row — treat as 404.
        raise HTTPException(status_code=404, detail="User not found")

    try:
        await supabase.delete_user(user_id)
    except SupabaseAdminError as e:
        logger.error(
            "Local tombstone set for user %s but Supabase deletion failed; "
            "manual cleanup required in Supabase Auth dashboard",
            user_id,
        )
        raise HTTPException(
            status_code=502,
            detail="User locked out locally but Supabase deletion failed; manual cleanup required",
        ) from e
