"""Startup behavior tests for the bundled screenshot OCR plugin."""

from pathlib import Path

import plugins.screenshot_ocr.main as screenshot_ocr


class _FakeTimer:
    instances = []

    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class _FakeAPI:
    def __init__(self):
        self.commands = []

    def register_builtin_command(self, **definition):
        self.commands.append(definition)


def test_register_delays_helper_probe_until_startup_is_idle(monkeypatch):
    _FakeTimer.instances.clear()
    monkeypatch.setattr(screenshot_ocr, "_runtime_site", lambda: None)
    monkeypatch.setattr(screenshot_ocr.threading, "Timer", _FakeTimer)
    monkeypatch.setattr(
        screenshot_ocr,
        "_warmup_cmd",
        lambda: (_ for _ in ()).throw(AssertionError("warmup must not run during register")),
    )
    api = _FakeAPI()

    screenshot_ocr.register(api)

    assert len(api.commands) == 1
    assert len(_FakeTimer.instances) == 1
    timer = _FakeTimer.instances[0]
    assert timer.interval == 2.0
    assert timer.daemon is True
    assert timer.started is True

    screenshot_ocr.dispose()
    assert timer.cancelled is True


def test_failed_helper_probe_is_cached(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(screenshot_ocr, "_CACHED_HELPER_CMD", None)
    monkeypatch.setattr(screenshot_ocr.sys, "executable", str(tmp_path / "missing-python.exe"))
    monkeypatch.setattr(
        screenshot_ocr,
        "_find_system_python_command",
        lambda: calls.append(True) or [],
    )

    helper = Path(tmp_path / "ocr_runner.py")
    assert screenshot_ocr._find_helper_command(helper) == []
    assert screenshot_ocr._find_helper_command(helper) == []
    assert calls == [True]
