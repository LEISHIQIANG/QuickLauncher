import ctypes
import hashlib

from hooks import hooks_wrapper


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
        self.GetHooksCapabilities = _FakeFunc(0x3F)
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
    assert diagnostics["capabilities"] == 0x3F
    assert diagnostics["has_hook_health"] is True
    assert diagnostics["mouse_hook_installed"] is True
    assert diagnostics["keyboard_hook_installed"] is False


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
