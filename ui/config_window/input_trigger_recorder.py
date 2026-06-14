"""Protected keyboard and mouse trigger recorder."""

import logging

from core.i18n import tr
from hooks.hook_pause import mouse_hook_paused
from hooks.key_map import key_display_name
from qt_compat import QEvent, QHBoxLayout, QLineEdit, QPushButton, Qt, QtCompat, QTimer, QWidget, pyqtSignal
from ui.config_window.hotkey_capture_helpers import (
    CAPTURE_TIMEOUT_MS,
    KeyboardStatePoller,
    apply_recorder_display_style,
    generic_modifiers_from_capture,
    key_name_from_vk,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class InputTriggerRecorderWidget(QWidget):
    """Record keyboard, five-button mouse, or mixed physical chords."""

    _native_capture_result = pyqtSignal(int, int, int, int)

    BUTTON_VALUES = {
        QtCompat.LeftButton: "left",
        QtCompat.RightButton: "right",
        QtCompat.MiddleButton: "middle",
        0x00000008: "x1",
        0x00000010: "x2",
    }
    NATIVE_BUTTON_VALUES = {1: "left", 2: "right", 4: "middle", 8: "x1", 16: "x2"}
    BUTTON_DISPLAY_NAMES = {
        "left": "左键",
        "right": "右键",
        "middle": "中键",
        "x1": "侧键后",
        "x2": "侧键前",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "mouse"
        self.keys = []
        self.button = ""
        self.modifiers = []
        self.recording = False
        self.mouse_hook = None
        self._mouse_hook_pause_scope = None
        self._native_capture_active = False
        self._native_capture_available = True
        self._capture_dll = None
        self._capture_keyboard_hook_installed_by_us = False
        self._capture_mouse_hook_installed_by_us = False
        self._capture_session = 0
        self._keyboard_state_poller = KeyboardStatePoller(
            self,
            self._handle_state_poll_result,
            log_label="trigger",
        )

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
        self._native_capture_result.connect(self._handle_native_capture_signal)

    def _toggle_recording(self):
        if self.recording:
            logger.debug("手动停止触发组合捕获: widget=%s", hex(id(self)))
            self._end_recording()
            return

        self.keys = []
        self.button = ""
        self.modifiers = []
        self.recording = True
        self._capture_session += 1
        if self.mouse_hook:
            self._mouse_hook_pause_scope = mouse_hook_paused(
                self.mouse_hook,
                restore_previous=True,
                log_label="录制触发组合时的鼠标钩子",
            )
            self._mouse_hook_pause_scope.__enter__()
        self.display.setPlaceholderText(tr("录制中，请按下组合并全部松开..."))
        apply_recorder_display_style(self.display, True)
        self.record_btn.setText(tr("停止"))
        self.display.setFocus()
        self._keyboard_state_poller.start()
        if not self._start_native_capture():
            logger.warning("触发组合录制无法启用 hooks.dll 受保护键鼠捕获")
            self.recording = False
            self._end_recording()
            self.display.setPlaceholderText(tr("hooks.dll 需要更新后才能录制"))

    def _end_recording(self, *, stop_native: bool = True):
        self._finish_native_capture(stop_native=stop_native)
        self.recording = False
        self._restore_mouse_pause_scope()
        self.display.setPlaceholderText(tr("点击开始录制"))
        apply_recorder_display_style(self.display, False)
        self.record_btn.setText(tr("录制"))
        self._refresh_display()

    def _restore_mouse_pause_scope(self):
        if self._mouse_hook_pause_scope is None:
            return
        try:
            self._mouse_hook_pause_scope.__exit__(None, None, None)
        except Exception as exc:
            logger.debug("结束触发录制时恢复鼠标钩子状态失败: %s", exc, exc_info=True)
        finally:
            self._mouse_hook_pause_scope = None

    def eventFilter(self, obj, event):
        if (
            obj is self.display
            and self.recording
            and event.type()
            in {
                QEvent.KeyPress,
                QEvent.KeyRelease,
                QEvent.MouseButtonPress,
                QEvent.MouseButtonRelease,
            }
        ):
            return True
        return super().eventFilter(obj, event)

    def _start_native_capture(self, capture_session: int | None = None) -> bool:
        if not self._native_capture_available:
            return False
        try:
            from hooks.hooks_wrapper import HooksDLL

            dll = HooksDLL.get_instance()
            self._capture_dll = dll
            if not dll.loaded or not dll.compatible or not getattr(dll, "_has_protected_chord_capture", False):
                self._native_capture_available = False
                return False

            self._capture_keyboard_hook_installed_by_us = False
            self._capture_mouse_hook_installed_by_us = False
            keyboard_ready, installed_temporarily = dll.rearm_keyboard_hook_for_capture()
            if not keyboard_ready:
                return False
            self._capture_keyboard_hook_installed_by_us = installed_temporarily
            if not dll.is_mouse_hook_installed():
                if not dll.install_mouse_hook(lambda _x, _y: None):
                    self._cleanup_temporary_hooks()
                    return False
                self._capture_mouse_hook_installed_by_us = True
            session = self._capture_session if capture_session is None else int(capture_session)

            if not dll.start_protected_chord_capture(
                lambda input_code, modifiers, side_modifiers: self._on_native_capture(
                    session,
                    input_code,
                    modifiers,
                    side_modifiers,
                ),
                keyboard=True,
                mouse_buttons=True,
                include_injected=True,
                timeout_ms=CAPTURE_TIMEOUT_MS,
                owner=self,
            ):
                self._cleanup_temporary_hooks()
                return False

            self._native_capture_active = True
            self._capture_timer.start(CAPTURE_TIMEOUT_MS + 500)
            return True
        except Exception as exc:
            logger.debug("启动触发组合受保护录制失败: %s", exc, exc_info=True)
            self._native_capture_available = False
            self._native_capture_active = False
            self._cleanup_temporary_hooks()
            return False

    def _on_native_capture(self, capture_session: int, input_code: int, modifiers: int, side_modifiers: int):
        self._native_capture_result.emit(
            int(capture_session),
            int(input_code),
            int(modifiers),
            int(side_modifiers),
        )

    def _handle_native_capture_signal(
        self,
        capture_session: int,
        input_code: int,
        modifiers: int,
        side_modifiers: int,
    ):
        self._handle_native_capture_result(
            input_code,
            modifiers,
            side_modifiers,
            capture_session,
        )

    def _handle_native_capture_result(
        self,
        input_code: int,
        modifiers: int,
        side_modifiers: int,
        capture_session: int | None = None,
    ):
        if capture_session is not None and (int(capture_session) != self._capture_session or not self.recording):
            logger.debug(
                "忽略过期触发组合捕获回调: widget=%s session=%s current_session=%s recording=%s",
                hex(id(self)),
                capture_session,
                self._capture_session,
                self.recording,
            )
            return
        del side_modifiers
        if input_code > 0:
            key_name = key_name_from_vk(input_code)
            if key_name and key_name not in self.keys:
                self.keys.append(key_name)
            self.modifiers = self._merge_modifiers(self.modifiers, generic_modifiers_from_capture(modifiers))
            self._refresh_display()
            return
        if input_code < 0:
            button = self.NATIVE_BUTTON_VALUES.get(-input_code, "")
            if button and not self.button:
                self.button = button
            self.modifiers = self._merge_modifiers(self.modifiers, generic_modifiers_from_capture(modifiers))
            self._refresh_display()
            return

        self.modifiers = self._merge_modifiers(self.modifiers, generic_modifiers_from_capture(modifiers))
        self._end_recording(stop_native=True)
        logger.debug(
            "触发组合捕获完成: widget=%s mode=%s keys=%s button=%s modifiers=%s text=%r",
            hex(id(self)),
            self.mode,
            self.keys,
            self.button,
            self.modifiers,
            self.display.text(),
        )

    def _handle_state_poll_result(self, input_code: int, modifiers: int, side_modifiers: int):
        if not self.recording:
            return
        self._handle_native_capture_result(input_code, modifiers, side_modifiers)

    @staticmethod
    def _merge_modifiers(existing: list[str], incoming: list[str]) -> list[str]:
        order = ("ctrl", "alt", "shift", "win")
        values = set(existing) | set(incoming)
        return [name for name in order if name in values]

    def _on_capture_timeout(self):
        if self._native_capture_active:
            logger.debug("触发组合捕获超时: widget=%s", hex(id(self)))
        self._end_recording()

    def _finish_native_capture(self, stop_native: bool):
        self._keyboard_state_poller.stop()
        if self._capture_timer.isActive():
            self._capture_timer.stop()
        dll = self._capture_dll
        if dll is not None and stop_native and self._native_capture_active:
            try:
                dll.stop_protected_chord_capture(owner=self)
            except Exception as exc:
                logger.debug("停止触发组合受保护录制失败: %s", exc, exc_info=True)
        self._native_capture_active = False
        if stop_native:
            self._cleanup_temporary_hooks()

    def _cleanup_temporary_hooks(self):
        dll = self._capture_dll
        if dll is None:
            self._capture_keyboard_hook_installed_by_us = False
            self._capture_mouse_hook_installed_by_us = False
            return
        if self._capture_mouse_hook_installed_by_us:
            try:
                dll.uninstall_mouse_hook()
            except Exception as exc:
                logger.debug("卸载触发录制临时鼠标钩子失败: %s", exc, exc_info=True)
            self._capture_mouse_hook_installed_by_us = False
        if self._capture_keyboard_hook_installed_by_us:
            try:
                dll.uninstall_keyboard_hook()
            except Exception as exc:
                logger.debug("卸载触发录制临时键盘钩子失败: %s", exc, exc_info=True)
            self._capture_keyboard_hook_installed_by_us = False

    def _refresh_display(self):
        if self.keys and self.button:
            self.mode = "hybrid"
        elif self.keys:
            self.mode = "keyboard"
        elif self.button:
            self.mode = "mouse"
        else:
            self.display.setText("")
            return

        parts = [modifier.capitalize() for modifier in self.modifiers]
        parts.extend(key_display_name(key) for key in self.keys)
        if self.button:
            parts.append(self.BUTTON_DISPLAY_NAMES.get(self.button, self.button))
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
