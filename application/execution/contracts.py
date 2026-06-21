"""Framework-independent contracts for every command execution entry point."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExecutionErrorCode(StrEnum):
    VALIDATION = "validation"
    PRECONDITION = "precondition"
    SECURITY = "security"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    PROCESS = "process"
    PLUGIN = "plugin"
    INTERNAL = "internal"


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout_seconds: float = 300.0
    capture_output: bool = True
    confirm_dangerous: bool = True
    audit: bool = True

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class CancellationToken:
    """Cooperative, thread-safe cancellation owned by the application layer."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def event(self) -> threading.Event:
        return self._event


@dataclass
class ExecutionRequest:
    command_id: str = ""
    args_text: str = ""
    raw_input: str = ""
    context_meta: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    shortcut: Any = None
    args: dict[str, str] = field(default_factory=dict)
    command_def: Any = None
    invocation: Any = None
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    message: str = ""
    error_code: ExecutionErrorCode | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
