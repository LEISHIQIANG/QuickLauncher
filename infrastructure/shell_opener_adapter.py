"""Windows implementation of :class:`application.ports.shell.ShellOpenerPort`.

All operations delegate to native QLshell.dll — hard dependency, no Python fallback.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from application.ports.shell import ShellOpenerPort
from core.native_services import _QLShellEngine

logger = logging.getLogger(__name__)


class WindowsShellOpenerAdapter:
    """Adapter using native QLshell.dll (hard dependency)."""

    def __init__(self) -> None:
        self._is_windows = os.name == "nt"
        if self._is_windows:
            self._engine = _QLShellEngine.get()

    def open_path(self, path: str | Path) -> bool:
        target = os.fspath(path)
        if not target:
            return False
        if not os.path.exists(target):
            logger.debug("open_path: target does not exist: %s", target)
            return False
        if self._is_windows:
            return self._engine.open_path(target)
        import subprocess as _sp

        _sp.Popen(["xdg-open", target], close_fds=True)
        return True

    def relaunch(self, argv: list[str] | None = None) -> bool:
        exe = sys.executable
        return self._engine.relaunch(exe, argv)

    def run_detached(self, argv: list[str], *, cwd: str | None = None) -> bool:
        if not argv:
            return False
        return self._engine.run_detached(argv[0], argv[1:], cwd)

    def launch_with_file(
        self,
        executable: str,
        file_path: str,
        *,
        cwd: str | None = None,
        use_cmd_start: bool = False,
    ) -> bool:
        if not executable or not file_path:
            return False
        return self._engine.launch_with_file(executable, file_path, cwd, use_cmd_start)


_default: ShellOpenerPort | None = None


def get_shell_opener() -> ShellOpenerPort:
    """Return the process-wide :class:`ShellOpenerPort` singleton."""
    global _default
    if _default is None:
        _default = WindowsShellOpenerAdapter()
    return _default


def set_shell_opener(adapter: ShellOpenerPort) -> None:
    """Override the default adapter (used by tests and bootstrap)."""
    global _default
    _default = adapter
