"""
鼠标/键盘钩子管理相关方法。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from core.executor_manager import PROCESS_CHECK_EXECUTOR, ManagedExecutor, get_executor, shutdown_executor
from qt_compat import QTimer

if TYPE_CHECKING:
    from hooks.mouse_hook_dll import MouseHook

logger = logging.getLogger(__name__)

_HOOK_INSTALL_RETRY_DELAYS_MS = (500, 2000, 5000)


def _get_process_check_executor() -> ManagedExecutor:
    return get_executor(PROCESS_CHECK_EXECUTOR)


def shutdown_process_check_executor() -> None:
    shutdown_executor(PROCESS_CHECK_EXECUTOR, timeout=3.0)


def _collect_special_process_pids(target_apps: set[str], cancel_event: threading.Event | None = None) -> set[int]:
    import psutil

    current_pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        if cancel_event is not None and cancel_event.is_set():
            break
        try:
            name = str(proc.info.get("name") or "").lower()
            if any(app in name for app in target_apps):
                current_pids.add(int(proc.info["pid"]))
        except Exception as exc:
            logger.debug("获取进程信息失败: %s", exc, exc_info=True)
    return current_pids


class HooksMixin:
    """鼠标/键盘钩子管理相关方法。"""

    mouse_hook: MouseHook | None
    keyboard_hook: Any
    _sleeping: bool
    _taskbar_double_click_signal: Any

    def _install_hook(self, attempt: int = 0):
        """安装鼠标钩子"""
        if self._install_mouse_backend():
            return

        if attempt < len(_HOOK_INSTALL_RETRY_DELAYS_MS):
            delay = _HOOK_INSTALL_RETRY_DELAYS_MS[attempt]
            logger.warning(
                "鼠标钩子安装失败，%sms 后重试 (%s/%s)", delay, attempt + 1, len(_HOOK_INSTALL_RETRY_DELAYS_MS)
            )
            QTimer.singleShot(delay, lambda: self._install_hook(attempt + 1))
            return

        logger.error("鼠标钩子连续安装失败")

    def _install_mouse_backend(self) -> bool:
        """安装 DLL 鼠标后端。hooks.dll 是全局单例，必须按单实例方式重装。"""
        try:
            from hooks.mouse_hook_dll import MouseHook

            if self.mouse_hook:
                try:
                    self.mouse_hook.uninstall()
                except Exception as exc:
                    logger.debug("卸载鼠标钩子失败: %s", exc, exc_info=True)
                self.mouse_hook = None

            hook = MouseHook()
            success = hook.install(self._on_middle_click_from_hook)  # type: ignore[attr-defined]
            if not success:
                return False

            if self.keyboard_hook:
                try:
                    hook.set_keyboard_hook(self.keyboard_hook)
                except Exception as exc:
                    logger.debug("关联键盘钩子失败: %s", exc, exc_info=True)

            try:
                hook.set_paused(self._mouse_paused_state)
            except Exception as exc:
                logger.debug("设置鼠标钩子暂停状态失败: %s", exc, exc_info=True)
            self.mouse_hook = hook

            # 注册任务栏双击回调
            if hasattr(hook, "set_taskbar_callback"):
                hook.set_taskbar_callback(self._on_taskbar_double_click_from_hook)

            # 设置全局钩子引用，供文件对话框使用
            try:
                from ui.utils.safe_file_dialog import set_global_mouse_hook

                set_global_mouse_hook(hook)
            except Exception as exc:
                logger.debug("设置全局鼠标钩子失败: %s", exc, exc_info=True)

            self._apply_mouse_hook_settings()

            logger.info("鼠标触发已切换到 DLL Hook")
            return True
        except Exception:
            logger.exception("安装鼠标后端失败 [dll_hook]")
            self.mouse_hook = None
            return False

    def _install_keyboard_hook(self):
        """安装键盘钩子 (Alt双击检测 + Alt按住状态)"""
        try:
            from hooks.keyboard_hook_dll import KeyboardHook

            if self.keyboard_hook:
                try:
                    self.keyboard_hook.uninstall()
                except Exception as exc:
                    logger.debug("卸载旧键盘钩子失败: %s", exc, exc_info=True)
            self.keyboard_hook = KeyboardHook()

            # 设置全局键盘钩子引用，供文件对话框使用
            try:
                from ui.utils.safe_file_dialog import set_global_keyboard_hook

                set_global_keyboard_hook(self.keyboard_hook)
            except Exception as exc:
                logger.debug("设置全局键盘钩子失败: %s", exc, exc_info=True)

            success = self.keyboard_hook.install(on_alt_double_tap=self._on_alt_double_tap_from_hook)

            if success:
                logger.info("键盘钩子安装成功")
                # 将键盘钩子传给鼠标钩子（用于检测 Alt 按住状态）
                if self.mouse_hook:
                    self.mouse_hook.set_keyboard_hook(self.keyboard_hook)
            else:
                logger.warning("  键盘钩子安装失败")
                self.keyboard_hook = None

        except Exception:
            logger.exception("键盘钩子异常")
            self.keyboard_hook = None

    def _check_hook_health(self):
        """Periodically recover DLL hooks if Windows reports them missing."""
        try:
            if getattr(self, "_sleeping", False):
                return

            mouse_hook = getattr(self, "mouse_hook", None)
            keyboard_hook = getattr(self, "keyboard_hook", None)
            mouse_missing = mouse_hook is None or (
                hasattr(mouse_hook, "is_installed") and not mouse_hook.is_installed()
            )
            keyboard_missing = keyboard_hook is None or (
                hasattr(keyboard_hook, "is_installed") and not keyboard_hook.is_installed()
            )

            dll = getattr(mouse_hook, "_dll", None) or getattr(keyboard_hook, "_dll", None)
            runtime_stats = dll.get_runtime_stats() if dll and hasattr(dll, "get_runtime_stats") else {}
            previous = getattr(self, "_last_hook_runtime_stats", {})
            self._last_hook_runtime_stats = runtime_stats
            if runtime_stats and previous:
                dropped_delta = runtime_stats.get("callback_queue_dropped", 0) - previous.get(
                    "callback_queue_dropped", 0
                )
                exception_delta = runtime_stats.get("callback_exceptions", 0) - previous.get("callback_exceptions", 0)
                if dropped_delta > 0 or exception_delta > 0:
                    logger.warning(
                        "钩子回调通道出现异常: dropped_delta=%s exception_delta=%s queue_depth=%s",
                        dropped_delta,
                        exception_delta,
                        runtime_stats.get("callback_queue_depth", 0),
                    )
            if mouse_missing or keyboard_missing:
                logger.warning(
                    "检测到钩子健康异常，准备自动重装: mouse_missing=%s keyboard_missing=%s",
                    mouse_missing,
                    keyboard_missing,
                )
                self._reinstall_hooks(mouse=mouse_missing, keyboard=keyboard_missing)
        except Exception as exc:
            logger.debug("检查钩子健康状态失败: %s", exc, exc_info=True)

    def _install_keyboard_hook_and_hotkey(self):
        """安装键盘钩子（延迟执行）。"""
        self._install_keyboard_hook()

    def _reinstall_hooks(self, *, mouse: bool = True, keyboard: bool = True):
        """重装钩子以保持优先级（轻量级，仅卸载重装）"""
        if getattr(self, "_hook_reinstall_in_progress", False):
            return False
        try:
            now = time.monotonic()
            if now < self._hook_reinstall_cooldown_until:  # type: ignore[has-type]
                return False
            self._hook_reinstall_in_progress = True

            success = True
            if mouse:
                mouse_backend_ok = self._install_mouse_backend()
                mouse_hook = getattr(self, "mouse_hook", None)
                if mouse_backend_ok and mouse_hook is not None and hasattr(mouse_hook, "is_installed"):
                    mouse_backend_ok = bool(mouse_hook.is_installed())
                success = mouse_backend_ok

            if keyboard:
                self._install_keyboard_hook()
                keyboard_ok = bool(self.keyboard_hook and self.keyboard_hook.is_installed())
                success = success and keyboard_ok

            if success:
                self._hook_reinstall_failures = 0
                self._hook_reinstall_cooldown_until = now + 1.0
                return True

            failures = int(getattr(self, "_hook_reinstall_failures", 0)) + 1
            self._hook_reinstall_failures = failures
            delay = min(30.0, float(2 ** min(failures, 5)))
            self._hook_reinstall_cooldown_until = now + delay
            logger.warning("钩子重装未完全成功，%.1fs 后再次检查", delay)
            return False
        except Exception as exc:
            logger.debug("重装键盘钩子失败: %s", exc, exc_info=True)
            failures = int(getattr(self, "_hook_reinstall_failures", 0)) + 1
            self._hook_reinstall_failures = failures
            self._hook_reinstall_cooldown_until = time.monotonic() + min(30.0, float(2 ** min(failures, 5)))
            return False
        finally:
            self._hook_reinstall_in_progress = False

    def _check_new_processes(self):
        """检测特定软件启动时重装钩子（仅监测可能有钩子冲突的软件）"""
        try:
            target_apps = set(self._get_special_apps())
            if not target_apps:
                self._known_processes = set()
                self._process_check_cancel_event = None
                return

            future = getattr(self, "_process_check_future", None)
            if future is not None and not future.done():
                return
            cancel_event = threading.Event()
            self._process_check_cancel_event = cancel_event
            future = _get_process_check_executor().submit(_collect_special_process_pids, target_apps, cancel_event)
            self._process_check_future = future
            future.add_done_callback(self._emit_process_check_done)
        except Exception as exc:
            logger.debug("提交特殊应用监控任务失败: %s", exc, exc_info=True)

    def _emit_process_check_done(self, future):
        try:
            signal = getattr(self, "_process_check_done_signal", None)
            if signal is not None:
                signal.emit(future)
        except Exception as exc:
            logger.debug("发送特殊应用监控结果失败: %s", exc, exc_info=True)

    def _on_process_check_done(self, future):
        try:
            if getattr(self, "_process_check_future", None) is future:
                self._process_check_future = None
                self._process_check_cancel_event = None
            current_pids = set(future.result())
            if not self._known_processes:
                self._known_processes = current_pids
                return

            new_pids = current_pids - self._known_processes
            if new_pids:
                logger.info("检测到目标软件启动，重装钩子以保持优先级")
                self._reinstall_hooks()

            self._known_processes = current_pids
        except Exception as exc:
            logger.debug("更新特殊应用监控失败: %s", exc, exc_info=True)

    def _on_alt_double_tap_from_hook(self):
        """Alt双击回调 (从键盘钩子线程调用，必须极快返回)"""
        try:
            self._alt_double_tap_signal.emit()
        except Exception as exc:
            logger.debug("发送Alt双击信号失败: %s", exc, exc_info=True)

    def _on_alt_double_tap(self):
        """处理 Alt 双击 - 切换鼠标中键钩子暂停状态 (主线程)"""
        try:
            if not self.mouse_hook:
                return

            # 切换暂停状态
            new_paused = not self.mouse_hook.is_paused()
            self._mouse_paused_state = new_paused
            self.mouse_hook.set_paused(new_paused)
            if self._sleeping:
                logger.info(
                    "轻睡眠中 Alt双击: 鼠标中键%s",
                    "已禁用" if new_paused else "已恢复",
                )

            # 获取当前主题
            theme = "dark"
            try:
                settings = self.data_manager.get_settings()
                theme = getattr(settings, "theme", "dark") or "dark"
            except Exception as exc:
                logger.debug("获取主题设置失败: %s", exc, exc_info=True)

            # 显示 Toast 通知
            if new_paused:
                text = "已关闭鼠标中键"
            else:
                text = "已开启鼠标中键"

            self._show_toast(text, theme)
            logger.info(f"Alt双击: 鼠标中键钩子 {'已暂停' if new_paused else '已恢复'}")
            self._mark_activity("alt_double_tap")

        except Exception as e:
            logger.error(f"处理Alt双击失败: {e}")

    def _get_special_apps(self):
        try:
            settings = self.data_manager.get_settings()
            return [
                str(app or "").strip().lower()
                for app in (getattr(settings, "special_apps", []) or [])
                if str(app or "").strip()
            ]
        except Exception:
            return []

    def _get_special_apps_for_hook(self):
        expanded_apps = []
        seen = set()

        for raw_app in self._get_special_apps():
            app = str(raw_app or "").strip().lower()
            if not app:
                continue
            candidates = [app]
            if app.endswith(".exe"):
                base_name = app[:-4].strip()
                if base_name:
                    candidates.append(base_name)
            else:
                candidates.append(f"{app}.exe")

            for candidate in candidates:
                normalized = str(candidate or "").strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    expanded_apps.append(normalized)

        return expanded_apps

    def _reset_special_app_monitor_state(self):
        self._known_processes = set()

    def _update_special_app_monitors(self, reset_state: bool = False):
        special_apps = self._get_special_apps()

        if reset_state:
            self._reset_special_app_monitor_state()

        if not special_apps:
            if self._process_check_timer.isActive():  # type: ignore[attr-defined]
                self._process_check_timer.stop()  # type: ignore[attr-defined]
            self._special_app_monitors_active = False
            return

        if not self._special_app_monitors_active:
            self._process_check_timer.start()  # type: ignore[attr-defined]
            self._special_app_monitors_active = True

    def _apply_mouse_hook_settings(self) -> bool:
        """将特殊应用配置同步到 DLL 鼠标钩子"""
        if not self.mouse_hook:
            logger.warning("鼠标钩子未初始化，无法应用配置")
            return False

        special_apps = self._get_special_apps_for_hook()
        self.mouse_hook.set_special_apps(special_apps)
        logger.info(f"已同步特殊应用列表[dll_hook]，共 {len(special_apps)} 个")

        # 应用触发配置
        trigger_config_applied = False
        try:
            settings = self.data_manager.get_settings()  # type: ignore[attr-defined]
            from core.trigger_config import normalize_trigger_settings

            trigger_settings = normalize_trigger_settings(settings)
            # 优先使用扩展接口
            if hasattr(self.mouse_hook, "set_trigger_config_ex"):
                normal_mode = trigger_settings["popup_trigger_mode"]
                normal_keys = trigger_settings["popup_trigger_keys"]
                normal_button = trigger_settings["popup_trigger_button"]
                normal_modifiers = trigger_settings["popup_trigger_modifiers"]
                special_mode = trigger_settings["popup_special_trigger_mode"]
                special_keys = trigger_settings["popup_special_trigger_keys"]
                special_button = trigger_settings["popup_special_trigger_button"]
                special_modifiers = trigger_settings["popup_special_trigger_modifiers"]

                requires_keyboard_hook = normal_mode in {"keyboard", "hybrid"} or special_mode in {
                    "keyboard",
                    "hybrid",
                }
                keyboard_hook = getattr(self, "keyboard_hook", None)
                keyboard_hook_ready = bool(
                    keyboard_hook and (not hasattr(keyboard_hook, "is_installed") or keyboard_hook.is_installed())
                )
                if requires_keyboard_hook and not keyboard_hook_ready:
                    logger.info("键盘触发配置需要键盘钩子，立即安装")
                    self._install_keyboard_hook()
                    keyboard_hook = getattr(self, "keyboard_hook", None)
                    if keyboard_hook and self.mouse_hook:
                        self.mouse_hook.set_keyboard_hook(keyboard_hook)

                trigger_config_applied = bool(
                    self.mouse_hook.set_trigger_config_ex(
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
                logger.info(
                    "已应用扩展触发配置: 普通=%s(%s)+%s+%s, 特殊=%s(%s)+%s+%s",
                    normal_mode,
                    normal_keys,
                    normal_button,
                    normal_modifiers,
                    special_mode,
                    special_keys,
                    special_button,
                    special_modifiers,
                )

                # 延迟检测 RegisterHotKey 是否成功（DLL 通过 PostThreadMessage 异步注册）
                if normal_mode == "keyboard" or special_mode == "keyboard":
                    QTimer.singleShot(500, self._check_trigger_hotkey_status)
            elif hasattr(self.mouse_hook, "set_trigger_config"):
                trigger_config_applied = bool(
                    self.mouse_hook.set_trigger_config(
                        trigger_settings["popup_trigger_button"],
                        trigger_settings["popup_trigger_modifiers"],
                        trigger_settings["popup_special_trigger_button"],
                        trigger_settings["popup_special_trigger_modifiers"],
                    )
                )
                logger.info(
                    "已应用触发配置: 普通=%s+%s, 特殊=%s+%s",
                    trigger_settings["popup_trigger_button"],
                    trigger_settings["popup_trigger_modifiers"],
                    trigger_settings["popup_special_trigger_button"],
                    trigger_settings["popup_special_trigger_modifiers"],
                )
            else:
                logger.warning("鼠标钩子不支持触发配置方法，可能是旧版DLL")
                trigger_config_applied = False
        except Exception as e:
            logger.error(f"应用触发配置失败: {e}", exc_info=True)
            trigger_config_applied = False

        # 应用任务栏触发设置（独立 try，不影响主逻辑）
        taskbar_config_applied = True
        try:
            settings = self.data_manager.get_settings()  # type: ignore[attr-defined]
            taskbar_source = getattr(settings, "popup_trigger_source", "mouse")
            taskbar_ctrl = getattr(settings, "popup_taskbar_trigger_ctrl", False)
            special_taskbar_source = getattr(settings, "popup_special_trigger_source", "mouse")
            special_taskbar_ctrl = getattr(settings, "popup_special_taskbar_trigger_ctrl", False)
            taskbar_enabled = (taskbar_source == "taskbar") or (special_taskbar_source == "taskbar")
            taskbar_ctrl_final = taskbar_ctrl or special_taskbar_ctrl
            taskbar_interval_ms = int(getattr(settings, "double_click_interval", 400) or 400)
            if hasattr(self.mouse_hook, "set_taskbar_trigger"):
                taskbar_config_applied = bool(
                    self.mouse_hook.set_taskbar_trigger(taskbar_enabled, taskbar_ctrl_final, taskbar_interval_ms)
                )
                if taskbar_config_applied:
                    self._taskbar_trigger_enabled = taskbar_enabled
                logger.info(
                    "任务栏触发: %s (ctrl=%s interval_ms=%s)",
                    "已启用" if taskbar_enabled else "已禁用",
                    taskbar_ctrl_final,
                    taskbar_interval_ms,
                )
            elif taskbar_enabled:
                logger.warning("鼠标钩子不支持任务栏触发方法，无法启用任务栏触发")
                taskbar_config_applied = False
        except Exception as e2:
            logger.debug("应用任务栏触发设置失败: %s", e2, exc_info=True)
            taskbar_config_applied = False

        return trigger_config_applied and taskbar_config_applied

    def _check_trigger_hotkey_status(self):
        """延迟检测 RegisterHotKey 注册状态，失败时记录详细日志供排查。"""
        try:
            if not self.mouse_hook:
                return

            normal_registered = (
                self.mouse_hook.is_normal_trigger_hotkey_registered()
                if hasattr(self.mouse_hook, "is_normal_trigger_hotkey_registered")
                else True  # DLL 不支持查询，假设已注册
            )
            special_registered = (
                self.mouse_hook.is_special_trigger_hotkey_registered()
                if hasattr(self.mouse_hook, "is_special_trigger_hotkey_registered")
                else True
            )

            settings = self.data_manager.get_settings()
            normal_mode = getattr(settings, "popup_trigger_mode", "mouse")
            special_mode = getattr(settings, "popup_special_trigger_mode", "mouse")

            if normal_mode == "keyboard" and not normal_registered:
                normal_keys = getattr(settings, "popup_trigger_keys", [])
                normal_mods = getattr(settings, "popup_trigger_modifiers", [])
                hotkey_str = "+".join([*normal_mods, *normal_keys])
                logger.warning(
                    "普通触发键盘快捷键 RegisterHotKey 注册失败: %s。"
                    "该快捷键可能已被系统或其他程序占用（如输入法IME），"
                    "将使用异步轮询备用通道（延迟约10-80ms）",
                    hotkey_str,
                )

            if special_mode == "keyboard" and not special_registered:
                special_keys = getattr(settings, "popup_special_trigger_keys", [])
                special_mods = getattr(settings, "popup_special_trigger_modifiers", [])
                hotkey_str = "+".join([*special_mods, *special_keys])
                logger.warning(
                    "特殊触发键盘快捷键 RegisterHotKey 注册失败: %s。"
                    "该快捷键可能已被系统或其他程序占用，"
                    "将使用异步轮询备用通道（延迟约10-80ms）",
                    hotkey_str,
                )
        except Exception as exc:
            logger.debug("检测触发热键注册状态失败: %s", exc, exc_info=True)
        """同步特殊应用设置到鼠标钩子"""
        try:
            if self._sleeping:
                self._reset_special_app_monitor_state()
                if self._process_check_timer.isActive():
                    self._process_check_timer.stop()
                self._special_app_monitors_active = False
            else:
                self._update_special_app_monitors(reset_state=True)
            if self.mouse_hook:
                self._apply_mouse_hook_settings()

        except Exception as e:
            logger.error(f"同步特殊应用设置失败: {e}")

    def _on_taskbar_double_click_from_hook(self, x: int, y: int):
        """任务栏双击回调 (从 DLL 线程调用，发射信号转到主线程)"""
        try:
            self._taskbar_double_click_signal.emit(x, y)
        except Exception as exc:
            logger.debug("发射任务栏双击信号失败: %s", exc, exc_info=True)

    def _on_taskbar_double_click(self, x: int, y: int):
        """处理任务栏双击 (主线程)"""
        try:
            if self._sleeping:
                self._wake_from_sleep("taskbar_double_click")  # type: ignore[attr-defined]
            if not self.mouse_hook or self.mouse_hook.is_paused():
                return
            if not getattr(self, "_taskbar_trigger_enabled", False):
                return
            self._on_show_popup(x, y)  # type: ignore[attr-defined]
            self._mark_activity("taskbar_double_click")  # type: ignore[attr-defined]
        except Exception as e:
            logger.error(f"处理任务栏双击失败: {e}")
