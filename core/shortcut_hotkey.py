"""Hotkey execution helpers for ShortcutExecutor."""

import ctypes
import logging
import time

from .data_models import ShortcutItem
from .shortcut_types import (
    _INPUT_UNION,
    INPUT,
    INPUT_KEYBOARD,
    KEYBDINPUT,
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    SendInput,
    user32,
)

_pynput_Key = None
_pynput_KeyboardController = None
_keyboard_instance = None
HAS_PYNPUT = False


def _import_pynput():
    """Lazy pynput import — avoids blocking module-level init on headless CI."""
    global HAS_PYNPUT, _pynput_Key, _pynput_KeyboardController
    if HAS_PYNPUT or _pynput_Key is not None:
        return
    try:
        from pynput.keyboard import Controller as KC
        from pynput.keyboard import Key as K

        _pynput_Key = K
        _pynput_KeyboardController = KC
        HAS_PYNPUT = True
    except (ImportError, AttributeError):
        HAS_PYNPUT = False


def Key():
    _import_pynput()
    return _pynput_Key


def keyboard():
    global _keyboard_instance
    _import_pynput()
    if _pynput_KeyboardController is None:
        return None
    if _keyboard_instance is None:
        _keyboard_instance = _pynput_KeyboardController()
    return _keyboard_instance


logger = logging.getLogger(__name__)
ShortcutExecutor = None


class HotkeyExecutionMixin:
    @staticmethod
    def _sendinput_key_event(vk: int, is_up: bool) -> bool:
        flags = KEYEVENTF_KEYUP if is_up else 0
        if ShortcutExecutor._is_extended_vk(vk):  # type: ignore[attr-defined]
            flags |= KEYEVENTF_EXTENDEDKEY

        scan = 0
        try:
            scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
        except (OSError, AttributeError):
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
        except (OSError, AttributeError):
            return False

    @staticmethod
    def _release_vk_strong(vk: int):
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        try:
            ShortcutExecutor._sendinput_key_event(vk, True)  # type: ignore[attr-defined]
        except (OSError, AttributeError) as e:
            logger.debug("_sendinput_key_event 释放 VK=0x%02X 失败: %s", vk, e)
        try:
            flags = KEYEVENTF_KEYUP
            if ShortcutExecutor._is_extended_vk(vk):  # type: ignore[attr-defined]
                flags |= KEYEVENTF_EXTENDEDKEY
            user32.keybd_event(vk, 0, flags, 0)
        except (OSError, AttributeError) as e:
            logger.debug("keybd_event 释放 VK=0x%02X 失败: %s", vk, e)

    @staticmethod
    def _release_modifiers_strong():
        vks = [0x10, 0xA0, 0xA1, 0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C]
        for vk in vks:
            try:
                if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                    ShortcutExecutor._release_vk_strong(vk)  # type: ignore[attr-defined]
            except (OSError, AttributeError):
                continue

    @classmethod
    def save_foreground_window(cls):
        """保存当前前台窗口句柄

        只排除已注册的 LauncherPopup HWND（弹窗自身），
        其他 QuickLauncher 窗口（例如用户已打开的配置窗口）依然可以
        作为恢复目标保存下来，这样弹窗隐藏后焦点能正确回到配置窗口。
        """
        try:
            hwnd = int(user32.GetForegroundWindow() or 0)
            process_id = cls._window_process_id(hwnd) if hwnd and user32.IsWindow(hwnd) else 0  # type: ignore[attr-defined]
            if not hwnd or not process_id:
                logger.debug("未保存无效的前台窗口: hwnd=%s pid=%s", hwnd, process_id)
                return False

            with cls._foreground_window_lock:  # type: ignore[attr-defined]
                popup_hwnds = getattr(cls, "_popup_hwnds", None)
                if popup_hwnds and hwnd in popup_hwnds:
                    logger.debug("前台窗口属于 LauncherPopup，保留已有外部目标: hwnd=%s", hwnd)
                    return False
                cls._previous_hwnd = hwnd  # type: ignore[attr-defined]
                cls._previous_hwnd_process_id = process_id  # type: ignore[attr-defined]
            logger.debug("保存前台窗口: hwnd=%s pid=%s", hwnd, process_id)
            return True
        except (OSError, AttributeError) as e:
            logger.debug("Failed to save foreground window: %s", e, exc_info=True)
            return False

    @classmethod
    def register_popup_hwnd(cls, hwnd: int) -> None:
        """将一个 LauncherPopup 的 HWND 注册为"弹窗自身"。

        save_foreground_window 在前台窗口是已注册的弹窗 HWND 时会保留
        之前的恢复目标，避免把弹窗自身当作恢复焦点使用。
        其他 QuickLauncher 窗口（例如配置窗口）不在此注册表内，
        仍然可以正确保存为恢复目标。
        """
        try:
            handle = int(hwnd or 0)
        except (TypeError, ValueError):
            return
        if not handle:
            return
        with cls._foreground_window_lock:  # type: ignore[attr-defined]
            popup_hwnds = getattr(cls, "_popup_hwnds", None)
            if popup_hwnds is None:
                cls._popup_hwnds = {handle}  # type: ignore[attr-defined]
            else:
                popup_hwnds.add(handle)

    @classmethod
    def unregister_popup_hwnd(cls, hwnd: int) -> None:
        """取消注册一个 LauncherPopup 的 HWND。"""
        try:
            handle = int(hwnd or 0)
        except (TypeError, ValueError):
            return
        if not handle:
            return
        with cls._foreground_window_lock:  # type: ignore[attr-defined]
            popup_hwnds = getattr(cls, "_popup_hwnds", None)
            if popup_hwnds is not None:
                popup_hwnds.discard(handle)

    @classmethod
    def restore_foreground_window(cls):
        """恢复之前的前台窗口

        v2.6.6.0 改进：
        - 增加窗口句柄有效性检查（IsWindow）
        - 如果目标窗口无效或恢复失败，尝试激活桌面作为后备
        - 这可以修复 Win10 上弹窗隐藏后左键选择失效的问题
        """
        with cls._foreground_window_lock:  # type: ignore[attr-defined]
            hwnd = cls._previous_hwnd  # type: ignore[attr-defined]
            expected_process_id = int(cls._previous_hwnd_process_id or 0)  # type: ignore[attr-defined]

        # 检查窗口句柄是否有效
        if hwnd:
            try:
                actual_process_id = cls._window_process_id(hwnd) if user32.IsWindow(hwnd) else 0  # type: ignore[attr-defined]
                if not actual_process_id or (expected_process_id and actual_process_id != expected_process_id):
                    logger.debug(
                        "之前的窗口已无效或句柄已复用: hwnd=%s expected_pid=%s actual_pid=%s",
                        hwnd,
                        expected_process_id,
                        actual_process_id,
                    )
                    hwnd = None
                    with cls._foreground_window_lock:  # type: ignore[attr-defined]
                        cls._previous_hwnd = None  # type: ignore[attr-defined]
                        cls._previous_hwnd_process_id = None  # type: ignore[attr-defined]
            except (OSError, AttributeError):
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
            except (OSError, AttributeError) as e:
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
        except (OSError, AttributeError) as e:
            logger.debug(f"后备焦点恢复失败: {e}")

        return False

    @classmethod
    def restore_foreground_window_fast(cls, timeout_ms: int = 180, poll_ms: int = 8) -> bool:
        target = cls._previous_hwnd  # type: ignore[attr-defined]
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
        from hooks.key_map import key_to_vk

        return key_to_vk(key_str)

    @staticmethod
    def _is_extended_vk(vk: int) -> bool:
        return vk in {
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x28,
            0x2D,
            0x2E,
            0x5B,
            0x5C,
            0xA3,
            0xA5,
        }

    @staticmethod
    def _execute_hotkey_sendinput(modifiers: list[str], key: str | list[str]) -> bool:
        """使用 SendInput 发送键盘组合，并只释放本次实际注入的按键。"""
        import random

        keys = key if isinstance(key, list | tuple) else [key]
        main_vks = [ShortcutExecutor._vk_from_key(item) for item in keys]  # type: ignore[attr-defined]
        main_vks = [vk for vk in main_vks if vk]
        if not main_vks:
            return False

        mod_vks: list[int] = []
        for m in modifiers or []:
            vk = ShortcutExecutor._vk_from_key(m)  # type: ignore[attr-defined]
            if vk:
                if vk == 0x10:
                    vk = 0xA0
                elif vk == 0x11:
                    vk = 0xA2
                elif vk == 0x12:
                    vk = 0xA4
                mod_vks.append(vk)

        pressed_by_us: list[int] = []
        try:
            for vk in mod_vks:
                if user32.GetAsyncKeyState(vk) & 0x8000:
                    logger.debug("[SendInput] 保留用户已按住的修饰键: %s", vk)
                    continue
                logger.debug("[SendInput] 按下修饰键: %s", vk)
                if not ShortcutExecutor._sendinput_key_event(vk, False):  # type: ignore[attr-defined]
                    return False
                pressed_by_us.append(vk)
                time.sleep(random.uniform(0.015, 0.025))

            for vk_main in main_vks:
                logger.debug("[SendInput] 按下主键: %s", vk_main)
                if not ShortcutExecutor._sendinput_key_event(vk_main, False):  # type: ignore[attr-defined]
                    return False
                pressed_by_us.append(vk_main)
                time.sleep(random.uniform(0.015, 0.025))
            time.sleep(random.uniform(0.040, 0.060))

            for vk_main in reversed(main_vks):
                if not ShortcutExecutor._sendinput_key_event(vk_main, True):  # type: ignore[attr-defined]
                    return False
                pressed_by_us.remove(vk_main)
                time.sleep(random.uniform(0.015, 0.025))

            for vk in reversed(mod_vks):
                if vk not in pressed_by_us:
                    continue
                logger.debug("[SendInput] 释放修饰键: %s", vk)
                if not ShortcutExecutor._sendinput_key_event(vk, True):  # type: ignore[attr-defined]
                    return False
                pressed_by_us.remove(vk)
                time.sleep(0.010)
            return True
        except (OSError, AttributeError) as exc:
            logger.error("[Hotkey] 错误: %s", exc)
            return False
        finally:
            for vk in reversed(pressed_by_us):
                ShortcutExecutor._sendinput_key_event(vk, True)  # type: ignore[attr-defined]

    @staticmethod
    def _force_release_modifiers():
        """强制释放所有修饰键，防止卡键"""
        # VK codes: Shift=0x10, Ctrl=0x11, Alt=0x12, Win=0x5B
        # 使用 keybd_event 强制发送 KeyUp 事件
        KEYEVENTF_KEYUP = 0x0002
        try:
            for vk in [0x10, 0x11, 0x12, 0x5B, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5]:
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except (OSError, AttributeError) as e:
            logger.error(f"强制释放修饰键失败: {e}")
        try:
            ShortcutExecutor._release_modifiers_strong()  # type: ignore[attr-defined]
        except (OSError, AttributeError) as exc:
            logger.debug("强制释放修饰键调用失败: %s", exc, exc_info=True)

    @staticmethod
    def _force_release_key(key: str):
        vk = ShortcutExecutor._vk_from_key(key)  # type: ignore[attr-defined]
        if not vk:
            return
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001
        try:
            flags = KEYEVENTF_KEYUP
            if ShortcutExecutor._is_extended_vk(vk):  # type: ignore[attr-defined]
                flags |= KEYEVENTF_EXTENDEDKEY
            user32.keybd_event(vk, 0, flags, 0)
        except (OSError, AttributeError) as e:
            logger.debug("keybd_event 释放 %s(VK=0x%02X) 失败: %s", key, vk, e)

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
            except (OSError, AttributeError) as exc:
                logger.debug("检测修饰键状态失败: %s", exc, exc_info=True)

        # 如果有卡住的键，尝试释放
        if stuck_keys:
            logger.debug(f"检测到卡住的修饰键: {[name for _, name in stuck_keys]}")

            for vk, name in stuck_keys:
                released = False

                # 尝试方法1: keybd_event
                for _ in range(3):
                    try:
                        flags = KEYEVENTF_KEYUP
                        if ShortcutExecutor._is_extended_vk(vk):  # type: ignore[attr-defined]
                            flags |= KEYEVENTF_EXTENDEDKEY
                        user32.keybd_event(vk, 0, flags, 0)
                        time.sleep(0.002)
                    except (OSError, AttributeError) as exc:
                        logger.debug("keybd_event释放修饰键失败: %s", exc, exc_info=True)

                    # 检查是否已释放
                    try:
                        state = user32.GetAsyncKeyState(vk)
                        if (state & 0x8000) == 0:
                            released = True
                            break
                    except (OSError, AttributeError) as exc:
                        logger.debug("检查修饰键释放状态失败: %s", exc, exc_info=True)

                # 尝试方法2: _release_vk_strong
                if not released:
                    try:
                        ShortcutExecutor._release_vk_strong(vk)  # type: ignore[attr-defined]
                        time.sleep(0.005)
                    except (OSError, AttributeError) as exc:
                        logger.debug("强力释放修饰键失败: %s", exc, exc_info=True)

                    # 再次检查
                    try:
                        state = user32.GetAsyncKeyState(vk)
                        if (state & 0x8000) == 0:
                            released = True
                    except (OSError, AttributeError) as exc:
                        logger.debug("再次检查修饰键释放状态失败: %s", exc, exc_info=True)

                # 尝试方法3: SendInput（使用模块级结构）
                if not released:
                    try:
                        ShortcutExecutor._sendinput_key_event(vk, True)  # type: ignore[attr-defined]
                        time.sleep(0.002)
                    except (OSError, AttributeError) as exc:
                        logger.debug("SendInput释放修饰键失败: %s", exc, exc_info=True)

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
            0xA0,
            0xA1,  # VK_LSHIFT, VK_RSHIFT
            0x11,  # VK_CONTROL
            0xA2,
            0xA3,  # VK_LCONTROL, VK_RCONTROL
            0x12,  # VK_MENU (Alt)
            0xA4,
            0xA5,  # VK_LMENU, VK_RMENU
            0x5B,
            0x5C,  # VK_LWIN, VK_RWIN
        ]

        # 第一轮：无条件释放所有修饰键（使用 keybd_event）
        for vk in all_modifier_vks:
            try:
                flags = KEYEVENTF_KEYUP
                if ShortcutExecutor._is_extended_vk(vk):  # type: ignore[attr-defined]
                    flags |= KEYEVENTF_EXTENDEDKEY
                user32.keybd_event(vk, 0, flags, 0)
            except (OSError, AttributeError) as exc:
                logger.debug("预执行清理keybd_event释放失败: %s", exc, exc_info=True)

        time.sleep(0.015)

        # 第二轮：使用 SendInput 再次释放
        for vk in all_modifier_vks:
            try:
                ShortcutExecutor._sendinput_key_event(vk, True)  # type: ignore[attr-defined]
            except (OSError, AttributeError) as exc:
                logger.debug("预执行清理SendInput释放失败: %s", exc, exc_info=True)

        time.sleep(0.015)

        # 第三轮：检测并强力释放仍然卡住的键
        for attempt in range(3):
            still_stuck = []
            for vk in all_modifier_vks:
                try:
                    if (user32.GetAsyncKeyState(vk) & 0x8000) != 0:
                        still_stuck.append(vk)
                except (OSError, AttributeError) as exc:
                    logger.debug("预执行检测残留按键状态失败: %s", exc, exc_info=True)

            if not still_stuck:
                break

            logger.warning(f"执行前检测到残留按键(尝试{attempt + 1}): {[hex(vk) for vk in still_stuck]}")
            for vk in still_stuck:
                try:
                    ShortcutExecutor._release_vk_strong(vk)  # type: ignore[attr-defined]
                    time.sleep(0.003)
                except (OSError, AttributeError) as exc:
                    logger.debug("预执行强力释放残留按键失败: %s", exc, exc_info=True)

            time.sleep(0.020)

        logger.debug("执行前清理完成")

    @staticmethod
    def _execute_hotkey_safe(shortcut: ShortcutItem):
        """安全执行快捷键"""
        acquired = False
        try:
            acquired = ShortcutExecutor._hotkey_lock.acquire(timeout=ShortcutExecutor._hotkey_lock_timeout)  # type: ignore[attr-defined]
            if not acquired:
                logger.warning("快捷键执行跳过: 上一个执行尚未完成")
                return False

            trigger_mode = getattr(shortcut, "trigger_mode", "immediate")

            # 先恢复前台窗口，再发送快捷键
            if trigger_mode == "after_close":
                logger.info("[Hotkey] 触发模式: after_close，恢复前台窗口")
                target_hwnd = ShortcutExecutor._previous_hwnd  # type: ignore[attr-defined]

                # 恢复窗口
                ShortcutExecutor.restore_foreground_window_fast(timeout_ms=100)  # type: ignore[attr-defined]

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
            keys = list(getattr(shortcut, "hotkey_keys", []) or [])
            if not keys and shortcut.hotkey_key:
                keys = [shortcut.hotkey_key]

            logger.info("[Hotkey] 发送快捷键: modifiers=%s, key_count=%d", modifiers, len(keys))
            result = ShortcutExecutor._execute_hotkey_sendinput(modifiers, keys)  # type: ignore[attr-defined]

            # 不自动释放修饰键，避免干扰正常按键
            # 如果用户遇到Alt卡住，可以手动按一下Alt键解决

            return result

        except (OSError, AttributeError) as e:
            logger.error(f"执行快捷键失败: {e}")
            return False
        finally:
            if acquired:
                ShortcutExecutor._hotkey_lock.release()  # type: ignore[attr-defined]

    @staticmethod
    def _get_pynput_key(key_str: str):
        """将字符串转换为 pynput 键"""
        key_lower = key_str.lower().strip()

        ShortcutExecutor._ensure_pynput_keys()  # type: ignore[attr-defined]
        # 检查特殊键
        if key_lower in ShortcutExecutor.PYNPUT_SPECIAL_KEYS:  # type: ignore[attr-defined]
            return ShortcutExecutor.PYNPUT_SPECIAL_KEYS[key_lower]  # type: ignore[attr-defined]

        # 单个字符
        if len(key_str) == 1:
            return key_str.lower()

        logger.warning(f"未知键: {key_str}")
        return None
