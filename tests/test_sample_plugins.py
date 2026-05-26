from __future__ import annotations

from pathlib import Path

from core.command_registry import CommandContext, CommandRegistry
from core.plugin_manager import PluginManager


def _load_registry() -> CommandRegistry:
    plugins_dir = Path(__file__).resolve().parents[1] / "plugins"
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(plugins_dir))
    manager.scan_plugins()
    for plugin_id in ("file_tools", "process_tools", "startup_tools", "network_tools", "api_tester"):
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
        "network_tools.ping",
        "network_tools.dns",
        "api_tester.get",
        "api_tester.history",
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

    find_result = registry.get("process_tools.find").handler(CommandContext())
    assert find_result.success is False
    assert "用法" in find_result.message

    top_result = registry.get("process_tools.top").handler(CommandContext(args_text="mem 3"))
    assert top_result.message
    assert top_result.display_type == "table"
    assert top_result.payload["columns"] == ["PID", "Name", "CPU", "Memory", "Status", "User", "Path"]
    assert len(top_result.payload["rows"]) <= 3

    path_result = registry.get("startup_tools.path").handler(CommandContext())
    assert path_result.success is True
    assert "PATH 条目数" in path_result.message
    assert path_result.display_type == "list"
    assert path_result.payload["items"][0]["title"] == "PATH 条目数"


def test_network_plugin_returns_log_payload(monkeypatch):
    import plugins.network_tools.main as network_tools

    monkeypatch.setattr(network_tools, "_run_cmd", lambda args, timeout=10: (True, "network output"))

    ping_result = network_tools.handle_ping(CommandContext(args_text="example.com"))
    assert ping_result.success is True
    assert ping_result.display_type == "log"
    assert ping_result.payload["window_size"] == "large"
    assert ping_result.payload["wrap"] is False
    assert ping_result.actions[0].value == "network output"

    dns_result = network_tools.handle_dns(CommandContext(args_text="example.com"))
    assert dns_result.display_type == "log"
    assert dns_result.payload["command"] == "nslookup"


def test_api_tester_request_returns_log_metadata(tmp_path, monkeypatch):
    import plugins.api_tester.main as api_tester

    class FakeHeaders:
        def get(self, key, default=""):
            return "application/json" if key == "Content-Type" else default

    class FakeResponse:
        status = 201
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    monkeypatch.setattr(api_tester.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse())

    result = api_tester._handle_request(CommandContext(args_text="https://example.com/api"), "get", str(tmp_path))

    assert result.success is True
    assert result.display_type == "log"
    assert result.payload["status"] == 201
    assert result.payload["method"] == "GET"
    assert result.payload["url"] == "https://example.com/api"
    assert result.payload["window_size"] == "large"
    assert [action.label for action in result.actions] == ["复制响应", "复制 curl"]

    history_result = api_tester._handle_history(CommandContext(), str(tmp_path))
    assert history_result.display_type == "list"
    assert history_result.payload["items"][0]["title"] == "GET 201"


def test_file_plugin_handlers(tmp_path):
    registry = _load_registry()
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")

    path_result = registry.get("file_tools.copy_path").handler(
        CommandContext(args_text="name", selected_files=[str(sample)])
    )
    assert path_result.success is True
    assert path_result.message == "sample.txt"

    hash_result = registry.get("file_tools.hash").handler(CommandContext(args_text=f'md5 "{sample}"'))
    assert hash_result.success is True
    assert "5d41402abc4b2a76b9719d911017c592" in hash_result.message
