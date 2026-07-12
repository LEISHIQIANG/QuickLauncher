"""Application ports for shell and external process opening.

UI and application services depend on :class:`ShellOpenerPort` rather than
calling :func:`os.startfile` or :func:`subprocess.Popen` directly.  This keeps
sensitive capabilities in the infrastructure layer where the architecture
gate can audit them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ShellOpenerPort(Protocol):
    """Open files/directories/URLs in the platform's default handler.

    All operations should swallow and log only platform-specific errors
    (``OSError`` on Windows) so the caller does not have to repeat the
    same try/except around every UI click.  The default implementation
    lives in :mod:`infrastructure.shell_opener_adapter`.
    """

    def open_path(self, path: str | Path) -> bool:
        """Open a file or directory in the OS default application.

        Returns ``True`` when the OS accepted the request.  Returns
        ``False`` (and never raises) when the path is missing or the
        OS shell rejects the call.
        """

    def relaunch(self, argv: list[str] | None = None) -> bool:
        """Restart the current process.

        Detaches the new process from the current one so the host can
        quit cleanly.  Returns ``True`` when the relaunch was scheduled.
        """

    def run_detached(self, argv: list[str], *, cwd: str | None = None) -> bool:
        """Run an external command detached from the host.

        Used for launching helper scripts (wscript.exe, cmd /c, etc.)
        that should not block the host event loop.
        """

    def launch_with_file(
        self,
        executable: str,
        file_path: str,
        *,
        cwd: str | None = None,
        use_cmd_start: bool = False,
    ) -> bool:
        """Open ``file_path`` with ``executable`` (or via ``cmd /c start``).

        Used for drag-and-drop where the UI already picked the launcher
        executable and just needs the host to spawn the child process
        with the right Windows creation flags.
        """
