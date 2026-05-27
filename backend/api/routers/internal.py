"""Internal endpoints for triggering background tasks."""

from fastapi import APIRouter, Depends, HTTPException, Request
from procrastinate.exceptions import AlreadyEnqueued
from pydantic import BaseModel, ValidationError

from backend.api.dependencies import get_task_queue, verify_internal_api_key
from backend.core.entities.task_status import TaskStatus
from backend.core.interfaces.task_queue import TaskQueue
from backend.infrastructure.tasks import worker_health
from backend.infrastructure.tasks.procrastinate_queue import ProcrastinateTaskQueue

router = APIRouter(dependencies=[Depends(verify_internal_api_key)])


class _StrictBase(BaseModel):
    model_config = {"extra": "forbid"}


class GenerateSignalsRequest(_StrictBase):
    prompt: str | None = None
    toolbox: str | None = None


class IngestFileRequest(_StrictBase):
    file_path: str
    table: str | None = None


class IndexDocumentsRequest(_StrictBase):
    root: str | None = None


_TASK_SCHEMAS: dict[str, type[BaseModel]] = {
    "generate-signals": GenerateSignalsRequest,
    "ingest-file": IngestFileRequest,
    "index-documents": IndexDocumentsRequest,
}


def _enqueue_kwargs(task_name: str, payload: BaseModel) -> dict[str, object]:
    """Return backend-specific enqueue kwargs (locks, etc.) for a given task."""
    if task_name == "ingest-file" and isinstance(payload, IngestFileRequest):
        key = f"ingest-file:{payload.table or payload.file_path}"
        return {"lock": key, "queueing_lock": key}
    if task_name == "index-documents" and isinstance(payload, IndexDocumentsRequest):
        key = f"index-documents:{payload.root or '*'}"
        return {"lock": key, "queueing_lock": key}
    return {}


@router.post("/tasks/{task_name}")
async def run_task(
    task_name: str,
    request: Request,
    task_queue: TaskQueue = Depends(get_task_queue),
) -> dict[str, str]:
    """Fire a named background task and return a task ID."""
    if isinstance(task_queue, ProcrastinateTaskQueue) and not worker_health.is_healthy():
        raise HTTPException(
            status_code=503,
            detail=f"task worker unavailable: {worker_health.current_reason()}",
        )

    schema = _TASK_SCHEMAS.get(task_name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_name}")

    body = await request.body()
    try:
        payload = schema.model_validate_json(body) if body else schema()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_input=False)) from e

    enqueue_kwargs = _enqueue_kwargs(task_name, payload)

    try:
        task_id = await task_queue.enqueue(
            task_name,
            **enqueue_kwargs,
            **payload.model_dump(exclude_none=True),
        )
    except AlreadyEnqueued as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"task_id": task_id, "status": "started"}


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    task_queue: TaskQueue = Depends(get_task_queue),
) -> TaskStatus:
    """Return current status of a task. 404 if unknown or backend has no record."""
    status = await task_queue.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No status for task: {task_id}")
    return status
