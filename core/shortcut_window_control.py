"""Window control helpers for ShortcutExecutor."""

import ctypes
import logging
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008

SendInput = user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
SendInput.restype = wintypes.UINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetShellWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = wintypes.BOOL
kernel32.GetCurrentProcessId.restype = wintypes.DWORD

logger = logging.getLogger(__name__)
ShortcutExecutor = None

GA_ROOT = 2
GA_ROOTOWNER = 3
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SHELL_SURFACE_CLASSES = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
}
_TOPMOST_TARGET_UNSET = object()


class WindowControlMixin:
    @staticmethod
    def _get_window_at_cursor() -> int | None:
        """获取鼠标位置的顶级窗口句柄

        Returns:
            窗口句柄，失败返回 None
        """
        try:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))

            # 获取鼠标所在窗口
            hwnd = user32.WindowFromPoint(pt)
            if not hwnd:
                return None

            # 获取顶级父窗口
            root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                hwnd = root_hwnd

            # 排除桌面窗口
            desktop_hwnd = user32.GetDesktopWindow()
            if hwnd == desktop_hwnd:
                logger.debug("目标是桌面窗口，跳过")
                return None

            return hwnd

        except Exception as e:
            logger.error(f"获取鼠标位置窗口失败: {e}")
            return None

    @staticmethod
    def _get_window_title(hwnd: int) -> str:
        """获取窗口标题"""
        try:
            title_buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buffer, 256)
            return title_buffer.value or "(无标题)"
        except Exception as e:
            logger.debug("Failed to get window title for hwnd=%s: %s", hwnd, e)
            return "(未知)"

    @staticmethod
    def _is_topmost(hwnd: int) -> bool:
        """检查窗口是否置顶"""
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        return bool(ex_style & WS_EX_TOPMOST)

    @staticmethod
    def _window_process_id(hwnd: int) -> int:
        try:
            process_id = wintypes.DWORD()
            thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if not thread_id:
                return 0
            return int(process_id.value)
        except (OSError, ValueError, ctypes.ArgumentError) as exc:
            logger.debug("获取窗口进程失败: hwnd=%s error=%s", hwnd, exc)
            return 0

    @staticmethod
    def _get_window_class_name(hwnd: int) -> str:
        try:
            class_buffer = ctypes.create_unicode_buffer(128)
            if user32.GetClassNameW(hwnd, class_buffer, len(class_buffer)):
                return class_buffer.value
        except (OSError, ValueError, ctypes.ArgumentError) as exc:
            logger.debug("获取窗口类名失败: hwnd=%s error=%s", hwnd, exc)
        return ""

    @staticmethod
    def _normalize_topmost_target(
        hwnd: int | None,
        expected_process_id: int = 0,
    ) -> tuple[int, int] | None:
        """Resolve a stable external root-owner window for topmost changes."""
        if not hwnd or not user32.IsWindow(hwnd):
            return None

        if expected_process_id:
            captured_process_id = ShortcutExecutor._window_process_id(hwnd)
            if captured_process_id != expected_process_id:
                logger.warning(
                    "置顶目标句柄已复用: hwnd=%s expected_pid=%s actual_pid=%s",
                    hwnd,
                    expected_process_id,
                    captured_process_id,
                )
                return None

        try:
            root_owner = user32.GetAncestor(hwnd, GA_ROOTOWNER)
            if root_owner and user32.IsWindow(root_owner):
                hwnd = root_owner
        except (OSError, ValueError, ctypes.ArgumentError) as exc:
            logger.debug("解析根所有者窗口失败: hwnd=%s error=%s", hwnd, exc)

        desktop_hwnd = user32.GetDesktopWindow()
        shell_hwnd = user32.GetShellWindow()
        if hwnd in (desktop_hwnd, shell_hwnd):
            logger.debug("置顶目标是桌面或 Shell 窗口，已忽略: hwnd=%s", hwnd)
            return None

        class_name = ShortcutExecutor._get_window_class_name(hwnd)
        if class_name.lower() in SHELL_SURFACE_CLASSES:
            logger.debug("置顶目标是桌面 Shell 表面，已忽略: hwnd=%s class=%s", hwnd, class_name)
            return None

        process_id = ShortcutExecutor._window_process_id(hwnd)
        if not process_id:
            logger.debug("无法确认置顶目标进程，已忽略: hwnd=%s", hwnd)
            return None

        current_process_id = int(kernel32.GetCurrentProcessId())
        if process_id == current_process_id:
            logger.debug("置顶目标属于 QuickLauncher，已忽略: hwnd=%s", hwnd)
            return None
        return int(hwnd), process_id

    @staticmethod
    def _take_topmost_target() -> tuple[int, int] | None:
        """Consume the popup's saved foreground window and resolve one target."""
        lock = getattr(ShortcutExecutor, "_foreground_window_lock", None)
        if lock is not None:
            with lock:
                saved_hwnd = ShortcutExecutor._previous_hwnd
                saved_process_id = int(getattr(ShortcutExecutor, "_previous_hwnd_process_id", 0) or 0)
                ShortcutExecutor._previous_hwnd = None
                ShortcutExecutor._previous_hwnd_process_id = None
        else:
            saved_hwnd = ShortcutExecutor._previous_hwnd
            saved_process_id = int(getattr(ShortcutExecutor, "_previous_hwnd_process_id", 0) or 0)
            ShortcutExecutor._previous_hwnd = None
            if hasattr(ShortcutExecutor, "_previous_hwnd_process_id"):
                ShortcutExecutor._previous_hwnd_process_id = None

        target = ShortcutExecutor._normalize_topmost_target(saved_hwnd, saved_process_id)
        if target is not None:
            logger.debug("使用保存的前台窗口作为置顶目标: hwnd=%s", target[0])
            return target

        cursor_hwnd = ShortcutExecutor._get_window_at_cursor()
        target = ShortcutExecutor._normalize_topmost_target(cursor_hwnd)
        if target is not None:
            logger.debug("使用鼠标位置窗口作为置顶目标: hwnd=%s", target[0])
        return target

    @staticmethod
    def _resolve_topmost_target(target=_TOPMOST_TARGET_UNSET) -> tuple[int, int] | None:
        if target is _TOPMOST_TARGET_UNSET:
            return ShortcutExecutor._take_topmost_target()
        if not target:
            return None
        try:
            hwnd, process_id = target
            return ShortcutExecutor._normalize_topmost_target(int(hwnd), int(process_id))
        except (TypeError, ValueError):
            logger.warning("无效的置顶目标快照: %r", target)
            return None

    @staticmethod
    def _is_same_window(hwnd: int, process_id: int) -> bool:
        if not user32.IsWindow(hwnd):
            return False
        return bool(process_id) and ShortcutExecutor._window_process_id(hwnd) == process_id

    @staticmethod
    def _apply_topmost_state(hwnd: int, process_id: int, topmost: bool) -> bool:
        """Apply and verify a topmost state without activating or showing the window."""
        insert_after = HWND_TOPMOST if topmost else HWND_NOTOPMOST
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE

        for attempt in range(3):
            if not ShortcutExecutor._is_same_window(hwnd, process_id):
                logger.warning("置顶目标已失效或句柄已复用: hwnd=%s", hwnd)
                return False

            if ShortcutExecutor._is_topmost(hwnd) is topmost:
                return True

            result = user32.SetWindowPos(wintypes.HWND(hwnd), insert_after, 0, 0, 0, 0, flags)
            if result and ShortcutExecutor._is_topmost(hwnd) is topmost:
                time.sleep(0.02)
                if ShortcutExecutor._is_same_window(hwnd, process_id) and ShortcutExecutor._is_topmost(hwnd) is topmost:
                    return True

            if attempt < 2:
                time.sleep(0.015)

        error = ctypes.GetLastError()
        actual = ShortcutExecutor._is_topmost(hwnd) if user32.IsWindow(hwnd) else None
        logger.error(
            "窗口置顶状态切换失败: hwnd=%s target=%s actual=%s error=%s",
            hwnd,
            topmost,
            actual,
            error,
        )
        return False

    @staticmethod
    def _set_topmost(topmost: bool, target=_TOPMOST_TARGET_UNSET) -> bool:
        """Set a verified topmost state for a captured external window."""
        try:
            resolved_target = ShortcutExecutor._resolve_topmost_target(target)
            if resolved_target is None:
                logger.warning("未找到可切换置顶状态的外部窗口")
                return False

            hwnd, process_id = resolved_target
            if not ShortcutExecutor._apply_topmost_state(hwnd, process_id, topmost):
                return False

            logger.info(
                "%s: hwnd=%s pid=%s title=%s",
                "已置顶" if topmost else "已取消置顶",
                hwnd,
                process_id,
                ShortcutExecutor._get_window_title(hwnd),
            )
            return True
        except Exception:
            logger.exception("设置窗口置顶状态失败")
            return False

    @staticmethod
    def _toggle_topmost(target=_TOPMOST_TARGET_UNSET) -> bool:
        """Toggle the captured external root window's verified topmost state."""
        try:
            resolved_target = ShortcutExecutor._resolve_topmost_target(target)
            if resolved_target is None:
                logger.warning("未找到可切换置顶状态的外部窗口")
                return False

            hwnd, process_id = resolved_target
            desired_topmost = not ShortcutExecutor._is_topmost(hwnd)
            return ShortcutExecutor._set_topmost(desired_topmost, resolved_target)
        except Exception:
            logger.exception("切换窗口置顶状态失败")
            return False
