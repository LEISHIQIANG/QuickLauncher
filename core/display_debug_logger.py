"""
显示器和窗口调试日志模块
用于诊断多显示器、不同DPI缩放下的窗口显示问题
"""

import logging
import ctypes
from ctypes import wintypes
import sys

logger = logging.getLogger(__name__)

# Windows API 常量
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD)
    ]


class DisplayDebugLogger:
    """显示器调试日志记录器"""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.shcore = ctypes.windll.shcore
        self.call_count = 0

    def log_all_display_info(self, cursor_x, cursor_y, window_width, window_height, icon_size, cell_size, hwnd=0):
        """记录所有显示相关信息"""
        self.call_count += 1
        separator = "================================================================================"

        logger.info(f"\n{separator}")
        logger.info(f"显示调试事件 #{self.call_count} [触发于中键弹出]")
        logger.info(f"{separator}")

        # 1. 鼠标位置
        self._log_cursor_info(cursor_x, cursor_y)

        # 2. 当前显示器信息 (Windows API)
        monitor_info = self._log_monitor_info(cursor_x, cursor_y)

        # 3. 窗口句柄信息 (如果提供)
        if hwnd:
            self._log_hwnd_info(hwnd)

        # 4. 窗口参数
        self._log_window_params(window_width, window_height, icon_size, cell_size)

        # 5. Qt 逻辑视图
        self._log_qt_info(cursor_x, cursor_y)

        logger.info(f"{separator}\n")
        return monitor_info

    def _log_cursor_info(self, x, y):
        logger.info(f"  [鼠标位置] (X={x}, Y={y})")

    def _log_hwnd_info(self, hwnd):
        """记录底层句柄的 DPI 状况"""
        try:
            dpi = 0
            if hasattr(self.user32, "GetDpiForWindow"):
                dpi = self.user32.GetDpiForWindow(ctypes.wintypes.HWND(hwnd))
            
            logger.info(f"  [HWND 信息] 句柄={hwnd}, 实时 DPI={dpi} (缩放={dpi/96*100:.1f}%)")
            
            # 记录原生窗口矩形
            rect = RECT()
            self.user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
            logger.info(f"    原生物理矩形: ({rect.left}, {rect.top}) -> ({rect.right}, {rect.bottom}) "
                       f"[{rect.right-rect.left}x{rect.bottom-rect.top}]")
        except Exception as e:
            logger.info(f"  [HWND 信息] 获取失败: {e}")

    def _log_monitor_info(self, x, y):
        """记录当前显示器详细信息"""
        try:
            pt = POINT(x, y)
            hMonitor = self.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)

            # 获取显示器信息
            monitor_info = MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
            self.user32.GetMonitorInfoW(hMonitor, ctypes.byref(monitor_info))

            # 获取 DPI
            dpiX = ctypes.c_uint()
            dpiY = ctypes.c_uint()
            try:
                self.shcore.GetDpiForMonitor(hMonitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpiX), ctypes.byref(dpiY))
            except:
                dpiX.value, dpiY.value = 96, 96

            scale = dpiX.value / 96.0

            logger.info(f"  [显示器(WinAPI)]")
            logger.info(f"    DPI: {dpiX.value} (缩放: {scale*100:.0f}%)")
            logger.info(f"    分辨率: {monitor_info.rcMonitor.right - monitor_info.rcMonitor.left}x"
                       f"{monitor_info.rcMonitor.bottom - monitor_info.rcMonitor.top}")
            logger.info(f"    工作区: ({monitor_info.rcWork.left}, {monitor_info.rcWork.top}) -> "
                       f"({monitor_info.rcWork.right}, {monitor_info.rcWork.bottom})")

            return {
                'handle': hMonitor,
                'dpi': dpiX.value,
                'scale': scale
            }
        except Exception as e:
            logger.error(f"  [显示器(WinAPI)] 获取失败: {e}")
            return None

    def _log_window_params(self, width, height, icon_size, cell_size):
        logger.info(f"  [窗口设置值]")
        logger.info(f"    逻辑尺寸: {width}x{height}")
        logger.info(f"    网格尺寸: Cell={cell_size}, Icon={icon_size}")

    def _log_qt_info(self, cursor_x, cursor_y):
        """记录 Qt 视角下的屏幕信息"""
        try:
            from qt_compat import QApplication, QPoint

            logger.info(f"  [Qt 视角]")
            screen = QApplication.screenAt(QPoint(cursor_x, cursor_y))
            if screen:
                logger.info(f"    当前屏幕: {screen.name()}")
                logger.info(f"    设备像素比 (DPR): {screen.devicePixelRatio()}")
                logger.info(f"    逻辑 DPI: {screen.logicalDotsPerInch()}")
                geom = screen.geometry()
                logger.info(f"    Qt 几何区: ({geom.x()}, {geom.y()}) {geom.width()}x{geom.height()}")
            else:
                logger.warning(f"    未找到对应屏幕")

        except Exception as e:
            logger.error(f"  [Qt 视角] 获取失败: {e}")


# 全局实例
_debug_logger = None

def get_display_debug_logger():
    """获取全局日志记录器实例"""
    global _debug_logger
    if _debug_logger is None:
        _debug_logger = DisplayDebugLogger()
    return _debug_logger

