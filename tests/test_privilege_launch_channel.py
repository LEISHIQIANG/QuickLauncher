from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import core.privilege_launch_channel as channel

logger = logging.getLogger(__name__)


def test_explorer_com_uses_registered_shell_application(monkeypatch):
    calls = []

    class ExplorerApplication:
        def ShellExecute(self, target, parameters, directory, verb, show):
            calls.append((target, parameters, directory, verb, show))

    desktop_window = SimpleNamespace(HWND=101, Document=SimpleNamespace(Application=ExplorerApplication()))
    shell_windows = SimpleNamespace(
        Count=0,
        FindWindowSW=lambda *_args: desktop_window,
        Item=lambda index: desktop_window,
    )
    shell_application = SimpleNamespace(Windows=lambda: shell_windows)
    client = SimpleNamespace(Dispatch=lambda prog_id: (calls.append(("dispatch", prog_id)), shell_application)[1])
    ctypes_module = SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(GetShellWindow=lambda: 101)))
    monkeypatch.setitem(
        sys.modules, "pythoncom", SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None)
    )
    monkeypatch.setitem(sys.modules, "ctypes", ctypes_module)
    monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    ok, error = channel.launch_via_explorer_com(r"C:\Tools\App.exe", "--flag", r"C:\Tools", 0)

    assert ok is True
    assert error == ""
    assert calls == [
        ("dispatch", "Shell.Application"),
        (r"C:\Tools\App.exe", "--flag", r"C:\Tools", "open", 0),
    ]


def test_standard_user_channel_keeps_single_three_second_budget(monkeypatch):
    calls = []
    now = [100.0]

    def fake_launch(target, arguments="", working_dir="", *, timeout_seconds, poll_seconds):
        calls.append((target, timeout_seconds))
        now[0] += min(timeout_seconds, 2.0)
        return False

    monkeypatch.setattr(channel.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(channel, "_looks_like_missing_filesystem_target", lambda target: False)
    monkeypatch.setattr(channel, "_can_create_process_directly", lambda target: True)

    import core.auto_start_manager as autostart

    monkeypatch.setattr(autostart, "_launch_via_explorer_token", fake_launch)

    com_calls = []
    monkeypatch.setattr(
        channel,
        "launch_via_explorer_com",
        lambda target, parameters="", directory="", show=1: (
            com_calls.append((target, parameters)),
            (False, "mocked_com_failed"),
        )[1],
    )

    ok, error = channel.launch_as_standard_user(
        r"C:\Tools\App.exe",
        "--flag",
        r"C:\Tools",
        timeout_seconds=3.0,
    )

    assert ok is False
    assert error == "Explorer token launch failed: COM=mocked_com_failed"
    assert len(com_calls) == 2
    assert com_calls[0] == (r"C:\Tools\App.exe", "--flag")
    assert com_calls[1] == (r"C:\Tools\App.exe", "--flag")
    assert len(calls) == 2
    assert calls[0][0] == r"C:\Tools\App.exe"
    assert abs(calls[0][1] - 2.85) < 0.001
    assert 0.8 <= calls[1][1] <= 0.9
    assert now[0] - 100.0 <= 2.86


def test_url_targets_are_not_treated_as_missing_filesystem_paths():
    assert channel._looks_like_missing_filesystem_target("https://example.com") is False
    assert channel._looks_like_missing_filesystem_target("mailto:user@example.com") is False


def test_cmd_start_quotes_shell_metacharacter_arguments():
    line = channel._build_cmd_start_line(
        r"C:\Temp\doc.txt",
        r'"C:\A B\file.txt" ok&calc ok|more ok>file ok^escape',
    )

    assert line == (r'start "" "C:\Temp\doc.txt" "C:\A B\file.txt" ' r'"ok&calc" "ok|more" "ok>file" "ok^escape"')


def test_cmd_start_rejects_control_characters():
    for value in ("line\nbreak", "line\rbreak", "nul\x00byte"):
        try:
            channel._build_cmd_start_line(r"C:\Temp\doc.txt", value)
        except ValueError:
            logger.debug("拒绝控制字符参数", exc_info=True)
        else:
            raise AssertionError(f"unsafe control characters were accepted: {value!r}")
