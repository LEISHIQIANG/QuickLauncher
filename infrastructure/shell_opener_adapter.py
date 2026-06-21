"""Windows implementation of :class:`application.ports.shell.ShellOpenerPort`.

This module is the single owner of :func:`os.startfile` and
:func:`subprocess.Popen` for shell-opening operations.  It is registered
in ``SENSITIVE_ADAPTERS`` in :mod:`scripts.check_architecture` so the
architecture gate accepts the call sites as legitimate.  Application
code must depend on the protocol, not on this module.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from application.ports.shell import ShellOpenerPort

logger = logging.getLogger(__name__)


class WindowsShellOpenerAdapter:
    """Default adapter using :func:`os.startfile` and detached :class:`subprocess.Popen`."""

    def __init__(self) -> None:
        self._is_windows = os.name == "nt"

    def open_path(self, path: str | Path) -> bool:
        target = os.fspath(path)
        if not target:
            return False
        if not os.path.exists(target):
            logger.debug("open_path: target does not exist: %s", target)
            return False
        try:
            if self._is_windows:
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target], close_fds=True)
            return True
        except OSError as exc:
            logger.debug("open_path: OS rejected %s: %s", target, exc, exc_info=True)
            return False

    def relaunch(self, argv: list[str] | None = None) -> bool:
        """Restart the current process detached from the host."""
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                cmd = [exe]
            else:
                exe = sys.executable
                script = os.path.abspath(sys.argv[0]) if sys.argv else ""
                cmd = [exe, script] if script else [exe]
            if argv:
                cmd.extend(argv)
            creationflags = 0
            if self._is_windows:
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000
            subprocess.Popen(cmd, creationflags=creationflags, close_fds=True)
            return True
        except OSError as exc:
            logger.error("relaunch: failed to start new process: %s", exc, exc_info=True)
            return False

    def run_detached(self, argv: list[str], *, cwd: str | None = None) -> bool:
        if not argv:
            return False
        try:
            creationflags = 0
            if self._is_windows:
                creationflags = 0x08000000
            subprocess.Popen(
                list(argv),
                cwd=cwd,
                creationflags=creationflags,
                shell=False,
                close_fds=True,
            )
            return True
        except OSError as exc:
            logger.error("run_detached: failed to run %s: %s", argv, exc, exc_info=True)
            return False

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
        try:
            if use_cmd_start:
                creationflags = (
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                    | 0x02000000  # CREATE_BREAKAWAY_FROM_JOB
                )
                subprocess.Popen(
                    ["cmd", "/c", "start", "", executable, file_path],
                    shell=False,
                    creationflags=creationflags,
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=cwd,
                )
            else:
                creationflags = (
                    subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                    | 0x02000000  # CREATE_BREAKAWAY_FROM_JOB
                )
                subprocess.Popen(
                    [executable, file_path],
                    creationflags=creationflags,
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=cwd,
                )
            return True
        except OSError as exc:
            logger.error("launch_with_file: failed %s %s: %s", executable, file_path, exc, exc_info=True)
            return False


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
