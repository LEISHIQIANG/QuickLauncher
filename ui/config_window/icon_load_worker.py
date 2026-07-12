"""Shared thread-safe icon loading worker for configuration dialogs.

This module is kept for backward compatibility.  New code should use
``core.qt_worker.IconLoadWorker`` directly, which provides the same
interface with base-class support for error reporting and cancellation.
"""

from __future__ import annotations

from core.qt_worker import IconLoadWorker

# Re-export for legacy importers
# The ``IconLoadWorker`` class now lives in ``core.qt_worker`` and provides:
#   - ``finished(sid, QImage)`` signal
#   - ``completed()`` signal
#   - ``error_occurred(str)`` signal
#   - ``cancel()`` method
#   - COM initialization via ``com_initialize()`` / ``com_uninitialize()``
__all__ = ["IconLoadWorker"]
