"""Launcher popup drag/drop regression tests."""

import ui.launcher_popup.popup_drag_drop as drag_drop
from core.data_models import ShortcutItem, ShortcutType


class _DummyManager:
    def __init__(self):
        self.recorded = []

    def record_shortcut_used(self, shortcut_id):
        self.recorded.append(shortcut_id)
        return True


class _DummyPopup(drag_drop.PopupDragDropMixin):
    def __init__(self):
        self._executing = True
        self.data_manager = _DummyManager()
        self.closed = False

    def close(self):
        self.closed = True


def test_drop_execution_records_usage_on_success(monkeypatch):
    item = ShortcutItem(id="drop-1", name="Drop", type=ShortcutType.FILE, target_path="app.exe")
    popup = _DummyPopup()

    class FakeExecutor:
        @staticmethod
        def execute_with_files(shortcut, files):
            return True

    monkeypatch.setattr(drag_drop, "HAS_EXECUTOR", True)
    monkeypatch.setattr(drag_drop, "ShortcutExecutor", FakeExecutor)

    popup._do_execute_drop(item, ["a.txt"], should_close=True)

    assert popup.data_manager.recorded == ["drop-1"]
    assert not popup._executing
    assert popup.closed


def test_drop_execution_does_not_record_usage_on_failure(monkeypatch):
    item = ShortcutItem(id="drop-1", name="Drop", type=ShortcutType.FILE, target_path="app.exe")
    popup = _DummyPopup()

    class FakeExecutor:
        @staticmethod
        def execute_with_files(shortcut, files):
            return False

    monkeypatch.setattr(drag_drop, "HAS_EXECUTOR", True)
    monkeypatch.setattr(drag_drop, "ShortcutExecutor", FakeExecutor)

    popup._do_execute_drop(item, ["a.txt"], should_close=False)

    assert popup.data_manager.recorded == []
    assert not popup._executing
    assert not popup.closed
