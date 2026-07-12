"""Deterministic startup/shutdown ownership for process resources."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LifecycleState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ResourceHandle:
    name: str
    stop: Callable[[], object]


class LifecycleManager:
    """Own resources and release them once in reverse registration order."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = LifecycleState.CREATED
        self._resources: list[ResourceHandle] = []

    @property
    def state(self) -> LifecycleState:
        with self._lock:
            return self._state

    def register(self, name: str, stop: Callable[[], object]) -> ResourceHandle:
        handle = ResourceHandle(name=name, stop=stop)
        with self._lock:
            if self._state in {LifecycleState.STOPPING, LifecycleState.STOPPED}:
                raise RuntimeError("cannot register a resource during shutdown")
            self._resources.append(handle)
        return handle

    def start(self) -> None:
        with self._lock:
            if self._state == LifecycleState.CREATED:
                self._state = LifecycleState.RUNNING
            elif self._state != LifecycleState.RUNNING:
                raise RuntimeError(f"cannot start lifecycle from {self._state.value}")

    def shutdown(self) -> list[str]:
        with self._lock:
            if self._state in {LifecycleState.STOPPING, LifecycleState.STOPPED}:
                return []
            self._state = LifecycleState.STOPPING
            resources = list(reversed(self._resources))
            self._resources.clear()
        failures: list[str] = []
        for resource in resources:
            try:
                resource.stop()
            except Exception:
                failures.append(resource.name)
                logger.exception("resource shutdown failed: %s", resource.name)
        with self._lock:
            self._state = LifecycleState.STOPPED
        return failures
