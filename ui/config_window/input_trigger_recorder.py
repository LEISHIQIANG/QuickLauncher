"""Protected keyboard and mouse trigger recorder."""

import logging
from typing import Any

from core.i18n import tr
from hooks.hook_pause import mouse_hook_paused
from hooks.key_map import key_display_name
from qt_compat import QEvent, QHBoxLayout, QLineEdit, QPoint, QPushButton, Qt, QtCompat, QTimer, QWidget, pyqtSignal
from ui.config_window.hotkey_capture_helpers import (
    CAPTURE_TIMEOUT_MS,
    KeyboardStatePoller,
    apply_recorder_display_style,
    generic_modifiers_from_capture,
    key_name_from_vk,
)
from ui.styles.popup_menu import PopupMenu
from ui.utils.ui_scale import scale_qss, sp

logger = logging.getLogger(__name__)


def _reapply_item_style(menu, style):
    """重新应用菜单项的样式（PopupMenu._refresh_styles 会在 popup 时覆盖）"""
    try:
        for child in menu.children():
            if child.property("popup_menu_role") == "action":
                child.setStyleSheet(style)
    except RuntimeError:
        logger.debug("Preset menu item style reapply skipped because the menu was deleted", exc_info=True)


class InputTriggerRecorderWidget(QWidget):
    """Record keyboard, five-button mouse, or mixed physical chords."""

    _native_capture_result = pyqtSignal(int, int, int, int)
    taskbar_trigger_requested = pyqtSignal(bool)  # bool = 是否带 Ctrl 修饰

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
        self._taskbar_trigger: bool = False
        self._taskbar_with_ctrl: bool = False
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
        self.display.setMinimumWidth(sp(120))
        self.display.setFixedHeight(sp(24))
        self.display.setContextMenuPolicy(Qt.NoContextMenu)
        apply_recorder_display_style(self.display, False)
        layout.addWidget(self.display, 1)

        self.record_btn = QPushButton(tr("录制"))
        self.record_btn.setFixedWidth(sp(52))
        self.record_btn.setFixedHeight(sp(24))
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton(tr("清空"))
        self.clear_btn.setFixedWidth(sp(52))
        self.clear_btn.setFixedHeight(sp(24))
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)

        self.preset_btn = QPushButton(tr("预设"))
        self.preset_btn.setFixedWidth(sp(96))
        self.preset_btn.setFixedHeight(sp(24))
        self.preset_btn.clicked.connect(self._show_preset_menu)
        layout.addWidget(self.preset_btn)

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
        self._taskbar_trigger = False
        self._taskbar_with_ctrl = False
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
        self._taskbar_trigger = False
        self._taskbar_with_ctrl = False
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
        self._taskbar_trigger = False
        self._taskbar_with_ctrl = False
        self._refresh_display()

    def set_taskbar_trigger(self, with_ctrl: bool):
        """设置任务栏双击触发显示"""
        self._end_recording()
        self._taskbar_trigger = True
        self._taskbar_with_ctrl = with_ctrl
        modifier_str = tr("Ctrl+") if with_ctrl else ""
        self.display.setText(f"{modifier_str}{tr('任务栏双击')}")

    def is_taskbar_trigger(self) -> bool:
        """查询当前是否是任务栏触发模式"""
        return self._taskbar_trigger

    def get_taskbar_ctrl(self) -> bool:
        """查询任务栏触发是否需要 Ctrl 修饰"""
        return self._taskbar_with_ctrl

    def set_mouse_hook(self, mouse_hook):
        self.mouse_hook = mouse_hook

    def _get_theme(self) -> str:
        """向上查找 ConfigWindow 获取当前主题"""
        parent = self.parent()
        while parent:
            if hasattr(parent, "data_manager"):
                try:
                    settings: Any = parent.data_manager.get_settings()
                    return str(getattr(settings, "theme", "dark") or "dark")
                except Exception:
                    break
            parent = parent.parent()
        return "dark"

    def _show_preset_menu(self):
        """显示预设下拉菜单 — 使用项目 PopupMenu，与 command_dialog 风格一致"""
        theme = self._get_theme()
        menu = PopupMenu(theme=theme, radius=12, parent=self)

        if theme == "dark":
            item_style = scale_qss(
                "QPushButton{background:transparent;border:0px solid transparent;border-radius:4px;"
                "padding:5px 10px;margin:0px;min-height:18px;"
                "font-size:10px;text-align:left;"
                "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',sans-serif;font-weight:400;"
                "color:rgba(255,255,255,0.88);}"
                "QPushButton:hover{background:rgba(255,255,255,0.105);color:rgba(255,255,255,0.98);}"
                "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
            )
        else:
            item_style = scale_qss(
                "QPushButton{background:transparent;border:0px solid transparent;border-radius:4px;"
                "padding:5px 10px;margin:0px;min-height:18px;"
                "font-size:10px;text-align:left;"
                "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',sans-serif;font-weight:400;"
                "color:rgba(28,28,30,0.88);}"
                "QPushButton:hover{background:rgba(0,0,0,0.055);color:rgba(28,28,30,0.96);}"
                "QPushButton:pressed{background:rgba(0,0,0,0.095);}"
            )

        presets = [
            (tr("中键"), "mouse", [], "middle", []),
            (tr("右键"), "mouse", [], "right", []),
            (tr("侧键后"), "mouse", [], "x1", []),
            (tr("侧键前"), "mouse", [], "x2", []),
            (tr("Ctrl+中键"), "mouse", [], "middle", ["ctrl"]),
            (tr("Alt+中键"), "mouse", [], "middle", ["alt"]),
            (tr("Shift+中键"), "mouse", [], "middle", ["shift"]),
            (tr("Ctrl+Space"), "keyboard", ["space"], "", ["ctrl"]),
            (tr("Alt+Space"), "keyboard", ["space"], "", ["alt"]),
        ]
        for name, mode, keys, button, modifiers in presets:
            key_tuple = tuple(keys)
            modifier_tuple = tuple(modifiers)

            def _make_cb(m=mode, k=key_tuple, b=button, mod=modifier_tuple):
                def cb():
                    self.set_trigger(m, list(k), b, list(mod))

                return cb

            btn = menu.add_action(name, _make_cb())
            btn.setStyleSheet(item_style)

        menu.add_separator()

        def _make_taskbar_cb():
            def cb():
                self.set_taskbar_trigger(False)
                self.taskbar_trigger_requested.emit(False)

            return cb

        btn = menu.add_action(tr("任务栏双击"), _make_taskbar_cb())
        btn.setStyleSheet(item_style)

        pos = self.preset_btn.mapToGlobal(QPoint(0, self.preset_btn.height()))
        menu.setFixedWidth(self.preset_btn.width())
        menu.popup(pos)
        QTimer.singleShot(0, lambda m=menu, s=item_style: _reapply_item_style(m, s))
