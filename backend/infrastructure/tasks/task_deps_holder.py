"""Process-wide holder for TaskDeps consumed by Procrastinate task shims.

Procrastinate tasks are module-level functions registered at import time, so
they cannot accept dependencies via constructor injection. The DI layer
(api/dependencies.py) builds TaskDeps once at lifespan startup and stashes it
here; the shims in `tasks.py` read it back.

This keeps the dependency flow one-directional: api -> infrastructure, never
the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.customer.tasks import TaskDeps


@dataclass
class _Holder:
    deps: TaskDeps | None = None


_holder = _Holder()


def set_task_deps(deps: TaskDeps) -> None:
    _holder.deps = deps


def get_task_deps() -> TaskDeps:
    if _holder.deps is None:
        raise RuntimeError("TaskDeps not initialized. Call set_task_deps() during app startup (see main.py lifespan).")
    return _holder.deps
