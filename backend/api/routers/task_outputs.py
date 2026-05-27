"""Public task outputs endpoints."""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.dependencies import get_task_output_repository
from backend.core.entities.task_output import TaskOutput
from backend.core.interfaces.task_output_repository import TaskOutputRepositoryInterface

router = APIRouter()


class TaskOutputResponse(BaseModel):
    id: str
    task_name: str
    toolbox: str | None
    payload: dict[str, Any]
    created_at: datetime


SignalState = Literal["active", "dismissed", "acted_on", "expired"]


class UpdateStateRequest(BaseModel):
    """Only `state` is user-mutable. Reads the existing payload server-side and
    only overwrites `state`, so a caller cannot smuggle arbitrary keys (e.g. a
    signal's `prompt`, which is fed back into the chat agent on click)."""

    model_config = {"extra": "forbid"}

    state: SignalState


def _as_utc(dt: datetime) -> datetime:
    """Tag naive datetimes as UTC so Pydantic serializes them with a Z suffix.

    The task_outputs.created_at column is stored naive but represents UTC
    (normalized on write). Without this, browsers parse the ISO string as
    local time and relative-time calculations drift by the TZ offset.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_response(o: TaskOutput) -> TaskOutputResponse:
    return TaskOutputResponse(
        id=o.id or "",
        task_name=o.task_name,
        toolbox=o.toolbox,
        payload=o.payload,
        created_at=_as_utc(o.created_at),
    )


@router.get("/task-outputs")
async def get_task_outputs(
    task_name: str,
    toolbox: str | None = None,
    repo: TaskOutputRepositoryInterface = Depends(get_task_output_repository),
) -> list[TaskOutputResponse]:
    """Get all task outputs for a given task_name, optionally filtered by toolbox."""
    outputs = await repo.get_all(task_name=task_name, toolbox=toolbox)
    return [_to_response(o) for o in outputs]


@router.patch("/task-outputs/{output_id}")
async def update_task_output_state(
    output_id: str,
    body: UpdateStateRequest,
    repo: TaskOutputRepositoryInterface = Depends(get_task_output_repository),
) -> TaskOutputResponse:
    """Toggle the `state` field on a task output (active/dismissed/acted_on/expired).

    Reads the existing payload server-side and only overwrites `state`, so a
    caller cannot smuggle arbitrary keys.
    """
    existing = await repo.get_by_id(output_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Task output {output_id} not found")
    new_payload = {**existing.payload, "state": body.state}
    output = await repo.update_payload(output_id, new_payload)
    if output is None:
        raise HTTPException(status_code=404, detail=f"Task output {output_id} not found")
    return _to_response(output)
