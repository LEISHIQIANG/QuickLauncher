"""Core-level file selection via Explorer shell inspection.

Provides get_selected_files_for_process() without depending on Qt or UI layer.
The UI layer may enhance this by checking active LauncherPopup widgets first.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import win32com.client
    import win32gui

    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

try:
    from core.window_detection import (
        _is_desktop_window,
        _normalize_window_hwnd,
        _window_selection_kind,
    )
except Exception:  # noqa: BLE001
    logger.debug("Failed to import window_detection", exc_info=True)
    HAS_WIN32_SHELL = False


def _selected_item_paths(selected_items) -> list[str]:
    """Extract file paths from Explorer SelectedItems collection."""
    paths: list[str] = []
    try:
        count = selected_items.Count
    except Exception:
        logger.debug("Failed to get SelectedItems count", exc_info=True)
        return paths
    for i in range(count):
        try:
            path = selected_items.Item(i).Path
            if path:
                paths.append(path)
        except Exception:
            logger.debug("Failed to get path for item %s", i, exc_info=True)
            continue
    return paths


def get_selected_files_for_process() -> list[str]:
    """Retrieve selected files from the active Explorer window.

    This is the shell-only fallback — no Qt or UI dependency.
    """
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
                    logger.debug("Failed to inspect Explorer window", exc_info=True)
                    continue
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        logger.debug("获取文件选择路径失败", exc_info=True)
    return []
