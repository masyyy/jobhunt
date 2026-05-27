from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.infrastructure.tasks import worker_health

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    if settings.TASK_BACKEND == "procrastinate" and not worker_health.is_healthy():
        raise HTTPException(
            status_code=503,
            detail=f"task worker unavailable: {worker_health.current_reason()}",
        )
    return {"status": "ok"}
