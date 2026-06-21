"""System settings page builder and event handlers."""

import logging
import os
import sys
import tempfile

from core.i18n import tr
from infrastructure.process import runtime as process_runtime
from qt_compat import (
    QButtonGroup,
    QCheckBox,
    QEasingCurve,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QParallelAnimationGroup,
    QPushButton,
    QRadioButton,
    QSlider,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from runtime_paths import app_executable, app_root, is_packaged_runtime
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.tooltip_helper import install_tooltip
from ui.utils.interruptible_animation import stop_animation
from ui.utils.ui_scale import DEFAULT_SCALE_PERCENT, MAX_SCALE_PERCENT, MIN_SCALE_PERCENT, scale_qss, set_scale, sp
from ui.utils.window_effect import is_win11

from .settings_helpers import SwitchButton

logger = logging.getLogger(__name__)


class SettingsSystemPageMixin:
    def _setup_system_page(self, page):
        # 启动
        layout, group = page.add_group("启动与运行")

        self.auto_start_cb = SwitchButton(tr("开机自动启动"))
        self.auto_start_cb.setTristate(False)
        self.auto_start_cb.stateChanged.connect(self._on_auto_start_changed)

        layout.addWidget(self.auto_start_cb)

        self.show_on_startup_cb = SwitchButton(tr("启动时显示设置窗口"))
        self.show_on_startup_cb.stateChanged.connect(self._on_startup_show_changed)
        layout.addWidget(self.show_on_startup_cb)

        self.hw_accel_cb = SwitchButton(tr("启用硬件加速 (性能优先)"))
        install_tooltip(self.hw_accel_cb, tr("开启后将提高进程优先级并优化资源调度，可能会增加系统资源占用"))
        self.hw_accel_cb.stateChanged.connect(self._on_hw_accel_changed)
        layout.addWidget(self.hw_accel_cb)

        self.hide_tray_cb = SwitchButton(tr("隐藏托盘图标"))
        install_tooltip(self.hide_tray_cb, tr("隐藏后可通过内置命令'配置窗口'唤出设置面板"))
        self.hide_tray_cb.stateChanged.connect(self._on_hide_tray_changed)
        layout.addWidget(self.hide_tray_cb)

        self.sleep_mode_cb = SwitchButton(tr("10秒无操作后轻睡眠"))
        install_tooltip(self.sleep_mode_cb, tr("无操作一段时间后进入低占用状态，下一次中键立即唤醒"))
        self.sleep_mode_cb.stateChanged.connect(self._on_sleep_mode_changed)
        layout.addWidget(self.sleep_mode_cb)

        self.disable_logging_cb = SwitchButton(tr("关闭日志"))
        install_tooltip(self.disable_logging_cb, tr("停止记录日志到error.log，减少硬盘写入（配置信息仍会保存）"))
        self.disable_logging_cb.stateChanged.connect(self._on_disable_logging_changed)
        layout.addWidget(self.disable_logging_cb)

        self.debug_log_cb = SwitchButton(tr("开启DEBUG日志"))
        install_tooltip(self.debug_log_cb, tr("开启后将记录详细的调试信息，用于问题排查"))
        self.debug_log_cb.stateChanged.connect(self._on_debug_log_changed)
        layout.addWidget(self.debug_log_cb)

        self.auto_update_cb = SwitchButton(tr("自动更新"))
        install_tooltip(self.auto_update_cb, tr("开启后仅在每次启动软件时检查一次新版本，其他时间不自动检查"))
        self.auto_update_cb.stateChanged.connect(self._on_auto_update_changed)
        layout.addWidget(self.auto_update_cb)

        # 全局缩放
        layout, group = page.add_group("全局缩放")
        scale_layout = QHBoxLayout()
        scale_layout.setSpacing(sp(8))

        self.ui_scale_slider = QSlider(QtCompat.Horizontal)
        self.ui_scale_slider.setRange(MIN_SCALE_PERCENT, MAX_SCALE_PERCENT)
        self.ui_scale_slider.setSingleStep(5)
        self.ui_scale_slider.setPageStep(5)
        self.ui_scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ui_scale_slider.setTickInterval(5)
        self.ui_scale_slider.valueChanged.connect(self._on_ui_scale_slider_changed)
        scale_layout.addWidget(self.ui_scale_slider, 1)

        self.ui_scale_edit = QLineEdit()
        self.ui_scale_edit.setFixedWidth(sp(56))
        self.ui_scale_edit.setMaxLength(3)
        self.ui_scale_edit.setAlignment(QtCompat.AlignCenter)
        self.ui_scale_edit.setPlaceholderText("100")
        self.ui_scale_edit.textEdited.connect(self._on_ui_scale_text_edited)
        self.ui_scale_edit.returnPressed.connect(self._on_ui_scale_apply_clicked)
        scale_layout.addWidget(self.ui_scale_edit)

        scale_suffix = QLabel("%")
        scale_suffix.setStyleSheet(scale_qss("background: transparent; border: none; border-radius: 0;"))
        scale_layout.addWidget(scale_suffix)

        self.ui_scale_apply_btn = QPushButton(tr("应用"))
        self.ui_scale_apply_btn.setFixedHeight(sp(24))
        self.ui_scale_apply_btn.setMinimumWidth(sp(64))
        self.ui_scale_apply_btn.clicked.connect(self._on_ui_scale_apply_clicked)
        scale_layout.addWidget(self.ui_scale_apply_btn)

        layout.addLayout(scale_layout)

        # 排序模式
        layout, group = page.add_group("排序方式")
        sort_layout = QHBoxLayout()
        self.sort_mode_group = QButtonGroup(self)
        self.custom_sort_radio = QRadioButton(tr("自定义排序"))
        self.smart_sort_radio = QRadioButton(tr("智能排序"))
        install_tooltip(self.custom_sort_radio, tr("按你拖拽调整的顺序显示，不会删除智能排序结果"))
        install_tooltip(self.smart_sort_radio, tr("按使用次数和最近使用时间显示，保留自定义排序可随时切回"))
        self.sort_mode_group.addButton(self.custom_sort_radio, 0)
        self.sort_mode_group.addButton(self.smart_sort_radio, 1)
        self.sort_mode_group.buttonClicked.connect(self._on_sort_mode_changed)
        sort_layout.addWidget(self.custom_sort_radio)
        sort_layout.addWidget(self.smart_sort_radio)
        sort_layout.addStretch()
        layout.addLayout(sort_layout)

        # 主题
        layout, group = page.add_group("主题风格")
        theme_layout = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        self.follow_system_radio = QRadioButton(tr("跟随系统"))
        self.dark_radio = QRadioButton(tr("深色模式"))
        self.light_radio = QRadioButton(tr("浅色模式"))
        self.theme_group.addButton(self.follow_system_radio, 0)
        self.theme_group.addButton(self.dark_radio, 1)
        self.theme_group.addButton(self.light_radio, 2)
        self.theme_group.buttonClicked.connect(self._on_theme_changed)
        theme_layout.addWidget(self.follow_system_radio)
        theme_layout.addWidget(self.dark_radio)
        theme_layout.addWidget(self.light_radio)
        theme_layout.addStretch()

        # 高级颜色滤镜复选框 (仅Win11) — 同一排末尾
        is_win11_platform = is_win11()
        self.advanced_mode_cb = QCheckBox(tr("高级模式"))
        self.advanced_mode_cb.setToolTip(tr("调节窗口颜色滤镜效果 (黑场/白场/中间调/色温/Acrylic/底色α)"))
        self.advanced_mode_cb.stateChanged.connect(self._on_advanced_mode_changed)
        if not is_win11_platform:
            self.advanced_mode_cb.setVisible(False)
        theme_layout.addWidget(self.advanced_mode_cb)
        layout.addLayout(theme_layout)

        self.color_filter_panel = self._create_color_filter_panel()
        self.color_filter_panel.setVisible(False)
        layout.addWidget(self.color_filter_panel)

        # 语言
        layout, group = page.add_group("语言")
        language_layout = QHBoxLayout()
        self.language_group = QButtonGroup(self)
        self.chinese_radio = QRadioButton(tr("中文"))
        self.english_radio = QRadioButton(tr("English"))
        self.language_group.addButton(self.chinese_radio, 0)
        self.language_group.addButton(self.english_radio, 1)
        self.language_group.buttonClicked.connect(self._on_language_changed)
        language_layout.addWidget(self.chinese_radio)
        language_layout.addWidget(self.english_radio)
        language_layout.addStretch()
        layout.addLayout(language_layout)

        # 日志修复
        layout, group = page.add_group("日志修复")
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(sp(8))

        tool_buttons = [
            ("运行日志", "查看 error.log，排查最近运行异常", self._on_runtime_log_clicked),
            ("诊断中心", "查看钩子、热键、配置、权限和最近错误状态", self._on_diagnostics_clicked),
            ("图标检查", "扫描缺失图标、失效路径、重复项和命令风险", self._on_shortcut_health_clicked),
            ("配置历史", "查看最近 20 次配置快照，并可恢复到历史版本", self._on_config_history_clicked),
        ]
        for title, tooltip, handler in tool_buttons:
            button = QPushButton(tr(title))
            install_tooltip(button, tr(tooltip))
            button.clicked.connect(handler)
            tools_layout.addWidget(button, 1)

        layout.addLayout(tools_layout)

    def _get_utility_window(self, attr_name):
        window = getattr(self, attr_name, None)
        if window is None:
            return None
        try:
            window.isVisible()
        except RuntimeError:
            setattr(self, attr_name, None)
            return None
        return window

    def _current_tool_theme(self):
        try:
            return self.data_manager.get_settings().theme or "light"
        except Exception:
            return "light"

    def _show_utility_window(self, attr_name, factory, refresh_method=None):
        theme = self._current_tool_theme()
        try:
            window = self._get_utility_window(attr_name)
            if window is None:
                window = factory(theme)
                setattr(self, attr_name, window)
            elif hasattr(window, "set_theme"):
                window.set_theme(theme)

            if refresh_method and hasattr(window, refresh_method):
                getattr(window, refresh_method)()

            window.show()
            window.raise_()
            window.activateWindow()
            return window
        except Exception as e:
            ThemedMessageBox.warning(self, tr("打开失败"), tr("无法打开工具窗口:\n{error}", error=e))
            return None

    def _on_runtime_log_clicked(self):
        """打开运行日志窗口。"""

        def create_window(theme):
            from ui.log_window import LogWindow

            log_file = os.path.join(str(self.data_manager.app_dir), "error.log")
            return LogWindow(log_file, theme=theme, parent=self)

        self._show_utility_window("_runtime_log_window", create_window, "load_log")

    def _on_diagnostics_clicked(self):
        """打开诊断中心。"""

        def create_window(theme):
            from ui.diagnostics_window import DiagnosticsWindow

            return DiagnosticsWindow(self.data_manager, tray_app=getattr(self, "tray_app", None), parent=self)

        self._show_utility_window("_diagnostics_window", create_window, "refresh")

    def _on_shortcut_health_clicked(self):
        """打开图标检查。"""

        def create_window(theme):
            from ui.shortcut_health_window import ShortcutHealthWindow

            return ShortcutHealthWindow(self.data_manager, parent=self)

        self._show_utility_window("_shortcut_health_window", create_window, "refresh")

    # === Settings Load ===

    def _schedule_auto_start_status_check(self):
        timer = getattr(self, "_auto_start_check_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_auto_start_status)
            self._auto_start_check_timer = timer
        if timer.isActive():
            return
        timer.start(350)

    def _refresh_auto_start_status(self):
        auto_start_cb = getattr(self, "auto_start_cb", None)
        if auto_start_cb is None:
            return

        old_updating = getattr(self, "_updating", False)
        try:
            from core.auto_start_manager import get_auto_start_check_result

            settings = self.data_manager.get_settings()
            actual_enabled, auto_start_reason = get_auto_start_check_result()
            desired_enabled = bool(settings.auto_start)

            self._updating = True
            if actual_enabled:
                if not desired_enabled:
                    self.data_manager.update_settings(auto_start=True)
                auto_start_cb.setToolTip("")
                auto_start_cb.setChecked(True)
            elif desired_enabled:
                logger.warning("配置要求开机自启，但任务缺失或定义已过期；设置页已同步为关闭: %s", auto_start_reason)
                self.data_manager.update_settings(auto_start=False)
                auto_start_cb.setToolTip(f"开机自启任务缺失或定义已过期，已切换为关闭。原因: {auto_start_reason}")
                auto_start_cb.setChecked(False)
            else:
                auto_start_cb.setToolTip("")
                auto_start_cb.setChecked(False)
        except Exception as e:
            logger.debug("Failed to load auto-start state: %s", e, exc_info=True)
            self._updating = True
            auto_start_cb.setToolTip(tr("检测开机自启状态失败，请查看日志。"))
            auto_start_cb.setChecked(False)
        finally:
            self._updating = old_updating

    def _load_system_settings(self, settings):
        self.auto_start_cb.setToolTip("")
        self.auto_start_cb.setChecked(bool(settings.auto_start))
        self._schedule_auto_start_status_check()

        self.show_on_startup_cb.setChecked(settings.show_on_startup)
        self.hw_accel_cb.setChecked(settings.hardware_acceleration)
        self.hide_tray_cb.setChecked(settings.hide_tray_icon)
        self.disable_logging_cb.setChecked(getattr(settings, "disable_logging", False))
        self.debug_log_cb.setChecked(getattr(settings, "enable_debug_log", False))
        self.auto_update_cb.setChecked(getattr(settings, "auto_update_enabled", False))
        self.sleep_mode_cb.setChecked(getattr(settings, "sleep_mode_enabled", True))

        # 全局缩放
        scale_val = self._normalize_ui_scale(getattr(settings, "ui_scale_percent", DEFAULT_SCALE_PERCENT))
        self.ui_scale_slider.blockSignals(True)
        self.ui_scale_slider.setValue(scale_val)
        self.ui_scale_slider.blockSignals(False)
        self.ui_scale_edit.blockSignals(True)
        self.ui_scale_edit.setText(str(scale_val))
        self.ui_scale_edit.blockSignals(False)

        # 排序方式
        sort_mode = getattr(settings, "sort_mode", "custom")
        if sort_mode == "smart":
            self.smart_sort_radio.setChecked(True)
        else:
            self.custom_sort_radio.setChecked(True)

        # 主题设置
        follow_system = getattr(settings, "theme_follow_system", True)
        if follow_system:
            self.follow_system_radio.setChecked(True)
        elif settings.theme == "dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)

        language = getattr(settings, "language", "zh_CN")
        if language == "en_US":
            self.english_radio.setChecked(True)
        else:
            self.chinese_radio.setChecked(True)

        # 高级颜色滤镜 - 每次打开重置为取消勾选
        self.advanced_mode_cb.setChecked(False)
        self.color_filter_panel.setVisible(False)
        # 加载滑块默认值 (下次勾选时显示)
        self._load_color_filter_sliders_from_settings()

    # === Event Handlers ===

    def _normalize_ui_scale(self, value) -> int:
        try:
            percent = int(str(value).strip().rstrip("%"))
        except (TypeError, ValueError):
            percent = DEFAULT_SCALE_PERCENT
        percent = max(MIN_SCALE_PERCENT, min(MAX_SCALE_PERCENT, percent))
        return int(round(percent / 5) * 5)

    def _sync_ui_scale_controls(self, value: int) -> None:
        value = self._normalize_ui_scale(value)
        self.ui_scale_slider.blockSignals(True)
        self.ui_scale_slider.setValue(value)
        self.ui_scale_slider.blockSignals(False)
        self.ui_scale_edit.blockSignals(True)
        self.ui_scale_edit.setText(str(value))
        self.ui_scale_edit.blockSignals(False)

    def _on_ui_scale_slider_changed(self, value: int):
        if self._updating:
            return
        self._sync_ui_scale_controls(value)

    def _on_ui_scale_text_edited(self, text: str):
        if self._updating:
            return
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits != text:
            self.ui_scale_edit.blockSignals(True)
            self.ui_scale_edit.setText(digits[:3])
            self.ui_scale_edit.blockSignals(False)
            return
        if not digits:
            return
        raw_value = int(digits)
        if MIN_SCALE_PERCENT <= raw_value <= MAX_SCALE_PERCENT:
            self.ui_scale_slider.blockSignals(True)
            self.ui_scale_slider.setValue(self._normalize_ui_scale(raw_value))
            self.ui_scale_slider.blockSignals(False)

    def _on_ui_scale_apply_clicked(self):
        if self._updating:
            return

        percent = self._normalize_ui_scale(self.ui_scale_edit.text())
        self._sync_ui_scale_controls(percent)
        current = self._normalize_ui_scale(
            getattr(self.data_manager.get_settings(), "ui_scale_percent", DEFAULT_SCALE_PERCENT)
        )
        if percent == current:
            return

        self.data_manager.update_settings(ui_scale_percent=percent)
        tray_app = getattr(self, "tray_app", None)
        if tray_app and hasattr(tray_app, "apply_ui_scale_and_reopen_config"):
            tray_app.apply_ui_scale_and_reopen_config(percent)
            return

        set_scale(percent)
        try:
            from ui.utils.font_manager import apply_app_font

            apply_app_font(13)
        except Exception as exc:
            logger.debug("应用 UI 缩放字体失败: %s", exc, exc_info=True)
        self.settings_changed.emit()

    def _on_auto_start_changed(self, state):
        if self._updating:
            return

        checked = state == 2

        if checked:
            self._updating = True
            from core.auto_start_manager import enable_auto_start

            success, method = enable_auto_start()
            logger.info(f"开机自启：启用结果 success={success}, method={method}")

            if success:
                self.data_manager.update_settings(auto_start=True)
                self._updating = False
                return

            self.data_manager.update_settings(auto_start=False)
            self._updating = False
            logger.error("开机自启：启用失败")

            if method == "cancelled":
                ThemedMessageBox.warning(self, tr("已取消"), tr("你取消了管理员授权，自启动未启用。"))
            else:
                ThemedMessageBox.critical(
                    self, "启用失败", "helper 创建开机自启失败。\n\n请检查 UAC、任务计划程序服务和日志。"
                )
            QTimer.singleShot(0, lambda: self._reset_checkbox_state(False))
            return

        self._updating = True
        logger.info("开机自启：开始禁用")
        from core.auto_start_manager import disable_auto_start

        success, method = disable_auto_start()

        try:
            from core.service_manager import _cleanup_legacy_service

            _cleanup_legacy_service()
        except Exception as exc:
            logger.debug("清理旧服务失败: %s", exc, exc_info=True)

        if success:
            self.data_manager.update_settings(auto_start=False)
            self._updating = False
            logger.info("开机自启：禁用完成")
            return

        self._updating = False
        if method == "cancelled":
            ThemedMessageBox.warning(self, tr("已取消"), tr("你取消了管理员授权，自启动保持原状。"))
        else:
            ThemedMessageBox.critical(self, tr("禁用失败"), tr("helper 禁用开机自启失败，自启动保持原状。"))
        QTimer.singleShot(0, lambda: self._reset_checkbox_state(True))

    def _reset_checkbox_state(self, checked):
        self._updating = True
        self.auto_start_cb.setChecked(checked)
        self._updating = False

    def _on_startup_show_changed(self, state):
        if self._updating:
            return
        self.data_manager.update_settings(show_on_startup=(state == 2))

    def _on_hw_accel_changed(self, state):
        if self._updating:
            return
        self.data_manager.update_settings(hardware_acceleration=(state == 2))

    def _on_hide_tray_changed(self, state):
        if self._updating:
            return
        checked = state == 2
        self.data_manager.update_settings(hide_tray_icon=checked)
        if checked:
            ThemedMessageBox.information(
                self, "提示", "托盘图标已隐藏。\n如需再次进入设置，请使用内置命令'配置窗口' (show_config_window)。"
            )

    def _on_disable_logging_changed(self, state):
        if self._updating:
            return
        checked = state == 2
        if checked:
            reply = ThemedMessageBox.question(
                self,
                "确认关闭日志",
                "关闭日志后将停止记录运行日志到 error.log 文件。\n\n"
                "这将减少硬盘写入，但可能影响问题排查。\n配置信息仍会正常保存。\n\n"
                "确定要关闭日志记录吗？",
            )
            if reply == ThemedMessageBox.Yes:
                self.data_manager.update_settings(disable_logging=True)
                import logging

                root_logger = logging.getLogger()
                for handler in root_logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                        root_logger.removeHandler(handler)
            else:
                self.disable_logging_cb.setChecked(False)
        else:
            self.data_manager.update_settings(disable_logging=False)
            ThemedMessageBox.warning(self, tr("需要重启"), tr("重新启用日志需要重启程序才能生效。"))

    def _on_debug_log_changed(self, state):
        if self._updating:
            return
        checked = state == 2

        logger.info(f"DEBUG日志开关变更: {checked}")

        self.data_manager.data.settings.enable_debug_log = checked
        logger.info(f"设置后的值: {self.data_manager.data.settings.enable_debug_log}")

        self.data_manager.save(immediate=True)
        logger.info("已调用 save(immediate=True)")

        if checked:
            reply = ThemedMessageBox.question(
                self, "需要重启", "DEBUG日志已开启，需要重启程序才能生效。\n\n是否立即重启？"
            )
            if reply == ThemedMessageBox.Yes:
                self._restart_app()

    def _on_sleep_mode_changed(self, state):
        if self._updating:
            return
        self.data_manager.update_settings(sleep_mode_enabled=(state == 2))

    def _on_auto_update_changed(self, state):
        if self._updating:
            return
        self.data_manager.update_settings(auto_update_enabled=(state == 2))

    def _on_sort_mode_changed(self, button):
        if self._updating:
            return
        mode = "smart" if button == self.smart_sort_radio else "custom"
        self.data_manager.update_settings(sort_mode=mode)

    def _restart_app(self):
        """重启应用"""
        logger.info("用户请求重启应用...")

        try:
            packaged = is_packaged_runtime()
            exe = str(app_executable() if packaged else sys.executable)

            if packaged:
                if not os.path.isabs(exe):
                    exe = os.path.abspath(exe)
                cwd = os.path.dirname(exe)

                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 1000
WshShell.Run """{exe}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), "quicklauncher_restart.vbs")
                with open(vbs_file, "w", encoding="utf-8") as f:
                    f.write(vbs_content)

                process_runtime.popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)
            else:
                cwd = str(app_root())
                main_py = os.path.join(cwd, "main.py")

                vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 1000
WshShell.Run """{exe}"" ""{main_py}""", 0, False
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile WScript.ScriptFullName
'''
                vbs_file = os.path.join(tempfile.gettempdir(), "quicklauncher_restart.vbs")
                with open(vbs_file, "w", encoding="utf-8") as f:
                    f.write(vbs_content)

                process_runtime.popen(["wscript.exe", vbs_file], cwd=cwd, creationflags=0x08000000, shell=False)

            from qt_compat import QApplication

            QTimer.singleShot(100, QApplication.quit)

        except Exception:
            logger.exception("重启失败")

    def _on_theme_changed(self, button):
        if self._updating:
            return

        if button == self.follow_system_radio:
            system_theme = self._get_system_theme()
            new_theme = system_theme
            self.data_manager.update_settings(theme=system_theme, theme_follow_system=True)
        elif button == self.dark_radio:
            new_theme = "dark"
            self.data_manager.update_settings(theme="dark", theme_follow_system=False)
        else:
            new_theme = "light"
            self.data_manager.update_settings(theme="light", theme_follow_system=False)

        self.setUpdatesEnabled(False)
        self.apply_theme(new_theme)
        self.setUpdatesEnabled(True)
        self.update()

        # 切换主题时更新滑块组可见性
        self._update_slider_group_visibility()

        self.settings_changed.emit()

    def _on_language_changed(self, button):
        if self._updating:
            return

        new_language = "en_US" if button == self.english_radio else "zh_CN"
        current_language = getattr(self.data_manager.get_settings(), "language", "zh_CN")
        if current_language == new_language:
            return

        self._switch_language_with_animation(new_language)

    def _get_system_theme(self):
        """检测系统主题"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"
        except Exception as e:
            logger.debug("Failed to detect system theme: %s", e)
            return "dark"

    # === 高级颜色滤镜 ===

    def _create_color_filter_panel(self):
        """创建高级颜色滤镜滑块面板 (深色 + 浅色两组)"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, sp(4), 0, 0)
        panel_layout.setSpacing(sp(8))

        # 深色组
        self._dark_group_widget, self._dark_sliders = self._create_filter_slider_group(tr("深色参数"), "dark")
        panel_layout.addWidget(self._dark_group_widget)

        # 浅色组
        self._light_group_widget, self._light_sliders = self._create_filter_slider_group(tr("浅色参数"), "light")
        panel_layout.addWidget(self._light_group_widget)

        # 根据当前主题初始化可见性
        self._update_slider_group_visibility()

        return panel

    def _create_filter_slider_group(self, title: str, prefix: str):
        """创建一组6个滑块 (黑场/白场/中间调/色温/Acrylic/底色α)"""
        from ui.utils.font_manager import get_qfont

        group_widget = QWidget()
        layout = QGridLayout(group_widget)
        layout.setContentsMargins(sp(4), sp(4), sp(4), sp(4))
        layout.setVerticalSpacing(sp(4))
        layout.setHorizontalSpacing(sp(6))

        # 标题标签
        title_label = QLabel(title)
        title_label.setFont(get_qfont(11))
        title_label.setStyleSheet(scale_qss("color: #888; padding-bottom: 2px;"))
        layout.addWidget(title_label, 0, 0, 1, 4)

        slider_defs = [
            ("黑场", "black_point", 0, 100, 50, ("中性", "压暗", "提亮")),
            ("白场", "white_point", 0, 100, 50, ("中性", "加亮", "压暗")),
            ("中间调", "mid_gamma", 0, 100, 50, ("中性", "变暗", "变亮")),
            ("色温", "temperature", 0, 100, 50, ("中性", "暖", "冷")),
            ("Acrylic", "acrylic", 1, 255, 30, ("极模糊", "强模糊", "中模糊", "弱模糊", "近实色")),
            ("底色α", "bg_alpha_filter", 1, 255, 100, ("极透", "高透", "半透", "低透", "实色")),
        ]

        sliders = {}
        for row, (label_text, key, min_val, max_val, default, descs) in enumerate(slider_defs, start=1):
            attr_name = f"_{prefix}_{key}_slider"
            val_attr = f"_{prefix}_{key}_label"

            lbl = QLabel(tr(label_text))
            lbl.setFixedWidth(sp(36))
            lbl.setAlignment(QtCompat.AlignRight | QtCompat.AlignVCenter)
            lbl.setStyleSheet(scale_qss("font-size: 11px;"))
            layout.addWidget(lbl, row, 0)

            slider = QSlider(QtCompat.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(default)
            slider.valueChanged.connect(self._on_color_filter_slider_changed)
            layout.addWidget(slider, row, 1)

            val_label = QLabel(self._desc_text(key, default, descs))
            val_label.setFixedWidth(sp(48))
            val_label.setAlignment(QtCompat.AlignCenter)
            val_label.setStyleSheet(scale_qss("font-size: 10px; color: #999;"))
            layout.addWidget(val_label, row, 2)

            setattr(self, attr_name, slider)
            setattr(self, val_attr, val_label)
            sliders[key] = (slider, val_label, min_val, max_val, descs)

        return group_widget, sliders

    def _desc_text(self, key: str, value: int, descs: tuple) -> str:
        """根据滑块值返回描述性文本"""
        if key == "acrylic":
            if value <= 5:
                return descs[0]  # type: ignore[no-any-return]
            if value <= 50:
                return descs[1]  # type: ignore[no-any-return]
            if value <= 120:
                return descs[2]  # type: ignore[no-any-return]
            if value <= 200:
                return descs[3]  # type: ignore[no-any-return]
            return descs[4]  # type: ignore[no-any-return]
        if key == "bg_alpha_filter":
            if value <= 10:
                return descs[0]  # type: ignore[no-any-return]
            if value <= 60:
                return descs[1]  # type: ignore[no-any-return]
            if value <= 140:
                return descs[2]  # type: ignore[no-any-return]
            if value <= 210:
                return descs[3]  # type: ignore[no-any-return]
            return descs[4]  # type: ignore[no-any-return]
        # black_point, white_point, mid_gamma, temperature
        if value == 50:
            return descs[0]  # type: ignore[no-any-return]
        if value > 50:
            return descs[1]  # type: ignore[no-any-return]
        return descs[2]  # type: ignore[no-any-return]

    def _on_advanced_mode_changed(self, state):
        """高级模式复选框切换"""
        if not is_win11():
            self.color_filter_panel.setVisible(False)
            if self.advanced_mode_cb.isChecked():
                self.advanced_mode_cb.setChecked(False)
            return

        checked = state == 2  # Qt.Checked
        self.color_filter_panel.setVisible(checked)
        if not checked:
            return
        # 根据当前主题显示对应的滑块组
        self._update_slider_group_visibility()
        # 加载当前设置到滑块
        self._load_color_filter_sliders_from_settings()

    def _update_slider_group_visibility(self):
        """根据当前主题只显示对应的滑块组"""
        try:
            settings = self.data_manager.get_settings()
            theme = settings.theme or "dark"
        except Exception:
            theme = "dark"

        dark_w = getattr(self, "_dark_group_widget", None)
        light_w = getattr(self, "_light_group_widget", None)
        if dark_w is not None:
            dark_w.setVisible(theme == "dark")
        if light_w is not None:
            light_w.setVisible(theme == "light")

    def _on_color_filter_slider_changed(self):
        """任意颜色滤镜滑块变化时保存"""
        if self._updating:
            return

        updates = {}
        for prefix in ("dark", "light"):
            for key in ("black_point", "white_point", "mid_gamma", "temperature", "acrylic", "bg_alpha_filter"):
                attr_name = f"_{prefix}_{key}_slider"
                slider = getattr(self, attr_name, None)
                if slider is None:
                    continue

                value = slider.value()
                updates[f"{prefix}_{key}"] = value

                # 更新描述标签
                _, _, _, descs = self._get_slider_meta(key)
                val_attr = f"_{prefix}_{key}_label"
                val_label = getattr(self, val_attr, None)
                if val_label and descs:
                    val_label.setText(self._desc_text(key, value, descs))

        self.data_manager.update_settings(**updates)
        self.color_filter_changed.emit()

    def _get_slider_meta(self, key: str):
        """返回 (min, max, default, descs)"""
        meta = {
            "black_point": (0, 100, 50, ("中性", "压暗", "提亮")),
            "white_point": (0, 100, 50, ("中性", "加亮", "压暗")),
            "mid_gamma": (0, 100, 50, ("中性", "变暗", "变亮")),
            "temperature": (0, 100, 50, ("中性", "暖", "冷")),
            "acrylic": (1, 255, 30, ("极模糊", "强模糊", "中模糊", "弱模糊", "近实色")),
            "bg_alpha_filter": (1, 255, 100, ("极透", "高透", "半透", "低透", "实色")),
        }
        return meta.get(key, (0, 100, 50, ("", "", "")))

    def _load_color_filter_sliders_from_settings(self):
        """从 settings 加载颜色滤镜参数到滑块"""
        self._updating = True
        try:
            settings = self.data_manager.get_settings()
            for prefix in ("dark", "light"):
                for key in ("black_point", "white_point", "mid_gamma", "temperature", "acrylic", "bg_alpha_filter"):
                    setting_key = f"{prefix}_{key}"
                    default_val = 50
                    if key == "acrylic":
                        default_val = 30
                    elif key == "bg_alpha_filter":
                        default_val = 100

                    value = getattr(settings, setting_key, default_val)

                    slider_attr = f"_{prefix}_{key}_slider"
                    slider = getattr(self, slider_attr, None)
                    if slider is not None:
                        slider.blockSignals(True)
                        slider.setValue(value)
                        slider.blockSignals(False)

                    _, _, _, descs = self._get_slider_meta(key)
                    label_attr = f"_{prefix}_{key}_label"
                    label = getattr(self, label_attr, None)
                    if label and descs:
                        label.setText(self._desc_text(key, value, descs))
        finally:
            self._updating = False

    def _load_system_color_filter_settings(self, settings):
        """在 _load_system_settings 中调用 - 仅更新已可见的滑块"""
        if not self.color_filter_panel.isVisible():
            return
        self._load_color_filter_sliders_from_settings()

    # === Language Animation ===

    def _rebuild_pages_for_language(self, current_index=0, scroll_value=0):
        """Rebuild settings pages so translated source strings are recreated."""
        self.nav_widget.blockSignals(True)
        self.nav_widget.clear()

        while self.content_stack.count():
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()

        self._init_pages()
        self._init_nav_items()

        target_index = current_index if 0 <= current_index < self.content_stack.count() else 0
        self._ensure_page_built(target_index)
        self.content_stack.setCurrentIndex(target_index)
        for row in range(self.nav_widget.count()):
            item = self.nav_widget.item(row)
            if item and item.data(QtCompat.UserRole) == target_index:
                self.nav_widget.setCurrentRow(row)
                break
        self.nav_widget.blockSignals(False)
        self._restore_page_scroll_value(target_index, scroll_value)
        QTimer.singleShot(0, lambda: self._restore_page_scroll_value(target_index, scroll_value))

    def _language_fade_targets(self):
        return (self.nav_container, self.content_container)

    def _set_language_fade_opacity(self, opacity: float):
        from ui.utils.widget_opacity import set_opacity

        for widget in self._language_fade_targets():
            set_opacity(widget, opacity)

    def _current_language_fade_opacity(self) -> float:

        values: list[float] = []
        for widget in self._language_fade_targets():
            ss = widget.styleSheet() or ""
            idx = ss.rfind("opacity:")
            if idx < 0:
                continue
            start = max(ss.rfind(";", 0, idx), ss.rfind("{", 0, idx)) + 1
            fragment = ss[start:].lstrip()
            if not fragment.startswith("opacity:"):
                continue
            try:
                values.append(float(fragment[len("opacity:") :].split(";", 1)[0].strip()))
            except ValueError:
                continue
        if not values:
            return 1.0
        return max(0.0, min(1.0, sum(values) / len(values)))

    def _clear_language_fade_effects(self):
        from ui.utils.widget_opacity import set_opacity

        for widget in self._language_fade_targets():
            try:
                set_opacity(widget, 1.0)
            except Exception as exc:
                logger.debug("清除图形效果失败: %s", exc, exc_info=True)

    def _build_language_fade_group(self, start: float, end: float, duration: int, easing):
        from ui.utils.widget_opacity import animate_opacity

        group = QParallelAnimationGroup(self)  # type: ignore[unused-ignore, arg-type]
        for widget in self._language_fade_targets():
            anim = animate_opacity(
                widget,
                start,
                end,
                duration_ms=int(duration),
                clear_on_finish=False,
            )
            anim.setEasingCurve(easing)
            group.addAnimation(anim)
        return group

    def _switch_language_with_animation(self, language: str):
        """Fade text out, switch language, then fade text back in without movement."""
        generation = int(getattr(self, "_language_anim_generation", 0) or 0) + 1
        self._language_anim_generation = generation
        stop_animation(getattr(self, "_language_fade_out", None), owner="SettingsPanel.language.fade_out")
        stop_animation(getattr(self, "_language_fade_in", None), owner="SettingsPanel.language.fade_in")
        current_index = self.content_stack.currentIndex()  # type: ignore[attr-defined]
        scroll_value = self._current_page_scroll_value(current_index)  # type: ignore[attr-defined]
        self._language_animating = True

        start_opacity = self._current_language_fade_opacity()
        self._set_language_fade_opacity(start_opacity)
        fade_out = self._build_language_fade_group(start_opacity, 0.0, 180, QEasingCurve.InOutQuart)

        def apply_language():
            if generation != int(getattr(self, "_language_anim_generation", 0) or 0):
                return
            try:
                self.data_manager.set_language(language)
                self._rebuild_pages_for_language(current_index, scroll_value)
                self._load_settings()
                self._restore_page_scroll_value(current_index, scroll_value)
                QTimer.singleShot(
                    0,
                    lambda generation=generation: self._restore_language_scroll_if_current(
                        generation, current_index, scroll_value
                    ),
                )
                self.settings_changed.emit()
            finally:
                fade_in = self._build_language_fade_group(0.0, 1.0, 280, QEasingCurve.OutCubic)

                def finish():
                    if generation != int(getattr(self, "_language_anim_generation", 0) or 0):
                        return
                    self._language_animating = False
                    self._language_fade_out = None
                    self._language_fade_in = None
                    self._clear_language_fade_effects()

                fade_in.finished.connect(finish)
                self._language_fade_in = fade_in
                fade_in.start()

        fade_out.finished.connect(apply_language)
        self._language_fade_out = fade_out
        fade_out.start()

    def _restore_language_scroll_if_current(self, generation: int, page_index: int, scroll_value: int):
        if generation != int(getattr(self, "_language_anim_generation", 0) or 0):
            return
        self._restore_page_scroll_value(page_index, scroll_value)  # type: ignore[attr-defined]
