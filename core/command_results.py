"""In-memory storage for command panel results."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from core.command_registry import CommandResult


@dataclass
class StoredCommandResult:
    id: str
    command_id: str = ""
    command_title: str = ""
    raw_input: str = ""
    source: str = ""
    created_at: float = 0.0
    duration: float = 0.0
    result: CommandResult = field(default_factory=CommandResult)
    args: dict[str, str] = field(default_factory=dict)
    masked_args: dict[str, str] = field(default_factory=dict)
    has_sensitive_args: bool = False
    context_meta: dict = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)


class CommandResultStore:
    """Keep recent command results for the independent command panel."""

    def __init__(self, max_items: int = 5):
        self.max_items = max(1, int(max_items or 5))
        self._items: list[StoredCommandResult] = []
        self._lock = threading.RLock()

    def add(self, result: CommandResult, **meta) -> str:
        result_id = str(uuid.uuid4())
        item = StoredCommandResult(
            id=result_id,
            command_id=str(meta.get("command_id") or ""),
            command_title=str(meta.get("command_title") or ""),
            raw_input=str(meta.get("raw_input") or ""),
            source=str(meta.get("source") or ""),
            created_at=float(meta.get("created_at") or time.time()),
            duration=float(meta.get("duration") or 0.0),
            result=result,
            args={str(k): str(v) for k, v in dict(meta.get("args") or {}).items()},
            masked_args={str(k): str(v) for k, v in dict(meta.get("masked_args") or {}).items()},
            has_sensitive_args=bool(meta.get("has_sensitive_args", False)),
            context_meta=dict(meta.get("context_meta") or {}),
            outputs={str(k): str(v) for k, v in dict(meta.get("outputs") or {}).items()},
        )
        with self._lock:
            self._items.insert(0, item)
            del self._items[self.max_items :]
        return result_id

    def get(self, result_id: str) -> StoredCommandResult | None:
        with self._lock:
            for item in self._items:
                if item.id == result_id:
                    return item
        return None

    def latest(self) -> StoredCommandResult | None:
        with self._lock:
            return self._items[0] if self._items else None

    def list(self) -> list[StoredCommandResult]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
