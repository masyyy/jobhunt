"""Local task queue using asyncio.create_task() for in-process execution."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any
from uuid import uuid4

from backend.core.entities.task_status import TaskStatus

logger = logging.getLogger(__name__)

TaskCallable = Callable[..., Coroutine[Any, Any, None]]


class LocalTaskQueue:
    def __init__(self, tasks: dict[str, TaskCallable]) -> None:
        self._tasks = tasks
        self._running: set[asyncio.Task[None]] = set()

    async def enqueue(
        self,
        task_name: str,
        *,
        lock: str | None = None,  # noqa: ARG002
        queueing_lock: str | None = None,  # noqa: ARG002
        schedule_in: timedelta | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> str:
        """Fire a named task via asyncio.create_task(). Returns task ID.

        lock/queueing_lock/schedule_in are accepted for protocol compatibility
        but ignored in local mode — this backend is ephemeral and does not
        persist job state between requests.
        """
        task_fn = self._tasks.get(task_name)
        if task_fn is None:
            raise ValueError(f"Unknown task: {task_name}")

        task_id = str(uuid4())

        async_task = asyncio.create_task(task_fn(**kwargs))
        self._running.add(async_task)

        def _done(t: asyncio.Task[None]) -> None:
            self._running.discard(t)
            if not t.cancelled() and t.exception():
                logger.exception(
                    "Background task '%s' (id=%s) failed",
                    task_name,
                    task_id,
                    exc_info=t.exception(),
                )

        async_task.add_done_callback(_done)

        logger.info("Started task '%s' with id=%s", task_name, task_id)
        return task_id

    async def get_status(self, task_id: str) -> TaskStatus | None:  # noqa: ARG002
        """Local mode has no persistent status store — always returns None."""
        return None
