"""鼠标按键录制组件"""

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
from ui.config_window.hotkey_capture_helpers import apply_recorder_display_style
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class MouseKeyRecorderWidget(QWidget):
    """鼠标按键+修饰键录制组件"""

    # 使用数字值代替XButton常量（Qt中侧键的标准值）
    BUTTON_NAMES = {
        QtCompat.LeftButton: "左键",
        QtCompat.RightButton: "右键",
        QtCompat.MiddleButton: "中键",
        0x00000008: "侧键后",  # XButton1
        0x00000010: "侧键前",  # XButton2
    }

    BUTTON_VALUES = {
        QtCompat.LeftButton: "left",
        QtCompat.RightButton: "right",
        QtCompat.MiddleButton: "middle",
        0x00000008: "x1",  # XButton1
        0x00000010: "x2",  # XButton2
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.button = ""
        self.modifiers = []
        self.recording = False  # 录制状态
        self.mouse_hook = None  # 鼠标钩子引用
        self._previous_mouse_paused = None
        self._mouse_hook_pause_scope = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText(tr("点击开始录制"))
        self.display.setMinimumWidth(sp(180))
        self.display.setFixedHeight(sp(24))
        self.display.setContextMenuPolicy(Qt.NoContextMenu)  # 禁用右键菜单
        apply_recorder_display_style(self.display, False)
        layout.addWidget(self.display, 1)

        self.record_btn = QPushButton(tr("录制"))
        self.record_btn.setFixedWidth(sp(52))
        self.record_btn.setFixedHeight(sp(24))
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton(tr("清空"))
        self.clear_btn.setFixedHeight(sp(24))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        self.display.installEventFilter(self)

    def _toggle_recording(self):
        """切换录制状态"""
        self.recording = not self.recording
        if self.recording:
            if self.mouse_hook:
                self._mouse_hook_pause_scope = mouse_hook_paused(
                    self.mouse_hook,
                    restore_previous=True,
                    log_label="录制鼠标按键时的鼠标钩子",
                )
                self._mouse_hook_pause_scope.__enter__()
            self.display.setPlaceholderText(tr("录制中，请按下鼠标按键..."))
            apply_recorder_display_style(self.display, True)
            self.record_btn.setText(tr("停止"))
            self.display.setFocus()
        else:
            self._end_recording()

    def _end_recording(self):
        """结束录制"""
        self.recording = False
        if self._mouse_hook_pause_scope is not None:
            try:
                self._mouse_hook_pause_scope.__exit__(None, None, None)
            except Exception as exc:
                logger.debug("结束鼠标按键录制时恢复鼠标钩子状态失败: %s", exc, exc_info=True)
            finally:
                self._mouse_hook_pause_scope = None
                self._previous_mouse_paused = None
        self.display.setPlaceholderText(tr("点击开始录制"))
        apply_recorder_display_style(self.display, False)
        self.record_btn.setText(tr("录制"))
        self._refresh_display()

    def eventFilter(self, obj, event):
        if obj is self.display:
            if event.type() == QEvent.MouseButtonPress and self.recording:
                self._handle_mouse_button(event)
                return True
            elif event.type() == QEvent.KeyPress and self.recording:
                if event.key() == 0x01000000:  # ESC
                    self._end_recording()
                return True
        return super().eventFilter(obj, event)

    def _handle_mouse_button(self, event):
        btn = event.button()
        if btn not in self.BUTTON_VALUES:
            return

        self.button = self.BUTTON_VALUES[btn]

        # 获取修饰键
        self.modifiers = []
        mods = event.modifiers()
        if mods & QtCompat.ControlModifier:
            self.modifiers.append("ctrl")
        if mods & QtCompat.ShiftModifier:
            self.modifiers.append("shift")
        if mods & QtCompat.AltModifier:
            self.modifiers.append("alt")
        if mods & QtCompat.MetaModifier:
            self.modifiers.append("win")

        # 录制完成，自动结束
        self._end_recording()

    def _refresh_display(self):
        if not self.button:
            self.display.setText("")
            return

        parts = [m.capitalize() for m in self.modifiers]
        parts.append(self._button_display_name(self.button))
        self.display.setText(" + ".join(parts))

    def _button_display_name(self, button):
        mapping = {
            "left": "左键",
            "right": "右键",
            "middle": "中键",
            "x1": "侧键后",
            "x2": "侧键前",
        }
        return mapping.get(button, button)

    def set_trigger(self, button, modifiers):
        """设置触发配置"""
        self.button = button
        self.modifiers = list(modifiers)
        self._refresh_display()

    def get_button(self):
        """获取按键"""
        return self.button

    def get_modifiers(self):
        """获取修饰键"""
        return list(self.modifiers)

    def clear(self):
        """清空"""
        self.button = ""
        self.modifiers = []
        self._refresh_display()

    def set_mouse_hook(self, mouse_hook):
        """设置鼠标钩子引用"""
        self.mouse_hook = mouse_hook
