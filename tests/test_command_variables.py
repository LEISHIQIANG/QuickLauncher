import pytest

from core.command_variables import (
    CommandVariableError,
    collect_input_prompts,
    fetch_public_wan_ipv4,
    find_unknown_variable_specs,
    find_unquoted_external_command_variables,
    is_value_only_variable_command,
    migrate_legacy_variable_syntax,
    quote_bash_arg,
    resolve_command_variables,
)
from core.config_repairs import apply_config_repairs, scan_config_repairs
from core.data_models import AppData, Folder, ShortcutItem, ShortcutType


def test_shortcut_item_command_variables_default_disabled():
    restored = ShortcutItem.from_dict({"type": "command", "command_type": "python"})

    assert restored.command_variables_enabled is False

    restored_cmd = ShortcutItem.from_dict({"type": "command", "command_type": "cmd"})

    assert restored_cmd.command_variables_enabled is False


def test_config_repairs_migrate_legacy_text_templates():
    item = ShortcutItem(
        type=ShortcutType.COMMAND,
        command_type="cmd",
        command_variables_enabled=False,
        command='echo {clipboard:q} {version} {"json": true} {{unknown}}',
    )
    url_item = ShortcutItem(
        type=ShortcutType.URL,
        url="https://example.com/search?q={input}",
        preferred_browser_args="--profile Default {url}",
    )
    data = AppData(folders=[Folder(items=[item, url_item])])

    scan = scan_config_repairs(data)
    assert scan.changed is False
    assert scan.repaired == 0
    assert any(issue.code == "legacy_variable_syntax" for issue in scan.issues)
    assert any(issue.code == "unknown_variable" for issue in scan.issues)

    assert item.command == 'echo {clipboard:q} {version} {"json": true} {{unknown}}'
    assert url_item.url == "https://example.com/search?q={input}"
    assert url_item.preferred_browser_args == "--profile Default {url}"

    report = apply_config_repairs(data)

    assert report.changed is True
    assert item.command == 'echo {{clipboard:q}} {version} {"json": true} {{unknown}}'
    assert url_item.url == "https://example.com/search?q={{input}}"
    assert url_item.preferred_browser_args == "--profile Default {{url}}"


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

    powershell_item = ShortcutItem.from_dict(
        {
            "type": "command",
            "command_type": "powershell",
            "command": "topmost",
        }
    )

    assert powershell_item.command_type == "powershell"
    assert powershell_item.command == "topmost"


def test_resolve_basic_variables_and_quoted_clipboard():
    text = resolve_command_variables(
        "echo {{clipboard:q}} {{date}} {{{{literal}}}}",
        clipboard_provider=lambda: "hello world",
    )

    assert text.startswith('echo "hello world" ')
    assert "{{literal}}" in text


def test_resolve_input_variables():
    text = resolve_command_variables(
        "open {{input:q}} {{input:搜索词}}",
        input_values={"input": "hello world", "搜索词": "abc"},
    )

    assert text == 'open "hello world" abc'


def test_unknown_variable_is_rejected():
    with pytest.raises(CommandVariableError):
        resolve_command_variables("echo {{not_supported}}")


def test_find_unknown_variable_specs_allows_ip_variables():
    assert find_unknown_variable_specs("{{LAN_IP}} {{wan_ip}} {{unknown}}") == ["unknown"]


def test_resolve_ip_variables(monkeypatch):
    monkeypatch.setattr("core.command_variables.get_default_lan_ipv4", lambda: "192.168.1.20")
    monkeypatch.setattr("core.command_variables.fetch_public_wan_ipv4", lambda: "203.0.113.9")

    assert resolve_command_variables("{{LAN_IP}} {{wan_ip}}") == "192.168.1.20 203.0.113.9"


def test_fetch_public_wan_ipv4_skips_ipv6(monkeypatch):
    responses = iter(['{"ip":"2001:db8::1"}', "203.0.113.9"])

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size):
            return next(responses).encode("utf-8")

    monkeypatch.setattr("core.command_variables.urllib.request.urlopen", lambda request, timeout=0: FakeResponse())

    assert fetch_public_wan_ipv4() == "203.0.113.9"


def test_fetch_public_wan_ipv4_errors_when_only_ipv6(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size):
            return b"2001:db8::1"

    monkeypatch.setattr("core.command_variables.urllib.request.urlopen", lambda request, timeout=0: FakeResponse())

    with pytest.raises(CommandVariableError):
        fetch_public_wan_ipv4()


def test_python_style_braces_can_be_left_literal_when_not_strict():
    text = resolve_command_variables('print({"a": 1})\\nprint(f"{name}")', strict_unknown=True)

    assert text == 'print({"a": 1})\\nprint(f"{name}")'


def test_collect_input_prompts_deduplicates():
    assert collect_input_prompts("{{input:q}} {{input:名称}} {{input:名称:q}}") == ["", "名称"]


def test_find_unquoted_external_command_variables():
    unsafe = find_unquoted_external_command_variables(
        "echo {{clipboard}} {{clipboard:q}} {{input:Name}} {{selected_text:q}} {{date}}"
    )

    assert unsafe == ["clipboard", "input:Name"]


def test_resolve_param_and_chain_variables():
    text = resolve_command_variables(
        "ping {{param:host:q}} && echo {{chain:prev.stdout:q}}",
        param_values={"host": "example.com"},
        chain_values={"prev.stdout": "hello world"},
    )

    assert "example.com" in text
    assert "hello world" in text


def test_resolve_selected_file_variables():
    text = resolve_command_variables(
        "tool {{selected_file:q}} {{selected_file_name:q}} {{selected_file_dir:q}}",
        selected_files=[r"C:\Work Folder\demo.txt"],
    )

    assert r'"C:\Work Folder\demo.txt"' in text
    assert "demo.txt" in text
    assert r'"C:\Work Folder"' in text


def test_resolve_selected_files_quotes_each_path():
    text = resolve_command_variables(
        "tool {{selected_files:q}}",
        selected_files=[r"C:\A\a.txt", r"D:\B Folder\b.txt"],
    )

    assert text == r'tool C:\A\a.txt "D:\B Folder\b.txt"'


def test_missing_selected_file_variables_resolve_empty():
    text = resolve_command_variables(
        "tool {{selected_file:q}} {{selected_file_name:q}} {{selected_file_dir:q}} {{selected_files:q}}",
        selected_files=[],
    )

    assert text == 'tool "" "" "" '


def test_param_and_chain_variables_require_quoting_in_cmd():
    unsafe = find_unquoted_external_command_variables("echo {{param:host}} {{chain:prev.stdout}} {{selected_file}}")

    assert unsafe == ["param:host", "chain:prev.stdout", "selected_file"]


def test_value_only_variable_commands_are_detected():
    assert is_value_only_variable_command("{{date}}")
    assert is_value_only_variable_command("{{clipboard:q}}")
    assert is_value_only_variable_command('"{{input:Keyword}}"')
    assert not is_value_only_variable_command("echo {{date}}")
    assert not is_value_only_variable_command("{{unknown}}")


def test_legacy_single_brace_variables_are_left_literal():
    text = resolve_command_variables("echo {clipboard:q} {date}", clipboard_provider=lambda: "hello")

    assert text == "echo {clipboard:q} {date}"


def test_migrate_legacy_variable_syntax_whitelist_only():
    text = migrate_legacy_variable_syntax(
        'echo {clipboard:q} {selected_file:q} {version} {"json": true} {param:host:q}'
    )

    assert "{{clipboard:q}}" in text
    assert "{{selected_file:q}}" in text
    assert "{{param:host:q}}" in text
    assert "{version}" in text
    assert '{"json": true}' in text


def test_migrate_legacy_url_placeholder_when_enabled():
    assert migrate_legacy_variable_syntax("--profile {url}", include_url=True) == "--profile {{url}}"
    assert migrate_legacy_variable_syntax("--profile {url}", include_url=False) == "--profile {url}"


def test_quote_bash_arg_basic():
    assert quote_bash_arg("hello") == "'hello'"


def test_quote_bash_arg_backslash_to_slash():
    assert quote_bash_arg(r"C:\Users\test\file.txt") == "'C:/Users/test/file.txt'"


def test_quote_bash_arg_with_spaces():
    assert quote_bash_arg(r"D:\My Folder\doc.txt") == "'D:/My Folder/doc.txt'"


def test_quote_bash_arg_single_quote():
    result = quote_bash_arg("it's a file")
    assert result == "'it'\\''s a file'"


def test_quote_bash_arg_empty():
    assert quote_bash_arg("") == "''"
    assert quote_bash_arg(None) == "''"


def test_resolve_bash_mode_selected_file():
    text = resolve_command_variables(
        "rm -rf {{selected_file:q}}",
        selected_files=[r"C:\Users\test\file.txt"],
        bash_mode=True,
    )

    assert text == "rm -rf 'C:/Users/test/file.txt'"


def test_resolve_bash_mode_selected_file_with_spaces():
    text = resolve_command_variables(
        "rm -rf {{selected_file:q}}",
        selected_files=[r"D:\My Folder\doc.txt"],
        bash_mode=True,
    )

    assert text == "rm -rf 'D:/My Folder/doc.txt'"


def test_resolve_bash_mode_selected_files():
    text = resolve_command_variables(
        "tool {{selected_files:q}}",
        selected_files=[r"C:\A\a.txt", r"D:\B Folder\b.txt"],
        bash_mode=True,
    )

    assert text == "tool 'C:/A/a.txt' 'D:/B Folder/b.txt'"


def test_resolve_bash_mode_clipboard():
    text = resolve_command_variables(
        "echo {{clipboard:q}}",
        clipboard_provider=lambda: "hello world",
        bash_mode=True,
    )

    assert text == "echo 'hello world'"


def test_resolve_default_mode_unchanged():
    text = resolve_command_variables(
        "rm -rf {{selected_file:q}}",
        selected_files=[r"C:\Users\test\file.txt"],
    )

    assert text == 'rm -rf C:\\Users\\test\\file.txt'
