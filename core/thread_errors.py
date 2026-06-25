"""Structured thread error logging for uncaught exceptions in worker threads.

Provides a centralized JSONL-based persistence layer for recording thread errors
that would otherwise be silently swallowed by Python's default excepthook.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import traceback
from datetime import datetime
from typing import Any

from runtime_paths import config_dir

logger = logging.getLogger(__name__)

_THREAD_ERROR_LOG = "thread_errors.jsonl"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3
_WRITE_LOCK = threading.Lock()


def _rotate_log(path: str) -> None:
    if not os.path.exists(path) or os.path.getsize(path) <= _MAX_BYTES:
        return
    for i in range(_BACKUP_COUNT - 1, 0, -1):
        old = f"{path}.{i}"
        new = f"{path}.{i + 1}"
        if os.path.exists(old):
            if os.path.exists(new):
                try:
                    os.remove(new)
                except OSError:
                    logger.debug("Could not remove old backup %s", new)
            try:
                os.replace(old, new)
            except OSError:
                logger.debug("Could not rotate %s -> %s", old, new)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.debug("Could not remove %s", path)


def _get_log_path() -> str:
    try:
        return str(config_dir() / _THREAD_ERROR_LOG)
    except Exception:
        return _THREAD_ERROR_LOG


def record_thread_error(
    thread_name: str,
    exc: BaseException,
    *,
    owner: str = "",
    trace: str = "",
) -> None:
    """Record an uncaught thread exception to the structured error log.

    Thread-safe; serializes writes through a module-level lock.

    Args:
        thread_name: Human-readable name of the thread.
        exc: The exception instance.
        owner: Optional identifier for the component that created the thread.
        trace: Optional pre-formatted traceback string; auto-generated if empty.
    """
    log_path = _get_log_path()
    with _WRITE_LOCK:
        try:
            dirname = os.path.dirname(log_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            _rotate_log(log_path)

            payload = {
                "time": datetime.now().isoformat(timespec="microseconds"),
                "thread_name": str(thread_name) or "",
                "thread_id": _current_thread_id(),
                "owner": str(owner or ""),
                "exc_type": type(exc).__qualname__,
                "exc_message": str(exc),
                "trace": trace or traceback.format_exc(),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Failed to record thread error: %s", exc, exc_info=True)


def get_thread_error_log(limit: int = 50, after: str = "") -> list[dict[str, Any]]:
    """Return the most recent thread error records.

    Args:
        limit: Maximum number of records to return.
        after: ISO timestamp filter — only records after this time are returned.

    Returns:
        A list of dicts, newest first, each containing the structured error fields.
    """
    log_path = _get_log_path()
    if not os.path.isfile(log_path):
        return []

    records: list[dict[str, Any]] = []
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                if after and record.get("time", "") <= after:
                    continue
                records.append(record)
    except (OSError, ValueError) as exc:
        logger.debug("Failed to read thread error log: %s", exc, exc_info=True)
        return []

    records.sort(key=lambda r: str(r.get("time", "")), reverse=True)
    return records[:limit]


def _current_thread_id() -> int:
    try:
        return threading.current_thread().ident or 0
    except (AttributeError, RuntimeError):
        return 0


__all__ = [
    "record_thread_error",
    "get_thread_error_log",
]
