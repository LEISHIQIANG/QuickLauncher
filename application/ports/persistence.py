"""Persistence ports for configuration use cases.

These are the narrow contracts the application layer expects from the
infrastructure adapters.  W2 stage D introduces a complementary
:class:`ConfigStatePort` that the :class:`core.save_coordinator.SaveCoordinator`
depends on for its coordination state (locks, revision, batch flags,
pending history).  ``SaveCoordinator`` is in the process of being migrated
to consume the state port rather than the historical DataManager private
attributes; the port below pins the contract that migration must keep.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol


class ConfigRepository(Protocol):
    def load(self) -> Mapping[str, Any]: ...

    def save(self, data: Mapping[str, Any], *, expected_revision: int) -> int: ...


class BackupStore(Protocol):
    def create(self, data: Mapping[str, Any], *, reason: str) -> str: ...

    def restore(self, backup_id: str) -> Mapping[str, Any]: ...


class HistoryStore(Protocol):
    def append(self, revision: int, data: Mapping[str, Any], *, action: str, summary: str) -> None: ...


class SaveScheduler(Protocol):
    def schedule(self, callback: Callable[[], None]) -> None: ...

    def cancel(self) -> None: ...


class Clock(Protocol):
    def now(self) -> float: ...


class ConfigStatePort(Protocol):
    """Coordination state shared by SaveCoordinator and other services.

    The state is the single source of truth for the runtime flags that
    coordinate writes (revision counter, batch nesting, pending history
    annotation, and the locks that serialise them).  Implementations
    must hand out the *same* lock objects every time so a service that
    holds the host and a service that holds the state lock the same
    underlying primitive.

    The :class:`core.config_state.ConfigState` dataclass is the canonical
    implementation; :class:`core.data_manager.DataManager` exposes the
    same attributes through state-routing properties.
    """

    @property
    def save_lock(self) -> Any: ...

    @property
    def write_lock(self) -> Any: ...

    @property
    def runtime_revision(self) -> int: ...

    @runtime_revision.setter
    def runtime_revision(self, value: int) -> None: ...

    @property
    def batch_depth(self) -> int: ...

    @batch_depth.setter
    def batch_depth(self, value: int) -> None: ...

    @property
    def batch_dirty(self) -> bool: ...

    @batch_dirty.setter
    def batch_dirty(self, value: bool) -> None: ...

    @property
    def batch_force_immediate(self) -> bool: ...

    @batch_force_immediate.setter
    def batch_force_immediate(self, value: bool) -> None: ...

    @property
    def pending_history_action(self) -> str: ...

    @pending_history_action.setter
    def pending_history_action(self, value: str) -> None: ...

    @property
    def pending_history_summary(self) -> str: ...

    @pending_history_summary.setter
    def pending_history_summary(self, value: str) -> None: ...

    @property
    def suppress_next_history(self) -> bool: ...

    @suppress_next_history.setter
    def suppress_next_history(self, value: bool) -> None: ...
