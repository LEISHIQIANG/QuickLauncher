"""Hotkey execution helpers for ShortcutExecutor."""

import logging
import time
from typing import List

from .data_models import ShortcutItem

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

try:
    from pynput.keyboard import Key, Controller as KeyboardController
    HAS_PYNPUT = True
    keyboard = KeyboardController()
except ImportError:
    Key = None
    HAS_PYNPUT = False
    keyboard = None

logger = logging.getLogger(__name__)
ShortcutExecutor = None


class HotkeyExecutionMixin:
    @staticmethod
    def _sendinput_key_event(vk: int, is_up: bool) -> bool:
        flags = KEYEVENTF_KEYUP if is_up else 0
        if ShortcutExecutor._is_extended_vk(vk):
            flags |= KEYEVENTF_EXTENDEDKEY

        scan = 0
        try:
            scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
        except Exception:
            scan = 0

        if scan:
            flags |= KEYEVENTF_SCANCODE
            ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        else:
            ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)

        inp = INPUT(type=INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))
        try:
            sent = SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return int(sent or 0) == 1
        except Exception:
            return False
    @staticmethod
    def _release_vk_strong(vk: int):
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        try:
            ShortcutExecutor._sendinput_key_event(vk, True)
        except Exception:
            pass
        try:
            flags = KEYEVENTF_KEYUP
            if ShortcutExecutor._is_extended_vk(vk):
                flags |= KEYEVENTF_EXTENDEDKEY
            user32.keybd_event(vk, 0, flags, 0)
        except Exception:
            pass
    @staticmethod
    def _release_modifiers_strong():
        vks = [0x10, 0xA0, 0xA1, 0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C]
        for vk in vks:
            try:
                if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                    ShortcutExecutor._release_vk_strong(vk)
            except Exception:
                continue
    @classmethod
    def save_foreground_window(cls):
        """保存当前前台窗口句柄"""
        try:
            cls._previous_hwnd = user32.GetForegroundWindow()
            logger.debug(f"保存前台窗口: {cls._previous_hwnd}")
        except Exception as e:
            logger.debug("Failed to save foreground window: %s", e, exc_info=True)
            cls._previous_hwnd = None
    @classmethod
    def restore_foreground_window(cls):
        """恢复之前的前台窗口
        
        v2.6.6.0 改进：
        - 增加窗口句柄有效性检查（IsWindow）
        - 如果目标窗口无效或恢复失败，尝试激活桌面作为后备
        - 这可以修复 Win10 上弹窗隐藏后左键选择失效的问题
        """
        hwnd = cls._previous_hwnd
        
        # 检查窗口句柄是否有效
        if hwnd:
            try:
                if not user32.IsWindow(hwnd):
                    logger.debug(f"之前的窗口已无效: {hwnd}")
                    hwnd = None
                    cls._previous_hwnd = None
            except Exception:
                hwnd = None
        
        if hwnd:
            try:
                # 先尝试 SetForegroundWindow
                result = user32.SetForegroundWindow(hwnd)
                if not result:
                    # 如果失败，尝试使用 AttachThreadInput 技巧
                    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
                    
                    if current_thread != target_thread:
                        user32.AttachThreadInput(current_thread, target_thread, True)
                        user32.SetForegroundWindow(hwnd)
                        user32.AttachThreadInput(current_thread, target_thread, False)
                
                logger.debug(f"恢复前台窗口: {hwnd}")
                return True
            except Exception as e:
                logger.debug(f"恢复前台窗口失败: {e}")
        
        # ===== 后备方案：激活桌面窗口 =====
        # 如果没有有效的之前窗口，或恢复失败，尝试激活桌面
        # 这可以"重置"系统的焦点状态，修复左键失效问题
        try:
            # 获取桌面窗口句柄
            desktop_hwnd = user32.GetDesktopWindow()
            if desktop_hwnd:
                # 获取 Shell_TrayWnd (任务栏) 或 Progman (桌面)
                # Progman 是桌面的父窗口，更适合作为焦点重置目标
                progman = user32.FindWindowW("Progman", None)
                if progman:
                    user32.SetForegroundWindow(progman)
                    logger.debug(f"后备方案：激活 Progman (桌面): {progman}")
                    return True
        except Exception as e:
            logger.debug(f"后备焦点恢复失败: {e}")
        
        return False
    @classmethod
    def restore_foreground_window_fast(cls, timeout_ms: int = 180, poll_ms: int = 8) -> bool:
        target = cls._previous_hwnd
        if not target:
            return False

        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        last_result = False

        while time.perf_counter() < deadline:
            last_result = cls.restore_foreground_window()
            if user32.GetForegroundWindow() == target:
                return True
            time.sleep(poll_ms / 1000.0)

        return last_result
    @staticmethod
    def _vk_from_key(key_str: str) -> int:
        k = (key_str or "").strip()
        k_lower = k.lower()
        if not k_lower:
            return 0

        vk_codes = {
            'ctrl': 0x11, 'control': 0x11, 'lctrl': 0xA2, 'rctrl': 0xA3,
            'alt': 0x12, 'menu': 0x12, 'lalt': 0xA4, 'ralt': 0xA5,
            'shift': 0x10, 'lshift': 0xA0, 'rshift': 0xA1,
            'win': 0x5B, 'lwin': 0x5B, 'rwin': 0x5C,
            'backspace': 0x08, 'back': 0x08,
            'tab': 0x09,
            'enter': 0x0D, 'return': 0x0D,
            'pause': 0x13,
            'capslock': 0x14, 'caps': 0x14,
            'escape': 0x1B, 'esc': 0x1B,
            'space': 0x20,
            'pageup': 0x21, 'pgup': 0x21,
            'pagedown': 0x22, 'pgdn': 0x22,
            'end': 0x23,
            'home': 0x24,
            'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
            'printscreen': 0x2C, 'prtscr': 0x2C,
            'insert': 0x2D, 'ins': 0x2D,
            'delete': 0x2E, 'del': 0x2E,
            'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
            'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
            'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
            'numlock': 0x90,
            'scrolllock': 0x91,
        }

        if k_lower in vk_codes:
            return vk_codes[k_lower]

        if len(k) == 1 and k.isalpha():
            return ord(k.upper())
        if len(k) == 1 and k.isdigit():
            return ord(k)
        return 0
    @staticmethod
    def _is_extended_vk(vk: int) -> bool:
        return vk in {
            0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
            0x5B, 0x5C,
            0xA3, 0xA5,
        }
    @staticmethod
    def _execute_hotkey_sendinput(modifiers: List[str], key: str) -> bool:
        """使用 keybd_event + 随机延迟模拟真实按键"""
        import random

        vk_main = ShortcutExecutor._vk_from_key(key)
        if not vk_main:
            return False

        mod_vks: List[int] = []
        for m in modifiers or []:
            vk = ShortcutExecutor._vk_from_key(m)
            if vk:
                if vk == 0x10: vk = 0xA0
                elif vk == 0x11: vk = 0xA2
                elif vk == 0x12: vk = 0xA4
                mod_vks.append(vk)

        try:
            # 按下修饰键
            for vk in mod_vks:
                logger.debug(f"[SendInput] 按下修饰键: {vk}")
                user32.keybd_event(vk, 0, 0, 0)
                time.sleep(random.uniform(0.015, 0.025))

            # 按下主键
            logger.debug(f"[SendInput] 按下主键: {vk_main}")
            user32.keybd_event(vk_main, 0, 0, 0)
            time.sleep(random.uniform(0.040, 0.060))

            # 释放主键
            logger.debug(f"[SendInput] 释放主键: {vk_main}")
            user32.keybd_event(vk_main, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(random.uniform(0.015, 0.025))

            # 释放修饰键（逆序，带 EXTENDEDKEY 标志）
            for vk in reversed(mod_vks):
                logger.debug(f"[SendInput] 释放修饰键: {vk}")
                flags = KEYEVENTF_KEYUP
                if ShortcutExecutor._is_extended_vk(vk):
                    flags |= KEYEVENTF_EXTENDEDKEY
                user32.keybd_event(vk, 0, flags, 0)
                time.sleep(0.010)

            # 强制释放所有修饰键
            time.sleep(0.020)
            for vk in [0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1]:
                flags = KEYEVENTF_KEYUP
                if ShortcutExecutor._is_extended_vk(vk):
                    flags |= KEYEVENTF_EXTENDEDKEY
                user32.keybd_event(vk, 0, flags, 0)

            return True

        except Exception as e:
            logger.error(f"[Hotkey] 错误: {e}")
            # 只在异常时清理修饰键
            for vk in [0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1]:
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            return False
    @staticmethod
    def _force_release_modifiers():
        """强制释放所有修饰键，防止卡键"""
        # VK codes: Shift=0x10, Ctrl=0x11, Alt=0x12, Win=0x5B
        # 使用 keybd_event 强制发送 KeyUp 事件
        KEYEVENTF_KEYUP = 0x0002
        try:
            for vk in [0x10, 0x11, 0x12, 0x5B, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5]:
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception as e:
            logger.error(f"强制释放修饰键失败: {e}")
        try:
            ShortcutExecutor._release_modifiers_strong()
        except Exception:
            pass
    @staticmethod
    def _force_release_key(key: str):
        vk = ShortcutExecutor._vk_from_key(key)
        if not vk:
            return
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        try:
            flags = KEYEVENTF_KEYUP
            if ShortcutExecutor._is_extended_vk(vk):
                flags |= KEYEVENTF_EXTENDEDKEY
            user32.keybd_event(vk, 0, flags, 0)
        except Exception:
            pass
    @staticmethod
    def _verify_and_release_all_modifiers():
        """验证并释放所有可能卡住的修饰键
        
        v2.6.6.0 新增方法：
        1. 检测所有修饰键的当前状态
        2. 如果发现按下状态，使用多种方法尝试释放
        3. 记录日志以便调试
        """
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        
        # 所有修饰键的VK码：通用 + 左右侧特定
        modifier_vks = [
            (0x10, "Shift"),
            (0xA0, "LShift"),
            (0xA1, "RShift"),
            (0x11, "Ctrl"),
            (0xA2, "LCtrl"),
            (0xA3, "RCtrl"),
            (0x12, "Alt"),
            (0xA4, "LAlt"),
            (0xA5, "RAlt"),
            (0x5B, "LWin"),
            (0x5C, "RWin"),
        ]
        
        stuck_keys = []
        
        # 检测哪些键处于按下状态
        for vk, name in modifier_vks:
            try:
                state = user32.GetAsyncKeyState(vk)
                if (state & 0x8000) != 0:
                    stuck_keys.append((vk, name))
            except Exception:
                pass
        
        # 如果有卡住的键，尝试释放
        if stuck_keys:
            logger.debug(f"检测到卡住的修饰键: {[name for _, name in stuck_keys]}")
            
            for vk, name in stuck_keys:
                released = False
                
                # 尝试方法1: keybd_event
                for _ in range(3):
                    try:
                        flags = KEYEVENTF_KEYUP
                        if ShortcutExecutor._is_extended_vk(vk):
                            flags |= KEYEVENTF_EXTENDEDKEY
                        user32.keybd_event(vk, 0, flags, 0)
                        time.sleep(0.002)
                    except Exception:
                        pass
                    
                    # 检查是否已释放
                    try:
                        state = user32.GetAsyncKeyState(vk)
                        if (state & 0x8000) == 0:
                            released = True
                            break
                    except Exception:
                        pass
                
                # 尝试方法2: _release_vk_strong
                if not released:
                    try:
                        ShortcutExecutor._release_vk_strong(vk)
                        time.sleep(0.005)
                    except Exception:
                        pass
                    
                    # 再次检查
                    try:
                        state = user32.GetAsyncKeyState(vk)
                        if (state & 0x8000) == 0:
                            released = True
                    except Exception:
                        pass
                
                # 尝试方法3: SendInput（使用模块级结构）
                if not released:
                    try:
                        ShortcutExecutor._sendinput_key_event(vk, True)
                        time.sleep(0.002)
                    except Exception:
                        pass
                
                if released:
                    logger.debug(f"成功释放修饰键: {name}")
                else:
                    logger.warning(f"无法释放修饰键: {name} (VK=0x{vk:02X})")
    @staticmethod
    def _pre_execution_cleanup():
        """执行快捷键前的清理工作

        v2.6.6.0 新增：
        这是解决修饰键卡住问题的核心方法。
        用户可能通过全局热键（如 Alt+Space）唤起弹窗，
        此时 Alt 键可能仍处于按下状态，导致后续执行的快捷键
        会与残留的 Alt 键组合，造成按键卡住。

        此方法在执行快捷键前：
        1. 强制释放所有修饰键
        2. 等待系统处理按键释放事件
        3. 验证所有修饰键都已释放
        """
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001

        # 所有需要清理的修饰键
        all_modifier_vks = [
            0x10,  # VK_SHIFT
            0xA0, 0xA1,  # VK_LSHIFT, VK_RSHIFT
            0x11,  # VK_CONTROL
            0xA2, 0xA3,  # VK_LCONTROL, VK_RCONTROL
            0x12,  # VK_MENU (Alt)
            0xA4, 0xA5,  # VK_LMENU, VK_RMENU
            0x5B, 0x5C,  # VK_LWIN, VK_RWIN
        ]

        # 第一轮：无条件释放所有修饰键（使用 keybd_event）
        for vk in all_modifier_vks:
            try:
                flags = KEYEVENTF_KEYUP
                if ShortcutExecutor._is_extended_vk(vk):
                    flags |= KEYEVENTF_EXTENDEDKEY
                user32.keybd_event(vk, 0, flags, 0)
            except Exception:
                pass

        time.sleep(0.015)

        # 第二轮：使用 SendInput 再次释放
        for vk in all_modifier_vks:
            try:
                ShortcutExecutor._sendinput_key_event(vk, True)
            except Exception:
                pass

        time.sleep(0.015)

        # 第三轮：检测并强力释放仍然卡住的键
        for attempt in range(3):
            still_stuck = []
            for vk in all_modifier_vks:
                try:
                    if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                        still_stuck.append(vk)
                except Exception:
                    pass

            if not still_stuck:
                break

            logger.warning(f"执行前检测到残留按键(尝试{attempt+1}): {[hex(vk) for vk in still_stuck]}")
            for vk in still_stuck:
                try:
                    ShortcutExecutor._release_vk_strong(vk)
                    time.sleep(0.003)
                except Exception:
                    pass

            time.sleep(0.020)

        logger.debug("执行前清理完成")
    @staticmethod
    def _execute_hotkey_safe(shortcut: ShortcutItem):
        """安全执行快捷键"""
        acquired = False
        try:
            acquired = ShortcutExecutor._hotkey_lock.acquire(timeout=ShortcutExecutor._hotkey_lock_timeout)
            if not acquired:
                logger.warning("快捷键执行跳过: 上一个执行尚未完成")
                return False

            trigger_mode = getattr(shortcut, 'trigger_mode', 'immediate')

            # 先恢复前台窗口，再发送快捷键
            if trigger_mode == 'after_close':
                logger.info("[Hotkey] 触发模式: after_close，恢复前台窗口")
                target_hwnd = ShortcutExecutor._previous_hwnd

                # 恢复窗口
                ShortcutExecutor.restore_foreground_window_fast(timeout_ms=100)

                # 验证窗口是否切换成功（最多等待 300ms）
                for i in range(6):
                    time.sleep(0.050)
                    current = user32.GetForegroundWindow()
                    if current == target_hwnd:
                        logger.info(f"[Hotkey] 窗口切换成功: {current}")
                        break
                    if i == 5:
                        logger.warning(f"[Hotkey] 窗口未切换到目标: 当前={current}, 目标={target_hwnd}")

                # 关键：等待窗口完全激活并准备接收输入
                time.sleep(0.250)  # 增加到250ms
            else:
                # immediate 模式：全局快捷键，直接发送，不恢复窗口
                logger.info("[Hotkey] 触发模式: immediate，全局快捷键")
                # 记录当前焦点窗口
                current_hwnd = user32.GetForegroundWindow()
                logger.info(f"[Hotkey] 当前焦点窗口: {current_hwnd}")

            modifiers = shortcut.hotkey_modifiers or []
            key = shortcut.hotkey_key or ""

            logger.info(f"[Hotkey] 发送快捷键: modifiers={modifiers}, key={key}")
            result = ShortcutExecutor._execute_hotkey_sendinput(modifiers, key)

            # 不自动释放修饰键，避免干扰正常按键
            # 如果用户遇到Alt卡住，可以手动按一下Alt键解决

            return result

        except Exception as e:
            logger.error(f"执行快捷键失败: {e}")
            return False
        finally:
            if acquired:
                ShortcutExecutor._hotkey_lock.release()
    @staticmethod
    def _get_pynput_key(key_str: str):
        """将字符串转换为 pynput 键"""
        key_lower = key_str.lower().strip()
        
        # 检查特殊键
        if key_lower in ShortcutExecutor.PYNPUT_SPECIAL_KEYS:
            return ShortcutExecutor.PYNPUT_SPECIAL_KEYS[key_lower]
        
        # 单个字符
        if len(key_str) == 1:
            return key_str.lower()
        
        logger.warning(f"未知键: {key_str}")
        return None
    @staticmethod
    def _execute_hotkey_pynput(shortcut: ShortcutItem) -> bool:
        """使用 pynput 执行快捷键（模拟真实按键）"""
        modifiers = shortcut.hotkey_modifiers or []
        key = shortcut.hotkey_key or ""

        if not key:
            logger.warning("快捷键未设置")
            return False

        logger.info(f"[pynput] 执行快捷键: {shortcut.hotkey}")

        pressed_keys = []
        try:
            # 转换修饰键
            mod_keys = []
            for mod in modifiers:
                pynput_key = ShortcutExecutor._get_pynput_key(mod)
                if pynput_key:
                    mod_keys.append(pynput_key)
            
            # 转换主键
            main_key = ShortcutExecutor._get_pynput_key(key)
            if not main_key:
                logger.error(f"无法识别主键: {key}")
                return False
            
            # 按下所有修饰键
            for mk in mod_keys:
                keyboard.press(mk)
                pressed_keys.append(mk)
                time.sleep(0.01)

            # 按下主键
            time.sleep(0.01)
            keyboard.press(main_key)
            pressed_keys.append(main_key)

            # 保持按键状态，让目标程序有足够时间识别
            time.sleep(0.08)

            # 立即释放主键
            keyboard.release(main_key)
            pressed_keys.remove(main_key)
            time.sleep(0.01)

            # 立即释放所有修饰键（逆序）
            for mk in reversed(mod_keys):
                keyboard.release(mk)
                pressed_keys.remove(mk)
                time.sleep(0.01)

            # 额外使用 Windows API 强制释放 Alt 键
            time.sleep(0.020)
            for vk in [0x12, 0xA4, 0xA5]:  # VK_MENU, VK_LMENU, VK_RMENU
                try:
                    if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                        user32.keybd_event(vk, 0, 0x0002, 0)
                        time.sleep(0.005)
                except Exception:
                    pass

            logger.info(f"[pynput] 快捷键发送完成: {shortcut.hotkey}")
            return True
            
        except Exception as e:
            logger.error(f"[pynput] 执行快捷键异常: {e}")
            # 只在异常时才清理残留按键
            for k in reversed(pressed_keys):
                try:
                    keyboard.release(k)
                except Exception:
                    pass
            return False
    @staticmethod
    def _execute_hotkey_ctypes(shortcut: ShortcutItem) -> bool:
        """使用 ctypes 执行快捷键（备用方案）"""
        modifiers = shortcut.hotkey_modifiers or []
        key = shortcut.hotkey_key or ""
        
        if not key:
            logger.warning("快捷键未设置")
            return False
        
        logger.info(f"[ctypes] 执行快捷键: {shortcut.hotkey}")
        
        def get_vk(k):
            return ShortcutExecutor._vk_from_key(k)
            
        pressed_vks = []
        try:
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_EXTENDEDKEY = 0x0001
            
            # 按下修饰键
            for mod in modifiers:
                vk = get_vk(mod)
                if vk:
                    flags = 0
                    if ShortcutExecutor._is_extended_vk(vk):
                        flags |= KEYEVENTF_EXTENDEDKEY
                    user32.keybd_event(vk, 0, flags, 0)
                    pressed_vks.append(vk)
                    time.sleep(0.01)
            
            # 按下主键
            vk_main = get_vk(key)
            if vk_main:
                flags = 0
                if ShortcutExecutor._is_extended_vk(vk_main):
                    flags |= KEYEVENTF_EXTENDEDKEY
                user32.keybd_event(vk_main, 0, flags, 0)
                pressed_vks.append(vk_main)
                time.sleep(0.05) # 稍微增加保持时间
            
            return True
            
        except Exception as e:
            logger.error(f"[ctypes] 执行异常: {e}")
            return False
            
        finally:
            # v2.6.5.9 改进：确保释放所有已按下的键（逆序释放）
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_EXTENDEDKEY = 0x0001
            
            for vk in reversed(pressed_vks):
                # 尝试多种方法释放
                for attempt in range(3):
                    try:
                        flags = KEYEVENTF_KEYUP
                        if ShortcutExecutor._is_extended_vk(vk):
                            flags |= KEYEVENTF_EXTENDEDKEY
                        user32.keybd_event(vk, 0, flags, 0)
                        time.sleep(0.003)
                        
                        # 检查是否已释放
                        state = user32.GetAsyncKeyState(vk)
                        if (state & 0x8000) == 0:
                            break  # 成功释放
                    except Exception as rel_e:
                        if attempt == 2:
                            logger.error(f"释放VK失败: {rel_e}")
                
                # 如果仍未释放，使用强力释放
                try:
                    if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                        ShortcutExecutor._release_vk_strong(vk)
                except Exception:
                    pass
            
            # 额外调用全面验证释放
            time.sleep(0.010)
            try:
                ShortcutExecutor._verify_and_release_all_modifiers()
            except Exception:
                pass
