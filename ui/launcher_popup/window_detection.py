"""Explorer 窗口检测工具函数"""

import logging

try:
    import win32gui
    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

logger = logging.getLogger(__name__)

EXPLORER_WINDOW_PROXIMITY_PX = 48
EXPLORER_WINDOW_CLASSES = {"CabinetWClass", "ExploreWClass", "Progman", "WorkerW"}
DESKTOP_WINDOW_CLASSES = {"Progman", "WorkerW"}


def _normalize_window_hwnd(hwnd) -> int:
    try:
        current = int(hwnd or 0)
    except Exception:
        return 0
    if not current or not HAS_WIN32_SHELL:
        return current
    try:
        for _ in range(8):
            parent = win32gui.GetParent(current)
            if not parent or parent == current:
                break
            current = int(parent)
    except Exception:
        pass
    return int(current or 0)


def _get_window_class_name(hwnd) -> str:
    if not HAS_WIN32_SHELL:
        return ""
    try:
        return str(win32gui.GetClassName(int(hwnd or 0)) or "")
    except Exception:
        return ""


def _is_explorer_like_window(hwnd) -> bool:
    class_name = _get_window_class_name(hwnd)
    if not class_name:
        return False
    return class_name in EXPLORER_WINDOW_CLASSES or "Shell" in class_name


def _is_desktop_window(hwnd) -> bool:
    class_name = _get_window_class_name(hwnd)
    if not class_name:
        return False
    return class_name in DESKTOP_WINDOW_CLASSES


def _point_near_window(hwnd, x: int, y: int, margin: int = EXPLORER_WINDOW_PROXIMITY_PX) -> bool:
    if not HAS_WIN32_SHELL:
        return False
    try:
        left, top, right, bottom = win32gui.GetWindowRect(int(hwnd or 0))
    except Exception:
        return False
    margin = max(0, int(margin or 0))
    return (
        (left - margin) <= int(x) <= (right + margin)
        and (top - margin) <= int(y) <= (bottom + margin)
    )
