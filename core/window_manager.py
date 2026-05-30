"""
窗口管理器
"""

import ctypes
import logging
import os

logger = logging.getLogger(__name__)

try:
    import psutil
    import win32con
    import win32gui
    import win32process

    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class WindowManager:
    """窗口管理器"""

    @staticmethod
    def try_activate(exe_path: str, restore_minimized: bool = True) -> bool:
        """尝试激活程序的现有窗口"""
        if not HAS_WIN32:
            return False

        try:
            process_name = os.path.splitext(os.path.basename(exe_path))[0].lower()

            # 1. 复杂度反转：先从桌面上极其有限的可见 top-level 主窗口开始枚举（耗时微秒级）
            visible_windows = []

            def callback(hwnd, lparam):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                            if not (ex_style & win32con.WS_EX_TOOLWINDOW):
                                owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                                if not owner:
                                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                                    visible_windows.append((hwnd, window_pid))
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(callback, None)

            # 2. 对这些主窗口的 PID 进行按需进程名检测（使用字典缓存避免重复查询）
            pid_cache = {}
            for hwnd, pid in visible_windows:
                if pid not in pid_cache:
                    is_match = False
                    try:
                        proc = psutil.Process(pid)
                        pname = proc.name()
                        if pname and pname.lower().replace(".exe", "").startswith(process_name):
                            is_match = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    pid_cache[pid] = is_match

                if pid_cache[pid]:
                    if WindowManager._activate_window(hwnd, restore_minimized):
                        return True

            return False

        except Exception as e:
            logger.debug(f"激活窗口失败: {e}")
            return False

    @staticmethod
    def _get_windows_for_pids(pids: list[int]):
        windows_by_pid = {pid: [] for pid in pids}
        pid_set = set(pids)

        def callback(hwnd, lparam):
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid in pid_set and win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                        if not (ex_style & win32con.WS_EX_TOOLWINDOW):
                            owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                            if not owner:
                                windows_by_pid[window_pid].append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass

        return windows_by_pid

    @staticmethod
    def _get_process_windows(pid: int) -> list[int]:
        """获取进程的所有窗口"""
        windows = []

        def callback(hwnd, lparam):
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid and win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                        if not (ex_style & win32con.WS_EX_TOOLWINDOW):
                            owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                            if not owner:
                                windows.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass

        return windows

    @staticmethod
    def _activate_window(hwnd: int, restore_minimized: bool = True) -> bool:
        """使用 Windows 标准的 SwitchToThisWindow 机制激活窗口。

        这是最稳健的单一方法，它能自动处理：
        1. 最小化窗口的恢复。
        2. 背景窗口的强制置顶。
        3. 模拟用户在任务栏点击的效果，避免闪烁和焦点丢失。
        """
        try:
            if not win32gui.IsWindow(hwnd):
                return False

            # 1. 基础状态准备
            # 如果窗口是隐藏的，必须先显示它
            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            # 如果最小化，且允许恢复，则准备恢复动作
            placement = win32gui.GetWindowPlacement(hwnd)
            is_minimized = placement[1] in (2, 6, 7)

            if is_minimized and not restore_minimized:
                return False

            # 2. 调用系统核心接口 SwitchToThisWindow
            # 这是目前已知最符合系统直觉、且能绕过大多数前台锁定的单一方案
            # 参数: hwnd, fAltTab (True 表示通过 Alt+Tab 切换，具有最强的置顶权限)
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)

            return True

        except Exception as e:
            logger.debug(f"SwitchToThisWindow 激活失败: {e}")
            return False
