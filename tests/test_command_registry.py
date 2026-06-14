"""Tests for core/command_registry.py — data models and CommandRegistry."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import time

import core.command_registry as command_registry
from core.command_registry import (
    COMMAND_INTERACTION_DIRECT,
    COMMAND_INTERACTION_PANEL,
    CommandAction,
    CommandContext,
    CommandDefinition,
    CommandMetadata,
    CommandParam,
    CommandRegistry,
    CommandResult,
    _CallbackHandler,
    builtin_command_metadata,
    execute_search_sources,
    register_search_source,
    remove_search_source,
    set_pending_command_result,
    take_pending_command_result,
)

logger = logging.getLogger(__name__)

# ============================================================
# Data model tests
# ============================================================


class TestCommandParam:
    def test_defaults(self):
        p = CommandParam(name="file")
        assert p.name == "file"
        assert p.type == "text"
        assert p.required is False
        assert p.default == ""

    def test_choice(self):
        p = CommandParam(name="algo", type="choice", choices=["md5", "sha1", "sha256"])
        assert p.type == "choice"
        assert len(p.choices) == 3


class TestCommandDefinition:
    def test_defaults_to_panel_interaction(self):
        cmd = CommandDefinition(
            id="uuid",
            title="UUID",
            aliases=["uuid"],
            description="Generate UUID",
            category="developer",
            handler=lambda ctx: CommandResult(success=True),
        )
        assert cmd.interaction_mode == COMMAND_INTERACTION_PANEL
        assert cmd.result_window_size == ""
        assert cmd.metadata.category == "developer"
        assert cmd.metadata.risk_level == "low"

    def test_metadata_dict_is_normalized(self):
        cmd = CommandDefinition(
            id="hosts",
            title="Hosts",
            aliases=["hosts"],
            description="Edit hosts",
            category="system",
            handler=lambda ctx: CommandResult(success=True),
            metadata={"risk_level": "medium", "requires_admin": True, "modifies_system": True},
        )

        assert isinstance(cmd.metadata, CommandMetadata)
        assert cmd.metadata.to_dict() == {
            "category": "system",
            "risk_level": "medium",
            "requires_admin": True,
            "uses_network": False,
            "modifies_system": True,
            "requires_confirmation": False,
        }

    def test_builtin_command_metadata_overrides(self):
        hosts = builtin_command_metadata("hosts", "system")
        git = builtin_command_metadata("git", "developer")

        assert hosts.requires_admin is True
        assert hosts.modifies_system is True
        assert hosts.risk_level == "medium"
        assert git.uses_network is True
        assert git.modifies_system is True


class TestCommandAction:
    def test_defaults(self):
        a = CommandAction()
        assert a.type == "copy"
        assert a.label == ""
        assert a.value == ""
        assert a.enabled is True
        assert a.danger is False
        assert a.primary is False
        assert a.payload == {}

    def test_full(self):
        a = CommandAction(
            type="open_url",
            label="打开",
            value="https://example.com",
            enabled=False,
            danger=True,
            primary=True,
            payload={"source": "test"},
        )
        assert a.type == "open_url"
        assert a.value == "https://example.com"
        assert a.enabled is False
        assert a.danger is True
        assert a.primary is True
        assert a.payload == {"source": "test"}


class TestCommandContext:
    def test_defaults(self):
        ctx = CommandContext()
        assert ctx.raw_input == ""
        assert ctx.args_text == ""
        assert ctx.clipboard_text == ""
        assert ctx.selected_files == []

    def test_with_fields(self):
        ctx = CommandContext(
            raw_input="/hash C:/test.txt md5",
            args_text="C:/test.txt md5",
            clipboard_text="hello",
            selected_files=["C:/test.txt"],
        )
        assert ctx.raw_input == "/hash C:/test.txt md5"
        assert ctx.clipboard_text == "hello"
        assert ctx.selected_files == ["C:/test.txt"]


class TestCommandResult:
    def test_success_defaults(self):
        r = CommandResult()
        assert r.success is True
        assert r.message == ""
        assert r.display_type == "text"
        assert r.actions == []

    def test_failure(self):
        r = CommandResult(success=False, message="出错了", error="file not found")
        assert r.success is False
        assert r.error == "file not found"

    def test_with_actions(self):
        r = CommandResult(
            message="42",
            actions=[CommandAction(type="copy", label="复制", value="42")],
        )
        assert len(r.actions) == 1
        assert r.actions[0].value == "42"


# ============================================================
# _CallbackHandler tests
# ============================================================


class TestCallbackHandler:
    def test_wraps_callback_name(self):
        h = _CallbackHandler("show_config_window")
        assert h._callback_name == "show_config_window"
        # call_callback returns None for unregistered callbacks,
        # which _CallbackHandler treats as failure (falsy result)
        result = h(CommandContext())
        assert result.message == "命令执行失败: show_config_window"


# ============================================================
# CommandRegistry tests
# ============================================================


class TestCommandRegistry:
    def _make_cmd(self, id: str = "test.cmd", aliases: list[str] | None = None):
        return CommandDefinition(
            id=id,
            title=id.replace(".", " ").title(),
            aliases=aliases or [id],
            description="a test command",
            category="test",
            handler=lambda ctx: CommandResult(success=True, message="ok"),
            source="builtin",
        )

    def test_register_and_get(self):
        reg = CommandRegistry()
        cmd = self._make_cmd("hello.world", aliases=["hello", "hw"])
        assert reg.register(cmd) is True
        assert reg.get("hello.world") is cmd
        assert reg.count() == 1

    def test_register_rejects_duplicate_id(self):
        reg = CommandRegistry()
        cmd1 = self._make_cmd("dup")
        cmd2 = self._make_cmd("dup")
        assert reg.register(cmd1) is True
        assert reg.register(cmd2) is False  # duplicate rejected
        assert reg.count() == 1

    def test_get_returns_none_for_unknown(self):
        reg = CommandRegistry()
        assert reg.get("nope") is None

    def test_get_canonical_by_alias(self):
        reg = CommandRegistry()
        cmd = self._make_cmd("foo.bar", aliases=["foo", "fb", "fbar"])
        reg.register(cmd)
        assert reg.get_canonical("foo") == "foo.bar"
        assert reg.get_canonical("FB") == "foo.bar"  # case insensitive
        assert reg.get_canonical("unknown") == ""

    def test_find_exact_match(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("hash.calc", aliases=["hash", "哈希"]))
        results = reg.find("hash")
        assert len(results) == 1
        assert results[0].id == "hash.calc"

    def test_find_prefix_match(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("base64.encode", aliases=["base64", "b64"]))
        reg.register(self._make_cmd("base32.encode", aliases=["base32"]))
        results = reg.find("base")
        assert len(results) == 2

    def test_find_substring_match(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("uuid.gen", aliases=["uuid", "u"]))
        reg.register(self._make_cmd("timestamp", aliases=["ts", "time"]))
        results = reg.find("time")
        assert len(results) == 1
        assert results[0].id == "timestamp"

    def test_find_chinese_alias(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("config", aliases=["config", "设置", "偏好"]))
        results = reg.find("设置")
        assert len(results) == 1
        assert results[0].id == "config"

    def test_find_empty_query_returns_all(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("a"))
        reg.register(self._make_cmd("b"))
        assert len(reg.find("")) == 2

    def test_list(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("a"))
        reg.register(self._make_cmd("b"))
        assert len(reg.list()) == 2

    def test_list_by_category(self):
        reg = CommandRegistry()
        cmd_a = self._make_cmd("a")
        cmd_a.category = "cat1"
        cmd_b = self._make_cmd("b")
        cmd_b.category = "cat2"
        reg.register(cmd_a)
        reg.register(cmd_b)
        cats = reg.list_by_category()
        assert "cat1" in cats
        assert "cat2" in cats
        assert len(cats["cat1"]) == 1
        assert len(cats["cat2"]) == 1

    def test_remove(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("rm.me"))
        assert reg.count() == 1
        assert reg.remove("rm.me") is True
        assert reg.count() == 0
        assert reg.remove("rm.me") is False  # already gone

    def test_remove_cleans_alias_map(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("x", aliases=["x", "ex"]))
        assert reg.get_canonical("x") == "x"
        reg.remove("x")
        assert reg.get_canonical("x") == ""

    def test_remove_with_none_aliases_does_not_crash(self):
        """CommandDefinition with aliases=None must be safely removable."""
        reg = CommandRegistry()
        cmd = CommandDefinition(
            id="test.no_aliases",
            title="No Aliases",
            aliases=None,
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        assert reg.register(cmd) is True
        assert reg.remove("test.no_aliases") is True
        assert reg.count() == 0

    def test_register_multiple_commands(self):
        reg = CommandRegistry()
        for i in range(10):
            reg.register(self._make_cmd(f"cmd.{i}", aliases=[f"c{i}"]))
        assert reg.count() == 10
        assert len(reg.find("c")) == 10  # all match prefix "c"

    def test_find_ordering_exact_before_prefix(self):
        reg = CommandRegistry()
        reg.register(self._make_cmd("hash", aliases=["hash", "哈希计算"]))
        reg.register(self._make_cmd("hash.calc", aliases=["hashcalc"]))
        results = reg.find("hash")
        # Exact match should come first
        assert results[0].id == "hash"

    def test_find_matches_title_description_category_and_search_terms(self):
        reg = CommandRegistry()
        cmd = self._make_cmd("text_tools.count", aliases=["count"])
        cmd.title = "文本统计"
        cmd.description = "Count lines and words"
        cmd.category = "文本"
        cmd.source = "plugin:text_tools"
        cmd.search_terms = ["Text Tools", "文本工具"]
        reg.register(cmd)

        assert reg.find("text")[0].id == "text_tools.count"
        assert reg.find("tools")[0].id == "text_tools.count"
        assert reg.find("lines")[0].id == "text_tools.count"
        assert reg.find("文本")[0].id == "text_tools.count"


# ============================================================
# Migration tests
# ============================================================


class TestRegistryMigration:
    def test_builtin_command_catalog_is_complete_and_fresh(self):
        from core.builtin_command_catalog import PANEL_COMMAND_IDS, build_builtin_command_definitions

        first = build_builtin_command_definitions()
        second = build_builtin_command_definitions()
        ids = [cmd.id for cmd in first]

        assert len(ids) >= 25
        assert len(ids) == len(set(ids))
        assert {"clean-cache", "config-repair", "git", "plugin-reload"}.issubset(ids)
        assert PANEL_COMMAND_IDS.issubset(set(ids))
        assert first[0] is not second[0]

    def test_migrate_slash_commands_preserves_count(self):
        reg = CommandRegistry()
        count = reg.migrate_slash_commands()
        # SLASH_COMMANDS has 32 entries
        assert count > 20
        assert reg.count() == count
        # Sampled command should exist
        assert reg.get("config") is not None
        assert reg.get("help") is not None
        assert reg.get("about") is not None

    def test_migrate_slash_commands_callback_handler(self):
        reg = CommandRegistry()
        reg.migrate_slash_commands()
        cmd = reg.get("config")
        assert cmd is not None
        assert isinstance(cmd.handler, _CallbackHandler)
        assert cmd.handler._callback_name == "show_config_window"
        assert cmd.interaction_mode == COMMAND_INTERACTION_DIRECT

    def test_migrate_slash_commands_aliases(self):
        reg = CommandRegistry()
        reg.migrate_slash_commands()
        # "配置" is a Chinese alias for "config"
        assert reg.get_canonical("配置") == "config"
        assert reg.get_canonical("settings") == "config"
        assert reg.get_canonical("exit") == "quit"

    def test_migrate_slash_commands_preserves_category(self):
        reg = CommandRegistry()
        reg.migrate_slash_commands()
        assert reg.get("topmost").category == "window"
        assert reg.get("help").category == "help"
        assert reg.get("control") is None
        assert reg.get("win-settings") is None
        assert reg.get("config").category == "system"

    def test_migrate_builtin_aliases(self):
        reg = CommandRegistry()
        reg.migrate_builtin_aliases()
        # Should have registered commands not in SLASH_COMMANDS
        assert reg.count() > 0

    def test_migrate_both_no_duplicates(self):
        reg = CommandRegistry()
        c1 = reg.migrate_slash_commands()
        reg.migrate_builtin_aliases()
        # No duplicates — total should be at least max(c1, c2)
        assert reg.count() >= c1

    def test_migrate_slash_commands_merges_existing_command_aliases_without_warning(self, caplog):
        reg = CommandRegistry()
        reg.register(
            CommandDefinition(
                id="wifi",
                title="Wi-Fi",
                aliases=["wifi"],
                description="new command",
                category="system",
                handler=lambda ctx: CommandResult(success=True),
                interaction_mode=COMMAND_INTERACTION_PANEL,
            )
        )

        count = reg.migrate_slash_commands()

        assert count > 20
        assert reg.get("wifi").interaction_mode == COMMAND_INTERACTION_PANEL
        assert reg.get_canonical("wlan") == "wifi"
        assert reg.get_canonical("无线密码") == "wifi"
        assert "重复命令 ID" not in caplog.text


# ============================================================
# Integration: slash_commands.py redirection
# ============================================================


class TestSlashCommandsRedirect:
    def setup_method(self):
        """Ensure the global registry is populated before each redirect test."""
        from core import ensure_registry_initialized

        ensure_registry_initialized()

    def test_find_matching_via_registry(self):
        """When registry has data, find_matching_commands should use it."""
        from core.slash_commands import find_matching_commands

        results = find_matching_commands("config")
        assert len(results) >= 1
        cmd = results[0]
        assert cmd.canonical == "config"
        assert "设置" in cmd.aliases or "配置" in cmd.aliases or "settings" in cmd.aliases

    def test_find_matching_chinese(self):
        from core.slash_commands import find_matching_commands

        results = find_matching_commands("配置")
        assert len(results) >= 1
        assert results[0].canonical == "config"

    def test_get_command_by_alias(self):
        from core.slash_commands import get_command_by_alias

        cmd = get_command_by_alias("help")
        assert cmd is not None
        assert cmd.canonical == "help"

    def test_get_command_by_alias_chinese(self):
        from core.slash_commands import get_command_by_alias

        cmd = get_command_by_alias("帮助")
        assert cmd is not None
        assert cmd.canonical == "help"

    def test_handler_name_preserved(self):
        """The handler field must remain the callback name for old dispatch."""
        from core.slash_commands import get_command_by_alias

        cmd = get_command_by_alias("config")
        assert cmd is not None
        assert cmd.handler == "show_config_window"  # callback name, not "config"

    def test_builtin_interaction_modes(self):
        from core import registry

        assert registry.get("wifi").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("hosts").metadata.requires_admin is True
        assert registry.get("hosts").metadata.modifies_system is True
        assert registry.get("netdiag").metadata.uses_network is True
        assert registry.get("git").metadata.modifies_system is True
        assert registry.get("env").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("god").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("netdiag").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("cidr").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("tls").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("path-audit").interaction_mode == COMMAND_INTERACTION_PANEL
        assert registry.get("fav-list") is None
        assert registry.get("fav-add") is None
        assert registry.get("fav-remove") is None
        assert registry.get("clean") is None
        assert registry.get("perf") is None


# ============================================================
# Phase 2: result pipe tests
# ============================================================


class TestPhase2ResultPipe:
    def teardown_method(self):
        take_pending_command_result()  # clear between tests

    def test_set_take(self):
        r = CommandResult(success=True, message="hello")
        set_pending_command_result(r)
        got = take_pending_command_result()
        assert got is r

    def test_take_clears(self):
        set_pending_command_result(CommandResult(success=True))
        take_pending_command_result()
        assert take_pending_command_result() is None

    def test_take_empty_returns_none(self):
        assert take_pending_command_result() is None

    def test_single_slot_thread_safe_smoke(self):
        import threading

        results = []

        def worker(index):
            result = CommandResult(success=True, message=str(index))
            set_pending_command_result(result)
            taken = take_pending_command_result()
            if taken is not None:
                results.append(taken.message)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert all(value.isdigit() for value in results)


# ============================================================
# Phase 2: command handler tests
# ============================================================


class TestPhase2UuidCommand:
    def test_returns_uuid_string(self):
        from core.commands import cmd_uuid

        result = cmd_uuid(CommandContext(raw_input="/uuid"))
        assert result.success is True
        assert len(result.message) == 36
        assert result.message.count("-") == 4

    def test_has_copy_action(self):
        from core.commands import cmd_uuid

        result = cmd_uuid(CommandContext(raw_input="/uuid"))
        assert result.actions
        assert result.actions[0].type == "copy"
        assert result.actions[0].value == result.message


class TestPhase2TimestampCommand:
    def test_no_args_returns_current(self):
        from core.commands import cmd_timestamp

        result = cmd_timestamp(CommandContext(raw_input="/timestamp"))
        assert result.success is True
        assert ":" in result.message  # contains time

    def test_with_seconds_timestamp(self):
        from core.commands import cmd_timestamp

        result = cmd_timestamp(CommandContext(raw_input="/timestamp 1700000000", args_text="1700000000"))
        assert result.success is True
        # 1700000000 → 2023-11-14
        assert "2023" in result.message or "2024" in result.message

    def test_invalid_timestamp_returns_error(self):
        from core.commands import cmd_timestamp

        result = cmd_timestamp(CommandContext(raw_input="/timestamp abcd", args_text="abcd"))
        assert result.success is False
        assert result.error

    def test_negative_timestamp_returns_error(self):
        from core.commands import cmd_timestamp

        result = cmd_timestamp(CommandContext(raw_input="/timestamp -1", args_text="-1"))
        assert result.success is False


class TestPhase2Base64Command:
    def test_encode_default(self):
        from core.commands import cmd_base64

        result = cmd_base64(CommandContext(raw_input="/base64", args_text="hello"))
        assert result.success is True
        assert result.message == "aGVsbG8="

    def test_encode_chinese(self):
        from core.commands import cmd_base64

        result = cmd_base64(CommandContext(raw_input="/base64", args_text="你好"))
        assert result.success is True
        assert isinstance(result.message, str)

    def test_decode(self):
        from core.commands import cmd_base64

        ctx = CommandContext(raw_input="/base64", args_text="decode aGVsbG8=")
        result = cmd_base64(ctx)
        assert result.success is True
        assert result.message == "hello"

    def test_decode_via_args_dict(self):
        from core.commands import cmd_base64

        ctx = CommandContext(raw_input="/base64", args_text="aGVsbG8=")
        ctx.args = {"mode": "decode"}
        result = cmd_base64(ctx)
        assert result.success is True
        assert result.message == "hello"

    def test_empty_input_returns_error(self):
        from core.commands import cmd_base64

        result = cmd_base64(CommandContext(raw_input="/base64"))
        assert result.success is False

    def test_decode_invalid_base64(self):
        from core.commands import cmd_base64

        ctx = CommandContext(raw_input="/base64", args_text="decode !!!invalid!!!")
        result = cmd_base64(ctx)
        assert result.success is False

    def test_oversized_input(self):
        from core.commands import cmd_base64

        big_text = "x" * 300000
        result = cmd_base64(CommandContext(raw_input="/base64", args_text=big_text))
        assert result.success is False


# ============================================================
# Phase 2: registration tests (via ensure_registry_initialized)
# ============================================================


class TestBuiltinRegistration:
    _HANDLERS = [
        "cmd_uuid",
        "cmd_timestamp",
        "cmd_base64",
        "cmd_urlencode",
        "cmd_color",
        "cmd_ip",
        "cmd_copy_path",
        "cmd_hash",
        "cmd_qr",
        "cmd_plugin_list",
        "cmd_plugin_reload",
        "cmd_plugin_new",
        "cmd_clean_cache",
    ]

    def _import_all(self):
        from core.commands import (
            cmd_base64,
            cmd_clean_cache,
            cmd_color,
            cmd_copy_path,
            cmd_hash,
            cmd_ip,
            cmd_plugin_list,
            cmd_plugin_new,
            cmd_plugin_reload,
            cmd_qr,
            cmd_timestamp,
            cmd_urlencode,
            cmd_uuid,
        )

        return (
            cmd_uuid,
            cmd_timestamp,
            cmd_base64,
            cmd_urlencode,
            cmd_color,
            cmd_ip,
            cmd_copy_path,
            cmd_hash,
            cmd_qr,
            cmd_plugin_list,
            cmd_plugin_reload,
            cmd_plugin_new,
            cmd_clean_cache,
        )

    def test_builtin_commands_have_correct_defs(self):
        for fn in self._import_all():
            assert callable(fn)

    def test_handlers_are_not_callback_handler(self):
        for fn in self._import_all():
            assert not isinstance(fn, _CallbackHandler)

    def test_builtin_commands_work_via_registry(self):
        reg = CommandRegistry()
        from core.command_registry import CommandDefinition

        handlers = self._import_all()
        ids = [
            "uuid",
            "timestamp",
            "base64",
            "urlencode",
            "color",
            "ip",
            "copy-path",
            "hash",
            "qr",
            "plugin-list",
            "plugin-reload",
            "plugin-new",
            "clean-cache",
        ]
        defs = [
            CommandDefinition(id=i, title=i, aliases=[i], description="", category="", handler=h)
            for i, h in zip(ids, handlers)
        ]
        for cmd in defs:
            assert reg.register(cmd) is True
        for cmd in defs:
            assert reg.get(cmd.id) is not None, f"{cmd.id} should be registered"


# ============================================================
# Phase 3: command handler tests
# ============================================================


class TestPhase3UrlencodeCommand:
    def test_encode(self):
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode", args_text="hello world"))
        assert r.success and r.message == "hello%20world"

    def test_decode(self):
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode", args_text="decode hello%2Bworld"))
        assert r.success and r.message == "hello+world"

    def test_chinese_encode(self):
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode", args_text="你好"))
        assert r.success and "%" in r.message

    def test_empty_input(self):
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode"))
        assert r.success is False

    def test_decode_symbols(self):
        """Percent-encoding decode: %20 → space."""
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode", args_text="decode hello%20world"))
        assert r.success and r.message == "hello world"

    def test_decode_invalid_keeps_original(self):
        """urllib.parse.unquote is lenient — invalid % sequences are kept as-is."""
        from core.commands import cmd_urlencode

        r = cmd_urlencode(CommandContext(raw_input="/urlencode", args_text="decode %ZZ"))
        assert r.success
        assert "%ZZ" in r.message


class TestPhase3ColorCommand:
    def test_full_hex(self):
        from core.commands import cmd_color

        r = cmd_color(CommandContext(raw_input="/color", args_text="#ff8800"))
        assert r.success
        assert "255" in r.message and "136" in r.message

    def test_short_hex(self):
        from core.commands import cmd_color

        r = cmd_color(CommandContext(raw_input="/color", args_text="#fff"))
        assert r.success
        assert "255" in r.message

    def test_invalid(self):
        from core.commands import cmd_color

        r = cmd_color(CommandContext(raw_input="/color", args_text="notacolor"))
        assert r.success is False

    def test_copy_actions(self):
        from core.commands import cmd_color

        r = cmd_color(CommandContext(raw_input="/color", args_text="#ff8800"))
        assert len(r.actions) == 2
        assert r.actions[0].type == "copy"


class TestPhase3IpCommand:
    def test_returns_ip(self):
        from core.commands import cmd_ip

        r = cmd_ip(CommandContext(raw_input="/ip"))
        assert r.success
        assert "." in r.message

    def test_has_copy_action(self):
        from core.commands import cmd_ip

        r = cmd_ip(CommandContext(raw_input="/ip"))
        assert r.actions and r.actions[0].type == "copy"

    def test_copy_actions_are_limited_to_local_and_public(self, monkeypatch):
        from core import commands

        monkeypatch.setattr(commands, "_get_primary_local_ip", lambda: "192.168.1.8")
        monkeypatch.setattr(
            commands,
            "_get_local_ipv4_addresses",
            lambda: [("192.168.1.8", "Wi-Fi")],
        )
        monkeypatch.setattr(commands, "_fetch_public_ip", lambda timeout=2.0: ("203.0.113.8", ""))

        r = commands.cmd_ip(CommandContext(raw_input="/ip"))

        assert r.success is True
        assert [a.label for a in r.actions] == ["复制内网 IP", "复制公网 IP"]


class TestPhase3CopyPathCommand:
    def test_needs_selected_files(self):
        from core.commands import cmd_copy_path

        r = cmd_copy_path(CommandContext(raw_input="/copy-path"))
        assert r.success is False

    def test_returns_path_from_selection(self):
        from core.commands import cmd_copy_path

        r = cmd_copy_path(
            CommandContext(
                raw_input="/copy-path",
                selected_files=["C:/test.txt"],
            )
        )
        assert r.success is True
        assert r.message == "C:/test.txt"

    def test_name_mode(self):
        from core.commands import cmd_copy_path

        r = cmd_copy_path(
            CommandContext(
                raw_input="/copy-path",
                args_text="name",
                selected_files=["C:/test.txt"],
            )
        )
        assert r.success and r.message == "test.txt"

    def test_dir_mode(self):
        from core.commands import cmd_copy_path

        r = cmd_copy_path(
            CommandContext(
                raw_input="/copy-path",
                args_text="dir",
                selected_files=["C:/test.txt"],
            )
        )
        assert r.success and r.message == "C:/"

    def test_multi_files(self):
        from core.commands import cmd_copy_path

        r = cmd_copy_path(
            CommandContext(
                raw_input="/copy-path",
                selected_files=["C:/a.txt", "D:/b.txt"],
            )
        )
        assert r.success
        assert r.message == "C:/a.txt\nD:/b.txt"


class TestPhase3HashCommand:
    def test_no_file_returns_error(self):
        from core.commands import cmd_hash

        r = cmd_hash(CommandContext(raw_input="/hash"))
        assert r.success is False

    def test_missing_file_returns_error(self):
        from core.commands import cmd_hash

        r = cmd_hash(CommandContext(raw_input="/hash", args_text="/nonexistent/file.txt"))
        assert r.success is False

    def test_args_format_algo_first(self):
        """/hash md5 /some/path"""
        from core.commands import cmd_hash

        # File doesn't exist, so we just check the parsing path doesn't crash
        r = cmd_hash(CommandContext(raw_input="/hash", args_text="md5 /nonexistent/file.txt"))
        assert r.success is False

    def test_has_copy_action_on_success(self):
        """When file exists, hash returns a copy action."""
        import tempfile

        from core.commands import cmd_hash

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            r = cmd_hash(CommandContext(raw_input="/hash", args_text=path))
            assert r.success is True
            assert r.actions and r.actions[0].type == "copy"
        finally:
            try:
                os.unlink(path)
            except Exception as exc:
                logger.debug("删除临时文件失败: %s", exc, exc_info=True)
                pass

    def test_sha256(self):
        import tempfile

        from core.commands import cmd_hash

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test data")
            path = f.name
        try:
            r = cmd_hash(CommandContext(raw_input="/hash", args_text=f"sha256 {path}"))
            assert r.success is True
            assert "SHA256" in r.message
        finally:
            try:
                os.unlink(path)
            except Exception as exc:
                logger.debug("删除临时文件失败: %s", exc, exc_info=True)
                pass


class TestPhase3QrCommand:
    def test_empty_input_returns_error(self):
        from core.commands import cmd_qr

        r = cmd_qr(CommandContext(raw_input="/qr"))
        assert r.success is False

    def test_returns_success_with_text(self):
        from core.commands import cmd_qr

        r = cmd_qr(CommandContext(raw_input="/qr", args_text="hello"))
        assert r.success is True
        assert r.message == "hello"
        assert r.display_type == "qr"

    def test_oversized_input_returns_error(self):
        from core.commands import cmd_qr

        long_text = "x" * 1025
        r = cmd_qr(CommandContext(raw_input="/qr", args_text=long_text))
        assert r.success is False

    def test_has_copy_and_open_actions(self):
        from core.commands import cmd_qr

        r = cmd_qr(CommandContext(raw_input="/qr", args_text="test qr"))
        assert r.success is True
        assert len(r.actions) == 2
        assert r.actions[0].type == "open_file"
        assert r.actions[1].type == "save_file"

    def test_payload_has_image_path(self):
        from core.commands import cmd_qr

        r = cmd_qr(CommandContext(raw_input="/qr", args_text="hello"))
        assert r.success is True
        assert "image_path" in r.payload
        assert r.payload["image_path"].endswith(".png")


# ============================================================
# Phase 5: plugin management command tests
# ============================================================


class TestPhase5PluginCommands:
    def test_plugin_list_no_manager(self):
        """When plugin_manager is None, list should return an error."""
        from core.commands import cmd_plugin_list

        r = cmd_plugin_list(CommandContext(raw_input="/plugin-list"))
        assert r.success is False

    def test_plugin_reload_no_manager(self):
        from core.commands import cmd_plugin_reload

        r = cmd_plugin_reload(CommandContext(raw_input="/plugin-reload"))
        assert r.success is False

    def test_plugin_new_no_manager(self):
        from core.commands import cmd_plugin_new

        r = cmd_plugin_new(CommandContext(raw_input="/plugin-new"))
        assert r.success is False

    def test_plugin_new_missing_id(self):
        from core.commands import cmd_plugin_new

        # Without plugin_manager, returns uninitialized error
        r = cmd_plugin_new(CommandContext(raw_input="/plugin-new"))
        assert r.success is False

    def test_plugin_new_invalid_id(self):
        from core.commands import cmd_plugin_new

        # Without plugin_manager, returns uninitialized error
        r = cmd_plugin_new(CommandContext(raw_input="/plugin-new", args_text="hello world!"))
        assert r.success is False


def test_execute_search_sources_runs_sources_with_bounded_timeout(monkeypatch):
    monkeypatch.setattr(command_registry, "SEARCH_SOURCE_TIMEOUT_SECONDS", 0.01)
    errors = []

    def fast(query):
        return [{"id": "fast", "title": f"Fast {query}", "command": "echo fast"}]

    def slow(query):
        time.sleep(1)
        return [{"id": "slow", "title": "Slow", "command": "echo slow"}]

    try:
        assert register_search_source(
            "test_fast_source",
            {"plugin_id": "fast_plugin", "handler": fast, "error_callback": lambda *args: errors.append(args)},
        )
        assert register_search_source(
            "test_slow_source",
            {"plugin_id": "slow_plugin", "handler": slow, "error_callback": lambda *args: errors.append(args)},
        )

        results = execute_search_sources("x", timeout=0.05)
    finally:
        remove_search_source("test_fast_source", plugin_id="fast_plugin")
        remove_search_source("test_slow_source", plugin_id="slow_plugin")

    flattened = {item["id"] for _source_id, _source_info, items in results for item in items}
    assert "fast" in flattened
    assert "slow" not in flattened
    assert errors


def test_execute_search_sources_does_not_nested_submit_to_same_pool(monkeypatch):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(command_registry, "_get_search_pool", lambda: pool)

    def first(query):
        return [{"id": "first", "title": query, "command": "echo first"}]

    def second(query):
        return [{"id": "second", "title": query, "command": "echo second"}]

    try:
        assert register_search_source("test_single_pool_first", {"plugin_id": "p1", "handler": first})
        assert register_search_source("test_single_pool_second", {"plugin_id": "p2", "handler": second})

        results = execute_search_sources("q", timeout=1.0)
    finally:
        remove_search_source("test_single_pool_first", plugin_id="p1")
        remove_search_source("test_single_pool_second", plugin_id="p2")
        pool.shutdown(wait=False, cancel_futures=True)

    flattened = {item["id"] for _source_id, _source_info, items in results for item in items}
    assert {"first", "second"}.issubset(flattened)
