"""Hotkey edit dialog."""

import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QCheckBox,
    QColor,
    QEvent,
    QFont,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    Qt,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.styles.style import Glassmorphism
from ui.tooltip_helper import install_tooltip

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_radio_stylesheet, get_small_checkbox_stylesheet

_MODIFIER_VKS = {
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "lwin": 0x5B,
    "rwin": 0x5C,
}
_GENERIC_MODIFIERS = (("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift"), ("win", "Win"))
_LEFT_RIGHT_LABELS = {
    "lctrl": "LCtrl",
    "rctrl": "RCtrl",
    "lalt": "LAlt",
    "ralt": "RAlt",
    "lshift": "LShift",
    "rshift": "RShift",
    "lwin": "LWin",
    "rwin": "RWin",
}


class HotkeyRecorderWidget(QWidget):
    """Compact hotkey recorder with optional left/right modifiers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modifiers = []
        self.key = ""
        self.advanced_sides = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText("点击后直接按下快捷键")
        self.display.setFocusPolicy(QtCompat.StrongFocus)
        layout.addWidget(self.display, 1)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.clicked.connect(self.clear_hotkey)
        layout.addWidget(self.clear_btn)

        self.setFocusProxy(self.display)
        self.display.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.display and event.type() == QEvent.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)

    def set_advanced_sides(self, enabled: bool):
        self.advanced_sides = enabled
        self._normalize_modifiers()
        self._refresh_display()

    def set_hotkey(self, hotkey: str, modifiers: list, key: str):
        self.modifiers = list(modifiers or [])
        self.key = key or ""
        self._normalize_modifiers()
        self._refresh_display()

    def clear_hotkey(self):
        self.modifiers = []
        self.key = ""
        self._refresh_display()

    def get_modifiers(self) -> list:
        return list(self.modifiers)

    def get_key(self) -> str:
        return self.key

    def get_hotkey_string(self) -> str:
        parts = [self._label_for_modifier(m) for m in self.modifiers]
        if self.key:
            parts.append(self._label_for_key(self.key))
        return " + ".join(parts)

    def keyPressEvent(self, event):
        key_name = self._key_name(event)
        if not key_name:
            return
        if key_name in {"ctrl", "alt", "shift", "win", "lctrl", "rctrl", "lalt", "ralt", "lshift", "rshift", "lwin", "rwin"}:
            return
        self.modifiers = self._current_modifiers(event)
        self.key = key_name
        self._refresh_display()

    def _current_modifiers(self, event) -> list:
        if self.advanced_sides:
            mods = []
            try:
                user32 = ctypes.windll.user32
                for name, vk in _MODIFIER_VKS.items():
                    if user32.GetAsyncKeyState(vk) & 0x8000:
                        mods.append(name)
            except Exception:
                mods = []
            if mods:
                return mods

        modifiers = event.modifiers()
        mods = []
        if modifiers & QtCompat.ControlModifier:
            mods.append("ctrl")
        if modifiers & QtCompat.AltModifier:
            mods.append("alt")
        if modifiers & QtCompat.ShiftModifier:
            mods.append("shift")
        if modifiers & QtCompat.MetaModifier:
            mods.append("win")
        return mods

    def _normalize_modifiers(self):
        if self.advanced_sides:
            return
        normalized = []
        for mod in self.modifiers:
            generic = mod
            if mod in ("lctrl", "rctrl"):
                generic = "ctrl"
            elif mod in ("lalt", "ralt"):
                generic = "alt"
            elif mod in ("lshift", "rshift"):
                generic = "shift"
            elif mod in ("lwin", "rwin"):
                generic = "win"
            if generic not in normalized:
                normalized.append(generic)
        self.modifiers = normalized

    def _refresh_display(self):
        value = self.get_hotkey_string()
        self.display.setText(value if value else "")

    def _label_for_modifier(self, mod: str) -> str:
        if mod in _LEFT_RIGHT_LABELS:
            return _LEFT_RIGHT_LABELS[mod]
        for key, label in _GENERIC_MODIFIERS:
            if mod == key:
                return label
        return mod

    def _label_for_key(self, key: str) -> str:
        if len(key) == 1:
            return key.upper()
        return key.upper() if key.startswith("f") and key[1:].isdigit() else key.title()

    def _key_name(self, event) -> str:
        key = event.key()
        text = event.text()
        qt = Qt

        special = {
            qt.Key_Escape: "esc",
            qt.Key_Tab: "tab",
            qt.Key_Backtab: "tab",
            qt.Key_Backspace: "backspace",
            qt.Key_Return: "enter",
            qt.Key_Enter: "enter",
            qt.Key_Insert: "insert",
            qt.Key_Delete: "delete",
            qt.Key_Pause: "pause",
            qt.Key_Print: "printscreen",
            qt.Key_Home: "home",
            qt.Key_End: "end",
            qt.Key_Left: "left",
            qt.Key_Up: "up",
            qt.Key_Right: "right",
            qt.Key_Down: "down",
            qt.Key_PageUp: "pageup",
            qt.Key_PageDown: "pagedown",
            qt.Key_Space: "space",
            qt.Key_Control: "ctrl",
            qt.Key_Shift: "shift",
            qt.Key_Alt: "alt",
            qt.Key_Meta: "win",
        }
        if key in special:
            return special[key]
        if qt.Key_F1 <= key <= qt.Key_F35:
            return f"f{key - qt.Key_F1 + 1}"
        if qt.Key_A <= key <= qt.Key_Z:
            return chr(ord("a") + key - qt.Key_A)
        if qt.Key_0 <= key <= qt.Key_9:
            return chr(ord("0") + key - qt.Key_0)
        if text and text.strip():
            value = text.lower()
            if len(value) == 1 and ord(value) >= 32:
                return value
        native_vk = event.nativeVirtualKey() if hasattr(event, "nativeVirtualKey") else 0
        if 0x60 <= native_vk <= 0x69:
            return f"num{native_vk - 0x60}"
        return ""


class HotkeyDialog(BaseDialog):
    """Hotkey edit dialog."""

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.HOTKEY)
        self._custom_icon_path = self.shortcut.icon_path or ""

        self.setWindowTitle(tr("编辑快捷键") if shortcut else tr("添加快捷键"))
        self.setMinimumWidth(420)

        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        from .base_dialog import BaseDialog
        if BaseDialog._is_compiled():
            return
        try:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                painter.setFont(QFont("Segoe UI Symbol", 38))
                painter.setPen(QColor(144, 238, 144))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌘")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        title_label = QLabel("编辑快捷键" if self.shortcut.name else "添加快捷键")
        title_label.setStyleSheet("font-size: 12px; font-weight: 400; color: gray;")
        layout.addWidget(title_label)

        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)
        basic_layout.setContentsMargins(8, 0, 8, 8)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)
        layout.addWidget(basic_group)

        hotkey_group = QGroupBox("快捷键")
        hotkey_layout = QVBoxLayout(hotkey_group)
        hotkey_layout.setSpacing(6)
        hotkey_layout.setContentsMargins(8, 0, 8, 8)
        self.hotkey_input = HotkeyRecorderWidget()
        hotkey_layout.addWidget(self.hotkey_input)

        option_row = QHBoxLayout()
        option_row.setSpacing(8)
        self.advanced_sides_cb = QCheckBox("区分左右修饰键")
        self.advanced_sides_cb.stateChanged.connect(lambda state: self.hotkey_input.set_advanced_sides(bool(state)))
        option_row.addWidget(self.advanced_sides_cb)
        self.conflict_label = QLabel("")
        self.conflict_label.setWordWrap(False)
        self.conflict_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        option_row.addWidget(self.conflict_label, 1)
        hotkey_layout.addLayout(option_row)

        layout.addWidget(hotkey_group)

        trigger_group = QGroupBox("触发模式")
        trigger_layout = QHBoxLayout(trigger_group)
        trigger_layout.setSpacing(12)
        trigger_layout.setContentsMargins(8, 0, 8, 8)
        self.trigger_immediate_rb = QRadioButton("马上发送按键")
        install_tooltip(self.trigger_immediate_rb, "点击图标后立刻发送这组按键，适合不需要回到原窗口的操作")
        self.trigger_after_close_rb = QRadioButton("先关闭面板，再发送按键")
        install_tooltip(self.trigger_after_close_rb, "先关闭快捷启动面板并把焦点还给原来的窗口，再发送这组按键，适合控制原窗口")
        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        trigger_layout.addStretch()
        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)
        layout.addWidget(trigger_group)

        test_row = QHBoxLayout()
        test_row.setSpacing(6)
        self._test_btn = QPushButton("测试发送")
        self._test_btn.clicked.connect(self._test_hotkey)
        test_row.addWidget(self._test_btn)
        self.test_result_label = QLabel("")
        test_row.addWidget(self.test_result_label, 1)
        layout.addLayout(test_row)

        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 0, 6, 6)
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        icon_layout.addWidget(self.icon_preview)

        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(6)
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(6)
        self._browse_icon_btn = QPushButton("选择图标...")
        self._browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(self._browse_icon_btn)
        self._clear_icon_btn = QPushButton("清除")
        self._clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(self._clear_icon_btn)
        icon_btn_layout.addStretch()
        self.invert_theme_cb = QCheckBox("随主题反转")
        self.invert_current_cb = QCheckBox("当前反转")
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        icon_btn_layout.addWidget(self.invert_theme_cb)
        icon_btn_layout.addWidget(self.invert_current_cb)
        icon_right_layout.addLayout(icon_btn_layout)
        icon_layout.addLayout(icon_right_layout, 1)
        layout.addWidget(icon_group)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedSize(80, 32)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setFixedSize(80, 32)
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self._ok_btn)
        layout.addLayout(btn_layout)

        self.hotkey_input.display.textChanged.connect(self._update_conflict)
        self.resize(self.minimumSizeHint())

    def _apply_theme(self):
        self._apply_theme_colors()
        theme = self.theme
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        self.setStyleSheet(base_style + f"""
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
        """)
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [
            self.hotkey_input.clear_btn,
            self._test_btn,
            self._browse_icon_btn,
            self._clear_icon_btn,
            self._cancel_btn,
            self._ok_btn,
        ]:
            btn.setStyleSheet(flat_btn_style)

        radio_style = get_radio_stylesheet(theme)
        self.trigger_immediate_rb.setStyleSheet(radio_style)
        self.trigger_after_close_rb.setStyleSheet(radio_style)

        cb_style = get_small_checkbox_stylesheet(theme)
        self.advanced_sides_cb.setStyleSheet(cb_style)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)

        if theme == "dark":
            self.icon_preview.setStyleSheet("QLabel { background-color: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; }")
            self.conflict_label.setStyleSheet("color: rgba(255,255,255,0.62); font-size: 11px;")
            self.test_result_label.setStyleSheet("color: rgba(255,255,255,0.62); font-size: 11px;")
        else:
            self.icon_preview.setStyleSheet("QLabel { background-color: rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); border-radius: 10px; }")
            self.conflict_label.setStyleSheet("color: rgba(0,0,0,0.55); font-size: 11px;")
            self.test_result_label.setStyleSheet("color: rgba(0,0,0,0.55); font-size: 11px;")

    def _load_data(self):
        self.name_edit.setText(self.shortcut.name or "")
        modifiers = self.shortcut.hotkey_modifiers or []
        has_lr = any(m in _LEFT_RIGHT_LABELS for m in modifiers)
        self.advanced_sides_cb.setChecked(has_lr)
        self.hotkey_input.set_advanced_sides(has_lr)
        self.hotkey_input.set_hotkey(self.shortcut.hotkey or "", modifiers, self.shortcut.hotkey_key or "")
        if getattr(self.shortcut, "trigger_mode", "immediate") == "after_close":
            self.trigger_after_close_rb.setChecked(True)
        else:
            self.trigger_immediate_rb.setChecked(True)
        if self._custom_icon_path:
            self.icon_path_edit.setText(self._custom_icon_path)
        self.invert_theme_cb.setChecked(self.shortcut.icon_invert_with_theme)
        self.invert_current_cb.setChecked(self.shortcut.icon_invert_current)
        self._update_icon_preview()
        self._update_conflict()

    def _update_conflict(self):
        hotkey = self.hotkey_input.get_hotkey_string()
        if not hotkey:
            self.conflict_label.setText("")
            self.conflict_label.setToolTip("")
            return
        try:
            from core.hotkey_conflict_checker import check_conflict

            is_conflict, conflict_desc = check_conflict(hotkey)
            self.conflict_label.setText(conflict_desc if is_conflict else "未检测到明显冲突")
            self.conflict_label.setToolTip(self.conflict_label.text())
        except Exception:
            self.conflict_label.setText("")
            self.conflict_label.setToolTip("")

    def _test_hotkey(self):
        if not self.hotkey_input.get_key():
            self.hotkey_input.display.setFocus()
            return
        preview = self._build_shortcut_preview()
        self._test_btn.setEnabled(False)
        self.test_result_label.setText("发送中...")

        import threading
        def _do():
            try:
                from core import ShortcutExecutor
                success, error = ShortcutExecutor.execute(preview)
                text = "发送成功" if success else f"发送失败: {error}"
            except Exception as e:
                text = f"发送失败: {e}"
            from qt_compat import QTimer
            QTimer.singleShot(0, lambda: self._on_test_hotkey_done(text))
        threading.Thread(target=_do, daemon=True).start()

    def _on_test_hotkey_done(self, text: str):
        if self._dialog_finished:
            return
        self.test_result_label.setText(text)
        self._test_btn.setEnabled(True)

    def _build_shortcut_preview(self) -> ShortcutItem:
        shortcut = ShortcutItem(type=ShortcutType.HOTKEY)
        shortcut.name = self.name_edit.text().strip()[:6] or "测试"
        shortcut.hotkey = self.hotkey_input.get_hotkey_string()
        shortcut.hotkey_modifiers = self.hotkey_input.get_modifiers()
        shortcut.hotkey_key = self.hotkey_input.get_key()
        shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        return shortcut

    def _update_icon_preview(self):
        pixmap = None
        if self._custom_icon_path and os.path.exists(self._custom_icon_path):
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.from_file(self._custom_icon_path, 40)
            except Exception:
                pass
        if not pixmap or pixmap.isNull():
            pixmap = self._create_hotkey_icon(40)
        if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor

            pixmap = IconExtractor.invert_pixmap(pixmap)
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.icon_preview.setPixmap(pixmap)

    def _create_hotkey_icon(self, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setBrush(QColor(70, 130, 180))
            painter.setPen(QtCompat.NoPen)
            margin = size // 8
            painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI Symbol", size // 3))
            painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌘")
        finally:
            painter.end()
        return pixmap

    def _browse_icon(self):
        file_path = choose_custom_icon(self, "选择图标")
        if file_path:
            self._custom_icon_path = file_path
            self.icon_path_edit.setText(file_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()

    def _clear_icon(self):
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
        self.invert_theme_cb.setChecked(False)
        self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_invert_theme_changed(self, state):
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_ok(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        if not self.hotkey_input.get_key():
            self.hotkey_input.display.setFocus()
            return
        hotkey_str = self.hotkey_input.get_hotkey_string()
        try:
            from core.hotkey_conflict_checker import check_conflict
            from ui.styles.themed_messagebox import ThemedMessageBox

            is_conflict, conflict_desc = check_conflict(hotkey_str)
            if is_conflict:
                result = ThemedMessageBox.question(self, "快捷键冲突", f"{conflict_desc}\n\n是否仍要使用此快捷键？")
                if not result:
                    return
        except Exception:
            pass
        self.accept()

    def get_shortcut(self) -> ShortcutItem:
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.hotkey = self.hotkey_input.get_hotkey_string()
        self.shortcut.hotkey_modifiers = self.hotkey_input.get_modifiers()
        self.shortcut.hotkey_key = self.hotkey_input.get_key()
        self.shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.type = ShortcutType.HOTKEY
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, "theme", "dark")
        return self.shortcut
