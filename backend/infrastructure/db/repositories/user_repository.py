from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.entities.user import User
from backend.core.interfaces.user_repository import UserDeletedError
from backend.infrastructure.db.models.user import User as UserModel


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, db_user: UserModel) -> User:
        return User(
            id=db_user.id,
            email=db_user.email,
            role=db_user.role,
            created_at=db_user.created_at,
            last_seen_at=db_user.last_seen_at,
            deleted_at=db_user.deleted_at,
        )

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        db_user = result.scalar_one_or_none()
        return self._to_entity(db_user) if db_user else None

    async def list_active(self) -> list[User]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.deleted_at.is_(None)).order_by(UserModel.created_at.desc())
        )
        return [self._to_entity(u) for u in result.scalars().all()]

    async def upsert_from_supabase(self, supabase_id: str, email: str, *, admin_emails: frozenset[str]) -> User:
        result = await self.session.execute(select(UserModel).where(UserModel.id == supabase_id))
        db_user = result.scalar_one_or_none()
        now = datetime.now()

        if db_user is None:
            role = "admin" if email.lower() in admin_emails else "regular"
            db_user = UserModel(id=supabase_id, email=email, role=role, created_at=now, last_seen_at=now)
            self.session.add(db_user)
        else:
            if db_user.deleted_at is not None:
                raise UserDeletedError(supabase_id)
            db_user.email = email
            db_user.last_seen_at = now

        await self.session.commit()
        await self.session.refresh(db_user)
        return self._to_entity(db_user)

    async def soft_delete(self, user_id: str) -> bool:
        result = await self.session.execute(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
            .values(deleted_at=datetime.now())
        )
        await self.session.commit()
        return result.rowcount > 0
