from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    """Application user entity. id matches the Supabase Auth user UUID."""

    id: str
    email: str
    role: str  # 'admin' | 'regular'
    created_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None = None
