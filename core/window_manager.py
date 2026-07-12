"""
窗口管理器 — 委托 QLwindow.dll 原生实现。

QLwindow.dll 是硬依赖，不可用时立即 RuntimeException。
无 Python 回退路径。
"""

from __future__ import annotations

import logging

from core.native_services import _QLWindowEngine

logger = logging.getLogger(__name__)


class WindowManager:
    """窗口管理器"""

    @staticmethod
    def try_activate(exe_path: str, restore_minimized: bool = True) -> bool:
        success, _hwnd = _QLWindowEngine.get().activate(str(exe_path), restore_minimized)
        return success

    @staticmethod
    def _get_windows_for_pids(pids: list[int]):
        return _QLWindowEngine.get().get_windows_for_pids(pids)

    @staticmethod
    def _get_process_windows(pid: int) -> list[int]:
        return _QLWindowEngine.get().get_process_windows(pid)

    @staticmethod
    def _activate_window(hwnd: int, restore_minimized: bool = True) -> bool:
        return _QLWindowEngine.get().activate_hwnd(hwnd, restore_minimized)
