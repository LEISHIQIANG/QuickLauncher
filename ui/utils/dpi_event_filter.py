"""Native event filter for ``WM_DPICHANGED`` (PerMonitorV2 DPI awareness).

QuickLauncher's manifest declares ``PerMonitorV2`` DPI awareness, which
means Windows sends ``WM_DPICHANGED`` (0x02E0) whenever a top-level
window is moved to a monitor with a different DPI.  Since
``QT_AUTO_SCREEN_SCALE_FACTOR=0`` disables Qt's automatic DPI handling,
the application must respond to ``WM_DPICHANGED`` itself.

This module provides:

* :class:`DpiChangeEventFilter` – a :class:`QAbstractNativeEventFilter`
  that reads the new DPI from the message's ``lParam`` and invokes a
  user-supplied callback.
* :func:`install_dpi_filter` – convenience helper that installs the
  filter on the current :class:`QApplication`.

Integration example (in :class:`TrayApp`)::

    from ui.utils.dpi_event_filter import install_dpi_filter

    self._dpi_filter = install_dpi_filter(self._on_system_dpi_changed)
"""

from __future__ import annotations

import ctypes
import logging

from PyQt5.QtCore import QAbstractNativeEventFilter

from qt_compat import QApplication

logger = logging.getLogger(__name__)

WM_DPICHANGED = 0x02E0


def _event_type_bytes(event_type) -> bytes:
    """Normalise native event type to ``bytes`` (robust across PyQt5 versions)."""
    if isinstance(event_type, bytes):
        return event_type
    if isinstance(event_type, str):
        return event_type.encode("ascii", errors="ignore")
    try:
        return bytes(event_type)
    except Exception:
        return b""


class DpiChangeEventFilter(QAbstractNativeEventFilter):
    """Handle ``WM_DPICHANGED`` for PerMonitorV2 windows.

    When a window is moved to a monitor with a different DPI, Windows
    posts ``WM_DPICHANGED`` with the new DPI packed in ``lParam``
    (``LOWORD`` = DPI X, ``HIWORD`` = DPI Y).  This filter extracts the
    value and calls ``on_dpi_changed(new_scale_percent)``.
    """

    def __init__(self, on_dpi_changed=None):
        super().__init__()
        self._on_dpi_changed = on_dpi_changed

    def nativeEventFilter(self, event_type, message):
        """Intercept ``WM_DPICHANGED`` and invoke the callback."""
        if _event_type_bytes(event_type) != b"windows_generic_MSG":
            return False, 0

        try:
            from PyQt5 import sip
        except ImportError:
            import sip

        try:
            msg = ctypes.wintypes.MSG.from_address(int(sip.voidptr(message)))
        except Exception:
            return False, 0

        if msg.message == WM_DPICHANGED:
            # lParam LOWORD = new DPI X, HIWORD = new DPI Y
            new_dpi_x = msg.lParam & 0xFFFF
            if new_dpi_x > 0:
                new_scale = round(new_dpi_x / 96.0 * 100)
                logger.info(
                    "WM_DPICHANGED: new DPI=%d  →  recommended scale=%d%%",
                    new_dpi_x,
                    new_scale,
                )
                if self._on_dpi_changed:
                    self._on_dpi_changed(new_scale)
            return True, 0  # message handled

        return False, 0  # pass through


def install_dpi_filter(on_dpi_changed) -> DpiChangeEventFilter:
    """Install the WM_DPICHANGED filter on ``QApplication``.

    Parameters
    ----------
    on_dpi_changed:
        Callable ``(new_scale_percent: int) -> None`` invoked when the
        system DPI changes.

    Returns
    -------
    DpiChangeEventFilter
        The installed filter instance (keep a reference to prevent GC).

    Raises
    ------
    RuntimeError
        If ``QApplication`` has not been created yet.
    """
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication not created yet — cannot install DPI filter")
    filt = DpiChangeEventFilter(on_dpi_changed)
    app.installNativeEventFilter(filt)
    return filt
