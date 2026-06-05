"""
C++ DLL钩子的Python封装
使用ctypes调用hooks.dll
"""

import ctypes
import hashlib
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime

# 回调函数类型
MOUSE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int)
KEYBOARD_CALLBACK = ctypes.CFUNCTYPE(None)
logger = logging.getLogger(__name__)


class HooksDLL:
    EXPECTED_VERSION = 4
    REQUIRED_EXPORTS = (
        "InstallMouseHook",
        "UninstallMouseHook",
        "SetMousePaused",
        "IsMousePaused",
        "SetAltDoubleClickCallback",
        "InstallKeyboardHook",
        "UninstallKeyboardHook",
        "IsAltHeld",
        "IsCtrlHeld",
        "SetGlobalHotkey",
        "ClearGlobalHotkey",
        "ReleaseAllModifierKeys",
    )
    _last_probe = {}
    _instance = None
    _instance_lock = threading.Lock()
    _load_attempted = False

    @classmethod
    def reset(cls) -> None:
        """清除加载状态，允许下次 get_instance() 重新尝试加载 DLL。

        适用于 DLL 文件从不可用变为可用的场景（如安装过程中 DLL 部署延迟）。
        """
        with cls._instance_lock:
            if cls._instance is not None:
                try:
                    if cls._instance.dll is not None:
                        cls._instance.dll = None
                        cls._instance.loaded = False
                except Exception:
                    pass
            cls._instance = None
            cls._load_attempted = False

    @classmethod
    def get_instance(cls, dll_path: str = None) -> "HooksDLL":
        """获取单例实例，避免多次加载DLL导致GC回调问题"""
        if cls._instance is not None and cls._instance.dll is not None:
            return cls._instance
        with cls._instance_lock:
            if cls._instance is not None and cls._instance.dll is not None:
                return cls._instance
            if cls._load_attempted and cls._instance is not None:
                # DLL 加载已尝试过但失败了，不再重复创建实例
                return cls._instance
            cls._load_attempted = True
            cls._instance = cls(dll_path)
            return cls._instance

    def __init__(self, dll_path: str = None):
        if dll_path is None:
            hooks_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(hooks_dir, "hooks.dll")
        dll_path = os.path.abspath(dll_path)
        self.dll_path = dll_path
        self.dll = None
        self.loaded = False
        self.compatible = False
        self.load_error = ""
        self.missing_exports = []
        self.version = None
        self.capabilities = 0
        self._has_special_apps = False
        self._has_last_error = False
        self._has_hook_health = False
        try:
            self.dll = ctypes.CDLL(dll_path)
            self.loaded = True
        except Exception as e:
            self.load_error = str(e)
            HooksDLL._last_probe = self.get_diagnostics()
            logger.error("hooks.dll load failed: %s", e)
            self._init_callback_refs()
            return

        self._bind_required_exports()
        self._bind_optional_exports()
        self.compatible = self.loaded and not self.missing_exports

        # 保持回调引用防止GC
        self._init_callback_refs()
        HooksDLL._last_probe = self.get_diagnostics()

    def _init_callback_refs(self):
        self._mouse_callback_ref = None
        self._alt_dclick_callback_ref = None
        self._keyboard_callback_ref = None
        self._hotkey_callback_ref = None

    def _bind_required_exports(self):
        for name in self.REQUIRED_EXPORTS:
            if not hasattr(self.dll, name):
                self.missing_exports.append(name)

        if self.missing_exports:
            logger.warning("hooks.dll missing exports: %s", self.missing_exports)
            return

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
        self.dll.SetGlobalHotkey.restype = ctypes.c_bool
        self.dll.ClearGlobalHotkey.argtypes = []
        self.dll.ClearGlobalHotkey.restype = None
        self.dll.ReleaseAllModifierKeys.argtypes = []
        self.dll.ReleaseAllModifierKeys.restype = None

    def _bind_optional_exports(self):
        # 特殊应用支持（可选，兼容旧DLL）
        try:
            self.dll.SetSpecialApps.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int]
            self.dll.SetSpecialApps.restype = None
            self.dll.ClearSpecialApps.argtypes = []
            self.dll.ClearSpecialApps.restype = None
            self._has_special_apps = True
        except AttributeError:
            self._has_special_apps = False

        try:
            self.dll.GetHooksVersion.argtypes = []
            self.dll.GetHooksVersion.restype = ctypes.c_int
            self.version = int(self.dll.GetHooksVersion())
        except AttributeError:
            self.version = None

        try:
            self.dll.GetHooksCapabilities.argtypes = []
            self.dll.GetHooksCapabilities.restype = ctypes.c_uint
            self.capabilities = int(self.dll.GetHooksCapabilities())
        except AttributeError:
            self.capabilities = 0

        try:
            self.dll.GetLastHookError.argtypes = []
            self.dll.GetLastHookError.restype = ctypes.c_ulong
            self._has_last_error = True
        except AttributeError:
            self._has_last_error = False

        try:
            self.dll.IsMouseHookInstalled.argtypes = []
            self.dll.IsMouseHookInstalled.restype = ctypes.c_bool
            self.dll.IsKeyboardHookInstalled.argtypes = []
            self.dll.IsKeyboardHookInstalled.restype = ctypes.c_bool
            self._has_hook_health = True
        except AttributeError:
            self._has_hook_health = False

        # 触发配置支持（可选）
        try:
            self.dll.SetTriggerConfig.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.dll.SetTriggerConfig.restype = None
            self._has_trigger_config = True
        except AttributeError:
            self._has_trigger_config = False

        # 扩展触发配置支持（可选）
        try:
            self.dll.SetTriggerConfigEx.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
            ]
            self.dll.SetTriggerConfigEx.restype = None
            self._has_trigger_config_ex = True
        except AttributeError:
            self._has_trigger_config_ex = False

    def get_last_hook_error(self) -> int:
        if self.dll is None or not getattr(self, "_has_last_error", False):
            return 0
        try:
            return int(self.dll.GetLastHookError())
        except Exception:
            return 0

    def is_mouse_hook_installed(self) -> bool:
        if self.dll is None or not getattr(self, "_has_hook_health", False):
            return False
        try:
            return bool(self.dll.IsMouseHookInstalled())
        except Exception:
            return False

    def is_keyboard_hook_installed(self) -> bool:
        if self.dll is None or not getattr(self, "_has_hook_health", False):
            return False
        try:
            return bool(self.dll.IsKeyboardHookInstalled())
        except Exception:
            return False

    def get_diagnostics(self) -> dict:
        compatible = bool(self.loaded and not self.missing_exports)
        version_ok = self.version is None or self.version >= self.EXPECTED_VERSION
        summary = "hooks.dll 可用" if compatible and version_ok else "hooks.dll 需要更新或不可用"
        file_info = _dll_file_info(self.dll_path)
        return {
            "path": self.dll_path,
            "path_resolved": file_info["path_resolved"],
            "exists": file_info["exists"],
            "size_bytes": file_info["size_bytes"],
            "mtime": file_info["mtime"],
            "sha256": file_info["sha256"],
            "loaded": self.loaded,
            "compatible": compatible and version_ok,
            "version": self.version,
            "expected_version": self.EXPECTED_VERSION,
            "capabilities": self.capabilities,
            "has_hook_health": bool(getattr(self, "_has_hook_health", False)),
            "mouse_hook_installed": self.is_mouse_hook_installed(),
            "keyboard_hook_installed": self.is_keyboard_hook_installed(),
            "missing_exports": list(self.missing_exports),
            "load_error": self.load_error,
            "last_hook_error": self.get_last_hook_error(),
            "summary": summary,
        }

    @classmethod
    def probe_default(cls) -> dict:
        try:
            return cls().get_diagnostics()
        except Exception as e:
            return {"loaded": False, "compatible": False, "summary": "hooks.dll 检测失败", "load_error": str(e)}

    def _ready(self) -> bool:
        return bool(self.loaded and self.compatible and self.dll is not None)

    def install_mouse_hook(self, callback: Callable[[int, int], None]) -> bool:
        """安装鼠标钩子"""
        if not self._ready():
            return False
        self._mouse_callback_ref = MOUSE_CALLBACK(callback)
        ok = bool(self.dll.InstallMouseHook(self._mouse_callback_ref))
        if not ok:
            logger.warning("InstallMouseHook failed, last_error=%s", self.get_last_hook_error())
        return ok

    def uninstall_mouse_hook(self):
        """卸载鼠标钩子"""
        if self._ready():
            self.dll.UninstallMouseHook()

    def set_mouse_paused(self, paused: bool):
        """设置鼠标钩子暂停状态"""
        if self._ready():
            self.dll.SetMousePaused(paused)

    def is_mouse_paused(self) -> bool:
        """获取鼠标钩子暂停状态"""
        if not self._ready():
            return False
        return self.dll.IsMousePaused()

    def set_alt_double_click_callback(self, callback: Callable[[int, int], None] | None):
        """设置Alt+左键双击回调"""
        if callback:
            self._alt_dclick_callback_ref = MOUSE_CALLBACK(callback)
            if self._ready():
                self.dll.SetAltDoubleClickCallback(self._alt_dclick_callback_ref)
        else:
            if self._ready():
                self.dll.SetAltDoubleClickCallback(None)

    def install_keyboard_hook(self, alt_double_tap_callback: Callable[[], None] | None = None) -> bool:
        """安装键盘钩子"""
        if alt_double_tap_callback:
            self._keyboard_callback_ref = KEYBOARD_CALLBACK(alt_double_tap_callback)
        else:
            self._keyboard_callback_ref = KEYBOARD_CALLBACK(lambda: None)
        if not self._ready():
            return False
        ok = bool(self.dll.InstallKeyboardHook(self._keyboard_callback_ref))
        if not ok:
            logger.warning("InstallKeyboardHook failed, last_error=%s", self.get_last_hook_error())
        return ok

    def uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        if self._ready():
            self.dll.UninstallKeyboardHook()

    def is_alt_held(self) -> bool:
        """获取Alt键按住状态"""
        if not self._ready():
            return False
        return self.dll.IsAltHeld()

    def is_ctrl_held(self) -> bool:
        """获取Ctrl键按住状态"""
        if not self._ready():
            return False
        return self.dll.IsCtrlHeld()

    def set_hotkey(self, hotkey_str: str, callback: Callable[[], None]):
        """设置全局热键"""
        if not self._ready():
            return False
        self._hotkey_callback_ref = KEYBOARD_CALLBACK(callback)
        return bool(self.dll.SetGlobalHotkey(hotkey_str.encode("utf-8"), self._hotkey_callback_ref))

    def clear_hotkey(self):
        """清除全局热键"""
        if self._ready():
            self.dll.ClearGlobalHotkey()

    def release_all_modifier_keys(self):
        """释放所有修饰键"""
        if self._ready():
            self.dll.ReleaseAllModifierKeys()

    def set_special_apps(self, apps: list):
        """设置特殊应用列表"""
        if not self._ready() or not self._has_special_apps:
            return

        if not apps:
            self.dll.ClearSpecialApps()
            return

        # 转换为 C 字符串数组
        c_apps = (ctypes.c_char_p * len(apps))()
        for i, app in enumerate(apps):
            c_apps[i] = app.encode("utf-8")

        self.dll.SetSpecialApps(c_apps, len(apps))

    def clear_special_apps(self):
        """清除特殊应用列表"""
        if self._ready() and self._has_special_apps:
            self.dll.ClearSpecialApps()

    def set_trigger_config(self, normal_button: str, normal_modifiers: list[str],
                           special_button: str, special_modifiers: list[str]):
        """设置触发按键配置"""
        if not self._ready() or not self._has_trigger_config:
            logger.warning("hooks.dll 不支持基础触发配置或尚未就绪")
            return

        from core.trigger_config import normalize_trigger_config

        normal = normalize_trigger_config("mouse", [], normal_button, normal_modifiers, fill_defaults=True)
        special = normalize_trigger_config(
            "mouse", [], special_button, special_modifiers, fill_defaults=True, default_modifiers=["ctrl"]
        )
        btn_map = {"left": 1, "right": 2, "middle": 4, "x1": 8, "x2": 16}
        mod_map = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}

        normal_btn = btn_map.get(normal.button, 4)
        normal_mod = sum(mod_map.get(m, 0) for m in normal.modifiers)
        special_btn = btn_map.get(special.button, 4)
        special_mod = sum(mod_map.get(m, 0) for m in special.modifiers)

        self.dll.SetTriggerConfig(normal_btn, normal_mod, special_btn, special_mod)

    def set_trigger_config_ex(self, normal_mode: str, normal_button: str, normal_keys: list[str],
                              normal_modifiers: list[str], special_mode: str, special_button: str,
                              special_keys: list[str], special_modifiers: list[str]):
        """设置扩展触发按键配置（支持keyboard/mouse/hybrid模式）"""
        if not self._ready() or not self._has_trigger_config_ex:
            logger.warning("hooks.dll 不支持扩展触发配置或尚未就绪")
            return

        from core.trigger_config import normalize_trigger_config

        normal = normalize_trigger_config(
            normal_mode, normal_keys, normal_button, normal_modifiers, fill_defaults=True
        )
        special = normalize_trigger_config(
            special_mode, special_keys, special_button, special_modifiers, fill_defaults=True, default_modifiers=["ctrl"]
        )
        mode_map = {"keyboard": 1, "mouse": 0, "hybrid": 2}
        btn_map = {"left": 1, "right": 2, "middle": 4, "x1": 8, "x2": 16}
        mod_map = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}

        normal_mode_int = mode_map.get(normal.mode, 0)
        normal_btn = btn_map.get(normal.button, 4)
        normal_vks = [self._key_to_vk(k) for k in normal.keys]
        normal_keys_vk = ",".join(str(vk) for vk in normal_vks if vk)
        normal_mod = sum(mod_map.get(m, 0) for m in normal.modifiers)

        special_mode_int = mode_map.get(special.mode, 0)
        special_btn = btn_map.get(special.button, 4)
        special_vks = [self._key_to_vk(k) for k in special.keys]
        special_keys_vk = ",".join(str(vk) for vk in special_vks if vk)
        special_mod = sum(mod_map.get(m, 0) for m in special.modifiers)

        self.dll.SetTriggerConfigEx(
            normal_mode_int, normal_btn, normal_keys_vk.encode("utf-8"), normal_mod,
            special_mode_int, special_btn, special_keys_vk.encode("utf-8"), special_mod
        )

    @staticmethod
    def _key_to_vk(key: str) -> int:
        """将按键字符串转换为VK码"""
        from hooks.key_map import key_to_vk

        return key_to_vk(key)


def _dll_file_info(path: str) -> dict:
    info = {
        "path_resolved": "",
        "exists": False,
        "size_bytes": 0,
        "mtime": "",
        "sha256": "",
    }
    try:
        resolved = os.path.abspath(path or "")
        info["path_resolved"] = resolved
        if not os.path.isfile(resolved):
            return info
        stat = os.stat(resolved)
        info["exists"] = True
        info["size_bytes"] = int(stat.st_size)
        info["mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        digest = hashlib.sha256()
        with open(resolved, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        info["sha256"] = digest.hexdigest()
    except Exception as exc:
        logger.debug("hooks.dll file diagnostics failed: %s", exc)
    return info
