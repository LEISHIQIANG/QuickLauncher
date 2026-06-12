"""
鼠标/键盘钩子管理相关方法。
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from qt_compat import QTimer

logger = logging.getLogger(__name__)

_HOOK_INSTALL_RETRY_DELAYS_MS = (500, 2000, 5000)
_PROCESS_CHECK_EXECUTOR = None
_PROCESS_CHECK_EXECUTOR_LOCK = threading.Lock()


def _get_process_check_executor() -> ThreadPoolExecutor:
    global _PROCESS_CHECK_EXECUTOR
    with _PROCESS_CHECK_EXECUTOR_LOCK:
        if _PROCESS_CHECK_EXECUTOR is None:
            _PROCESS_CHECK_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="QLProcessCheck")
        return _PROCESS_CHECK_EXECUTOR


def shutdown_process_check_executor() -> None:
    global _PROCESS_CHECK_EXECUTOR
    with _PROCESS_CHECK_EXECUTOR_LOCK:
        executor = _PROCESS_CHECK_EXECUTOR
        _PROCESS_CHECK_EXECUTOR = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


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
            success = hook.install(self._on_middle_click_from_hook)
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
        """安装键盘钩子并启动热键管理器（延迟执行）"""
        self._install_keyboard_hook()
        # 共享键盘钩子的DLL实例
        if self.keyboard_hook and hasattr(self.keyboard_hook, "_dll"):
            self.hotkey_manager._dll = self.keyboard_hook._dll
        self.hotkey_manager.start()

    def _reinstall_hooks(self, *, mouse: bool = True, keyboard: bool = True):
        """重装钩子以保持优先级（轻量级，仅卸载重装）"""
        if getattr(self, "_hook_reinstall_in_progress", False):
            return False
        try:
            now = time.monotonic()
            if now < self._hook_reinstall_cooldown_until:
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
                if keyboard_ok:
                    self.hotkey_manager._dll = self.keyboard_hook._dll
                    current_hotkey = getattr(self.hotkey_manager, "_current_hotkey", None)
                    if current_hotkey:
                        success = bool(self.hotkey_manager.set_hotkey(current_hotkey)) and success

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

    def _on_hook_hotkey_from_hook(self):
        """键盘钩子热键回调 (从钩子线程调用，必须极快返回)"""
        try:
            self._hook_hotkey_signal.emit()
        except Exception as exc:
            logger.debug("发送热键信号失败: %s", exc, exc_info=True)

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
            if self._process_check_timer.isActive():
                self._process_check_timer.stop()
            self._special_app_monitors_active = False
            return

        if not self._special_app_monitors_active:
            self._process_check_timer.start()
            self._special_app_monitors_active = True

    def _apply_mouse_hook_settings(self):
        """将特殊应用配置同步到 DLL 鼠标钩子"""
        if not self.mouse_hook:
            logger.warning("鼠标钩子未初始化，无法应用配置")
            return

        special_apps = self._get_special_apps_for_hook()
        self.mouse_hook.set_special_apps(special_apps)
        logger.info(f"已同步特殊应用列表[dll_hook]，共 {len(special_apps)} 个")

        # 应用触发配置
        try:
            settings = self.data_manager.get_settings()
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
            elif hasattr(self.mouse_hook, "set_trigger_config"):
                self.mouse_hook.set_trigger_config(
                    trigger_settings["popup_trigger_button"],
                    trigger_settings["popup_trigger_modifiers"],
                    trigger_settings["popup_special_trigger_button"],
                    trigger_settings["popup_special_trigger_modifiers"],
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
        except Exception as e:
            logger.error(f"应用触发配置失败: {e}", exc_info=True)

    def _sync_special_apps_to_hook(self):
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
