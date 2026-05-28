import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.command_registry import CommandContext
from core.commands import cmd_process as facade_cmd_process
from core.commands import cmd_sysreport as facade_cmd_sysreport
from core.commands_system import _format_bytes, cmd_process, cmd_sysreport


def _install_psutil(monkeypatch, fake_psutil):
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)


def test_system_command_facade_identity():
    assert facade_cmd_process is cmd_process
    assert facade_cmd_sysreport is cmd_sysreport


def test_format_bytes_units():
    assert _format_bytes(0) == "0 B"
    assert _format_bytes(1536) == "1.5 KB"
    assert _format_bytes(2 * 1024**3) == "2.0 GB"


def test_cmd_process_cpu_sort(monkeypatch):
    fake_psutil = MagicMock()
    fake_psutil.process_iter.return_value = [
        SimpleNamespace(
            info={"pid": 1, "name": "low.exe", "exe": "", "memory_info": SimpleNamespace(rss=1), "cpu_percent": 1.0}
        ),
        SimpleNamespace(
            info={"pid": 2, "name": "high.exe", "exe": "", "memory_info": SimpleNamespace(rss=1), "cpu_percent": 90.0}
        ),
    ]
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_process(CommandContext(args_text="cpu"))

    assert result.success is True
    assert result.message.index("high.exe") < result.message.index("low.exe")
    assert result.payload["rows"][0]["pid"] == 2


def test_cmd_process_search_skips_unreadable_process(monkeypatch):
    class BadProc:
        @property
        def info(self):
            raise RuntimeError("access denied")

    fake_psutil = MagicMock()
    fake_psutil.process_iter.return_value = [
        BadProc(),
        SimpleNamespace(
            info={
                "pid": 42,
                "name": "tool.exe",
                "exe": "C:\\tools\\tool.exe",
                "memory_info": SimpleNamespace(rss=4096),
                "cpu_percent": 0.0,
            }
        ),
    ]
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_process(CommandContext(args_text="search tool"))

    assert result.success is True
    assert "tool.exe" in result.message
    assert len(result.payload["rows"]) == 1


def test_cmd_process_search_no_match(monkeypatch):
    fake_psutil = MagicMock()
    fake_psutil.process_iter.return_value = [
        SimpleNamespace(
            info={"pid": 1, "name": "alpha.exe", "exe": "", "memory_info": SimpleNamespace(rss=1), "cpu_percent": 0}
        )
    ]
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_process(CommandContext(args_text="find beta"))

    assert result.success is True
    assert result.message == "未找到匹配进程: beta"


def test_cmd_process_kill_uses_force_kill_after_wait_failure(monkeypatch):
    proc = MagicMock()
    proc.name.return_value = "demo.exe"
    proc.wait.side_effect = TimeoutError("still running")
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = proc
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_process(CommandContext(args_text="kill 123"))

    assert result.success is True
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


def test_cmd_process_kill_invalid_pid(monkeypatch):
    fake_psutil = MagicMock()
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_process(CommandContext(args_text="kill abc"))

    assert result.success is False
    assert result.error == "终止失败"


def test_cmd_sysreport_includes_battery(monkeypatch):
    fake_psutil = MagicMock()
    fake_psutil.virtual_memory.return_value = SimpleNamespace(used=4 * 1024**3, total=8 * 1024**3, percent=50.0)
    fake_psutil.disk_usage.return_value = SimpleNamespace(used=100 * 1024**3, total=256 * 1024**3, percent=39.1)
    fake_psutil.net_io_counters.return_value = SimpleNamespace(bytes_sent=1024, bytes_recv=2048)
    fake_psutil.boot_time.return_value = 1680000000.0
    fake_psutil.cpu_percent.return_value = 12.5
    fake_psutil.cpu_count.return_value = 8
    fake_psutil.sensors_battery.return_value = SimpleNamespace(percent=66.0, power_plugged=False)
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_sysreport(CommandContext())

    assert result.success is True
    assert "系统快照" in result.message
    assert "电池: 66.0% (电池供电)" in result.message


def test_cmd_sysreport_failure(monkeypatch):
    fake_psutil = MagicMock()
    fake_psutil.virtual_memory.side_effect = RuntimeError("boom")
    _install_psutil(monkeypatch, fake_psutil)

    result = cmd_sysreport(CommandContext())

    assert result.success is False
    assert result.error == "系统信息失败"
