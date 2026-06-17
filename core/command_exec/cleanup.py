"""Process cleanup and temp-file lifecycle helpers for command execution.

The functions in this module are extracted from the legacy
``core.shortcut_command_exec.CommandExecutionMixin`` to keep the public
method surface (used by tests and other modules) while moving the
implementation details out of the god-class.

Public surface (kept stable):

* :func:`terminate_process_tree`
* :func:`cleanup_file_later`

The :class:`CommandExecutionMixin` keeps its method names and now simply
delegates to the functions below.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterable

from core.background_tasks import start_background_thread

logger = logging.getLogger(__name__)


def terminate_process_tree(process) -> None:
    """Terminate a process and, on Windows, best-effort kill its children.

    The function is defensive: it never raises.  If ``process`` is
    ``None`` the call is a no-op.  On non-Windows platforms only the
    primary ``process.kill()`` is used because there is no portable
    taskkill equivalent.
    """
    if process is None:
        return
    pid = getattr(process, "pid", None)
    try:
        process.kill()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        logger.debug("终止进程失败: %s", exc, exc_info=True)
    if os.name != "nt" or not pid:
        return
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=3,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        logger.debug("Failed to terminate command process tree pid=%s: %s", pid, exc, exc_info=True)


def cleanup_file_later(
    process: subprocess.Popen | None,
    paths: Iterable[str] | None = None,
) -> None:
    """Wait for ``process`` to finish and then remove the given temp files.

    Runs on a background thread so the caller does not block.  The
    cleanup is best-effort: it will swallow exceptions and log them.
    """
    path_tuple: tuple[str, ...] = tuple(paths or ())

    def _cleanup() -> None:
        try:
            if process is not None:
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    terminate_process_tree(process)
                    try:
                        process.wait(timeout=2.0)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("等待进程终止失败: %s", exc, exc_info=True)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("清理进程失败: %s", exc, exc_info=True)
        finally:
            for path in path_tuple:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("临时文件清理失败 %s: %s", path, exc, exc_info=True)

    start_background_thread(
        name="CommandTempCleanup",
        target=_cleanup,
        owner="shortcut-command-exec",
    )


__all__ = [
    "cleanup_file_later",
    "terminate_process_tree",
]
