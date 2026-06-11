"""
各窗口的 show 方法。
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

_COMMAND_PANEL_FIRST_SHOW_DELAY_MS = 100


class WindowsMixin:
    """各窗口的 show 方法。"""

    def _show_config(self):
        """显示配置窗口"""
        self._wake_from_sleep("config")
        logger.info("显示配置窗口...")
        config_start = time.perf_counter()
        try:
            if self.config_window is None:
                from ui.config_window import ConfigWindow

                self.config_window = ConfigWindow(self.data_manager, tray_app=self)
                self.config_window.settings_changed.connect(self._on_settings_changed)
                pending_center = getattr(self, "_pending_config_window_center", None)
                pending_pos = getattr(self, "_pending_config_window_pos", None)
                pending_view_state = getattr(self, "_pending_config_window_view_state", None)
                if pending_center is not None:
                    rect = self.config_window.frameGeometry()
                    rect.moveCenter(pending_center)
                    self.config_window.move(rect.topLeft())
                    self.config_window._centered_show_animation = True
                    self._pending_config_window_center = None
                    self._pending_config_window_pos = None
                elif pending_pos is not None:
                    self.config_window.move(pending_pos)
                    self._pending_config_window_pos = None
                if pending_view_state is not None:
                    try:
                        self.config_window.restore_view_state(pending_view_state)
                    except Exception as exc:
                        logger.debug("恢复配置窗口页面状态失败: %s", exc, exc_info=True)
                    finally:
                        self._pending_config_window_view_state = None

            if not getattr(self, "_hotkey_signal_connected", False):
                try:
                    panel = getattr(self.config_window, "settings_panel", None)
                    if panel and hasattr(panel, "hotkey_recording_changed"):
                        panel.hotkey_recording_changed.connect(self._on_hotkey_recording_changed)
                        self._hotkey_signal_connected = True
                except Exception as exc:
                    logger.debug("连接热键录制信号失败: %s", exc, exc_info=True)

            if not getattr(self, "_special_apps_signal_connected", False):
                try:
                    panel = getattr(self.config_window, "settings_panel", None)
                    if panel and hasattr(panel, "special_apps_changed"):
                        panel.special_apps_changed.connect(self._sync_special_apps_to_hook)
                        logger.info("已连接 special_apps_changed 信号")
                    if panel and hasattr(panel, "trigger_config_changed"):
                        panel.trigger_config_changed.connect(self._apply_mouse_hook_settings)
                        logger.info("已连接 trigger_config_changed 信号")
                    self._special_apps_signal_connected = True
                except Exception as exc:
                    logger.error("连接信号失败: %s", exc, exc_info=True)

            self.config_window.show()

            try:
                hwnd = int(self.config_window.winId())
                from qt_compat import QTimer
                from ui.utils.window_effect import force_activate_window

                force_activate_window(hwnd)
                QTimer.singleShot(100, lambda: force_activate_window(hwnd))

            except Exception:
                self.config_window.raise_()
                self.config_window.activateWindow()

            logger.info(
                "配置窗口已显示并进入四段式强力激活流程，耗时 %.1f ms", (time.perf_counter() - config_start) * 1000
            )
        except Exception as e:
            logger.exception("显示配置窗口失败")
            from core.i18n import tr
            from ui.styles.themed_messagebox import ThemedMessageBox

            ThemedMessageBox.critical(None, tr("错误"), tr("无法打开设置窗口:\n{error}", error=e))

    def _toggle_config(self):
        """切换配置窗口的显示/隐藏状态（全局快捷键 Ctrl+Shift+L 触发）"""
        try:
            if (
                self.config_window is not None
                and self.config_window.isVisible()
                and not self.config_window.isMinimized()
            ):
                self.config_window.hide()
                logger.info("配置窗口已隐藏 (快捷键切换)")
            else:
                self._show_config()
        except Exception as e:
            logger.error("切换配置窗口失败: %s", e, exc_info=True)
            # 降级为直接显示
            try:
                self._show_config()
            except Exception as exc:
                logger.debug("降级显示配置窗口失败: %s", exc, exc_info=True)

    def _on_settings_changed(self):
        """设置变更时的回调"""
        self._pending_settings_sync = True
        self._mark_activity("settings_changed")
        if not self._settings_sync_timer.isActive():
            self._settings_sync_timer.start()

    def apply_ui_scale_and_reopen_config(self, percent: int):
        """Apply global UI scale by recreating the config window with animations."""
        try:
            percent = int(percent)
        except (TypeError, ValueError):
            percent = 100

        old_window = getattr(self, "config_window", None)
        old_center = None
        old_view_state = None
        try:
            if old_window is not None:
                old_center = old_window.frameGeometry().center()
                if hasattr(old_window, "capture_view_state"):
                    old_view_state = old_window.capture_view_state()
        except RuntimeError:
            old_window = None

        def reopen():
            try:
                from ui.utils.font_manager import apply_app_font
                from ui.utils.ui_scale import set_scale

                set_scale(percent)
                apply_app_font(13)
            except Exception as exc:
                logger.debug("应用全局缩放失败: %s", exc, exc_info=True)

            try:
                self.data_manager.reload()
            except Exception as exc:
                logger.debug("重载设置数据失败: %s", exc, exc_info=True)

            try:
                refresh_popup = getattr(self, "_refresh_popup_after_settings_change", None)
                if callable(refresh_popup):
                    refresh_popup(model_changed=False, preload_icons=True)
            except Exception as exc:
                logger.debug("全局缩放后预热弹窗图标失败: %s", exc, exc_info=True)

            self.config_window = None
            self._hotkey_signal_connected = False
            self._special_apps_signal_connected = False
            if old_center is not None:
                self._pending_config_window_center = old_center
            if old_view_state is not None:
                self._pending_config_window_view_state = old_view_state

            self._show_config()
            self._on_settings_changed()

        if old_window is None:
            reopen()
            return

        try:
            from qt_compat import QTimer

            if hasattr(old_window, "animate_close_then"):
                old_window.animate_close_then(reopen)
            else:
                old_window.close()
                QTimer.singleShot(0, reopen)
        except RuntimeError:
            reopen()
        except Exception as exc:
            logger.debug("缩放重开设置窗口失败: %s", exc, exc_info=True)
            reopen()

    def _on_hotkey_recording_changed(self, recording: bool):
        try:
            self._is_hotkey_recording = bool(recording)
            if recording:
                self.hotkey_manager.stop()
                if self.keyboard_hook:
                    self.keyboard_hook.set_hotkey("", None)
                return
            pass
        except Exception as exc:
            logger.debug("设置热键录制状态失败: %s", exc, exc_info=True)

    def _show_log(self):
        """显示日志窗口"""
        self._wake_from_sleep("log")
        logger.info("_show_log 方法被调用")
        try:
            theme = self.data_manager.get_settings().theme
            logger.debug(f"log_window 状态: {self.log_window}")
            if self.log_window is None:
                logger.info("创建新的日志窗口")
                from ui.log_window import LogWindow

                log_dir = self.data_manager.app_dir
                log_file = os.path.join(log_dir, "error.log")
                self.log_window = LogWindow(log_file, theme=theme)
                logger.info("日志窗口创建完成")

            try:
                logger.debug("检查窗口是否有效")
                _ = self.log_window.isVisible()
                logger.debug("窗口有效")
                self.log_window.set_theme(theme)
            except RuntimeError as e:
                logger.warning(f"窗口已被删除，重新创建: {e}")
                from ui.log_window import LogWindow

                log_dir = self.data_manager.app_dir
                log_file = os.path.join(log_dir, "error.log")
                self.log_window = LogWindow(log_file, theme=theme)
                logger.info("日志窗口重新创建完成")

            logger.info("显示日志窗口")
            self.log_window.show()
            self.log_window.raise_()
            self.log_window.activateWindow()

            try:
                hwnd = int(self.log_window.winId())
                from ui.utils.window_effect import force_activate_window

                force_activate_window(hwnd)
                logger.debug("已强制激活日志窗口")
            except Exception as e:
                logger.warning(f"强制激活失败: {e}")

            logger.debug("窗口已显示，准备加载日志")
            from qt_compat import QTimer

            QTimer.singleShot(100, self.log_window.load_log)
            logger.info("日志窗口显示完成")
        except Exception:
            logger.exception("显示日志窗口失败")

    def _show_slash_help(self):
        """显示斜杠命令帮助。"""
        self._wake_from_sleep("slash_help")
        try:
            theme = self.data_manager.get_settings().theme
            if self.slash_help_window is None:
                from ui.slash_help_window import SlashHelpWindow

                self.slash_help_window = SlashHelpWindow(self.data_manager)
            else:
                self.slash_help_window.set_theme(theme)
                self.slash_help_window.refresh()
            self.slash_help_window.show()
            self.slash_help_window.raise_()
            self.slash_help_window.activateWindow()
            return True
        except RuntimeError:
            from ui.slash_help_window import SlashHelpWindow

            self.slash_help_window = SlashHelpWindow(self.data_manager)
            self.slash_help_window.show()
            return True
        except Exception as e:
            logger.error("显示斜杠命令帮助失败: %s", e, exc_info=True)
            return False

    def _show_about(self):
        """显示关于对话框。"""
        self._wake_from_sleep("about")
        try:
            theme = self.data_manager.get_settings().theme
            if getattr(self, "about_window", None) is None:
                from ui.about_window import AboutWindow

                self.about_window = AboutWindow(theme=theme)
            else:
                self.about_window.set_theme(theme)
            self.about_window.show()
            self.about_window.raise_()
            self.about_window.activateWindow()
            return True
        except RuntimeError:
            from ui.about_window import AboutWindow

            self.about_window = AboutWindow(theme=self.data_manager.get_settings().theme)
            self.about_window.show()
            return True
        except Exception as e:
            logger.error("显示关于对话框失败: %s", e, exc_info=True)
            return False

    def _show_diagnostics(self):
        """显示诊断中心。"""
        self._wake_from_sleep("diagnostics")
        try:
            theme = self.data_manager.get_settings().theme
            if self.diagnostics_window is None:
                from ui.diagnostics_window import DiagnosticsWindow

                self.diagnostics_window = DiagnosticsWindow(self.data_manager, tray_app=self)
            else:
                self.diagnostics_window.set_theme(theme)
                self.diagnostics_window.refresh()
            self.diagnostics_window.show()
            self.diagnostics_window.raise_()
            self.diagnostics_window.activateWindow()
        except RuntimeError:
            from ui.diagnostics_window import DiagnosticsWindow

            self.diagnostics_window = DiagnosticsWindow(self.data_manager, tray_app=self)
            self.diagnostics_window.show()
        except Exception as e:
            logger.error("显示诊断中心失败: %s", e, exc_info=True)

    def _show_shortcut_health(self):
        """显示图标检查。"""
        self._wake_from_sleep("shortcut_health")
        try:
            theme = self.data_manager.get_settings().theme
            if self.shortcut_health_window is None:
                from ui.shortcut_health_window import ShortcutHealthWindow

                self.shortcut_health_window = ShortcutHealthWindow(self.data_manager)
            else:
                self.shortcut_health_window.set_theme(theme)
                self.shortcut_health_window.refresh()
            self.shortcut_health_window.show()
            self.shortcut_health_window.raise_()
            self.shortcut_health_window.activateWindow()
        except RuntimeError:
            from ui.shortcut_health_window import ShortcutHealthWindow

            self.shortcut_health_window = ShortcutHealthWindow(self.data_manager)
            self.shortcut_health_window.show()
        except Exception as e:
            logger.error("显示图标检查失败: %s", e, exc_info=True)

    def show_command_panel(
        self, command_id="", args_text="", raw_input="", result_id=None, context_meta=None, shortcut=None
    ):
        """显示独立命令面板。"""
        self._wake_from_sleep("command_panel")
        try:
            theme = self.data_manager.get_settings().theme
            created_window = False
            if getattr(self, "command_result_store", None) is None:
                from core.command_results import CommandResultStore

                self.command_result_store = CommandResultStore()
            if getattr(self, "command_panel_window", None) is None:
                from ui.command_panel_window import CommandPanelWindow

                self.command_panel_window = CommandPanelWindow(self.data_manager, self.command_result_store)
                created_window = True
            else:
                self.command_panel_window.set_theme(theme)

            if result_id:
                self.command_panel_window.show_result(result_id)
            elif shortcut is not None:
                self.command_panel_window.run_shortcut(
                    shortcut,
                    raw_input=raw_input or getattr(shortcut, "command", "") or getattr(shortcut, "name", ""),
                    context_meta=context_meta or {},
                )
            elif command_id:
                self.command_panel_window.run_command(
                    command_id=command_id,
                    args_text=args_text,
                    raw_input=raw_input,
                    context_meta=context_meta or {},
                )

            window = self.command_panel_window
            if created_window and not result_id and bool(getattr(window, "_running", False)):
                from qt_compat import QTimer

                QTimer.singleShot(
                    _COMMAND_PANEL_FIRST_SHOW_DELAY_MS,
                    lambda panel=window: self._present_command_panel_window(panel),
                )
            else:
                self._present_command_panel_window(window)
            return True
        except RuntimeError:
            from ui.command_panel_window import CommandPanelWindow

            self.command_panel_window = CommandPanelWindow(self.data_manager, self.command_result_store)
            self._present_command_panel_window(self.command_panel_window)
            return True
        except Exception as e:
            logger.error("显示命令面板失败: %s", e, exc_info=True)
            return False

    def _present_command_panel_window(self, window):
        """Show the current command panel only after its first layout is ready."""
        if window is not getattr(self, "command_panel_window", None):
            return
        try:
            window.show()
            window.raise_()
            window.activateWindow()
            hwnd = int(window.winId())
            self._command_panel_hwnd = hwnd
            from ui.utils.window_effect import force_activate_window

            force_activate_window(hwnd)
        except RuntimeError:
            logger.debug("命令面板在延迟显示前已销毁", exc_info=True)
        except Exception as exc:
            logger.debug("激活命令面板窗口失败: %s", exc, exc_info=True)

    def _show_config_history(self):
        """显示配置历史窗口。"""
        self._wake_from_sleep("config_history")
        try:
            theme = self.data_manager.get_settings().theme
            if self.config_history_window is None:
                from ui.config_history_window import ConfigHistoryWindow

                self.config_history_window = ConfigHistoryWindow(self.data_manager)
            else:
                self.config_history_window.set_theme(theme)
                self.config_history_window.refresh()
            self.config_history_window.show()
            self.config_history_window.raise_()
            self.config_history_window.activateWindow()
        except RuntimeError:
            from ui.config_history_window import ConfigHistoryWindow

            self.config_history_window = ConfigHistoryWindow(self.data_manager)
            self.config_history_window.show()
        except Exception as e:
            logger.error("显示配置历史窗口失败: %s", e, exc_info=True)
