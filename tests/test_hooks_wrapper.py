import ctypes
import hashlib
import os

import pytest

from hooks import hooks_wrapper
from hooks.key_map import KEY_TO_VK


class _FakeFunc:
    def __init__(self, result=None):
        self.result = result
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.result


class _FakeDLL:
    def __init__(self):
        for name in hooks_wrapper.HooksDLL.REQUIRED_EXPORTS:
            setattr(self, name, _FakeFunc(True))
        self.GetHooksVersion = _FakeFunc(hooks_wrapper.HooksDLL.EXPECTED_VERSION)
        self.GetHooksCapabilities = _FakeFunc(0x7F)
        self.GetLastHookError = _FakeFunc(0)
        self.IsMouseHookInstalled = _FakeFunc(True)
        self.IsKeyboardHookInstalled = _FakeFunc(False)
        self.SetSpecialApps = _FakeFunc(None)
        self.ClearSpecialApps = _FakeFunc(None)


def test_hooks_wrapper_reports_version_and_capabilities(monkeypatch):
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    dll = hooks_wrapper.HooksDLL("fake.dll")
    diagnostics = dll.get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is True
    assert diagnostics["version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION
    assert diagnostics["capabilities"] == 0x7F
    assert diagnostics["has_hook_health"] is True
    assert diagnostics["has_hotkey_capture"] is True
    assert diagnostics["mouse_hook_installed"] is True
    assert diagnostics["keyboard_hook_installed"] is False


def test_hooks_wrapper_binds_hotkey_capture_exports(monkeypatch):
    class _StartCaptureFunc(_FakeFunc):
        def __init__(self, owner):
            super().__init__(True)
            self.owner = owner

        def __call__(self, callback, timeout_ms):
            self.owner.start_calls.append((callback, timeout_ms))
            return True

    class _StopCaptureFunc(_FakeFunc):
        def __init__(self, owner):
            super().__init__(None)
            self.owner = owner

        def __call__(self):
            self.owner.stopped = True
            return None

    class CaptureDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            self.start_calls = []
            self.stopped = False
            self.active = True
            self.StartHotkeyCapture = _StartCaptureFunc(self)
            self.StopHotkeyCapture = _StopCaptureFunc(self)
            self.IsHotkeyCaptureActive = _FakeFunc(True)

    fake = CaptureDLL()
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)

    dll = hooks_wrapper.HooksDLL("capture.dll")

    assert dll.get_diagnostics()["has_hotkey_capture"] is True
    assert dll.start_hotkey_capture(lambda vk, mods, sides: None, timeout_ms=1234) is True
    assert fake.start_calls and fake.start_calls[-1][1] == 1234
    assert dll.is_hotkey_capture_active() is True

    dll.stop_hotkey_capture()
    assert fake.stopped is True


def test_hooks_wrapper_tolerates_older_dll_without_health_exports(monkeypatch):
    class LegacyDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            del self.IsMouseHookInstalled
            del self.IsKeyboardHookInstalled

    monkeypatch.setattr(ctypes, "CDLL", lambda path: LegacyDLL())

    diagnostics = hooks_wrapper.HooksDLL("legacy.dll").get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is True
    assert diagnostics["has_hook_health"] is False
    assert diagnostics["mouse_hook_installed"] is False
    assert diagnostics["keyboard_hook_installed"] is False


def test_hooks_wrapper_handles_load_failure(monkeypatch):
    def fail(path):
        raise OSError("missing")

    monkeypatch.setattr(ctypes, "CDLL", fail)

    dll = hooks_wrapper.HooksDLL("missing.dll")

    assert dll.install_mouse_hook(lambda x, y: None) is False
    assert dll.get_diagnostics()["loaded"] is False


def test_hooks_wrapper_reports_outdated_version(monkeypatch):
    class OutdatedDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            self.GetHooksVersion = _FakeFunc(hooks_wrapper.HooksDLL.EXPECTED_VERSION - 1)

    monkeypatch.setattr(ctypes, "CDLL", lambda path: OutdatedDLL())

    diagnostics = hooks_wrapper.HooksDLL("old.dll").get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is False
    assert diagnostics["expected_version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION


def test_hooks_wrapper_reports_file_metadata(monkeypatch, tmp_path):
    dll_path = tmp_path / "hooks.dll"
    content = b"fake dll"
    dll_path.write_bytes(content)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    diagnostics = hooks_wrapper.HooksDLL(str(dll_path)).get_diagnostics()

    assert diagnostics["exists"] is True
    assert diagnostics["size_bytes"] == len(content)
    assert diagnostics["sha256"] == hashlib.sha256(content).hexdigest()
    assert diagnostics["path_resolved"].endswith("hooks.dll")


def test_hooks_wrapper_uses_shared_key_map():
    assert hooks_wrapper.HooksDLL._key_to_vk("VolumeUp") == 0xAF
    assert hooks_wrapper.HooksDLL._key_to_vk("PgDn") == 0x22


def test_dll_global_hotkey_parser_accepts_shared_key_map():
    dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hooks", "hooks.dll"))
    if not os.path.exists(dll_path):
        pytest.skip("hooks.dll is not available")

    dll = hooks_wrapper.HooksDLL(dll_path)
    if not dll.loaded or not dll.compatible:
        pytest.skip(f"hooks.dll unavailable: {dll.load_error or dll.missing_exports}")

    callback = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)
    rejected = [
        key
        for key in sorted(KEY_TO_VK)
        if not dll.dll.SetGlobalHotkey(f"ctrl+{key}".encode(), callback)
    ]
    dll.dll.ClearGlobalHotkey()

    assert rejected == []
