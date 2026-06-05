"""Shared keyboard name to Windows virtual-key mapping."""

from __future__ import annotations

KEY_TO_VK: dict[str, int] = {
    **{chr(code).lower(): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(num): ord(str(num)) for num in range(10)},
    **{f"f{num}": 0x70 + num - 1 for num in range(1, 25)},
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "back": 0x08,
    "esc": 0x1B,
    "escape": 0x1B,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "pause": 0x13,
    "printscreen": 0x2C,
    "prtscr": 0x2C,
    "volumeup": 0xAF,
    "volumedown": 0xAE,
    "volumemute": 0xAD,
    "mute": 0xAD,
    "medianext": 0xB0,
    "mediaprev": 0xB1,
    "mediastop": 0xB2,
    "mediaplay": 0xB3,
    "playpause": 0xB3,
}

VK_TO_KEY: dict[int, str] = {}
for _key, _vk in KEY_TO_VK.items():
    VK_TO_KEY.setdefault(_vk, _key)


def key_to_vk(key: str) -> int:
    """Return a Windows virtual-key code for a normalized key name."""
    return KEY_TO_VK.get(str(key or "").strip().lower(), 0)
