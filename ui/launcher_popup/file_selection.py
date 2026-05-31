"""文件选择检测线程"""

# ruff: noqa: I001

import logging
import os
import sys
import time
from dataclasses import dataclass

try:
    import win32com.client
    import win32gui

    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import QThread, pyqtSignal
from core.window_detection import (
    _normalize_window_hwnd,
    _is_desktop_window,
    _window_from_point,
    _window_selection_kind,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectionTriggerContext:
    """Immutable snapshot used to bind selected files to the triggering window."""

    request_id: int = 0
    trigger_method: str = "mouse"
    trigger_pos: tuple[int, int] | None = None
    foreground_hwnd: int = 0
    foreground_root_hwnd: int = 0
    cursor_hwnd: int = 0
    cursor_root_hwnd: int = 0
    target_root_hwnd: int = 0
    target_kind: str = "none"
    started_at: float = 0.0
    ignore_reason: str = ""

    @classmethod
    def capture(
        cls,
        request_id: int,
        trigger_method: str = "mouse",
        trigger_pos=None,
        foreground_hwnd: int | None = None,
        started_at: float | None = None,
    ) -> "SelectionTriggerContext":
        started = float(started_at if started_at is not None else time.monotonic())
        method = (trigger_method or "mouse").strip().lower()
        pos = _coerce_pos(trigger_pos)

        if not HAS_WIN32_SHELL:
            return cls(
                request_id=int(request_id or 0),
                trigger_method=method,
                trigger_pos=pos,
                started_at=started,
                ignore_reason="not_explorer_or_desktop",
            )

        fg_hwnd = int(foreground_hwnd or 0)
        if not fg_hwnd:
            try:
                fg_hwnd = int(win32gui.GetForegroundWindow() or 0)
            except Exception:
                fg_hwnd = 0
        fg_root = _normalize_window_hwnd(fg_hwnd)

        cursor_hwnd = 0
        cursor_root = 0
        target_root = 0
        target_kind = "none"
        ignore_reason = ""

        if method == "mouse" and pos is not None:
            cursor_hwnd = _window_from_point(pos[0], pos[1])
            cursor_root = _normalize_window_hwnd(cursor_hwnd)
            same_window = fg_root and cursor_root and fg_root == cursor_root
            same_desktop = fg_root and cursor_root and _is_desktop_window(fg_root) and _is_desktop_window(cursor_root)
            if same_window or same_desktop:
                target_root = fg_root
            else:
                ignore_reason = "window_mismatch"
        else:
            target_root = fg_root

        if target_root:
            target_kind = _window_selection_kind(target_root)
            if target_kind not in {"explorer", "desktop"}:
                ignore_reason = "not_explorer_or_desktop"
                target_root = 0
        elif not ignore_reason:
            ignore_reason = "not_explorer_or_desktop"

        return cls(
            request_id=int(request_id or 0),
            trigger_method=method,
            trigger_pos=pos,
            foreground_hwnd=fg_hwnd,
            foreground_root_hwnd=fg_root,
            cursor_hwnd=cursor_hwnd,
            cursor_root_hwnd=cursor_root,
            target_root_hwnd=target_root,
            target_kind=target_kind,
            started_at=started,
            ignore_reason=ignore_reason,
        )


def _coerce_pos(trigger_pos) -> tuple[int, int] | None:
    if trigger_pos and len(trigger_pos) >= 2:
        return (int(trigger_pos[0]), int(trigger_pos[1]))
    return None


def _selected_item_paths(selected_items) -> list[str]:
    paths = []
    try:
        iterator = iter(selected_items)
    except Exception:
        iterator = None

    if iterator is not None:
        for item in iterator:
            path = str(getattr(item, "Path", "") or "")
            if path:
                paths.append(path)
        return paths

    try:
        count = int(getattr(selected_items, "Count", 0) or 0)
    except Exception:
        count = 0
    for idx in range(count):
        try:
            item = selected_items.Item(idx)
        except Exception:
            continue
        path = str(getattr(item, "Path", "") or "")
        if path:
            paths.append(path)
    return paths


def _desktop_dispatch_from_shell_windows(shell_windows):
    """Return the Desktop shell dispatch when it is not present in Windows()."""
    try:
        # ShellWindowTypeConstants.SWC_DESKTOP = 8
        # ShellWindowFindWindowOptions.SWFO_NEEDDISPATCH = 1
        return shell_windows.FindWindowSW(0, 0, 8, 0, 1)
    except Exception:
        return None


class FileSelectionThread(QThread):
    """文件选择检测线程"""

    files_found = pyqtSignal(list)

    def __init__(
        self,
        context: SelectionTriggerContext | None = None,
        target_hwnd=None,
        request_id: int = 0,
        request_started_at: float = 0.0,
        trigger_pos=None,
        trigger_method: str = "mouse",
    ):
        super().__init__()
        if isinstance(context, SelectionTriggerContext):
            self.context = context
        else:
            if context is not None and target_hwnd is None:
                target_hwnd = context
            self.context = SelectionTriggerContext.capture(
                request_id=int(request_id or 0),
                trigger_method=trigger_method,
                trigger_pos=trigger_pos,
                foreground_hwnd=target_hwnd,
                started_at=float(request_started_at or time.monotonic()),
            )

        self.target_hwnd = self.context.foreground_hwnd
        self.request_id = self.context.request_id
        self.request_started_at = self.context.started_at
        self.requested_root_hwnd = self.context.target_root_hwnd
        self.matched_hwnd = 0
        self.matched_root_hwnd = 0
        self.captured_at = 0.0
        self.trigger_pos = self.context.trigger_pos
        self.target_kind = self.context.target_kind
        self.ignore_reason = self.context.ignore_reason

    def run(self):
        if not HAS_WIN32_SHELL:
            self.ignore_reason = "not_explorer_or_desktop"
            self.captured_at = time.monotonic()
            self.files_found.emit([])
            return
        found_files = []
        matched_hwnd = 0
        try:
            import pythoncom

            pythoncom.CoInitialize()
            try:
                found_files, matched_hwnd = self._get_files()
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug(f"FileSelectionThread error: {e}")
            self.ignore_reason = self.ignore_reason or "no_selected_items"

        self.matched_hwnd = int(matched_hwnd or 0)
        self.matched_root_hwnd = _normalize_window_hwnd(self.matched_hwnd)
        self.captured_at = time.monotonic()
        self.files_found.emit(found_files)

    def _get_files(self):
        try:
            if not self.context.target_root_hwnd or self.context.target_kind not in {"explorer", "desktop"}:
                self.ignore_reason = self.context.ignore_reason or "not_explorer_or_desktop"
                return [], 0

            shell = win32com.client.Dispatch("Shell.Application")
            target_root = int(self.context.target_root_hwnd or 0)
            target_kind = self.context.target_kind

            windows = shell.Windows()

            for i in range(windows.Count):
                try:
                    w = windows.Item(i)
                    w_hwnd = int(getattr(w, "HWND", 0) or 0)
                    root_hwnd = _normalize_window_hwnd(w_hwnd) or w_hwnd
                    if target_kind == "desktop":
                        is_target = _is_desktop_window(root_hwnd)
                    else:
                        is_target = root_hwnd == target_root or w_hwnd == target_root
                    if not is_target:
                        continue

                    selected_items = w.Document.SelectedItems()
                    selected_count = int(getattr(selected_items, "Count", 0) or 0)
                    if selected_count <= 0:
                        self.ignore_reason = "no_selected_items"
                        return [], w_hwnd
                    items = _selected_item_paths(selected_items)
                    if not items:
                        self.ignore_reason = "empty_path_items"
                        return [], w_hwnd
                    self.ignore_reason = ""
                    self.requested_root_hwnd = target_root
                    return list(items), int(w_hwnd)
                except Exception:
                    continue

            if target_kind == "desktop":
                desktop = _desktop_dispatch_from_shell_windows(windows)
                if desktop is not None:
                    try:
                        selected_items = desktop.Document.SelectedItems()
                        selected_count = int(getattr(selected_items, "Count", 0) or 0)
                        if selected_count <= 0:
                            self.ignore_reason = "no_selected_items"
                            return [], target_root
                        items = _selected_item_paths(selected_items)
                        if not items:
                            self.ignore_reason = "empty_path_items"
                            return [], target_root
                        self.ignore_reason = ""
                        self.requested_root_hwnd = target_root
                        return list(items), target_root
                    except Exception as e:
                        logger.debug("desktop selection fallback failed: %s", e)

            self.ignore_reason = "no_selected_items"
        except Exception as e:
            logger.debug(f"获取Explorer选中文件失败: {e}")
            self.ignore_reason = self.ignore_reason or "no_selected_items"
        return [], 0


def get_selected_files_for_process() -> list[str]:
    """Retrieve selected files using cached values in LauncherPopup,
    or falling back to direct Explorer inspection if no popup is active/cached.
    """
    try:
        from qt_compat import QApplication
        from ui.launcher_popup.popup_window import LauncherPopup

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, LauncherPopup) and widget.isVisible():
                files = getattr(widget, "_selected_files", None)
                if files:
                    return list(files)
    except Exception as exc:
        logger.debug("从弹窗获取选中文件失败: %s", exc, exc_info=True)

    if not HAS_WIN32_SHELL:
        return []

    try:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                return []

            root_hwnd = _normalize_window_hwnd(fg_hwnd) or fg_hwnd
            target_kind = _window_selection_kind(root_hwnd)
            if target_kind not in {"explorer", "desktop"}:
                return []

            shell = win32com.client.Dispatch("Shell.Application")
            windows = shell.Windows()
            for i in range(windows.Count):
                try:
                    w = windows.Item(i)
                    w_hwnd = int(getattr(w, "HWND", 0) or 0)
                    w_root_hwnd = _normalize_window_hwnd(w_hwnd) or w_hwnd
                    if target_kind == "desktop":
                        is_target = _is_desktop_window(w_root_hwnd)
                    else:
                        is_target = w_root_hwnd == root_hwnd or w_hwnd == root_hwnd

                    if is_target:
                        selected_items = w.Document.SelectedItems()
                        return _selected_item_paths(selected_items)
                except Exception:
                    continue
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:
        logger.debug("通过COM获取选中文件失败: %s", exc, exc_info=True)
    return []
