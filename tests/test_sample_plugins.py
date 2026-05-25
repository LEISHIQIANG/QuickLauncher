from __future__ import annotations

from pathlib import Path

from core.command_registry import CommandContext, CommandRegistry
from core.plugin_manager import PluginManager


def _load_registry() -> CommandRegistry:
    plugins_dir = Path(__file__).resolve().parents[1] / "plugins"
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(plugins_dir))
    manager.scan_plugins()
    for plugin_id in ("file_tools", "process_tools", "startup_tools"):
        assert manager.load_plugin(plugin_id) is True
    return registry


def test_sample_plugins_load_and_register_commands():
    registry = _load_registry()

    for command_id in (
        "file_tools.copy_path",
        "file_tools.hash",
        "process_tools.top",
        "process_tools.find",
        "startup_tools.audit",
        "startup_tools.path",
    ):
        assert registry.get(command_id) is not None


def test_plugin_commands_are_discoverable_by_plugin_name():
    plugins_dir = Path(__file__).resolve().parents[1] / "plugins"
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(plugins_dir))
    manager.scan_plugins()

    assert manager.load_plugin("text_tools") is True

    results = registry.find("text")
    result_ids = {cmd.id for cmd in results}
    assert "text_tools.reverse" in result_ids
    assert "text_tools.count" in result_ids
    assert "text_tools.case" in result_ids


def test_disk_cleaner_uses_plugin_api_for_elevation():
    import plugins.disk_cleaner.main as disk_cleaner

    class FakeAPI:
        def __init__(self):
            self.calls = []

        def launch_target(self, target, parameters="", directory="", *, show_window=True, run_as_admin=False):
            self.calls.append((target, parameters, directory, show_window, run_as_admin))
            return True, ""

        def register_command(self, **kwargs):
            return True

    api = FakeAPI()
    disk_cleaner.register(api)

    ok, message = disk_cleaner._run_elevated("cmd.exe", "/c echo ok")

    assert ok is True
    assert "管理员权限" in message
    assert api.calls == [("cmd.exe", "/c echo ok", "", False, True)]


def test_process_and_startup_plugin_handlers():
    registry = _load_registry()

    find_result = registry.get("process_tools.find").handler(
        CommandContext()
    )
    assert find_result.success is False
    assert "用法" in find_result.message

    top_result = registry.get("process_tools.top").handler(
        CommandContext(args_text="mem 3")
    )
    assert top_result.message

    path_result = registry.get("startup_tools.path").handler(
        CommandContext()
    )
    assert path_result.success is True
    assert "PATH 条目数" in path_result.message


def test_file_plugin_handlers(tmp_path):
    registry = _load_registry()
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    path_result = registry.get("file_tools.copy_path").handler(
        CommandContext(args_text="name", selected_files=[str(sample)])
    )
    assert path_result.success is True
    assert path_result.message == "sample.txt"

    hash_result = registry.get("file_tools.hash").handler(
        CommandContext(args_text=f'md5 "{sample}"')
    )
    assert hash_result.success is True
    assert "5d41402abc4b2a76b9719d911017c592" in hash_result.message
