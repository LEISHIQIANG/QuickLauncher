"""Action chain runtime context and execution support.

This module provides the runtime context for action chain execution,
including run tracking, node snapshots, and value management.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from application.errors import UserCancelled

__all__ = [
    "ChainRunContext",
    "ChainNodeRunSnapshot",
    "ChainValueKind",
    "ChainValue",
]


@dataclass
class ChainValueKind:
    """Constants for chain value types."""

    ANY = "any"
    TEXT = "text"
    JSON = "json"
    LIST = "list"
    FILE = "file"
    FOLDER = "folder"
    URL = "url"
    NUMBER = "number"
    BOOL = "bool"

    ALL = {ANY, TEXT, JSON, LIST, FILE, FOLDER, URL, NUMBER, BOOL}


@dataclass
class ChainValue:
    """A typed value in the action chain."""

    kind: str = ChainValueKind.TEXT
    value: Any = None
    text: str = ""
    preview: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "text": self.text,
            "preview": self.preview,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainValue:
        return cls(
            kind=str(data.get("kind") or ChainValueKind.TEXT),
            value=data.get("value"),
            text=str(data.get("text") or ""),
            preview=str(data.get("preview") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ChainNodeRunSnapshot:
    """Snapshot of a single node's execution."""

    node_id: str = ""
    order: int = 0
    title: str = ""
    status: str = "pending"  # pending, running, ok, failed, skipped, warning
    started_at: float = 0.0
    duration: float = 0.0
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    typed_inputs: dict[str, ChainValue] = field(default_factory=dict)
    typed_outputs: dict[str, ChainValue] = field(default_factory=dict)
    message: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "order": self.order,
            "title": self.title,
            "status": self.status,
            "started_at": self.started_at,
            "duration": self.duration,
            "inputs": dict(self.inputs or {}),
            "outputs": dict(self.outputs or {}),
            "typed_inputs": {k: v.to_dict() for k, v in (self.typed_inputs or {}).items()},
            "typed_outputs": {k: v.to_dict() for k, v in (self.typed_outputs or {}).items()},
            "message": self.message,
            "error": self.error,
            "warnings": list(self.warnings or []),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainNodeRunSnapshot:
        return cls(
            node_id=str(data.get("node_id") or ""),
            order=int(data.get("order") or 0),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or "pending"),
            started_at=float(data.get("started_at") or 0.0),
            duration=float(data.get("duration") or 0.0),
            inputs=dict(data.get("inputs") or {}),
            outputs=dict(data.get("outputs") or {}),
            typed_inputs={k: ChainValue.from_dict(v) for k, v in (data.get("typed_inputs") or {}).items()},
            typed_outputs={k: ChainValue.from_dict(v) for k, v in (data.get("typed_outputs") or {}).items()},
            message=str(data.get("message") or ""),
            error=str(data.get("error") or ""),
            warnings=list(data.get("warnings") or []),
        )


@dataclass
class ChainRunContext:
    """Context for an action chain run."""

    chain_id: str = ""
    run_id: str = ""
    values: dict[str, str] = field(default_factory=dict)
    typed_values: dict[str, ChainValue] = field(default_factory=dict)
    snapshots: dict[str, ChainNodeRunSnapshot] = field(default_factory=dict)
    cancel_event: Any = None
    started_at: float = 0.0
    max_steps: int = 0
    current_step: int = 0

    def __post_init__(self):
        if not self.run_id:
            self.run_id = str(uuid.uuid4())
        if not self.started_at:
            self.started_at = time.time()

    def is_cancelled(self) -> bool:
        """Check if the run has been cancelled."""
        if self.cancel_event is None:
            return False
        try:
            return bool(self.cancel_event.is_set())
        except Exception:
            return False

    def check_cancelled(self) -> None:
        """Raise if the run has been cancelled."""
        if self.is_cancelled():
            raise CancelledError("动作链执行已取消。")

    def create_snapshot(self, node_id: str, order: int, title: str) -> ChainNodeRunSnapshot:
        """Create a new snapshot for a node."""
        snapshot = ChainNodeRunSnapshot(
            node_id=node_id,
            order=order,
            title=title,
            status="running",
            started_at=time.time(),
        )
        self.snapshots[node_id] = snapshot
        return snapshot

    def complete_snapshot(
        self,
        node_id: str,
        status: str,
        outputs: dict[str, str] | None = None,
        typed_outputs: dict[str, ChainValue] | None = None,
        message: str = "",
        error: str = "",
        warnings: list[str] | None = None,
    ) -> None:
        """Mark a snapshot as complete."""
        snapshot = self.snapshots.get(node_id)
        if snapshot is None:
            return
        snapshot.status = status
        snapshot.duration = time.time() - snapshot.started_at
        if outputs is not None:
            snapshot.outputs = outputs
        if typed_outputs is not None:
            snapshot.typed_outputs = typed_outputs
        if message:
            snapshot.message = message
        if error:
            snapshot.error = error
        if warnings:
            snapshot.warnings = warnings

    def get_snapshot(self, node_id: str) -> ChainNodeRunSnapshot | None:
        """Get the snapshot for a node."""
        return self.snapshots.get(node_id)

    def get_snapshots_dict(self) -> dict[str, dict[str, Any]]:
        """Get all snapshots as a dictionary."""
        return {node_id: snapshot.to_dict() for node_id, snapshot in self.snapshots.items()}

    def elapsed(self) -> float:
        """Get the elapsed time since the run started."""
        return time.time() - self.started_at


class CancelledError(UserCancelled):
    """Raised when an action chain run is cancelled."""

    pass
