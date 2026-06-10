"""Shared helpers for protected hotkey capture widgets."""

from hooks.key_map import VK_TO_KEY
from ui.utils.ui_scale import sp

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
    return VK_TO_KEY.get(vk, "")


def apply_recorder_display_style(display, active: bool):
    background = "rgba(74, 158, 255, 0.10)" if active else "transparent"
    display.setStyleSheet(
        f"QLineEdit {{ border: {sp(1)}px solid transparent; border-radius: {sp(4)}px; background: {background}; padding: 0 {sp(6)}px; }}"
    )
