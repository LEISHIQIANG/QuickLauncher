"""Shared keyboard name to Windows virtual-key mapping."""

from __future__ import annotations

import re

_GENERIC_VK_RE = re.compile(r"^vk_([0-9a-f]{2})$")
MODIFIER_KEY_NAMES = {
    "alt",
    "control",
    "ctrl",
    "lalt",
    "lctrl",
    "lshift",
    "lwin",
    "menu",
    "meta",
    "ralt",
    "rctrl",
    "rshift",
    "rwin",
    "shift",
    "super",
    "win",
    "windows",
    "cmd",
}

KEY_TO_VK: dict[str, int] = {
    **{chr(code).lower(): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(num): ord(str(num)) for num in range(10)},
    **{f"f{num}": 0x70 + num - 1 for num in range(1, 25)},
    "backspace": 0x08,
    "tab": 0x09,
    "clear": 0x0C,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "select": 0x29,
    "print": 0x2A,
    "execute": 0x2B,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "help": 0x2F,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    "sleep": 0x5F,
    **{f"num{num}": 0x60 + num for num in range(10)},
    "multiply": 0x6A,
    "add": 0x6B,
    "separator": 0x6C,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "browserback": 0xA6,
    "browserforward": 0xA7,
    "browserrefresh": 0xA8,
    "browserstop": 0xA9,
    "browsersearch": 0xAA,
    "browserfavorites": 0xAB,
    "browserhome": 0xAC,
    "volumemute": 0xAD,
    "volumedown": 0xAE,
    "volumeup": 0xAF,
    "medianext": 0xB0,
    "mediaprev": 0xB1,
    "mediastop": 0xB2,
    "mediaplay": 0xB3,
    "launchmail": 0xB4,
    "launchmedia": 0xB5,
    "launchapp1": 0xB6,
    "launchapp2": 0xB7,
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
    "processkey": 0xE5,
    "packet": 0xE7,
    "attn": 0xF6,
    "crsel": 0xF7,
    "exsel": 0xF8,
    "ereof": 0xF9,
    "play": 0xFA,
    "zoom": 0xFB,
    "noname": 0xFC,
    "pa1": 0xFD,
    "oemclear": 0xFE,
}

KEY_TO_VK.update(
    {
        "return": KEY_TO_VK["enter"],
        "control": KEY_TO_VK["ctrl"],
        "menu": KEY_TO_VK["alt"],
        "back": KEY_TO_VK["backspace"],
        "escape": KEY_TO_VK["esc"],
        "caps": KEY_TO_VK["capslock"],
        "del": KEY_TO_VK["delete"],
        "ins": KEY_TO_VK["insert"],
        "pgup": KEY_TO_VK["pageup"],
        "pgdn": KEY_TO_VK["pagedown"],
        "prtscr": KEY_TO_VK["printscreen"],
        "win": KEY_TO_VK["lwin"],
        "windows": KEY_TO_VK["lwin"],
        "cmd": KEY_TO_VK["lwin"],
        "meta": KEY_TO_VK["lwin"],
        "super": KEY_TO_VK["lwin"],
        "numpad0": KEY_TO_VK["num0"],
        "numpad1": KEY_TO_VK["num1"],
        "numpad2": KEY_TO_VK["num2"],
        "numpad3": KEY_TO_VK["num3"],
        "numpad4": KEY_TO_VK["num4"],
        "numpad5": KEY_TO_VK["num5"],
        "numpad6": KEY_TO_VK["num6"],
        "numpad7": KEY_TO_VK["num7"],
        "numpad8": KEY_TO_VK["num8"],
        "numpad9": KEY_TO_VK["num9"],
        "mute": KEY_TO_VK["volumemute"],
        "playpause": KEY_TO_VK["mediaplay"],
    }
)

_CANONICAL_KEYS = [
    *(chr(code).lower() for code in range(ord("A"), ord("Z") + 1)),
    *(str(num) for num in range(10)),
    *(f"f{num}" for num in range(1, 25)),
    *(
        key
        for key in KEY_TO_VK
        if key
        not in {
            "return",
            "control",
            "menu",
            "back",
            "escape",
            "caps",
            "del",
            "ins",
            "pgup",
            "pgdn",
            "prtscr",
            "win",
            "windows",
            "cmd",
            "meta",
            "super",
            "numpad0",
            "numpad1",
            "numpad2",
            "numpad3",
            "numpad4",
            "numpad5",
            "numpad6",
            "numpad7",
            "numpad8",
            "numpad9",
            "mute",
            "playpause",
        }
    ),
]

VK_TO_KEY: dict[int, str] = {}
for _key in _CANONICAL_KEYS:
    VK_TO_KEY.setdefault(KEY_TO_VK[_key], _key)

KEY_DISPLAY_NAMES = {
    "esc": "Esc",
    "capslock": "Caps Lock",
    "printscreen": "Print Screen",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "numlock": "Num Lock",
    "scrolllock": "Scroll Lock",
    "browserback": "Browser Back",
    "browserforward": "Browser Forward",
    "browserrefresh": "Browser Refresh",
    "browserstop": "Browser Stop",
    "browsersearch": "Browser Search",
    "browserfavorites": "Browser Favorites",
    "browserhome": "Browser Home",
    "volumemute": "Volume Mute",
    "volumedown": "Volume Down",
    "volumeup": "Volume Up",
    "medianext": "Media Next",
    "mediaprev": "Media Previous",
    "mediastop": "Media Stop",
    "mediaplay": "Media Play/Pause",
    "launchmail": "Launch Mail",
    "launchmedia": "Launch Media",
    "launchapp1": "Launch App 1",
    "launchapp2": "Launch App 2",
}


def key_to_vk(key: str) -> int:
    """Return a Windows virtual-key code for a normalized key name."""
    text = str(key or "").strip().lower()
    if text in KEY_TO_VK:
        return KEY_TO_VK[text]
    match = _GENERIC_VK_RE.fullmatch(text)
    if not match:
        return 0
    value = int(match.group(1), 16)
    return value if 0 < value <= 0xFF else 0


def vk_to_key(vk_code: int) -> str:
    """Return a stable key name, retaining unknown physical VKs generically."""
    vk = int(vk_code or 0)
    if vk <= 0 or vk > 0xFF:
        return ""
    return VK_TO_KEY.get(vk, f"vk_{vk:02x}")


def key_display_name(key: str) -> str:
    text = str(key or "").strip().lower()
    if not text:
        return ""
    if len(text) == 1:
        return text.upper()
    if text.startswith("f") and text[1:].isdigit():
        return text.upper()
    if text.startswith("num") and text[3:].isdigit():
        return f"Num {text[3:]}"
    match = _GENERIC_VK_RE.fullmatch(text)
    if match:
        return f"VK 0x{match.group(1).upper()}"
    return KEY_DISPLAY_NAMES.get(text, text.replace("_", " ").title())
