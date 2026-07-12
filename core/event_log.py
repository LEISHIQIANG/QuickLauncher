"""Lightweight event log for key operations (events.jsonl)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_EVENTS_FILE = "events.jsonl"
_MAX_BYTES = 512 * 1024  # 512 KB
_BACKUP_COUNT = 2

_lock = threading.Lock()
_event_dir: Path | None = None


def init_event_log(config_dir: Path | str) -> None:
    """Initialize the event log directory."""
    global _event_dir
    _event_dir = Path(config_dir)


def log_event(event: str, summary: str, details: dict | None = None) -> None:
    """Append an event to events.jsonl with rotation."""
    if _event_dir is None:
        return
    try:
        _event_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "summary": summary,
        }
        if details:
            # Truncate large detail values
            safe_details = {}
            for k, v in details.items():
                s = str(v)
                if len(s) > 200:
                    s = s[:200] + "..."
                safe_details[k] = s
            entry["details"] = safe_details  # type: ignore[assignment]

        with _lock:
            path = _event_dir / _EVENTS_FILE
            _rotate_if_needed(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("log_event failed: %s", exc)


def _rotate_if_needed(path: Path) -> None:
    """Rotate events.jsonl if it exceeds max size."""
    try:
        if not path.exists():
            return
        if path.stat().st_size < _MAX_BYTES:
            return
        # Rotate: events.jsonl.2 -> delete, events.jsonl.1 -> events.jsonl.2, events.jsonl -> events.jsonl.1
        for i in range(_BACKUP_COUNT, 0, -1):
            src = path.with_suffix(f".jsonl.{i}")
            dst = path.with_suffix(f".jsonl.{i + 1}")
            if src.exists():
                if i >= _BACKUP_COUNT:
                    try:
                        src.unlink()
                    except Exception:
                        logger.debug("删除旧事件日志备份失败", exc_info=True)
                else:
                    src.rename(dst)
        path.rename(path.with_suffix(".jsonl.1"))
    except Exception as exc:
        logger.debug("rotate events.jsonl failed: %s", exc)


def read_recent_events(config_dir: Path | str, max_lines: int = 200) -> list[dict]:
    """Read recent events from events.jsonl (tail)."""
    try:
        path = Path(config_dir) / _EVENTS_FILE
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for line in lines[-max_lines:]:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        events.append(data)
                except json.JSONDecodeError:
                    logger.debug("解析事件日志行失败", exc_info=True)
        return events
    except Exception:
        return []
