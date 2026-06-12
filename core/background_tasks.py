"""Lightweight registry for owned background threads."""

from __future__ import annotations

import logging
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTaskInfo:
    name: str
    owner: str
    started_at: float
    daemon: bool
    alive: bool


_TASKS: dict[int, tuple[weakref.ReferenceType[threading.Thread], str, str, float, bool]] = {}
_TASKS_LOCK = threading.Lock()


def start_background_thread(
    *,
    name: str,
    target: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    owner: Any = None,
    daemon: bool = True,
    before_start: Callable[[threading.Thread], Any] | None = None,
) -> threading.Thread:
    """Start a background thread and register it for diagnostics/cleanup."""

    owner_name = _owner_name(owner)

    def _run() -> None:
        try:
            target(*args, **dict(kwargs or {}))
        finally:
            unregister_background_thread(thread)

    thread = threading.Thread(target=_run, name=name, daemon=daemon)
    register_background_thread(thread, owner=owner_name)
    if before_start is not None:
        before_start(thread)
    thread.start()
    return thread


def register_background_thread(thread: threading.Thread, *, owner: str | None = None) -> None:
    if thread is None:
        return
    task_id = id(thread)
    with _TASKS_LOCK:
        _TASKS[task_id] = (
            weakref.ref(thread),
            str(owner or "unknown"),
            str(thread.name or f"Thread-{task_id}"),
            time.monotonic(),
            bool(thread.daemon),
        )


def unregister_background_thread(thread: threading.Thread) -> None:
    if thread is None:
        return
    with _TASKS_LOCK:
        _TASKS.pop(id(thread), None)


def list_background_tasks() -> list[BackgroundTaskInfo]:
    stale: list[int] = []
    result: list[BackgroundTaskInfo] = []
    with _TASKS_LOCK:
        for task_id, (thread_ref, owner, name, started_at, daemon) in list(_TASKS.items()):
            thread = thread_ref()
            if thread is None:
                stale.append(task_id)
                continue
            alive = thread.is_alive()
            if not alive:
                stale.append(task_id)
            result.append(
                BackgroundTaskInfo(
                    name=name,
                    owner=owner,
                    started_at=started_at,
                    daemon=daemon,
                    alive=alive,
                )
            )
        for task_id in stale:
            _TASKS.pop(task_id, None)
    return result


def join_background_tasks(owner: Any = None, *, timeout: float = 5.0) -> list[BackgroundTaskInfo]:
    """Join registered tasks for *owner* up to a shared timeout budget."""

    owner_name = _owner_name(owner) if owner is not None else None
    deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
    threads: list[threading.Thread] = []
    with _TASKS_LOCK:
        for thread_ref, task_owner, _name, _started_at, _daemon in _TASKS.values():
            if owner_name is not None and task_owner != owner_name:
                continue
            thread = thread_ref()
            if thread is not None:
                threads.append(thread)
    current = threading.current_thread()
    for thread in threads:
        if thread is current:
            continue
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        thread.join(timeout=remaining)
    remaining_tasks = [task for task in list_background_tasks() if owner_name is None or task.owner == owner_name]
    if remaining_tasks:
        logger.warning(
            "Background tasks still running for %s: %s",
            owner_name or "all owners",
            ", ".join(task.name for task in remaining_tasks if task.alive),
        )
    return remaining_tasks


def _owner_name(owner: Any) -> str:
    if owner is None:
        return "global"
    if isinstance(owner, str):
        return owner
    return f"{owner.__class__.__module__}.{owner.__class__.__qualname__}"
