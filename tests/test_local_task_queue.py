"""Tests for LocalTaskQueue dispatch and error handling."""

import asyncio
from typing import Any

import pytest

from backend.infrastructure.tasks.local import LocalTaskQueue, TaskCallable


@pytest.fixture()
def completed_event() -> asyncio.Event:
    return asyncio.Event()


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_runs_task(self, completed_event: asyncio.Event) -> None:
        async def my_task() -> None:
            completed_event.set()

        queue = LocalTaskQueue(tasks={"my-task": my_task})
        task_id = await queue.enqueue("my-task")

        assert isinstance(task_id, str)
        assert len(task_id) > 0

        await asyncio.sleep(0.05)
        assert completed_event.is_set()

    @pytest.mark.asyncio
    async def test_enqueue_passes_kwargs(self) -> None:
        received: dict[str, Any] = {}

        async def my_task(foo: str, bar: int) -> None:
            received["foo"] = foo
            received["bar"] = bar

        queue = LocalTaskQueue(tasks={"my-task": my_task})
        await queue.enqueue("my-task", foo="hello", bar=42)

        await asyncio.sleep(0.05)
        assert received == {"foo": "hello", "bar": 42}

    @pytest.mark.asyncio
    async def test_enqueue_unknown_task_raises(self) -> None:
        tasks: dict[str, TaskCallable] = {}
        queue = LocalTaskQueue(tasks=tasks)

        with pytest.raises(ValueError, match="Unknown task"):
            await queue.enqueue("nonexistent")

    @pytest.mark.asyncio
    async def test_enqueue_returns_unique_ids(self) -> None:
        async def noop() -> None:
            pass

        queue = LocalTaskQueue(tasks={"noop": noop})
        id1 = await queue.enqueue("noop")
        id2 = await queue.enqueue("noop")

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_failed_task_does_not_raise(self) -> None:
        async def failing_task() -> None:
            raise RuntimeError("boom")

        queue = LocalTaskQueue(tasks={"fail": failing_task})
        task_id = await queue.enqueue("fail")

        assert isinstance(task_id, str)
        # Give it time to fail — should not propagate to caller
        await asyncio.sleep(0.05)
