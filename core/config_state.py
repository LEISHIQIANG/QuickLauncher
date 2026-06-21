"""Runtime configuration state shared by DataManager and its services.

The configuration domain has a single writer (the main application thread, via
DataManager + SaveCoordinator) and many readers (folder/shortcut/settings
services, UI).  Until W2 stage A this state was scattered across
``DataManager`` private attributes (``_save_lock``, ``_runtime_revision``,
``_batch_dirty`` ...).  Service classes were forced to either receive the full
``DataManager`` or cast its private attributes via ``Any``-typed ``host``
parameters.

This module introduces :class:`ConfigState`, a frozen-but-mutable dataclass
that owns the *locks* and the *coordination flags* but leaves application
payload (``data: AppData``) on the host.  The dataclass is deliberately
small: anything that can be derived from ``AppData`` itself stays on
``AppData``.

Design notes:

* ``save_lock`` and ``write_lock`` are created once and *shared* with
  ``DataManager`` so the legacy ``dm._save_lock`` reference continues to lock
  the same object.  This is the migration bridge.
* The dataclass is *not* thread-safe on its own; writers must hold
  ``save_lock`` to mutate ``runtime_revision``, ``batch_*``, ``pending_*``
  and ``suppress_next_history``.
* ``HistoryStore.append`` receives a stable view of the revision when the
  snapshot is captured; services should read ``runtime_revision`` only
  while holding ``save_lock``.
* ``deleted_system_ids`` is the set of icon-repo system IDs the user has
  removed in this session; it is consumed by the icon repository
  when persisting ``icon_repo.json``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class ConfigState:
    """Shared runtime coordination state for the configuration domain.

    Lock-protected mutable state.  The owner (typically ``DataManager``) is
    responsible for serialising all writes through ``save_lock``.

    Attributes mirror the historical DataManager private fields of the same
    meaning; see the matching field on DataManager for full semantics.
    """

    save_lock: threading.RLock = field(default_factory=threading.RLock)
    write_lock: threading.Lock = field(default_factory=threading.Lock)
    runtime_revision: int = 0
    batch_depth: int = 0
    batch_dirty: bool = False
    batch_force_immediate: bool = False
    pending_history_action: str = "\u914d\u7f6e\u53d8\u66f4"
    pending_history_summary: str = ""
    suppress_next_history: bool = False
    deleted_system_ids: set[str] = field(default_factory=set)

    def snapshot(self) -> ConfigState:
        """Return a *value* snapshot for diagnostics and tests.

        The snapshot copies the primitive fields but does not deep-copy
        ``deleted_system_ids``; the returned object is a fresh dataclass
        suitable for read-only inspection.
        """
        return ConfigState(
            save_lock=threading.RLock(),
            write_lock=threading.Lock(),
            runtime_revision=self.runtime_revision,
            batch_depth=self.batch_depth,
            batch_dirty=self.batch_dirty,
            batch_force_immediate=self.batch_force_immediate,
            pending_history_action=self.pending_history_action,
            pending_history_summary=self.pending_history_summary,
            suppress_next_history=self.suppress_next_history,
            deleted_system_ids=set(self.deleted_system_ids),
        )

    def attach_to_host(self, host: Any) -> None:
        """Mirror the legacy DataManager private fields onto the host.

        This is the W2 stage A migration bridge: the dataclass owns the
        locks and the coordination flags, the host keeps the same
        private-attribute names so existing code paths
        (``dm._save_lock``, ``dm._batch_dirty``, ``dm._deleted_system_ids``
        ...) keep working without rewrites.

        All references are shared, not copied: writes through
        ``dm._save_lock`` (read-only) and ``dm._batch_dirty`` continue to
        read the same objects, and writes through the property setters
        declared on the host (added in stage C) will mutate the dataclass.
        For now the dataclass is the single source of truth; direct writes
        to ``dm._batch_dirty`` from service code are converted in stage C.
        """
        # Bind legacy names to the same lock / set instances.
        host._save_lock = self.save_lock
        host._write_lock = self.write_lock
        host._deleted_system_ids = self.deleted_system_ids
