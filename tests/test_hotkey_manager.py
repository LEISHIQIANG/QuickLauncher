from unittest.mock import MagicMock, patch

import pytest

import hooks.hotkey_manager


@pytest.fixture(autouse=True)
def mock_windows():
    with (
        patch("ctypes.windll", MagicMock()),
        patch.dict(
            "sys.modules",
            {
                "win32api": MagicMock(),
                "win32con": MagicMock(),
                "win32ui": MagicMock(),
                "win32gui": MagicMock(),
            },
            clear=False,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _ensure_qapp():
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def manager():
    m = hooks.hotkey_manager.HotkeyManager()
    yield m
    m.stop()


class FakeDll:
    def __init__(self):
        self.calls = []

    def set_hotkey(self, hotkey, callback):
        self.calls.append(("set", hotkey, callback))
        return True

    def clear_hotkey(self):
        self.calls.append("clear")


def test_import_hotkey_manager():
    assert hasattr(hooks.hotkey_manager, "HotkeyManager")


def test_manager_create():
    m = hooks.hotkey_manager.HotkeyManager()
    assert isinstance(m, hooks.hotkey_manager.HotkeyManager)
    assert not m._is_running
    m.stop()


def test_register_hotkey(manager):
    dll = FakeDll()
    manager._dll = dll
    assert manager.set_hotkey("Ctrl+Shift+P")
    assert ("set", "<ctrl>+<shift>+p", manager._on_activated) in dll.calls


def test_unregister_hotkey(manager):
    dll = FakeDll()
    manager._dll = dll
    manager.set_hotkey("Ctrl+P")
    manager.stop()
    assert not manager._is_running
    assert "clear" in dll.calls


def test_register_duplicate(manager):
    dll = FakeDll()
    manager._dll = dll
    manager.set_hotkey("Alt+Space")
    manager.set_hotkey("Ctrl+Shift+P")
    assert ("set", "<alt>+<space>", manager._on_activated) in dll.calls
    assert ("set", "<ctrl>+<shift>+p", manager._on_activated) in dll.calls


def test_clear_all_hotkeys(manager):
    dll = FakeDll()
    manager._dll = dll
    manager.set_hotkey("Ctrl+P")
    manager.stop()
    assert "clear" in dll.calls
    assert not manager._is_running


def test_start_stop(manager):
    assert not manager._is_running
    assert manager.start()
    assert manager._is_running
    manager.stop()
    assert not manager._is_running


def test_callback_invocation(manager):
    results = []
    manager.activated.connect(lambda: results.append("activated"))
    manager.start()
    manager._on_activated()
    manager._drain_pending_activated()
    assert results == ["activated"]


def test_stopped_manager_ignores_late_native_callback(manager):
    results = []
    manager.activated.connect(lambda: results.append("activated"))
    manager.start()
    manager.stop()

    manager._on_activated()
    manager._drain_pending_activated()

    assert results == []
    assert manager._pending_activated == 0


def test_invalid_key_combo(manager):
    assert not manager.set_hotkey("")
    assert not manager.set_hotkey("   ")
    assert not manager.set_hotkey("Ctrl+Alt")
