"""Process-wide ownership and shutdown for long-lived thread pools."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

COMMAND_EXECUTOR = "command"
STREAM_IO_EXECUTOR = "stream-io"
PLUGIN_SEARCH_EXECUTOR = "plugin-search"
PLUGIN_SEARCH_COORDINATOR_EXECUTOR = "plugin-search-coordinator"
PROCESS_CHECK_EXECUTOR = "process-check"

_EXECUTOR_SPECS: dict[str, tuple[int, str]] = {
    COMMAND_EXECUTOR: (8, "CmdExecPool"),
    STREAM_IO_EXECUTOR: (4, "CmdStreamIO"),
    PLUGIN_SEARCH_EXECUTOR: (6, "PluginSearch"),
    PLUGIN_SEARCH_COORDINATOR_EXECUTOR: (4, "PluginSearchCoordinator"),
    PROCESS_CHECK_EXECUTOR: (1, "QLProcessCheck"),
}

T = TypeVar("T")


class ManagedExecutor(concurrent.futures.Executor):
    """Thread pool wrapper that tracks work and supports bounded draining."""

    def __init__(self, name: str, max_workers: int, thread_name_prefix: str) -> None:
        self.name = name
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._lock = threading.Lock()
        self._futures: set[concurrent.futures.Future[Any]] = set()
        self._closed = False

    def submit(self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> concurrent.futures.Future[T]:
        with self._lock:
            if self._closed:
                raise RuntimeError(f"executor is shut down: {self.name}")
            future = self._pool.submit(fn, *args, **kwargs)
            self._futures.add(future)

        def _forget(done: concurrent.futures.Future[Any]) -> None:
            with self._lock:
                self._futures.discard(done)

        future.add_done_callback(_forget)
        return future

    def pending_futures(self) -> list[concurrent.futures.Future[Any]]:
        with self._lock:
            return [future for future in self._futures if not future.done()]

    def drain(self, timeout: float) -> list[concurrent.futures.Future[Any]]:
        """Reject new work, cancel queued work, and wait up to *timeout*."""
        should_shutdown = False
        with self._lock:
            if not self._closed:
                self._closed = True
                should_shutdown = True
            futures = list(self._futures)
        # ThreadPoolExecutor.cancel_futures invokes Future callbacks
        # synchronously.  Those callbacks acquire ``self._lock``, so shutdown
        # must never run while the manager lock is held.
        if should_shutdown:
            self._pool.shutdown(wait=False, cancel_futures=True)
        for future in futures:
            future.cancel()
        if futures and timeout > 0:
            concurrent.futures.wait(futures, timeout=timeout)
        return [future for future in futures if not future.done()]

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        timeout = 30.0 if wait else 0.0
        pending = self.drain(timeout)
        if pending and wait:
            logger.warning("Executor %s still has %d running task(s)", self.name, len(pending))


class ExecutorManager:
    """Own named executors and provide one idempotent process shutdown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executors: dict[str, ManagedExecutor] = {}
        self._shutdown_started = False

    def get(self, name: str) -> ManagedExecutor:
        try:
            max_workers, thread_name_prefix = _EXECUTOR_SPECS[name]
        except KeyError as exc:
            raise ValueError(f"unknown executor: {name}") from exc
        with self._lock:
            if self._shutdown_started:
                raise RuntimeError("application executor manager is shut down")
            executor = self._executors.get(name)
            if executor is None:
                executor = ManagedExecutor(name, max_workers, thread_name_prefix)
                self._executors[name] = executor
            return executor

    def shutdown_one(self, name: str, timeout: float = 3.0) -> int:
        """Close one pool while leaving the manager available for recreation."""
        with self._lock:
            executor = self._executors.pop(name, None)
        if executor is None:
            return 0
        pending = executor.drain(max(0.0, float(timeout or 0.0)))
        if pending:
            logger.warning("Executor %s did not drain before timeout: %d task(s)", name, len(pending))
        return len(pending)

    def shutdown_all(self, timeout: float = 5.0) -> dict[str, int]:
        """Permanently reject submissions and drain all named pools."""
        with self._lock:
            if self._shutdown_started:
                return {}
            self._shutdown_started = True
            executors = list(self._executors.items())
            self._executors.clear()

        deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
        pending_by_name: dict[str, int] = {}
        for name, executor in executors:
            remaining = max(0.0, deadline - time.monotonic())
            pending = executor.drain(remaining)
            if pending:
                pending_by_name[name] = len(pending)
                logger.warning("Executor %s still running at application shutdown: %d task(s)", name, len(pending))
        return pending_by_name

    @property
    def shutdown_started(self) -> bool:
        with self._lock:
            return self._shutdown_started


_manager: ExecutorManager | None = None


def _get_manager() -> ExecutorManager:
    global _manager
    if _manager is None:
        _manager = ExecutorManager()
    return _manager


def get_executor(name: str) -> ManagedExecutor:
    return _get_manager().get(name)


def shutdown_executor(name: str, timeout: float = 3.0) -> int:
    return _get_manager().shutdown_one(name, timeout)


def shutdown_all_executors(timeout: float = 5.0) -> dict[str, int]:
    return _get_manager().shutdown_all(timeout)


def executor_shutdown_started() -> bool:
    return _get_manager().shutdown_started
