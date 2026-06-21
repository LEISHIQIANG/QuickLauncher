"""Hotkey edit dialog."""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
import ctypes
import logging
import os

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from hooks.key_map import key_display_name
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
    QRectF,
    QSizePolicy,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.design_tokens import StatusScale
from ui.styles.style import Glassmorphism
from ui.tooltip_helper import install_tooltip
from ui.utils.pixel_snap import create_pixmap
from ui.utils.ui_scale import font_px, scale_qss, sp

from .base_dialog import BaseDialog
from .hotkey_capture_helpers import (
    CAPTURE_TIMEOUT_MS,
    KeyboardStatePoller,
    apply_recorder_display_style,
    generic_modifiers_from_capture,
    key_name_from_vk,
    side_modifiers_from_capture,
)
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_compact_checkbox_stylesheet, get_radio_stylesheet, get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)

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

    _native_capture_result = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modifiers = []
        self.keys = []
        self.advanced_sides = False
        self._recording = False
        self._native_capture_active = False
        self._native_capture_available = True
        self._capture_dll = None
        self._capture_hook_installed_by_us = False
        self._capture_session = 0
        self._keyboard_state_poller = KeyboardStatePoller(
            self,
            self._handle_state_poll_result,
            log_label="hotkey",
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(6))

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText("点击后直接按下快捷键")
        self.display.setFocusPolicy(QtCompat.StrongFocus)
        self.display.setFixedHeight(sp(24))
        apply_recorder_display_style(self.display, False)
        layout.addWidget(self.display, 1)

        self.record_btn = QPushButton("录制")
        self.record_btn.setFixedWidth(sp(52))
        self.record_btn.setFixedHeight(sp(24))
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedHeight(sp(24))
        self.clear_btn.clicked.connect(self.clear_hotkey)
        layout.addWidget(self.clear_btn)

        self.setFocusProxy(self.display)
        self.display.installEventFilter(self)
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._on_capture_timeout)
        self._native_capture_result.connect(self._handle_native_capture_signal)

    def eventFilter(self, obj, event):
        if obj is self.display:
            if event.type() == QEvent.MouseButtonPress:
                self.start_recording()
                return False
            if event.type() == QEvent.KeyPress:
                return True
        return super().eventFilter(obj, event)

    def _toggle_recording(self):
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if self._recording:
            return
        self.modifiers = []
        self.keys = []
        self._refresh_display()
        self._recording = True
        self._capture_session += 1
        self._keyboard_state_poller.start()
        if self._start_native_capture():
            self._set_recording_ui(True)
            return
        self._finish_native_capture(stop_native=True)
        self._recording = False
        self._set_recording_ui(False)
        self.display.setPlaceholderText("hooks.dll 需要更新后才能录制")

    def stop_recording(self):
        self._finish_native_capture(stop_native=True)
        self._recording = False
        self._set_recording_ui(False)

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

            self._capture_hook_installed_by_us = False
            keyboard_ready, installed_temporarily = dll.rearm_keyboard_hook_for_capture()
            if not keyboard_ready:
                return False
            self._capture_hook_installed_by_us = installed_temporarily
            session = self._capture_session if capture_session is None else int(capture_session)

            if not dll.start_protected_chord_capture(
                lambda input_code, modifiers, side_modifiers: self._on_native_capture(
                    session,
                    input_code,
                    modifiers,
                    side_modifiers,
                ),
                keyboard=True,
                mouse_buttons=False,
                include_injected=True,
                timeout_ms=CAPTURE_TIMEOUT_MS,
                owner=self,
            ):
                self._cleanup_temporary_hook()
                return False

            self._native_capture_active = True
            self._capture_timer.start(CAPTURE_TIMEOUT_MS + 500)
            return True
        except Exception as exc:
            logger.debug("启动受保护快捷键录制失败: %s", exc, exc_info=True)
            self._native_capture_available = False
            self._native_capture_active = False
            self._cleanup_temporary_hook()
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
        if capture_session is not None and (int(capture_session) != self._capture_session or not self._recording):
            logger.debug(
                "忽略过期快捷键捕获回调: widget=%s session=%s current_session=%s recording=%s",
                hex(id(self)),
                capture_session,
                self._capture_session,
                self._recording,
            )
            return
        if input_code > 0:
            key_name = key_name_from_vk(input_code)
            if key_name and key_name not in self.keys:
                self.keys.append(key_name)
            self.modifiers = self._merge_modifiers(
                self.modifiers,
                self._modifiers_from_capture(modifiers, side_modifiers),
            )
            self._refresh_display()
            return

        self.modifiers = self._merge_modifiers(
            self.modifiers,
            self._modifiers_from_capture(modifiers, side_modifiers),
        )
        # input_code=0 表示本次组合的全部按键已经松开。
        self._finish_native_capture(stop_native=True)
        self._recording = False
        self._set_recording_ui(False)
        self._refresh_display()
        logger.debug(
            "快捷键捕获完成: widget=%s keys=%s modifiers=%s text=%r",
            hex(id(self)),
            self.keys,
            self.modifiers,
            self.display.text(),
        )

    def _handle_state_poll_result(self, input_code: int, modifiers: int, side_modifiers: int):
        if not self._recording:
            return
        self._handle_native_capture_result(input_code, modifiers, side_modifiers)

    def _on_capture_timeout(self):
        if self._native_capture_active:
            logger.debug("快捷键捕获超时: widget=%s", hex(id(self)))
        self.stop_recording()

    def _finish_native_capture(self, stop_native: bool):
        self._keyboard_state_poller.stop()
        if self._capture_timer.isActive():
            self._capture_timer.stop()
        dll = self._capture_dll
        if dll is not None and stop_native and self._native_capture_active:
            try:
                dll.stop_protected_chord_capture(owner=self)
            except Exception as exc:
                logger.debug("停止受保护快捷键录制失败: %s", exc, exc_info=True)
        if stop_native:
            self._cleanup_temporary_hook()
        self._native_capture_active = False

    def _cleanup_temporary_hook(self):
        dll = self._capture_dll
        if dll is not None and self._capture_hook_installed_by_us:
            try:
                dll.uninstall_keyboard_hook()
            except Exception as exc:
                logger.debug("卸载录制临时键盘钩子失败: %s", exc, exc_info=True)
        self._capture_hook_installed_by_us = False

    def _set_recording_ui(self, native_active: bool):
        if self._recording:
            self.record_btn.setText("停止")
            if native_active:
                self.display.setPlaceholderText("录制中，请按下组合并全部松开")
                apply_recorder_display_style(self.display, True)
            else:
                self.display.setPlaceholderText("按下快捷键")
                apply_recorder_display_style(self.display, False)
        else:
            self.record_btn.setText("录制")
            self.display.setPlaceholderText("点击后直接按下快捷键")
            apply_recorder_display_style(self.display, False)

    def set_advanced_sides(self, enabled: bool):
        self.advanced_sides = enabled
        self._normalize_modifiers()
        self._refresh_display()

    def set_hotkey(self, hotkey: str, modifiers: list, key: str, keys: list[str] | None = None):
        del hotkey
        self.modifiers = list(modifiers or [])
        self.keys = list(keys or [])
        if not self.keys and key:
            self.keys = [key]
        self._normalize_modifiers()
        self._refresh_display()

    def clear_hotkey(self):
        self.stop_recording()
        self.modifiers = []
        self.keys = []
        self._refresh_display()

    def get_modifiers(self) -> list:
        return list(self.modifiers)

    def get_key(self) -> str:
        return self.keys[0] if self.keys else ""

    def get_keys(self) -> list[str]:
        return list(self.keys)

    def get_hotkey_string(self) -> str:
        parts = [self._label_for_modifier(m) for m in self.modifiers]
        parts.extend(self._label_for_key(key) for key in self.keys)
        return " + ".join(parts)

    def keyPressEvent(self, event):
        key_name = self._key_name(event)
        if not key_name:
            return
        if key_name in {
            "ctrl",
            "alt",
            "shift",
            "win",
            "lctrl",
            "rctrl",
            "lalt",
            "ralt",
            "lshift",
            "rshift",
            "lwin",
            "rwin",
        }:
            return
        self.modifiers = self._current_modifiers(event)
        self.keys = [key_name]
        self._refresh_display()
        if self._recording and not self._native_capture_active:
            self.stop_recording()

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

    def _modifiers_from_capture(self, modifiers: int, side_modifiers: int) -> list:
        if self.advanced_sides:
            return side_modifiers_from_capture(side_modifiers)
        return generic_modifiers_from_capture(modifiers)

    @staticmethod
    def _merge_modifiers(existing: list[str], incoming: list[str]) -> list[str]:
        order = ("ctrl", "alt", "shift", "win", "lctrl", "rctrl", "lalt", "ralt", "lshift", "rshift", "lwin", "rwin")
        values = set(existing) | set(incoming)
        return [name for name in order if name in values]

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
        return key_display_name(key)

    def _key_name(self, event) -> str:
        key = event.key()
        text = event.text()
        qt = Qt

        special = {
            qt.Key_Escape: "esc",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Tab: "tab",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Backtab: "tab",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Backspace: "backspace",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Return: "enter",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Enter: "enter",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Insert: "insert",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Delete: "delete",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Pause: "pause",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Print: "printscreen",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Home: "home",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_End: "end",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Left: "left",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Up: "up",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Right: "right",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Down: "down",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_PageUp: "pageup",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_PageDown: "pagedown",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Space: "space",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Control: "ctrl",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Shift: "shift",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Alt: "alt",  # type: ignore[unused-ignore, attr-defined]
            qt.Key_Meta: "win",  # type: ignore[unused-ignore, attr-defined]
        }
        if key in special:
            return special[key]
        if qt.Key_F1 <= key <= qt.Key_F35:  # type: ignore[unused-ignore, attr-defined]
            return f"f{key - qt.Key_F1 + 1}"  # type: ignore[unused-ignore, attr-defined]
        if qt.Key_A <= key <= qt.Key_Z:  # type: ignore[unused-ignore, attr-defined]
            return chr(ord("a") + key - qt.Key_A)  # type: ignore[unused-ignore, attr-defined]
        if qt.Key_0 <= key <= qt.Key_9:  # type: ignore[unused-ignore, attr-defined]
            return chr(ord("0") + key - qt.Key_0)  # type: ignore[unused-ignore, attr-defined]
        if text and text.strip():
            value = text.lower()
            if len(value) == 1 and ord(value) >= 32:
                return value  # type: ignore[no-any-return]
        native_vk = event.nativeVirtualKey() if hasattr(event, "nativeVirtualKey") else 0
        if 0x60 <= native_vk <= 0x69:
            return f"num{native_vk - 0x60}"
        return ""


class HotkeyDialog(BaseDialog):
    """Hotkey edit dialog."""

    def __init__(self, parent=None, shortcut: ShortcutItem = None):  # type: ignore[assignment]
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.HOTKEY)
        self._custom_icon_path = self.shortcut.icon_path or ""

        self.setWindowTitle(tr("编辑快捷键") if shortcut else tr("添加快捷键"))
        self.setMinimumWidth(sp(420))

        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        from .base_dialog import BaseDialog

        if BaseDialog._is_compiled():
            return
        try:
            pixmap = QPixmap(sp(64), sp(64))
            pixmap.setDevicePixelRatio(1.0)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                painter.setRenderHint(QtCompat.HighQualityAntialiasing)
                painter.setFont(QFont("Segoe UI Symbol", font_px(38)))
                painter.setPen(QColor(StatusScale.success).lighter(130))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌘")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception as exc:
            logger.debug("设置窗口图标失败: %s", exc, exc_info=True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(sp(6))
        layout.setContentsMargins(sp(8), sp(8), sp(8), sp(8))

        title_label = QLabel("编辑快捷键" if self.shortcut.name else "添加快捷键")
        title_label.setStyleSheet(scale_qss("font-size: 12px; font-weight: 400; color: gray;"))
        layout.addWidget(title_label)

        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(sp(6))
        basic_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)
        layout.addWidget(basic_group)

        hotkey_group = QGroupBox("快捷键")
        hotkey_layout = QVBoxLayout(hotkey_group)
        hotkey_layout.setSpacing(sp(6))
        hotkey_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.hotkey_input = HotkeyRecorderWidget()
        hotkey_layout.addWidget(self.hotkey_input)

        option_row = QHBoxLayout()
        option_row.setSpacing(sp(8))
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
        trigger_layout.setSpacing(sp(12))
        trigger_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))
        self.trigger_immediate_rb = QRadioButton("无延迟发送")
        install_tooltip(self.trigger_immediate_rb, "点击图标后立刻发送这组按键，适合不需要回到原窗口的操作")
        self.trigger_after_close_rb = QRadioButton("窗口淡出后发送")
        install_tooltip(
            self.trigger_after_close_rb, "先关闭快捷启动面板并把焦点还给原来的窗口，再发送这组按键，适合控制原窗口"
        )
        trigger_layout.addWidget(self.trigger_immediate_rb)
        trigger_layout.addWidget(self.trigger_after_close_rb)
        trigger_layout.addStretch()
        self.trigger_group_btn = QButtonGroup(self)
        self.trigger_group_btn.addButton(self.trigger_immediate_rb)
        self.trigger_group_btn.addButton(self.trigger_after_close_rb)
        layout.addWidget(trigger_group)

        test_row = QHBoxLayout()
        test_row.setSpacing(sp(6))
        self._test_btn = QPushButton("测试发送")
        self._test_btn.clicked.connect(self._test_hotkey)
        test_row.addWidget(self._test_btn)
        self.test_result_label = QLabel("")
        test_row.addWidget(self.test_result_label, 1)
        layout.addLayout(test_row)

        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), 0, sp(6), sp(6))
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        icon_layout.addWidget(self.icon_preview)

        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(sp(6))
        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(sp(6))
        self._browse_icon_btn = QPushButton("选择图标...")
        self._browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(self._browse_icon_btn)
        self._clear_icon_btn = QPushButton("清除")
        self._clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(self._clear_icon_btn)
        icon_btn_layout.addStretch()
        self.invert_light_cb = QCheckBox("浅色反转")
        self.invert_dark_cb = QCheckBox("深色反转")
        icon_btn_layout.addWidget(self.invert_light_cb)
        icon_btn_layout.addWidget(self.invert_dark_cb)
        icon_right_layout.addLayout(icon_btn_layout)
        icon_layout.addLayout(icon_right_layout, 1)
        layout.addWidget(icon_group)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(sp(8))
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedSize(sp(80), sp(32))
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setFixedSize(sp(80), sp(32))
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
        self.setStyleSheet(
            base_style
            + scale_qss(
                f"""
            QDialog {{ background: transparent; border: none; border-radius: 0; }}
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
            )
        )
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [
            self.hotkey_input.record_btn,
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
        invert_cb_style = get_compact_checkbox_stylesheet(theme)
        self.invert_light_cb.setStyleSheet(invert_cb_style)
        self.invert_dark_cb.setStyleSheet(invert_cb_style)

        if theme == "dark":
            self.icon_preview.setStyleSheet(
                scale_qss(
                    "QLabel { background-color: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; }"
                )
            )
            self.conflict_label.setStyleSheet(scale_qss("color: rgba(255,255,255,0.62); font-size: 11px;"))
            self.test_result_label.setStyleSheet(scale_qss("color: rgba(255,255,255,0.62); font-size: 11px;"))
        else:
            self.icon_preview.setStyleSheet(
                scale_qss(
                    "QLabel { background-color: rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); border-radius: 10px; }"
                )
            )
            self.conflict_label.setStyleSheet(scale_qss("color: rgba(0,0,0,0.55); font-size: 11px;"))
            self.test_result_label.setStyleSheet(scale_qss("color: rgba(0,0,0,0.55); font-size: 11px;"))

    def _load_data(self):
        self.name_edit.setText(self.shortcut.name or "")
        modifiers = self.shortcut.hotkey_modifiers or []
        has_lr = any(m in _LEFT_RIGHT_LABELS for m in modifiers)
        self.advanced_sides_cb.setChecked(has_lr)
        self.hotkey_input.set_advanced_sides(has_lr)
        self.hotkey_input.set_hotkey(
            self.shortcut.hotkey or "",
            modifiers,
            self.shortcut.hotkey_key or "",
            getattr(self.shortcut, "hotkey_keys", []),
        )
        if getattr(self.shortcut, "trigger_mode", "immediate") == "after_close":
            self.trigger_after_close_rb.setChecked(True)
        else:
            self.trigger_immediate_rb.setChecked(True)
        if self._custom_icon_path:
            self.icon_path_edit.setText(self._custom_icon_path)
        self.invert_light_cb.setChecked(self.shortcut.icon_invert_light)
        self.invert_dark_cb.setChecked(self.shortcut.icon_invert_dark)
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
        self.test_result_label.setText(tr("发送中..."))

        from core.background_tasks import start_background_thread

        def _do():
            try:
                from core import ShortcutExecutor

                success, error = ShortcutExecutor.execute(preview)
                text = "发送成功" if success else f"发送失败: {error}"
            except Exception as e:
                text = f"发送失败: {e}"
            from qt_compat import QTimer

            QTimer.singleShot(0, lambda: self._on_test_hotkey_done(text))

        self._test_hotkey_thread = start_background_thread(
            name="HotkeyDialogTest",
            target=_do,
            owner=self,
        )

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
        shortcut.hotkey_keys = self.hotkey_input.get_keys()
        shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        return shortcut

    def _update_icon_preview(self):
        pixmap = None
        if self._custom_icon_path and os.path.exists(self._custom_icon_path):
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.from_file(self._custom_icon_path, 40)
            except Exception as exc:
                logger.debug("加载自定义图标失败: %s", exc, exc_info=True)
        if not pixmap or pixmap.isNull():
            pixmap = self._create_hotkey_icon(40)
        _current_theme = getattr(self, "theme", "dark")
        _need_invert = (
            self.invert_light_cb.isChecked() if _current_theme == "light" else self.invert_dark_cb.isChecked()
        )
        if _need_invert and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor

            pixmap = IconExtractor.invert_pixmap(pixmap)
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.icon_preview.setPixmap(pixmap)

    def _create_hotkey_icon(self, size: int) -> QPixmap:
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)
            painter.setBrush(QColor(StatusScale.info))
            painter.setPen(QtCompat.NoPen)
            margin = size // 8
            painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)
            painter.setPen(QColor(QtCompat.white))
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
            self._update_icon_preview()

    def _clear_icon(self):
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
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
                result = ThemedMessageBox.question(
                    self, tr("快捷键冲突"), tr("{conflict}\n\n是否仍要使用此快捷键？", conflict=conflict_desc)
                )
                if not result:
                    return
        except Exception as exc:
            logger.debug("检查快捷键冲突失败: %s", exc, exc_info=True)
        self.accept()

    def accept(self):
        if hasattr(self, "hotkey_input"):
            self.hotkey_input.stop_recording()
        super().accept()

    def reject(self):
        if hasattr(self, "hotkey_input"):
            self.hotkey_input.stop_recording()
        super().reject()

    def get_shortcut(self) -> ShortcutItem:
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.hotkey = self.hotkey_input.get_hotkey_string()
        self.shortcut.hotkey_modifiers = self.hotkey_input.get_modifiers()
        self.shortcut.hotkey_key = self.hotkey_input.get_key()
        self.shortcut.hotkey_keys = self.hotkey_input.get_keys()
        self.shortcut.trigger_mode = "after_close" if self.trigger_after_close_rb.isChecked() else "immediate"
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.type = ShortcutType.HOTKEY
        self.shortcut.icon_invert_light = self.invert_light_cb.isChecked()
        self.shortcut.icon_invert_dark = self.invert_dark_cb.isChecked()
        return self.shortcut
