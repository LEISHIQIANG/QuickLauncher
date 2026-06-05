"""
命令编辑对话框
"""

import logging
import os
import sys

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QCheckBox,
    QColor,
    QComboBox,
    QFont,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPen,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QtCompat,
    QThread,
    QTimer,
    QVBoxLayout,
    pyqtSignal,
)
from ui.styles.style import Colors, Glassmorphism, PopupMenu, StyleSheet
from ui.tooltip_helper import install_tooltip
from ui.utils.safe_file_dialog import get_existing_directory

from .base_dialog import BaseDialog
from .command_param_dialog import CommandParamDialog
from .command_profile_helpers import (
    format_command_env,
    format_command_params,
    parse_command_env_text,
    parse_command_params_text,
)
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)


class CommandTestThread(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, shortcut: ShortcutItem, timeout: float = 10.0, parent=None):
        super().__init__(parent)
        self.shortcut = shortcut
        self.timeout = timeout
        self._suppress_signal = False

    def suppress_result_signal(self):
        self._suppress_signal = True

    def run(self):
        try:
            from core import ShortcutExecutor

            if not ShortcutExecutor:
                result = {
                    "success": False,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "error": "执行器不可用，请检查运行环境依赖。",
                    "duration": 0.0,
                }
            else:
                result = ShortcutExecutor.test_command(self.shortcut, timeout=self.timeout)
        except Exception as e:
            result = {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "duration": 0.0,
            }
        if not self._suppress_signal:
            self.finished_signal.emit(result)


class CommandDialog(BaseDialog):
    """命令编辑对话框"""

    _orphaned_threads = []

    BUILTIN_COMMANDS = [
        ("置顶/取消置顶 (Toggle Topmost)", "toggle_topmost"),
        ("开启置顶 (Pin Window)", "pin_on"),
        ("关闭置顶 (Unpin Window)", "pin_off"),
        ("配置窗口 (Config Window)", "show_config_window"),
        ("运行日志 (Log Window)", "show_log"),
        ("斜杠命令帮助 (Slash Help)", "show_help"),
        ("诊断中心 (Diagnostics)", "show_diagnostics"),
        ("图标检查 (Shortcut Health)", "show_shortcut_health"),
        ("配置历史 (Config History)", "show_config_history"),
        ("清理图标缓存 (Clean Icon Cache)", "clean_icon_cache"),
        ("清理缓存 (Clean Cache)", "clean-cache"),
        ("重装全局钩子 (Reload Hooks)", "reload_hooks"),
        ("打开数据目录 (Data Directory)", "open_data_dir"),
        ("打开安装目录 (Install Directory)", "open_install_dir"),
        ("配置文件 data.json (Config File)", "open_config_file"),
        ("用户图标目录 (Icons Directory)", "open_icons_dir"),
        ("历史快照目录 (History Directory)", "open_history_dir"),
        ("自动备份目录 (Auto Backups)", "open_auto_backups_dir"),
        ("错误日志 error.log (Error Log)", "open_error_log"),
    ]

    BUILTIN_COMMAND_ALIASES = {
        "topmost": "toggle_topmost",
        "置顶": "toggle_topmost",
        "pin": "toggle_topmost",
        "toggle_topmost": "toggle_topmost",
        "topmost_on": "pin_on",
        "置顶开": "pin_on",
        "pin_on": "pin_on",
        "topmost_off": "pin_off",
        "置顶关": "pin_off",
        "unpin": "pin_off",
        "pin_off": "pin_off",
        "show_config": "show_config_window",
        "show_config_window": "show_config_window",
        "config_window": "show_config_window",
        "配置窗口": "show_config_window",
        "show_log": "show_log",
        "日志": "show_log",
        "show_help": "show_help",
        "help": "show_help",
        "帮助": "show_help",
        "show_diagnostics": "show_diagnostics",
        "diagnostics": "show_diagnostics",
        "diag": "show_diagnostics",
        "诊断": "show_diagnostics",
        "诊断中心": "show_diagnostics",
        "show_shortcut_health": "show_shortcut_health",
        "shortcut_health": "show_shortcut_health",
        "shortcut-health": "show_shortcut_health",
        "health": "show_shortcut_health",
        "图标检查": "show_shortcut_health",
        "诊断图标": "show_shortcut_health",
        "show_config_history": "show_config_history",
        "config_history": "show_config_history",
        "config-history": "show_config_history",
        "配置历史": "show_config_history",
        "clean_icon_cache": "clean_icon_cache",
        "icon_cache": "clean_icon_cache",
        "icon-cache": "clean_icon_cache",
        "clean-icons": "clean_icon_cache",
        "清理图标": "clean_icon_cache",
        "图标缓存": "clean_icon_cache",
        "clean_cache": "clean-cache",
        "clean-cache": "clean-cache",
        "cache-clean": "clean-cache",
        "clear-cache": "clean-cache",
        "清理缓存": "clean-cache",
        "缓存清理": "clean-cache",
        "reload_hooks": "reload_hooks",
        "reload-hooks": "reload_hooks",
        "hooks": "reload_hooks",
        "重装钩子": "reload_hooks",
        "open_data_dir": "open_data_dir",
        "app_data": "open_data_dir",
        "app-data": "open_data_dir",
        "config_dir": "open_data_dir",
        "config-dir": "open_data_dir",
        "data-dir": "open_data_dir",
        "数据目录": "open_data_dir",
        "配置目录": "open_data_dir",
        "open_install_dir": "open_install_dir",
        "install_dir": "open_install_dir",
        "install-dir": "open_install_dir",
        "program_dir": "open_install_dir",
        "program-dir": "open_install_dir",
        "project_dir": "open_install_dir",
        "project-dir": "open_install_dir",
        "安装目录": "open_install_dir",
        "项目目录": "open_install_dir",
        "软件目录": "open_install_dir",
        "open_config_file": "open_config_file",
        "config-file": "open_config_file",
        "data-json": "open_config_file",
        "data.json": "open_config_file",
        "配置文件": "open_config_file",
        "open_icons_dir": "open_icons_dir",
        "icons-dir": "open_icons_dir",
        "图标目录": "open_icons_dir",
        "open_history_dir": "open_history_dir",
        "history-dir": "open_history_dir",
        "历史目录": "open_history_dir",
        "open_auto_backups_dir": "open_auto_backups_dir",
        "auto-backups": "open_auto_backups_dir",
        "备份目录": "open_auto_backups_dir",
        "open_error_log": "open_error_log",
        "error-log": "open_error_log",
        "error.log": "open_error_log",
        "错误日志": "open_error_log",
    }

    @classmethod
    def _builtin_command_options(cls):
        options = list(cls.BUILTIN_COMMANDS)
        seen = {command for _name, command in options}
        try:
            from core import ensure_plugin_manager_initialized, ensure_registry_initialized, registry

            ensure_registry_initialized()
            ensure_plugin_manager_initialized()
            if registry is not None:
                for cmd in registry.list():
                    source = getattr(cmd, "source", "")
                    if not source.startswith("plugin-builtin:") or cmd.id in seen:
                        continue
                    title = getattr(cmd, "title", "") or cmd.id
                    options.append((title, cmd.id))
                    seen.add(cmd.id)
        except Exception:
            pass
        return options

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        # 清理已完成的孤儿线程
        self._cleanup_finished_orphans()

        super().__init__(parent)
        if shortcut:
            self.shortcut = shortcut
        else:
            self.shortcut = ShortcutItem(type=ShortcutType.COMMAND)

        self._custom_icon_path = self.shortcut.icon_path or ""
        self._command_test_thread = None

        # 确保有默认值
        if not hasattr(self.shortcut, "command_type"):
            self.shortcut.command_type = "cmd"

        self.setWindowTitle(tr("编辑运行命令") if shortcut else tr("添加运行命令"))
        self.setMinimumWidth(460)

        self._setup_window_icon()
        self._setup_ui()
        self._loading_data = False
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        """设置窗口图标 - 使用更可靠的方式"""
        if BaseDialog._is_compiled():
            return
        try:
            # 使用简单的几何图形绘制图标，避免依赖系统字体
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)

            painter = QPainter(pixmap)
            try:
                if not painter.isActive():
                    return
                painter.setRenderHint(QtCompat.Antialiasing)

                # 绘制一个简单的闪电形状（几何图形，不依赖字体）
                from qt_compat import QPoint, QPolygon

                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QColor(255, 200, 0))

                # 闪电形状的点
                points = [
                    QPoint(32, 10),
                    QPoint(28, 30),
                    QPoint(35, 30),
                    QPoint(25, 54),
                    QPoint(38, 35),
                    QPoint(30, 35),
                ]
                polygon = QPolygon(points)
                painter.drawPolygon(polygon)
            finally:
                painter.end()

            self.setWindowIcon(QIcon(pixmap))
        except Exception as exc:
            # 即使设置图标失败也不要崩溃
            logger.debug("设置窗口图标失败: %s", exc, exc_info=True)

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)

        custom_style = base_style + f"""
            QDialog {{ background: transparent; border: none; }}
            QGroupBox {{
                border: 1px solid {border_color};
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 8px;
                font-weight: 400;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: -9px;
                top: -3px;
                color: {title_color};
                font-size: 13px;
            }}
        """
        self.setStyleSheet(custom_style)

        # 1. 样式重置与定义
        # 这里的 text_primary 已经在之前被定义 (Step 519)

        # --- 输入框通用样式 ---
        input_style = f"""
            background-color: {"rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(255, 255, 255, 0.8)"};
            border: 1px solid {border_color};
            border-radius: 10px;
            color: {text_primary};
            font-size: 13px;
            selection-background-color: {selection_bg};
            selection-color: {selection_text};
        """

        self.name_edit.setStyleSheet(f"QLineEdit {{ {input_style} padding: 4px 8px; }}")
        self.icon_path_edit.setStyleSheet(f"QLineEdit {{ {input_style} padding: 4px 8px; }}")
        self.workdir_edit.setStyleSheet(f"QLineEdit {{ {input_style} padding: 4px 8px; }}")
        capture_label_color = "rgba(255, 255, 255, 0.58)" if theme == "dark" else "rgba(60, 60, 67, 0.62)"
        capture_spin_bg = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(255, 255, 255, 0.68)"
        capture_spin_disabled_bg = "rgba(255, 255, 255, 0.035)" if theme == "dark" else "rgba(255, 255, 255, 0.38)"
        capture_spin_disabled_text = "rgba(255, 255, 255, 0.34)" if theme == "dark" else "rgba(60, 60, 67, 0.32)"

        capture_option_style = f"""
            QLabel#CaptureOptionLabel {{
                color: {capture_label_color};
                font-size: 12px;
                font-weight: 400;
                background: transparent;
                padding: 0px;
            }}
            QLabel#CaptureOptionLabel:disabled {{
                color: {capture_spin_disabled_text};
            }}
            QSpinBox#CaptureOptionSpin {{
                background-color: {capture_spin_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_primary};
                font-size: 12px;
                font-weight: 400;
                padding: 1px 6px;
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QSpinBox#CaptureOptionSpin:disabled {{
                background-color: {capture_spin_disabled_bg};
                color: {capture_spin_disabled_text};
            }}
            QCheckBox#CommandPanelSizeCheck {{
                color: {text_primary};
                font-size: 12px;
                font-weight: 400;
                spacing: 6px;
                background: transparent;
            }}
            QCheckBox#CommandPanelSizeCheck:disabled {{
                color: {capture_spin_disabled_text};
            }}
            QCheckBox#CommandPanelSizeCheck::indicator {{
                width: 12px;
                height: 12px;
            }}
        """
        self.capture_timeout_label.setStyleSheet(capture_option_style)
        self.command_panel_size_label.setStyleSheet(capture_option_style)
        for button in self.command_panel_size_buttons:
            button.setStyleSheet(capture_option_style)
        self.capture_timeout_spin.setStyleSheet(capture_option_style)

        # --- 命令输入框容器样式 ---
        # 只有容器负责背景和边框，内部编辑器完全透明
        self.command_container.setStyleSheet(f"""
            #CommandContainer {{
                {input_style}
            }}
        """)

        # 内部编辑器：透明、无边框、无背景
        editor_style = f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {text_primary};
                font-size: 13px;
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
        """
        self.command_edit.setStyleSheet(editor_style)
        self.test_output.setStyleSheet(editor_style + f"""
            QPlainTextEdit {{
                background-color: {"rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(255, 255, 255, 0.75)"};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        # 再次强制视口透明（双重保险）
        if hasattr(self.command_edit, "viewport"):
            self.command_edit.viewport().setStyleSheet("background: transparent;")

        # --- 下拉菜单样式 ---
        # 主控件（按钮部分）样式 - 参考设置窗口的呼出位置下拉框
        combo_border = "rgba(255, 255, 255, 0.1)" if theme == "dark" else "rgba(0, 0, 0, 0.08)"
        combo_bg = "rgba(190, 190, 197, 0.22)" if theme == "dark" else "rgba(255, 255, 255, 0.8)"
        combo_hover_bg = "rgba(190, 190, 197, 0.30)" if theme == "dark" else "rgba(255, 255, 255, 1.0)"

        combo_qss = f"""
            QComboBox {{
                background-color: {combo_bg};
                border: 1px solid {combo_border};
                border-radius: 10px;
                padding: 5px 12px;
                    padding-right: 30px;
                    color: {text_primary};
                    min-height: 24px;
                    font-size: 12px;
                }}
                QComboBox:hover {{
                    background-color: {combo_hover_bg};
                    border: 1px solid {"#0A84FF" if theme == "dark" else "#007AFF"};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 24px;
                }}
                QComboBox::down-arrow {{
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='{("white" if theme == "dark" else "#555")}'><path d='M7 10l5 5 5-5z'/></svg>");
                    width: 14px;
                    height: 14px;
                }}
            """
        combo_qss = StyleSheet.get_combobox_style(theme)
        self.type_combo.setStyleSheet(combo_qss)
        self.builtin_combo.setStyleSheet(combo_qss)
        self.command_encoding_combo.setStyleSheet(StyleSheet.get_combobox_style(theme))

        profile_toggle_bg = "rgba(255, 255, 255, 0.025)" if theme == "dark" else "rgba(255, 255, 255, 0.42)"
        profile_toggle_hover = "rgba(255, 255, 255, 0.10)" if theme == "dark" else "rgba(255, 255, 255, 0.82)"
        profile_toggle_border = "rgba(255, 255, 255, 0.10)" if theme == "dark" else "rgba(0, 0, 0, 0.08)"
        profile_toggle_color = "rgba(255, 255, 255, 0.58)" if theme == "dark" else "rgba(60, 60, 67, 0.62)"
        self.advanced_profile_toggle.setStyleSheet(f"""
            QPushButton#CommandProfileToggle {{
                background-color: {profile_toggle_bg};
                border: 1px solid {profile_toggle_border};
                border-radius: 6px;
                color: {profile_toggle_color};
                font-size: 9px;
                font-weight: 400;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }}
            QPushButton#CommandProfileToggle:hover {{
                background-color: {profile_toggle_hover};
                border: 1px solid {"rgba(10, 132, 255, 0.75)" if theme == "dark" else "rgba(0, 122, 255, 0.75)"};
                color: {"rgba(255, 255, 255, 0.9)" if theme == "dark" else "rgba(28, 28, 30, 0.86)"};
            }}
            QPushButton#CommandProfileToggle:checked {{
                background-color: {profile_toggle_hover};
            }}
        """)
        self.advanced_profile_frame.setStyleSheet("""
            QFrame#CommandProfileFrame {
                background: transparent;
                border: none;
            }
        """)
        self._set_command_profile_toggle_icon(self.advanced_profile_toggle.isChecked())

        # 应用单选按钮样式
        try:
            from .theme_helper import get_radio_stylesheet

            radio_style = get_radio_stylesheet(theme)
            self.trigger_immediate_rb.setStyleSheet(radio_style)
            self.trigger_after_close_rb.setStyleSheet(radio_style)
        except Exception as exc:
            logger.debug("应用单选按钮样式失败: %s", exc, exc_info=True)
        self.setStyleSheet(custom_style)

        # 按钮使用扁平操作按钮样式（与主配置窗口底部四按钮一致）
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [
            self._browse_icon_btn,
            self._clear_icon_btn,
            self._browse_workdir_btn,
            self.insert_var_btn,
            self._add_param_btn,
            self._insert_param_btn,
            self._test_btn,
            self._cancel_btn,
            self._ok_btn,
        ]:
            btn.setStyleSheet(flat_btn_style)

        # 应用复选框样式
        cb_style = get_small_checkbox_stylesheet(theme)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)
        compact_option_cb_style = cb_style + f"""
            QCheckBox {{
                font-size: 12px;
                spacing: 6px;
                font-weight: 400;
            }}
            QCheckBox:disabled {{
                color: {capture_spin_disabled_text};
            }}
            QCheckBox::indicator {{
                width: 12px;
                height: 12px;
            }}
            """
        self.show_window_cb.setStyleSheet(compact_option_cb_style)
        self.run_as_admin_cb.setStyleSheet(compact_option_cb_style)
        self.variable_expansion_cb.setStyleSheet(compact_option_cb_style)
        self.capture_output_cb.setStyleSheet(compact_option_cb_style)
        for button in self.command_panel_size_buttons:
            button.setStyleSheet(compact_option_cb_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑运行命令" if self.shortcut.name else "添加运行命令")
        title_label.setStyleSheet("font-size: 12px; font-weight: 400; color: gray;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 1. 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)
        basic_layout.setContentsMargins(8, 0, 8, 8)

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)

        # 类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(
            [tr("CMD 命令"), tr("PowerShell 命令"), tr("Python 代码"), tr("Git Bash"), tr("内置命令")]
        )
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.type_combo.showPopup = lambda: self._show_type_popup()

        basic_layout.addRow(tr("类型:"), self.type_combo)

        layout.addWidget(basic_group)

        # 2. 图标设置 (移到第二位)
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 0, 6, 6)

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """)
        icon_layout.addWidget(self.icon_preview)

        icon_path_layout = QVBoxLayout()
        icon_path_layout.setSpacing(6)

        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_path_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(6)

        browse_icon_btn = QPushButton("选择图标...")
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton("清除")
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(clear_icon_btn)
        self._clear_icon_btn = clear_icon_btn

        icon_btn_layout.addStretch()
        icon_path_layout.addLayout(icon_btn_layout)

        # 图标反转选项（紧凑垂直排列，在清除按钮右侧）
        invert_v_layout = QVBoxLayout()
        invert_v_layout.setSpacing(2)
        invert_v_layout.setContentsMargins(0, 0, 0, 0)
        self.invert_theme_cb = QCheckBox("随主题反转")
        self.invert_current_cb = QCheckBox("当前反转")
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        invert_v_layout.addWidget(self.invert_theme_cb)
        invert_v_layout.addWidget(self.invert_current_cb)
        icon_btn_layout.addLayout(invert_v_layout)

        icon_layout.addLayout(icon_path_layout, 1)

        # 3. 命令设置 (移到第三位)
        cmd_group = QGroupBox("命令内容")
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setSpacing(4)  # 减小间距
        cmd_layout.setContentsMargins(8, 8, 8, 8)  # 减小内部边距

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.hint_label = QLabel("输入命令内容:")
        self.hint_label.setStyleSheet("color: gray; font-size: 11px; margin-top: -2px;")
        top_row.addWidget(self.hint_label, 1)

        self.insert_var_btn = QPushButton("插入")
        self.insert_var_btn.setFixedSize(54, 24)
        self.insert_var_btn.clicked.connect(self._show_insert_popup)
        top_row.addWidget(self.insert_var_btn, 0, QtCompat.AlignRight)

        self._test_btn = QPushButton("测试")
        self._test_btn.setFixedSize(54, 24)
        self._test_btn.clicked.connect(self._test_command)
        top_row.addWidget(self._test_btn, 0, QtCompat.AlignRight)

        cmd_layout.addLayout(top_row)

        # 使用 StackedWidget 切换不同类型的输入
        self.input_stack = QStackedWidget()

        # 1. 文本编辑器 (CMD/Python) - 重构为容器模式
        # 外层容器：负责背景、边框、圆角
        self.command_container = QFrame()
        self.command_container.setObjectName("CommandContainer")
        container_layout = QVBoxLayout(self.command_container)
        container_layout.setContentsMargins(4, 2, 4, 4)  # 内部留白，防止文字贴边
        container_layout.setSpacing(0)

        # 内层编辑器：完全透明，只负责显示文字
        self.command_edit = QPlainTextEdit()
        self.command_edit.setFixedHeight(92)
        self.command_edit.setTabChangesFocus(True)
        # 关键：关闭视口背景自动填充
        if hasattr(self.command_edit, "viewport"):
            self.command_edit.viewport().setAutoFillBackground(False)

        if hasattr(QPlainTextEdit, "LineWrapMode"):
            self.command_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.command_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        self.command_edit.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        self.command_edit.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)

        container_layout.addWidget(self.command_edit)
        self.input_stack.addWidget(self.command_container)

        # 2. 内置命令下拉框
        self.builtin_combo = QComboBox()
        self.builtin_combo.setFixedHeight(48)  # 同步高度
        for name, cmd in self._builtin_command_options():
            self.builtin_combo.addItem(name, cmd)
        self.builtin_combo.currentIndexChanged.connect(self._on_builtin_changed)
        self.builtin_combo.showPopup = lambda: self._show_builtin_popup()

        self.input_stack.addWidget(self.builtin_combo)
        self.input_stack.setFixedHeight(100)

        cmd_layout.addWidget(self.input_stack)
        self.test_output = QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setFixedHeight(72)
        self.test_output.setPlaceholderText("运行结果会显示在这里")
        self.test_output.setVisible(False)
        cmd_layout.addWidget(self.test_output)
        cmd_layout.setContentsMargins(8, 4, 8, 8)  # 恢复适度边距，保持比例协调
        layout.addWidget(cmd_group)

        # 4. 高级选项
        advanced_group = QGroupBox("高级选项")
        advanced_layout = QFormLayout(advanced_group)
        advanced_layout.setSpacing(6)
        advanced_layout.setContentsMargins(8, 0, 8, 8)

        workdir_layout = QHBoxLayout()
        workdir_layout.setSpacing(6)
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText("可选，工作目录")
        workdir_layout.addWidget(self.workdir_edit)
        self._browse_workdir_btn = QPushButton("浏览...")
        self._browse_workdir_btn.clicked.connect(self._browse_workdir)
        workdir_layout.addWidget(self._browse_workdir_btn)
        advanced_layout.addRow(tr("工作目录:"), workdir_layout)

        option_row = QHBoxLayout()
        option_row.setSpacing(8)
        self.advanced_profile_toggle = QPushButton()
        self.advanced_profile_toggle.setObjectName("CommandProfileToggle")
        self.advanced_profile_toggle.setCheckable(True)
        self.advanced_profile_toggle.setChecked(False)
        self.advanced_profile_toggle.setFixedSize(42, 12)
        self.advanced_profile_toggle.setToolTip(tr("高级设置"))
        self.advanced_profile_toggle.setCursor(QtCompat.PointingHandCursor)
        self.advanced_profile_toggle.clicked.connect(self._toggle_command_profile_panel)
        self.show_window_cb = QCheckBox("显示执行窗口")
        self.show_window_cb.setFixedHeight(26)
        self.show_window_cb.stateChanged.connect(self._update_capture_controls)
        self.run_as_admin_cb = QCheckBox("以管理员身份运行")
        self.run_as_admin_cb.setFixedHeight(26)
        self.run_as_admin_cb.stateChanged.connect(self._update_capture_controls)
        self.variable_expansion_cb = QCheckBox("解析变量")
        self.variable_expansion_cb.setFixedHeight(26)
        install_tooltip(self.variable_expansion_cb, "替换 {{clipboard}}、{{input}}、{{date}} 等占位符；Python 默认关闭")
        option_row.addWidget(self.show_window_cb)
        option_row.addWidget(self.run_as_admin_cb)
        option_row.addWidget(self.variable_expansion_cb)
        option_row.addStretch()
        advanced_layout.addRow("", option_row)

        capture_row = QHBoxLayout()
        capture_row.setSpacing(8)
        self.capture_output_cb = QCheckBox("捕获输出并显示在命令面板")
        self.capture_output_cb.setFixedHeight(26)
        self.capture_output_cb.stateChanged.connect(self._update_capture_controls)
        capture_row.addWidget(self.capture_output_cb)
        self.command_panel_size_label = QLabel("面板大小")
        self.command_panel_size_label.setObjectName("CaptureOptionLabel")
        capture_row.addWidget(self.command_panel_size_label)
        self.command_panel_size_group = QButtonGroup(self)
        self.command_panel_size_group.setExclusive(True)
        self.command_panel_size_buttons = []
        for text, value in (("小", "small"), ("中", "medium"), ("大", "large")):
            button = QCheckBox(text)
            button.setObjectName("CommandPanelSizeCheck")
            button.setProperty("panel_size", value)
            button.setFixedHeight(26)
            self.command_panel_size_group.addButton(button)
            self.command_panel_size_buttons.append(button)
            capture_row.addWidget(button)
        self.command_panel_size_buttons[1].setChecked(True)
        self.capture_timeout_label = QLabel("超时")
        self.capture_timeout_label.setObjectName("CaptureOptionLabel")
        capture_row.addWidget(self.capture_timeout_label)
        self.capture_timeout_spin = QSpinBox()
        self.capture_timeout_spin.setObjectName("CaptureOptionSpin")
        self.capture_timeout_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.capture_timeout_spin.setRange(1, 3600)
        self.capture_timeout_spin.setSuffix(" 秒")
        self.capture_timeout_spin.setFixedSize(72, 26)
        capture_row.addWidget(self.capture_timeout_spin)
        capture_row.addStretch()
        capture_toggle_widget = QFrame()
        capture_toggle_widget.setObjectName("CommandProfileToggleCell")
        capture_toggle_cell = QHBoxLayout(capture_toggle_widget)
        capture_toggle_cell.setContentsMargins(0, 3, 0, 0)
        capture_toggle_cell.addStretch()
        capture_toggle_cell.addWidget(self.advanced_profile_toggle, 0, QtCompat.AlignVCenter | QtCompat.AlignRight)
        advanced_layout.addRow(capture_toggle_widget, capture_row)

        self.advanced_profile_frame = QFrame()
        self.advanced_profile_frame.setObjectName("CommandProfileFrame")
        self.advanced_profile_frame.setVisible(False)
        profile_layout = QFormLayout(self.advanced_profile_frame)
        profile_layout.setSpacing(6)
        profile_layout.setContentsMargins(0, 2, 0, 0)

        self.command_encoding_combo = QComboBox()
        self.command_encoding_combo.setFixedHeight(32)
        self.command_encoding_combo.addItem("自动识别", "auto")
        self.command_encoding_combo.addItem("UTF-8", "utf-8")
        self.command_encoding_combo.addItem("GBK", "gbk")
        self.command_encoding_combo.addItem("系统 ANSI (mbcs)", "mbcs")
        self.command_encoding_combo.showPopup = lambda: self._show_encoding_popup()
        profile_layout.addRow("输出编码:", self.command_encoding_combo)

        self.command_env_edit = QPlainTextEdit()
        self.command_env_edit.setFixedHeight(52)
        self.command_env_edit.setPlaceholderText("每行一个 KEY=VALUE")
        profile_layout.addRow("环境变量:", self.command_env_edit)

        params_layout = QVBoxLayout()
        self.command_params_edit = QPlainTextEdit()
        self.command_params_edit.setFixedHeight(72)
        self.command_params_edit.setPlaceholderText(
            "每行一个参数: name,type,required,default,choice1|choice2，或 JSON 参数行"
        )
        params_btn_row = QHBoxLayout()
        add_param_btn = QPushButton("新增参数")
        add_param_btn.clicked.connect(self._add_param_template_line)
        self._add_param_btn = add_param_btn
        insert_param_btn = QPushButton("插入占位符")
        insert_param_btn.clicked.connect(self._insert_selected_param_placeholder)
        self._insert_param_btn = insert_param_btn
        params_btn_row.addWidget(add_param_btn)
        params_btn_row.addWidget(insert_param_btn)
        params_btn_row.addStretch()
        params_layout.addWidget(self.command_params_edit)
        params_layout.addLayout(params_btn_row)
        profile_layout.addRow("参数模板:", params_layout)
        advanced_layout.addRow("", self.advanced_profile_frame)

        layout.addWidget(advanced_group)

        # 5. 触发模式
        trigger_group = QGroupBox("触发模式")
        trigger_layout = QHBoxLayout(trigger_group)
        trigger_layout.setSpacing(12)
        trigger_layout.setContentsMargins(8, 0, 8, 8)

        self.trigger_immediate_rb = QRadioButton("无延迟运行")
        install_tooltip(self.trigger_immediate_rb, "点击图标后立刻运行命令，适合打开程序、网页或执行后台命令")

        self.trigger_after_close_rb = QRadioButton("窗口淡出后运行")
        install_tooltip(
            self.trigger_after_close_rb,
            "先关闭快捷启动面板并把焦点还给原来的窗口，再运行命令，适合需要操作原窗口的命令",
        )

        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        trigger_layout.addStretch()

        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)

        layout.addWidget(trigger_group)
        layout.addWidget(icon_group)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 32)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        self._ok_btn = ok_btn

        layout.addLayout(btn_layout)

        # 自适应大小
        self.adjustSize()
        self.setMinimumWidth(460)

    def _on_type_changed(self, index):
        """类型改变"""
        if index == 0:  # CMD
            self.hint_label.setText(tr("输入要执行的CMD命令（静默运行，不显示窗口）:"))
            self.command_edit.setPlaceholderText("例如: shutdown /s /t 0")
            self.input_stack.setCurrentIndex(0)
            self.input_stack.setFixedHeight(100)
            self.show_window_cb.setEnabled(True)
            self._update_capture_controls()
            self.insert_var_btn.setEnabled(True)
            self._test_btn.setEnabled(True)
            self.variable_expansion_cb.setEnabled(True)
            if not getattr(self, "_loading_data", False):
                self.variable_expansion_cb.setChecked(False)
        elif index == 1:  # PowerShell
            self.hint_label.setText(tr("输入要执行的 PowerShell 命令（静默运行，不显示窗口）:"))
            self.command_edit.setPlaceholderText("例如: Get-ChildItem {{selected_file_dir:q}}")
            self.input_stack.setCurrentIndex(0)
            self.input_stack.setFixedHeight(100)
            self.show_window_cb.setEnabled(True)
            self._update_capture_controls()
            self.insert_var_btn.setEnabled(True)
            self._test_btn.setEnabled(True)
            self.variable_expansion_cb.setEnabled(True)
            if not getattr(self, "_loading_data", False):
                self.variable_expansion_cb.setChecked(False)
        elif index == 2:  # Python
            self.hint_label.setText(tr("输入要执行的 Python 代码（通过系统 Python 运行）:"))
            self.command_edit.setPlaceholderText("例如: os.system('notepad')")
            self.input_stack.setCurrentIndex(0)
            self.input_stack.setFixedHeight(100)
            self.show_window_cb.setEnabled(True)
            self._update_capture_controls()
            self.insert_var_btn.setEnabled(True)
            self._test_btn.setEnabled(True)
            self.variable_expansion_cb.setEnabled(True)
            if not getattr(self, "_loading_data", False):
                self.variable_expansion_cb.setChecked(False)
        elif index == 3:  # Git Bash
            self.hint_label.setText(tr("输入要执行的 Bash 命令（通过 Git Bash 运行）:"))
            self.command_edit.setPlaceholderText("例如: ls -la /c/Users")
            self.input_stack.setCurrentIndex(0)
            self.input_stack.setFixedHeight(100)
            self.show_window_cb.setEnabled(True)
            self._update_capture_controls()
            self.insert_var_btn.setEnabled(True)
            self._test_btn.setEnabled(True)
            self.variable_expansion_cb.setEnabled(True)
            if not getattr(self, "_loading_data", False):
                self.variable_expansion_cb.setChecked(False)
        elif index == 4:  # Built-in
            self.hint_label.setText(tr("选择内置命令:"))
            self.input_stack.setCurrentIndex(1)
            self.input_stack.setFixedHeight(48)
            self.insert_var_btn.setEnabled(False)
            self._test_btn.setEnabled(False)
            self.variable_expansion_cb.setChecked(False)
            self.variable_expansion_cb.setEnabled(False)
            # 触发一次内置命令变更，以更新图标
            self._on_builtin_changed(self.builtin_combo.currentIndex())

        # 更新图标
        self._update_icon_preview()

    def _update_capture_controls(self):
        if not hasattr(self, "capture_output_cb"):
            return
        is_builtin = getattr(self, "type_combo", None) is not None and self.type_combo.currentIndex() == 4
        if is_builtin:
            command = self.builtin_combo.itemData(self.builtin_combo.currentIndex())
            is_builtin = not self._is_plugin_builtin_command(command or "")
        blocked = is_builtin or self.show_window_cb.isChecked() or self.run_as_admin_cb.isChecked()
        if blocked:
            self.capture_output_cb.setChecked(False)
        self.capture_output_cb.setEnabled(not blocked)
        enabled = self.capture_output_cb.isChecked() and not blocked
        self.command_panel_size_label.setEnabled(enabled)
        for button in self.command_panel_size_buttons:
            button.setEnabled(enabled)
        self.capture_timeout_label.setEnabled(enabled)
        self.capture_timeout_spin.setEnabled(enabled)

    def _is_plugin_builtin_command(self, command_id: str) -> bool:
        try:
            from core import registry
            if registry is None:
                return False
            cmd = registry.get(command_id)
            return cmd is not None and getattr(cmd, "source", "").startswith("plugin-builtin:")
        except Exception:
            return False

    def _update_builtin_advanced_options(self):
        """根据当前选中的 builtin 命令是否来自插件，启用或禁用高级选项。"""
        command = self.builtin_combo.itemData(self.builtin_combo.currentIndex())
        is_plugin = self._is_plugin_builtin_command(command or "")
        self.show_window_cb.setEnabled(is_plugin)
        if not getattr(self, "_loading_data", False):
            if not is_plugin:
                self.show_window_cb.setChecked(False)
                self.capture_output_cb.setChecked(False)
            else:
                self._apply_plugin_builtin_defaults(command)
        self._update_capture_controls()

    def _apply_plugin_builtin_defaults(self, command_id: str) -> None:
        """将 plugin-builtin 命令的 param 默认值填入高级选项 checkbox。"""
        try:
            from core import registry
            if registry is None:
                return
            cmd = registry.get(command_id)
            if cmd is None or not getattr(cmd, "params", None):
                return
            for param in cmd.params:
                name = getattr(param, "name", "")
                default = str(getattr(param, "default", "") or "").lower()
                val = default == "true"
                if name == "show_window":
                    self.show_window_cb.setChecked(val)
                elif name == "capture_output":
                    self.capture_output_cb.setChecked(val)
        except Exception:
            pass

    def _on_builtin_changed(self, index):
        """内置命令改变"""
        self.invert_current_cb.setChecked(False)
        command = self.builtin_combo.itemData(index)
        if not command:
            return
        if getattr(self, "_loading_data", False) and self._custom_icon_path:
            self._update_icon_preview()
            return

        import os

        system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")

        # 自动设置图标
        icon_path = ""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        command_icon_files = {
            "open_task_manager": "taskmgr.png",
            "open_windows_settings": "windows-settings.png",
            "open_services": "services.png",
            "open_device_manager": "device-manager.png",
            "open_disk_management": "disk-management.png",
            "open_network_connections": "network-connections.png",
            "open_startup_folder": "startup-folder.png",
            "open_system_info": "system-info.png",
            "open_config_file": "config-file.png",
            "open_icons_dir": "icons-dir.png",
            "open_history_dir": "history-dir.png",
            "open_auto_backups_dir": "auto-backups.png",
            "open_error_log": "error-log.png",
        }
        if command in command_icon_files:
            icon_path = os.path.join(base_dir, "assets", "command_icons", command_icon_files[command])
        elif command == "open_control_panel":
            icon_path = os.path.join(system32, "control.exe")
        elif command == "open_this_pc":
            # 使用资源 ID (-109) 而不是索引
            icon_path = os.path.join(system32, "imageres.dll,-109")
        elif command == "open_recycle_bin":
            # 使用资源 ID (-55) (Recycle Bin Empty)
            icon_path = os.path.join(system32, "imageres.dll,-55")
        elif command == "show_config_window":
            icon_path = os.path.join(base_dir, "assets", "setting.ico")
        elif "topmost" in command or "pin" in command:
            # 尝试给置顶命令也加个图标 (imageres.dll, -229 is a pin icon in Win10/11 usually)
            pass

        if icon_path:
            self._custom_icon_path = icon_path
            self.icon_path_edit.setText(icon_path)
        else:
            if not getattr(self, "_loading_data", False):
                self._custom_icon_path = ""
                self.icon_path_edit.clear()
        self._update_icon_preview()
        self._update_builtin_advanced_options()

    def _selected_popup_button_qss(self) -> str:
        bg = Colors.get_selection_bg(self.theme)
        fg = Colors.get_selection_text(self.theme)
        border = "rgba(10, 132, 255, 0.42)" if self.theme == "dark" else "rgba(0, 122, 255, 0.22)"
        return f"QPushButton{{ background:{bg}; color:{fg}; border:1px solid {border}; }}"

    def _show_type_popup(self):
        """显示类型选择弹出菜单"""
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        self._type_menu = menu
        items = [self.type_combo.itemText(i) for i in range(self.type_combo.count())]
        current = self.type_combo.currentText()
        for i, item_text in enumerate(items):

            def _make_cb(idx):
                def cb():
                    self.type_combo.setCurrentIndex(idx)

                return cb

            btn = menu.add_action(item_text, _make_cb(i))
            if item_text == current:
                btn.setStyleSheet(btn.styleSheet() + self._selected_popup_button_qss())
        pos = self.type_combo.mapToGlobal(self.type_combo.rect().bottomLeft())
        menu.setMinimumWidth(self.type_combo.width())
        menu.popup(pos)

    def _show_builtin_popup(self):
        """显示内置命令选择弹出菜单"""
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        self._builtin_menu = menu
        current = self.builtin_combo.currentText()
        for i in range(self.builtin_combo.count()):
            item_text = self.builtin_combo.itemText(i)

            def _make_cb(idx):
                def cb():
                    self.builtin_combo.setCurrentIndex(idx)

                return cb

            btn = menu.add_action(item_text, _make_cb(i))
            if item_text == current:
                btn.setStyleSheet(btn.styleSheet() + self._selected_popup_button_qss())
        pos = self.builtin_combo.mapToGlobal(self.builtin_combo.rect().bottomLeft())
        menu.setMinimumWidth(self.builtin_combo.width())
        menu.popup(pos)

    def _show_encoding_popup(self):
        """显示输出编码选择弹出菜单"""
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        self._encoding_menu = menu
        current = self.command_encoding_combo.currentText()
        for i in range(self.command_encoding_combo.count()):
            item_text = self.command_encoding_combo.itemText(i)

            def _make_cb(idx):
                def cb():
                    self.command_encoding_combo.setCurrentIndex(idx)

                return cb

            btn = menu.add_action(item_text, _make_cb(i))
            if item_text == current:
                btn.setStyleSheet(btn.styleSheet() + self._selected_popup_button_qss())
        pos = self.command_encoding_combo.mapToGlobal(self.command_encoding_combo.rect().bottomLeft())
        menu.setMinimumWidth(self.command_encoding_combo.width())
        menu.popup(pos)

    def _show_insert_popup(self):
        """显示变量和常用片段菜单"""
        if self.type_combo.currentIndex() == 4:
            return
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        self._insert_menu = menu
        items = [
            ("剪贴板", "{{clipboard}}"),
            ("剪贴板(引用)", "{{clipboard:q}}"),
            ("运行时输入", "{{input}}"),
            ("选中文本", "{{selected_text}}"),
            ("选中文本(引用)", "{{selected_text:q}}"),
            ("选中文件(引用)", "{{selected_file:q}}"),
            ("选中文件列表(引用)", "{{selected_files:q}}"),
            ("选中文件名(引用)", "{{selected_file_name:q}}"),
            ("选中文件目录(引用)", "{{selected_file_dir:q}}"),
            ("日期", "{{date}}"),
            ("时间", "{{time}}"),
            ("内网 IP", "{{LAN_IP}}"),
            ("公网 IP", "{{WAN_IP}}"),
            ("程序目录", "{{app_dir}}"),
            ("配置目录", "{{config_dir}}"),
            ("PowerShell 片段", "Write-Output {{clipboard:q}}"),
            ("Python 模板", "import os\nprint(os.getcwd())"),
        ]
        for label, text in items:
            menu.add_action(label, lambda t=text: self._insert_command_text(t))
        pos = self.insert_var_btn.mapToGlobal(self.insert_var_btn.rect().bottomLeft())
        menu.setMinimumWidth(180)
        menu.popup(pos)

    def _insert_command_text(self, text: str):
        cursor = self.command_edit.textCursor()
        if cursor.hasSelection():
            cursor.insertText(text)
        else:
            if self.command_edit.toPlainText() and not self.command_edit.toPlainText().endswith(("\n", " ")):
                cursor.insertText(" ")
            cursor.insertText(text)
        self.command_edit.setTextCursor(cursor)
        self.command_edit.setFocus()
        if "{{selected_text" in text:
            self.variable_expansion_cb.setChecked(True)
            self.trigger_after_close_rb.setChecked(True)
        elif text.startswith("{{") or "{{input" in text or "{{clipboard" in text:
            self.variable_expansion_cb.setChecked(True)

    def _add_param_template_line(self):
        dialog = CommandParamDialog(parent=self)
        if dialog.exec_() != dialog.Accepted:
            return
        param = dialog.param()
        if not param:
            return
        params = self._parse_command_params_text()
        params.append(param)
        self.command_params_edit.setPlainText(self._format_command_params(params))

    def _insert_selected_param_placeholder(self):
        params = self._parse_command_params_text()
        if not params:
            self.command_params_edit.setPlainText("name,text,true,,")
            params = self._parse_command_params_text()
        if not params:
            return
        menu = PopupMenu(theme=self.theme, radius=8, parent=None)
        quote_by_default = self.type_combo.currentIndex() in (0, 1, 3)
        for param in params:
            name = str(param.get("name") or "").strip()
            if not name:
                continue
            preferred = f"{{{{param:{name}:q}}}}" if quote_by_default else f"{{{{param:{name}}}}}"
            plain = f"{{{{param:{name}}}}}"
            quoted = f"{{{{param:{name}:q}}}}"
            menu.add_action(preferred, lambda text=preferred: self._insert_command_text(text), enabled=True)
            alternate = plain if preferred == quoted else quoted
            menu.add_action(alternate, lambda text=alternate: self._insert_command_text(text), enabled=True)
        menu.popup(self._insert_param_btn.mapToGlobal(self._insert_param_btn.rect().bottomLeft()))

    def _parse_command_params_text(self):
        return parse_command_params_text(self.command_params_edit.toPlainText())

    @staticmethod
    def _format_command_params(params) -> str:
        return format_command_params(params)

    @staticmethod
    def _parse_env_text(text: str) -> dict:
        return parse_command_env_text(text)

    @staticmethod
    def _format_env(env: dict) -> str:
        return format_command_env(env)

    def _set_command_profile_panel_expanded(self, expanded: bool):
        if not hasattr(self, "advanced_profile_frame"):
            return
        self.advanced_profile_frame.setVisible(expanded)
        self.advanced_profile_toggle.setChecked(expanded)
        self.advanced_profile_toggle.setText("")
        self._set_command_profile_toggle_icon(expanded)
        self._schedule_command_profile_resize()

    def _toggle_command_profile_panel(self):
        self._set_command_profile_panel_expanded(self.advanced_profile_toggle.isChecked())

    def _set_command_profile_toggle_icon(self, expanded: bool):
        if not hasattr(self, "advanced_profile_toggle"):
            return
        pixmap = QPixmap(18, 8)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            color = QColor(255, 255, 255, 150) if self.theme == "dark" else QColor(60, 60, 67, 150)
            painter.setPen(QPen(color, 1.4))
            if expanded:
                painter.drawLine(4, 5, 9, 2)
                painter.drawLine(9, 2, 14, 5)
            else:
                painter.drawLine(4, 2, 9, 5)
                painter.drawLine(9, 5, 14, 2)
        finally:
            painter.end()
        self.advanced_profile_toggle.setIcon(QIcon(pixmap))

    def _schedule_command_profile_resize(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.updateGeometry()
        self._resize_to_layout_hint()
        QTimer.singleShot(0, self._resize_to_layout_hint)

    def _resize_to_layout_hint(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        hint = self.sizeHint()
        target_width = max(self.minimumWidth(), self.width(), hint.width())
        target_height = max(self.minimumHeight(), hint.height())
        if target_height > 0:
            self.resize(target_width, target_height)

    def _browse_workdir(self):
        folder = get_existing_directory(self, tr("选择工作目录"))
        if folder:
            self.workdir_edit.setText(folder)

    def _selected_command_panel_size(self) -> str:
        for button in getattr(self, "command_panel_size_buttons", []):
            if button.isChecked():
                value = str(button.property("panel_size") or "").lower().strip()
                if value in ("small", "medium", "large"):
                    return value
        return "medium"

    def _set_command_panel_size(self, size: str):
        size = str(size or "medium").lower().strip()
        if size not in ("small", "medium", "large"):
            size = "medium"
        for button in getattr(self, "command_panel_size_buttons", []):
            if button.property("panel_size") == size:
                button.setChecked(True)
                return

    def _build_preview_shortcut(self) -> ShortcutItem:
        import copy

        shortcut = copy.copy(self.shortcut)
        type_index = self.type_combo.currentIndex()
        shortcut.type = ShortcutType.COMMAND
        shortcut.name = self.name_edit.text().strip()[:6] or "测试"
        if type_index == 0:
            shortcut.command_type = "cmd"
        elif type_index == 1:
            shortcut.command_type = "powershell"
        elif type_index == 2:
            shortcut.command_type = "python"
        elif type_index == 3:
            shortcut.command_type = "bash"
        else:
            shortcut.command_type = "builtin"
        shortcut.command = (
            self.builtin_combo.currentData() if type_index == 4 else self.command_edit.toPlainText().strip()
        )
        shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        shortcut.show_window = self.show_window_cb.isChecked()
        shortcut.working_dir = self.workdir_edit.text().strip()
        shortcut.run_as_admin = self.run_as_admin_cb.isChecked()
        shortcut.command_variables_enabled = self.variable_expansion_cb.isChecked()
        shortcut.capture_output = self.capture_output_cb.isChecked()
        shortcut.command_timeout_seconds = float(self.capture_timeout_spin.value())
        shortcut.command_panel_size = self._selected_command_panel_size()
        shortcut.command_params = self._parse_command_params_text()
        shortcut.command_env = self._parse_env_text(self.command_env_edit.toPlainText())
        shortcut.command_encoding = self.command_encoding_combo.currentData() or "auto"
        return shortcut

    def _collect_runtime_inputs(self, command: str):
        try:
            from core.command_variables import collect_input_prompts

            prompts = collect_input_prompts(command)
        except Exception as exc:
            logger.debug("收集输入提示失败: %s", exc, exc_info=True)
            return {}
        values = {}
        for prompt in prompts:
            label = prompt or "输入内容"
            try:
                from ui.styles.themed_messagebox import ThemedInputDialog

                value, ok = ThemedInputDialog.getText(self, "运行参数", label)
            except Exception as e:
                logger.debug("加载 ThemedInputDialog 失败，取消默认输入框回退: %s", e, exc_info=True)
                return None
            if not ok:
                return None
            values[prompt] = value
            if not prompt:
                values["input"] = value
        return values

    def _test_command(self):
        if self.type_combo.currentIndex() == 4:
            return
        if self._command_test_thread is not None and self._command_test_thread.isRunning():
            return
        shortcut = self._build_preview_shortcut()
        self.test_output.setVisible(True)
        self.adjustSize()
        if not shortcut.command:
            self.test_output.setPlainText("命令内容为空。")
            return
        inputs = self._collect_runtime_inputs(shortcut.command) if shortcut.command_variables_enabled else {}
        if inputs is None:
            self.test_output.setPlainText("测试运行已取消。")
            return
        if inputs:
            from core.command_io import CommandInvocationSnapshot, prepare_runtime_shortcut

            shortcut = prepare_runtime_shortcut(
                shortcut,
                CommandInvocationSnapshot(
                    command_id=getattr(shortcut, "id", ""),
                    command_title=getattr(shortcut, "name", ""),
                    input_values=dict(inputs),
                ),
            )

        self._test_btn.setEnabled(False)
        self.test_output.setPlainText("正在测试...")
        self._command_test_thread = CommandTestThread(
            shortcut, timeout=float(self.capture_timeout_spin.value()), parent=None
        )
        self._command_test_thread.finished_signal.connect(self._show_test_result)
        self._command_test_thread.start()

    def _show_test_result(self, result: dict):
        if self._dialog_finished or not hasattr(self, "test_output") or not hasattr(self, "_test_btn"):
            return
        lines = [
            f"状态: {'成功' if result.get('success') else '失败'}",
            f"退出码: {result.get('exit_code')}",
            f"耗时: {result.get('duration', 0):.2f}s",
        ]
        if result.get("resolved_command"):
            lines.extend(["", "最终命令:", str(result.get("resolved_command"))])
        if result.get("error"):
            lines.extend(["", "错误:", str(result.get("error"))])
        if result.get("stdout"):
            lines.extend(["", "stdout:", str(result.get("stdout"))])
        if result.get("stderr"):
            lines.extend(["", "stderr:", str(result.get("stderr"))])
        self.test_output.setPlainText("\n".join(lines))
        self._test_btn.setEnabled(self.type_combo.currentIndex() != 4)
        self._command_test_thread = None

    def closeEvent(self, event):
        super().closeEvent(event)

    def done(self, result):
        self._cleanup_command_test_thread()
        super().done(result)

    def _cleanup_command_test_thread(self):
        # 强制终止正在后台测试的挂起子进程（如果有），避免垃圾子进程泄露
        if hasattr(self, "shortcut") and self.shortcut:
            try:
                process = getattr(self.shortcut, "_active_test_process", None)
                if process and process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=1.0)
                        logger.info("测试后台挂起子进程已被成功强制终止清理")
                    except Exception as exc:
                        logger.debug("子进程终止超时: %s", exc, exc_info=True)
            except Exception as e:
                logger.debug(f"清理挂起子进程时发生异常: {e}")

        thread = getattr(self, "_command_test_thread", None)
        if thread is None:
            return
        try:
            thread.finished_signal.disconnect(self._show_test_result)
        except Exception as exc:
            logger.debug("断开信号失败: %s", exc, exc_info=True)
        try:
            thread.suppress_result_signal()
        except Exception as exc:
            logger.debug("抑制结果信号失败: %s", exc, exc_info=True)
        if thread.isRunning():
            thread.wait(500)
        if thread.isRunning():
            thread.wait(2000)  # 延长等待替代 terminate，让线程自然完成
        if thread.isRunning():
            try:
                thread.setParent(None)
                self._orphaned_threads.append(thread)
                _cls = type(self)
                thread.finished.connect(lambda t=thread: _cls._forget_orphaned_thread(t))
                thread.finished.connect(thread.deleteLater)
            except Exception as exc:
                logger.debug("设置孤儿线程清理失败: %s", exc, exc_info=True)
            self._command_test_thread = None
        else:
            try:
                thread.deleteLater()
            except Exception as exc:
                logger.debug("删除线程失败: %s", exc, exc_info=True)
            self._command_test_thread = None

    @classmethod
    def _forget_orphaned_thread(cls, thread):
        try:
            cls._orphaned_threads.remove(thread)
        except ValueError:
            logger.debug("移除孤立线程记录失败", exc_info=True)

    @classmethod
    def _cleanup_finished_orphans(cls):
        """清理已完成的孤儿线程（仅从列表移除，deleteLater 由 finished 信号负责）"""
        if not cls._orphaned_threads:
            return
        still_running = [t for t in cls._orphaned_threads if t.isRunning()]
        removed = len(cls._orphaned_threads) - len(still_running)
        cls._orphaned_threads = still_running
        if removed:
            logger.info(f"清理了 {removed} 个已完成的孤儿线程")

    def _load_data(self):
        """加载数据"""
        self._loading_data = True
        try:
            self.name_edit.setText(self.shortcut.name or "")

            # 暂时阻塞信号，避免初始化时频繁触发
            self.type_combo.blockSignals(True)

            # 加载命令类型
            cmd_type = getattr(self.shortcut, "command_type", "cmd")
            command = self.shortcut.command or ""

            if cmd_type == "powershell":
                self.type_combo.setCurrentIndex(1)
            elif cmd_type == "python":
                self.type_combo.setCurrentIndex(2)
            elif cmd_type == "bash":
                self.type_combo.setCurrentIndex(3)
            elif cmd_type == "builtin":
                self.type_combo.setCurrentIndex(4)
            else:
                self.type_combo.setCurrentIndex(0)

            self.type_combo.blockSignals(False)

            # 加载触发模式
            if getattr(self.shortcut, "trigger_mode", "immediate") == "after_close":
                self.trigger_after_close_rb.setChecked(True)
            else:
                self.trigger_immediate_rb.setChecked(True)

            # 加载命令内容
            if cmd_type == "builtin":
                # 尝试在下拉框中选中对应命令
                index = self.builtin_combo.findData(command)
                if index < 0 and command:
                    self.builtin_combo.addItem(f"当前内置命令 ({command})", command)
                    index = self.builtin_combo.findData(command)
                if index >= 0:
                    self.builtin_combo.setCurrentIndex(index)
            else:
                self.command_edit.setPlainText(command)

            if self._custom_icon_path:
                self.icon_path_edit.setText(self._custom_icon_path)

            # 加载反转设置
            self.invert_theme_cb.setChecked(self.shortcut.icon_invert_with_theme)
            self.invert_current_cb.setChecked(self.shortcut.icon_invert_current)
            self.show_window_cb.setChecked(getattr(self.shortcut, "show_window", False))
            self.workdir_edit.setText(getattr(self.shortcut, "working_dir", "") or "")
            self.run_as_admin_cb.setChecked(getattr(self.shortcut, "run_as_admin", False))
            self.capture_output_cb.setChecked(getattr(self.shortcut, "capture_output", False))
            self.capture_timeout_spin.setValue(int(getattr(self.shortcut, "command_timeout_seconds", 10.0) or 10.0))
            self._set_command_panel_size(getattr(self.shortcut, "command_panel_size", "medium"))
            self.command_params_edit.setPlainText(
                self._format_command_params(getattr(self.shortcut, "command_params", []))
            )
            self.command_env_edit.setPlainText(self._format_env(getattr(self.shortcut, "command_env", {})))
            enc = str(getattr(self.shortcut, "command_encoding", "auto") or "auto").lower()
            idx = self.command_encoding_combo.findData(enc)
            self.command_encoding_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.variable_expansion_cb.setChecked(getattr(self.shortcut, "command_variables_enabled", False))
            has_profile_options = (
                enc != "auto"
                or bool(getattr(self.shortcut, "command_env", {}))
                or bool(getattr(self.shortcut, "command_params", []))
            )
            self._set_command_profile_panel_expanded(has_profile_options)

            # 手动调用一次以初始化界面状态
            self._on_type_changed(self.type_combo.currentIndex())

        except Exception as exc:
            logger.debug("加载数据失败: %s", exc, exc_info=True)
        finally:
            self._loading_data = False

    def _update_icon_preview(self):
        """更新图标预览"""
        # 避免递归调用或死循环，如果正在更新中则返回
        if getattr(self, "_updating_icon", False):
            return
        self._updating_icon = True

        try:
            pixmap = None

            if self._custom_icon_path:
                try:
                    should_load = False
                    # 检查是否为资源路径 (包含逗号)
                    if "," in self._custom_icon_path:
                        should_load = True
                    # 或者检查文件是否存在
                    elif os.path.exists(self._custom_icon_path):
                        should_load = True

                    if should_load:
                        from core.icon_extractor import IconExtractor

                        pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
                except Exception as e:
                    logger.debug(f"加载自定义图标失败: {e}")

            if not pixmap or pixmap.isNull():
                pixmap = self._create_command_icon(48)

            # 应用反转
            if (
                self.invert_theme_cb.isChecked()
                and self.invert_current_cb.isChecked()
                and pixmap
                and not pixmap.isNull()
            ):
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.invert_pixmap(pixmap)

            # 缩放到预览尺寸
            if pixmap and not pixmap.isNull():
                pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                self.icon_preview.setPixmap(pixmap)
            else:
                self.icon_preview.clear()
        except Exception as exc:
            logger.debug("更新图标预览失败: %s", exc, exc_info=True)
        finally:
            self._updating_icon = False

    def _create_command_icon(self, size: int) -> QPixmap:
        """创建命令图标"""
        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(QtCompat.transparent)

            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)

                painter.setBrush(QColor(50, 50, 50))
                painter.setPen(QtCompat.NoPen)
                margin = size // 8
                painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)

                painter.setPen(QColor(0, 255, 0))
                font = QFont("Consolas", size // 3)
                font.setBold(True)
                painter.setFont(font)

                # 根据类型显示不同图标文本
                text = ">_"
                if self.type_combo.currentIndex() == 1:  # PowerShell
                    text = "PS"
                    painter.setPen(QColor(90, 180, 255))
                elif self.type_combo.currentIndex() == 2:  # Python
                    text = "Py"
                    painter.setPen(QColor(255, 215, 0))  # 金色
                elif self.type_combo.currentIndex() == 3:  # Git Bash
                    text = "Sh"
                    painter.setPen(QColor(232, 79, 52))  # 橙红色
                elif self.type_combo.currentIndex() == 4:  # Built-in
                    text = "In"
                    painter.setPen(QColor(100, 200, 255))  # 蓝色

                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, text)
            finally:
                painter.end()
            return pixmap
        except Exception as e:
            logger.error("创建命令图标失败: %s", e, exc_info=True)
            # 返回一个空的透明图片防止后续崩溃
            empty = QPixmap(size, size)
            empty.fill(QtCompat.transparent)
            return empty

    def _browse_icon(self):
        """浏览图标文件"""
        file_path = choose_custom_icon(self, "选择图标")
        if file_path:
            self._custom_icon_path = file_path
            self.icon_path_edit.setText(file_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()

    def _clear_icon(self):
        """清除自定义图标"""
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
        self.invert_theme_cb.setChecked(False)
        self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_invert_theme_changed(self, state):
        """随主题反转勾选变化"""
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_ok(self):
        """确定"""
        name = self.name_edit.text().strip()

        type_index = self.type_combo.currentIndex()
        if type_index == 4:  # Built-in
            command = self.builtin_combo.currentData()
        else:
            command = self.command_edit.toPlainText().strip()

        if not name:
            self.name_edit.setFocus()
            try:
                from ui.styles.themed_messagebox import ThemedMessageBox

                ThemedMessageBox.warning(self, tr("校验失败"), tr("请输入命令名称！"))
            except Exception as exc:
                logger.debug("显示警告对话框失败: %s", exc, exc_info=True)
            return

        if not command:
            if type_index == 4:
                pass  # 内置命令一定有值
            else:
                self.command_edit.setFocus()
                try:
                    from ui.styles.themed_messagebox import ThemedMessageBox

                    ThemedMessageBox.warning(self, tr("校验失败"), tr("请输入命令内容！"))
                except Exception as exc:
                    logger.debug("显示警告对话框失败: %s", exc, exc_info=True)
                return

        if (
            self.variable_expansion_cb.isChecked()
            and "{{selected_text" in command
            and self.trigger_immediate_rb.isChecked()
        ):
            self.trigger_after_close_rb.setChecked(True)

        self.accept()

    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]

        type_index = self.type_combo.currentIndex()
        if type_index == 0:
            self.shortcut.command_type = "cmd"
            self.shortcut.command = self.command_edit.toPlainText().strip()
        elif type_index == 1:
            self.shortcut.command_type = "powershell"
            self.shortcut.command = self.command_edit.toPlainText().strip()
        elif type_index == 2:
            self.shortcut.command_type = "python"
            self.shortcut.command = self.command_edit.toPlainText().strip()
        elif type_index == 3:
            self.shortcut.command_type = "bash"
            self.shortcut.command = self.command_edit.toPlainText().strip()
        else:
            self.shortcut.command_type = "builtin"
            self.shortcut.command = self.builtin_combo.currentData()

        self.shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        self.shortcut.show_window = self.show_window_cb.isChecked()
        self.shortcut.working_dir = self.workdir_edit.text().strip()
        self.shortcut.run_as_admin = self.run_as_admin_cb.isChecked()
        self.shortcut.command_variables_enabled = self.variable_expansion_cb.isChecked()
        self.shortcut.capture_output = self.capture_output_cb.isChecked()
        self.shortcut.command_timeout_seconds = float(self.capture_timeout_spin.value())
        self.shortcut.command_panel_size = self._selected_command_panel_size()
        self.shortcut.command_params = self._parse_command_params_text()
        self.shortcut.command_env = self._parse_env_text(self.command_env_edit.toPlainText())
        self.shortcut.command_encoding = self.command_encoding_combo.currentData() or "auto"
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.type = ShortcutType.COMMAND
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, "theme", "dark")
        return self.shortcut
