"""Thread-safe single-writer state with optimistic revision checks."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from application.errors import RevisionConflict

State = dict[str, Any]
StateCommand = Callable[[State], State]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True)
class AppSnapshot:
    revision: int
    state: Mapping[str, Any]


class StateStore:
    """Serialize state commands and expose immutable revisioned snapshots."""

    def __init__(self, initial_state: Mapping[str, Any] | None = None, *, revision: int = 0) -> None:
        if revision < 0:
            raise ValueError("revision must be non-negative")
        self._lock = threading.RLock()
        self._state: State = deepcopy(dict(initial_state or {}))
        self._revision = revision

    def snapshot(self) -> AppSnapshot:
        with self._lock:
            return AppSnapshot(revision=self._revision, state=_freeze(self._state))

    def submit(self, command: StateCommand, *, expected_revision: int) -> AppSnapshot:
        """Apply one command atomically when the caller observed the current revision."""
        with self._lock:
            if expected_revision != self._revision:
                raise RevisionConflict(expected_revision, self._revision)
            working_copy = deepcopy(self._state)
            next_state = command(working_copy)
            if not isinstance(next_state, dict):
                raise TypeError("state command must return a dict")
            self._state = deepcopy(next_state)
            self._revision += 1
            return AppSnapshot(revision=self._revision, state=_freeze(self._state))

    def replace(self, state: Mapping[str, Any], *, expected_revision: int) -> AppSnapshot:
        return self.submit(lambda _current: dict(state), expected_revision=expected_revision)
