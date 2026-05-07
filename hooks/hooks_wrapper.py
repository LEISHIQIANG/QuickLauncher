"""
C++ DLL钩子的Python封装
使用ctypes调用hooks.dll
"""
import ctypes
import os
from typing import Callable, Optional

# 回调函数类型
MOUSE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int)
KEYBOARD_CALLBACK = ctypes.CFUNCTYPE(None)

class HooksDLL:
    def __init__(self, dll_path: str = None):
        if dll_path is None:
            hooks_dir = os.path.dirname(__file__)
            dll_path = os.path.join(hooks_dir, "hooks.dll")
        self.dll = ctypes.CDLL(dll_path)

        # 定义函数签名
        self.dll.InstallMouseHook.argtypes = [MOUSE_CALLBACK]
        self.dll.InstallMouseHook.restype = ctypes.c_bool

        self.dll.UninstallMouseHook.argtypes = []
        self.dll.UninstallMouseHook.restype = None

        self.dll.SetMousePaused.argtypes = [ctypes.c_bool]
        self.dll.SetMousePaused.restype = None

        self.dll.IsMousePaused.argtypes = []
        self.dll.IsMousePaused.restype = ctypes.c_bool

        self.dll.SetAltDoubleClickCallback.argtypes = [MOUSE_CALLBACK]
        self.dll.SetAltDoubleClickCallback.restype = None

        self.dll.InstallKeyboardHook.argtypes = [KEYBOARD_CALLBACK]
        self.dll.InstallKeyboardHook.restype = ctypes.c_bool

        self.dll.UninstallKeyboardHook.argtypes = []
        self.dll.UninstallKeyboardHook.restype = None

        self.dll.IsAltHeld.argtypes = []
        self.dll.IsAltHeld.restype = ctypes.c_bool

        self.dll.IsCtrlHeld.argtypes = []
        self.dll.IsCtrlHeld.restype = ctypes.c_bool

        self.dll.SetGlobalHotkey.argtypes = [ctypes.c_char_p, KEYBOARD_CALLBACK]
        self.dll.SetGlobalHotkey.restype = None

        self.dll.ClearGlobalHotkey.argtypes = []
        self.dll.ClearGlobalHotkey.restype = None

        self.dll.ReleaseAllModifierKeys.argtypes = []
        self.dll.ReleaseAllModifierKeys.restype = None

        # 特殊应用支持（可选，兼容旧DLL）
        try:
            self.dll.SetSpecialApps.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int]
            self.dll.SetSpecialApps.restype = None
            self.dll.ClearSpecialApps.argtypes = []
            self.dll.ClearSpecialApps.restype = None
            self._has_special_apps = True
        except AttributeError:
            self._has_special_apps = False

        # 保持回调引用防止GC
        self._mouse_callback_ref = None
        self._alt_dclick_callback_ref = None
        self._keyboard_callback_ref = None
        self._hotkey_callback_ref = None

    def install_mouse_hook(self, callback: Callable[[int, int], None]) -> bool:
        """安装鼠标钩子"""
        self._mouse_callback_ref = MOUSE_CALLBACK(callback)
        return self.dll.InstallMouseHook(self._mouse_callback_ref)

    def uninstall_mouse_hook(self):
        """卸载鼠标钩子"""
        self.dll.UninstallMouseHook()

    def set_mouse_paused(self, paused: bool):
        """设置鼠标钩子暂停状态"""
        self.dll.SetMousePaused(paused)

    def is_mouse_paused(self) -> bool:
        """获取鼠标钩子暂停状态"""
        return self.dll.IsMousePaused()

    def set_alt_double_click_callback(self, callback: Optional[Callable[[int, int], None]]):
        """设置Alt+左键双击回调"""
        if callback:
            self._alt_dclick_callback_ref = MOUSE_CALLBACK(callback)
            self.dll.SetAltDoubleClickCallback(self._alt_dclick_callback_ref)
        else:
            self.dll.SetAltDoubleClickCallback(None)

    def install_keyboard_hook(self, alt_double_tap_callback: Optional[Callable[[], None]] = None) -> bool:
        """安装键盘钩子"""
        if alt_double_tap_callback:
            self._keyboard_callback_ref = KEYBOARD_CALLBACK(alt_double_tap_callback)
        else:
            self._keyboard_callback_ref = KEYBOARD_CALLBACK(lambda: None)
        return self.dll.InstallKeyboardHook(self._keyboard_callback_ref)

    def uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        self.dll.UninstallKeyboardHook()

    def is_alt_held(self) -> bool:
        """获取Alt键按住状态"""
        return self.dll.IsAltHeld()

    def is_ctrl_held(self) -> bool:
        """获取Ctrl键按住状态"""
        return self.dll.IsCtrlHeld()

    def set_hotkey(self, hotkey_str: str, callback: Callable[[], None]):
        """设置全局热键"""
        self._hotkey_callback_ref = KEYBOARD_CALLBACK(callback)
        self.dll.SetGlobalHotkey(hotkey_str.encode('utf-8'), self._hotkey_callback_ref)

    def clear_hotkey(self):
        """清除全局热键"""
        self.dll.ClearGlobalHotkey()

    def release_all_modifier_keys(self):
        """释放所有修饰键"""
        self.dll.ReleaseAllModifierKeys()

    def set_special_apps(self, apps: list):
        """设置特殊应用列表"""
        if not self._has_special_apps:
            return

        if not apps:
            self.dll.ClearSpecialApps()
            return

        # 转换为 C 字符串数组
        c_apps = (ctypes.c_char_p * len(apps))()
        for i, app in enumerate(apps):
            c_apps[i] = app.encode('utf-8')

        self.dll.SetSpecialApps(c_apps, len(apps))

    def clear_special_apps(self):
        """清除特殊应用列表"""
        if self._has_special_apps:
            self.dll.ClearSpecialApps()

