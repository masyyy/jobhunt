from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.db.models.base import Base


class User(Base):
    """Application user. id matches the Supabase Auth user UUID."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Email uniqueness is enforced only for active rows (see ux_users_email_active).
    # Soft-deleted tombstones keep the original email so the audit trail is intact;
    # a future invite for the same address is allowed to insert a new row.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="regular")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'regular')", name="ck_users_role"),
        Index(
            "ux_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )
