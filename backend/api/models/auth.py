from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity resolved from a verified Supabase JWT, joined with the local users row."""

    id: str
    email: str
    role: str
