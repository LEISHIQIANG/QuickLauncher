"""Shared helpers for protected hotkey capture widgets."""

import ctypes
import logging

from hooks.key_map import vk_to_key
from qt_compat import QTimer
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)

SIDE_MODIFIER_BITS = {
    "lshift": 0x0001,
    "rshift": 0x0002,
    "lctrl": 0x0004,
    "rctrl": 0x0008,
    "lalt": 0x0010,
    "ralt": 0x0020,
    "lwin": 0x0040,
    "rwin": 0x0080,
}
SIDE_MODIFIER_ORDER = ("lctrl", "rctrl", "lalt", "ralt", "lshift", "rshift", "lwin", "rwin")

CAPTURE_MOD_ALT = 1
CAPTURE_MOD_CTRL = 2
CAPTURE_MOD_SHIFT = 4
CAPTURE_MOD_WIN = 8
CAPTURE_TIMEOUT_MS = 10000
KEYBOARD_POLL_INTERVAL_MS = 5

_GENERIC_MODIFIER_VKS = {
    0x10: CAPTURE_MOD_SHIFT,
    0x11: CAPTURE_MOD_CTRL,
    0x12: CAPTURE_MOD_ALT,
}
_SIDE_MODIFIER_VKS = {
    0xA0: ("lshift", CAPTURE_MOD_SHIFT),
    0xA1: ("rshift", CAPTURE_MOD_SHIFT),
    0xA2: ("lctrl", CAPTURE_MOD_CTRL),
    0xA3: ("rctrl", CAPTURE_MOD_CTRL),
    0xA4: ("lalt", CAPTURE_MOD_ALT),
    0xA5: ("ralt", CAPTURE_MOD_ALT),
    0x5B: ("lwin", CAPTURE_MOD_WIN),
    0x5C: ("rwin", CAPTURE_MOD_WIN),
}
_SIDE_NAME_TO_BIT = {
    "lshift": 0x0001,
    "rshift": 0x0002,
    "lctrl": 0x0004,
    "rctrl": 0x0008,
    "lalt": 0x0010,
    "ralt": 0x0020,
    "lwin": 0x0040,
    "rwin": 0x0080,
}
_MODIFIER_VKS = set(_GENERIC_MODIFIER_VKS) | set(_SIDE_MODIFIER_VKS)
_POLLABLE_VKS = tuple(range(0x08, 0xFF))

VK_TO_KEY_NAME = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x13: "pause",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2C: "printscreen",
    0x2D: "insert",
    0x2E: "delete",
    0x60: "num0",
    0x61: "num1",
    0x62: "num2",
    0x63: "num3",
    0x64: "num4",
    0x65: "num5",
    0x66: "num6",
    0x67: "num7",
    0x68: "num8",
    0x69: "num9",
    0x6A: "multiply",
    0x6B: "add",
    0x6D: "subtract",
    0x6E: "decimal",
    0x6F: "divide",
    0x90: "numlock",
    0x91: "scrolllock",
    0xAD: "volumemute",
    0xAE: "volumedown",
    0xAF: "volumeup",
    0xB0: "medianext",
    0xB1: "mediaprev",
    0xB2: "mediastop",
    0xB3: "mediaplay",
    0xBA: ";",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: "/",
    0xC0: "`",
    0xDB: "[",
    0xDC: "\\",
    0xDD: "]",
    0xDE: "'",
}


def generic_modifiers_from_capture(modifiers: int) -> list[str]:
    mods = []
    if modifiers & CAPTURE_MOD_CTRL:
        mods.append("ctrl")
    if modifiers & CAPTURE_MOD_ALT:
        mods.append("alt")
    if modifiers & CAPTURE_MOD_SHIFT:
        mods.append("shift")
    if modifiers & CAPTURE_MOD_WIN:
        mods.append("win")
    return mods


def side_modifiers_from_capture(side_modifiers: int) -> list[str]:
    return [name for name in SIDE_MODIFIER_ORDER if side_modifiers & SIDE_MODIFIER_BITS[name]]


def key_name_from_vk(vk_code: int) -> str:
    vk = int(vk_code or 0)
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x70 + 1}"
    if vk in VK_TO_KEY_NAME:
        return VK_TO_KEY_NAME[vk]
    return vk_to_key(vk)


class KeyboardStatePoller:
    """Fallback chord capture for environments where WH_KEYBOARD_LL is silent."""

    def __init__(self, parent, callback, *, log_label: str):
        self._callback = callback
        self._log_label = log_label
        self._timer = QTimer(parent)
        self._timer.setInterval(KEYBOARD_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._previous = set()  # type: ignore[var-annotated]
        self._preexisting = set()  # type: ignore[var-annotated]
        self._captured = set()  # type: ignore[var-annotated]
        self._started = False
        self._seen_modifiers = 0
        self._seen_side_modifiers = 0

    def start(self):
        current = self._pressed_vks()
        self._previous = current
        self._preexisting = set(current)
        self._captured.clear()
        self._started = False
        self._seen_modifiers = 0
        self._seen_side_modifiers = 0
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._previous.clear()
        self._preexisting.clear()
        self._captured.clear()
        self._started = False

    def is_active(self) -> bool:
        return self._timer.isActive()

    @staticmethod
    def _pressed_vks() -> set[int]:
        try:
            get_state = ctypes.windll.user32.GetAsyncKeyState
            return {vk for vk in _POLLABLE_VKS if get_state(vk) & 0x8000}
        except Exception:
            return set()

    @staticmethod
    def _modifier_state(current: set[int]) -> tuple[int, int]:
        modifiers = 0
        side_modifiers = 0
        for vk, bit in _GENERIC_MODIFIER_VKS.items():
            if vk in current:
                modifiers |= bit
        for vk, (name, bit) in _SIDE_MODIFIER_VKS.items():
            if vk in current:
                modifiers |= bit
                side_modifiers |= _SIDE_NAME_TO_BIT[name]
        return modifiers, side_modifiers

    def _poll(self):
        if not self._timer.isActive():
            return
        current = self._pressed_vks()
        released_preexisting = self._preexisting - current
        if released_preexisting:
            self._preexisting.difference_update(released_preexisting)

        effective_current = current - self._preexisting
        new_down = effective_current - self._previous
        modifiers, side_modifiers = self._modifier_state(effective_current)
        self._seen_modifiers |= modifiers
        self._seen_side_modifiers |= side_modifiers

        for vk in sorted(new_down):
            if vk in _MODIFIER_VKS:
                self._captured.add(vk)
                continue
            if not key_name_from_vk(vk):
                continue
            self._captured.add(vk)
            self._started = True
            logger.debug(
                "%s 键盘状态后备捕获: input=%s modifiers=%s side_modifiers=%s",
                self._log_label,
                vk,
                modifiers,
                side_modifiers,
            )
            self._callback(vk, modifiers, side_modifiers)

        self._previous = current
        if self._started and not (self._captured & current):
            seen_modifiers = self._seen_modifiers
            seen_side_modifiers = self._seen_side_modifiers
            logger.debug(
                "%s 键盘状态后备完成: modifiers=%s side_modifiers=%s",
                self._log_label,
                seen_modifiers,
                seen_side_modifiers,
            )
            self.stop()
            self._callback(0, seen_modifiers, seen_side_modifiers)


def apply_recorder_display_style(display, active: bool):
    background = "rgba(74, 158, 255, 0.10)" if active else "transparent"
    display.setStyleSheet(
        f"QLineEdit {{ border: {sp(1)}px solid transparent; border-radius: {sp(4)}px; background: {background}; padding: 0 {sp(6)}px; }}"
    )
