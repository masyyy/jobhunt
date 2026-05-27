"""Supabase Auth integration: JWKS-based JWT verification, require_auth, and /me."""

import asyncio
from functools import lru_cache
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException

from backend.api.dependencies import get_user_repository
from backend.api.models.auth import AuthenticatedUser
from backend.config import settings
from backend.core.interfaces.user_repository import UserDeletedError, UserRepositoryInterface

auth_router = APIRouter()


@lru_cache(maxsize=1)
def _get_jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        settings.supabase_jwks_url,
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=600,
    )


def _verify_supabase_jwt_sync(token: str) -> dict[str, Any]:
    """Blocking JWT verification. Don't call from an async route directly —
    use verify_supabase_jwt() which off-threads it."""
    client = _get_jwks_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientError as e:
        raise HTTPException(status_code=401, detail="Invalid token signing key") from e

    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=settings.supabase_jwt_issuer,
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


async def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify a Supabase RS256/ES256 JWT against the project's JWKS.

    PyJWKClient may make a blocking HTTPS round-trip on cache miss / key
    rotation, so the actual verification runs in a worker thread.
    """
    return await asyncio.to_thread(_verify_supabase_jwt_sync, token)


async def require_auth(
    authorization: str | None = Header(default=None),
    users: UserRepositoryInterface = Depends(get_user_repository),
) -> AuthenticatedUser:
    """Validate Bearer JWT, upsert the local user row, return identity."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing authorization")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.removeprefix("Bearer ")
    payload = await verify_supabase_jwt(token)

    supabase_id = payload.get("sub")
    email = payload.get("email", "")
    if not supabase_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    try:
        user = await users.upsert_from_supabase(supabase_id, email, admin_emails=settings.initial_admin_email_set)
    except UserDeletedError as e:
        raise HTTPException(status_code=401, detail="User account has been deleted") from e

    return AuthenticatedUser(id=user.id, email=user.email, role=user.role)


async def require_admin(user: AuthenticatedUser = Depends(require_auth)) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@auth_router.get("/me")
async def get_me(user: AuthenticatedUser = Depends(require_auth)) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "role": user.role}
