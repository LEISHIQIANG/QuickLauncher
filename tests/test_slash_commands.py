"""Tests for core/slash_commands.py fallback path."""

import pytest

from core.slash_commands import (
    _ALIAS_TO_COMMAND,
    SLASH_COMMANDS,
    SlashCommand,
    find_matching_commands,
    get_command_by_alias,
)


@pytest.fixture(autouse=True)
def _force_fallback(monkeypatch):
    """Force all functions to use the local fallback path."""
    monkeypatch.setattr("core.slash_commands._registry_available", lambda: False)


# ── SlashCommand dataclass ──────────────────────────────────────────────


def test_slash_command_construction():
    cmd = SlashCommand(
        canonical="test",
        aliases=["test", "t"],
        description="A test command",
        category="system",
        handler="test_handler",
        icon_path="icons/test.png",
        display_name="Test",
        interaction_mode="direct",
    )
    assert cmd.canonical == "test"
    assert cmd.aliases == ["test", "t"]
    assert cmd.description == "A test command"
    assert cmd.category == "system"
    assert cmd.handler == "test_handler"
    assert cmd.icon_path == "icons/test.png"
    assert cmd.display_name == "Test"
    assert cmd.interaction_mode == "direct"


def test_slash_command_defaults():
    cmd = SlashCommand(canonical="x", aliases=["x"], description="d", category="c", handler="h")
    assert cmd.icon_path == ""
    assert cmd.display_name == ""
    assert cmd.interaction_mode == "direct"


# ── SLASH_COMMANDS list ─────────────────────────────────────────────────


def test_slash_commands_list_has_entries():
    assert len(SLASH_COMMANDS) > 0
    assert all(isinstance(c, SlashCommand) for c in SLASH_COMMANDS)


def test_slash_commands_have_unique_canonicals():
    canonicals = [c.canonical for c in SLASH_COMMANDS]
    assert len(canonicals) == len(set(canonicals))


# ── _ALIAS_TO_COMMAND dict ──────────────────────────────────────────────


def test_alias_to_command_has_expected_aliases():
    assert "config" in _ALIAS_TO_COMMAND
    assert "settings" in _ALIAS_TO_COMMAND
    assert "quit" in _ALIAS_TO_COMMAND
    assert "exit" in _ALIAS_TO_COMMAND


def test_alias_to_command_maps_to_correct_command():
    assert _ALIAS_TO_COMMAND["config"].canonical == "config"
    assert _ALIAS_TO_COMMAND["settings"].canonical == "config"
    assert _ALIAS_TO_COMMAND["quit"].canonical == "quit"
    assert _ALIAS_TO_COMMAND["exit"].canonical == "quit"


def test_alias_to_command_is_case_sensitive_in_keys():
    # All keys are stored lowercased
    for key in _ALIAS_TO_COMMAND:
        assert key == key.lower()


# ── find_matching_commands ──────────────────────────────────────────────


def test_find_matching_commands_empty_query_returns_all():
    results = find_matching_commands("")
    assert len(results) == len(SLASH_COMMANDS)


def test_find_matching_commands_whitespace_returns_all():
    results = find_matching_commands("   ")
    assert len(results) == len(SLASH_COMMANDS)


def test_find_matching_commands_exact_match():
    results = find_matching_commands("config")
    assert len(results) >= 1
    assert results[0].canonical == "config"


def test_find_matching_commands_prefix():
    results = find_matching_commands("conf")
    canonicals = [r.canonical for r in results]
    assert "config" in canonicals


def test_find_matching_commands_no_match():
    results = find_matching_commands("xyznonexistent")
    assert results == []


def test_find_matching_commands_alias_match():
    results = find_matching_commands("settings")
    assert len(results) == 1
    assert results[0].canonical == "config"


def test_find_matching_commands_chinese_alias():
    results = find_matching_commands("配置")
    assert len(results) >= 1
    canonicals = [r.canonical for r in results]
    assert "config" in canonicals


def test_find_matching_commands_chinese_alias_exact():
    results = find_matching_commands("退出")
    assert len(results) >= 1
    canonicals = [r.canonical for r in results]
    assert "quit" in canonicals


def test_find_matching_commands_substring():
    # "diag" is both a prefix of "diagnostics" alias and an exact alias
    results = find_matching_commands("diag")
    canonicals = [r.canonical for r in results]
    assert "diagnostics" in canonicals


def test_find_matching_commands_none_query():
    results = find_matching_commands(None)
    assert len(results) == len(SLASH_COMMANDS)


# ── get_command_by_alias ────────────────────────────────────────────────


def test_get_command_by_alias_canonical():
    cmd = get_command_by_alias("config")
    assert cmd is not None
    assert cmd.canonical == "config"


def test_get_command_by_alias_alias():
    cmd = get_command_by_alias("settings")
    assert cmd is not None
    assert cmd.canonical == "config"


def test_get_command_by_alias_nonexistent():
    cmd = get_command_by_alias("nonexistent_xyz")
    assert cmd is None


def test_get_command_by_alias_chinese():
    cmd = get_command_by_alias("配置")
    assert cmd is not None
    assert cmd.canonical == "config"


def test_get_command_by_alias_case_sensitive():
    # Aliases are lowercased in the dict, input is lowered too
    cmd = get_command_by_alias("CONFIG")
    # The function does .lower() on input, and keys are lowercased
    assert cmd is not None
    assert cmd.canonical == "config"
