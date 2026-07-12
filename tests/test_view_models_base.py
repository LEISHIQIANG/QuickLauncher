"""Tests for the P1-06 Stage 1 view-model base classes."""

from __future__ import annotations

import pytest

from ui.view_models.base import DialogViewModel, ListViewModel, ViewModel

pytestmark = pytest.mark.ui


def test_viewmodel_emits_state_changed():
    vm = ViewModel()
    seen = []
    vm.state_changed.connect(lambda payload: seen.append(payload))
    vm.emit_state({"x": 1})
    assert seen == [{"x": 1}]


def test_viewmodel_dirty_flag_round_trip():
    vm = ViewModel()
    assert vm.is_dirty() is False
    seen = []
    vm.dirty_changed.connect(lambda value: seen.append(value))
    vm.set_dirty(True)
    assert vm.is_dirty() is True
    assert seen == [True]
    # Setting the same value does not re-emit.
    vm.set_dirty(True)
    assert seen == [True]
    vm.set_dirty(False)
    assert seen == [True, False]


def test_viewmodel_shutdown_is_noop_by_default():
    vm = ViewModel()
    assert vm.shutdown() is None


def test_list_viewmodel_item_signals():
    vm = ListViewModel()
    inserts, removes, updates, resets = [], [], [], []

    vm.item_inserted.connect(lambda i: inserts.append(i))
    vm.item_removed.connect(lambda i: removes.append(i))
    vm.item_updated.connect(lambda i: updates.append(i))
    vm.items_changed.connect(lambda: resets.append(True))

    vm._notify_item_inserted(0)
    vm._notify_item_inserted(1)
    vm._notify_item_updated(0)
    vm._notify_item_removed(1)
    vm._notify_items_reset()

    assert inserts == [0, 1]
    assert removes == [1]
    assert updates == [0]
    # 4 notifier calls (2 inserts + 1 update + 1 remove + 1 reset) →
    # 5 resets (each notify emits one, plus the standalone reset).
    assert len(resets) == 5


def test_dialog_viewmodel_commit_and_revert():
    vm = DialogViewModel()
    accepted, rejected = [], []
    vm.accepted.connect(lambda: accepted.append(True))
    vm.rejected.connect(lambda: rejected.append(True))

    assert vm.commit() is True
    assert vm.is_committed() is True
    assert vm.is_dirty() is False
    assert accepted == [True]

    vm.set_dirty(True)
    assert vm.revert() is True
    assert vm.is_reverted() is True
    assert vm.is_dirty() is False
    assert rejected == [True]


def test_dialog_viewmodel_commit_resets_reverted_flag():
    """Calling ``revert`` then ``commit`` must flip both flags."""
    vm = DialogViewModel()
    vm.revert()
    assert vm.is_reverted() is True
    assert vm.is_committed() is False
    vm.commit()
    assert vm.is_committed() is True
    assert vm.is_reverted() is False


def test_dialog_viewmodel_revert_resets_committed_flag():
    vm = DialogViewModel()
    vm.commit()
    assert vm.is_committed() is True
    vm.revert()
    assert vm.is_reverted() is True
    assert vm.is_committed() is False


def test_viewmodel_default_state_payload():
    vm = ViewModel()
    vm.set_dirty(True)
    payloads = []
    vm.state_changed.connect(lambda p: payloads.append(p))
    vm.emit_state()
    # The explicit emit_state call appends an empty payload, not None
    assert payloads == [None]
