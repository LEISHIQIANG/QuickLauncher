import pytest

from core.command_variables import (
    CommandVariableError,
    collect_input_prompts,
    find_unquoted_external_command_variables,
    is_value_only_variable_command,
    resolve_command_variables,
)
from core.data_models import ShortcutItem


def test_shortcut_item_command_variables_default_disabled():
    restored = ShortcutItem.from_dict({"type": "command", "command_type": "python"})

    assert restored.command_variables_enabled is False

    restored_cmd = ShortcutItem.from_dict({"type": "command", "command_type": "cmd"})

    assert restored_cmd.command_variables_enabled is False


def test_shortcut_item_normalizes_legacy_builtin_command_aliases():
    item = ShortcutItem.from_dict(
        {
            "type": "command",
            "command_type": "cmd",
            "command": "topmost",
        }
    )

    assert item.command_type == "builtin"
    assert item.command == "toggle_topmost"

    config_item = ShortcutItem.from_dict(
        {
            "type": "command",
            "command_type": "cmd",
            "command": "show_config",
        }
    )

    assert config_item.command_type == "builtin"
    assert config_item.command == "show_config_window"

    python_item = ShortcutItem.from_dict(
        {
            "type": "command",
            "command_type": "python",
            "command": "print('topmost')",
        }
    )

    assert python_item.command_type == "python"
    assert python_item.command == "print('topmost')"


def test_resolve_basic_variables_and_quoted_clipboard():
    text = resolve_command_variables(
        "echo {clipboard:q} {date} {{literal}}",
        clipboard_provider=lambda: "hello world",
    )

    assert text.startswith('echo "hello world" ')
    assert "{literal}" in text


def test_resolve_input_variables():
    text = resolve_command_variables(
        "open {input:q} {input:搜索词}",
        input_values={"input": "hello world", "搜索词": "abc"},
    )

    assert text == 'open "hello world" abc'


def test_unknown_variable_is_rejected():
    with pytest.raises(CommandVariableError):
        resolve_command_variables("echo {not_supported}")


def test_python_style_braces_can_be_left_literal_when_not_strict():
    text = resolve_command_variables('print({"a": 1})\\nprint(f"{name}")', strict_unknown=False)

    assert text == 'print({"a": 1})\\nprint(f"{name}")'


def test_collect_input_prompts_deduplicates():
    assert collect_input_prompts("{input:q} {input:名称} {input:名称:q}") == ["", "名称"]


def test_find_unquoted_external_command_variables():
    unsafe = find_unquoted_external_command_variables(
        "echo {clipboard} {clipboard:q} {input:Name} {selected_text:q} {date}"
    )

    assert unsafe == ["clipboard", "input:Name"]


def test_resolve_param_and_chain_variables():
    text = resolve_command_variables(
        "ping {param:host:q} && echo {chain:prev.stdout:q}",
        param_values={"host": "example.com"},
        chain_values={"prev.stdout": "hello world"},
    )

    assert "example.com" in text
    assert "hello world" in text


def test_param_and_chain_variables_require_quoting_in_cmd():
    unsafe = find_unquoted_external_command_variables("echo {param:host} {chain:prev.stdout}")

    assert unsafe == ["param:host", "chain:prev.stdout"]


def test_value_only_variable_commands_are_detected():
    assert is_value_only_variable_command("{date}")
    assert is_value_only_variable_command("{clipboard:q}")
    assert is_value_only_variable_command('"{input:Keyword}"')
    assert not is_value_only_variable_command("echo {date}")
    assert not is_value_only_variable_command("{unknown}")
