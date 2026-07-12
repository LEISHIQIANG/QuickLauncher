"""GDI / USER handle monitoring for diagnosing window-creation failures.

When a long-running tray application creates and destroys many HWNDs
(LauncherPopup, CommandPanel, shadow companions, PopupMenu, etc.),
the per-process GDI and USER handle counters can approach the Windows
default limit (10 000 each).  ``CreateWindowEx`` silently fails once
the limit is reached, and Qt logs:

    "Failed to create platform window for QWidget ..."

This module exposes a cheap ``get_gdi_handle_count()`` that callers can
sample before and after heavy window operations, and a
``warn_if_near_limit()`` helper that emits a single warning when the
count crosses a configurable threshold.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any, cast

logger = logging.getLogger(__name__)

_GUI_HANDLE_LIMIT = 10_000  # Windows default per-process limit
_GUI_WARN_THRESHOLD = 7_000  # emit warning above this count
_last_warn_time = 0.0


def get_gdi_handle_count() -> int:
    """Return the number of GDI handles owned by the current process.

    Uses ``GetGuiResources`` (GR_GDIOBJECTS = 0).  Returns -1 when the
    call fails (e.g. running on a non-Windows platform or inside a
    sandbox that blocks the API).
    """
    try:
        GR_GDIOBJECTS = 0
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        count = ctypes.windll.user32.GetGuiResources(handle, GR_GDIOBJECTS)
        return int(count)
    except Exception:
        return -1


def get_user_handle_count() -> int:
    """Return the number of USER handles (HWND, HMENU, etc.)."""
    try:
        GR_USEROBJECTS = 1
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        count = ctypes.windll.user32.GetGuiResources(handle, GR_USEROBJECTS)
        return int(count)
    except Exception:
        return -1


def get_gui_handle_counts() -> tuple[int, int]:
    """Return ``(GDI, USER)`` handle counts for the current process."""
    return get_gdi_handle_count(), get_user_handle_count()


def relieve_gdi_pressure(target: int = 8_500, max_attempts: int = 3) -> int:
    """Force GDI handle release by running GC and pending Qt deletions.

    On Windows, GDI handles are tied to native HWNDs.  When PyQt widgets
    are dereferenced in Python their C++ ``QWidget`` (and therefore the
    underlying HWND) may not be freed until the next garbage collection
    cycle and event-loop iteration.

    This helper runs ``gc.collect()`` and ``QApplication.processEvents()``
    in a loop, up to ``max_attempts`` times, stopping early if the GDI
    handle count drops below *target*.  Returns the final count.

    Safe to call even when ``QApplication`` is not yet initialised or
    when not on Windows (returns -1 in those cases).
    """
    gdi_count, user_count = get_gui_handle_counts()
    if gdi_count < 0 and user_count < 0:
        return -1
    if max(gdi_count, user_count) <= target:
        return gdi_count
    try:
        import gc

        from qt_compat import QApplication
    except ImportError:
        return gdi_count

    app = QApplication.instance()
    if app is None:
        return gdi_count

    logger.info(
        "GUI 句柄超过目标 %d，尝试释放资源 (GDI=%d, USER=%d)",
        target,
        gdi_count,
        user_count,
    )
    for attempt in range(max_attempts):
        collected = gc.collect(2)
        try:
            from qt_compat import QEvent

            QApplication.sendPostedEvents(None, cast(Any, QEvent).DeferredDelete)
        except Exception:
            logger.debug("处理 Qt DeferredDelete 事件失败", exc_info=True)
        app.processEvents()
        import time as _time

        _time.sleep(0.02)
        new_gdi_count, new_user_count = get_gui_handle_counts()
        logger.debug(
            "GUI 释放第 %d 轮: GC 收集 %d 个对象, GDI %d -> %d, USER %d -> %d",
            attempt + 1,
            collected,
            gdi_count,
            new_gdi_count,
            user_count,
            new_user_count,
        )
        gdi_count, user_count = new_gdi_count, new_user_count
        if max(gdi_count, user_count) <= target:
            logger.info("GUI 句柄已释放 (GDI=%d, USER=%d)", gdi_count, user_count)
            return gdi_count

    logger.warning(
        "GUI 资源释放 %d 轮后仍偏高 (GDI=%d, USER=%d)，当前句柄可能均为活跃窗口占用",
        max_attempts,
        gdi_count,
        user_count,
    )
    return gdi_count


def warn_if_near_limit() -> int:
    """Log a warning if the GDI handle count is above the threshold.

    Returns the current GDI handle count (or -1 on failure).
    Warnings are emitted at most once every 60 seconds to avoid
    flooding the log.
    """
    global _last_warn_time

    gdi_count, user_count = get_gui_handle_counts()
    if gdi_count < 0 and user_count < 0:
        return -1
    if max(gdi_count, user_count) >= _GUI_WARN_THRESHOLD:
        import time as _time

        now = _time.monotonic()
        if now - _last_warn_time >= 60.0:
            logger.warning(
                "GDI 句柄数 %d / %d (USER %d) 接近系统上限，" "后续窗口创建可能失败。请检查是否有窗口/阴影资源泄漏。",
                gdi_count,
                _GUI_HANDLE_LIMIT,
                user_count,
            )
            _last_warn_time = now
    return gdi_count
