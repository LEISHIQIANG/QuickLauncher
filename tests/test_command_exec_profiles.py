from core import ShortcutItem, ShortcutType
from core.command_exec.profiles import (
    chain_values,
    command_panel_size,
    command_param_defs,
    command_param_values,
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
