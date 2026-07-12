"""Narrow mutation boundary used by configuration application services.

The class used to cast ``host._save_lock`` / ``host._batch_dirty`` directly,
which forced ``DataManager`` to keep these fields forever.  W2 stage B routes
the state-derived reads through a :class:`ConfigState` instance (W2 stage A),
so services depend on the state object instead of the host facade.

Two construction patterns are supported during the migration bridge:

* ``ConfigUnitOfWork(host, state)`` — preferred: ``state`` is the single
  source of truth for locks, batch flags, and ``deleted_system_ids``.
* ``ConfigUnitOfWork(host)`` — legacy: derives ``state`` from
  ``host._state`` (set by :meth:`ConfigState.attach_to_host`); falls back
  to the historical private-attribute reads if ``state`` is missing.

The :class:`DataManager` constructor always uses the preferred form; the
fallback exists for tests that build a bare ``ConfigUnitOfWork``.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from .config_state import ConfigState


class LockLike(Protocol):
    def __enter__(self) -> Any: ...

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None: ...


class ConfigUnitOfWork:
    """Expose state mutation operations without exposing the DataManager facade."""

    def __init__(self, host: Any, state: ConfigState | None = None) -> None:
        self._host = host
        if state is None:
            state = getattr(host, "_state", None)
        self._state = state

    @property
    def state(self) -> ConfigState | None:
        """The underlying :class:`ConfigState` (may be ``None`` for legacy hosts)."""
        return self._state

    @property
    def lock(self) -> LockLike:
        if self._state is not None:
            return self._state.save_lock
        return cast(LockLike, self._host._save_lock)

    @property
    def data(self) -> Any:
        return self._host.data

    def mark_history(self, action: str, summary: str = "") -> None:
        if self._state is not None:
            self._state.pending_history_action = action
            self._state.pending_history_summary = summary
        self._host._mark_history(action, summary)

    def save(self, immediate: bool = False) -> bool:
        return bool(self._host.save(immediate=immediate))

    def batch_update(self, immediate: bool = False) -> AbstractContextManager[Any]:
        return cast(AbstractContextManager[Any], self._host.batch_update(immediate=immediate))

    @property
    def batch_dirty(self) -> bool:
        if self._state is not None:
            return self._state.batch_dirty
        return bool(self._host._batch_dirty)

    @batch_dirty.setter
    def batch_dirty(self, value: bool) -> None:
        if self._state is not None:
            self._state.batch_dirty = bool(value)
        self._host._batch_dirty = bool(value)

    @property
    def suppress_next_history(self) -> bool:
        if self._state is not None:
            return self._state.suppress_next_history
        return bool(self._host._suppress_next_history)

    @suppress_next_history.setter
    def suppress_next_history(self, value: bool) -> None:
        if self._state is not None:
            self._state.suppress_next_history = bool(value)
        self._host._suppress_next_history = bool(value)

    @property
    def deleted_system_ids(self) -> set[str]:
        if self._state is not None:
            return self._state.deleted_system_ids
        return cast(set[str], self._host._deleted_system_ids)

    @deleted_system_ids.setter
    def deleted_system_ids(self, value: set[str]) -> None:
        new_value = set(value)
        if self._state is not None:
            self._state.deleted_system_ids = new_value
        self._host._deleted_system_ids = new_value

    def save_icon_repo(self) -> bool:
        return bool(self._host.save_icon_repo())
