"""Window control helpers for ShortcutExecutor."""

import logging
from typing import Optional

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

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

logger = logging.getLogger(__name__)
ShortcutExecutor = None


class WindowControlMixin:
    @staticmethod
    def _get_window_at_cursor() -> Optional[int]:
        """获取鼠标位置的顶级窗口句柄
        
        Returns:
            窗口句柄，失败返回 None
        """
        try:
            pt = ShortcutExecutor.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            
            # 获取鼠标所在窗口
            hwnd = user32.WindowFromPoint(pt)
            if not hwnd:
                return None
            
            # 获取顶级父窗口
            GA_ROOT = 2
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
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        return bool(ex_style & WS_EX_TOPMOST)
    @staticmethod
    def _set_topmost(topmost: bool) -> bool:
        """设置置顶状态
        
        Args:
            topmost: True=置顶, False=取消置顶
        
        Returns:
            bool: 是否成功
        """
        try:
            hwnd = None
            
            # 1. 优先尝试使用保存的前台窗口 (Launcher 唤起前的窗口)
            if ShortcutExecutor._previous_hwnd:
                if user32.IsWindow(ShortcutExecutor._previous_hwnd):
                    hwnd = ShortcutExecutor._previous_hwnd
                    logger.debug(f"使用保存的前台窗口: {hwnd}")
            
            # 2. 如果没有保存窗口，回退到鼠标位置
            if not hwnd:
                hwnd = ShortcutExecutor._get_window_at_cursor()
                logger.debug(f"使用鼠标位置窗口: {hwnd}")
                
            if not hwnd:
                logger.warning("未找到目标窗口")
                return False
            
            logger.debug(f"目标窗口: hwnd={hwnd}")
            
            # 常量定义（使用正确的类型）
            HWND_TOPMOST = wintypes.HWND(-1)
            HWND_NOTOPMOST = wintypes.HWND(-2)
            
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            
            target = HWND_TOPMOST if topmost else HWND_NOTOPMOST
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            
            # 转换窗口句柄为正确类型
            hwnd_handle = wintypes.HWND(hwnd)
            
            # 设置置顶状态
            result = user32.SetWindowPos(
                hwnd_handle,
                target,
                0, 0, 0, 0,
                flags
            )
            
            if result:
                status = "已置顶" if topmost else "取消置顶"
                # 验证是否生效
                new_state = ShortcutExecutor._is_topmost(hwnd)
                logger.info(f"{status}: hwnd={hwnd}, 验证状态: {new_state}")
                return True
            else:
                error = ctypes.GetLastError()
                logger.error(f"SetWindowPos 失败, 错误码: {error}")
                return False
            
        except Exception as e:
            logger.error(f"设置置顶失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    @staticmethod
    def _toggle_topmost() -> bool:
        """切换置顶状态
        
        自动判断当前状态：没置顶就置顶，已置顶就取消
        优先操作保存的前台窗口（即唤起 Launcher 前的窗口），
        如果没有保存，则操作鼠标所在的窗口。
        
        Returns:
            bool: 是否成功
        """
        try:
            hwnd = None
            
            # 1. 优先尝试使用保存的前台窗口 (Launcher 唤起前的窗口)
            if ShortcutExecutor._previous_hwnd:
                if user32.IsWindow(ShortcutExecutor._previous_hwnd):
                    hwnd = ShortcutExecutor._previous_hwnd
                    logger.debug(f"使用保存的前台窗口: {hwnd}")
            
            # 2. 如果没有保存窗口，回退到鼠标位置
            if not hwnd:
                hwnd = ShortcutExecutor._get_window_at_cursor()
                logger.debug(f"使用鼠标位置窗口: {hwnd}")
            
            if not hwnd:
                logger.warning("未找到目标窗口")
                return False
            
            # 判断当前是否已置顶
            is_topmost = ShortcutExecutor._is_topmost(hwnd)
            logger.info(f"窗口 hwnd={hwnd} 当前置顶状态: {is_topmost}")
            
            # 常量定义
            HWND_TOPMOST = wintypes.HWND(-1)
            HWND_NOTOPMOST = wintypes.HWND(-2)
            
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            
            # 切换状态
            target = HWND_NOTOPMOST if is_topmost else HWND_TOPMOST
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            
            hwnd_handle = wintypes.HWND(hwnd)
            
            result = user32.SetWindowPos(
                hwnd_handle,
                target,
                0, 0, 0, 0,
                flags
            )
            
            if result:
                new_state = not is_topmost
                status = "已置顶" if new_state else "取消置顶"
                logger.info(f"{status}: hwnd={hwnd}")
                return True
            else:
                error = ctypes.GetLastError()
                logger.error(f"SetWindowPos 失败, 错误码: {error}")
                return False
            
        except Exception as e:
            logger.error(f"切换置顶失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
