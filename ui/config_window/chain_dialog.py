"""动作链编辑对话框 — 左右两栏布局，卡片式步骤，风险分析，测试运行。"""

from __future__ import annotations

import copy
import logging
import os
import uuid

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QCheckBox,
    QColor,
    QFont,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    Qt,
    QtCompat,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Colors, Glassmorphism, PopupMenu

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)

# 类型标签颜色映射
_TYPE_COLORS = {
    ShortcutType.FILE: ("#64B5F6", "FILE"),
    ShortcutType.FOLDER: ("#64B5F6", "DIR"),
    ShortcutType.URL: ("#4DB6AC", "URL"),
    ShortcutType.HOTKEY: ("#7986CB", "KEY"),
    ShortcutType.COMMAND: ("#81C784", "CMD"),
}

# 状态颜色
_STATUS_COLORS = {"ok": "#4CAF50", "failed": "#F44336", "skipped": "#9E9E9E"}


class _ChainTestThread(QThread):
    """后台线程执行动作链测试。"""

    result_ready = pyqtSignal(object)

    def __init__(self, chain: ShortcutItem, data_manager, parent=None):
        super().__init__(parent)
        self.chain = chain
        self.data_manager = data_manager

    def run(self):
        try:
            from core.shortcut_chain_exec import execute_shortcut_chain

            result = execute_shortcut_chain(self.chain, self.data_manager)
            self.result_ready.emit(result)
        except Exception as e:
            logger.exception("动作链测试运行失败")
            from core.command_registry import CommandResult

            self.result_ready.emit(CommandResult(success=False, message=str(e), error=str(e)))


class StepCardWidget(QFrame):
    """步骤卡片 — 内联参数控制：延迟、失败策略、启用状态。"""

    clicked = pyqtSignal(int)
    step_changed = pyqtSignal(int)  # 参数变更通知

    def __init__(self, index: int, step: dict, shortcut_name: str, shortcut_type: ShortcutType, icon: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.step_index = index
        self._selected = False
        self._checkbox_style = ""
        self._type_color = _TYPE_COLORS.get(shortcut_type, ("#999", "??"))[0]
        self._setup_ui(step, shortcut_name, shortcut_type, icon)

    def _setup_ui(self, step: dict, shortcut_name: str, shortcut_type: ShortcutType, icon: QPixmap | None):
        self.setMinimumHeight(40)
        self.setCursor(QtCompat.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)

        # 序号
        num_label = QLabel(f"{self.step_index + 1}")
        num_label.setFixedWidth(18)
        num_label.setAlignment(Qt.AlignCenter)
        num_label.setStyleSheet(
            "color: rgba(128,128,128,180); font-size: 11px; font-weight: 500; "
            "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;"
        )
        layout.addWidget(num_label)

        # 快捷方式图标
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignCenter)
        if icon and not icon.isNull():
            icon_label.setPixmap(icon.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        # 名称
        display_name = shortcut_name or step.get("shortcut_id", "???")
        name_label = QLabel(display_name)
        name_label.setStyleSheet(
            "font-size: 13px; font-weight: 400; "
            "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;"
        )
        layout.addWidget(name_label, 1)

        # ── 内联参数控件 ──

        # 延迟 (QSpinBox，纯输入框，无加减按钮)
        delay_spin = QSpinBox()
        delay_spin.setButtonSymbols(QSpinBox.NoButtons)
        delay_spin.setRange(0, 60000)
        delay_spin.setValue(max(0, int(step.get("delay_ms", 0) or 0)))
        delay_spin.setSuffix("ms")
        delay_spin.setFixedWidth(70)
        delay_spin.setToolTip(tr("执行前延迟"))
        delay_spin.setStyleSheet(
            "QSpinBox { font-size: 11px; font-weight: 400; "
            "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; "
            "padding: 1px 3px; border-radius: 5px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 14px; }"
        )
        delay_spin.valueChanged.connect(self._on_delay_changed)
        layout.addWidget(delay_spin)
        self._delay_spin = delay_spin

        # 失败停止 (QCheckBox)
        stop_cb = QCheckBox(tr("失败停止"))
        stop_cb.setChecked(bool(step.get("stop_on_error", True)))
        stop_cb.setToolTip(tr("该步骤失败时停止后续步骤"))
        stop_cb.stateChanged.connect(self._on_stop_changed)
        layout.addWidget(stop_cb)
        self._stop_cb = stop_cb

        # 启用 (QCheckBox)
        enabled_cb = QCheckBox(tr("启用"))
        enabled_cb.setChecked(bool(step.get("enabled", True)))
        enabled_cb.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(enabled_cb)
        self._enabled_cb = enabled_cb

        self._update_style(selected=False)

    # 控件变更 → 同步到 _steps 并通知对话框
    def _on_delay_changed(self, value):
        self.step_changed.emit(self.step_index)

    def _on_stop_changed(self, _):
        self.step_changed.emit(self.step_index)

    def _on_enabled_changed(self, state):
        # 禁用时名称变灰
        self.step_changed.emit(self.step_index)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style(selected)

    def set_checkbox_style(self, style: str):
        self._checkbox_style = style
        self._stop_cb.setStyleSheet(style)
        self._enabled_cb.setStyleSheet(style)
        self._update_style(self._selected)

    def _update_style(self, selected: bool):
        c = self._type_color
        # 从父级对话框获取 QToolTip 规则，避免子级 setStyleSheet 阻断继承
        parent = self.parent()
        while parent and not isinstance(parent, ChainDialog):
            parent = parent.parent()
        tip_rule = getattr(parent, "_tip_stylesheet", "") if parent else ""
        child_rules = self._checkbox_style + tip_rule
        if selected:
            self.setStyleSheet(
                f"StepCardWidget {{"
                f" background-color: rgba(0, 122, 255, 0.15);"
                f" border-left: 3px solid {c};"
                f" border-top: 1px solid rgba(0, 122, 255, 0.4);"
                f" border-right: 1px solid rgba(0, 122, 255, 0.4);"
                f" border-bottom: 1px solid rgba(0, 122, 255, 0.4);"
                f" border-radius: 8px;"
                f"}}"
                + child_rules
            )
        else:
            self.setStyleSheet(
                f"StepCardWidget {{"
                f" background-color: rgba(128, 128, 128, 0.08);"
                f" border-left: 3px solid {c};"
                f" border-top: 1px solid rgba(128, 128, 128, 0.12);"
                f" border-right: 1px solid rgba(128, 128, 128, 0.12);"
                f" border-bottom: 1px solid rgba(128, 128, 128, 0.12);"
                f" border-radius: 8px;"
                f"}}"
                f"StepCardWidget:hover {{"
                f" background-color: rgba(128, 128, 128, 0.15);"
                f"}}"
                + child_rules
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.step_index)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        # 右键菜单由 ChainDialog 统一处理
        parent = self.parent()
        while parent and not isinstance(parent, ChainDialog):
            parent = parent.parent()
        if parent:
            parent._show_step_context_menu(self.step_index, event.globalPos())


class ChainDialog(BaseDialog):
    """动作链编辑对话框 — 左右两栏布局。"""

    def __init__(self, parent=None, shortcut: ShortcutItem | None = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.CHAIN, name=tr("动作链"))
        self._steps = copy.deepcopy(list(getattr(self.shortcut, "chain_steps", []) or []))
        self._available = self._collect_available_shortcuts()
        self._selected_index = -1
        self._test_thread = None
        self._last_test_result = None
        self._closing_with_animation = False
        self._pending_done_result = None
        self._close_anim_timer = None

        self.setWindowTitle(tr("编辑动作链") if shortcut else tr("新建动作链"))
        self.setMinimumSize(760, 620)

        self._setup_ui()
        self._apply_theme()
        self._load_data()
        self._refresh_risk_analysis()

    def done(self, result):
        if getattr(self, "_closing_with_animation", False):
            return
        if not self.isVisible() or getattr(self, "_dialog_finished", False):
            super().done(result)
            return

        self._closing_with_animation = True
        self._pending_done_result = result

        anim_timer = getattr(self, "_anim_timer", None)
        if anim_timer is not None:
            try:
                anim_timer.stop()
            except Exception:
                pass

        self._close_anim_origin_pos = self.pos()
        self._close_anim_step = 0
        self._close_anim_duration_ms = 170
        self._close_anim_interval_ms = 16
        self._close_anim_total_steps = max(1, self._close_anim_duration_ms // self._close_anim_interval_ms)

        self._close_anim_timer = QTimer(self)
        self._close_anim_timer.setInterval(self._close_anim_interval_ms)
        self._close_anim_timer.timeout.connect(self._on_close_animation_tick)
        self._close_anim_timer.start()

    def _on_close_animation_tick(self):
        self._close_anim_step += 1
        progress = self._close_anim_step / self._close_anim_total_steps
        if progress >= 1.0:
            progress = 1.0

        eased = progress * progress
        self.setWindowOpacity(max(0.0, 1.0 - progress * 1.25))
        origin = self._close_anim_origin_pos
        self.move(origin.x(), origin.y() + int(eased * 16))

        if progress >= 1.0:
            timer = getattr(self, "_close_anim_timer", None)
            if timer is not None:
                timer.stop()
            self._closing_with_animation = False
            super().done(self._pending_done_result)

    # ── UI 构建 ──────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(8, 8, 8, 8)

        # 顶部标题
        title_label = QLabel(tr("编辑动作链") if self.shortcut.name else tr("新建动作链"))
        title_label.setStyleSheet(
            "font-size: 12px; font-weight: 400; color: gray; "
            "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;"
        )
        root.addWidget(title_label)

        # 左右分栏
        body = QHBoxLayout()
        body.setSpacing(8)
        body.addLayout(self._build_left_panel(), 3)
        body.addLayout(self._build_right_panel(), 2)
        root.addLayout(body, 1)

        # 底部按钮行 — 与 body 同比例 (3:2)，5 按钮总宽 = 左栏宽
        from qt_compat import QSizePolicy

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # 左侧：5 个类型快捷添加按钮 + 测试运行，stretch 3
        ops_layout = QHBoxLayout()
        ops_layout.setSpacing(4)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        self.file_btn = QPushButton(tr("快捷应用"))
        self.file_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.FILE))
        self.cmd_btn = QPushButton(tr("代码命令"))
        self.cmd_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.COMMAND))
        self.hotkey_btn = QPushButton(tr("快捷键"))
        self.hotkey_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.HOTKEY))
        self.url_btn = QPushButton(tr("打开网站"))
        self.url_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.URL))
        self.test_btn = QPushButton(tr("测试运行"))
        self.test_btn.clicked.connect(self._run_test)
        for b in (self.file_btn, self.cmd_btn, self.hotkey_btn, self.url_btn, self.test_btn):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            ops_layout.addWidget(b, 1)
        btn_row.addLayout(ops_layout, 3)

        # 右侧：取消/保存，stretch 2
        right_btn_layout = QHBoxLayout()
        right_btn_layout.setContentsMargins(0, 0, 0, 0)
        right_btn_layout.addStretch()
        self._cancel_btn = QPushButton(tr("取消"))
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn = QPushButton(tr("保存"))
        self._save_btn.clicked.connect(self.accept)
        right_btn_layout.addWidget(self._cancel_btn)
        right_btn_layout.addWidget(self._save_btn)
        btn_row.addLayout(right_btn_layout, 2)

        root.addLayout(btn_row)

    def _build_left_panel(self) -> QVBoxLayout:
        left = QVBoxLayout()
        left.setSpacing(4)

        # 基本设置
        basic = QGroupBox(tr("基本设置"))
        form = QVBoxLayout(basic)
        form.setSpacing(4)
        form.setContentsMargins(8, 4, 8, 6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("名称:")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("动作链名称"))
        name_row.addWidget(self.name_edit, 1)
        form.addLayout(name_row)

        result_row = QHBoxLayout()
        result_row.addWidget(QLabel(tr("结果显示:")))
        self._result_checks: dict[str, QCheckBox] = {}
        for key in ("none", "small", "medium", "large"):
            label_map = {"none": tr("无"), "small": tr("小"), "medium": tr("中"), "large": tr("大")}
            cb = QCheckBox(label_map[key])
            cb.setStyleSheet("QCheckBox { font-size: 12px; spacing: 3px; }")
            cb.toggled.connect(lambda checked, k=key: self._on_result_check(k, checked))
            result_row.addWidget(cb)
            self._result_checks[key] = cb
        self._result_checks["medium"].setChecked(True)  # 默认 medium
        result_row.addStretch()
        form.addLayout(result_row)

        left.addWidget(basic)

        # 图标设置
        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        icon_group = QGroupBox(tr("图标"))
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 0, 6, 6)

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            "QLabel { background-color: rgba(255, 255, 255, 0.1); "
            "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; }"
        )
        icon_layout.addWidget(self.icon_preview)

        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(6)

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText(tr("留空则使用默认图标"))
        self.icon_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(8)

        browse_icon_btn = QPushButton(tr("选择图标..."))
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton(tr("清除"))
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(clear_icon_btn)
        self._clear_icon_btn = clear_icon_btn

        icon_btn_layout.addStretch()

        # 图标反转选项
        invert_v_layout = QVBoxLayout()
        invert_v_layout.setSpacing(2)
        invert_v_layout.setContentsMargins(0, 0, 0, 0)
        self.invert_theme_cb = QCheckBox(tr("随主题反转"))
        self.invert_current_cb = QCheckBox(tr("当前反转"))
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        invert_v_layout.addWidget(self.invert_theme_cb)
        invert_v_layout.addWidget(self.invert_current_cb)
        icon_btn_layout.addLayout(invert_v_layout)

        icon_right_layout.addLayout(icon_btn_layout)
        icon_layout.addLayout(icon_right_layout, 1)

        left.addWidget(icon_group)

        # 步骤列表
        steps_group = QGroupBox(tr("步骤列表"))
        steps_layout = QVBoxLayout(steps_group)
        steps_layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(4, 4, 4, 4)
        self._cards_layout.setSpacing(4)
        self._cards_layout.addStretch()
        scroll.setWidget(self._cards_container)
        steps_layout.addWidget(scroll)
        self._scroll_area = scroll

        left.addWidget(steps_group, 1)

        return left

    def _build_right_panel(self) -> QVBoxLayout:
        right = QVBoxLayout()
        right.setSpacing(4)

        # 用 QGroupBox 与左侧"基本设置"对齐
        result_group = QGroupBox(tr("执行结果"))
        result_layout = QVBoxLayout(result_group)
        result_layout.setContentsMargins(6, 4, 6, 6)

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setFrameShape(QFrame.NoFrame)
        result_layout.addWidget(self.result_view)

        right.addWidget(result_group)
        return right

    # ── 主题 ────────────────────────────────────────────────

    def _apply_theme(self):
        self._apply_theme_colors()
        theme = self.theme

        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"
        input_bg = "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(255, 255, 255, 0.8)"
        tip_bg = "rgba(44, 44, 48, 240)" if theme == "dark" else "rgba(255, 255, 255, 240)"
        tip_fg = "#ffffff" if theme == "dark" else "#1c1c1e"
        tip_border = "rgba(255, 255, 255, 0.15)" if theme == "dark" else "rgba(0, 0, 0, 0.1)"
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)

        custom = (
            base_style
            + f"""
            QDialog {{ background: transparent; border: none; }}
            QLabel, QCheckBox, QGroupBox, QLineEdit, QSpinBox, QPushButton {{
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-weight: 400;
            }}
            QToolTip {{
                background: {tip_bg};
                color: {tip_fg};
                border: 1px solid {tip_border};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 400;
            }}
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
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 10px;
                color: {text_primary};
                font-size: 13px;
                padding: 4px 8px;
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QSpinBox {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_primary};
                font-size: 12px;
                padding: 2px 4px;
            }}
        """
        )
        self._tip_stylesheet = f"QToolTip {{ background: {tip_bg}; color: {tip_fg}; border: 1px solid {tip_border}; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 400; }}"
        self.setStyleSheet(custom)

        # 按钮复用扁平操作按钮样式
        refined_button_font = """
            QPushButton {
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 400;
                min-height: 22px;
            }
        """
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme) + refined_button_font
        for btn in (self.file_btn, self.cmd_btn, self.hotkey_btn, self.url_btn,
                     self.test_btn, self._browse_icon_btn, self._clear_icon_btn,
                     self._cancel_btn, self._save_btn):
            btn.setStyleSheet(flat_btn_style)
        # 测试按钮用强调色
        # 所有复选框统一使用 get_small_checkbox_stylesheet
        cb_style = get_small_checkbox_stylesheet(theme)
        for cb in self._result_checks.values():
            cb.setStyleSheet(cb_style)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)

        # result_view 透明背景，文字直接显示在分栏框里
        self.result_view.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; border: none; "
            f"color: {text_primary}; font-size: 12px; padding: 8px; "
            f"font-family: 'Cascadia Code', 'Consolas', monospace; }}"
        )
        # viewport 必须用 palette 强制上色，否则 BaseDialog 透明背景会让点击时闪白
        from PyQt5.QtGui import QPalette
        vp = self.result_view.viewport()
        pal = self.result_view.palette()
        bg_color = QColor(28, 28, 30) if theme == "dark" else QColor(242, 242, 247)
        bg_color.setAlpha(120)
        pal.setColor(QPalette.Base, bg_color)
        self.result_view.setPalette(pal)
        vp.setAutoFillBackground(True)

    # ── 数据加载 ─────────────────────────────────────────────

    def _on_result_check(self, key: str, checked: bool):
        """互斥复选：选中一个时取消其他。"""
        if not checked:
            # 防止全部取消，至少保留一个
            if not any(cb.isChecked() for cb in self._result_checks.values()):
                self._result_checks[key].setChecked(True)
            return
        for k, cb in self._result_checks.items():
            if k != key:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _get_result_window_value(self) -> str:
        for key, cb in self._result_checks.items():
            if cb.isChecked():
                return key
        return "medium"

    def _load_data(self):
        self.name_edit.setText(self.shortcut.name or tr("动作链"))
        crw = getattr(self.shortcut, "chain_result_window", "medium")
        if crw in self._result_checks:
            self._result_checks[crw].setChecked(True)
        # 图标
        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        if self._custom_icon_path:
            self.icon_edit.setText(self._custom_icon_path)
        self.invert_theme_cb.setChecked(getattr(self.shortcut, "icon_invert_with_theme", False))
        self.invert_current_cb.setChecked(getattr(self.shortcut, "icon_invert_current", False))
        self.invert_current_cb.setEnabled(self.invert_theme_cb.isChecked())
        self._update_icon_preview()
        self._refresh_cards()

    # ── 图标操作 ─────────────────────────────────────────────

    def _browse_icon(self):
        file_path = choose_custom_icon(self, tr("选择图标"))
        if file_path:
            self._custom_icon_path = file_path
            self.icon_edit.setText(file_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()

    def _clear_icon(self):
        self._custom_icon_path = ""
        self.icon_edit.clear()
        self.invert_theme_cb.setChecked(False)
        self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_invert_theme_changed(self, state):
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _update_icon_preview(self):
        pixmap = None
        if self._custom_icon_path:
            try:
                from core.icon_extractor import IconExtractor

                if "," in self._custom_icon_path or os.path.exists(self._custom_icon_path):
                    pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
            except Exception:
                pass
        if not pixmap or pixmap.isNull():
            pixmap = self._create_chain_icon(48)
        if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.invert_pixmap(pixmap)
            except Exception:
                pass
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.icon_preview.setPixmap(pixmap)

    def _create_chain_icon(self, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setBrush(QColor(180, 100, 50))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⛓")  # ⚓ chain symbol
        painter.end()
        return pixmap

    def _collect_available_shortcuts(self) -> list[ShortcutItem]:
        parent = self.parent()
        data_manager = getattr(parent, "data_manager", None)
        data = getattr(data_manager, "data", None)
        result = []
        for folder in list(getattr(data, "folders", []) or []):
            for item in list(getattr(folder, "items", []) or []):
                if item.id == self.shortcut.id or item.type == ShortcutType.CHAIN:
                    continue
                result.append(item)
        return result

    def _shortcut_map(self) -> dict[str, ShortcutItem]:
        return {item.id: item for item in self._available}

    # ── 图标加载 ─────────────────────────────────────────────

    def _load_step_icon(self, shortcut: ShortcutItem | None) -> QPixmap | None:
        """加载快捷方式的图标，返回 QPixmap；无图标返回 None。"""
        if shortcut is None:
            return None
        icon_path = getattr(shortcut, "icon_path", "") or ""
        target_path = getattr(shortcut, "target_path", "") or ""
        try:
            import os
            import sys

            from core.icon_extractor import IconExtractor

            source_size = 64
            if icon_path:
                if "," in icon_path or os.path.exists(icon_path):
                    pm = IconExtractor.from_file(icon_path, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm
            if target_path:
                if os.path.exists(target_path):
                    pm = IconExtractor.extract(target_path, target_path, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm
            # 文件夹类型默认图标
            if shortcut.type == ShortcutType.FOLDER:
                folder_ico = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico")
                if os.path.exists(folder_ico):
                    pm = IconExtractor.from_file(folder_ico, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm
        except Exception:
            pass
        return None

    # ── 卡片刷新 ─────────────────────────────────────────────

    def _refresh_cards(self):
        # 清除旧卡片（保留 stretch）
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        smap = self._shortcut_map()
        cb_style = next((cb.styleSheet() for cb in self._result_checks.values() if cb.styleSheet()), "")
        for i, step in enumerate(self._steps):
            sid = step.get("shortcut_id", "")
            target = smap.get(sid)
            name = getattr(target, "name", sid) if target else sid
            stype = getattr(target, "type", ShortcutType.FILE) if target else ShortcutType.FILE
            icon = self._load_step_icon(target)
            card = StepCardWidget(i, step, name, stype, icon, parent=self._cards_container)
            card.clicked.connect(self._on_card_clicked)
            card.step_changed.connect(self._on_step_changed)
            # 应用复选框样式（与其他复选框一致）
            card.set_checkbox_style(cb_style)
            # 插入到 stretch 之前
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        # 选中状态
        self._update_selection()

    def _on_step_changed(self, index: int):
        """卡片内联控件变更 → 同步到 _steps 数据。"""
        if not (0 <= index < len(self._steps)):
            return
        # 找到对应卡片
        card = self._find_card(index)
        if card is None:
            return
        self._steps[index]["delay_ms"] = card._delay_spin.value()
        self._steps[index]["stop_on_error"] = card._stop_cb.isChecked()
        self._steps[index]["enabled"] = card._enabled_cb.isChecked()
        self._refresh_risk_analysis()

    def _find_card(self, index: int) -> StepCardWidget | None:
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, StepCardWidget) and w.step_index == index:
                return w
        return None

    def _update_selection(self):
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, StepCardWidget):
                w.set_selected(w.step_index == self._selected_index)

    def _on_card_clicked(self, index: int):
        self._selected_index = index
        self._update_selection()

    # ── 步骤操作 ─────────────────────────────────────────────

    def _show_type_menu(self, stype: ShortcutType):
        """显示指定类型的快捷方式菜单。"""
        filtered = [it for it in self._available if it.type == stype]
        if not filtered:
            return
        menu = PopupMenu(self)
        for item in filtered:
            menu.add_action(item.name or item.id, lambda it=item: self._add_step(it))
        # 定位到对应按钮下方
        btn_map = {
            ShortcutType.FILE: self.file_btn,
            ShortcutType.COMMAND: self.cmd_btn,
            ShortcutType.HOTKEY: self.hotkey_btn,
            ShortcutType.URL: self.url_btn,
        }
        btn = btn_map.get(stype, self.file_btn)
        menu.popup(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _add_step(self, target: ShortcutItem):
        self._steps.append(
            {
                "id": str(uuid.uuid4()),
                "shortcut_id": target.id,
                "enabled": True,
                "stop_on_error": True,
                "delay_ms": 0,
            }
        )
        self._selected_index = len(self._steps) - 1
        self._refresh_cards()
        self._refresh_risk_analysis()

    def _remove_step(self):
        if 0 <= self._selected_index < len(self._steps):
            del self._steps[self._selected_index]
            self._selected_index = min(self._selected_index, len(self._steps) - 1)
            self._refresh_cards()
            self._refresh_risk_analysis()

    def _move_step(self, delta: int):
        new_idx = self._selected_index + delta
        if not (0 <= self._selected_index < len(self._steps) and 0 <= new_idx < len(self._steps)):
            return
        self._steps[self._selected_index], self._steps[new_idx] = (
            self._steps[new_idx],
            self._steps[self._selected_index],
        )
        self._selected_index = new_idx
        self._refresh_cards()

    def _show_step_context_menu(self, index: int, global_pos):
        if not (0 <= index < len(self._steps)):
            return
        step = self._steps[index]
        menu = PopupMenu(self)
        enabled = step.get("enabled", True)
        menu.add_action(tr("禁用") if enabled else tr("启用"), lambda: self._toggle_step_enabled(index))
        menu.add_separator()
        menu.add_action(tr("上移"), lambda: self._move_step_at(index, -1), enabled=index > 0)
        menu.add_action(tr("下移"), lambda: self._move_step_at(index, 1), enabled=index < len(self._steps) - 1)
        menu.add_separator()
        menu.add_action(tr("删除"), lambda: self._delete_step_at(index))
        menu.popup(global_pos)

    def _toggle_step_enabled(self, index: int):
        if 0 <= index < len(self._steps):
            self._steps[index]["enabled"] = not self._steps[index].get("enabled", True)
            self._refresh_cards()

    def _move_step_at(self, index: int, delta: int):
        self._selected_index = index
        self._move_step(delta)

    def _delete_step_at(self, index: int):
        self._selected_index = index
        self._remove_step()

    # ── 风险分析 ─────────────────────────────────────────────

    def _refresh_risk_analysis(self):
        risks = self._analyze_risks()
        if risks:
            lines = [tr("⚠ 风险分析"), ""]
            lines.extend(risks)
            lines.append("")
            lines.append(tr("共 {n} 个步骤", n=len(self._steps)))
        elif self._steps:
            lines = [tr("✓ 未发现明显风险"), "", tr("共 {n} 个步骤", n=len(self._steps))]
        else:
            lines = [tr("暂无步骤。"), "", tr("点击「添加」将已有快捷方式加入动作链。")]
        self.result_view.setPlainText("\n".join(lines))

    def _analyze_risks(self) -> list[str]:
        smap = self._shortcut_map()
        risks = []
        for i, step in enumerate(self._steps):
            sid = step.get("shortcut_id", "")
            target = smap.get(sid)
            num = i + 1
            if target is None:
                risks.append(tr("  步骤 {n}: 引用的快捷方式不存在", n=num))
                continue
            if getattr(target, "run_as_admin", False):
                risks.append(tr("  步骤 {n}: 将以管理员权限运行", n=num))
            if target.type == ShortcutType.HOTKEY:
                risks.append(tr("  步骤 {n}: 快捷键操作，可能产生冲突", n=num))
            if target.type == ShortcutType.COMMAND:
                risks.append(tr("  步骤 {n}: 将执行命令", n=num))
        return risks

    # ── 测试运行 ─────────────────────────────────────────────

    def _run_test(self):
        chain = self.get_shortcut()
        parent = self.parent()
        data_manager = getattr(parent, "data_manager", None)
        if data_manager is None:
            self.result_view.setPlainText(tr("错误: 无法获取数据管理器"))
            return
        self.test_btn.setEnabled(False)
        self.result_view.setPlainText(tr("正在执行..."))
        self._test_thread = _ChainTestThread(chain, data_manager, self)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, result):
        self.test_btn.setEnabled(True)
        self._last_test_result = result
        lines = []
        success = getattr(result, "success", False)
        lines.append(("✓ " if success else "✗ ") + (getattr(result, "message", "") or ""))
        lines.append("")
        payload = getattr(result, "payload", None) or {}
        items = payload.get("items", [])
        for item in items:
            status = item.get("status", "")
            icon = {"ok": "✓", "failed": "✗", "skipped": "○"}.get(status, "?")
            title = item.get("title", "")
            detail = item.get("detail", "")
            dur = item.get("duration", 0.0)
            line = f"  {icon} {title}"
            if dur > 0:
                line += f"  ({dur:.2f}s)"
            lines.append(line)
            if detail and status == "failed":
                for dl in str(detail).splitlines():
                    lines.append(f"      {dl}")
        duration = payload.get("duration", 0.0)
        if duration > 0:
            lines.append("")
            lines.append(tr("总耗时: {t:.2f}s", t=duration))
        error = getattr(result, "error", "")
        if error:
            lines.append(tr("错误: {e}", e=error))
        self.result_view.setPlainText("\n".join(lines))

    # ── get_shortcut 契约 ────────────────────────────────────

    def get_shortcut(self) -> ShortcutItem:
        shortcut = copy.deepcopy(self.shortcut)
        shortcut.type = ShortcutType.CHAIN
        shortcut.name = self.name_edit.text().strip() or tr("动作链")
        shortcut.chain_steps = ShortcutItem._normalize_chain_steps(copy.deepcopy(self._steps))
        shortcut.chain_result_window = self._get_result_window_value()
        shortcut.icon_path = self._custom_icon_path
        shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            shortcut.icon_invert_theme_when_set = getattr(self, "theme", "dark")
        return shortcut
