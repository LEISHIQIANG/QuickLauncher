"""
键盘钩子 - DLL版本兼容封装
保持与原Python版本相同的接口
"""
import logging
from typing import Callable, Optional
from .hooks_wrapper import HooksDLL

logger = logging.getLogger(__name__)

class KeyboardHook:
    """键盘钩子 - 使用C++ DLL实现"""

    def __init__(self):
        self._dll = HooksDLL()
        self._on_alt_double_tap: Optional[Callable[[], None]] = None
        self._on_hotkey: Optional[Callable[[], None]] = None

    def install(self, on_alt_double_tap: Optional[Callable[[], None]] = None) -> bool:
        """安装键盘钩子"""
        self._on_alt_double_tap = on_alt_double_tap
        success = self._dll.install_keyboard_hook(on_alt_double_tap)
        if success:
            logger.info("键盘钩子安装成功 (DLL版本)")
        return success

    def uninstall(self):
        """卸载键盘钩子"""
        self._dll.uninstall_keyboard_hook()
        logger.info("键盘钩子已卸载")

    def set_hotkey(self, hotkey_str: str, callback: Optional[Callable[[], None]] = None):
        """设置热键"""
        self._on_hotkey = callback
        if callback:
            self._dll.set_hotkey(hotkey_str, callback)

    @property
    def alt_held(self) -> bool:
        """Alt键是否按住"""
        return self._dll.is_alt_held()

    @property
    def ctrl_held(self) -> bool:
        """Ctrl键是否按住"""
        return self._dll.is_ctrl_held()
