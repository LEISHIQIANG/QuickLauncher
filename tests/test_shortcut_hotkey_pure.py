"""Tests for shortcut_hotkey.py pure logic functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestVkFromKey:
    """Cover HotkeyExecutionMixin._vk_from_key pure mapping logic."""

    @staticmethod
    def _call(key_str: str) -> int:
        # Import the class; it depends on shortcut_types at module level so we
        # need to patch the ShortcutExecutor reference used by the mixin.
        from core.shortcut_hotkey import HotkeyExecutionMixin

        # The mixin methods are on ShortcutExecutor but _vk_from_key is static
        # and doesn't reference self, so we can call it directly from the class.
        return HotkeyExecutionMixin._vk_from_key(key_str)

    # -- Modifier keys ---------------------------------------------------
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("ctrl", 0x11),
            ("Ctrl", 0x11),
            ("CONTROL", 0x11),
            ("lctrl", 0xA2),
            ("rctrl", 0xA3),
            ("alt", 0x12),
            ("Alt", 0x12),
            ("menu", 0x12),
            ("lalt", 0xA4),
            ("ralt", 0xA5),
            ("shift", 0x10),
            ("Shift", 0x10),
            ("lshift", 0xA0),
            ("rshift", 0xA1),
            ("win", 0x5B),
            ("lwin", 0x5B),
            ("rwin", 0x5C),
        ],
    )
    def test_modifier_keys(self, name, expected):
        assert self._call(name) == expected

    # -- Special keys ----------------------------------------------------
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("backspace", 0x08),
            ("back", 0x08),
            ("tab", 0x09),
            ("enter", 0x0D),
            ("return", 0x0D),
            ("pause", 0x13),
            ("capslock", 0x14),
            ("caps", 0x14),
            ("escape", 0x1B),
            ("esc", 0x1B),
            ("space", 0x20),
            ("pageup", 0x21),
            ("pgup", 0x21),
            ("pagedown", 0x22),
            ("pgdn", 0x22),
            ("end", 0x23),
            ("home", 0x24),
            ("left", 0x25),
            ("up", 0x26),
            ("right", 0x27),
            ("down", 0x28),
            ("printscreen", 0x2C),
            ("prtscr", 0x2C),
            ("insert", 0x2D),
            ("ins", 0x2D),
            ("delete", 0x2E),
            ("del", 0x2E),
        ],
    )
    def test_navigation_and_editing_keys(self, name, expected):
        assert self._call(name) == expected

    # -- Function keys ---------------------------------------------------
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("f1", 0x70),
            ("f5", 0x74),
            ("f12", 0x7B),
            ("f13", 0x7C),
            ("f24", 0x87),
        ],
    )
    def test_function_keys(self, name, expected):
        assert self._call(name) == expected

    # -- Numpad keys -----------------------------------------------------
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("num0", 0x60),
            ("num9", 0x69),
            ("numpad0", 0x60),
            ("numpad9", 0x69),
            ("multiply", 0x6A),
            ("add", 0x6B),
            ("subtract", 0x6D),
            ("decimal", 0x6E),
            ("divide", 0x6F),
            ("numlock", 0x90),
            ("scrolllock", 0x91),
        ],
    )
    def test_numpad_keys(self, name, expected):
        assert self._call(name) == expected

    # -- Punctuation / symbol keys --------------------------------------
    @pytest.mark.parametrize(
        "name,expected",
        [
            (";", 0xBA),
            ("=", 0xBB),
            (",", 0xBC),
            ("-", 0xBD),
            (".", 0xBE),
            ("/", 0xBF),
            ("`", 0xC0),
            ("[", 0xDB),
            ("\\", 0xDC),
            ("]", 0xDD),
            ("'", 0xDE),
        ],
    )
    def test_symbol_keys(self, name, expected):
        assert self._call(name) == expected

    # -- Single letter / digit ------------------------------------------
    def test_single_letter(self):
        assert self._call("a") == ord("A")
        assert self._call("Z") == ord("Z")
        assert self._call("m") == ord("M")

    def test_single_digit(self):
        assert self._call("0") == ord("0")
        assert self._call("9") == ord("9")

    # -- Edge cases ------------------------------------------------------
    def test_empty_string(self):
        assert self._call("") == 0

    def test_whitespace_only(self):
        assert self._call("   ") == 0

    def test_unknown_multi_char(self):
        assert self._call("unknown") == 0

    def test_leading_trailing_spaces(self):
        # The function strips whitespace via .strip()
        assert self._call(" ctrl") == 0x11  # stripped to "ctrl"


class TestIsExtendedVk:
    """Cover HotkeyExecutionMixin._is_extended_vk."""

    @staticmethod
    def _call(vk: int) -> bool:
        from core.shortcut_hotkey import HotkeyExecutionMixin

        return HotkeyExecutionMixin._is_extended_vk(vk)

    @pytest.mark.parametrize(
        "vk",
        [0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0xA3, 0xA5],
    )
    def test_extended_keys(self, vk):
        assert self._call(vk) is True

    @pytest.mark.parametrize("vk", [0x10, 0x11, 0x12, 0x41, 0x70, 0x00, 0xFF])
    def test_non_extended_keys(self, vk):
        assert self._call(vk) is False
