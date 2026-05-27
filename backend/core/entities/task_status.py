from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TaskStatusValue = Literal["queued", "doing", "succeeded", "failed", "cancelled"]


class TaskStatus(BaseModel):
    """Observable status of a background task.

    `started_at` is populated from the first 'started' event; `finished_at`
    from the first 'succeeded'/'failed'/'cancelled' event. Procrastinate does
    not persist exception messages beyond its log stream, so there is no
    `error` field here — consult worker logs for failure causes.
    """

    task_id: str
    task_name: str
    status: TaskStatusValue
    attempts: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
