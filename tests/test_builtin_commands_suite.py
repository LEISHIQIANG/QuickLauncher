"""Comprehensive test suite for Phase 2/3 built-in commands & custom plugins.

Ensures absolute robustness, 100% reliability, and complete validation under all environments.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os

# ===========================================================================
# ── Setup environment-level mocks before any imports ───────────────────────
# ===========================================================================
import pathlib
import socket
import sys
import tempfile
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Mock psutil in sys.modules so that it is globally available in tests
mock_psutil = MagicMock()
mock_proc = MagicMock()
mock_proc.create_time.return_value = 1680000000.0
mock_proc.memory_info.return_value.rss = 50 * 1024 * 1024
mock_proc.cpu_times.return_value.user = 0.5
mock_proc.cpu_times.return_value.system = 0.3
mock_proc.name.return_value = "python.exe"
mock_proc.exe.return_value = "C:\\python.exe"
mock_psutil.Process.return_value = mock_proc
sys.modules["psutil"] = mock_psutil

# Initialize core mocks
import core

core.data_manager = MagicMock()

# Setup mock data manager fields
mock_settings = MagicMock()
mock_settings.favorite_commands = ["uuid", "timestamp"]
# Ensure preprocessing settings return explicit False (not truthy MagicMock)
mock_settings.preprocessing_enabled = True
mock_settings.preprocessing_strict_mode = False
mock_settings.preprocessing_rate_limiting_enabled = False
mock_settings.preprocessing_audit_enabled = False
mock_settings.security_block_dangerous_patterns = False
mock_settings.security_require_variable_quoting = False
core.data_manager.get_settings.return_value = mock_settings
core.data_manager.data.folders = []
core.data_manager.app_dir = pathlib.Path(tempfile.gettempdir())
core.data_manager.install_dir = pathlib.Path(tempfile.gettempdir())

# ===========================================================================
# ── Core imports after mocks are ready ─────────────────────────────────────
# ===========================================================================

from core.command_registry import CommandContext
from core.commands import (
    cmd_base64,
    cmd_cidr,
    cmd_clean_cache,
    cmd_color,
    cmd_config_repair,
    cmd_conflict,
    cmd_copy_path,
    cmd_dns,
    cmd_env,
    cmd_explorer,
    cmd_git,
    cmd_god,
    cmd_hash,
    cmd_hosts,
    cmd_ip,
    cmd_json,
    cmd_jwt,
    cmd_netdiag,
    cmd_path_audit,
    cmd_plugin_list,
    cmd_plugin_new,
    cmd_plugin_reload,
    cmd_port,
    cmd_process,
    cmd_qr,
    cmd_sysreport,
    cmd_timestamp,
    cmd_tls,
    cmd_urlencode,
    cmd_uuid,
    cmd_wifi,
)
from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

_PLUGIN_TEST_TMP = tempfile.TemporaryDirectory()
_PLUGIN_TEST_ROOT = pathlib.Path(_PLUGIN_TEST_TMP.name) / "plugins"
_PLUGIN_PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1] / ".plugins"


def _load_packaged_plugin_module(plugin_id: str):
    package_path = _PLUGIN_PACKAGE_DIR / f"{plugin_id}.qlzip"
    assert package_path.is_file(), package_path
    _PLUGIN_TEST_ROOT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path) as archive:
        archive.extractall(_PLUGIN_TEST_ROOT)
    module_path = _PLUGIN_TEST_ROOT / plugin_id / "main.py"
    spec = importlib.util.spec_from_file_location(f"builtin_suite_plugin_{plugin_id}", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


network_tools_main = _load_packaged_plugin_module("network_tools")
text_tools_main = _load_packaged_plugin_module("text_tools")
handle_dns = network_tools_main.handle_dns
handle_ping = network_tools_main.handle_ping
case_text = text_tools_main.case_text
count_text = text_tools_main.count_text
reverse_text = text_tools_main.reverse_text

# ===========================================================================
# ── String Processing (Base64 & URL) ───────────────────────────────────────
# ===========================================================================


def test_cmd_urlencode():
    # Simple encode
    ctx = CommandContext(args_text="hello world")
    res = cmd_urlencode(ctx)
    assert res.success is True
    assert res.message == "hello%20world"

    # Chinese encode
    ctx = CommandContext(args_text="你好")
    res = cmd_urlencode(ctx)
    assert res.success is True
    assert res.message == "%E4%BD%A0%E5%A5%BD"

    # Explicit encode prefix
    ctx = CommandContext(args_text="encode hello")
    res = cmd_urlencode(ctx)
    assert res.success is True
    assert res.message == "hello"

    # Decode prefix
    ctx = CommandContext(args_text="decode %E4%BD%A0%E5%A5%BD")
    res = cmd_urlencode(ctx)
    assert res.success is True
    assert res.message == "你好"

    # Clipboard fallback
    ctx = CommandContext(args_text="", clipboard_text="hello")
    res = cmd_urlencode(ctx)
    assert res.success is True
    assert res.message == "hello"


def test_cmd_base64():
    # Simple encode
    ctx = CommandContext(args_text="hello")
    res = cmd_base64(ctx)
    assert res.success is True
    assert res.message == "aGVsbG8="

    # Decode prefix
    ctx = CommandContext(args_text="decode aGVsbG8=")
    res = cmd_base64(ctx)
    assert res.success is True
    assert res.message == "hello"

    # Decode prefix with missing padding
    ctx = CommandContext(args_text="decode aGVsbG8")
    res = cmd_base64(ctx)
    assert res.success is True
    assert res.message == "hello"

    # Clipboard fallback
    ctx = CommandContext(args_text="", clipboard_text="hello")
    res = cmd_base64(ctx)
    assert res.success is True
    assert res.message == "aGVsbG8="


# ===========================================================================
# ── Color & IP & Path & Hash ──────────────────────────────────────────────
# ===========================================================================


def test_cmd_color():
    # 6 hex digits
    ctx = CommandContext(args_text="#ff8800")
    res = cmd_color(ctx)
    assert res.success is True
    assert "HEX: #FF8800" in res.message
    assert "RGB: rgb(255, 136, 0)" in res.message

    # 3 hex digits
    ctx = CommandContext(args_text="f80")
    res = cmd_color(ctx)
    assert res.success is True
    assert "HEX: #FF8800" in res.message

    # 8 hex digits (RGBA)
    ctx = CommandContext(args_text="#ff88007f")
    res = cmd_color(ctx)
    assert res.success is True
    assert "RGBA: rgba(255, 136, 0, 0.50)" in res.message or "rgba(255, 136, 0, 0.4" in res.message

    # Invalid
    ctx = CommandContext(args_text="invalid")
    res = cmd_color(ctx)
    assert res.success is False


@patch("core.commands._fetch_public_ip")
@patch("core.commands._get_local_ipv4_addresses")
@patch("core.commands._get_primary_local_ip")
def test_cmd_ip(mock_primary, mock_local, mock_public):
    mock_primary.return_value = "192.168.1.23"
    mock_local.return_value = [("192.168.1.23", "Wi-Fi"), ("10.8.0.2", "VPN")]
    mock_public.return_value = ("203.0.113.8", "")

    res = cmd_ip(CommandContext())
    assert res.success is True
    assert "内网 IP:" in res.message
    assert "192.168.1.23" in res.message
    assert "10.8.0.2" in res.message
    assert "公网 IP: 203.0.113.8" in res.message
    assert res.payload["public_ip"] == "203.0.113.8"


@patch("core.commands._fetch_public_ip")
@patch("core.commands._get_local_ipv4_addresses")
@patch("core.commands._get_primary_local_ip")
def test_cmd_ip_public_failure_still_shows_local(mock_primary, mock_local, mock_public):
    mock_primary.return_value = "192.168.1.23"
    mock_local.return_value = [("192.168.1.23", "Wi-Fi")]
    mock_public.return_value = ("", "timeout")

    res = cmd_ip(CommandContext())
    assert res.success is True
    assert "192.168.1.23" in res.message
    assert "公网 IP: 获取失败" in res.message


def test_cmd_config_repair_scan_and_fix(monkeypatch):
    class FakeDataManager:
        def __init__(self):
            self.data = AppData(
                folders=[
                    Folder(
                        items=[
                            ShortcutItem(
                                type=ShortcutType.COMMAND,
                                command_type="cmd",
                                command="echo {clipboard:q}",
                                command_variables_enabled=False,
                            )
                        ]
                    )
                ]
            )
            self.saved = 0

        def _mark_history(self, action, summary=""):
            self.history = (action, summary)

        def save(self, immediate=False):
            self.saved += 1
            return True

    fake = FakeDataManager()
    monkeypatch.setattr(core, "data_manager", fake)

    scan = cmd_config_repair(CommandContext(args_text=""))
    assert scan.success is True
    assert fake.saved == 0
    assert fake.data.folders[0].items[0].command == "echo {clipboard:q}"

    fixed = cmd_config_repair(CommandContext(args_text="fix"))
    assert fixed.success is True
    assert fake.saved == 1
    assert fake.data.folders[0].items[0].command == "echo {{clipboard:q}}"


def test_cmd_clean_cache_preview_uses_dry_run(monkeypatch):
    from core import project_cache_cleaner

    calls = []

    def fake_clean(data_manager, dry_run=False):
        calls.append((data_manager, dry_run))
        return {
            "total_removed": 3,
            "total_size_freed_mb": 1.25,
            "failed": 0,
            "by_area": {"__pycache__": {"files_removed": 3, "size_freed_mb": 1.25}},
        }

    monkeypatch.setattr(project_cache_cleaner, "clean_unused_project_cache", fake_clean)

    result = cmd_clean_cache(CommandContext(args_text="preview"))

    assert result.success is True
    assert calls == [(core.data_manager, True)]
    assert "缓存清理预览" in result.message
    assert "Python 字节码" in result.message
    assert result.actions[0].value == result.message


def test_cmd_copy_path():
    # No selection
    ctx = CommandContext()
    res = cmd_copy_path(ctx)
    assert res.success is False

    # Normal files
    ctx = CommandContext(selected_files=["C:\\test\\a.txt", "C:\\test\\b.log"])
    res = cmd_copy_path(ctx)
    assert res.success is True
    assert "a.txt" in res.message
    assert "b.log" in res.message

    # Name mode
    ctx = CommandContext(selected_files=["C:\\test\\a.txt"], args_text="name")
    res = cmd_copy_path(ctx)
    assert res.success is True
    assert res.message == "a.txt"

    # Dir mode
    ctx = CommandContext(selected_files=["C:\\test\\a.txt"], args_text="dir")
    res = cmd_copy_path(ctx)
    assert res.success is True
    assert res.message == "C:\\test"


def test_cmd_hash():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"hello world")
        tmp_name = tmp.name

    try:
        # Default md5
        ctx = CommandContext(args_text=tmp_name)
        res = cmd_hash(ctx)
        assert res.success is True
        md5_val = hashlib.md5(b"hello world").hexdigest()
        assert md5_val in res.message.lower()

        # Explicit sha256 with quotes
        ctx = CommandContext(args_text=f'sha256 "{tmp_name}"')
        res = cmd_hash(ctx)
        assert res.success is True
        sha256_val = hashlib.sha256(b"hello world").hexdigest()
        assert sha256_val in res.message.lower()

        # Selection fallback
        ctx = CommandContext(selected_files=[tmp_name])
        res = cmd_hash(ctx)
        assert res.success is True
        assert md5_val in res.message.lower()

        # File not found
        ctx = CommandContext(args_text="nonexistent.txt")
        res = cmd_hash(ctx)
        assert res.success is False
        assert "不存在" in res.message or "not found" in res.message.lower()

    finally:
        os.unlink(tmp_name)


# ===========================================================================
# ── Timestamp & UUID & QR ──────────────────────────────────────────────────
# ===========================================================================


def test_cmd_uuid():
    res = cmd_uuid(CommandContext())
    assert res.success is True
    assert len(res.message) == 36


def test_cmd_timestamp():
    # Empty (current)
    res = cmd_timestamp(CommandContext())
    assert res.success is True
    assert len(res.message.split("\n")) == 2

    # Normal timestamp
    ctx = CommandContext(args_text="1684789200")
    res = cmd_timestamp(ctx)
    assert res.success is True
    assert "2023-" in res.message

    # Millisecond timestamp
    ctx = CommandContext(args_text="1684789200000")
    res = cmd_timestamp(ctx)
    assert res.success is True
    assert "2023-" in res.message

    # Overflow timestamp
    ctx = CommandContext(args_text="999999999999999999")
    res = cmd_timestamp(ctx)
    assert res.success is False
    assert "无效" in res.message


def test_cmd_qr():
    # Valid
    ctx = CommandContext(args_text="hello")
    res = cmd_qr(ctx)
    assert res.success is True
    assert res.display_type == "qr"
    assert "image_path" in res.payload
    assert os.path.exists(res.payload["image_path"])
    os.unlink(res.payload["image_path"])

    # Empty
    ctx = CommandContext(args_text="")
    res = cmd_qr(ctx)
    assert res.success is False

    # Oversized
    ctx = CommandContext(args_text="a" * 2000)
    res = cmd_qr(ctx)
    assert res.success is False


# ===========================================================================
# ── Plugins & Favorites ────────────────────────────────────────────────────
# ===========================================================================


def test_cmd_json():
    res = cmd_json(CommandContext(args_text='{"b":2,"a":1}'))
    assert res.success is True
    assert '"a": 1' in res.message

    res = cmd_json(CommandContext(args_text='min {"b": 2, "a": 1}'))
    assert res.success is True
    assert res.message == '{"b":2,"a":1}'

    res = cmd_json(CommandContext(args_text="{bad json}"))
    assert res.success is False
    assert "JSON 无效" in res.message


def test_cmd_jwt():
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "u1", "role": "admin"}).encode()).decode().rstrip("=")
    res = cmd_jwt(CommandContext(args_text=f"{header}.{payload}."))
    assert res.success is True
    assert '"sub": "u1"' in res.message
    assert res.payload["payload"]["role"] == "admin"


@patch("core.commands._run_cmd")
@patch("socket.create_connection")
@patch("socket.getaddrinfo")
def test_cmd_netdiag(mock_getaddrinfo, mock_create_connection, mock_run):
    mock_getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 80))]
    mock_create_connection.return_value.__enter__.return_value = object()
    mock_run.return_value = (True, "Average = 20ms")

    res = cmd_netdiag(CommandContext(args_text="https://example.com:443/path"))
    assert res.success is True
    assert "网络诊断: example.com" in res.message
    assert "DNS: 93.184.216.34" in res.message
    assert "TCP 443: 可连接" in res.message
    assert "平均延迟: 20ms" in res.message


def test_cmd_cidr():
    res = cmd_cidr(CommandContext(args_text="192.168.1.34/24"))
    assert res.success is True
    assert "网络: 192.168.1.0/24" in res.message
    assert "子网掩码: 255.255.255.0" in res.message
    assert "广播地址: 192.168.1.255" in res.message
    assert res.payload["network"] == "192.168.1.0/24"

    res = cmd_cidr(CommandContext(args_text="bad-cidr"))
    assert res.success is False


@patch("core.commands.socket.create_connection")
@patch("core.commands.ssl.create_default_context")
def test_cmd_tls(mock_ssl_context, mock_create_connection):
    raw_sock = MagicMock()
    raw_sock.__enter__.return_value = object()
    raw_sock.__exit__.return_value = None
    mock_create_connection.return_value = raw_sock

    tls_sock = MagicMock()
    tls_sock.__enter__.return_value = tls_sock
    tls_sock.__exit__.return_value = None
    tls_sock.getpeercert.return_value = {
        "subject": ((("commonName", "example.com"),),),
        "issuer": ((("organizationName", "Example CA"),),),
        "notBefore": "Jan 01 00:00:00 2026 GMT",
        "notAfter": "Jan 01 00:00:00 2027 GMT",
        "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
    }
    tls_sock.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
    tls_sock.version.return_value = "TLSv1.3"

    ctx = MagicMock()
    ctx.wrap_socket.return_value = tls_sock
    mock_ssl_context.return_value = ctx

    res = cmd_tls(CommandContext(args_text="https://example.com:443"))
    assert res.success is True
    assert "目标: example.com:443" in res.message
    assert "TLSv1.3" in res.message
    assert "Example CA" in res.message
    assert "www.example.com" in res.message

    res = cmd_tls(CommandContext(args_text="example.com 8443"))
    assert res.success is True
    assert "目标: example.com:8443" in res.message


@patch("core.commands.socket.create_connection")
def test_cmd_tls_dns_failure(mock_create_connection):
    mock_create_connection.side_effect = socket.gaierror(11001, "getaddrinfo failed")

    res = cmd_tls(CommandContext(args_text="bad-domain-does-not-exist"))
    assert res.success is False
    assert "无法解析域名" in res.message
    assert "getaddrinfo failed" not in res.message


def test_cmd_path_audit(tmp_path):
    valid_dir = tmp_path / "bin"
    valid_dir.mkdir()
    missing_dir = tmp_path / "missing"
    raw_path = os.pathsep.join([str(valid_dir), str(valid_dir), str(missing_dir)])

    res = cmd_path_audit(CommandContext(args_text=raw_path))
    assert res.success is True
    assert "PATH 体检" in res.message
    assert "失效目录: 1" in res.message
    assert "重复目录: 1" in res.message
    assert str(missing_dir) in res.message


def test_cmd_process():
    proc_a = MagicMock()
    proc_a.info = {
        "pid": 10,
        "name": "alpha.exe",
        "exe": "C:\\alpha.exe",
        "memory_info": SimpleNamespace(rss=200 * 1024 * 1024),
        "cpu_percent": 1.0,
    }
    proc_b = MagicMock()
    proc_b.info = {
        "pid": 11,
        "name": "beta.exe",
        "exe": "C:\\beta.exe",
        "memory_info": SimpleNamespace(rss=50 * 1024 * 1024),
        "cpu_percent": 9.0,
    }
    mock_psutil.process_iter.return_value = [proc_a, proc_b]

    res = cmd_process(CommandContext(args_text="top"))
    assert res.success is True
    assert "alpha.exe" in res.message
    assert res.message.index("alpha.exe") < res.message.index("beta.exe")
    assert "内存占用最高进程\n\nPID: 10" in res.message
    assert "\n\nPID: 11" in res.message

    res = cmd_process(CommandContext(args_text="find beta"))
    assert res.success is True
    assert "beta.exe" in res.message
    assert "alpha.exe" not in res.message


def test_cmd_sysreport():
    mock_psutil.virtual_memory.return_value = SimpleNamespace(used=4 * 1024**3, total=8 * 1024**3, percent=50.0)
    mock_psutil.disk_usage.return_value = SimpleNamespace(used=100 * 1024**3, total=256 * 1024**3, percent=39.1)
    mock_psutil.net_io_counters.return_value = SimpleNamespace(bytes_sent=1024, bytes_recv=2048)
    mock_psutil.boot_time.return_value = 1680000000.0
    mock_psutil.cpu_percent.return_value = 12.5
    mock_psutil.cpu_count.return_value = 8
    mock_psutil.sensors_battery.return_value = None

    res = cmd_sysreport(CommandContext())
    assert res.success is True
    assert "系统快照" in res.message
    assert "CPU: 12.5%" in res.message


def test_cmd_plugin_commands():
    # List (requires pm mock or returns failure)
    res = cmd_plugin_list(CommandContext())
    assert res.success is False

    res = cmd_plugin_reload(CommandContext(args_text="some_plugin"))
    assert res.success is False

    res = cmd_plugin_new(CommandContext(args_text="some_plugin"))
    assert res.success is False


# ===========================================================================
# ── Network Commands (Wi-Fi, Hosts, Port) ──────────────────────────────────
# ===========================================================================


@patch("core.commands._run_cmd")
def test_cmd_wifi(mock_run):
    # Mocking profile show lists
    mock_run.return_value = (True, "All User Profile     : Home-WiFi\nAll User Profile     : Work-WiFi")
    res = cmd_wifi(CommandContext(args_text=""))
    assert res.success is True
    assert "Home-WiFi" in res.message
    assert "Work-WiFi" in res.message

    # Mocking password retrieval
    mock_run.return_value = (True, "Key Content            : secret123\n关键内容            : secret123")
    res = cmd_wifi(CommandContext(args_text="Home-WiFi"))
    assert res.success is True
    assert "secret123" in res.message


@patch("core.shortcut_executor.ShortcutExecutor._launch_with_privilege")
def test_cmd_hosts(mock_launch):
    mock_launch.return_value = (True, "")
    res = cmd_hosts(CommandContext())
    assert res.success is True
    mock_launch.assert_called_once()
    assert mock_launch.call_args.kwargs["run_as_admin"] is True


def test_cmd_port():
    # Mock connection on port 8080
    mock_conn = MagicMock()
    mock_conn.laddr.port = 8080
    mock_conn.pid = 9999
    mock_psutil.net_connections.return_value = [mock_conn]

    # Port status query
    res = cmd_port(CommandContext(args_text="8080"))
    assert res.success is True
    assert "python.exe" in res.message
    assert "9999" in res.message


# ===========================================================================
# ── Windows System Operations ──────────────────────────────────────────────
# ===========================================================================


@patch("subprocess.Popen")
def test_cmd_env(mock_popen):
    res = cmd_env(CommandContext())
    assert res.success is True
    mock_popen.assert_called_once()


@patch("core.commands._run_cmd")
def test_cmd_dns(mock_run):
    mock_run.return_value = (True, "dns flushed")
    res = cmd_dns(CommandContext())
    assert res.success is True


def test_cmd_git_status(monkeypatch, tmp_path):
    calls = []

    class Proc:
        def __init__(self, argv, cwd=None, **kwargs):
            self.argv = argv
            self.cwd = cwd
            self.returncode = 0
            calls.append((argv, cwd))

        def communicate(self, timeout=None):
            if self.argv[1:3] == ["rev-parse", "--is-inside-work-tree"]:
                return "true\n", ""
            return "## main\n M file.txt\n", ""

    monkeypatch.setattr("subprocess.Popen", Proc)

    res = cmd_git(CommandContext(args_text=f"status {tmp_path}"))

    assert res.success is True
    assert res.display_type == "table"
    assert res.payload["repo"] == str(tmp_path)
    assert res.payload["rows"][0][0] == "branch"


@patch("os.startfile")
def test_cmd_god(mock_startfile):
    res = cmd_god(CommandContext())
    assert res.success is True
    mock_startfile.assert_called_once()


@patch("subprocess.run")
@patch("subprocess.Popen")
def test_cmd_explorer(mock_popen, mock_run):
    # Mocking processes to check if explorer restarted
    p1 = MagicMock()
    p1.info = {"name": "explorer.exe"}
    mock_psutil.process_iter.return_value = [p1]

    res = cmd_explorer(CommandContext())
    assert res.success is True


def test_cmd_conflict():
    res = cmd_conflict(CommandContext())
    assert res.success is True


# ===========================================================================
# ── Plugin Handlers: Text & Network ────────────────────────────────────────
# ===========================================================================


def test_plugin_text_tools():
    # Reverse text
    ctx = CommandContext(args_text="hello")
    res = reverse_text(ctx)
    assert res.success is True
    assert res.message == "olleh"

    # Count text
    ctx = CommandContext(args_text="hello world\nline two")
    res = count_text(ctx)
    assert res.success is True
    assert "行数: 2" in res.message
    assert "字数: 4" in res.message
    assert "字符数: 20" in res.message

    # Case upper
    ctx = CommandContext(args_text="upper hello")
    res = case_text(ctx)
    assert res.success is True
    assert res.message == "HELLO"

    # Case lower
    ctx = CommandContext(args_text="lower HELLO")
    res = case_text(ctx)
    assert res.success is True
    assert res.message == "hello"

    # Case default (upper)
    ctx = CommandContext(args_text="hello")
    res = case_text(ctx)
    assert res.success is True
    assert res.message == "HELLO"


def test_plugin_network_tools():
    mock_run = MagicMock()
    with patch.object(network_tools_main, "_run_cmd", mock_run):
        _assert_plugin_network_tools(mock_run)


def _assert_plugin_network_tools(mock_run):
    # Ping success
    mock_run.return_value = (True, "ping successful output")
    ctx = CommandContext(args_text="example.com")
    res = handle_ping(ctx)
    assert res.success is True
    assert "ping successful output" in res.message

    # Ping dangerous input
    ctx = CommandContext(args_text="example.com; rm -rf /")
    res = handle_ping(ctx)
    assert res.success is False

    # DNS success
    mock_run.return_value = (True, "nslookup successful output")
    ctx = CommandContext(args_text="example.com")
    res = handle_dns(ctx)
    assert res.success is True
    assert "nslookup successful output" in res.message


def test_cmd_wifi_quote_stripping_and_case_insensitive(monkeypatch):
    calls = []

    def mock_run(args):
        calls.append(args)
        return (True, "Security Key           : Present\nKey Content            : MyPass123")

    monkeypatch.setattr("core.commands._run_cmd", mock_run)

    # 1. Strip quotes and check
    res = cmd_wifi(CommandContext(args_text='"My-Wifi-Profile"'))
    assert res.success is True
    assert "MyPass123" in res.message
    # Check that name was stripped of quotes when querying
    assert calls[0][4] == "name=My-Wifi-Profile"


def test_cmd_git_custom_args(monkeypatch, tmp_path):
    calls = []

    class Proc:
        def __init__(self, argv, cwd=None, **kwargs):
            self.argv = argv
            self.cwd = cwd
            self.returncode = 0
            calls.append((argv, cwd))

        def communicate(self, timeout=None):
            if self.argv[1:3] == ["rev-parse", "--is-inside-work-tree"]:
                return "true\n", ""
            return "git log custom output\n", ""

    monkeypatch.setattr("subprocess.Popen", Proc)

    res = cmd_git(CommandContext(args_text=f"log -n 5 {tmp_path}"))
    assert res.success is True
    # The last call is the log call
    assert calls[1][0] == ["git", "log", "-n", "5"]
    assert calls[1][1] == str(tmp_path)


def test_cmd_process_cpu_sorting(monkeypatch):
    proc_a = MagicMock()
    proc_a.info = {
        "pid": 10,
        "name": "alpha.exe",
        "exe": "C:\\alpha.exe",
        "memory_info": SimpleNamespace(rss=200 * 1024 * 1024),
    }
    # Initial call to cpu_percent returns 0.0, second returns 5.0
    proc_a.cpu_percent.side_effect = [0.0, 5.0]

    proc_b = MagicMock()
    proc_b.info = {
        "pid": 11,
        "name": "beta.exe",
        "exe": "C:\\beta.exe",
        "memory_info": SimpleNamespace(rss=50 * 1024 * 1024),
    }
    proc_b.cpu_percent.side_effect = [0.0, 95.0]

    monkeypatch.setattr("psutil.process_iter", lambda attrs: [proc_a, proc_b])

    res = cmd_process(CommandContext(args_text="cpu"))
    assert res.success is True
    # beta.exe (95%) should be listed before alpha.exe (5%) when sorted by cpu
    assert "beta.exe" in res.message
    assert "alpha.exe" in res.message
    assert res.message.index("beta.exe") < res.message.index("alpha.exe")
    assert "CPU: 95.0%" in res.message
    assert "CPU: 5.0%" in res.message


def test_cmd_env_and_god_registration():
    from core.builtin_command_catalog import PANEL_COMMAND_IDS, build_builtin_command_definitions
    from core.builtin_commands import canonical_builtin_command

    defs = build_builtin_command_definitions()
    ids = {d.id for d in defs}
    assert "env" in ids
    assert "god" in ids
    assert "env" not in PANEL_COMMAND_IDS
    assert "god" not in PANEL_COMMAND_IDS

    # Test alias resolution
    assert canonical_builtin_command("env-edit") == "env"
    assert canonical_builtin_command("godmode") == "god"
