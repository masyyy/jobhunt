import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.entities.task_output import TaskOutput
from backend.infrastructure.db.models.task_output import TaskOutput as TaskOutputModel


def _to_naive_utc(dt: datetime) -> datetime:
    """Drop tzinfo after converting to UTC, matching the naive DateTime columns."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


class TaskOutputRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_entity(self, row: TaskOutputModel) -> TaskOutput:
        return TaskOutput(
            id=row.id,
            task_name=row.task_name,
            toolbox=row.toolbox,
            payload=row.payload,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    async def get_by_id(self, output_id: str) -> TaskOutput | None:
        try:
            result = await self.session.execute(select(TaskOutputModel).where(TaskOutputModel.id == output_id))
            row = result.scalar_one_or_none()
            return self._to_entity(row) if row is not None else None
        except Exception:
            await self.session.rollback()
            raise

    async def get_all(self, *, task_name: str, toolbox: str | None = None) -> list[TaskOutput]:
        try:
            stmt = select(TaskOutputModel).where(TaskOutputModel.task_name == task_name)
            if toolbox is not None:
                stmt = stmt.where(TaskOutputModel.toolbox == toolbox)
            stmt = stmt.order_by(TaskOutputModel.created_at.desc())
            result = await self.session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            raise

    async def replace_all(self, outputs: list[TaskOutput], *, task_name: str, toolbox: str | None = None) -> None:
        try:
            stmt = delete(TaskOutputModel).where(TaskOutputModel.task_name == task_name)
            if toolbox is not None:
                stmt = stmt.where(TaskOutputModel.toolbox == toolbox)
            else:
                stmt = stmt.where(TaskOutputModel.toolbox.is_(None))
            await self.session.execute(stmt)
            for o in outputs:
                created_at = o.created_at or datetime.now(UTC)
                self.session.add(
                    TaskOutputModel(
                        id=o.id or str(uuid.uuid4()),
                        task_name=o.task_name,
                        toolbox=o.toolbox,
                        payload=o.payload,
                        created_at=_to_naive_utc(created_at),
                        expires_at=_to_naive_utc(o.expires_at) if o.expires_at else None,
                    )
                )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def update_payload(self, output_id: str, payload: dict[str, Any]) -> TaskOutput | None:
        try:
            result = await self.session.execute(select(TaskOutputModel).where(TaskOutputModel.id == output_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.payload = payload
            await self.session.commit()
            await self.session.refresh(row)
            return self._to_entity(row)
        except Exception:
            await self.session.rollback()
            raise
