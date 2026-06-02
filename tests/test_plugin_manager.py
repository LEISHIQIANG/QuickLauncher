"""Tests for core/plugin_manager.py — plugin scanning, loading, and lifecycle."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

import pytest

from core.command_registry import CommandAction, CommandContext, CommandParam, CommandRegistry, CommandResult
from core.plugin_manager import (
    HIGH_RISK_PERMISSIONS,
    PERMISSIONS_KNOWN,
    PluginAPI,
    PluginManager,
    PluginManifest,
    has_high_risk_permissions,
    validate_manifest,
)

# ============================================================
# Manifest validation tests
# ============================================================


def test_valid_manifest():
    m = PluginManifest(
        id="text_tools",
        name="Text Tools",
        version="1.0.0",
        description="Text processing commands",
        author="Test",
        entry="main.py",
        permissions=["clipboard.read", "clipboard.write"],
        commands=[{"id": "text_tools.reverse", "title": "Reverse"}],
    )
    assert validate_manifest(m) == ""


def test_missing_id():
    m = PluginManifest(id="", name="Test", version="1.0")
    assert "缺少 plugin.id" in validate_manifest(m)


def test_missing_name():
    m = PluginManifest(id="test", name="", version="1.0")
    assert "缺少 plugin.name" in validate_manifest(m)


def test_missing_version():
    m = PluginManifest(id="test", name="Test", version="")
    assert "缺少 plugin.version" in validate_manifest(m)


def test_unknown_permission():
    m = PluginManifest(
        id="test",
        name="Test",
        version="1.0",
        permissions=["unknown.perm"],
    )
    err = validate_manifest(m)
    assert "未知权限" in err


def test_known_permissions():
    assert "clipboard.read" in PERMISSIONS_KNOWN
    assert "process.run" in PERMISSIONS_KNOWN
    assert "network.request" in PERMISSIONS_KNOWN


def test_high_risk_permissions():
    assert has_high_risk_permissions(["process.run"]) is True
    assert has_high_risk_permissions(["clipboard.read"]) is False
    assert has_high_risk_permissions(["file.write", "admin.required"]) is True


def test_plugin_launch_target_uses_shortcut_privilege_path(monkeypatch):
    import core.shortcut_executor as shortcut_executor

    captured = {}

    def fake_launch(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
        captured.update(
            target=target,
            parameters=parameters,
            directory=directory,
            show_cmd=show_cmd,
            run_as_admin=run_as_admin,
        )
        return True, ""

    monkeypatch.setattr(shortcut_executor.ShortcutExecutor, "_launch_with_privilege", staticmethod(fake_launch))

    api = PluginAPI("tools", ".", ["process.run", "admin.required"], CommandRegistry())
    ok, error = api.launch_target(
        r"C:\Tools\App.exe",
        ["--flag", "value"],
        r"C:\Tools",
        show_window=False,
        run_as_admin=True,
    )

    assert ok is True
    assert error == ""
    assert captured["target"] == r"C:\Tools\App.exe"
    assert captured["parameters"] == "--flag value"
    assert captured["directory"] == r"C:\Tools"
    assert captured["show_cmd"] == 0
    assert captured["run_as_admin"] is True


def test_plugin_launch_target_requires_permissions():
    api = PluginAPI("tools", ".", [], CommandRegistry())

    with pytest.raises(PermissionError):
        api.launch_target(r"C:\Tools\App.exe")

    api = PluginAPI("tools", ".", ["process.run"], CommandRegistry())
    with pytest.raises(PermissionError):
        api.launch_target(r"C:\Tools\App.exe", run_as_admin=True)


def test_plugin_run_command_uses_icon_command_privilege_path(monkeypatch):
    import core.shortcut_executor as shortcut_executor

    captured = {}

    def fake_launch(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
        captured.update(
            target=target,
            parameters=parameters,
            directory=directory,
            show_cmd=show_cmd,
            run_as_admin=run_as_admin,
        )
        return True, ""

    monkeypatch.setattr(shortcut_executor.ShortcutExecutor, "_launch_with_privilege", staticmethod(fake_launch))
    monkeypatch.setenv("ComSpec", r"C:\Windows\System32\cmd.exe")

    api = PluginAPI("tools", ".", ["process.run"], CommandRegistry())
    ok, error = api.run_command("echo hello", cwd=r"C:\Temp", show_window=False)

    assert ok is True
    assert error == ""
    assert captured["target"] == r"C:\Windows\System32\cmd.exe"
    assert "/c" in captured["parameters"]
    assert "echo hello" in captured["parameters"]
    assert captured["directory"] == r"C:\Temp"
    assert captured["show_cmd"] == 0
    assert captured["run_as_admin"] is False


def test_command_id_must_have_dot():
    m = PluginManifest(
        id="test",
        name="Test",
        version="1.0",
        commands=[{"id": "nodot"}],
    )
    err = validate_manifest(m)
    assert "点号" in err


# ============================================================
# PluginManager scanning tests
# ============================================================


def _create_plugin_dir(base: str, plugin_id: str, **overrides) -> str:
    d = os.path.join(base, plugin_id)
    os.makedirs(d, exist_ok=True)
    manifest = {
        "id": overrides.get("id", plugin_id),
        "name": overrides.get("name", plugin_id.replace("_", " ").title()),
        "version": overrides.get("version", "1.0.0"),
        "description": overrides.get("description", ""),
        "author": overrides.get("author", "Test"),
        "entry": overrides.get("entry", "main.py"),
        "permissions": overrides.get("permissions", []),
        "commands": overrides.get("commands", []),
    }
    with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    # Create main.py
    main_py = overrides.get("main_py", "")
    with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
        f.write(main_py)
    return d


class TestPluginManagerScan:
    def test_scan_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert plugins == []

    def test_scan_single_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "hello_world", permissions=["clipboard.read"])
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 1
            assert plugins[0].manifest.id == "hello_world"
            assert plugins[0].status == "loaded"

    def test_scan_multiple_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "text_tools")
            _create_plugin_dir(tmp, "dev_tools")
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 2

    def test_scan_skips_non_plugin_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "good_plugin")
            os.makedirs(os.path.join(tmp, "no_manifest"), exist_ok=True)
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 1

    def test_scan_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "bad_plugin")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "plugin.json"), "w") as f:
                f.write("not json")
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 1
            assert plugins[0].status == "error"

    def test_scan_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "bad_plugin")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "", "name": ""}, f)
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 1
            assert plugins[0].status == "error"

    def test_scan_missing_entry_file_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "missing_entry")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "id": "missing_entry",
                        "name": "Missing Entry",
                        "version": "1.0.0",
                        "entry": "main.py",
                    },
                    f,
                )
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            plugins = pm.scan_plugins()
            assert len(plugins) == 1
            assert plugins[0].status == "error"
            assert "入口文件不存在" in plugins[0].error


# ============================================================
# PluginManager load/enable tests
# ============================================================


_SAMPLE_MAIN_PY = """\
def register(api):
    api.register_command(
        id="sample.hello",
        title="Hello",
        aliases=["hello", "hi"],
        description="Say hello",
        category="test",
        handler=lambda ctx: __import__("core.command_registry",
            fromlist=["CommandResult"]).CommandResult(
            success=True, message="Hello from plugin!"
        ),
    )
"""


_SAMPLE_MAIN_WITH_ERROR = """\
def register(api):
    raise RuntimeError("plugin error")
"""

_SAMPLE_MAIN_COMMAND_FAILURE = """\
def fail(ctx):
    raise RuntimeError("boom")

def register(api):
    api.register_command(
        id="fail_plugin.fail",
        title="Fail",
        aliases=["fail"],
        description="",
        category="test",
        handler=fail,
)
"""

_SAMPLE_MAIN_COMMAND_TIMEOUT = """\
import time

def slow(ctx):
    time.sleep(0.2)
    return {"success": True, "message": "too late"}

def register(api):
    api.register_command(
        id="timeout_plugin.slow",
        title="Slow",
        aliases=["slow"],
        description="",
        category="test",
        handler=slow,
    )
"""

_SAMPLE_MAIN_SEARCH_FAILURE = """\
def search(query):
    raise RuntimeError("search boom")

def register(api):
    api.register_search_source("search_plugin_search", search)
"""

_SAMPLE_MAIN_CHAIN_PROCESSOR = """\
def reverse_text(args):
    text = str(args.get("text", ""))
    return {"outputs": {"output": text[::-1], "length": str(len(text))}}

def register(api):
    assert api.register_chain_processor(
        {
            "id": "reverse_text",
            "title": "反转文本",
            "category": "插件电池",
            "description": "反转输入文本。",
            "inputs": [{"id": "text", "kind": "text", "required": True}],
            "outputs": [{"id": "output", "kind": "text"}, {"id": "length", "kind": "number"}],
            "params": [{"id": "text", "kind": "text", "required": True}],
            "safety": {"level": "safe", "capability": "chain.processor.chain_tools_reverse_text"},
            "examples": [{"title": "反转文本示例", "args": {"text": "abc"}}],
        },
        reverse_text,
    )
"""


class TestPluginManagerLoad:
    def test_load_and_enable_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            ok = pm.load_plugin("sample")
            assert ok is True
            info = pm.get_plugin("sample")
            assert info is not None
            assert info.status == "enabled"
            assert "sample.hello" in info.registered_commands
            assert reg.get("sample.hello") is not None

    def test_disable_plugin_removes_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            pm.load_plugin("sample")
            assert reg.get("sample.hello") is not None
            ok = pm.disable_plugin("sample")
            assert ok is True
            assert reg.get("sample.hello") is None
            info = pm.get_plugin("sample")
            assert info.status == "disabled"

    def test_plugin_can_register_and_cleanup_chain_processor(self):
        from core.chain_processors import execute_chain_processor, processor_definition

        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "chain_tools", main_py=_SAMPLE_MAIN_CHAIN_PROCESSOR)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()

            assert pm.enable_plugin("chain_tools")
            info = pm.get_plugin("chain_tools")
            assert "chain_tools_reverse_text" in info.registered_chain_processors
            definition = processor_definition("chain_tools_reverse_text")
            assert definition is not None
            assert definition.title == "反转文本"
            result = execute_chain_processor("chain_tools_reverse_text", {"text": "abc"})
            assert result.success is True
            assert result.message == "cba"
            assert result.payload["outputs"]["length"] == "3"

            assert pm.disable_plugin("chain_tools")
            assert processor_definition("chain_tools_reverse_text") is None
            result = execute_chain_processor("chain_tools_reverse_text", {"text": "abc"})
            assert result.success is False
            assert result.error == "Unknown processor"

    def test_load_error_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "bad", main_py=_SAMPLE_MAIN_WITH_ERROR)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            ok = pm.load_plugin("bad")
            assert ok is False
            info = pm.get_plugin("bad")
            assert info.status == "error"
            assert info.error != ""

    def test_reload_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            pm.load_plugin("sample")
            assert reg.get("sample.hello") is not None
            ok = pm.reload_plugin("sample")
            assert ok is True
            assert reg.get("sample.hello") is not None

    def test_enable_nonexistent_plugin(self):
        reg = CommandRegistry()
        pm = PluginManager(reg, plugins_dir=tempfile.gettempdir())
        ok = pm.enable_plugin("nonexistent")
        assert ok is False

    def test_enable_plugin_invokes_interactive_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()

            confirmed = []
            pm.set_confirm_high_risk_callback(lambda info: confirmed.append(info.manifest.id) or True)

            ok = pm.enable_plugin("sample")

            assert ok is True
            assert confirmed == ["sample"]

    def test_auto_enable_skips_interactive_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()

            pm.set_confirm_high_risk_callback(lambda info: pytest.fail("auto_enable should not prompt"))

            count = pm.auto_enable(["sample"])

            assert count == 1
            assert pm.get_plugin("sample").status == "enabled"

    def test_enable_disable_save_enabled_plugin_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            saved = []
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp, save_callback=lambda ids: saved.append(list(ids)))
            pm.scan_plugins()

            assert pm.enable_plugin("sample")
            assert saved[-1] == ["sample"]

            assert pm.disable_plugin("sample")
            assert saved[-1] == []

    def test_auto_enable_restores_saved_plugins_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)

            first = PluginManager(CommandRegistry(), plugins_dir=tmp)
            first.scan_plugins()
            assert first.enable_plugin("sample")
            saved_ids = [p.manifest.id for p in first.list_enabled()]

            second_reg = CommandRegistry()
            second = PluginManager(second_reg, plugins_dir=tmp)
            second.scan_plugins()
            assert second.auto_enable(saved_ids) == 1

            assert second.get_plugin("sample").status == "enabled"
            assert second_reg.get("sample.hello") is not None

    def test_repeated_command_failures_quarantine_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "fail_plugin", main_py=_SAMPLE_MAIN_COMMAND_FAILURE)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            assert pm.enable_plugin("fail_plugin")
            handler = reg.get("fail_plugin.fail").handler

            for _ in range(3):
                result = handler(CommandContext())
                assert result.success is False

            info = pm.get_plugin("fail_plugin")
            assert info.status == "quarantined"
            assert info.quarantined is True
            assert reg.get("fail_plugin.fail") is None
            state_path = os.path.join(tmp, ".config", "plugin_state.json")
            with open(state_path, encoding="utf-8") as handle:
                state = json.load(handle)
            assert state["plugins"]["fail_plugin"]["status"] == "quarantined"
            assert os.path.exists(os.path.join(tmp, ".config", "plugin_errors.jsonl"))

    def test_plugin_command_timeout_returns_without_waiting_for_handler(self, monkeypatch):
        import core.plugin_manager as plugin_manager

        monkeypatch.setattr(plugin_manager, "PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS", 0.01)
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "timeout_plugin", main_py=_SAMPLE_MAIN_COMMAND_TIMEOUT)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            assert pm.enable_plugin("timeout_plugin")
            handler = reg.get("timeout_plugin.slow").handler

            started = time.perf_counter()
            result = handler(CommandContext())
            elapsed = time.perf_counter() - started

            assert result.success is False
            assert result.error == "timeout"
            assert elapsed < 0.15

    def test_auto_enable_skips_persisted_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "fail_plugin", main_py=_SAMPLE_MAIN_COMMAND_FAILURE)
            reg = CommandRegistry()
            first = PluginManager(reg, plugins_dir=tmp)
            first.scan_plugins()
            assert first.enable_plugin("fail_plugin")
            handler = reg.get("fail_plugin.fail").handler
            for _ in range(3):
                handler(CommandContext())

            second = PluginManager(CommandRegistry(), plugins_dir=tmp)
            second.scan_plugins()

            assert second.auto_enable(["fail_plugin"]) == 0
            assert second.get_plugin("fail_plugin").status == "quarantined"

    def test_repeated_search_source_failures_quarantine_plugin(self):
        from core.command_registry import execute_search_source

        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "search_plugin", main_py=_SAMPLE_MAIN_SEARCH_FAILURE)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            assert pm.enable_plugin("search_plugin")

            for _ in range(3):
                assert execute_search_source("search_plugin_search", "x") == []

            info = pm.get_plugin("search_plugin")
            assert info.status == "quarantined"

    def test_reload_enabled_plugin_keeps_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            saved = []
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp, save_callback=lambda ids: saved.append(list(ids)))
            pm.scan_plugins()
            assert pm.enable_plugin("sample")
            saved.clear()

            assert pm.reload_plugin("sample")

            assert pm.get_plugin("sample").status == "enabled"
            assert saved[-1] == ["sample"]

    def test_scan_plugins_does_not_persist_temporary_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            saved = []
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp, save_callback=lambda ids: saved.append(list(ids)))
            pm.scan_plugins()
            assert pm.enable_plugin("sample")
            saved.clear()

            pm.scan_plugins()

            assert saved == []
            assert reg.get("sample.hello") is None

    def test_load_error_status_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "bad")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "", "name": ""}, f)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            ok = pm.load_plugin("?")
            assert ok is False

    def test_list_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "a", main_py=_SAMPLE_MAIN_PY)
            _create_plugin_dir(tmp, "b", permissions=["clipboard.read"])
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            pm.load_plugin("a")
            enabled = pm.list_enabled()
            assert len(enabled) == 1
            assert enabled[0].manifest.id == "a"


# ============================================================
# PluginAPI tests
# ============================================================


class TestPluginAPI:
    def test_register_command_requires_dot(self):
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="nodot",
            title="Bad",
            aliases=["bad"],
            description="",
            category="",
            handler=lambda ctx: CommandResult(),
        )
        assert ok is False

    def test_register_command_namespace_check(self):
        reg = CommandRegistry()
        api = PluginAPI("text_tools", os.getcwd(), [], reg)
        ok = api.register_command(
            id="other_tools.cmd",
            title="Bad",
            aliases=["bad"],
            description="",
            category="",
            handler=lambda ctx: CommandResult(),
        )
        assert ok is False

    def test_register_command_success(self):
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok = api.register_command(
            id="my_plugin.hello",
            title="Hello",
            aliases=["hello"],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True, message="hi"),
        )
        assert ok is True
        # Command is staged — not yet in registry
        assert reg.get("my_plugin.hello") is None
        # Commit staged commands
        assert api.commit_staged() is True
        assert reg.get("my_plugin.hello") is not None
        assert "my_plugin.hello" in api._registered_ids

    def test_register_command_result_window_size(self):
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok = api.register_command(
            id="my_plugin.panel",
            title="Panel",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
            result_window_size="large",
        )
        assert ok is True
        assert api.commit_staged() is True
        assert reg.get("my_plugin.panel").result_window_size == "large"

    def test_register_command_metadata(self):
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok = api.register_command(
            id="my_plugin.clean",
            title="Clean",
            aliases=[],
            description="",
            category="maintenance",
            handler=lambda ctx: CommandResult(success=True),
            risk_level="medium",
            uses_network=True,
            modifies_system=True,
        )

        assert ok is True
        assert api.commit_staged() is True
        metadata = reg.get("my_plugin.clean").metadata
        assert metadata.category == "maintenance"
        assert metadata.risk_level == "medium"
        assert metadata.uses_network is True
        assert metadata.modifies_system is True

    def test_register_command_params(self):
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok = api.register_command(
            id="my_plugin.params",
            title="Params",
            handler=lambda ctx: CommandResult(success=True),
            params=[
                CommandParam(name="name", required=True),
                {"name": "mode", "type": "choice", "choices": ["a", "b"], "default": "a"},
            ],
        )
        assert ok is True
        assert api.commit_staged() is True
        cmd = reg.get("my_plugin.params")
        assert [p.name for p in cmd.params] == ["name", "mode"]
        assert cmd.params[1].choices == ["a", "b"]

    def test_register_chain_processor_api(self):
        from core.chain_processors import (
            execute_chain_processor,
            processor_definition,
            unregister_external_processors,
        )

        unregister_external_processors("my_plugin")
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok = api.register_chain_processor(
            {
                "id": "slugify",
                "title": "Slugify",
                "category": "插件电池",
                "inputs": [{"id": "text", "kind": "text"}],
                "outputs": [{"id": "output", "kind": "text"}],
                "params": [{"id": "text", "kind": "text"}],
                "safety": {"level": "safe", "capability": "chain.processor.my_plugin_slugify"},
                "examples": [{"title": "Slugify 示例", "args": {"text": "Hello World"}}],
            },
            lambda args: {"outputs": {"output": str(args.get("text", "")).lower().replace(" ", "-")}},
        )

        assert ok is True
        assert processor_definition("my_plugin_slugify") is not None
        result = execute_chain_processor("my_plugin_slugify", {"text": "Hello World"})
        assert result.success is True
        assert result.message == "hello-world"
        assert result.payload["outputs"]["output"] == "hello-world"
        unregister_external_processors("my_plugin")
        assert processor_definition("my_plugin_slugify") is None

    def test_permission_check(self):
        api = PluginAPI("test", os.getcwd(), ["clipboard.read"], CommandRegistry())
        api._check_permission("clipboard.read")
        import pytest

        with pytest.raises(PermissionError):
            api._check_permission("process.run")

    def test_read_clipboard_missing_permission(self):
        import pytest

        api = PluginAPI("test", os.getcwd(), [], CommandRegistry())
        with pytest.raises(PermissionError):
            api.read_clipboard()

    def test_data_dir_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = PluginAPI("test", tmp, [], CommandRegistry())
            d = api.data_dir
            assert d.exists()
            assert d.name == "data"

    def test_check_data_path_rejects_sibling_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = PluginAPI("test", os.path.join(tmp, "plugin"), [], CommandRegistry())
            api.data_dir.mkdir(parents=True, exist_ok=True)
            sibling = os.path.join(tmp, "plugin", "data_evil", "x.txt")
            with pytest.raises(PermissionError):
                api.check_data_path(sibling)

            assert api.check_data_path(api.data_dir / "ok.txt").name == "ok.txt"

    def test_high_risk_set(self):
        assert "process.run" in HIGH_RISK_PERMISSIONS
        assert "file.write" in HIGH_RISK_PERMISSIONS
        assert "admin.required" in HIGH_RISK_PERMISSIONS
        assert "clipboard.read" not in HIGH_RISK_PERMISSIONS

    def test_register_duplicate_command_id_rejected(self):
        """Same command ID within same plugin is rejected during commit."""
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        ok1 = api.register_command(
            id="my_plugin.test",
            title="T1",
            aliases=["t1"],
            description="",
            category="",
            handler=lambda ctx: CommandResult(),
        )
        ok2 = api.register_command(
            id="my_plugin.test",
            title="T2",
            aliases=["t2"],
            description="",
            category="",
            handler=lambda ctx: CommandResult(),
        )
        # Both stages succeed (validation passes)
        assert ok1 is True
        assert ok2 is True
        # Commit should fail because second command ID duplicates first
        assert api.commit_staged() is False
        # Registry should have no commands from this plugin (rolled back)
        assert reg.get("my_plugin.test") is None
        assert len(api._registered_ids) == 0

    def test_disable_already_disabled_plugin(self):
        """Disabling an already-disabled plugin is a no-op success."""
        reg = CommandRegistry()
        pm = PluginManager(reg, plugins_dir=tempfile.gettempdir())
        assert pm.disable_plugin("nonexistent") is False
        # Create a plugin, disable it twice
        import tempfile as tf

        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "test_p", main_py=_SAMPLE_MAIN_PY)
            pm2 = PluginManager(reg, plugins_dir=tmp)
            pm2.scan_plugins()
            pm2.load_plugin("test_p")
            assert pm2.disable_plugin("test_p") is True
            assert pm2.disable_plugin("test_p") is True  # already disabled → success

    def test_reload_error_plugin(self):
        """Reloading a plugin that had an error re-attempts loading."""
        import tempfile as tf

        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "broken", main_py=_SAMPLE_MAIN_WITH_ERROR)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            ok = pm.load_plugin("broken")
            assert ok is False
            # Reload (still broken → should fail)
            ok = pm.reload_plugin("broken")
            assert ok is False

    def test_reload_enabled_plugin_failure_does_not_leave_fake_enabled(self):
        """Reload failure after unloading commands should not leave a fake enabled state."""
        import tempfile as tf

        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "sample", main_py=_SAMPLE_MAIN_PY)
            saved = []
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp, save_callback=lambda ids: saved.append(list(ids)))
            pm.scan_plugins()
            assert pm.enable_plugin("sample")
            saved.clear()
            assert reg.get("sample.hello") is not None

            with open(os.path.join(tmp, "sample", "main.py"), "w", encoding="utf-8") as f:
                f.write('def register(api):\n    raise RuntimeError("reload boom")\n')

            assert pm.reload_plugin("sample") is False
            info = pm.get_plugin("sample")
            assert info is not None
            assert info.status == "error"
            assert "reload failed after unloading previous commands" in info.error
            assert reg.get("sample.hello") is None
            assert saved[-1] == []

    def test_failed_plugin_import_cleans_sys_modules(self):
        """A module that fails during import should not be reused from sys.modules."""
        import tempfile as tf

        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(
                tmp,
                "broken_import",
                main_py='raise RuntimeError("import boom")\n\ndef register(api):\n    pass\n',
            )
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            pm.scan_plugins()

            assert pm.load_plugin("broken_import") is False
            assert "_plugin_broken_import" not in sys.modules

    def test_remove_by_owner_cleans_all_commands(self):
        """remove_by_owner should clean all commands for a given plugin owner."""
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        api.register_command(
            id="my_plugin.cmd1",
            title="Cmd1",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        api.register_command(
            id="my_plugin.cmd2",
            title="Cmd2",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        assert api.commit_staged() is True
        assert reg.count() == 2
        # Remove by owner
        removed = reg.remove_by_owner("plugin:my_plugin")
        assert removed == 2
        assert reg.count() == 0

    def test_wrap_handler_converts_dict_to_command_result(self):
        """Plugin handlers returning dicts should be auto-converted."""
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.dict_handler",
            title="Dict",
            aliases=["dict"],
            description="",
            category="test",
            handler=lambda ctx: {"success": True, "message": "from dict"},
        )
        assert ok is True
        assert api.commit_staged() is True
        wrapped = reg.get("test.dict_handler").handler
        result = wrapped(CommandContext())
        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.message == "from dict"

    def test_wrap_handler_keeps_all_result_actions(self):
        """Plugin results keep the full action list for the independent command panel."""
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.action_limit",
            title="Actions",
            aliases=["actions"],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(
                success=True,
                actions=[
                    CommandAction(type="copy", label="A", value="a"),
                    CommandAction(type="copy", label="B", value="b"),
                    CommandAction(type="copy", label="C", value="c"),
                ],
            ),
        )
        assert ok is True
        assert api.commit_staged() is True
        result = reg.get("test.action_limit").handler(CommandContext())
        assert [action.label for action in result.actions] == ["A", "B", "C"]

    def test_wrap_handler_converts_dict_action_fields(self):
        """Plugin dict actions may use the extended command panel action fields."""
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.dict_actions",
            title="Actions",
            aliases=["actions"],
            description="",
            category="test",
            handler=lambda ctx: {
                "success": True,
                "actions": [
                    {
                        "type": "open_url",
                        "label": "Open",
                        "value": "https://example.com",
                        "enabled": False,
                        "danger": True,
                        "primary": True,
                        "payload": {"source": "test"},
                    }
                ],
            },
        )
        assert ok is True
        assert api.commit_staged() is True
        result = reg.get("test.dict_actions").handler(CommandContext())
        assert isinstance(result.actions[0], CommandAction)
        assert result.actions[0].enabled is False
        assert result.actions[0].danger is True
        assert result.actions[0].primary is True
        assert result.actions[0].payload == {"source": "test"}

    def test_wrap_handler_filters_unsafe_actions_and_truncates_labels(self):
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.unsafe_actions",
            title="Actions",
            aliases=["actions"],
            description="",
            category="test",
            handler=lambda ctx: {
                "success": True,
                "actions": [
                    {"type": "open_url", "label": "Bad", "value": "javascript:alert(1)"},
                    {"type": "copy", "label": "L" * 200, "value": "ok"},
                    {"type": "unknown", "label": "Unknown", "value": "x"},
                ],
            },
        )
        assert ok is True
        assert api.commit_staged() is True
        result = reg.get("test.unsafe_actions").handler(CommandContext())
        assert len(result.actions) == 1
        assert result.actions[0].type == "copy"
        assert len(result.actions[0].label) == 80

    def test_wrap_handler_none_return(self):
        """Plugin handlers returning None should produce error result."""
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.none_handler",
            title="None",
            aliases=["none"],
            description="",
            category="test",
            handler=lambda ctx: None,
        )
        assert ok is True
        assert api.commit_staged() is True
        wrapped = reg.get("test.none_handler").handler
        result = wrapped(CommandContext())
        assert result.success is False
        assert "未返回结果" in result.message

    def test_wrap_handler_exception(self):
        """Plugin handlers that raise exceptions should produce error result."""
        reg = CommandRegistry()
        api = PluginAPI("test", os.getcwd(), [], reg)
        ok = api.register_command(
            id="test.error_handler",
            title="Error",
            aliases=["err"],
            description="",
            category="test",
            handler=lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert ok is True
        assert api.commit_staged() is True
        wrapped = reg.get("test.error_handler").handler
        result = wrapped(CommandContext())
        assert result.success is False
        assert "boom" in result.message

    def test_search_source_lifecycle(self):
        """Search source staging → commit → appears in global _search_sources."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        api.register_search_source("my_source")
        # Not in global dict before commit
        assert "my_source" not in _search_sources
        assert api.commit_staged() is True
        # Appears after commit
        assert "my_source" in _search_sources
        assert _search_sources["my_source"]["plugin_id"] == "my_plugin"
        # Cleanup for test isolation
        _search_sources.pop("my_source", None)

    def test_register_search_source_keeps_handler(self):
        """Search source handlers should survive staging and commit."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)

        def handler(query):
            return [{"title": query}]

        api.register_search_source("my_handler_source", handler)
        assert api.commit_staged() is True
        try:
            assert _search_sources["my_handler_source"]["handler"] is handler
            assert _search_sources["my_handler_source"]["plugin_id"] == "my_plugin"
        finally:
            _search_sources.pop("my_handler_source", None)

    def test_register_search_source_without_commit(self):
        """Staged search sources are not visible until commit."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        api.register_search_source("staged_only")
        assert "staged_only" not in _search_sources
        assert api._staged_search_sources == ["staged_only"]

    def test_commit_staged_rolls_back_search_sources_on_failure(self):
        """When commit fails, search sources are rolled back along with commands."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        # Register a search source
        api.register_search_source("rollback_source")
        # Register a valid command
        api.register_command(
            id="my_plugin.ok",
            title="Ok",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        # Register a duplicate command (will fail at commit)
        api.register_command(
            id="my_plugin.ok",
            title="Duplicate",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        # Commit fails due to duplicate
        assert api.commit_staged() is False
        # Search source should be rolled back
        assert "rollback_source" not in _search_sources
        # Command should be rolled back
        assert reg.get("my_plugin.ok") is None
        assert len(api._registered_ids) == 0

    def test_search_source_conflict_does_not_overwrite_existing_source(self):
        """A conflicting search source id should fail without replacing the current owner."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        first = PluginAPI("first_plugin", os.getcwd(), [], reg)
        second = PluginAPI("second_plugin", os.getcwd(), [], reg)
        first.register_search_source("shared_source", lambda query: [{"title": "first"}])
        second.register_search_source("shared_source", lambda query: [{"title": "second"}])

        try:
            assert first.commit_staged() is True
            assert second.commit_staged() is False
            assert _search_sources["shared_source"]["plugin_id"] == "first_plugin"
            assert _search_sources["shared_source"]["handler"]("x") == [{"title": "first"}]
        finally:
            _search_sources.pop("shared_source", None)

    def test_search_source_rollback_preserves_existing_owner(self):
        """Rollback should only remove search sources written by the failing plugin."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        first = PluginAPI("first_plugin", os.getcwd(), [], reg)
        first.register_search_source("rollback_shared", lambda query: [{"title": "first"}])
        assert first.commit_staged() is True

        second = PluginAPI("second_plugin", os.getcwd(), [], reg)
        second.register_search_source("second_unique")
        second.register_search_source("rollback_shared")

        try:
            assert second.commit_staged() is False
            assert "second_unique" not in _search_sources
            assert _search_sources["rollback_shared"]["plugin_id"] == "first_plugin"
        finally:
            _search_sources.pop("rollback_shared", None)

    def test_commit_staged_only_search_sources(self):
        """A plugin with only search sources (no commands) commits successfully."""
        from core.command_registry import _search_sources

        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        api.register_search_source("source_only")
        assert api.commit_staged() is True
        assert "source_only" in _search_sources
        _search_sources.pop("source_only", None)

    def test_double_commit_is_noop(self):
        """Calling commit_staged twice succeeds on second call."""
        reg = CommandRegistry()
        api = PluginAPI("my_plugin", os.getcwd(), [], reg)
        api.register_command(
            id="my_plugin.cmd",
            title="Cmd",
            aliases=[],
            description="",
            category="test",
            handler=lambda ctx: CommandResult(success=True),
        )
        assert api.commit_staged() is True
        assert api.commit_staged() is True
        assert reg.get("my_plugin.cmd") is not None

    def test_disable_plugin_cleans_search_sources(self):
        """Disabling a plugin removes its registered search sources."""
        import tempfile as tf

        from core.command_registry import _search_sources

        _SAMPLE_MAIN_WITH_SEARCH = """\
def register(api):
    api.register_command(
        id="search_test.cmd",
        title="Search",
        aliases=[],
        handler=lambda ctx: __import__("core.command_registry",
            fromlist=["CommandResult"]).CommandResult(success=True, message="ok"),
    )
    api.register_search_source("search_test_src")
"""
        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "search_test", main_py=_SAMPLE_MAIN_WITH_SEARCH)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            pm.load_plugin("search_test")
            assert "search_test_src" in _search_sources
            pm.disable_plugin("search_test")
            assert "search_test_src" not in _search_sources
            assert reg.get("search_test.cmd") is None

    def test_disable_plugin_does_not_remove_foreign_search_source(self):
        """Disable cleanup is scoped by plugin owner to avoid cross-plugin source loss."""
        import tempfile as tf

        from core.command_registry import _search_sources

        first_main = """\
def register(api):
    api.register_command(
        id="first.cmd",
        title="First",
        aliases=[],
        handler=lambda ctx: __import__("core.command_registry",
            fromlist=["CommandResult"]).CommandResult(success=True, message="ok"),
    )
    api.register_search_source("shared_runtime_source")
"""
        second_main = """\
def register(api):
    api.register_command(
        id="second.cmd",
        title="Second",
        aliases=[],
        handler=lambda ctx: __import__("core.command_registry",
            fromlist=["CommandResult"]).CommandResult(success=True, message="ok"),
    )
"""
        with tf.TemporaryDirectory() as tmp:
            _create_plugin_dir(tmp, "first", main_py=first_main)
            _create_plugin_dir(tmp, "second", main_py=second_main)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=tmp)
            pm.scan_plugins()
            assert pm.load_plugin("first")
            assert pm.load_plugin("second")
            second_info = pm.get_plugin("second")
            assert second_info is not None
            second_info.registered_search_sources.append("shared_runtime_source")

            try:
                pm.disable_plugin("second")
                assert _search_sources["shared_runtime_source"]["plugin_id"] == "first"
            finally:
                _search_sources.pop("shared_runtime_source", None)
