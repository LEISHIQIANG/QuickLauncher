"""输入触发录制组件 - 支持键盘和鼠标"""

import logging

from core.i18n import tr
from hooks.hook_pause import mouse_hook_paused
from qt_compat import (
    QEvent,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    Qt,
    QtCompat,
    QWidget,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class InputTriggerRecorderWidget(QWidget):
    """键盘+鼠标触发录制组件，支持keyboard/mouse/hybrid三种模式"""

    BUTTON_VALUES = {
        QtCompat.LeftButton: "left",
        QtCompat.RightButton: "right",
        QtCompat.MiddleButton: "middle",
        0x00000008: "x1",
        0x00000010: "x2",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "mouse"
        self.keys = []
        self.button = ""
        self.modifiers = []
        self.recording = False
        self.mouse_hook = None
        self._previous_mouse_paused = None
        self._mouse_hook_pause_scope = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText(tr("点击开始录制"))
        self.display.setMinimumWidth(sp(180))
        self.display.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.display, 1)

        self.record_btn = QPushButton(tr("录制"))
        self.record_btn.setFixedHeight(sp(26))
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton(tr("清空"))
        self.clear_btn.setFixedHeight(sp(26))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        self.display.installEventFilter(self)

    def _toggle_recording(self):
        self.recording = not self.recording
        if self.recording:
            # 清空之前的数据
            self.keys = []
            self.button = ""
            self.modifiers = []

            if self.mouse_hook:
                self._mouse_hook_pause_scope = mouse_hook_paused(
                    self.mouse_hook,
                    restore_previous=True,
                    log_label="录制触发按键时的鼠标钩子",
                )
                self._mouse_hook_pause_scope.__enter__()
            self.display.setPlaceholderText(tr("录制中，按键盘或鼠标..."))
            self.display.setStyleSheet(f"border: {sp(2)}px solid #4A9EFF; background: rgba(74, 158, 255, 0.1);")
            self.record_btn.setText(tr("停止"))
            self.display.setFocus()
        else:
            self._end_recording()

    def _end_recording(self):
        self.recording = False
        if self._mouse_hook_pause_scope is not None:
            try:
                self._mouse_hook_pause_scope.__exit__(None, None, None)
            except Exception as exc:
                logger.debug("结束触发录制时恢复鼠标钩子状态失败: %s", exc, exc_info=True)
            finally:
                self._mouse_hook_pause_scope = None
                self._previous_mouse_paused = None
        self.display.setPlaceholderText(tr("点击开始录制"))
        self.display.setStyleSheet("")
        self.record_btn.setText(tr("录制"))
        self._refresh_display()

    def eventFilter(self, obj, event):
        if obj is self.display and self.recording:
            if event.type() == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Escape:
                    self._end_recording()
                    return True
                if key not in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                    self._handle_keyboard_key(event)
                    return True
            elif event.type() == QEvent.MouseButtonPress:
                self._handle_mouse_button(event)
                return True
        return super().eventFilter(obj, event)

    def _handle_keyboard_key(self, event):
        key_str = self._key_to_string(event.key())
        if not key_str:
            return

        self.keys.append(key_str)
        self.modifiers = self._get_modifiers(event)
        self._end_recording()

    def _handle_mouse_button(self, event):
        btn = event.button()
        if btn not in self.BUTTON_VALUES:
            return

        self.button = self.BUTTON_VALUES[btn]
        self.modifiers = self._get_modifiers(event)
        self._end_recording()

    def _get_modifiers(self, event):
        mods = []
        mod_flags = event.modifiers()
        if mod_flags & QtCompat.ControlModifier:
            mods.append("ctrl")
        if mod_flags & QtCompat.ShiftModifier:
            mods.append("shift")
        if mod_flags & QtCompat.AltModifier:
            mods.append("alt")
        if mod_flags & QtCompat.MetaModifier:
            mods.append("win")
        return mods

    def _key_to_string(self, key_code):
        """将Qt键码转换为字符串"""
        if Qt.Key_A <= key_code <= Qt.Key_Z:
            return chr(key_code).lower()
        if Qt.Key_0 <= key_code <= Qt.Key_9:
            return chr(key_code)
        if Qt.Key_F1 <= key_code <= Qt.Key_F24:
            return f"f{key_code - Qt.Key_F1 + 1}"

        key_map = {
            Qt.Key_Space: "space",
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Tab: "tab",
            Qt.Key_Backspace: "backspace",
            Qt.Key_Escape: "esc",
            Qt.Key_Delete: "delete",
            Qt.Key_Insert: "insert",
            Qt.Key_Home: "home",
            Qt.Key_End: "end",
            Qt.Key_PageUp: "pageup",
            Qt.Key_PageDown: "pagedown",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
            Qt.Key_Pause: "pause",
            Qt.Key_Print: "printscreen",
        }
        return key_map.get(key_code, "")

    def _refresh_display(self):
        # 判断模式
        if self.keys and self.button:
            self.mode = "hybrid"
        elif self.keys:
            self.mode = "keyboard"
        elif self.button:
            self.mode = "mouse"
        else:
            self.display.setText("")
            return

        parts = [m.capitalize() for m in self.modifiers]
        for k in self.keys:
            parts.append(k.upper() if len(k) == 1 else k.capitalize())
        if self.button:
            btn_names = {"left": "左键", "right": "右键", "middle": "中键", "x1": "侧键后", "x2": "侧键前"}
            parts.append(btn_names.get(self.button, self.button))

        self.display.setText(" + ".join(parts))

    def set_trigger(self, mode, keys, button, modifiers):
        self.mode = mode
        self.keys = list(keys)
        self.button = button
        self.modifiers = list(modifiers)
        self._refresh_display()

    def get_mode(self):
        return self.mode

    def get_keys(self):
        return list(self.keys)

    def get_button(self):
        return self.button

    def get_modifiers(self):
        return list(self.modifiers)

    def clear(self):
        self.mode = "mouse"
        self.keys = []
        self.button = ""
        self.modifiers = []
        self._refresh_display()

    def set_mouse_hook(self, mouse_hook):
        self.mouse_hook = mouse_hook
