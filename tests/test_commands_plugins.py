from types import SimpleNamespace

import core
from core.command_registry import CommandContext
from core.commands_plugins import cmd_plugin_list, cmd_plugin_new, cmd_plugin_reload


def test_plugin_list_formats_registered_plugins(monkeypatch):
    plugin = SimpleNamespace(
        manifest=SimpleNamespace(id="demo", version="1.2.3", description="Demo plugin"),
        status="enabled",
        error="",
        registered_commands=["demo.one", "demo.two"],
    )
    monkeypatch.setattr(core, "plugin_manager", SimpleNamespace(list_plugins=lambda: [plugin]))

    result = cmd_plugin_list(CommandContext())

    assert result.success is True
    assert "demo v1.2.3" in result.message
    assert "已注册 2 个命令" in result.message
    assert result.actions[0].value == result.message


def test_plugin_reload_all_enabled_plugins(monkeypatch):
    plugins = [
        SimpleNamespace(manifest=SimpleNamespace(id="one"), status="enabled"),
        SimpleNamespace(manifest=SimpleNamespace(id="two"), status="disabled"),
        SimpleNamespace(manifest=SimpleNamespace(id="three"), status="enabled"),
    ]
    reloaded = []
    monkeypatch.setattr(
        core,
        "plugin_manager",
        SimpleNamespace(
            list_plugins=lambda: plugins,
            reload_plugin=lambda plugin_id: reloaded.append(plugin_id) or plugin_id != "three",
        ),
    )

    result = cmd_plugin_reload(CommandContext())

    assert result.success is True
    assert result.message == "已重载 1 个已启用的插件"
    assert reloaded == ["one", "three"]


def test_plugin_reload_single_plugin_reports_failure(monkeypatch):
    monkeypatch.setattr(
        core,
        "plugin_manager",
        SimpleNamespace(reload_plugin=lambda plugin_id: False),
    )

    result = cmd_plugin_reload(CommandContext(args_text="missing"))

    assert result.success is False
    assert "missing" in result.message


def test_plugin_new_validates_and_writes_template(monkeypatch, tmp_path):
    calls = []

    def fake_write_plugin_template(plugin_dir, plugin_id):
        calls.append((plugin_dir, plugin_id))

    monkeypatch.setattr(core, "plugin_manager", SimpleNamespace(plugins_dir=str(tmp_path)))
    monkeypatch.setattr("core.plugin_template.write_plugin_template", fake_write_plugin_template)

    result = cmd_plugin_new(CommandContext(args_text="demo_plugin"))

    assert result.success is True
    assert calls == [(str(tmp_path / "demo_plugin"), "demo_plugin")]


def test_plugin_new_rejects_invalid_or_existing_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "plugin_manager", SimpleNamespace(plugins_dir=str(tmp_path)))
    (tmp_path / "exists").mkdir()

    invalid = cmd_plugin_new(CommandContext(args_text="bad id!"))
    existing = cmd_plugin_new(CommandContext(args_text="exists"))

    assert invalid.success is False
    assert invalid.error == "格式错误"
    assert existing.success is False
    assert existing.error == "已存在"
