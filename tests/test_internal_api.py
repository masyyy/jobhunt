"""Tests for the internal task-trigger API: auth, routing, and payload validation."""

import httpx
import pytest
from fastapi import FastAPI

from backend.api.dependencies import get_task_queue, verify_internal_api_key
from backend.api.routers.internal import router
from backend.config import settings
from backend.infrastructure.tasks.local import LocalTaskQueue


def _build_app(task_queue: LocalTaskQueue | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the internal router."""
    app = FastAPI()
    app.include_router(router, prefix="/internal")

    if task_queue is not None:
        app.dependency_overrides[get_task_queue] = lambda: task_queue

    return app


def _make_noop_queue() -> LocalTaskQueue:
    async def noop(**kwargs: object) -> None:
        pass

    return LocalTaskQueue(tasks={"generate-signals": noop})


class TestAuth:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_401(self) -> None:
        app = _build_app(_make_noop_queue())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/internal/tasks/generate-signals")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_api_key_returns_401(self) -> None:
        app = _build_app(_make_noop_queue())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/tasks/generate-signals",
                headers={"X-API-Key": "wrong-key"},
            )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_passes(self) -> None:
        app = _build_app(_make_noop_queue())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/tasks/generate-signals",
                headers={"X-API-Key": settings.INTERNAL_API_KEY},
            )

        assert resp.status_code == 200


class TestTaskRouting:
    @pytest.mark.asyncio
    async def test_valid_task_returns_task_id(self) -> None:
        app = _build_app(_make_noop_queue())
        # Skip auth for routing tests
        app.dependency_overrides[verify_internal_api_key] = lambda: None

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/internal/tasks/generate-signals")

        assert resp.status_code == 200
        body = resp.json()
        assert "task_id" in body
        assert body["status"] == "started"

    @pytest.mark.asyncio
    async def test_unknown_task_returns_404(self) -> None:
        app = _build_app(_make_noop_queue())
        app.dependency_overrides[verify_internal_api_key] = lambda: None

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/internal/tasks/nonexistent-task")

        assert resp.status_code == 404
        assert "Unknown task" in resp.json()["detail"]


class TestPayloadValidation:
    @pytest.fixture()
    def app(self) -> FastAPI:
        app = _build_app(_make_noop_queue())
        app.dependency_overrides[verify_internal_api_key] = lambda: None
        return app

    @pytest.mark.asyncio
    async def test_valid_prompt_accepted(self, app: FastAPI) -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/tasks/generate-signals",
                json={"prompt": "test prompt"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_extra_fields_rejected(self, app: FastAPI) -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/tasks/generate-signals",
                json={"repo_factory": "injected"},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_malformed_json_returns_422(self, app: FastAPI) -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/internal/tasks/generate-signals",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 422
