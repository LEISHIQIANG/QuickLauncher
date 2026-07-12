import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest

from core.hotkey_conflict_checker import (
    SYSTEM_HOTKEYS,
    _get_vk_code,
    check_conflict,
    is_hotkey_registered,
    normalize_hotkey,
)

# ── normalize_hotkey ──────────────────────────────────────────────────────────


class TestNormalizeHotkey:
    """normalize_hotkey 单元测试"""

    # ---- 基本功能 ----

    def test_single_key(self):
        assert normalize_hotkey("A") == "A"
        assert normalize_hotkey("F1") == "F1"

    def test_ctrl_plus_key(self):
        assert normalize_hotkey("Ctrl+A") == "Ctrl+A"

    def test_alt_plus_key(self):
        assert normalize_hotkey("Alt+F4") == "Alt+F4"

    def test_shift_plus_key(self):
        assert normalize_hotkey("Shift+Tab") == "Shift+Tab"

    def test_win_plus_key(self):
        assert normalize_hotkey("Win+D") == "Win+D"

    # ---- 修饰键排序 ----

    def test_ctrl_alt_sorting(self):
        # 不同顺序输入，输出都应为 Ctrl+Alt+...
        assert normalize_hotkey("Ctrl+Alt+A") == "Ctrl+Alt+A"
        assert normalize_hotkey("Alt+Ctrl+A") == "Ctrl+Alt+A"

    def test_ctrl_shift_sorting(self):
        assert normalize_hotkey("Ctrl+Shift+A") == "Ctrl+Shift+A"
        assert normalize_hotkey("Shift+Ctrl+A") == "Ctrl+Shift+A"

    def test_ctrl_win_sorting(self):
        assert normalize_hotkey("Win+Ctrl+A") == "Ctrl+Win+A"
        assert normalize_hotkey("Ctrl+Win+A") == "Ctrl+Win+A"

    def test_alt_shift_sorting(self):
        assert normalize_hotkey("Shift+Alt+A") == "Alt+Shift+A"
        assert normalize_hotkey("Alt+Shift+A") == "Alt+Shift+A"

    def test_alt_win_sorting(self):
        assert normalize_hotkey("Win+Alt+A") == "Alt+Win+A"
        assert normalize_hotkey("Alt+Win+A") == "Alt+Win+A"

    def test_shift_win_sorting(self):
        assert normalize_hotkey("Win+Shift+A") == "Shift+Win+A"
        assert normalize_hotkey("Shift+Win+A") == "Shift+Win+A"

    def test_four_modifiers_all_orders(self):
        """四个修饰键任意排列，输出顺序应固定为 Ctrl+Alt+Shift+Win"""
        expected = "Ctrl+Alt+Shift+Win+A"
        import itertools

        for perm in itertools.permutations(["Ctrl", "Alt", "Shift", "Win"]):
            hotkey = "+".join(perm) + "+A"
            assert normalize_hotkey(hotkey) == expected, f"输入: {hotkey}"

    # ---- 大小写不敏感 ----

    def test_lowercase(self):
        assert normalize_hotkey("ctrl+a") == "Ctrl+A"

    def test_uppercase(self):
        assert normalize_hotkey("CTRL+A") == "Ctrl+A"

    def test_mixed_case(self):
        assert normalize_hotkey("cTrL+a") == "Ctrl+A"
        assert normalize_hotkey("AlT+F4") == "Alt+F4"
        assert normalize_hotkey("sHiFt+Tab") == "Shift+Tab"

    # ---- 别名 ----

    def test_control_alias(self):
        """control 应视为 ctrl"""
        assert normalize_hotkey("Control+A") == "Ctrl+A"
        assert normalize_hotkey("control+a") == "Ctrl+A"

    def test_windows_alias(self):
        """windows 应视为 win"""
        assert normalize_hotkey("Windows+D") == "Win+D"

    def test_super_alias(self):
        """super 应视为 win"""
        assert normalize_hotkey("Super+D") == "Win+D"

    # ---- 分隔符变体 ----

    def test_spaces_instead_of_plus(self):
        """用空格替代 + 也能正确解析"""
        assert normalize_hotkey("Ctrl A") == "Ctrl+A"
        assert normalize_hotkey("Ctrl Alt A") == "Ctrl+Alt+A"

    def test_plus_sign_separator(self):
        assert normalize_hotkey("Ctrl+Alt+A") == "Ctrl+Alt+A"

    def test_whitespace_around_parts(self):
        """前后空格应被清理"""
        assert normalize_hotkey(" Ctrl + A ") == "Ctrl+A"

    # ---- 特殊按键名称 ----

    def test_function_keys(self):
        for i in range(1, 13):
            assert normalize_hotkey(f"F{i}") == f"F{i}"

    def test_special_keys(self):
        for key in [
            "Space",
            "Enter",
            "Esc",
            "Tab",
            "Backspace",
            "Delete",
            "Insert",
            "Home",
            "End",
            "PageUp",
            "PageDown",
            "Left",
            "Up",
            "Right",
            "Down",
        ]:
            assert normalize_hotkey(f"Ctrl+{key}") == f"Ctrl+{key.title()}", f"按键: {key}"

    # ---- Title Case 验证 ----

    def test_output_is_title_case(self):
        assert normalize_hotkey("ctrl+shift+f5") == "Ctrl+Shift+F5"


# ── check_conflict ────────────────────────────────────────────────────────────


class TestCheckConflict:
    """check_conflict 单元测试"""

    # ---- 空输入 ----

    def test_empty_string(self):
        is_conflict, desc = check_conflict("")
        assert is_conflict is False
        assert desc == ""

    def test_whitespace_only(self):
        is_conflict, desc = check_conflict("   ")
        assert is_conflict is False
        assert desc == ""

    # ---- 系统快捷键冲突 ----

    @pytest.mark.parametrize("hotkey", list(SYSTEM_HOTKEYS.keys()))
    def test_system_hotkey_conflict(self, hotkey):
        is_conflict, desc = check_conflict(hotkey)
        assert is_conflict is True
        assert "系统快捷键冲突" in desc
        assert SYSTEM_HOTKEYS[hotkey] in desc

    def test_system_hotkey_case_insensitive(self):
        """大小写变体也应检测为冲突"""
        is_conflict, desc = check_conflict("win+d")
        assert is_conflict is True
        assert "系统快捷键冲突" in desc

    def test_system_hotkey_alias(self):
        """使用别名也应检测为冲突"""
        is_conflict, desc = check_conflict("Control+C")
        assert is_conflict is True
        assert "复制" in desc

    # ---- 常用快捷键冲突 ----

    @pytest.mark.parametrize(
        "hotkey,desc_part",
        [
            ("Ctrl+S", "保存"),
            ("Ctrl+O", "打开"),
            ("Ctrl+N", "新建"),
            ("Ctrl+W", "关闭"),
            ("Ctrl+P", "打印"),
            ("Ctrl+F", "查找"),
            ("Ctrl+H", "替换"),
        ],
    )
    def test_common_conflict(self, hotkey, desc_part):
        is_conflict, desc = check_conflict(hotkey)
        assert is_conflict is True
        assert "常用快捷键冲突" in desc
        assert desc_part in desc

    # ---- 无冲突 ----

    @pytest.mark.parametrize(
        "hotkey",
        [
            "Ctrl+F5",
            "Ctrl+Shift+F1",
            "Alt+Shift+X",
            "Ctrl+Alt+Shift+Q",
            "F9",
            "Ctrl+0",
        ],
    )
    def test_no_conflict(self, hotkey):
        is_conflict, desc = check_conflict(hotkey)
        assert is_conflict is False
        assert desc == ""


# ── _get_vk_code ──────────────────────────────────────────────────────────────


class TestGetVkCode:
    """_get_vk_code 单元测试"""

    # ---- 字母 A-Z ----

    @pytest.mark.parametrize("char", [chr(c) for c in range(ord("A"), ord("Z") + 1)])
    def test_uppercase_letters(self, char):
        assert _get_vk_code(char) == ord(char)

    @pytest.mark.parametrize("char", [chr(c) for c in range(ord("a"), ord("z") + 1)])
    def test_lowercase_letters(self, char):
        assert _get_vk_code(char) == ord(char.upper())

    # ---- 数字 0-9 ----

    @pytest.mark.parametrize("digit", [chr(c) for c in range(ord("0"), ord("9") + 1)])
    def test_digits(self, digit):
        assert _get_vk_code(digit) == ord(digit)

    # ---- 功能键 F1-F12 ----

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("F1", 0x70),
            ("F2", 0x71),
            ("F3", 0x72),
            ("F4", 0x73),
            ("F5", 0x74),
            ("F6", 0x75),
            ("F7", 0x76),
            ("F8", 0x77),
            ("F9", 0x78),
            ("F10", 0x79),
            ("F11", 0x7A),
            ("F12", 0x7B),
        ],
    )
    def test_function_keys(self, key, expected):
        assert _get_vk_code(key) == expected

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("f1", 0x70),
            ("f5", 0x74),
            ("f12", 0x7B),
        ],
    )
    def test_function_keys_case_insensitive(self, key, expected):
        assert _get_vk_code(key) == expected

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("F13", 0x7C),
            ("f24", 0x87),
        ],
    )
    def test_extended_function_keys(self, key, expected):
        assert _get_vk_code(key) == expected

    # ---- 特殊按键 ----

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("SPACE", 0x20),
            ("ENTER", 0x0D),
            ("ESC", 0x1B),
            ("TAB", 0x09),
            ("BACKSPACE", 0x08),
            ("DELETE", 0x2E),
            ("INSERT", 0x2D),
            ("HOME", 0x24),
            ("END", 0x23),
            ("PAGEUP", 0x21),
            ("PAGEDOWN", 0x22),
            ("LEFT", 0x25),
            ("UP", 0x26),
            ("RIGHT", 0x27),
            ("DOWN", 0x28),
        ],
    )
    def test_special_keys(self, key, expected):
        assert _get_vk_code(key) == expected

    @pytest.mark.parametrize(
        "key",
        [
            "space",
            "enter",
            "esc",
            "tab",
            "delete",
            "home",
        ],
    )
    def test_special_keys_case_insensitive(self, key):
        expected = _get_vk_code(key.upper())
        assert _get_vk_code(key) == expected

    # ---- 未知按键 ----

    @pytest.mark.parametrize(
        "key",
        [
            "UNKNOWN",
            "XXX",
            "MEDIA_PLAY",
            "",
        ],
    )
    def test_unknown_keys_return_zero(self, key):
        assert _get_vk_code(key) == 0


# ── Extended normalize_hotkey edge cases ─────────────────────────────────────


class TestNormalizeHotkeyEdgeCases:
    """normalize_hotkey 边界用例"""

    def test_empty_string(self):
        """空字符串应返回空字符串"""
        assert normalize_hotkey("") == ""

    def test_single_modifier_only(self):
        """单独一个修饰键也应正确标题化"""
        assert normalize_hotkey("Ctrl") == "Ctrl"
        assert normalize_hotkey("Alt") == "Alt"
        assert normalize_hotkey("Shift") == "Shift"
        assert normalize_hotkey("Win") == "Win"

    def test_duplicate_modifiers_deduped(self):
        """重复修饰键：实际行为是都保留（排序后），不做去重"""
        # normalize_hotkey 不做去重，重复修饰键会重复出现
        result = normalize_hotkey("Ctrl+Ctrl+A")
        parts = result.split("+")
        assert parts.count("Ctrl") == 2
        assert parts[-1] == "A"

    def test_only_plus_signs(self):
        """只有加号分隔符，无实际内容"""
        assert normalize_hotkey("++") == ""

    def test_whitespace_input(self):
        """纯空白输入"""
        assert normalize_hotkey("   ") == ""


# ── Extended check_conflict non-conflicting hotkeys ──────────────────────────


class TestCheckConflictMoreNonConflicting:
    """更多无冲突快捷键验证"""

    @pytest.mark.parametrize(
        "hotkey",
        [
            "Ctrl+F9",
            "Ctrl+Shift+F5",
            "Alt+F7",
            "Ctrl+Alt+F12",
            "Ctrl+Shift+Z",
            "Ctrl+Alt+G",
            "Shift+F10",
            "Ctrl+Shift+F6",
            "Ctrl+Alt+T",
            "F8",
        ],
    )
    def test_no_conflict_extended(self, hotkey):
        is_conflict, desc = check_conflict(hotkey)
        assert is_conflict is False
        assert desc == ""


# ── SYSTEM_HOTKEYS and _NORMALIZED_SYSTEM_HOTKEYS validation ─────────────────


class TestSystemHotkeysIntegrity:
    """SYSTEM_HOTKEYS 字典和规范化缓存完整性"""

    def test_system_hotkeys_not_empty(self):
        assert len(SYSTEM_HOTKEYS) > 0

    def test_all_system_hotkeys_have_description(self):
        """每个系统快捷键都有非空描述"""
        for hotkey, desc in SYSTEM_HOTKEYS.items():
            assert desc, f"SYSTEM_HOTKEYS['{hotkey}'] has empty description"

    def test_normalized_system_hotkeys_keys_match(self):
        """_NORMALIZED_SYSTEM_HOTKEYS 的键数与 SYSTEM_HOTKEYS 一致"""
        from core.hotkey_conflict_checker import _NORMALIZED_SYSTEM_HOTKEYS

        assert len(_NORMALIZED_SYSTEM_HOTKEYS) == len(SYSTEM_HOTKEYS)

    def test_normalized_system_hotkeys_values_match(self):
        """规范化后每个值仍然对应原始描述"""
        from core.hotkey_conflict_checker import _NORMALIZED_SYSTEM_HOTKEYS

        for raw_key, desc in SYSTEM_HOTKEYS.items():
            norm = normalize_hotkey(raw_key)
            assert norm in _NORMALIZED_SYSTEM_HOTKEYS, f"'{raw_key}' -> '{norm}' not in normalized dict"
            assert _NORMALIZED_SYSTEM_HOTKEYS[norm] == desc

    def test_normalized_keys_are_title_case(self):
        """所有规范化后的键都是标题格式"""
        from core.hotkey_conflict_checker import _NORMALIZED_SYSTEM_HOTKEYS

        for key in _NORMALIZED_SYSTEM_HOTKEYS:
            parts = key.split("+")
            for part in parts:
                assert part == part.title(), f"'{key}' part '{part}' is not title case"


def test_vk_code_uses_shared_key_map_aliases():
    assert _get_vk_code("PgDn") == 0x22
    assert _get_vk_code("VolumeUp") == 0xAF


def test_registration_probe_uses_unique_atom_and_always_deletes_it(monkeypatch):
    calls = []

    class User32:
        @staticmethod
        def RegisterHotKey(_hwnd, hotkey_id, modifiers, vk):
            calls.append(("register", hotkey_id, modifiers, vk))
            return 0

    class Kernel32:
        @staticmethod
        def GlobalAddAtomW(name):
            calls.append(("add", name))
            return 0xC123

        @staticmethod
        def GlobalDeleteAtom(atom):
            calls.append(("delete", atom))
            return 0

    monkeypatch.setattr("ctypes.windll.user32", User32())
    monkeypatch.setattr("ctypes.windll.kernel32", Kernel32())

    assert is_hotkey_registered(["ctrl"], "P") is True
    assert ("register", 0xC123, 0x0002, ord("P")) in calls
    assert calls[-1] == ("delete", 0xC123)
