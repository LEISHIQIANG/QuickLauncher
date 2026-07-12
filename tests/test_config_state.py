"""Guard tests for the W2 stage A + B state abstraction.

The DataManager facade used to own the entire runtime configuration state
through private attributes (``_save_lock``, ``_batch_dirty`` ...).  Services
that did not want to depend on the full facade had to cast ``host._xxx``
via :class:`typing.Any`.  W2 stages A and B introduce a
:class:`core.config_state.ConfigState` dataclass and a
:class:`core.config_unit_of_work.ConfigUnitOfWork` that reads from the
state.

These tests pin three properties the rest of the migration depends on:

1. :meth:`ConfigState.attach_to_host` shares lock objects, so a service
   that holds the host and a service that holds the state lock the same
   RLock instance.
2. :class:`ConfigUnitOfWork` returns the state-owned lock even when the
   host still has its private attributes set; this is the bridge that
   makes it possible to remove the host private fields in stage C.
3. ``batch_dirty`` and ``deleted_system_ids`` mutations through the
   unit-of-work are visible to readers that only have the host (and
   vice versa), because the underlying object is shared.
"""

from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from core.config_state import ConfigState
from core.config_unit_of_work import ConfigUnitOfWork


class ConfigStateAttachToHostTests(unittest.TestCase):
    def test_attach_shares_lock_objects(self) -> None:
        host = SimpleNamespace()
        state = ConfigState()
        state.attach_to_host(host)
        self.assertIs(host._save_lock, state.save_lock)
        self.assertIs(host._write_lock, state.write_lock)
        self.assertIs(host._deleted_system_ids, state.deleted_system_ids)

    def test_attach_does_not_create_new_lock_per_call(self) -> None:
        host = SimpleNamespace()
        state = ConfigState()
        state.attach_to_host(host)
        original_lock = state.save_lock
        with state.save_lock:
            pass
        # A re-attach with the same state must not invent a new RLock.
        state.attach_to_host(host)
        self.assertIs(host._save_lock, original_lock)

    def test_snapshot_is_independent(self) -> None:
        state = ConfigState(runtime_revision=5, batch_dirty=True)
        host = SimpleNamespace()
        state.attach_to_host(host)
        host._deleted_system_ids.add("alpha")
        snap = state.snapshot()
        snap.runtime_revision = 99
        snap.deleted_system_ids.add("beta")
        # Mutating the snapshot must not affect the live state.
        self.assertEqual(state.runtime_revision, 5)
        self.assertIn("alpha", state.deleted_system_ids)
        self.assertNotIn("beta", state.deleted_system_ids)


class ConfigUnitOfWorkStateRouteTests(unittest.TestCase):
    def _make_host(self) -> Any:
        host = SimpleNamespace()
        host._save_lock = threading.RLock()
        host._write_lock = threading.Lock()
        host._batch_dirty = False
        host._suppress_next_history = False
        host._deleted_system_ids = set()
        host.data = SimpleNamespace(settings=SimpleNamespace())
        host._mark_history = MagicMock()
        host.save = MagicMock(return_value=True)
        host.batch_update = MagicMock()
        host.save_icon_repo = MagicMock(return_value=True)
        return host

    def test_lock_uses_state_when_provided(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        self.assertIs(uow.lock, state.save_lock)

    def test_lock_falls_back_to_host_when_state_missing(self) -> None:
        host = self._make_host()
        uow = ConfigUnitOfWork(host)
        self.assertIs(uow.lock, host._save_lock)

    def test_lock_inherits_host_state_via_attach(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        # Mirror what DataManager.__init__ does: store the state on the
        # host so that legacy construction (``ConfigUnitOfWork(host)``)
        # can derive it automatically.
        host._state = state
        uow = ConfigUnitOfWork(host)
        self.assertIs(uow.state, state)
        self.assertIs(uow.lock, host._save_lock)

    def test_batch_dirty_setter_propagates_to_state_and_host(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        uow.batch_dirty = True
        self.assertTrue(state.batch_dirty)
        self.assertTrue(host._batch_dirty)

    def test_suppress_next_history_setter_propagates(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        uow.suppress_next_history = True
        self.assertTrue(state.suppress_next_history)
        self.assertTrue(host._suppress_next_history)

    def test_deleted_system_ids_setter_propagates(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        uow.deleted_system_ids = {"foo", "bar"}
        self.assertEqual(state.deleted_system_ids, {"foo", "bar"})
        self.assertEqual(host._deleted_system_ids, {"foo", "bar"})

    def test_mark_history_dual_writes(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        uow.mark_history("配置变更", "summary")
        host._mark_history.assert_called_once_with("配置变更", "summary")
        self.assertEqual(state.pending_history_action, "配置变更")
        self.assertEqual(state.pending_history_summary, "summary")

    def test_save_and_save_icon_repo_delegate(self) -> None:
        host = self._make_host()
        state = ConfigState()
        state.attach_to_host(host)
        uow = ConfigUnitOfWork(host, state)
        uow.save(immediate=True)
        host.save.assert_called_once_with(immediate=True)
        uow.save_icon_repo()
        host.save_icon_repo.assert_called_once_with()


class ConfigStateDataManagerIntegrationTests(unittest.TestCase):
    def test_data_manager_owns_a_state(self) -> None:
        from core.data_manager import DataManager

        dm = DataManager.__new__(DataManager)
        # Exercise the same state bootstrap DataManager.__init__ performs
        # without paying for the full load/repair pipeline.
        dm._state = ConfigState()
        dm._state.attach_to_host(dm)
        self.assertIs(dm._save_lock, dm._state.save_lock)
        self.assertIs(dm._write_lock, dm._state.write_lock)
        self.assertIs(dm._deleted_system_ids, dm._state.deleted_system_ids)
        # The unit of work built from the host must see the same state.
        uow = ConfigUnitOfWork(dm)
        self.assertIs(uow.state, dm._state)
        self.assertIs(uow.lock, dm._state.save_lock)


if __name__ == "__main__":
    unittest.main()
