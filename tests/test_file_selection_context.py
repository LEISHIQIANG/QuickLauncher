"""Explorer/Desktop selected-file source resolution regressions."""

import time
from types import SimpleNamespace

import ui.launcher_popup.file_selection as file_selection
import ui.launcher_popup.popup_data_refresh as popup_data_refresh
import ui.launcher_popup.popup_item_execution as popup_item_execution
import ui.launcher_popup.popup_window as popup_window
import ui.launcher_popup.window_detection as window_detection
from core.data_models import ShortcutItem, ShortcutType
from qt_compat import QColor
from ui.launcher_popup.popup_renderer import PopupRendererMixin


class _FakeItem:
    def __init__(self, path):
        self.Path = path


class _FakeSelectedItems:
    def __init__(self, paths):
        self._items = [_FakeItem(path) for path in paths]
        self.Count = len(self._items)

    def __iter__(self):
        return iter(self._items)


class _FakeDocument:
    def __init__(self, paths):
        self._paths = paths

    def SelectedItems(self):
        return _FakeSelectedItems(self._paths)


class _FakeWindow:
    def __init__(self, hwnd, paths):
        self.HWND = hwnd
        self.Document = _FakeDocument(paths)


class _FakeWindows:
    def __init__(self, windows, desktop_window=None):
        self._windows = windows
        self._desktop_window = desktop_window
        self.Count = len(windows)

    def Item(self, index):
        return self._windows[index]

    def FindWindowSW(self, *_args):
        return self._desktop_window


class _FakeShell:
    def __init__(self, windows, desktop_window=None):
        self._windows = _FakeWindows(windows, desktop_window=desktop_window)

    def Windows(self):
        return self._windows


def _install_file_selection_fakes(
    monkeypatch, *, foreground, cursor, roots, desktop_roots, shell_windows, desktop_window=None
):
    monkeypatch.setattr(file_selection, "HAS_WIN32_SHELL", True)
    monkeypatch.setattr(
        file_selection, "win32gui", SimpleNamespace(GetForegroundWindow=lambda: foreground), raising=False
    )
    monkeypatch.setattr(file_selection, "_window_from_point", lambda _x, _y: cursor)
    monkeypatch.setattr(file_selection, "_normalize_window_hwnd", lambda hwnd: roots.get(hwnd, hwnd))
    monkeypatch.setattr(file_selection, "_is_desktop_window", lambda hwnd: roots.get(hwnd, hwnd) in desktop_roots)

    def kind(hwnd):
        root = roots.get(hwnd, hwnd)
        if root in desktop_roots:
            return "desktop"
        if root:
            return "explorer"
        return "other"

    monkeypatch.setattr(file_selection, "_window_selection_kind", kind)
    monkeypatch.setattr(
        file_selection,
        "win32com",
        SimpleNamespace(client=SimpleNamespace(Dispatch=lambda _name: _FakeShell(shell_windows, desktop_window))),
        raising=False,
    )


def _thread_for_context(
    monkeypatch,
    *,
    foreground=11,
    cursor=12,
    roots=None,
    desktop_roots=None,
    shell_windows=None,
    desktop_window=None,
):
    roots = roots or {11: 100, 12: 100}
    desktop_roots = desktop_roots or set()
    shell_windows = shell_windows or [_FakeWindow(11, ["C:/one.txt"])]
    _install_file_selection_fakes(
        monkeypatch,
        foreground=foreground,
        cursor=cursor,
        roots=roots,
        desktop_roots=desktop_roots,
        shell_windows=shell_windows,
        desktop_window=desktop_window,
    )
    context = file_selection.SelectionTriggerContext.capture(
        request_id=1,
        trigger_method="mouse",
        trigger_pos=(50, 50),
    )
    return file_selection.FileSelectionThread(context)


def test_multiple_explorer_windows_use_only_matching_foreground_and_cursor_window(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        shell_windows=[
            _FakeWindow(11, ["C:/front.txt"]),
            _FakeWindow(21, ["C:/other.txt"]),
        ],
        roots={11: 100, 12: 100, 21: 200},
    )

    files, matched_hwnd = thread._get_files()

    assert files == ["C:/front.txt"]
    assert matched_hwnd == 11


def test_desktop_selection_does_not_fallback_when_target_explorer_has_no_selection(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        shell_windows=[
            _FakeWindow(11, []),
            _FakeWindow(31, ["C:/desktop.txt"]),
        ],
        roots={11: 100, 12: 100, 31: 300},
        desktop_roots={300},
    )

    files, matched_hwnd = thread._get_files()

    assert files == []
    assert matched_hwnd == 11
    assert thread.ignore_reason == "no_selected_items"


def test_foreground_explorer_and_cursor_desktop_is_window_mismatch(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        cursor=31,
        shell_windows=[
            _FakeWindow(11, ["C:/front.txt"]),
            _FakeWindow(31, ["C:/desktop.txt"]),
        ],
        roots={11: 100, 31: 300},
        desktop_roots={300},
    )

    assert thread.context.target_root_hwnd == 0
    assert thread.context.ignore_reason == "window_mismatch"
    assert thread._get_files() == ([], 0)


def test_shell_tray_window_is_not_treated_as_explorer(monkeypatch):
    monkeypatch.setattr(window_detection, "HAS_WIN32_SHELL", True)
    monkeypatch.setattr(
        window_detection,
        "win32gui",
        SimpleNamespace(GetClassName=lambda _hwnd: "Shell_TrayWnd"),
        raising=False,
    )

    assert window_detection._is_explorer_like_window(100) is False
    assert window_detection._window_selection_kind(100) == "other"


def test_desktop_selection_is_used_only_when_foreground_and_cursor_are_desktop(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        foreground=31,
        cursor=32,
        shell_windows=[
            _FakeWindow(11, ["C:/front.txt"]),
            _FakeWindow(31, ["C:/desktop.txt"]),
        ],
        roots={11: 100, 31: 300, 32: 301},
        desktop_roots={300, 301},
    )

    files, matched_hwnd = thread._get_files()

    assert files == ["C:/desktop.txt"]
    assert matched_hwnd == 31


def test_desktop_selection_uses_shell_windows_desktop_fallback(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        foreground=31,
        cursor=32,
        shell_windows=[
            _FakeWindow(11, ["C:/front.txt"]),
        ],
        desktop_window=_FakeWindow(31, ["C:/desktop.txt"]),
        roots={11: 100, 31: 300, 32: 301},
        desktop_roots={300, 301},
    )

    files, matched_hwnd = thread._get_files()

    assert files == ["C:/desktop.txt"]
    assert matched_hwnd == 300


def test_empty_selected_item_paths_are_filtered(monkeypatch):
    thread = _thread_for_context(
        monkeypatch,
        shell_windows=[_FakeWindow(11, ["", "C:/valid.txt"])],
    )

    files, matched_hwnd = thread._get_files()

    assert files == ["C:/valid.txt"]
    assert matched_hwnd == 11


def _popup_for_selection():
    popup = popup_window.LauncherPopup.__new__(popup_window.LauncherPopup)
    popup._file_check_seq = 1
    popup._selected_files = ["C:/front.txt"]
    popup._selected_files_status = "ready"
    popup._selected_files_request_hwnd = 100
    popup._selected_files_source_hwnd = 100
    popup._selected_files_captured_at = time.monotonic()
    popup._selected_files_context = SimpleNamespace(request_id=1, target_kind="explorer")
    popup.SELECTED_FILES_CACHE_TTL_SECONDS = 5.0
    popup._request_page_animation_update = lambda: None
    popup.update = lambda: None
    return popup


def test_popup_consumes_ready_selection_cache(monkeypatch):
    popup = _popup_for_selection()
    monkeypatch.setattr(popup_data_refresh, "_is_explorer_like_window", lambda hwnd: hwnd == 100)
    monkeypatch.setattr(popup_data_refresh, "_is_desktop_window", lambda _hwnd: False)

    assert popup_window.LauncherPopup._take_valid_selected_files_for_click(popup) == ["C:/front.txt"]


def test_popup_drops_expired_selection_cache(monkeypatch):
    popup = _popup_for_selection()
    popup._selected_files_captured_at = time.monotonic() - 6.0
    monkeypatch.setattr(popup_data_refresh, "_is_explorer_like_window", lambda hwnd: hwnd == 100)
    monkeypatch.setattr(popup_data_refresh, "_is_desktop_window", lambda _hwnd: False)

    assert popup_window.LauncherPopup._take_valid_selected_files_for_click(popup) == []
    assert popup._selected_files_status == "idle"


def test_selection_expiry_refresh_clears_state_and_repaints_indicator():
    popup = _popup_for_selection()
    popup._selected_files_captured_at = time.monotonic() - 6.0
    repaint_count = []
    popup._request_page_animation_update = lambda: repaint_count.append(True)

    popup_window.LauncherPopup._expire_selected_files_if_current(
        popup,
        request_id=1,
        captured_at=popup._selected_files_captured_at,
    )

    assert popup._selected_files_status == "idle"
    assert popup._selected_files == []
    assert repaint_count == [True]


def test_popup_pending_selection_does_not_wait_and_invalidates_request():
    popup = _popup_for_selection()
    popup._selected_files = []
    popup._selected_files_status = "pending"

    assert popup_window.LauncherPopup._take_valid_selected_files_for_click(popup) == []
    assert popup._file_check_seq == 2
    assert popup._selected_files_status == "idle"


def test_selection_sensitive_command_defers_while_probe_is_pending(monkeypatch):
    popup = popup_window.LauncherPopup.__new__(popup_window.LauncherPopup)
    popup._selected_files_status = "pending"
    scheduled = []
    monkeypatch.setattr(popup_item_execution.QTimer, "singleShot", lambda ms, cb: scheduled.append((ms, cb)))

    item = ShortcutItem(type=ShortcutType.COMMAND, command_type="cmd", command="echo {{selected_file:q}}")

    assert popup_window.LauncherPopup._should_wait_for_selection(popup, item) is True
    assert scheduled and scheduled[0][0] == 35


def test_invalid_selection_context_does_not_start_worker(monkeypatch):
    popup = popup_window.LauncherPopup.__new__(popup_window.LauncherPopup)
    popup._file_check_seq = 0
    popup._selected_files_trigger_pos = (10, 10)
    popup._request_page_animation_update = lambda: None
    popup.update = lambda: None
    context = SimpleNamespace(
        request_id=1,
        target_kind="other",
        target_root_hwnd=0,
        foreground_root_hwnd=100,
        cursor_root_hwnd=100,
        trigger_pos=(10, 10),
        ignore_reason="not_explorer_or_desktop",
        started_at=time.monotonic(),
    )
    monkeypatch.setattr(popup_data_refresh.SelectionTriggerContext, "capture", lambda **_kwargs: context)
    monkeypatch.setattr(
        popup_data_refresh,
        "FileSelectionThread",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker should not start")),
    )

    popup_window.LauncherPopup._start_file_check(popup, hwnd=100)

    assert popup._selected_files_status == "empty"
    assert popup._selected_files == []


def test_indicator_turns_orange_only_for_valid_ready_selection_in_dark_theme():
    widget = SimpleNamespace(
        settings=SimpleNamespace(theme="dark"),
        _selected_files_status="ready",
        _selected_files=["C:/front.txt"],
        _selected_files_captured_at=time.monotonic(),
        SELECTED_FILES_CACHE_TTL_SECONDS=5.0,
    )

    color = PopupRendererMixin._indicator_accent_color(widget, QColor(10, 132, 255))

    assert (color.red(), color.green(), color.blue()) == (255, 159, 10)


def test_indicator_uses_darker_orange_for_light_theme():
    widget = SimpleNamespace(
        settings=SimpleNamespace(theme="light"),
        _selected_files_status="ready",
        _selected_files=["C:/front.txt"],
        _selected_files_captured_at=time.monotonic(),
        SELECTED_FILES_CACHE_TTL_SECONDS=5.0,
    )

    color = PopupRendererMixin._indicator_accent_color(widget, QColor(0, 122, 255))

    assert (color.red(), color.green(), color.blue()) == (201, 92, 0)
