"""
鼠标/键盘钩子管理相关方法。
"""

import logging
import time

logger = logging.getLogger(__name__)


class HooksMixin:
    """鼠标/键盘钩子管理相关方法。"""

    def _install_hook(self):
        """安装鼠标钩子"""
        if not self._install_mouse_backend():
            logger.error("鼠标钩子安装失败")

    def _install_mouse_backend(self) -> bool:
        """安装 DLL 鼠标后端。hooks.dll 是全局单例，必须按单实例方式重装。"""
        try:
            from hooks.mouse_hook_dll import MouseHook

            if self.mouse_hook:
                try:
                    self.mouse_hook.uninstall()
                except Exception:
                    pass
                self.mouse_hook = None

            hook = MouseHook()
            success = hook.install(self._on_middle_click_from_hook)
            if not success:
                return False

            if self.keyboard_hook:
                try:
                    hook.set_keyboard_hook(self.keyboard_hook)
                except Exception:
                    pass

            try:
                hook.set_paused(self._mouse_paused_state)
            except Exception:
                pass
            self.mouse_hook = hook
            self._apply_mouse_hook_settings()

            logger.info("鼠标触发已切换到 DLL Hook")
            return True
        except Exception as e:
            logger.error(f"安装鼠标后端失败 [dll_hook]: {e}")
            import traceback

            logger.error(traceback.format_exc())
            self.mouse_hook = None
            return False

    def _install_keyboard_hook(self):
        """安装键盘钩子 (Alt双击检测 + Alt按住状态)"""
        try:
            from hooks.keyboard_hook_dll import KeyboardHook

            self.keyboard_hook = KeyboardHook()

            success = self.keyboard_hook.install(on_alt_double_tap=self._on_alt_double_tap_from_hook)

            if success:
                logger.info("键盘钩子安装成功")
                # 将键盘钩子传给鼠标钩子（用于检测 Alt 按住状态）
                if self.mouse_hook:
                    self.mouse_hook.set_keyboard_hook(self.keyboard_hook)
            else:
                logger.warning("  键盘钩子安装失败")

        except Exception as e:
            logger.error(f"  键盘钩子异常: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def _install_keyboard_hook_and_hotkey(self):
        """安装键盘钩子并启动热键管理器（延迟执行）"""
        self._install_keyboard_hook()
        # 共享键盘钩子的DLL实例
        if self.keyboard_hook and hasattr(self.keyboard_hook, "_dll"):
            self.hotkey_manager._dll = self.keyboard_hook._dll
        self.hotkey_manager.start()

    def _reinstall_hooks(self):
        """重装钩子以保持优先级（轻量级，仅卸载重装）"""
        try:
            now = time.monotonic()
            if now < self._hook_reinstall_cooldown_until:
                return
            self._hook_reinstall_cooldown_until = now + 2.0

            if not self._install_mouse_backend():
                return

            if self.keyboard_hook:
                self.keyboard_hook.uninstall()
                self.keyboard_hook.install(self._on_alt_double_tap_from_hook)
        except Exception:
            pass

    def _check_new_processes(self):
        """检测特定软件启动时重装钩子（仅监测可能有钩子冲突的软件）"""
        try:
            import psutil

            # 需要监测的软件关键词（可能有钩子冲突的专业软件）
            target_apps = set(self._get_special_apps())

            if not target_apps:
                self._known_processes = set()
                return

            current_pids = set()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = proc.info["name"].lower()
                    if any(app in name for app in target_apps):
                        current_pids.add(proc.info["pid"])
                except Exception:
                    pass

            if not self._known_processes:
                self._known_processes = current_pids
                return

            new_pids = current_pids - self._known_processes
            if new_pids:
                logger.info("检测到目标软件启动，重装钩子以保持优先级")
                self._reinstall_hooks()

            self._known_processes = current_pids
        except Exception:
            pass

    def _on_alt_double_tap_from_hook(self):
        """Alt双击回调 (从键盘钩子线程调用，必须极快返回)"""
        try:
            self._alt_double_tap_signal.emit()
        except Exception:
            pass

    def _on_hook_hotkey_from_hook(self):
        """键盘钩子热键回调 (从钩子线程调用，必须极快返回)"""
        try:
            self._hook_hotkey_signal.emit()
        except Exception:
            pass

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
            except Exception:
                pass

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

        for app in self._get_special_apps():
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
            return

        special_apps = self._get_special_apps_for_hook()
        self.mouse_hook.set_special_apps(special_apps)
        logger.info(f"已同步特殊应用列表[dll_hook]，共 {len(special_apps)} 个")

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
