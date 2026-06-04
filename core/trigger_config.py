"""Popup trigger configuration normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_TRIGGER_MODES = {"mouse", "keyboard", "hybrid"}
VALID_TRIGGER_BUTTONS = {"left", "right", "middle", "x1", "x2"}
VALID_TRIGGER_MODIFIERS = {"ctrl", "alt", "shift", "win"}
_MODIFIER_ALIASES = {
    "control": "ctrl",
    "cmd": "win",
    "windows": "win",
    "meta": "win",
    "super": "win",
}
_KEY_ALIASES = {
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "prtscr": "printscreen",
}
_NAMED_KEYS = {
    "space",
    "enter",
    "tab",
    "backspace",
    "esc",
    "delete",
    "insert",
    "home",
    "end",
    "pageup",
    "pagedown",
    "left",
    "right",
    "up",
    "down",
    "pause",
    "printscreen",
}


@dataclass(frozen=True)
class TriggerConfig:
    mode: str = "mouse"
    keys: list[str] = field(default_factory=list)
    button: str = "middle"
    modifiers: list[str] = field(default_factory=list)


def normalize_trigger_modifier(value: str) -> str:
    text = str(value or "").strip().lower()
    text = _MODIFIER_ALIASES.get(text, text)
    return text if text in VALID_TRIGGER_MODIFIERS else ""


def normalize_trigger_key(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = _KEY_ALIASES.get(text, text)
    if len(text) == 1 and ("a" <= text <= "z" or "0" <= text <= "9"):
        return text
    if text.startswith("f") and text[1:].isdigit():
        number = int(text[1:])
        if 1 <= number <= 24:
            return f"f{number}"
        return ""
    return text if text in _NAMED_KEYS else ""


def _dedupe_normalized(values, normalizer) -> list[str]:
    result: list[str] = []
    seen = set()
    if not isinstance(values, list | tuple | set):
        values = []
    for value in values:
        normalized = normalizer(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def normalize_trigger_config(
    mode: str = "mouse",
    keys: list[str] | None = None,
    button: str = "middle",
    modifiers: list[str] | None = None,
    *,
    fill_defaults: bool = False,
    default_modifiers: list[str] | None = None,
) -> TriggerConfig:
    normalized_mode = str(mode or "mouse").strip().lower()
    if normalized_mode not in VALID_TRIGGER_MODES:
        normalized_mode = "mouse"

    normalized_keys = _dedupe_normalized(keys or [], normalize_trigger_key)
    normalized_modifiers = _dedupe_normalized(modifiers or [], normalize_trigger_modifier)
    normalized_button = str(button or "").strip().lower()
    if normalized_button not in VALID_TRIGGER_BUTTONS:
        normalized_button = "middle" if fill_defaults else ""

    if normalized_mode == "mouse":
        normalized_keys = []
        if fill_defaults and not normalized_button:
            normalized_button = "middle"
    elif normalized_mode == "keyboard":
        normalized_button = ""
        if fill_defaults and not normalized_keys:
            normalized_mode = "mouse"
            normalized_button = "middle"
            normalized_modifiers = _dedupe_normalized(default_modifiers or [], normalize_trigger_modifier)
    elif normalized_mode == "hybrid" and fill_defaults and (not normalized_keys or not normalized_button):
        normalized_mode = "mouse"
        normalized_keys = []
        normalized_button = "middle"
        normalized_modifiers = _dedupe_normalized(default_modifiers or [], normalize_trigger_modifier)

    if fill_defaults:
        fallback_modifiers = _dedupe_normalized(default_modifiers or [], normalize_trigger_modifier)
        alt_only = set(normalized_modifiers) == {"alt"}
        unsafe_left_right = normalized_button in {"left", "right"} and not normalized_modifiers
        unsafe_keyboard = normalized_mode == "keyboard" and not normalized_modifiers
        unsafe_hybrid = normalized_mode == "hybrid" and unsafe_left_right
        unsafe_alt_only = alt_only and (bool(normalized_keys) or normalized_button in {"left", "right", "middle"})
        if unsafe_left_right or unsafe_keyboard or unsafe_hybrid or unsafe_alt_only:
            normalized_mode = "mouse"
            normalized_keys = []
            normalized_button = "middle"
            normalized_modifiers = fallback_modifiers

    return TriggerConfig(
        mode=normalized_mode,
        keys=normalized_keys,
        button=normalized_button,
        modifiers=normalized_modifiers,
    )


def normalize_trigger_settings(settings) -> dict[str, object]:
    """Return normalized popup trigger fields for an AppSettings-like object."""
    normal = normalize_trigger_config(
        getattr(settings, "popup_trigger_mode", "mouse"),
        getattr(settings, "popup_trigger_keys", []),
        getattr(settings, "popup_trigger_button", "middle"),
        getattr(settings, "popup_trigger_modifiers", []),
        fill_defaults=True,
    )
    special = normalize_trigger_config(
        getattr(settings, "popup_special_trigger_mode", "mouse"),
        getattr(settings, "popup_special_trigger_keys", []),
        getattr(settings, "popup_special_trigger_button", "middle"),
        getattr(settings, "popup_special_trigger_modifiers", ["ctrl"]),
        fill_defaults=True,
        default_modifiers=["ctrl"],
    )
    return {
        "popup_trigger_mode": normal.mode,
        "popup_trigger_keys": normal.keys,
        "popup_trigger_button": normal.button,
        "popup_trigger_modifiers": normal.modifiers,
        "popup_special_trigger_mode": special.mode,
        "popup_special_trigger_keys": special.keys,
        "popup_special_trigger_button": special.button,
        "popup_special_trigger_modifiers": special.modifiers,
    }


def trigger_config_to_hotkey(mode: str, keys: list[str], modifiers: list[str]) -> str:
    config = normalize_trigger_config(mode, keys, "", modifiers)
    if config.mode != "keyboard" or not config.keys:
        return ""
    return "+".join([*config.modifiers, *config.keys])
