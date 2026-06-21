"""Form UI helpers — extracted from CommandDialog (per §4.7)."""

# pixmap_dpi: allow - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging

from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QCheckBox,
    QColor,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QtCompat,
    QVBoxLayout,
)
from ui.styles.style import PopupMenu
from ui.tooltip_helper import install_tooltip
from ui.utils.safe_file_dialog import get_existing_directory
from ui.utils.ui_scale import scale_qss, sp

from .base_dialog import BaseDialog
from .command_param_dialog import CommandParamDialog
from .command_profile_helpers import (
    format_command_env,
    format_command_params,
    parse_command_env_text,
    parse_command_params_text,
)
from .template_variable_highlighter import install_template_variable_highlighter

logger = logging.getLogger(__name__)


class CommandDialogFormMixin:
    """Form UI helpers — extracted from CommandDialog (per §4.7)."""

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
                painter.setRenderHint(QtCompat.HighQualityAntialiasing)

                # 绘制一个简单的闪电形状（几何图形，不依赖字体）
                from qt_compat import QPoint, QPolygon

                painter.setPen(QtCompat.NoPen)
                _lightning_yellow = QColor()
                _lightning_yellow.setRgb(255, 200, 0)
                painter.setBrush(_lightning_yellow)

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

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(sp(8))
        layout.setContentsMargins(sp(8), sp(8), sp(8), sp(8))  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑运行命令" if self.shortcut.name else "添加运行命令")
        title_label.setStyleSheet(scale_qss("font-size: 12px; font-weight: 400; color: gray;"))
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 1. 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(sp(6))
        basic_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))

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
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), 0, sp(6), sp(6))

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            scale_qss(
                """
            QLabel {
                background-color: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """
            )
        )
        icon_layout.addWidget(self.icon_preview)

        icon_path_layout = QVBoxLayout()
        icon_path_layout.setSpacing(sp(6))

        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_path_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(sp(6))

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

        # 图标反转选项（并排排列）
        self.invert_light_cb = QCheckBox("浅色反转")
        self.invert_dark_cb = QCheckBox("深色反转")
        icon_btn_layout.addWidget(self.invert_light_cb)
        icon_btn_layout.addWidget(self.invert_dark_cb)

        icon_layout.addLayout(icon_path_layout, 1)

        # 3. 命令设置 (移到第三位)
        cmd_group = QGroupBox("命令内容")
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setSpacing(sp(4))  # 减小间距
        cmd_layout.setContentsMargins(sp(8), sp(8), sp(8), sp(8))  # 减小内部边距

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(sp(8))

        self.hint_label = QLabel("输入命令内容:")
        self.hint_label.setStyleSheet(scale_qss("color: gray; font-size: 11px; margin-top: -2px;"))
        top_row.addWidget(self.hint_label, 1)

        self.insert_var_btn = QPushButton("插入")
        self.insert_var_btn.setFixedSize(sp(52), sp(24))
        self.insert_var_btn.clicked.connect(self._show_insert_popup)
        top_row.addWidget(self.insert_var_btn, 0, QtCompat.AlignRight)

        self._test_btn = QPushButton("测试")
        self._test_btn.setFixedSize(sp(52), sp(24))
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
        container_layout.setContentsMargins(sp(4), sp(2), sp(4), sp(4))  # 内部留白，防止文字贴边
        container_layout.setSpacing(0)

        # 内层编辑器：完全透明，只负责显示文字
        self.command_edit = QPlainTextEdit()
        self._command_variable_highlighter = install_template_variable_highlighter(self.command_edit, self.theme)
        self.command_edit.setFixedHeight(sp(92))
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
        self.builtin_combo.setFixedHeight(sp(48))  # 同步高度
        for name, cmd in self._builtin_command_options():
            self.builtin_combo.addItem(name, cmd)
        self.builtin_combo.currentIndexChanged.connect(self._on_builtin_changed)
        self.builtin_combo.showPopup = lambda: self._show_builtin_popup()

        self.input_stack.addWidget(self.builtin_combo)
        self.input_stack.setFixedHeight(sp(100))

        cmd_layout.addWidget(self.input_stack)
        self.test_output = QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setFixedHeight(sp(72))
        self.test_output.setPlaceholderText("运行结果会显示在这里")
        self.test_output.setVisible(False)
        cmd_layout.addWidget(self.test_output)
        cmd_layout.setContentsMargins(sp(8), sp(4), sp(8), sp(8))  # 恢复适度边距，保持比例协调
        layout.addWidget(cmd_group)

        # 4. 高级选项
        advanced_group = QGroupBox("高级选项")
        advanced_layout = QFormLayout(advanced_group)
        advanced_layout.setSpacing(sp(6))
        advanced_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))

        workdir_layout = QHBoxLayout()
        workdir_layout.setSpacing(sp(6))
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText("可选，工作目录")
        workdir_layout.addWidget(self.workdir_edit)
        self._browse_workdir_btn = QPushButton("浏览...")
        self._browse_workdir_btn.clicked.connect(self._browse_workdir)
        workdir_layout.addWidget(self._browse_workdir_btn)
        advanced_layout.addRow(tr("工作目录:"), workdir_layout)

        option_row = QHBoxLayout()
        option_row.setSpacing(sp(8))
        self.advanced_profile_toggle = QPushButton()
        self.advanced_profile_toggle.setObjectName("CommandProfileToggle")
        self.advanced_profile_toggle.setCheckable(True)
        self.advanced_profile_toggle.setChecked(False)
        self.advanced_profile_toggle.setFixedSize(sp(40), sp(12))
        self.advanced_profile_toggle.setToolTip(tr("高级设置"))
        self.advanced_profile_toggle.setCursor(QtCompat.PointingHandCursor)
        self.advanced_profile_toggle.clicked.connect(self._toggle_command_profile_panel)
        self.show_window_cb = QCheckBox("显示执行窗口")
        self.show_window_cb.setFixedHeight(sp(24))
        self.show_window_cb.stateChanged.connect(self._update_capture_controls)
        self.run_as_admin_cb = QCheckBox("以管理员身份运行")
        self.run_as_admin_cb.setFixedHeight(sp(24))
        self.run_as_admin_cb.stateChanged.connect(self._update_capture_controls)
        self.variable_expansion_cb = QCheckBox("解析变量")
        self.variable_expansion_cb.setFixedHeight(sp(24))
        install_tooltip(self.variable_expansion_cb, "替换 {{clipboard}}、{{input}}、{{date}} 等占位符；Python 默认关闭")
        option_row.addWidget(self.show_window_cb)
        option_row.addWidget(self.run_as_admin_cb)
        option_row.addWidget(self.variable_expansion_cb)
        option_row.addStretch()
        advanced_layout.addRow("", option_row)

        capture_row = QHBoxLayout()
        capture_row.setSpacing(sp(8))
        self.capture_output_cb = QCheckBox("捕获输出并显示在命令面板")
        self.capture_output_cb.setFixedHeight(sp(24))
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
            button.setFixedHeight(sp(24))
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
        self.capture_timeout_spin.setFixedSize(sp(72), sp(24))
        capture_row.addWidget(self.capture_timeout_spin)
        capture_row.addStretch()
        capture_toggle_widget = QFrame()
        capture_toggle_widget.setObjectName("CommandProfileToggleCell")
        capture_toggle_cell = QHBoxLayout(capture_toggle_widget)
        capture_toggle_cell.setContentsMargins(0, sp(3), 0, 0)
        capture_toggle_cell.addStretch()
        capture_toggle_cell.addWidget(self.advanced_profile_toggle, 0, QtCompat.AlignVCenter | QtCompat.AlignRight)
        advanced_layout.addRow(capture_toggle_widget, capture_row)

        self.advanced_profile_frame = QFrame()
        self.advanced_profile_frame.setObjectName("CommandProfileFrame")
        self.advanced_profile_frame.setVisible(False)
        profile_layout = QFormLayout(self.advanced_profile_frame)
        profile_layout.setSpacing(sp(6))
        profile_layout.setContentsMargins(0, sp(2), 0, 0)

        self.command_encoding_combo = QComboBox()
        self.command_encoding_combo.setFixedHeight(sp(32))
        self.command_encoding_combo.addItem("自动识别", "auto")
        self.command_encoding_combo.addItem("UTF-8", "utf-8")
        self.command_encoding_combo.addItem("GBK", "gbk")
        self.command_encoding_combo.addItem("系统 ANSI (mbcs)", "mbcs")
        self.command_encoding_combo.showPopup = lambda: self._show_encoding_popup()
        profile_layout.addRow("输出编码:", self.command_encoding_combo)

        self.command_env_edit = QPlainTextEdit()
        self.command_env_edit.setFixedHeight(sp(52))
        self.command_env_edit.setPlaceholderText("每行一个 KEY=VALUE")
        profile_layout.addRow("环境变量:", self.command_env_edit)

        params_layout = QVBoxLayout()
        self.command_params_edit = QPlainTextEdit()
        self.command_params_edit.setFixedHeight(sp(72))
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
        trigger_layout.setSpacing(sp(12))
        trigger_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))

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
        btn_layout.setSpacing(sp(8))
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(sp(80), sp(32))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(sp(80), sp(32))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        self._ok_btn = ok_btn

        layout.addLayout(btn_layout)

        # 自适应大小
        self.adjustSize()
        self.setMinimumWidth(sp(460))

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
            ("选中多文件(逐项引用)", "{{selected_files:q}}"),
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
        menu.setMinimumWidth(sp(180))
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
