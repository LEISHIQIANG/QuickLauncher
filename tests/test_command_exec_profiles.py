from core import ShortcutItem, ShortcutType
from core.command_exec.profiles import (
    chain_values,
    command_panel_size,
    command_param_defs,
    command_param_values,
    effective_command_type,
    merge_runtime_env,
)


def test_command_param_defs_and_values_normalize_runtime_overrides():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = [
        {"name": "host", "type": "choice", "required": True, "default": "prod", "choices": "prod,stage"},
        {"name": "count", "type": "unknown", "default": 3},
        {"type": "text", "default": "ignored"},
    ]
    shortcut._runtime_param_values = {"count": 5, "extra": True}

    assert command_param_defs(shortcut) == [
        {
            "name": "host",
            "type": "choice",
            "required": True,
            "default": "prod",
            "choices": ["prod", "stage"],
            "sensitive": False,
        },
        {
            "name": "count",
            "type": "text",
            "required": False,
            "default": "3",
            "choices": [],
            "sensitive": False,
        },
    ]
    assert command_param_values(shortcut) == {"host": "prod", "count": "5", "extra": "True"}


def test_chain_values_returns_copy_only_for_dicts():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut._chain_values = {"one": "1"}

    values = chain_values(shortcut)
    values["one"] = "changed"

    assert shortcut._chain_values == {"one": "1"}
    shortcut._chain_values = ["bad"]
    assert chain_values(shortcut) == {}


def test_merge_runtime_env_accepts_dict_and_text_env():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_env = {" API_KEY ": "secret", "EMPTY": "", "NONE": None, "": "skip"}

    assert merge_runtime_env(shortcut, {"BASE": "1"}) == {
        "BASE": "1",
        "API_KEY": "secret",
        "EMPTY": "",
        "NONE": "None",
    }

    shortcut.command_env = "A=1\n# ignored\nBAD_LINE\nB = two"
    assert merge_runtime_env(shortcut, {}) == {"A": "1", "B": "two"}


def test_command_panel_size_normalizes_unknown_values():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)

    shortcut.command_panel_size = "large"
    assert command_panel_size(shortcut) == "large"
    shortcut.command_panel_size = "unexpected"
    assert command_panel_size(shortcut) == "medium"
    shortcut.command_panel_size = ""
    assert command_panel_size(shortcut) == "medium"


def test_command_panel_size_small():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_panel_size = "small"
    assert command_panel_size(shortcut) == "small"


def test_command_panel_size_none_falls_back():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_panel_size = None
    assert command_panel_size(shortcut) == "medium"


def test_command_param_defs_empty_list():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = []
    assert command_param_defs(shortcut) == []


def test_command_param_defs_skips_non_dict_entries():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = [
        {"name": "valid", "type": "text"},
        "not_a_dict",
        42,
        {"name": "", "type": "text"},
    ]
    defs = command_param_defs(shortcut)
    assert len(defs) == 1
    assert defs[0]["name"] == "valid"


def test_command_param_defs_missing_attr():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    del shortcut.command_params
    assert command_param_defs(shortcut) == []


def test_command_param_values_empty():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = []
    assert command_param_values(shortcut) == {}


def test_chain_values_missing_attr():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    if hasattr(shortcut, "_chain_values"):
        del shortcut._chain_values
    assert chain_values(shortcut) == {}


def test_chain_values_none():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut._chain_values = None
    assert chain_values(shortcut) == {}


def test_merge_runtime_env_empty_base():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_env = {}
    assert merge_runtime_env(shortcut, None) == {}


def test_merge_runtime_env_empty_keys_skipped():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_env = {"": "val", "  ": "val2", "GOOD": "ok"}
    result = merge_runtime_env(shortcut, {})
    assert "GOOD" in result
    assert "" not in result


def test_command_param_defs_normalizes_choice_types():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = [
        {"name": "env", "type": "choice", "choices": "prod,stage,dev"},
    ]
    defs = command_param_defs(shortcut)
    assert defs[0]["choices"] == ["prod", "stage", "dev"]
    assert defs[0]["type"] == "choice"


def test_command_param_defs_invalid_type_defaults_to_text():
    shortcut = ShortcutItem(type=ShortcutType.COMMAND)
    shortcut.command_params = [
        {"name": "x", "type": "unknown_type"},
    ]
    defs = command_param_defs(shortcut)
    assert defs[0]["type"] == "text"


# ---------------------------------------------------------------------------
# effective_command_type
# ---------------------------------------------------------------------------


def test_effective_command_type_cmd():
    assert effective_command_type("cmd") == "cmd"


def test_effective_command_type_powershell():
    assert effective_command_type("powershell") == "powershell"


def test_effective_command_type_none_defaults_to_cmd():
    assert effective_command_type(None) == "cmd"


def test_effective_command_type_empty_defaults_to_cmd():
    assert effective_command_type("") == "cmd"


def test_effective_command_type_case_insensitive():
    assert effective_command_type("CMD") == "cmd"
    assert effective_command_type("PowerShell") == "powershell"
