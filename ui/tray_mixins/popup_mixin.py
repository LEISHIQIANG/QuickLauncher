"""
弹窗管理、坐标转换、多开相关方法。
"""

import ctypes
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_COMMAND_PANEL_WINDOW_TITLES = ("命令面板", "Command Panel")


def _root_hwnd(user32, hwnd: int) -> int:
    try:
        hwnd = int(hwnd or 0)
        if not hwnd:
            return 0
        return int(user32.GetAncestor(hwnd, 2) or hwnd)  # GA_ROOT
    except Exception:
        logger.debug("_root_hwnd failed", exc_info=True)
        return int(hwnd or 0)


def _window_pid(user32, hwnd: int) -> int:
    try:
        from ctypes import wintypes

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(int(hwnd or 0), ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        logger.debug("_window_pid failed", exc_info=True)
        return 0


def _window_title(user32, hwnd: int) -> str:
    try:
        title_buf = ctypes.create_unicode_buffer(192)
        user32.GetWindowTextW(int(hwnd or 0), title_buf, len(title_buf))
        return title_buf.value or ""
    except Exception:
        logger.debug("_window_title failed", exc_info=True)
        return ""


def _window_from_point(user32, x: int, y: int) -> int:
    try:
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        return int(user32.WindowFromPoint(POINT(int(x), int(y))) or 0)
    except Exception:
        logger.debug("_window_from_point failed", exc_info=True)
        return 0


def _own_command_panel_context_reason(x: int, y: int, command_panel_hwnd: int = 0) -> str:
    """
    Detect middle-click hook callbacks that originate from the independent
    command panel. Packaged builds can report a transient middle-button event
    while the frameless command panel is being dragged across monitors; handling
    that callback would briefly summon the launcher popup.
    """
    try:
        import os

        user32 = ctypes.windll.user32
        own_pid = os.getpid()
        target_root = _root_hwnd(user32, int(command_panel_hwnd or 0))
        if target_root and _window_pid(user32, target_root) != own_pid:
            target_root = 0

        candidates = (("cursor", _window_from_point(user32, x, y)),)
        for label, hwnd in candidates:
            root = _root_hwnd(user32, hwnd)
            if not root:
                continue
            if target_root and root == target_root:
                return f"command_panel_{label}"
            if _window_pid(user32, root) != own_pid:
                continue
            title = _window_title(user32, root)
            if any(marker in title for marker in _COMMAND_PANEL_WINDOW_TITLES):
                return f"command_panel_title_{label}"
    except Exception as exc:
        logger.debug("检查命令面板窗口上下文失败: %s", exc, exc_info=True)
    return ""


def _describe_window_at_point(x: int, y: int) -> str:
    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        def describe(hwnd) -> str:
            if not hwnd:
                return "hwnd=0"
            root = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
            class_buf = ctypes.create_unicode_buffer(128)
            title_buf = ctypes.create_unicode_buffer(192)
            user32.GetClassNameW(root, class_buf, len(class_buf))
            user32.GetWindowTextW(root, title_buf, len(title_buf))
            return f"hwnd=0x{int(root):x} pid={pid.value} " f"class={class_buf.value!r} title={title_buf.value!r}"

        pt = POINT(int(x), int(y))
        foreground = user32.GetForegroundWindow()
        cursor_hwnd = user32.WindowFromPoint(pt)
        mb_state = user32.GetAsyncKeyState(0x04) & 0xFFFF
        return f"mb_async=0x{mb_state:04x} fg={{{describe(foreground)}}} cursor={{{describe(cursor_hwnd)}}}"
    except Exception as exc:
        return f"window_context_error={exc!r}"


def _is_own_native_dialog_foreground() -> bool:
    """Return True while a Windows native dialog created by this process is active."""
    try:
        import os
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        root = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
        if int(pid.value) != os.getpid():
            return False

        class_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(root, class_buf, len(class_buf))
        return class_buf.value == "#32770"
    except Exception:
        logger.debug("_is_own_native_dialog_foreground failed", exc_info=True)
        return False


class PopupMixin:
    """弹窗管理、坐标转换、多开相关方法。"""

    popup_window: Any
    _extra_popup_windows: list[Any]

    def _on_middle_click_from_hook(self, x: int, y: int):
        """从钩子线程接收中键点击（在钩子线程中调用）"""
        # 使用Windows API直接获取鼠标位置，避免DPI转换问题
        try:

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            x, y = pt.x, pt.y
        except Exception as exc:
            logger.debug("获取光标位置失败: %s", exc, exc_info=True)

        paused_state = False
        if hasattr(self, "mouse_hook") and self.mouse_hook:
            try:
                paused_state = self.mouse_hook.is_paused()
            except Exception as exc:
                logger.debug("检查鼠标钩子暂停状态失败: %s", exc, exc_info=True)

        # 如果当前鼠标钩子已被设为暂停，则100%拒绝在主线程分发信号与呼起弹窗，提供双重生命周期安全屏障
        if paused_state:
            logger.info("HOOK_CALLBACK_IGNORED hook_paused pos=(%s,%s)", x, y)
            return

        logger.info("HOOK_CALLBACK_DETAIL pos=(%s,%s)", x, y)

        command_panel_reason = _own_command_panel_context_reason(
            x,
            y,
            getattr(self, "_command_panel_hwnd", 0),
        )
        if command_panel_reason:
            logger.info("HOOK_CALLBACK_IGNORED %s pos=(%s,%s)", command_panel_reason, x, y)
            return

        if _is_own_native_dialog_foreground():
            logger.info("HOOK_CALLBACK_IGNORED own_native_dialog pos=(%s,%s)", x, y)
            return

        # 简单的防抖动 (Debounce)
        current_time = time.monotonic()
        if hasattr(self, "_last_click_time") and (current_time - self._last_click_time < 0.05):  # type: ignore[has-type]
            logger.debug("点击过快，已忽略")
            return
        self._last_click_time = current_time

        # 通过信号传递到主线程
        self.show_popup_signal.emit(x, y)  # type: ignore[attr-defined]

    def _on_show_popup(self, x: int, y: int):
        """显示弹出窗口（在主线程中执行）"""
        if self._wake_from_sleep("middle_click"):  # type: ignore[attr-defined]
            return
        current_time = time.monotonic()
        if hasattr(self, "_last_show_popup_time") and (current_time - self._last_show_popup_time < 0.3):  # type: ignore[has-type]
            return
        self._last_show_popup_time = current_time
        selection_trigger_pos = (int(x), int(y))
        x, y = self._normalize_popup_pos(x, y)
        logger.info(
            "HOOK_SHOW_CONTEXT pos=(%s,%s) %s",
            selection_trigger_pos[0],
            selection_trigger_pos[1],
            _describe_window_at_point(selection_trigger_pos[0], selection_trigger_pos[1]),
        )
        logger.info(f"显示弹出窗口: qt=({x}, {y}) win={selection_trigger_pos}")
        popup_start = time.perf_counter()

        from ui.tray_app import _get_shortcut_executor

        try:
            _get_shortcut_executor().save_foreground_window()
        except Exception as exc:
            logger.debug("保存前台窗口失败: %s", exc, exc_info=True)

        self._has_shown_popup = True
        try:
            if self._deferred_startup_timer and self._deferred_startup_timer.isActive():  # type: ignore[attr-defined]
                self._deferred_startup_timer.stop()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("停止延迟启动定时器失败: %s", exc, exc_info=True)

        if not self._icon_preload_started:  # type: ignore[attr-defined]
            from qt_compat import QTimer

            QTimer.singleShot(0, self._preload_icons)  # type: ignore[attr-defined]

        try:
            self._prune_extra_popup_windows()
            if self.popup_window:
                if self.popup_window.isVisible():
                    from qt_compat import QApplication, QPoint

                    current_screen = QApplication.screenAt(QPoint(x, y))
                    window_screen = QApplication.screenAt(self.popup_window.pos())

                    if current_screen == window_screen:
                        if self._should_multi_open_pinned_popup(self.popup_window):
                            self._keep_as_extra_popup(self.popup_window)
                            self.popup_window = None
                        else:
                            self.popup_window.hide()
                            return

                if self.popup_window is not None:
                    try:
                        _ = self.popup_window.width()
                    except RuntimeError:
                        self.popup_window = None

            if self.popup_window:
                self.popup_window.refresh_data(
                    x,
                    y,
                    selection_trigger_pos=selection_trigger_pos,
                    trigger_method="mouse",
                )
                self.popup_window.preload_visible_icons(force=True, all_pages=True)
                self.popup_window.prepare_first_show()
                if not self.popup_window._prepare_selected_background():
                    return
                self.popup_window.show()
                self.popup_window.activateWindow()
                self.popup_window.raise_()
                logger.info("弹出窗口已复用并显示，耗时 %.1f ms", (time.perf_counter() - popup_start) * 1000)
            else:
                from ui.launcher_popup import LauncherPopup

                self.popup_window = LauncherPopup(
                    self.data_manager,  # type: ignore[attr-defined]
                    x,
                    y,
                    self,
                    selection_trigger_pos=selection_trigger_pos,
                    trigger_method="mouse",
                )
                self.popup_window.preload_background()
                self.popup_window.preload_visible_icons(force=True, all_pages=True)
                self.popup_window.prepare_first_show()
                if not self.popup_window._prepare_selected_background():
                    return
                self.popup_window.show()
                self.popup_window.activateWindow()
                self.popup_window.raise_()
                logger.info("弹出窗口已创建并显示，耗时 %.1f ms", (time.perf_counter() - popup_start) * 1000)

        except Exception:
            logger.exception("显示弹出窗口失败")

    def _should_multi_open_pinned_popup(self, popup) -> bool:
        try:
            if not popup or not popup.isVisible() or not bool(getattr(popup, "is_pinned", False)):
                return False
            settings = self.data_manager.get_settings()  # type: ignore[attr-defined]
            return bool(getattr(settings, "popup_multi_open_when_pinned", False))
        except Exception:
            logger.debug("_should_multi_open_pinned_popup failed", exc_info=True)
            return False

    def _keep_as_extra_popup(self, popup):
        try:
            if popup and popup not in self._extra_popup_windows:
                self._extra_popup_windows.append(popup)
                self._trim_extra_popup_windows()
                logger.debug("固定弹窗已保留，当前保留数量: %d", len(self._extra_popup_windows))
        except Exception as exc:
            logger.debug("保留额外弹窗失败: %s", exc, exc_info=True)

    def _trim_extra_popup_windows(self):
        max_extra = max(0, int(getattr(self, "_max_extra_popup_windows", 2) or 0))
        while len(self._extra_popup_windows) > max_extra:
            old_popup = self._extra_popup_windows.pop(0)
            try:
                old_popup.close()
                old_popup.deleteLater()
            except Exception:
                try:
                    old_popup.hide()
                except Exception as exc:
                    logger.debug("隐藏旧弹窗失败: %s", exc, exc_info=True)

    def _prune_extra_popup_windows(self):
        kept = []
        for popup in list(getattr(self, "_extra_popup_windows", []) or []):
            try:
                _ = popup.width()
                kept.append(popup)
            except RuntimeError:
                logger.debug("检查弹窗宽度失败(C++对象已销毁)", exc_info=True)
            except Exception:
                kept.append(popup)
        self._extra_popup_windows = kept
        self._trim_extra_popup_windows()

    def _normalize_popup_pos(self, x: int, y: int):
        """把鼠标回调中的物理像素归一化为"项目坐标"。

        委托给 :func:`ui.utils.coordinate_utils.normalize_caret_position`，
        避免在多处出现相同的转换逻辑（曾经散落在 ``_try_convert_win_physical_to_qt``、
        ``_center_to`` 和 ``SetWindowPos`` 三处，互不一致）。
        """
        from ui.utils.coordinate_utils import normalize_caret_position

        return normalize_caret_position(int(x), int(y))
