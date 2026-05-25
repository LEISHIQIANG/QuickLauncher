"""System settings page builder."""

import os

from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
)
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.tooltip_helper import install_tooltip

from .settings_helpers import SwitchButton


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
        layout.addLayout(theme_layout)

        # 日志修复
        layout, group = page.add_group("日志修复")
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(8)

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
            return DiagnosticsWindow(self.data_manager, tray_app=getattr(self, 'tray_app', None), parent=self)

        self._show_utility_window("_diagnostics_window", create_window, "refresh")

    def _on_shortcut_health_clicked(self):
        """打开图标检查。"""
        def create_window(theme):
            from ui.shortcut_health_window import ShortcutHealthWindow
            return ShortcutHealthWindow(self.data_manager, parent=self)

        self._show_utility_window("_shortcut_health_window", create_window, "refresh")
