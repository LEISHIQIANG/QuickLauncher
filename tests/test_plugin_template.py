from __future__ import annotations

import json

from core.command_registry import CommandRegistry, CommandResult
from core.plugin_manager import PluginAPI
from core.plugin_template import build_plugin_manifest, command_namespace, write_plugin_template


def test_plugin_template_writes_readme_manifest_and_entry(tmp_path):
    plugin_dir = tmp_path / "my-plugin"

    write_plugin_template(
        plugin_dir,
        "my-plugin",
        "My Plugin",
        "Tester",
        "Solves a concrete local problem.",
    )

    manifest_path = plugin_dir / "plugin.json"
    main_path = plugin_dir / "main.py"
    readme_path = plugin_dir / "README.md"

    assert manifest_path.exists()
    assert main_path.exists()
    assert readme_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == "my-plugin"
    assert manifest["commands"][0]["id"] == "my_plugin.hello"
    assert "keywords" in manifest

    readme = readme_path.read_text(encoding="utf-8")
    assert "权限说明" in readme
    assert "图标配置" in readme
    assert "系统默认图标" in readme
    assert "发布前检查" in readme
    assert "my_plugin.hello" in readme
    assert "独立命令面板会显示完整" in readme
    assert "result_window_size" in readme
    assert "CommandParam" in readme


def test_command_namespace_normalizes_hyphens():
    assert command_namespace("my-plugin") == "my_plugin"
    assert command_namespace("my_plugin") == "my_plugin"


def test_plugin_api_accepts_raw_and_normalized_namespace():
    registry = CommandRegistry()
    api = PluginAPI("my-plugin", ".", [], registry)

    ok_normalized = api.register_command(
        id="my_plugin.hello",
        title="Hello",
        aliases=["hello"],
        description="",
        category="test",
        handler=lambda ctx: CommandResult(success=True, message="ok"),
    )
    ok_raw = api.register_command(
        id="my-plugin.raw",
        title="Raw",
        aliases=["raw"],
        description="",
        category="test",
        handler=lambda ctx: CommandResult(success=True, message="ok"),
    )

    assert ok_normalized is True
    assert ok_raw is True
    # Commit staged commands
    assert api.commit_staged() is True
    assert registry.get("my_plugin.hello") is not None
    assert registry.get("my-plugin.raw") is not None


def test_plugin_manifest_template_contains_search_metadata():
    manifest = build_plugin_manifest("startup-tools", "Startup Tools")

    assert manifest["commands"][0]["id"] == "startup_tools.hello"
    assert manifest["icon"] == ""
    assert "Startup Tools" in manifest["keywords"]
    assert "startup tools" in manifest["keywords"]
