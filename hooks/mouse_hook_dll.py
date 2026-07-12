"""
鼠标钩子 - DLL版本兼容封装
保持与原Python版本相同的接口
"""

import logging
from collections.abc import Callable

from .hooks_wrapper import HooksDLL

logger = logging.getLogger(__name__)


class MouseHook:
    """鼠标钩子 - 使用C++ DLL实现"""

    def __init__(self):
        self._dll = HooksDLL.get_instance()
        self._callback: Callable[[int, int], None] | None = None
        self._alt_double_click_callback: Callable[[int, int], None] | None = None
        self._keyboard_hook = None

    def set_special_apps(self, apps: list[str]):
        """设置特殊应用列表"""
        self._dll.set_special_apps(apps)

    def install(self, callback: Callable[[int, int], None]) -> bool:
        """安装钩子"""
        self._callback = callback
        success = self._dll.install_mouse_hook(callback)
        if success:
            logger.info(
                "鼠标输入后端安装成功: low_level=%s raw_input=%s",
                self._dll.is_mouse_hook_installed(),
                self._dll.is_raw_input_fallback_active(),
            )
        return success

    def uninstall(self):
        """卸载钩子"""
        self._dll.uninstall_mouse_hook()
        logger.info("鼠标钩子已卸载")

    def set_paused(self, paused: bool):
        """设置暂停状态"""
        self._dll.set_mouse_paused(paused)

    def is_paused(self) -> bool:
        """获取暂停状态"""
        return self._dll.is_mouse_paused()

    def is_installed(self) -> bool:
        """Return whether the DLL reports the mouse hook as installed."""
        return self._dll.is_mouse_hook_installed()

    def set_keyboard_hook(self, kb_hook):
        """设置键盘钩子引用"""
        self._keyboard_hook = kb_hook

    def set_alt_double_click_callback(self, callback: Callable[[int, int], None] | None):
        """设置Alt+左键双击回调"""
        self._alt_double_click_callback = callback
        self._dll.set_alt_double_click_callback(callback)

    def get_stats(self) -> dict:
        """获取统计信息（基于实际 DLL 状态）"""
        try:
            diagnostics = self._dll.get_diagnostics()
            hook_ok = diagnostics.get("loaded", False) and diagnostics.get("compatible", False)
            installed = diagnostics.get("mouse_hook_installed")
            raw_input_active = diagnostics.get("raw_input_fallback_active")
            runtime_stats = diagnostics.get("runtime_stats") or {}
        except Exception as e:
            logger.debug("获取 DLL 诊断信息失败: %s", e)
            hook_ok = False
            installed = None
            raw_input_active = None
            runtime_stats = {}
        return {
            "total_events": runtime_stats.get("low_level_mouse_events"),
            "raw_input_events": runtime_stats.get("raw_mouse_events"),
            "raw_fallback_triggers": runtime_stats.get("raw_fallback_triggers"),
            "safe_mode_activations": None,
            "errors": runtime_stats.get("callback_exceptions"),
            "callback_queue_dropped": runtime_stats.get("callback_queue_dropped"),
            "callback_queue_depth": runtime_stats.get("callback_queue_depth"),
            "is_safe_mode": self.is_paused(),
            "is_blocked": not self._dll.is_ready(),
            "hook_installed": installed,
            "raw_input_fallback_active": raw_input_active,
            "hook_health_ok": hook_ok if installed is None else bool(hook_ok and (installed or raw_input_active)),
        }

    def force_release(self):
        """强制释放所有修饰键"""
        try:
            self._dll.release_all_modifier_keys()
        except Exception as e:
            logger.warning("force_release 失败: %s", e)

    @property
    def alt_held(self) -> bool:
        """Alt键是否按住"""
        return self._dll.is_alt_held()

    def set_trigger_config(
        self, normal_button: str, normal_modifiers: list[str], special_button: str, special_modifiers: list[str]
    ) -> bool:
        """设置触发按键配置"""
        return bool(self._dll.set_trigger_config(normal_button, normal_modifiers, special_button, special_modifiers))

    def set_trigger_config_ex(
        self,
        normal_mode: str,
        normal_button: str,
        normal_keys: list[str],
        normal_modifiers: list[str],
        special_mode: str,
        special_button: str,
        special_keys: list[str],
        special_modifiers: list[str],
    ) -> bool:
        """设置扩展触发按键配置（支持keyboard/mouse/hybrid模式）"""
        return bool(
            self._dll.set_trigger_config_ex(
                normal_mode,
                normal_button,
                normal_keys,
                normal_modifiers,
                special_mode,
                special_button,
                special_keys,
                special_modifiers,
            )
        )

    def set_taskbar_trigger(self, enabled: bool, require_ctrl: bool = False, interval_ms: int = 400):
        """启用/禁用任务栏双击触发（需要 DLL 支持）"""
        if hasattr(self._dll, "set_taskbar_trigger_enabled"):
            result = self._dll.set_taskbar_trigger_enabled(enabled, require_ctrl, interval_ms)
            if result:
                logger.info(
                    "任务栏触发: %s (ctrl=%s interval_ms=%s)",
                    "已启用" if enabled else "已禁用",
                    require_ctrl,
                    interval_ms,
                )
            return bool(result)
        logger.debug("当前 DLL 版本不支持任务栏触发")
        return False

    def set_taskbar_callback(self, callback):
        """设置任务栏双击回调（需要 DLL 支持）"""
        if hasattr(self._dll, "set_taskbar_double_click_callback"):
            result = self._dll.set_taskbar_double_click_callback(callback)
            if result:
                logger.info("任务栏双击回调已设置")
            return bool(result)
        logger.debug("当前 DLL 版本不支持任务栏回调")
        return False

    def is_taskbar_trigger_available(self) -> bool:
        """检测当前系统是否支持任务栏触发"""
        if hasattr(self._dll, "is_taskbar_trigger_available"):
            return bool(self._dll.is_taskbar_trigger_available())
        return False

    def is_normal_trigger_hotkey_registered(self) -> bool:
        """查询普通触发热键是否通过 RegisterHotKey 成功注册."""
        if hasattr(self._dll, "is_normal_trigger_hotkey_registered"):
            return bool(self._dll.is_normal_trigger_hotkey_registered())
        return False

    def is_special_trigger_hotkey_registered(self) -> bool:
        """查询特殊触发热键是否通过 RegisterHotKey 成功注册."""
        if hasattr(self._dll, "is_special_trigger_hotkey_registered"):
            return bool(self._dll.is_special_trigger_hotkey_registered())
        return False
