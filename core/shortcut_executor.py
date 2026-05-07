"""
快捷方式执行器
"""

from __future__ import annotations

import os
import subprocess
import ctypes
from ctypes import wintypes
import time
import logging
import threading
import webbrowser
import shlex
import sys
import win32process
from typing import Optional, List

from .data_models import ShortcutItem, ShortcutType
from .windows_uipi import is_process_elevated
from .shortcut_hotkey import HotkeyExecutionMixin
from .shortcut_file_exec import FileExecutionMixin
from .shortcut_url_exec import UrlExecutionMixin
from .shortcut_command_exec import CommandExecutionMixin
from .shortcut_window_control import WindowControlMixin

logger = logging.getLogger(__name__)
STANDARD_USER_LAUNCH_FAILED_MESSAGE = (
    "QuickLauncher 当前以管理员权限运行，且降权启动失败。"
    "请先以普通权限启动 QuickLauncher，或为该项目显式勾选“以管理员身份运行”。"
)

# 尝试导入窗口管理器
try:
    from .window_manager import WindowManager
    HAS_WINDOW_MANAGER = True
except ImportError:
    HAS_WINDOW_MANAGER = False

# 尝试导入 pynput 键盘控制
try:
    from pynput.keyboard import Key, Controller as KeyboardController
    HAS_PYNPUT = True
    keyboard = KeyboardController()
except ImportError:
    HAS_PYNPUT = False
    keyboard = None
    logger.warning("pynput 未安装，快捷键功能受限")

# ===== 配置 user32 函数签名 =====
user32 = ctypes.windll.user32
SendInput = user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
SendInput.restype = wintypes.UINT

# SetWindowPos 参数类型
user32.SetWindowPos.argtypes = [
    wintypes.HWND,   # hWnd
    wintypes.HWND,   # hWndInsertAfter
    ctypes.c_int,    # X
    ctypes.c_int,    # Y
    ctypes.c_int,    # cx
    ctypes.c_int,    # cy
    ctypes.c_uint,   # uFlags
]
user32.SetWindowPos.restype = wintypes.BOOL

# IsWindow - 检查窗口句柄是否有效
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

# GetDesktopWindow - 获取桌面窗口句柄
user32.GetDesktopWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND

# FindWindowW - 查找窗口
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

shell32 = ctypes.windll.shell32
shell32.ShellExecuteW.argtypes = [
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_int,
]
shell32.ShellExecuteW.restype = wintypes.HINSTANCE

# ===== Module-level ctypes structs for SendInput (performance optimization) =====
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


class ShortcutExecutor(HotkeyExecutionMixin, FileExecutionMixin, UrlExecutionMixin, CommandExecutionMixin, WindowControlMixin):
    """快捷方式执行器"""

    # 记录弹窗显示前的前台窗口
    _previous_hwnd = None
    _hotkey_lock = threading.Lock()
    _hotkey_lock_timeout = 2.0  # 锁超时时间（秒），增加到2秒确保执行完成
    _last_cleanup_time = 0  # 上次清理时间戳，用于防止过于频繁的清理




    # pynput 特殊键映射
    PYNPUT_SPECIAL_KEYS = {}
    if HAS_PYNPUT:
        PYNPUT_SPECIAL_KEYS = {
            # 修饰键
            'ctrl': Key.ctrl, 'control': Key.ctrl,
            'alt': Key.alt, 'menu': Key.alt,
            'shift': Key.shift,
            'win': Key.cmd, 'lwin': Key.cmd, 'rwin': Key.cmd_r,
            
            # 功能键
            'tab': Key.tab,
            'enter': Key.enter, 'return': Key.enter,
            'escape': Key.esc, 'esc': Key.esc,
            'space': Key.space,
            'backspace': Key.backspace, 'back': Key.backspace,
            'delete': Key.delete, 'del': Key.delete,
            'insert': Key.insert, 'ins': Key.insert,
            'home': Key.home,
            'end': Key.end,
            'pageup': Key.page_up, 'pgup': Key.page_up,
            'pagedown': Key.page_down, 'pgdn': Key.page_down,
            
            # 方向键
            'up': Key.up,
            'down': Key.down,
            'left': Key.left,
            'right': Key.right,
            
            # F键
            'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
            'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
            'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
            
            # 其他
            'capslock': Key.caps_lock,
            'numlock': Key.num_lock,
            'scrolllock': Key.scroll_lock,
            'printscreen': Key.print_screen,
            'pause': Key.pause,
        }
    
    # ===== POINT 结构体（用于获取鼠标位置）=====
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    
    




    
    @staticmethod
    def execute(shortcut: ShortcutItem, force_new: bool = False) -> tuple[bool, str]:
        """执行快捷方式
        
        Returns:
            tuple[bool, str]: (是否成功, 错误消息)
        """
        try:
            if shortcut.type == ShortcutType.HOTKEY:
                # 快捷键执行：已经在内部处理了线程，这里返回状态
                # 注意：快捷键执行通常是异步的，错误可能无法立即捕获
                success = ShortcutExecutor._execute_hotkey_safe(shortcut)
                return success, "" if success else "快捷键执行失败"
                
            elif shortcut.type == ShortcutType.URL:
                success = ShortcutExecutor._execute_url(shortcut)
                return success, "" if success else "无法打开指定的 URL"
                
            elif shortcut.type == ShortcutType.COMMAND:
                # 命令执行：有些是内置命令，有些是系统命令
                return ShortcutExecutor._execute_command(shortcut)
                
            else:
                # 文件/文件夹执行
                return ShortcutExecutor._execute_file(shortcut, force_new)
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"执行快捷方式失败: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            return False, error_msg
    
    @staticmethod
    def execute_with_files(shortcut: ShortcutItem, files: List[str]) -> bool:
        """使用快捷方式打开指定文件列表
        
        将拖放的文件作为参数传递给快捷方式对应的程序打开。
        
        Args:
            shortcut: 快捷方式项（必须是 FILE 或 FOLDER 类型）
            files: 要打开的文件路径列表
        
        Returns:
            bool: 是否执行成功
        """
        if not files:
            logger.warning("没有要打开的文件")
            return False
        
        if shortcut.type not in (ShortcutType.FILE, ShortcutType.FOLDER):
            logger.warning(f"不支持的快捷方式类型用于拖放: {shortcut.type}")
            return False
        
        target = shortcut.target_path
        
        if not target:
            logger.warning("目标路径为空")
            return False
        
        # 解析快捷方式文件获取真实目标
        real_target = ShortcutExecutor._resolve_shortcut(target)
        
        if not real_target or not os.path.exists(real_target):
            logger.warning(f"目标不存在: {target} -> {real_target}")
            return False
        
        logger.info(f"拖放执行: {shortcut.name}, 目标: {real_target}, 文件数: {len(files)}")
        
        success = True
        run_as_admin = getattr(shortcut, "run_as_admin", False)
        
        # 判断目标类型
        if os.path.isdir(real_target):
            # 目标是文件夹：在资源管理器中打开并选中文件，或复制文件到该文件夹
            success = ShortcutExecutor._open_folder_with_files(real_target, files)
        elif real_target.lower().endswith('.exe'):
            # 目标是可执行文件：将所有文件作为参数传递
            success = ShortcutExecutor._open_exe_with_files(
                real_target,
                files,
                shortcut.target_args,
                getattr(shortcut, "working_dir", "") or "",
                run_as_admin=run_as_admin
            )
        else:
            # 其他文件类型（如 .lnk 快捷方式本身指向程序）
            success = ShortcutExecutor._open_file_with_files(real_target, files, run_as_admin=run_as_admin)
        
        return success
    

    
    









    







    





    
    
    

    # ===== 窗口置顶功能（已修复）=====
    
    
    
    
    


def _bind_shortcut_executor_mixins():
    from . import shortcut_command_exec, shortcut_file_exec, shortcut_hotkey, shortcut_url_exec, shortcut_window_control

    for module in (shortcut_command_exec, shortcut_file_exec, shortcut_hotkey, shortcut_url_exec, shortcut_window_control):
        module.ShortcutExecutor = ShortcutExecutor


_bind_shortcut_executor_mixins()
