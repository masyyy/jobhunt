from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from backend.core.entities.task_output import TaskOutput

TaskOutputRepoFactory = Callable[[], AbstractAsyncContextManager["TaskOutputRepositoryInterface"]]


class TaskOutputRepositoryInterface(Protocol):
    async def get_by_id(self, output_id: str) -> TaskOutput | None: ...

    async def get_all(self, *, task_name: str, toolbox: str | None = None) -> list[TaskOutput]: ...

    async def replace_all(self, outputs: list[TaskOutput], *, task_name: str, toolbox: str | None = None) -> None: ...

    async def update_payload(self, output_id: str, payload: dict[str, Any]) -> TaskOutput | None: ...
