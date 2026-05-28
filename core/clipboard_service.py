"""Unified Clipboard Service — thread-safe clipboard read/write/snapshot/restore.

Provides a single entry point for all clipboard operations across QuickLauncher.
Dual-implementation architecture:
  - Win32ClipboardImpl: thread-safe, uses win32clipboard, auto-initializes STA COM
  - QtClipboardImpl: main-thread only, uses QApplication.clipboard(), triggers signals

Usage:
    from core.clipboard_service import clipboard_service
    text = clipboard_service.read_text()
    snapshot = clipboard_service.read_snapshot()
    clipboard_service.write_text("hello")
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ── Error types ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class ClipboardError(RuntimeError):
    """Base for all clipboard errors."""

    def __init__(self, code: str, message: str = "", detail: dict | None = None):
        self.code = code
        self.detail = detail or {}
        super().__init__(message or code)


class ClipboardOpenError(ClipboardError):
    """OpenClipboard retries exhausted."""

    code = "open_timeout"


class ClipboardFormatUnreadableError(ClipboardError):
    """Specified format cannot be read."""

    code = "format_unreadable"


class ClipboardEmptyError(ClipboardError):
    """Clipboard is empty."""

    code = "empty"


class ClipboardRestoreError(ClipboardError):
    """Snapshot restore failed."""

    code = "restore_failed"


class ClipboardComError(ClipboardError):
    """COM initialization failed."""

    code = "com_init_failed"


class ClipboardUipiError(ClipboardError):
    """UIPI blocked cross-integrity read."""

    code = "uipi_blocked"


# ---------------------------------------------------------------------------
# ── Data models ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@dataclass
class ClipboardFormatInfo:
    format_id: int
    name: str
    readable: bool
    size_hint: int = 0


@dataclass
class ClipboardSnapshot:
    sequence: int
    captured_at: float
    formats: dict[int, object] = field(default_factory=dict)
    text: str = ""
    file_paths: list[str] = field(default_factory=list)
    html: str = ""
    rtf: bytes = b""
    image_info: dict = field(default_factory=dict)
    source: str = "win32"
    truncated: bool = False
    error: str = ""

    @property
    def has_image(self) -> bool:
        return bool(self.image_info and "width" in self.image_info)

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.file_paths and not self.html and not self.image_info


@dataclass
class ClipboardClassification:
    kind: str
    confidence: float
    summary: str
    actions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ── Constants ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Max text size for snapshot storage (100 KB)
_MAX_SNAPSHOT_TEXT_BYTES = 100 * 1024

# Format IDs we always store binary data for
CF_UNICODETEXT = 13
CF_TEXT = 1
CF_HDROP = 15
CF_DIB = 8
CF_BITMAP = 2
CF_DIBV5 = 17
CF_HTML = 4934  # "HTML Format" registered format
CF_RTF = 4930   # "Rich Text Format"
CF_LOCALE = 16
CF_OEMTEXT = 7
CF_PALETTE = 9

# Formats we never store binary for (detect-only)
_DETECT_ONLY_FORMATS = {CF_DIB, CF_BITMAP, CF_DIBV5, CF_LOCALE, CF_OEMTEXT, CF_PALETTE}

# Registered format name cache
_REGISTERED_FORMAT_NAMES: dict[int, str] = {}

# Global clipboard lock — OpenClipboard is process-level, all threads must serialize
_clipboard_lock = threading.RLock()

# Backoff delays for OpenClipboard (ms)
_OPEN_RETRY_DELAYS_MS = [10, 20, 50, 100, 100, 100, 200, 200]


def _get_format_name(format_id: int) -> str:
    """Get clipboard format name, cached."""
    if format_id in _REGISTERED_FORMAT_NAMES:
        return _REGISTERED_FORMAT_NAMES[format_id]
    try:
        import win32clipboard
        name = win32clipboard.GetClipboardFormatName(format_id)
        _REGISTERED_FORMAT_NAMES[format_id] = name
        return name
    except Exception:
        return f"format_{format_id}"


# ---------------------------------------------------------------------------
# ── Win32 implementation (thread-safe) ────────────────────────────────────
# ---------------------------------------------------------------------------


class Win32ClipboardImpl:
    """Clipboard implementation using win32clipboard — thread-safe with STA COM."""

    _com_local = threading.local()
    _use_worker_thread: bool = False
    _sta_thread: threading.Thread | None = None
    _sta_queue: queue.Queue | None = None

    @staticmethod
    def _ensure_sta():
        """Ensure STA COM on current thread before clipboard operations."""
        if getattr(Win32ClipboardImpl._com_local, "_com_initialized", False):
            return
        try:
            import pythoncom
            try:
                pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            except pythoncom.CO_E_ALREADYINITIALIZED:
                pass  # Already initialized (may be MTA — proceed with caution)
            except Exception:
                Win32ClipboardImpl._use_worker_thread = True
        except ImportError:
            pass  # pythoncom not available, try win32clipboard directly
        Win32ClipboardImpl._com_local._com_initialized = True

    @staticmethod
    def _open_clipboard(timeout_ms: int = 200) -> None:
        """Open clipboard with exponential backoff retry."""
        import win32clipboard

        Win32ClipboardImpl._ensure_sta()

        if Win32ClipboardImpl._use_worker_thread:
            Win32ClipboardImpl._run_on_sta_thread(win32clipboard.OpenClipboard)
            return

        last_error = None
        for attempt, delay_ms in enumerate(_OPEN_RETRY_DELAYS_MS):
            try:
                win32clipboard.OpenClipboard()
                return
            except Exception as e:
                last_error = e
                if attempt == 0:
                    # Diagnostic: log which window holds the clipboard
                    try:
                        holder = ctypes.windll.user32.GetOpenClipboardWindow()
                        if holder:
                            logger.debug("Clipboard held by hwnd=%d", holder)
                    except Exception:
                        pass
                if delay_ms:
                    time.sleep(delay_ms / 1000.0)

        raise ClipboardOpenError(
            message=f"OpenClipboard failed after {len(_OPEN_RETRY_DELAYS_MS)} retries",
            detail={"last_error": str(last_error)},
        )

    @staticmethod
    def _run_on_sta_thread(func, *args, **kwargs):
        """Run clipboard operation on a dedicated STA thread."""
        import queue as _queue

        if Win32ClipboardImpl._sta_thread is None:
            def _sta_worker():
                try:
                    import pythoncom
                    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
                except Exception:
                    pass
                q = Win32ClipboardImpl._sta_queue
                while True:
                    try:
                        cmd, a, kw, rq = q.get()
                        try:
                            rq.put(cmd(*a, **kw))
                        except Exception as e:
                            rq.put(e)
                    except Exception:
                        pass

            Win32ClipboardImpl._sta_queue = _queue.Queue()
            t = threading.Thread(target=_sta_worker, daemon=True, name="ClipboardSTA")
            t.start()
            Win32ClipboardImpl._sta_thread = t

        result_queue = _queue.Queue()
        Win32ClipboardImpl._sta_queue.put((func, args, kwargs, result_queue))
        result = result_queue.get(timeout=10)
        if isinstance(result, Exception):
            raise result
        return result

    # ---- read ----

    @staticmethod
    def read_text() -> str:
        """Read clipboard text. Returns empty string on failure (never raises)."""
        try:
            import win32clipboard
            import win32con

            Win32ClipboardImpl._open_clipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    return data or ""
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                    data = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                    if isinstance(data, (bytes, bytearray)):
                        try:
                            return data.decode("mbcs", errors="replace")
                        except Exception:
                            return data.decode(errors="replace")
                    return data or ""
            finally:
                win32clipboard.CloseClipboard()
        except ClipboardOpenError:
            raise
        except Exception:
            pass
        return ""

    @staticmethod
    def write_text(text: str) -> bool:
        """Write text to clipboard."""
        try:
            import win32clipboard
            import win32con

            Win32ClipboardImpl._open_clipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text or "")
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug("write_text failed: %s", e)
            return False

    @staticmethod
    def get_sequence_number() -> int:
        if os.name != "nt":
            return 0
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return 0

    @staticmethod
    def get_available_formats() -> list[ClipboardFormatInfo]:
        """Enumerate available clipboard formats."""
        formats: list[ClipboardFormatInfo] = []
        try:
            import win32clipboard

            Win32ClipboardImpl._open_clipboard()
            try:
                fmt = 0
                while True:
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                    if not fmt:
                        break
                    name = _get_format_name(fmt)
                    formats.append(ClipboardFormatInfo(format_id=fmt, name=name, readable=True))
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
        return formats

    @staticmethod
    def is_format_available(format_id: int) -> bool:
        try:
            import win32clipboard
            return win32clipboard.IsClipboardFormatAvailable(format_id)
        except Exception:
            return False

    @staticmethod
    def read_snapshot() -> ClipboardSnapshot:
        """Read full clipboard snapshot."""
        import win32clipboard
        import win32con

        sequence = Win32ClipboardImpl.get_sequence_number()
        captured_at = time.time()

        snapshot = ClipboardSnapshot(
            sequence=sequence,
            captured_at=captured_at,
        )

        Win32ClipboardImpl._open_clipboard()
        try:
            fmt = 0
            while True:
                fmt = win32clipboard.EnumClipboardFormats(fmt)
                if not fmt:
                    break

                # Detect-only formats: record metadata but don't store binary
                if fmt in _DETECT_ONLY_FORMATS:
                    if fmt == CF_DIB or fmt == CF_BITMAP or fmt == CF_DIBV5:
                        try:
                            data = win32clipboard.GetClipboardData(fmt)
                            if data:
                                import struct
                                if fmt == CF_DIB:
                                    # BITMAPINFOHEADER starts at offset 0
                                    if isinstance(data, bytes) and len(data) >= 40:
                                        w = struct.unpack_from("<i", data, 4)[0]
                                        h = struct.unpack_from("<i", data, 8)[0]
                                        snapshot.image_info = {
                                            "width": abs(w),
                                            "height": abs(h),
                                            "format": "DIB",
                                            "size_hint": len(data),
                                        }
                                elif fmt == CF_DIBV5:
                                    if isinstance(data, bytes) and len(data) >= 124:
                                        w = struct.unpack_from("<i", data, 4)[0]
                                        h = struct.unpack_from("<i", data, 8)[0]
                                        snapshot.image_info = {
                                            "width": abs(w),
                                            "height": abs(h),
                                            "format": "DIBV5",
                                            "size_hint": len(data),
                                        }
                        except Exception:
                            pass
                    continue

                try:
                    data = win32clipboard.GetClipboardData(fmt)
                except Exception:
                    continue

                # Check size limit for large data
                size_hint = 0
                if isinstance(data, bytes):
                    size_hint = len(data)
                    if size_hint > _MAX_SNAPSHOT_TEXT_BYTES * 10:
                        snapshot.truncated = True
                        continue
                elif isinstance(data, str):
                    size_hint = len(data.encode("utf-8"))

                # Store text formats
                if fmt == win32con.CF_UNICODETEXT:
                    snapshot.text = data or ""
                    if isinstance(snapshot.text, str) and len(snapshot.text.encode("utf-8")) > _MAX_SNAPSHOT_TEXT_BYTES:
                        snapshot.text = snapshot.text[:_MAX_SNAPSHOT_TEXT_BYTES]
                        snapshot.truncated = True
                elif fmt == win32con.CF_TEXT:
                    if not snapshot.text:
                        if isinstance(data, (bytes, bytearray)):
                            try:
                                snapshot.text = data.decode("mbcs", errors="replace")
                            except Exception:
                                snapshot.text = data.decode(errors="replace")
                        else:
                            snapshot.text = str(data or "")
                elif fmt == CF_HDROP:
                    if isinstance(data, (tuple, list)):
                        snapshot.file_paths = list(data)
                    elif isinstance(data, str):
                        snapshot.file_paths = [data]
                elif fmt == CF_HTML:
                    if isinstance(data, (bytes, bytearray)):
                        try:
                            snapshot.html = data.decode("utf-8", errors="replace")
                        except Exception:
                            snapshot.html = str(data)
                    elif isinstance(data, str):
                        snapshot.html = data
                    if len(snapshot.html.encode("utf-8")) > _MAX_SNAPSHOT_TEXT_BYTES:
                        snapshot.html = snapshot.html[:_MAX_SNAPSHOT_TEXT_BYTES]
                        snapshot.truncated = True

                # Store structured formats selectively
                if fmt in {win32con.CF_UNICODETEXT, win32con.CF_TEXT, CF_HDROP}:
                    snapshot.formats[fmt] = data

        except Exception as e:
            snapshot.error = str(e)
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

        return snapshot

    @staticmethod
    def restore_snapshot(snapshot: ClipboardSnapshot) -> bool:
        """Restore clipboard from a snapshot."""
        if snapshot is None:
            return False
        try:
            import win32clipboard
            import win32con

            Win32ClipboardImpl._open_clipboard(timeout_ms=300)
            try:
                win32clipboard.EmptyClipboard()
                ok = True

                # Restore text
                if snapshot.text:
                    try:
                        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, snapshot.text)
                    except Exception as e:
                        ok = False
                        logger.debug("restore CF_UNICODETEXT failed: %s", e)

                # Restore file paths
                if snapshot.file_paths:
                    try:
                        win32clipboard.SetClipboardData(CF_HDROP, snapshot.file_paths)
                    except Exception as e:
                        ok = False
                        logger.debug("restore CF_HDROP failed: %s", e)

                # Restore other formats from stored binary
                for fmt, data in snapshot.formats.items():
                    if fmt in (win32con.CF_UNICODETEXT, CF_TEXT, CF_HDROP):
                        continue  # Already restored above
                    try:
                        win32clipboard.SetClipboardData(fmt, data)
                    except Exception:
                        ok = False

                return ok
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug("restore_snapshot failed: %s", e)
            return False

    @staticmethod
    def write_html(html: str, plain_text: str) -> bool:
        """Write HTML + plain text fallback to clipboard."""
        if not html:
            return Win32ClipboardImpl.write_text(plain_text)
        try:
            import win32clipboard

            Win32ClipboardImpl._open_clipboard()
            try:
                win32clipboard.EmptyClipboard()

                import win32con
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, plain_text or "")

                # Build HTML Format with required header
                header = (
                    "Version:0.9\r\n"
                    "StartHTML:{start:09d}\r\n"
                    "EndHTML:{end:09d}\r\n"
                    "StartFragment:{frag_start:09d}\r\n"
                    "EndFragment:{frag_end:09d}\r\n"
                )
                fragment = html
                full_html = f"<!DOCTYPE html><html><body>{fragment}</body></html>"
                header_offset = len(header.format(
                    start=0, end=0, frag_start=0, frag_end=0
                ))
                frag_start = header_offset + len(
                    "<!DOCTYPE html><html><body>"
                )
                frag_end = frag_start + len(fragment)
                end_all = header_offset + len(full_html)

                header_filled = header.format(
                    start=header_offset,
                    end=end_all,
                    frag_start=frag_start,
                    frag_end=frag_end,
                )
                cf_html_data = header_filled + full_html

                # Register HTML Format if needed
                try:
                    cf_html_id = win32clipboard.RegisterClipboardFormat("HTML Format")
                    win32clipboard.SetClipboardData(cf_html_id, cf_html_data)
                except Exception:
                    pass

                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug("write_html failed: %s", e)
            return False


# ---------------------------------------------------------------------------
# ── Qt implementation (main-thread only, signal compatible) ───────────────
# ---------------------------------------------------------------------------


class QtClipboardImpl:
    """Clipboard implementation using QApplication.clipboard() — main thread only."""

    @staticmethod
    def read_text() -> str:
        try:
            from qt_compat import QApplication
            cb = QApplication.clipboard()
            return cb.text() or ""
        except Exception:
            return ""

    @staticmethod
    def write_text(text: str) -> bool:
        try:
            from qt_compat import QApplication
            QApplication.clipboard().setText(text)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# ── QtClipboardBridge — sync Win32 writes to Qt signals ───────────────────
# ---------------------------------------------------------------------------


class QtClipboardBridge:
    """Bridge Win32 clipboard writes to Qt clipboard signal.

    When a background thread writes to the clipboard via Win32, Qt's
    QClipboard.dataChanged signal is NOT automatically emitted. This
    bridge re-reads the clipboard text on the main thread and sets it
    on QClipboard, which triggers the signal for Qt consumers.
    """

    _instance = None
    _initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            try:
                from qt_compat import QObject, pyqtSignal

                class _Bridge(QObject):
                    _signal = pyqtSignal()

                    def __init__(self):
                        super().__init__()
                        self._signal.connect(self._sync_qt_clipboard)

                    def notify_change(self):
                        self._signal.emit()

                    def _sync_qt_clipboard(self):
                        try:
                            from qt_compat import QApplication
                            app = QApplication.instance()
                            if app is None:
                                return
                            text = Win32ClipboardImpl.read_text()
                            if text is not None:
                                QApplication.clipboard().setText(text)
                        except Exception:
                            pass

                cls._instance = _Bridge()
            except Exception:
                cls._instance = None
        return cls._instance

    @classmethod
    def notify_change(cls):
        bridge = cls.get_instance()
        if bridge is not None:
            try:
                bridge.notify_change()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ── ClipboardService — unified facade ─────────────────────────────────────
# ---------------------------------------------------------------------------


class ClipboardService:
    """Unified clipboard service — auto-selects implementation per thread.

    Main thread → QtClipboardImpl (triggers Qt signals)
    Background thread → Win32ClipboardImpl (thread-safe, STA COM)
    """

    def __init__(self):
        self._win32_impl = Win32ClipboardImpl
        self._qt_impl = QtClipboardImpl
        self._stats: dict = {
            "read_count": 0,
            "write_count": 0,
            "snapshot_count": 0,
            "restore_count": 0,
            "open_retries": 0,
            "open_failures": 0,
        }
        self._listeners: list[Callable[[int], None]] = []
        self._last_sequence: int = 0

    def _get_impl(self):
        if threading.current_thread() is threading.main_thread():
            return self._qt_impl
        return self._win32_impl

    def _get_win32_impl(self):
        return self._win32_impl

    # ---- read ----

    def read_text(self, timeout_ms: int = 200) -> str:
        """Read clipboard text. Returns empty string on failure."""
        self._stats["read_count"] += 1
        if threading.current_thread() is threading.main_thread():
            return self._qt_impl.read_text()
        try:
            return self._win32_impl.read_text()
        except ClipboardOpenError:
            self._stats["open_failures"] += 1
            return ""

    def read_text_win32(self, timeout_ms: int = 200) -> str:
        """Read clipboard text via Win32 — always thread-safe."""
        try:
            return self._win32_impl.read_text()
        except ClipboardOpenError:
            self._stats["open_failures"] += 1
            return ""

    # ---- write ----

    def write_text(self, text: str, *, preserve_history: bool = True) -> bool:
        """Write text to clipboard. Returns success."""
        self._stats["write_count"] += 1
        result = self._win32_impl.write_text(text)
        if result:
            self._notify_change()
            # Bridge to Qt if called from non-main thread
            if threading.current_thread() is not threading.main_thread():
                QtClipboardBridge.notify_change()
            self._check_sequence_change()
        return result

    def write_html(self, html: str, plain_text: str = "") -> bool:
        """Write HTML + plain text fallback."""
        self._stats["write_count"] += 1
        result = self._win32_impl.write_html(html, plain_text or "")
        if result:
            self._notify_change()
            if threading.current_thread() is not threading.main_thread():
                QtClipboardBridge.notify_change()
            self._check_sequence_change()
        return result

    # ---- snapshot ----

    def read_snapshot(self, timeout_ms: int = 200) -> ClipboardSnapshot:
        """Read full clipboard snapshot."""
        self._stats["snapshot_count"] += 1
        try:
            snapshot = self._win32_impl.read_snapshot()
            if snapshot.error:
                self._stats["open_failures"] += 1
            return snapshot
        except ClipboardOpenError:
            self._stats["open_failures"] += 1
            return ClipboardSnapshot(
                sequence=0,
                captured_at=time.time(),
                error="open_timeout",
            )
        except Exception as e:
            return ClipboardSnapshot(
                sequence=0,
                captured_at=time.time(),
                error=str(e),
            )

    def restore_snapshot(self, snapshot: ClipboardSnapshot, timeout_ms: int = 300) -> bool:
        """Restore clipboard from snapshot."""
        self._stats["restore_count"] += 1
        try:
            result = self._win32_impl.restore_snapshot(snapshot)
            if result:
                self._notify_change()
                if threading.current_thread() is not threading.main_thread():
                    QtClipboardBridge.notify_change()
                self._check_sequence_change()
            return result
        except Exception as e:
            logger.debug("restore_snapshot failed: %s", e)
            return False

    # ---- format info ----

    def get_sequence_number(self) -> int:
        return self._win32_impl.get_sequence_number()

    def get_available_formats(self) -> list[ClipboardFormatInfo]:
        return self._win32_impl.get_available_formats()

    def is_format_available(self, format_id: int) -> bool:
        return self._win32_impl.is_format_available(format_id)

    # ---- listeners ----

    def register_listener(self, callback: Callable[[int], None]) -> None:
        """Register a callback for clipboard sequence number changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback) -> None:
        self._listeners = [cb for cb in self._listeners if cb is not callback]

    def _notify_change(self):
        seq = self.get_sequence_number()
        for cb in self._listeners:
            try:
                cb(seq)
            except Exception as e:
                logger.debug("clipboard listener error: %s", e)

    def _check_sequence_change(self):
        seq = self.get_sequence_number()
        if seq and seq != self._last_sequence:
            self._last_sequence = seq
            self._notify_change()

    # ---- stats ----

    def get_stats(self) -> dict:
        return dict(self._stats)

    def reset_stats(self):
        self._stats = {k: 0 for k in self._stats}

    # ---- classify ----

    def classify(self, snapshot: ClipboardSnapshot | None = None) -> ClipboardClassification:
        """Classify clipboard content using classifiers."""
        from .clipboard_classifiers import classify_clipboard

        if snapshot is None:
            snapshot = self.read_snapshot()
        return classify_clipboard(snapshot)


# Global singleton
clipboard_service = ClipboardService()


# ---------------------------------------------------------------------------
# ── Compatibility wrappers (deprecated) ───────────────────────────────────
# ---------------------------------------------------------------------------


def read_clipboard_text_deprecated() -> str:
    """Deprecated: use clipboard_service.read_text() instead."""
    logger.debug("DEPRECATED: read_clipboard_text() called — use clipboard_service.read_text()")
    return clipboard_service.read_text_win32()
