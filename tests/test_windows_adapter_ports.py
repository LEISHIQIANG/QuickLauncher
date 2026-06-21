from __future__ import annotations

from application.ports.platform import AutoStartPort, WindowPort
from infrastructure.windows import WindowsAutoStartAdapter, WindowsWindowAdapter


def test_windows_adapters_satisfy_runtime_ports():
    window: WindowPort = WindowsWindowAdapter()
    auto_start: AutoStartPort = WindowsAutoStartAdapter()

    assert window is not None
    assert auto_start is not None
