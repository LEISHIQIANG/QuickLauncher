from core.data_models import ShortcutItem, ShortcutType
from core.shortcut_executor import ShortcutExecutor


def test_execute_dispatches_hotkey(monkeypatch):
    shortcut = ShortcutItem(type=ShortcutType.HOTKEY, hotkey="Ctrl+S")
    called = {}

    def fake_execute(item):
        called["item"] = item
        return True

    monkeypatch.setattr(ShortcutExecutor, "_execute_hotkey_safe", staticmethod(fake_execute))

    success, error = ShortcutExecutor.execute(shortcut)

    assert success is True
    assert error == ""
    assert called["item"] is shortcut


def test_execute_dispatches_url(monkeypatch):
    shortcut = ShortcutItem(type=ShortcutType.URL, url="https://example.com")
    called = {}

    def fake_execute(item):
        called["item"] = item
        return True

    monkeypatch.setattr(ShortcutExecutor, "_execute_url", staticmethod(fake_execute))

    success, error = ShortcutExecutor.execute(shortcut)

    assert success is True
    assert error == ""
    assert called["item"] is shortcut


def test_execute_dispatches_command(monkeypatch):
    shortcut = ShortcutItem(type=ShortcutType.COMMAND, command="echo ok")
    called = {}

    def fake_execute(item):
        called["item"] = item
        return True, ""

    monkeypatch.setattr(ShortcutExecutor, "_execute_command", staticmethod(fake_execute))

    success, error = ShortcutExecutor.execute(shortcut)

    assert success is True
    assert error == ""
    assert called["item"] is shortcut


def test_execute_dispatches_file(monkeypatch):
    shortcut = ShortcutItem(type=ShortcutType.FILE, target_path="tool.exe")
    called = {}

    def fake_execute(item, force_new=False):
        called["item"] = item
        called["force_new"] = force_new
        return True, ""

    monkeypatch.setattr(ShortcutExecutor, "_execute_file", staticmethod(fake_execute))

    success, error = ShortcutExecutor.execute(shortcut, force_new=True)

    assert success is True
    assert error == ""
    assert called == {"item": shortcut, "force_new": True}


def test_execute_with_files_rejects_unsupported_type():
    shortcut = ShortcutItem(type=ShortcutType.URL, url="https://example.com")

    assert ShortcutExecutor.execute_with_files(shortcut, ["a.txt"]) is False
