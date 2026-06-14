from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from core.command_registry import CommandContext, CommandRegistry
from core.plugin_manager import PluginManager

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGE_DIR = ROOT / ".plugins"


def _python_312_command() -> list[str]:
    candidates: list[list[str]] = []
    if sys.version_info[:2] == (3, 12):
        candidates.append([sys.executable])

    configured = os.environ.get("QUICKLAUNCHER_TEST_PYTHON312")
    if configured:
        candidates.append([configured])

    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.append([py_launcher, "-3.12"])

    for executable_name in ("python3.12", "python312"):
        executable = shutil.which(executable_name)
        if executable:
            candidates.append([executable])

    for command in candidates:
        completed = subprocess.run(
            [
                *command,
                "-c",
                "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)",
            ],
            capture_output=True,
            timeout=10,
        )
        if completed.returncode == 0:
            return command

    raise AssertionError(
        "screenshot_ocr runtime validation requires CPython 3.12; " "install it or set QUICKLAUNCHER_TEST_PYTHON312"
    )


def _load_module(plugin_dir: Path, plugin_id: str):
    module_path = plugin_dir / plugin_id / "main.py"
    spec = importlib.util.spec_from_file_location(f"sample_plugin_{plugin_id}", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_sample_packages(tmp_path: Path, plugin_ids: tuple[str, ...]) -> tuple[CommandRegistry, PluginManager]:
    install_dir = tmp_path / "plugins"
    install_dir.mkdir()
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(install_dir))
    for plugin_id in plugin_ids:
        package_path = PLUGIN_PACKAGE_DIR / f"{plugin_id}.qlzip"
        assert package_path.is_file()
        assert manager.install_from_package(str(package_path)) == plugin_id
    manager.scan_plugins()
    for plugin_id in plugin_ids:
        assert manager.load_plugin(plugin_id) is True
    return registry, manager


def _load_registry(tmp_path: Path) -> CommandRegistry:
    registry, _manager = _install_sample_packages(
        tmp_path,
        ("file_tools", "process_tools", "startup_tools", "network_tools", "api_tester"),
    )
    return registry


def test_sample_plugins_load_and_register_commands(tmp_path):
    registry = _load_registry(tmp_path)

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


def test_plugin_commands_are_discoverable_by_plugin_name(tmp_path):
    registry, _manager = _install_sample_packages(tmp_path, ("text_tools",))

    results = registry.find("text")
    result_ids = {cmd.id for cmd in results}
    assert "text_tools.reverse" in result_ids
    assert "text_tools.count" in result_ids
    assert "text_tools.case" in result_ids


def test_screenshot_ocr_package_bundles_wx_library_without_python_runtime():
    package_path = PLUGIN_PACKAGE_DIR / "screenshot_ocr.qlzip"
    assert package_path.is_file()

    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        screenshot_py = archive.read("screenshot_ocr/screenshot.py").decode("utf-8")
        main_py = archive.read("screenshot_ocr/main.py").decode("utf-8")

    assert "screenshot_ocr/runtime/site-packages/wx/__init__.py" in names
    assert "screenshot_ocr/ocr_worker.py" in names
    assert not any(name.lower().endswith("python.exe") for name in names)
    assert not any(name.lower().endswith("python312.dll") for name in names)
    assert "class _Win32GuiFallback" in screenshot_py
    assert "win32gui = _Win32GuiFallback()" in screenshot_py
    assert '"import win32gui\\n"' in main_py
    assert "and _python_has_wx([str(current)])" in main_py
    assert "request_persistent_helper" in main_py


def test_qr_code_scanner_prefers_host_helper_for_bundled_qt_runtime():
    package_path = PLUGIN_PACKAGE_DIR / "qr_code_scanner.qlzip"
    assert package_path.is_file()

    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        main_py = archive.read("qr_code_scanner/main.py").decode("utf-8")
        runner_py = archive.read("qr_code_scanner/qr_runner.py").decode("utf-8")

    assert "qr_code_scanner/runtime/site-packages/zxingcpp.cp312-win_amd64.pyd" in names
    assert "qr_code_scanner/runtime/site-packages/zxingcpp.cp313-win_amd64.pyd" in names
    assert "qr_code_scanner/qr_worker.py" in names
    assert 'current.parent / "QuickLauncher.exe"' in main_py
    assert "def _python_has_qr_runtime" in main_py
    assert "from PyQt5.QtCore import QPoint" in main_py
    assert "import zxingcpp" in main_py
    assert 'APP_ROOT = Path(sys.executable or "").resolve().parent' in runner_py
    assert 'APP_ROOT / "PyQt5"' in runner_py
    assert "request_persistent_helper" in main_py


def test_host_plugin_helper_loads_screenshot_ocr_bundled_wx(tmp_path):
    python_command = _python_312_command()
    _registry, manager = _install_sample_packages(tmp_path, ("screenshot_ocr",))
    plugin_dir = Path(manager.plugins_dir) / "screenshot_ocr"
    site_packages = plugin_dir / "runtime" / "site-packages"
    helper = tmp_path / "helper_import_wx.py"
    helper.write_text(
        "import sys\n" "import wx\n" "print('WX_OK=' + wx.version())\n" "print('ARGS=' + ','.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            *python_command,
            str(ROOT / "main.py"),
            "--plugin-helper",
            str(helper),
            "--plugin-site",
            str(site_packages),
            "--",
            "a",
            "b",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "WX_OK=" in completed.stdout
    assert "ARGS=a,b" in completed.stdout


def test_disk_cleaner_uses_plugin_api_for_elevation(tmp_path):
    _registry, manager = _install_sample_packages(tmp_path, ("disk_cleaner",))
    disk_cleaner = _load_module(Path(manager.plugins_dir), "disk_cleaner")

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


def test_process_and_startup_plugin_handlers(tmp_path):
    registry = _load_registry(tmp_path)

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


def test_network_plugin_returns_log_payload(tmp_path, monkeypatch):
    _registry, manager = _install_sample_packages(tmp_path, ("network_tools",))
    network_tools = _load_module(Path(manager.plugins_dir), "network_tools")

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
    _registry, manager = _install_sample_packages(tmp_path, ("api_tester",))
    api_tester = _load_module(Path(manager.plugins_dir), "api_tester")

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
    registry = _load_registry(tmp_path)
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
