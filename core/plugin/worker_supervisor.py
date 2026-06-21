"""Lifecycle owner for persistent out-of-process plugin workers."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from core.plugin_worker_runtime import PersistentPluginWorker, PluginWorkerBackpressure

logger = logging.getLogger(__name__)


class PluginWorkerSupervisor:
    """Lifecycle owner for persistent out-of-process plugin workers.

    The supervisor owns the worker pool, health checks, backpressure, and a
    simple circuit breaker that prevents infinite restart loops after
    repeated crashes.
    """

    MAX_CONSECUTIVE_FAILURES = 5
    QUARANTINE_SECONDS = 300

    def __init__(self, plugin_id: str, *, max_workers: int = 8) -> None:
        self.plugin_id = str(plugin_id)
        self.max_workers = max(1, int(max_workers))
        self._workers: dict[str, PersistentPluginWorker] = {}
        self._lock = threading.RLock()
        self._closed = False
        self._consecutive_failures: dict[str, int] = {}
        self._quarantined_until: dict[str, float] = {}

    def get_or_create(self, key: str, factory: Callable[[], PersistentPluginWorker]) -> PersistentPluginWorker:
        normalized = str(key or "").replace("\\", "/").lower()
        with self._lock:
            if self._closed:
                raise RuntimeError(f"plugin worker supervisor is closed: {self.plugin_id}")
            # Circuit breaker: reject creation if quarantined.
            quarantined_until = self._quarantined_until.get(normalized)
            if quarantined_until is not None:
                if time.monotonic() < quarantined_until:
                    raise PluginWorkerBackpressure(
                        f"plugin worker {normalized} is quarantined until "
                        f"{quarantined_until:.0f} (consecutive failures="
                        f"{self._consecutive_failures.get(normalized, 0)})"
                    )
                self._quarantined_until.pop(normalized, None)
                self._consecutive_failures.pop(normalized, None)
            existing = self._workers.get(normalized)
            if existing is not None:
                return existing
            if len(self._workers) >= self.max_workers:
                raise PluginWorkerBackpressure(f"plugin worker capacity reached: {self.plugin_id} ({self.max_workers})")
            worker = factory()
            self._workers[normalized] = worker
            return worker

    def report_failure(self, key: str) -> None:
        """Record a worker failure and quarantine if threshold exceeded."""
        normalized = str(key or "").replace("\\", "/").lower()
        with self._lock:
            count = self._consecutive_failures.get(normalized, 0) + 1
            self._consecutive_failures[normalized] = count
            if count >= self.MAX_CONSECUTIVE_FAILURES:
                self._quarantined_until[normalized] = time.monotonic() + self.QUARANTINE_SECONDS
                logger.warning(
                    "plugin worker %s/%s quarantined: %d consecutive failures",
                    self.plugin_id,
                    normalized,
                    count,
                )
                worker = self._workers.get(normalized)
                if worker is not None:
                    worker.quarantined = True

    def clear_quarantine(self, key: str) -> bool:
        """Clear circuit-breaker state for a worker key."""
        normalized = str(key or "").replace("\\", "/").lower()
        with self._lock:
            had_state = normalized in self._quarantined_until or normalized in self._consecutive_failures
            self._quarantined_until.pop(normalized, None)
            self._consecutive_failures.pop(normalized, None)
            worker = self._workers.get(normalized)
            if worker is not None:
                worker.quarantined = False
            return had_state

    def cancel(self, key: str, request_id: str) -> bool:
        """Cancel a request on a specific worker by key."""
        normalized = str(key or "").replace("\\", "/").lower()
        with self._lock:
            worker = self._workers.get(normalized)
        if worker is None:
            return False
        return worker.cancel(request_id)  # type: ignore[attr-defined, no-any-return]

    def stop(self, key: str) -> None:
        normalized = str(key or "").replace("\\", "/").lower()
        with self._lock:
            worker = self._workers.pop(normalized, None)
        if worker is not None:
            worker.close()

    def poll_health(self, timeout: float = 3.0) -> dict[str, bool]:
        with self._lock:
            workers = list(self._workers.items())
        return {key: (not worker.running or worker.health_check(timeout=timeout)) for key, worker in workers}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            workers = list(self._workers.items())
            closed = self._closed
        return {
            "plugin_id": self.plugin_id,
            "closed": closed,
            "worker_count": len(workers),
            "consecutive_failures": dict(self._consecutive_failures),
            "quarantined_until": {k: round(v, 1) for k, v in self._quarantined_until.items()},
            "workers": {
                key: {
                    "running": worker.running,
                    "quarantined": worker.quarantined,
                    "capabilities": sorted(worker.negotiated_capabilities),
                }
                for key, worker in workers
            },
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.close()
