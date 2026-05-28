"""Bash capture fallback helpers for Windows/MSYS edge cases."""

from __future__ import annotations

import re
import time
from collections.abc import Callable


def bash_path(path: str) -> str:
    return str(path or "").replace("\\", "/")


def quote_bash_path(path: str) -> str:
    return bash_path(path).replace('"', '\\"')


def build_bash_fallback_wrapper(
    command: str,
    *,
    tmp_path: str | None,
    stdout_path: str,
    stderr_path: str,
    marker_path: str,
) -> str:
    marker_q = quote_bash_path(marker_path)
    stdout_q = quote_bash_path(stdout_path)
    stderr_q = quote_bash_path(stderr_path)
    if tmp_path:
        command_q = quote_bash_path(tmp_path)
        return "#!/bin/bash\n" f'"{command_q}" >"{stdout_q}" 2>"{stderr_q}"\n' f'echo "EXIT:$?" >>"{marker_q}"\n'

    safe_command = str(command or "").replace("'", "'\\''")
    return (
        "#!/bin/bash\n"
        f'echo \'{safe_command}\' | bash --noprofile --norc >"{stdout_q}" 2>"{stderr_q}"\n'
        f'echo "EXIT:$?" >>"{marker_q}"\n'
    )


def read_bash_fallback_exit_code(marker_path: str | None) -> int | None:
    if not marker_path:
        return None
    try:
        with open(marker_path, "r", encoding="utf-8", errors="replace") as marker:
            text = marker.read().strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None
    match = re.search(r"EXIT:(-?\d+)", text)
    return int(match.group(1)) if match else None


def wait_for_bash_fallback_completion(
    *,
    process,
    marker_path: str,
    timeout_value: float,
    cancel_event=None,
    terminate_process_tree: Callable | None = None,
    poll_interval: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = clock() + max(0.0, float(timeout_value or 0.0))
    while read_bash_fallback_exit_code(marker_path) is None:
        if cancel_event and cancel_event.is_set():
            if terminate_process_tree is not None:
                terminate_process_tree(process)
            return "cancelled"
        if clock() >= deadline:
            if terminate_process_tree is not None:
                terminate_process_tree(process)
            return "timed_out"
        sleep(poll_interval)
    return "completed"
