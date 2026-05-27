"""ProcrastinateTaskQueue: adapter from the TaskQueue protocol to procrastinate.App."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from procrastinate import App
from procrastinate.jobs import Status

from backend.core.entities.task_status import TaskStatus, TaskStatusValue

_STATUS_MAP: dict[Status, TaskStatusValue] = {
    Status.TODO: "queued",
    Status.DOING: "doing",
    Status.SUCCEEDED: "succeeded",
    Status.FAILED: "failed",
    Status.CANCELLED: "cancelled",
    Status.ABORTING: "doing",
    Status.ABORTED: "cancelled",
}

_TERMINAL_EVENT_TYPES = ("succeeded", "failed", "cancelled")

_EVENTS_QUERY = """
    SELECT type, at
    FROM procrastinate_events
    WHERE job_id = %(job_id)s
    ORDER BY at ASC
"""


class ProcrastinateTaskQueue:
    def __init__(self, app: App) -> None:
        self._app = app

    async def enqueue(
        self,
        task_name: str,
        *,
        lock: str | None = None,
        queueing_lock: str | None = None,
        schedule_in: timedelta | None = None,
        **kwargs: Any,
    ) -> str:
        configure_kwargs: dict[str, Any] = {"allow_unknown": False}
        if lock is not None:
            configure_kwargs["lock"] = lock
        if queueing_lock is not None:
            configure_kwargs["queueing_lock"] = queueing_lock
        if schedule_in is not None:
            configure_kwargs["schedule_in"] = {"seconds": int(schedule_in.total_seconds())}

        deferrer = self._app.configure_task(task_name, **configure_kwargs)
        job_id = await deferrer.defer_async(**kwargs)
        return str(job_id)

    async def get_status(self, task_id: str) -> TaskStatus | None:
        try:
            job_id_int = int(task_id)
        except ValueError:
            return None

        jobs = list(await self._app.job_manager.list_jobs_async(id=job_id_int))
        if not jobs:
            return None

        job = jobs[0]
        raw = job.status
        raw_status = Status(raw) if isinstance(raw, str) else raw
        mapped: TaskStatusValue = _STATUS_MAP.get(raw_status, "queued") if raw_status is not None else "queued"

        started_at, finished_at = await self._event_timestamps(job_id_int)

        return TaskStatus(
            task_id=str(job.id),
            task_name=job.task_name,
            status=mapped,
            attempts=job.attempts,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def _event_timestamps(self, job_id: int) -> tuple[datetime | None, datetime | None]:
        """Return (first started_at, first terminal finished_at) for a job.

        Procrastinate records transition events in procrastinate_events. Job itself
        carries only the current status, not timing, so we query the log directly.
        Retries produce multiple 'started' rows; we take the earliest so the status
        reflects when the job first began running.
        """
        rows = await self._app.connector.execute_query_all_async(_EVENTS_QUERY, job_id=job_id)
        started_at: datetime | None = None
        finished_at: datetime | None = None
        for row in rows:
            event_type = row["type"]
            at = row["at"]
            if event_type == "started" and started_at is None:
                started_at = at
            elif event_type in _TERMINAL_EVENT_TYPES and finished_at is None:
                finished_at = at
        return started_at, finished_at
