"""Plugin worker thread tracking extracted from plugin_manager.py."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_PLUGIN_EXECUTOR_REGISTRY_LOCK = threading.Lock()


def _track_executor(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    executor: threading.Thread,
) -> None:
    """Register a plugin command worker thread."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        executors = registry.setdefault(plugin_id, [])
        executors.append(executor)


def _untrack_executor(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    executor: threading.Thread,
) -> None:
    """Remove a finished command worker from the tracking registry."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        executors = registry.get(plugin_id)
        if executors is not None:
            try:
                executors.remove(executor)
            except ValueError as exc:
                logger.debug("plugin executor already untracked: %s", exc, exc_info=True)
            if not executors:
                registry.pop(plugin_id, None)


def _drain_plugin_executors(
    registry: dict[str, list[threading.Thread]],
    plugin_id: str,
    timeout: float = 5.0,
) -> None:
    """Wait briefly for tracked plugin command workers during quarantine."""
    with _PLUGIN_EXECUTOR_REGISTRY_LOCK:
        workers = registry.pop(plugin_id, [])
    if not workers:
        return
    deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
    for worker in workers:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        worker.join(timeout=remaining)
    still_alive = [worker for worker in workers if worker.is_alive()]
    if still_alive:
        logger.warning("插件 %s 隔离时仍有 %d 个命令工作线程在运行", plugin_id, len(still_alive))


# ---------------------------------------------------------------------------
