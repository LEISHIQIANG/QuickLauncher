"""
命令编辑对话框
"""

import os
import sys
import logging
import tempfile

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QLineEdit, QPushButton, QLabel, QGroupBox, QFileDialog, QCheckBox,
    QPlainTextEdit, QPixmap, QPainter, QColor, QFont,
    QComboBox, QSpinBox, QStackedWidget, QIcon,
    Qt, QtCompat, PYQT_VERSION, QRadioButton, QButtonGroup,
    QPainterPath, QPen, QTimer, QRectF, QListView, QPoint,
    exec_dialog
)

from ui.utils.window_effect import get_window_effect, is_win11, enable_acrylic_for_config_window

from core import ShortcutItem, ShortcutType
from .theme_helper import log_error, get_temp_icon_dir, get_radio_stylesheet, get_checkbox_stylesheet, get_small_checkbox_stylesheet
from .icon_picker_dialog import IconPickerDialog
from ui.styles.style import get_dialog_stylesheet, Glassmorphism, PopupMenu
from ui.utils.window_effect import enable_window_shadow_and_round_corners
from ui.utils.dialog_helper import center_dialog_on_main_window
from .base_dialog import BaseDialog





class CommandDialog(BaseDialog):
    """命令编辑对话框"""

    BUILTIN_COMMANDS = [
        ("置顶/取消置顶 (Toggle Topmost)", "toggle_topmost"),
        ("开启置顶 (Pin Window)", "pin_on"),
        ("关闭置顶 (Unpin Window)", "pin_off"),
        ("配置窗口 (Config Window)", "show_config_window"),
        ("打开控制面板 (Control Panel)", "open_control_panel"),
        ("打开此电脑 (This PC)", "open_this_pc"),
        ("打开回收站 (Recycle Bin)", "open_recycle_bin"),
    ]

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        super().__init__(parent)
        if shortcut:
            self.shortcut = shortcut
        else:
            self.shortcut = ShortcutItem(type=ShortcutType.COMMAND)

        self._custom_icon_path = self.shortcut.icon_path or ""

        # 确保有默认值
        if not hasattr(self.shortcut, 'command_type'):
            self.shortcut.command_type = 'cmd'

        self.setWindowTitle("编辑运行命令" if shortcut else "添加运行命令")
        self.setMinimumWidth(480)
        
        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        """设置窗口图标"""
        try:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)
            
            painter = QPainter(pixmap)
            try:
                if not painter.isActive():
                    return
                painter.setRenderHint(QtCompat.Antialiasing)
                
                # 绘制闪电
                font = QFont("Segoe UI Emoji", 40)
                font.setStyleHint(QFont.StyleHint.SansSerif)
                painter.setFont(font)
                
                # 使用金黄色以匹配"闪电"的直观感觉
                painter.setPen(QColor(255, 200, 0))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⚡")
            finally:
                painter.end()
            
            self.setWindowIcon(QIcon(pixmap))
        except Exception as e:
            # 即使设置图标失败也不要崩溃
            pass

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"

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
            selection-background-color: #007aff;
        """

        self.name_edit.setStyleSheet(f"QLineEdit {{ {input_style} padding: 4px 8px; }}")
        self.icon_path_edit.setStyleSheet(f"QLineEdit {{ {input_style} padding: 4px 8px; }}")

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
                selection-background-color: #007aff;
            }}
        """
        self.command_edit.setStyleSheet(editor_style)
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
        self.type_combo.setStyleSheet(combo_qss)
        self.builtin_combo.setStyleSheet(combo_qss)

        # 应用单选按钮样式
        try:
                from .theme_helper import get_radio_stylesheet
                radio_style = get_radio_stylesheet(theme)
                self.trigger_immediate_rb.setStyleSheet(radio_style)
                self.trigger_after_close_rb.setStyleSheet(radio_style)
        except Exception:
                pass
        self.setStyleSheet(custom_style)

        # 按钮使用扁平操作按钮样式（与主配置窗口底部四按钮一致）
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [self._browse_icon_btn, self._clear_icon_btn,
                         self._cancel_btn, self._ok_btn]:
                btn.setStyleSheet(flat_btn_style)

        # 应用复选框样式
        cb_style = get_small_checkbox_stylesheet(theme)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)
        self.show_window_cb.setStyleSheet(cb_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)  # 特殊页边距：复杂编辑窗口保持 10px
        
        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑运行命令" if self.shortcut.name else "添加运行命令")
        title_label.setStyleSheet("font-size: 14px; font-weight: 400; color: gray;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # 1. 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(16)
        basic_layout.setContentsMargins(12, 0, 12, 12)
        
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow("名称:", self.name_edit)
        
        # 类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(["CMD 命令", "Python 代码", "内置命令"])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.type_combo.showPopup = lambda: self._show_type_popup()

        basic_layout.addRow("类型:", self.type_combo)
        
        layout.addWidget(basic_group)

        # 2. 图标设置 (移到第二位)
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(10)
        icon_layout.setContentsMargins(12, 0, 12, 12)
        
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(40, 40) # 稍微减小图标预览大小，原为48
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
        icon_path_layout.setSpacing(8)
        
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_path_layout.addWidget(self.icon_path_edit)
        
        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(4) # 减小间距
        
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
        self.invert_theme_cb.setStyleSheet("""
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """)
        self.invert_current_cb = QCheckBox("当前反转")
        self.invert_current_cb.setStyleSheet("""
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """)
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        invert_v_layout.addWidget(self.invert_theme_cb)
        invert_v_layout.addWidget(self.invert_current_cb)
        icon_btn_layout.addLayout(invert_v_layout)

        icon_layout.addLayout(icon_path_layout, 1)
        layout.addWidget(icon_group)
        
        # 3. 命令设置 (移到第三位)
        cmd_group = QGroupBox("命令内容")
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setSpacing(4) # 减小间距
        cmd_layout.setContentsMargins(8, 8, 8, 8) # 减小内部边距
        
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.hint_label = QLabel("输入命令内容:")
        self.hint_label.setStyleSheet("color: gray; font-size: 11px; margin-top: -2px;")
        top_row.addWidget(self.hint_label)
        top_row.addStretch()

        self.show_window_cb = QCheckBox("显示执行窗口")
        top_row.addWidget(self.show_window_cb)

        cmd_layout.addLayout(top_row)

        # 使用 StackedWidget 切换不同类型的输入
        self.input_stack = QStackedWidget()
        
        # 1. 文本编辑器 (CMD/Python) - 重构为容器模式
        # 外层容器：负责背景、边框、圆角
        from qt_compat import QFrame
        self.command_container = QFrame()
        self.command_container.setObjectName("CommandContainer")
        container_layout = QVBoxLayout(self.command_container)
        container_layout.setContentsMargins(4, 2, 4, 4) # 内部留白，防止文字贴边
        container_layout.setSpacing(0)
        
        # 内层编辑器：完全透明，只负责显示文字
        self.command_edit = QPlainTextEdit()
        self.command_edit.setFixedHeight(40) # 略微减小编辑器高度，留给容器内边距
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
        self.builtin_combo.setFixedHeight(48) # 同步高度
        for name, cmd in self.BUILTIN_COMMANDS:
            self.builtin_combo.addItem(name, cmd)
        self.builtin_combo.currentIndexChanged.connect(self._on_builtin_changed)
        self.builtin_combo.showPopup = lambda: self._show_builtin_popup()
        
        self.input_stack.addWidget(self.builtin_combo)
        self.input_stack.setFixedHeight(48) # 锁定两行高度
        
        cmd_layout.addWidget(self.input_stack)
        cmd_layout.setContentsMargins(8, 4, 8, 8) # 恢复适度边距，保持比例协调
        layout.addWidget(cmd_group)

        # 4. 触发模式 (移到第四位)
        trigger_group = QGroupBox("触发模式")
        trigger_layout = QVBoxLayout(trigger_group)
        trigger_layout.setSpacing(8)
        
        self.trigger_immediate_rb = QRadioButton("立即触发 (全局快捷键)")
        install_tooltip(self.trigger_immediate_rb, "点击后立即执行，适合不依赖特定窗口焦点的操作")

        self.trigger_after_close_rb = QRadioButton("窗口关闭后触发 (聚焦指定窗口)")
        install_tooltip(self.trigger_after_close_rb, "等待快捷启动窗口完全关闭后执行，适合需要操作当前活动窗口的快捷键")
        
        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        
        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)
        
        layout.addWidget(trigger_group)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
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
        self.setMinimumWidth(480)

    def _on_type_changed(self, index):
        """类型改变"""
        if index == 0:  # CMD
            self.hint_label.setText("输入要执行的CMD命令（静默运行，不显示窗口）:")
            self.command_edit.setPlaceholderText("例如: shutdown /s /t 0")
            self.input_stack.setCurrentIndex(0)
        elif index == 1:  # Python
            self.hint_label.setText("输入要执行的Python代码（提供 os, sys, subprocess 等上下文）:")
            self.command_edit.setPlaceholderText("例如: os.system('notepad')")
            self.input_stack.setCurrentIndex(0)
        elif index == 2:  # Built-in
            self.hint_label.setText("选择内置命令:")
            self.input_stack.setCurrentIndex(1)
            # 触发一次内置命令变更，以更新图标
            self._on_builtin_changed(self.builtin_combo.currentIndex())
            
        # 更新图标
        self._update_icon_preview()

    def _on_builtin_changed(self, index):
        """内置命令改变"""
        self.invert_current_cb.setChecked(False)
        command = self.builtin_combo.itemData(index)
        if not command:
            return

        import os
        system32 = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32')

        # 自动设置图标
        icon_path = ""
        if command == "open_control_panel":
            icon_path = os.path.join(system32, "control.exe")
        elif command == "open_this_pc":
            # 使用资源 ID (-109) 而不是索引
            icon_path = os.path.join(system32, "imageres.dll,-109")
        elif command == "open_recycle_bin":
            # 使用资源 ID (-55) (Recycle Bin Empty)
            icon_path = os.path.join(system32, "imageres.dll,-55")
        elif command == "show_config_window":
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            icon_path = os.path.join(base_dir, "assets", "setting.ico")
        elif "topmost" in command or "pin" in command:
            # 尝试给置顶命令也加个图标 (imageres.dll, -229 is a pin icon in Win10/11 usually)
            pass

        if icon_path:
            self._custom_icon_path = icon_path
            self.icon_path_edit.setText(icon_path)
            self._update_icon_preview()

    def _show_type_popup(self):
        """显示类型选择弹出菜单"""
        menu = PopupMenu(theme=self.theme, radius=12, parent=None)
        items = ["CMD 命令", "Python 代码", "内置命令"]
        current = self.type_combo.currentText()
        for i, item_text in enumerate(items):
            def _make_cb(idx):
                def cb():
                    self.type_combo.setCurrentIndex(idx)
                return cb
            btn = menu.add_action(item_text, _make_cb(i))
            if item_text == current:
                sel_bg = "#0A84FF" if self.theme == "dark" else "#007AFF"
                btn.setStyleSheet(btn.styleSheet() + f"QPushButton{{ background:{sel_bg}; color:#ffffff; }}")
        pos = self.type_combo.mapToGlobal(self.type_combo.rect().bottomLeft())
        menu.setMinimumWidth(self.type_combo.width())
        menu.popup(pos)

    def _show_builtin_popup(self):
        """显示内置命令选择弹出菜单"""
        menu = PopupMenu(theme=self.theme, radius=12, parent=None)
        current = self.builtin_combo.currentText()
        for i in range(self.builtin_combo.count()):
            item_text = self.builtin_combo.itemText(i)
            def _make_cb(idx):
                def cb():
                    self.builtin_combo.setCurrentIndex(idx)
                return cb
            btn = menu.add_action(item_text, _make_cb(i))
            if item_text == current:
                sel_bg = "rgba(80, 110, 150, 180)" if self.theme == "dark" else "rgba(180, 210, 240, 180)"
                btn.setStyleSheet(btn.styleSheet() + f"QPushButton{{ background:{sel_bg}; color:#ffffff; }}")
        pos = self.builtin_combo.mapToGlobal(self.builtin_combo.rect().bottomLeft())
        menu.setMinimumWidth(self.builtin_combo.width())
        menu.popup(pos)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            # 限制拖动区域：只有点击顶部 50px 区域（标题栏）才能拖动
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if pos.y() <= 50:
                self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                event.accept()
            else:
                self._drag_pos = None

    def mouseMoveEvent(self, event):
        if getattr(self, '_drag_pos', None) is not None and event.buttons() & QtCompat.LeftButton:
            new_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(self.pos() + (new_pos - self._drag_pos))
            self._drag_pos = new_pos
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _load_data(self):
        """加载数据"""
        try:
            self.name_edit.setText(self.shortcut.name or "")
            
            # 暂时阻塞信号，避免初始化时频繁触发
            self.type_combo.blockSignals(True)
            
            # 加载命令类型
            cmd_type = getattr(self.shortcut, 'command_type', 'cmd')
            if cmd_type == 'python':
                self.type_combo.setCurrentIndex(1)
            elif cmd_type == 'builtin':
                self.type_combo.setCurrentIndex(2)
            else:
                self.type_combo.setCurrentIndex(0)
            
            self.type_combo.blockSignals(False)
            
            # 加载触发模式
            if getattr(self.shortcut, 'trigger_mode', 'immediate') == 'after_close':
                self.trigger_after_close_rb.setChecked(True)
            else:
                self.trigger_immediate_rb.setChecked(True)
        
            # 加载命令内容
            command = self.shortcut.command or ""
            if cmd_type == 'builtin':
                # 尝试在下拉框中选中对应命令
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
            self.show_window_cb.setChecked(getattr(self.shortcut, 'show_window', False))

            # 手动调用一次以初始化界面状态
            self._on_type_changed(self.type_combo.currentIndex())
            
        except Exception as e:
            pass

    def _update_icon_preview(self):
        """更新图标预览"""
        # 避免递归调用或死循环，如果正在更新中则返回
        if getattr(self, '_updating_icon', False):
            return
        self._updating_icon = True
        
        try:
            pixmap = None
            
            if self._custom_icon_path:
                try:
                    should_load = False
                    # 检查是否为资源路径 (包含逗号)
                    if ',' in self._custom_icon_path:
                        should_load = True
                    # 或者检查文件是否存在
                    elif os.path.exists(self._custom_icon_path):
                        should_load = True
                        
                    if should_load:
                        from core.icon_extractor import IconExtractor
                        pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
                except Exception as e:
                    logger.debug(f"加载自定义图标失败: {e}")

            # 应用反转
            if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
                from core.icon_extractor import IconExtractor
                pixmap = IconExtractor.invert_pixmap(pixmap)

            # 缩放到预览尺寸
            if pixmap and not pixmap.isNull():
                pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                self.icon_preview.setPixmap(pixmap)
        except:
            pass
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
                painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 6, 6)
                
                painter.setPen(QColor(0, 255, 0))
                font = QFont("Consolas", size // 3)
                font.setBold(True)
                painter.setFont(font)
                
                # 根据类型显示不同图标文本
                text = ">_"
                if self.type_combo.currentIndex() == 1: # Python
                    text = "Py"
                    painter.setPen(QColor(255, 215, 0)) # 金色
                elif self.type_combo.currentIndex() == 2: # Built-in
                    text = "In"
                    painter.setPen(QColor(100, 200, 255)) # 蓝色
                    
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, text)
            finally:
                painter.end()
            return pixmap
        except Exception as e:
            print(f"Error creating command icon: {e}")
            # 返回一个空的透明图片防止后续崩溃
            empty = QPixmap(size, size)
            empty.fill(QtCompat.transparent)
            return empty
    
    def _browse_icon(self):
        """浏览图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "",
            "图标文件 (*.ico *.png *.jpg *.jpeg *.bmp *.exe *.dll);;所有文件 (*.*)"
        )

        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ('.dll', '.exe'):
                # 检查文件是否包含图标
                from core.icon_extractor import IconExtractor
                count = IconExtractor.get_icon_count(file_path)

                if count > 0:
                    # 显示图标选择器
                    dialog = IconPickerDialog(self, file_path)
                    if exec_dialog(dialog) and dialog.selected_index >= 0:
                        self._custom_icon_path = f"{file_path},{dialog.selected_index}"
                        self.icon_path_edit.setText(self._custom_icon_path)
                        self.invert_theme_cb.setChecked(False)
                        self.invert_current_cb.setChecked(False)
                        self._update_icon_preview()
                        return

            # 如果不是 DLL/EXE 或者取消了选择，或者文件中没有图标
            # 如果是普通图片，直接设置
            if ext not in ('.dll', '.exe') or count == 0:
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
        if type_index == 2: # Built-in
            command = self.builtin_combo.currentData()
        else:
            command = self.command_edit.toPlainText().strip()
        
        if not name:
            self.name_edit.setFocus()
            return
        
        if not command:
            if type_index == 2:
                pass # 内置命令一定有值
            else:
                self.command_edit.setFocus()
                return
        
        self.accept()
    
    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]
        
        type_index = self.type_combo.currentIndex()
        if type_index == 0:
            self.shortcut.command_type = 'cmd'
            self.shortcut.command = self.command_edit.toPlainText().strip()
        elif type_index == 1:
            self.shortcut.command_type = 'python'
            self.shortcut.command = self.command_edit.toPlainText().strip()
        else:
            self.shortcut.command_type = 'builtin'
            self.shortcut.command = self.builtin_combo.currentData()
            
        self.shortcut.trigger_mode = 'after_close' if self.trigger_after_close_rb.isChecked() else 'immediate'
        self.shortcut.show_window = self.show_window_cb.isChecked()
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.type = ShortcutType.COMMAND
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, 'theme', 'dark')
        return self.shortcut
    
    def showEvent(self, event):
        """显示时应用阴影效果"""
        super().showEvent(event)
        
        # 居中对齐父窗口
        self._center_on_parent()
        
        if not getattr(self, '_shadow_applied', False):
            self._shadow_applied = True
            # 延迟一小段时间应用，确保窗口几何信息已准备就绪
            QTimer.singleShot(100, self._apply_effects)
            
        # 启动出现动画
        self._start_show_animation()
    
    def _start_show_animation(self):
        """窗口出现动画 (0.2s)"""
        # 1. 透明度动画
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)
        
        # 2. 位置动画 (微升 20px)
        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        self.pos_anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
        self.pos_anim.setEndValue(pos)
        self.pos_anim.setEasingCurve(QtCompat.OutCubic)
        
        # 并行运行
        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.start()
            
    def _center_on_parent(self):
        """居中显示在主窗口（ConfigWindow）"""
        center_dialog_on_main_window(self)
            
    def _apply_effects(self):
        """应用窗口特效 - 圆角 + 磨砂玻璃"""
        try:
            hwnd = int(self.winId())
            effect = get_window_effect()
            theme = getattr(self, 'theme', 'dark')
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)
            enable_acrylic_for_config_window(self, theme, blur_amount=10)
        except Exception:
            pass
