from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TaskOutput(BaseModel):
    """Generic structured output produced by a task."""

    id: str | None = None
    task_name: str
    toolbox: str | None = None
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None = None
