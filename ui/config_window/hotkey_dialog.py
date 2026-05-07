"""
快捷键编辑对话框
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox, QCheckBox, QWidget,
    QFileDialog, QPixmap, QPainter, QColor, QFont, QIcon,
    Qt, QtCompat, PYQT_VERSION, QRadioButton, QButtonGroup, QSizePolicy,
    QPainterPath, QPen, QTimer, QRectF, QListView, QMenu, QAction, QPoint
)

from ui.utils.window_effect import get_window_effect, is_win11, enable_acrylic_for_config_window
from core import ShortcutItem, ShortcutType
from .theme_helper import get_radio_stylesheet, get_checkbox_stylesheet, get_small_checkbox_stylesheet
from ui.styles.style import get_dialog_stylesheet, Glassmorphism
from ui.utils.window_effect import enable_window_shadow_and_round_corners
from ui.utils.dialog_helper import center_dialog_on_main_window
from .base_dialog import BaseDialog


class HotkeyInputWidget(QWidget):
    """快捷键输入组件 - 复选框版本"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)  # 减少间距
        
        # Ctrl 复选框
        self.ctrl_cb = QCheckBox("Ctrl")
        layout.addWidget(self.ctrl_cb)
        
        plus1 = QLabel("+")
        plus1.setFixedWidth(8)
        plus1.setAlignment(QtCompat.AlignCenter)
        layout.addWidget(plus1)
        
        # Alt 复选框
        self.alt_cb = QCheckBox("Alt")
        layout.addWidget(self.alt_cb)
        
        plus2 = QLabel("+")
        plus2.setFixedWidth(8)
        plus2.setAlignment(QtCompat.AlignCenter)
        layout.addWidget(plus2)
        
        # Shift 复选框
        self.shift_cb = QCheckBox("Shift")
        layout.addWidget(self.shift_cb)
        
        plus3 = QLabel("+")
        plus3.setFixedWidth(8)
        plus3.setAlignment(QtCompat.AlignCenter)
        layout.addWidget(plus3)
        
        # Win 复选框
        self.win_cb = QCheckBox("Win")
        layout.addWidget(self.win_cb)
        
        plus4 = QLabel("+")
        plus4.setFixedWidth(8)
        plus4.setAlignment(QtCompat.AlignCenter)
        layout.addWidget(plus4)
        
        # 主键输入
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("主键")
        self.key_edit.setMaxLength(10)
        self.key_edit.setMinimumWidth(80)
        self.key_edit.setMaximumWidth(140)
        self.key_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.key_edit, 1)
    
    def set_hotkey(self, hotkey: str, modifiers: list, key: str):
        """设置快捷键"""
        if modifiers is None:
            modifiers = []
        
        self.ctrl_cb.setChecked("ctrl" in modifiers)
        self.alt_cb.setChecked("alt" in modifiers)
        self.shift_cb.setChecked("shift" in modifiers)
        self.win_cb.setChecked("win" in modifiers)
        self.key_edit.setText(key or "")
    
    def get_hotkey_string(self) -> str:
        """获取快捷键字符串"""
        parts = []
        
        if self.ctrl_cb.isChecked():
            parts.append("Ctrl")
        if self.alt_cb.isChecked():
            parts.append("Alt")
        if self.shift_cb.isChecked():
            parts.append("Shift")
        if self.win_cb.isChecked():
            parts.append("Win")
        
        key = self.key_edit.text().strip()
        if key:
            parts.append(key)
        
        return " + ".join(parts) if parts else ""
    
    def get_modifiers(self) -> list:
        """获取修饰键列表"""
        modifiers = []
        if self.ctrl_cb.isChecked():
            modifiers.append("ctrl")
        if self.alt_cb.isChecked():
            modifiers.append("alt")
        if self.shift_cb.isChecked():
            modifiers.append("shift")
        if self.win_cb.isChecked():
            modifiers.append("win")
        return modifiers
    
    def get_key(self) -> str:
        """获取主键"""
        return self.key_edit.text().strip()
    
    def apply_theme(self, theme: str):
        """应用主题到复选框"""
        try:
            self.setStyleSheet(get_checkbox_stylesheet(theme))
        except Exception as e:
            print(f"Error applying theme to HotkeyInputWidget: {e}")

class HotkeyDialog(BaseDialog):
    """快捷键编辑对话框"""

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.HOTKEY)
        self._custom_icon_path = self.shortcut.icon_path or ""

        self.setWindowTitle("编辑快捷键" if shortcut else "添加快捷键")
        self.setMinimumWidth(380)
        
        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()
    
    def _setup_window_icon(self):
        """设置窗口图标"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QtCompat.transparent)
        
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            
            # 绘制键盘图标
            font = QFont("Segoe UI Emoji", 40)
            font.setStyleHint(QFont.StyleHint.SansSerif)
            painter.setFont(font)
            
            painter.setPen(QColor(144, 238, 144))
            painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌨")
        finally:
            painter.end()
        
        self.setWindowIcon(QIcon(pixmap))
    
    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"

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
        # 同时应用主题到快捷键输入组件
        self.hotkey_input.apply_theme(theme)

        # 按钮使用扁平操作按钮样式（与主配置窗口底部四按钮一致）
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [self._browse_icon_btn, self._clear_icon_btn,
                     self._refresh_btn, self._cancel_btn, self._ok_btn]:
            btn.setStyleSheet(flat_btn_style)

        # 应用单选按钮样式
        radio_style = get_radio_stylesheet(theme)
        self.trigger_immediate_rb.setStyleSheet(radio_style)
        self.trigger_after_close_rb.setStyleSheet(radio_style)

        # 应用复选框样式
        cb_style = get_small_checkbox_stylesheet(theme)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)

        if theme == "dark":
            self.icon_preview.setStyleSheet(
                "QLabel { background-color: rgba(255, 255, 255, 0.1); "
                "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; }"
            )
        else:
            self.icon_preview.setStyleSheet(
                "QLabel { background-color: rgba(0, 0, 0, 0.05); border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 10px; }"
            )

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑快捷键" if self.shortcut.name else "添加快捷键")
        title_label.setStyleSheet("font-size: 12px; font-weight: 400; color: gray;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)
        basic_layout.setContentsMargins(8, 0, 8, 8)
        
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow("名称:", self.name_edit)
        
        layout.addWidget(basic_group)
        
        # 图标设置
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 6, 6, 6)

        # 图标预览
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        icon_layout.addWidget(self.icon_preview)

        # 图标路径
        icon_path_layout = QVBoxLayout()
        icon_path_layout.setSpacing(6)
        
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_path_layout.addWidget(self.icon_path_edit)
        
        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(6)

        browse_icon_btn = QPushButton("选择图标...")
        browse_icon_btn.setMinimumWidth(70)
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton("清除")
        clear_icon_btn.setFixedHeight(26)
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

        # 快捷键设置
        hotkey_group = QGroupBox("快捷键组合")
        hotkey_layout = QVBoxLayout(hotkey_group)
        hotkey_layout.setSpacing(6)
        hotkey_layout.setContentsMargins(8, 0, 8, 8)
        
        # 使用复选框版本的输入组件
        self.hotkey_input = HotkeyInputWidget()
        hotkey_layout.addWidget(self.hotkey_input)
        
        layout.addWidget(hotkey_group)

        # 触发模式
        trigger_group = QGroupBox("触发模式")
        trigger_layout = QVBoxLayout(trigger_group)
        trigger_layout.setSpacing(6)
        trigger_layout.setContentsMargins(8, 0, 8, 8)
        
        self.trigger_immediate_rb = QRadioButton("立即触发 (全局快捷键)")
        install_tooltip(self.trigger_immediate_rb, "点击后立即执行")

        self.trigger_after_close_rb = QRadioButton("窗口关闭后触发")
        install_tooltip(self.trigger_after_close_rb, "等待快捷启动窗口完全关闭后执行")
        
        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        
        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)
        
        layout.addWidget(trigger_group)
        
        # 预览
        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(6)
        preview_layout.addWidget(QLabel("预览:"))

        self.preview_label = QLineEdit()
        self.preview_label.setReadOnly(True)
        self.preview_label.setText("无")
        preview_layout.addWidget(self.preview_label, 1)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(50)
        refresh_btn.clicked.connect(self._update_preview)
        preview_layout.addWidget(refresh_btn)
        self._refresh_btn = refresh_btn

        layout.addLayout(preview_layout)

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

        # 连接信号更新预览
        self.hotkey_input.ctrl_cb.stateChanged.connect(self._update_preview)
        self.hotkey_input.alt_cb.stateChanged.connect(self._update_preview)
        self.hotkey_input.shift_cb.stateChanged.connect(self._update_preview)
        self.hotkey_input.win_cb.stateChanged.connect(self._update_preview)
        self.hotkey_input.key_edit.textChanged.connect(self._update_preview)

        # 自适应大小
        if self.height() > 500:
            self.resize(380, 500)
        else:
            self.resize(380, self.height())
    
    def _load_data(self):
        """加载数据"""
        self.name_edit.setText(self.shortcut.name or "")
        self.hotkey_input.set_hotkey(
            self.shortcut.hotkey or "",
            self.shortcut.hotkey_modifiers or [],
            self.shortcut.hotkey_key or ""
        )
        
        # 加载触发模式
        if getattr(self.shortcut, 'trigger_mode', 'immediate') == 'after_close':
            self.trigger_after_close_rb.setChecked(True)
        else:
            self.trigger_immediate_rb.setChecked(True)
        
        # 加载图标
        if self._custom_icon_path:
            self.icon_path_edit.setText(self._custom_icon_path)

        # 加载反转设置
        self.invert_theme_cb.setChecked(self.shortcut.icon_invert_with_theme)
        self.invert_current_cb.setChecked(self.shortcut.icon_invert_current)

        self._update_icon_preview()
        self._update_preview()
    
    def _update_icon_preview(self):
        """更新图标预览"""
        pixmap = None

        # 尝试加载自定义图标
        if self._custom_icon_path and os.path.exists(self._custom_icon_path):
            try:
                from core.icon_extractor import IconExtractor
                pixmap = IconExtractor.from_file(self._custom_icon_path, 40)
            except:
                pass

        # 默认快捷键图标
        if not pixmap or pixmap.isNull():
            pixmap = self._create_hotkey_icon(40)

        # 应用反转
        if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor
            pixmap = IconExtractor.invert_pixmap(pixmap)

        # 缩放到预览尺寸
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

        self.icon_preview.setPixmap(pixmap)
    
    def _create_hotkey_icon(self, size: int) -> QPixmap:
        """创建快捷键图标"""
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        
        painter.setBrush(QColor(70, 130, 180))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 6, 6)
        
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌨")
        
        painter.end()
        return pixmap
    
    def _browse_icon(self):
        """浏览图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标", "",
            "图标文件 (*.ico *.png *.jpg *.jpeg *.bmp *.exe);;所有文件 (*.*)"
        )

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
    
    def _update_preview(self):
        """更新预览"""
        hotkey = self.hotkey_input.get_hotkey_string()
        self.preview_label.setText(hotkey if hotkey else "无")
    
    def _on_invert_theme_changed(self, state):
        """随主题反转勾选变化"""
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_ok(self):
        """确定"""
        name = self.name_edit.text().strip()
        key = self.hotkey_input.get_key()

        if not name:
            self.name_edit.setFocus()
            return

        if not key:
            self.hotkey_input.key_edit.setFocus()
            return

        # 快捷键冲突检测
        hotkey_str = self.hotkey_input.get_hotkey_string()
        try:
            from core.hotkey_conflict_checker import check_conflict
            is_conflict, conflict_desc = check_conflict(hotkey_str)
            if is_conflict:
                from ui.styles.themed_messagebox import ThemedMessageBox
                result = ThemedMessageBox.question(
                    self, "快捷键冲突",
                    f"{conflict_desc}\n\n是否仍要使用此快捷键？"
                )
                if not result:
                    return
        except Exception:
            pass

        self.accept()

    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.hotkey = self.hotkey_input.get_hotkey_string()
        self.shortcut.hotkey_modifiers = self.hotkey_input.get_modifiers()
        self.shortcut.hotkey_key = self.hotkey_input.get_key()
        self.shortcut.trigger_mode = 'after_close' if self.trigger_after_close_rb.isChecked() else 'immediate'
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, 'theme', 'dark')
        return self.shortcut
