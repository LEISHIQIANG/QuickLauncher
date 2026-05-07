"""文件选择检测线程"""

import logging
import time

try:
    import win32com.client
    import win32gui
    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import QThread, pyqtSignal
from ui.launcher_popup.window_detection import (
    _normalize_window_hwnd, _is_desktop_window, _is_explorer_like_window, _point_near_window
)

logger = logging.getLogger(__name__)


class FileSelectionThread(QThread):
    """文件选择检测线程"""
    files_found = pyqtSignal(list)

    def __init__(self, target_hwnd=None, request_id: int = 0, request_started_at: float = 0.0, trigger_pos=None):
        super().__init__()
        self.target_hwnd = target_hwnd
        self.request_id = int(request_id or 0)
        self.request_started_at = float(request_started_at or time.monotonic())
        self.requested_root_hwnd = _normalize_window_hwnd(target_hwnd)
        self.matched_hwnd = 0
        self.matched_root_hwnd = 0
        self.captured_at = 0.0
        self.trigger_pos = None
        if trigger_pos and len(trigger_pos) >= 2:
            self.trigger_pos = (int(trigger_pos[0]), int(trigger_pos[1]))

    def run(self):
        if not HAS_WIN32_SHELL:
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
        if found_files:
            self.matched_hwnd = int(matched_hwnd or 0)
            self.matched_root_hwnd = _normalize_window_hwnd(self.matched_hwnd)
            self.captured_at = time.monotonic()
            self.files_found.emit(found_files)

    def _get_files(self):
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            fg_hwnd = self.target_hwnd if self.target_hwnd else win32gui.GetForegroundWindow()
            fg_root = _normalize_window_hwnd(fg_hwnd) or fg_hwnd
            fg_is_desktop = _is_desktop_window(fg_root)
            fg_is_explorer = _is_explorer_like_window(fg_root)

            windows = shell.Windows()
            folder_candidate = None
            desktop_candidate = None

            for i in range(windows.Count):
                try:
                    w = windows.Item(i)
                    w_hwnd = int(getattr(w, "HWND", 0) or 0)
                    root_hwnd = _normalize_window_hwnd(w_hwnd) or w_hwnd
                    selected_items = w.Document.SelectedItems()
                    if selected_items.Count <= 0:
                        continue
                    items = [item.Path for item in selected_items if getattr(item, "Path", "")]
                    if not items:
                        continue
                    if _is_desktop_window(root_hwnd):
                        desktop_candidate = {"files": items, "hwnd": w_hwnd, "root_hwnd": root_hwnd}
                    elif root_hwnd == fg_root or w_hwnd == fg_root:
                        folder_candidate = {"files": items, "hwnd": w_hwnd, "root_hwnd": root_hwnd}
                except Exception:
                    continue

            trigger_pos = self.trigger_pos
            if fg_is_explorer and not fg_is_desktop and trigger_pos:
                in_folder = _point_near_window(fg_root, trigger_pos[0], trigger_pos[1], margin=0)
                if in_folder:
                    if folder_candidate:
                        self.requested_root_hwnd = int(folder_candidate["root_hwnd"])
                        return list(folder_candidate["files"]), int(folder_candidate["hwnd"])
                    return [], 0
                else:
                    if desktop_candidate:
                        self.requested_root_hwnd = int(desktop_candidate["root_hwnd"])
                        return list(desktop_candidate["files"]), int(desktop_candidate["hwnd"])
                    return [], 0

            if folder_candidate and fg_is_explorer and not fg_is_desktop:
                self.requested_root_hwnd = int(folder_candidate["root_hwnd"])
                return list(folder_candidate["files"]), int(folder_candidate["hwnd"])
            if desktop_candidate:
                self.requested_root_hwnd = int(desktop_candidate["root_hwnd"])
                return list(desktop_candidate["files"]), int(desktop_candidate["hwnd"])
        except Exception as e:
            logger.debug(f"获取Explorer选中文件失败: {e}")
        return [], 0
