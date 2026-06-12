"""
Win32 全局热键管理器

使用 Win32 RegisterHotKey API 注册全局热键，通过 Qt 原生事件过滤器接收
WM_HOTKEY 消息。独立于 hooks.dll 的 SetGlobalHotkey 接口，可与之共存。
"""

import ctypes
import ctypes.wintypes
import logging

from PyQt5.QtCore import QAbstractNativeEventFilter

logger = logging.getLogger(__name__)

# Win32 常量
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # 防止按住时重复触发
WM_HOTKEY = 0x0312

# 常用虚拟键码
VK_MAP = {
    "l": 0x4C,
    "L": 0x4C,
}


def _vk_from_key(key: str) -> int:
    """将按键名称转换为 Win32 虚拟键码。"""
    if key in VK_MAP:
        return VK_MAP[key]
    # 单字符 A-Z / 0-9 直接使用 ASCII 码
    if len(key) == 1:
        ch = key.upper()
        if ch.isascii():
            return ord(ch)
    # 尝试从项目的 key_map 获取
    try:
        from hooks.key_map import key_to_vk

        return key_to_vk(key)
    except Exception:
        return 0


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    """Qt 原生事件过滤器，拦截 WM_HOTKEY 消息并分发回调。"""

    def __init__(self, registry: dict):
        super().__init__()
        # registry: {int_id: {"callback": callable, ...}, ...}
        self._registry = registry

    def nativeEventFilter(self, event_type, message):
        if _event_type_bytes(event_type) == b"windows_generic_MSG":
            try:
                try:
                    from PyQt5 import sip
                except ImportError:
                    import sip

                msg = ctypes.wintypes.MSG.from_address(int(sip.voidptr(message)))
                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    entry = self._registry.get(hotkey_id)
                    if entry and entry.get("callback"):
                        try:
                            entry["callback"]()
                        except Exception as exc:
                            logger.debug("热键回调执行失败: %s", exc, exc_info=True)
            except Exception as exc:
                logger.debug("处理 WM_HOTKEY 消息失败: %s", exc, exc_info=True)
        return False, 0


def _event_type_bytes(event_type) -> bytes:
    if isinstance(event_type, bytes):
        return event_type
    if isinstance(event_type, str):
        return event_type.encode("ascii", errors="ignore")
    try:
        return bytes(event_type)
    except Exception:
        return b""


class Win32GlobalHotkey:
    """
    Win32 RegisterHotKey 全局热键管理器。

    用法::

        hk = Win32GlobalHotkey()
        hk.register("Ctrl+Shift+L", callback=toggle_fn)
        # ... 应用退出时 ...
        hk.unregister_all()

    独立于 hooks.dll 的 SetGlobalHotkey 接口，使用 Win32 API 直接注册，
    可同时注册多个热键而不互相干扰。
    """

    def __init__(self):
        self._hotkeys: dict[int, dict] = {}
        self._next_id = 1
        self._filter = None
        self._filter_installed = False

    def _ensure_filter(self):
        """确保 Qt 原生事件过滤器已安装。"""
        if self._filter_installed:
            return True
        try:
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                logger.warning("QApplication 未就绪，无法安装原生事件过滤器")
                return False
            self._filter = _HotkeyEventFilter(self._hotkeys)
            app.installNativeEventFilter(self._filter)
            self._filter_installed = True
            logger.debug("已安装 Qt 原生事件过滤器")
            return True
        except Exception as exc:
            logger.error("安装 Qt 原生事件过滤器失败: %s", exc, exc_info=True)
            self._filter = None
            self._filter_installed = False
            return False

    def register(self, hotkey_str: str, callback) -> int:
        """
        注册全局热键。

        Args:
            hotkey_str: 热键字符串，如 "Ctrl+Shift+L"
            callback: 热键触发时的回调函数（在主线程调用）

        Returns:
            热键 ID (>0 表示成功)，0 表示失败
        """
        if not hotkey_str or not callback:
            return 0

        modifiers, vk = self._parse_hotkey(hotkey_str)
        if vk == 0:
            logger.error("无法解析热键: %s", hotkey_str)
            return 0

        if not self._ensure_filter():
            logger.error("全局热键注册中止: Qt 原生事件过滤器不可用")
            return 0

        hotkey_id = self._next_id
        self._next_id += 1

        # MOD_NOREPEAT 防止按住修饰键时重复触发
        mod_flags = modifiers | MOD_NOREPEAT

        try:
            user32 = ctypes.windll.user32
            result = user32.RegisterHotKey(None, hotkey_id, mod_flags, vk)
            if result:
                self._hotkeys[hotkey_id] = {
                    "callback": callback,
                    "hotkey_str": hotkey_str,
                    "modifiers": modifiers,
                    "vk": vk,
                }
                logger.info("全局热键注册成功: %s (id=%d)", hotkey_str, hotkey_id)
                return hotkey_id
            else:
                logger.warning("全局热键注册失败: %s (可能已被其他程序占用)", hotkey_str)
                return 0
        except Exception as exc:
            logger.error("RegisterHotKey 调用失败: %s", exc, exc_info=True)
            return 0

    def unregister(self, hotkey_id: int) -> bool:
        """取消注册指定热键。"""
        if hotkey_id not in self._hotkeys:
            return False
        try:
            user32 = ctypes.windll.user32
            if not user32.UnregisterHotKey(None, hotkey_id):
                logger.warning("全局热键取消失败: id=%d", hotkey_id)
                return False
            entry = self._hotkeys.pop(hotkey_id, None)
            logger.info(
                "全局热键已取消: %s (id=%d)",
                entry.get("hotkey_str", "?") if entry else "?",
                hotkey_id,
            )
            return True
        except Exception as exc:
            logger.error("UnregisterHotKey 调用失败: %s", exc, exc_info=True)
            return False

    def unregister_all(self):
        """取消注册所有热键。"""
        for hid in list(self._hotkeys.keys()):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, hid)
            except Exception as exc:
                logger.debug("取消热键 id=%d 失败: %s", hid, exc, exc_info=True)
        self._hotkeys.clear()
        logger.info("所有全局热键已取消")

    def remove_filter(self):
        """移除 Qt 原生事件过滤器。"""
        if self._filter_installed and self._filter:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app:
                    app.removeNativeEventFilter(self._filter)
            except Exception as exc:
                logger.debug("移除原生事件过滤器失败: %s", exc, exc_info=True)
            self._filter = None
            self._filter_installed = False

    @staticmethod
    def _parse_hotkey(hotkey_str: str) -> tuple[int, int]:
        """
        解析热键字符串，返回 (modifiers, vk_code)。

        支持的修饰键: Ctrl, Alt, Shift, Win
        """
        if not hotkey_str:
            return 0, 0

        parts = [p.strip() for p in hotkey_str.split("+") if p.strip()]
        modifiers = 0
        key = None

        for part in parts:
            lower = part.lower()
            if lower in ("ctrl", "control"):
                modifiers |= MOD_CONTROL
            elif lower == "alt":
                modifiers |= MOD_ALT
            elif lower == "shift":
                modifiers |= MOD_SHIFT
            elif lower in ("win", "windows", "meta", "super"):
                modifiers |= MOD_WIN
            else:
                if key is not None:
                    return 0, 0
                key = part

        if key is None:
            return 0, 0

        vk = _vk_from_key(key)
        return modifiers, vk
