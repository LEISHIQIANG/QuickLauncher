import ctypes

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
        self.GetHooksCapabilities = _FakeFunc(0x1F)
        self.GetLastHookError = _FakeFunc(0)
        self.SetSpecialApps = _FakeFunc(None)
        self.ClearSpecialApps = _FakeFunc(None)


def test_hooks_wrapper_reports_version_and_capabilities(monkeypatch):
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    dll = hooks_wrapper.HooksDLL("fake.dll")
    diagnostics = dll.get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is True
    assert diagnostics["version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION
    assert diagnostics["capabilities"] == 0x1F


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
