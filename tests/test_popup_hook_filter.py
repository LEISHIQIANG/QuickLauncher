import os
from types import SimpleNamespace

from ui.tray_mixins import popup_mixin


class _FakeUser32:
    def __init__(self, *, foreground=0, cursor=0, roots=None, pids=None, titles=None):
        self.foreground = foreground
        self.cursor = cursor
        self.roots = dict(roots or {})
        self.pids = dict(pids or {})
        self.titles = dict(titles or {})

    def GetAncestor(self, hwnd, _flag):
        return self.roots.get(int(hwnd or 0), int(hwnd or 0))

    def GetForegroundWindow(self):
        return self.foreground

    def WindowFromPoint(self, _point):
        return self.cursor

    def GetWindowThreadProcessId(self, hwnd, pid_ref):
        pid = self.pids.get(int(hwnd or 0), 0)
        try:
            pid_ref.contents.value = pid
        except AttributeError:
            pid_ref._obj.value = pid
        return 1

    def GetWindowTextW(self, hwnd, buffer, length):
        text = self.titles.get(int(hwnd or 0), "")
        buffer.value = text[: max(0, int(length) - 1)]
        return len(buffer.value)


def _patch_user32(monkeypatch, fake_user32):
    monkeypatch.setattr(os, "getpid", lambda: 42)
    monkeypatch.setattr(popup_mixin.ctypes, "windll", SimpleNamespace(user32=fake_user32), raising=False)


def test_command_panel_hook_context_matches_recorded_hwnd(monkeypatch):
    fake_user32 = _FakeUser32(
        foreground=101,
        roots={101: 100, 123: 100},
        pids={100: 42},
    )
    _patch_user32(monkeypatch, fake_user32)

    reason = popup_mixin._own_command_panel_context_reason(10, 20, command_panel_hwnd=123)

    assert reason == "command_panel_foreground"


def test_command_panel_hook_context_falls_back_to_own_window_title(monkeypatch):
    fake_user32 = _FakeUser32(
        cursor=200,
        pids={200: 42},
        titles={200: "QuickLauncher - \u547d\u4ee4\u9762\u677f"},
    )
    _patch_user32(monkeypatch, fake_user32)

    reason = popup_mixin._own_command_panel_context_reason(10, 20)

    assert reason == "command_panel_title_cursor"


def test_command_panel_hook_context_ignores_other_own_windows(monkeypatch):
    fake_user32 = _FakeUser32(
        foreground=300,
        pids={300: 42},
        titles={300: "QuickLauncher"},
    )
    _patch_user32(monkeypatch, fake_user32)

    reason = popup_mixin._own_command_panel_context_reason(10, 20)

    assert reason == ""


def test_middle_click_callback_does_not_emit_popup_for_command_panel(monkeypatch):
    emitted = []

    class _Signal:
        def emit(self, *args):
            emitted.append(args)

    class _Tray(popup_mixin.PopupMixin):
        show_popup_signal = _Signal()

    tray = _Tray()
    tray.show_popup_signal = _Signal()
    tray._command_panel_hwnd = 123
    monkeypatch.setattr(
        popup_mixin,
        "_own_command_panel_context_reason",
        lambda _x, _y, _hwnd: "command_panel_foreground",
    )
    monkeypatch.setattr(popup_mixin, "_is_own_native_dialog_foreground", lambda: False)

    tray._on_middle_click_from_hook(10, 20)

    assert emitted == []
