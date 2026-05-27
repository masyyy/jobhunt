from datetime import timedelta
from typing import Any, Protocol

from backend.core.entities.task_status import TaskStatus


class TaskQueue(Protocol):
    async def enqueue(
        self,
        task_name: str,
        *,
        lock: str | None = None,
        queueing_lock: str | None = None,
        schedule_in: timedelta | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit a named task for execution. Returns task ID.

        lock: serialize execution of jobs sharing this key.
        queueing_lock: reject enqueue if another job with this key is already queued.
        schedule_in: delay before the job becomes eligible.
        """
        ...

    async def get_status(self, task_id: str) -> TaskStatus | None:
        """Return the current status of a task, or None if unknown."""
        ...
