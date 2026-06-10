"""输入触发录制组件 - 支持键盘和鼠标"""

import ctypes
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
    QTimer,
    QWidget,
    pyqtSignal,
)
from ui.config_window.hotkey_capture_helpers import (
    CAPTURE_TIMEOUT_MS,
    apply_recorder_display_style,
    generic_modifiers_from_capture,
    key_name_from_vk,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class InputTriggerRecorderWidget(QWidget):
    """键盘+鼠标触发录制组件，支持keyboard/mouse/hybrid三种模式"""

    _native_capture_result = pyqtSignal(int, int, int)

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
        self._native_capture_active = False
        self._native_capture_available = True
        self._capture_dll = None
        self._capture_hook_installed_by_us = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText(tr("点击开始录制"))
        self.display.setMinimumWidth(sp(180))
        self.display.setFixedHeight(sp(26))
        self.display.setContextMenuPolicy(Qt.NoContextMenu)
        apply_recorder_display_style(self.display, False)
        layout.addWidget(self.display, 1)

        self.record_btn = QPushButton(tr("录制"))
        self.record_btn.setFixedWidth(sp(52))
        self.record_btn.setFixedHeight(sp(26))
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton(tr("清空"))
        self.clear_btn.setFixedHeight(sp(26))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        self.display.installEventFilter(self)
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._on_capture_timeout)
        self._native_capture_result.connect(self._handle_native_capture_result)

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
            apply_recorder_display_style(self.display, True)
            self.record_btn.setText(tr("停止"))
            self.display.setFocus()
            if not self._start_native_capture():
                logger.warning("触发按键录制无法启用 hooks.dll 受保护键盘捕获")
                self.recording = False
                self._end_recording()
                self.display.setPlaceholderText(tr("hooks.dll 需要更新后才能录制"))
        else:
            self._end_recording()

    def _end_recording(self):
        self._finish_native_capture(stop_native=True)
        self.recording = False
        self._restore_mouse_pause_scope()
        self.display.setPlaceholderText(tr("点击开始录制"))
        apply_recorder_display_style(self.display, False)
        self.record_btn.setText(tr("录制"))
        self._refresh_display()

    def _restore_mouse_pause_scope(self):
        if self._mouse_hook_pause_scope is not None:
            try:
                self._mouse_hook_pause_scope.__exit__(None, None, None)
            except Exception as exc:
                logger.debug("结束触发录制时恢复鼠标钩子状态失败: %s", exc, exc_info=True)
            finally:
                self._mouse_hook_pause_scope = None
                self._previous_mouse_paused = None

    def eventFilter(self, obj, event):
        if obj is self.display and self.recording:
            if event.type() == QEvent.KeyPress:
                return True
            elif event.type() == QEvent.MouseButtonPress:
                self._handle_mouse_button(event)
                return True
        return super().eventFilter(obj, event)

    def _start_native_capture(self) -> bool:
        if not self._native_capture_available:
            return False
        try:
            from hooks.hooks_wrapper import HooksDLL

            dll = HooksDLL.get_instance()
            self._capture_dll = dll
            if not dll.loaded or not dll.compatible or not getattr(dll, "_has_hotkey_capture", False):
                self._native_capture_available = False
                return False

            self._capture_hook_installed_by_us = False
            if not dll.is_keyboard_hook_installed():
                if not dll.install_keyboard_hook(None):
                    return False
                self._capture_hook_installed_by_us = True

            if not dll.start_hotkey_capture(self._on_native_capture, timeout_ms=CAPTURE_TIMEOUT_MS):
                if self._capture_hook_installed_by_us:
                    try:
                        dll.uninstall_keyboard_hook()
                    except Exception as exc:
                        logger.debug("卸载触发按键录制临时键盘钩子失败: %s", exc, exc_info=True)
                    self._capture_hook_installed_by_us = False
                return False

            self._native_capture_active = True
            self._capture_timer.start(CAPTURE_TIMEOUT_MS + 500)
            return True
        except Exception as exc:
            logger.debug("启动触发按键受保护录制失败: %s", exc, exc_info=True)
            self._native_capture_available = False
            self._capture_hook_installed_by_us = False
            self._native_capture_active = False
            return False

    def _on_native_capture(self, vk_code: int, modifiers: int, side_modifiers: int):
        self._native_capture_result.emit(int(vk_code), int(modifiers), int(side_modifiers))

    def _handle_native_capture_result(self, vk_code: int, modifiers: int, side_modifiers: int):
        key_str = key_name_from_vk(vk_code)
        if key_str:
            self.keys.append(key_str)
            self.modifiers = generic_modifiers_from_capture(modifiers)
        # DLL 会继续吞掉后续 keyup，直到本次组合键全部松开。
        self._finish_native_capture(stop_native=False)
        self.recording = False
        self._restore_mouse_pause_scope()
        self.display.setPlaceholderText(tr("点击开始录制"))
        apply_recorder_display_style(self.display, False)
        self.record_btn.setText(tr("录制"))
        self._refresh_display()
        if self._capture_hook_installed_by_us:
            QTimer.singleShot(250, self._cleanup_capture_hook_after_result)

    def _on_capture_timeout(self):
        if self._native_capture_active:
            logger.debug("触发按键录制超时，停止受保护录制")
        self._end_recording()

    def _finish_native_capture(self, stop_native: bool):
        if self._capture_timer.isActive():
            self._capture_timer.stop()
        dll = self._capture_dll
        if dll is not None and stop_native and self._native_capture_active:
            try:
                dll.stop_hotkey_capture()
            except Exception as exc:
                logger.debug("停止触发按键受保护录制失败: %s", exc, exc_info=True)
        should_cleanup_native = self._native_capture_active or self._capture_hook_installed_by_us
        if dll is not None and stop_native and should_cleanup_native:
            try:
                dll.release_all_modifier_keys()
            except Exception as exc:
                logger.debug("释放触发按键录制残留修饰键失败: %s", exc, exc_info=True)
        if dll is not None and self._capture_hook_installed_by_us and stop_native:
            try:
                dll.uninstall_keyboard_hook()
            except Exception as exc:
                logger.debug("卸载触发按键录制临时键盘钩子失败: %s", exc, exc_info=True)
            self._capture_hook_installed_by_us = False
        self._native_capture_active = False

    def _cleanup_capture_hook_after_result(self, attempt: int = 0):
        if not self._capture_hook_installed_by_us:
            return
        dll = self._capture_dll
        if dll is None:
            self._capture_hook_installed_by_us = False
            return
        try:
            if dll.is_hotkey_capture_active() and attempt < 20:
                QTimer.singleShot(250, lambda: self._cleanup_capture_hook_after_result(attempt + 1))
                return
            if dll.is_hotkey_capture_active():
                dll.stop_hotkey_capture()
            dll.uninstall_keyboard_hook()
        except Exception as exc:
            logger.debug("清理触发按键录制临时键盘钩子失败: %s", exc, exc_info=True)
        finally:
            self._capture_hook_installed_by_us = False

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
        self.modifiers = self._get_physical_modifiers() or self._get_modifiers(event)
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

    def _get_physical_modifiers(self):
        mods = []
        try:
            user32 = ctypes.windll.user32
            if (user32.GetAsyncKeyState(0x11) & 0x8000) or (user32.GetAsyncKeyState(0xA2) & 0x8000) or (user32.GetAsyncKeyState(0xA3) & 0x8000):
                mods.append("ctrl")
            if (user32.GetAsyncKeyState(0x12) & 0x8000) or (user32.GetAsyncKeyState(0xA4) & 0x8000) or (user32.GetAsyncKeyState(0xA5) & 0x8000):
                mods.append("alt")
            if (user32.GetAsyncKeyState(0x10) & 0x8000) or (user32.GetAsyncKeyState(0xA0) & 0x8000) or (user32.GetAsyncKeyState(0xA1) & 0x8000):
                mods.append("shift")
            if (user32.GetAsyncKeyState(0x5B) & 0x8000) or (user32.GetAsyncKeyState(0x5C) & 0x8000):
                mods.append("win")
        except Exception:
            return []
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
        self._end_recording()
        self.mode = "mouse"
        self.keys = []
        self.button = ""
        self.modifiers = []
        self._refresh_display()

    def set_mouse_hook(self, mouse_hook):
        self.mouse_hook = mouse_hook
