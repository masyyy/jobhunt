"""Liveness flag for the in-process Procrastinate worker.

The worker runs as an asyncio task. If it dies (DB outage, bug), FastAPI would
otherwise keep accepting enqueues that nobody processes. This module exposes a
small thread-safe flag that the lifespan hook flips: healthy when the worker
task has been launched, unhealthy the moment it completes (cleanly or not).

The done-callback may execute on the event loop's shutdown path where state
visibility across threads matters, so a threading.Lock guards reads/writes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _State:
    healthy: bool = False
    reason: str = "worker not started"


_lock = threading.Lock()
_state = _State()


def mark_healthy() -> None:
    with _lock:
        _state.healthy = True
        _state.reason = ""


def mark_unhealthy(reason: str) -> None:
    with _lock:
        _state.healthy = False
        _state.reason = reason


def is_healthy() -> bool:
    with _lock:
        return _state.healthy


def current_reason() -> str:
    with _lock:
        return _state.reason
