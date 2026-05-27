"""Public task outputs endpoints."""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.auth import require_admin, require_auth
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
    """Only `state` is user-mutable. Task outputs are global (no per-user
    ownership), so accepting an arbitrary payload would let any authenticated
    user rewrite a signal's `prompt` — which is fed back into the chat agent
    on click — for every other user."""

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


@router.get("/task-outputs", dependencies=[Depends(require_auth)])
async def get_task_outputs(
    task_name: str,
    toolbox: str | None = None,
    repo: TaskOutputRepositoryInterface = Depends(get_task_output_repository),
) -> list[TaskOutputResponse]:
    """Get all task outputs for a given task_name, optionally filtered by toolbox."""
    outputs = await repo.get_all(task_name=task_name, toolbox=toolbox)
    return [_to_response(o) for o in outputs]


@router.patch("/task-outputs/{output_id}", dependencies=[Depends(require_admin)])
async def update_task_output_state(
    output_id: str,
    body: UpdateStateRequest,
    repo: TaskOutputRepositoryInterface = Depends(get_task_output_repository),
) -> TaskOutputResponse:
    """Toggle the `state` field on a task output (active/dismissed/acted_on/expired).

    Admin-only — task outputs are global (no per-user ownership), so any write
    here mutates the dashboard for every user. Reads the existing payload
    server-side and only overwrites `state`, so even an admin caller cannot
    smuggle arbitrary keys.
    """
    existing = await repo.get_by_id(output_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Task output {output_id} not found")
    new_payload = {**existing.payload, "state": body.state}
    output = await repo.update_payload(output_id, new_payload)
    if output is None:
        raise HTTPException(status_code=404, detail=f"Task output {output_id} not found")
    return _to_response(output)
