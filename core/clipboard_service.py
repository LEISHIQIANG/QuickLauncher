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

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

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

    def __init__(self, code: str = "open_timeout", message: str = "", detail: dict | None = None):
        super().__init__(code, message, detail)


class ClipboardFormatUnreadableError(ClipboardError):
    """Specified format cannot be read."""

    code = "format_unreadable"

    def __init__(self, message: str = "", detail: dict | None = None):
        super().__init__(self.code, message, detail)


class ClipboardEmptyError(ClipboardError):
    """Clipboard is empty."""

    code = "empty"

    def __init__(self, code: str = "empty", message: str = "", detail: dict | None = None):
        super().__init__(code, message, detail)


class ClipboardRestoreError(ClipboardError):
    """Snapshot restore failed."""

    code = "restore_failed"

    def __init__(self, message: str = "", detail: dict | None = None):
        super().__init__(self.code, message, detail)


class ClipboardComError(ClipboardError):
    """COM initialization failed."""

    code = "com_init_failed"

    def __init__(self, message: str = "", detail: dict | None = None):
        super().__init__(self.code, message, detail)


class ClipboardUipiError(ClipboardError):
    """UIPI blocked cross-integrity read."""

    code = "uipi_blocked"

    def __init__(self, message: str = "", detail: dict | None = None):
        super().__init__(self.code, message, detail)


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


# ClipboardClassification moved to clipboard_classifiers to break circular dependency.
# Re-exported here for backward compatibility.
from .clipboard_classifiers import ClipboardClassification  # noqa: E402

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
CF_RTF = 4930  # "Rich Text Format"
CF_LOCALE = 16
CF_OEMTEXT = 7
CF_PALETTE = 9

# Formats we never store binary for (detect-only)
_DETECT_ONLY_FORMATS = {CF_DIB, CF_BITMAP, CF_DIBV5, CF_LOCALE, CF_OEMTEXT, CF_PALETTE}

# Registered format name cache
_REGISTERED_FORMAT_NAMES: dict[int, str] = {}

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
        return name  # type: ignore[no-any-return]
    except Exception:
        logger.debug("GetClipboardFormatName failed for %d", format_id, exc_info=True)
        return f"format_{format_id}"


# ---------------------------------------------------------------------------
# ── Win32 implementation (thread-safe) ────────────────────────────────────
# ---------------------------------------------------------------------------


class Win32ClipboardImpl:
    """Clipboard implementation using native QLclipboard.dll — thread-safe with STA COM."""

    _engine = None

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            from .native_services import _QLClipboardEngine

            cls._engine = _QLClipboardEngine.get()
        return cls._engine

    @staticmethod
    def read_text(timeout_ms: int = 200) -> str:
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        result = engine.read_text()
        return result if result is not None else ""

    @staticmethod
    def write_text(text: str, timeout_ms: int = 500) -> bool:
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        return engine.write_text(text)  # type: ignore[no-any-return]

    @staticmethod
    def get_sequence_number() -> int:
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        return engine.get_sequence_number()  # type: ignore[no-any-return]

    @staticmethod
    def get_available_formats() -> list[ClipboardFormatInfo]:
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        native_formats = engine.enum_formats()
        return [ClipboardFormatInfo(format_id=f["formatId"], name=f["name"], readable=True) for f in native_formats]

    @staticmethod
    def is_format_available(format_id: int) -> bool:
        try:
            import win32clipboard

            return win32clipboard.IsClipboardFormatAvailable(format_id)  # type: ignore[no-any-return]
        except Exception:
            return False

    @staticmethod
    def read_snapshot() -> ClipboardSnapshot:
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        return Win32ClipboardImpl._read_snapshot_native(engine)

    @staticmethod
    def _read_snapshot_native(engine) -> ClipboardSnapshot:
        import win32con

        sequence = Win32ClipboardImpl.get_sequence_number()
        captured_at = time.time()
        snapshot = ClipboardSnapshot(sequence=sequence, captured_at=captured_at)

        try:
            sid, count = engine.create_snapshot()
        except Exception as exc:
            snapshot.error = str(exc)
            return snapshot

        try:
            for i in range(count):
                try:
                    fmt_id, data = engine.get_snapshot_entry(sid, i)
                except Exception:
                    continue
                if fmt_id < 0:
                    continue

                if fmt_id == win32con.CF_UNICODETEXT:
                    if data:
                        text = data.decode("utf-16-le", errors="replace").rstrip("\x00")
                        snapshot.text = text
                elif fmt_id == win32con.CF_TEXT:
                    if data and not snapshot.text:
                        try:
                            snapshot.text = data.decode("mbcs", errors="replace")
                        except Exception:
                            snapshot.text = data.decode(errors="replace")
                elif fmt_id == CF_HDROP and data:
                    snapshot.file_paths = [data.decode("utf-16-le", errors="replace").rstrip("\x00")]
                elif fmt_id == CF_HTML and data:
                    try:
                        snapshot.html = data.decode("utf-8", errors="replace")
                    except Exception:
                        snapshot.html = str(data)
            engine.free_snapshot(sid)
        except Exception as exc:
            engine.free_snapshot(sid)
            snapshot.error = str(exc)
        return snapshot

    @staticmethod
    def restore_snapshot(snapshot: ClipboardSnapshot) -> bool:
        if snapshot is None:
            return False
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        if snapshot.text:
            return engine.write_text(snapshot.text)  # type: ignore[no-any-return]
        return False

    @staticmethod
    def write_html(html: str, plain_text: str) -> bool:
        if not html:
            return Win32ClipboardImpl.write_text(plain_text)
        engine = Win32ClipboardImpl._get_engine()
        if engine is None:
            raise ClipboardComError("QLclipboard.dll not available")
        engine.write_text(plain_text or "")
        html_bytes = engine.build_html_format(html)
        try:

            import win32clipboard

            deadline = time.monotonic() + max(10.0, 500.0) / 1000.0
            for delay_ms in _OPEN_RETRY_DELAYS_MS:
                try:
                    win32clipboard.OpenClipboard()
                    break
                except Exception:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    time.sleep(min(delay_ms / 1000.0, remaining))
            else:
                raise ClipboardOpenError("OpenClipboard failed for write_html")
            try:
                cf_html_id = win32clipboard.RegisterClipboardFormat("HTML Format")
                win32clipboard.SetClipboardData(cf_html_id, html_bytes)
            finally:
                win32clipboard.CloseClipboard()
        except ClipboardOpenError:
            raise
        except Exception:
            logger.debug("write_html encountered non-fatal clipboard error", exc_info=True)
        return True


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
            return cb.text() or ""  # type: ignore[unused-ignore, union-attr]
        except (ImportError, RuntimeError, AttributeError) as exc:
            logger.debug("读取Qt剪贴板文本失败: %s", exc, exc_info=True)
            return ""

    @staticmethod
    def write_text(text: str) -> bool:
        try:
            from qt_compat import QApplication

            QApplication.clipboard().setText(text)  # type: ignore[unused-ignore, union-attr]
            return True
        except (ImportError, RuntimeError, AttributeError) as exc:
            logger.debug("写入Qt剪贴板文本失败: %s", exc, exc_info=True)
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
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is not None:
                return cls._instance
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
                                QApplication.clipboard().setText(text)  # type: ignore[unused-ignore, union-attr]
                        except (ImportError, RuntimeError, AttributeError) as exc:
                            logger.debug("Qt剪贴板同步失败: %s", exc, exc_info=True)

                cls._instance = _Bridge()
            except (ImportError, RuntimeError, AttributeError):
                logger.warning("QtClipboardBridge singleton creation failed", exc_info=True)
                cls._instance = None
        return cls._instance

    @classmethod
    def notify_change(cls):
        bridge = cls.get_instance()
        if bridge is not None:
            try:
                bridge.notify_change()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("剪贴板桥接通知失败: %s", exc, exc_info=True)


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
            return self._win32_impl.read_text(timeout_ms)
        except ClipboardOpenError:
            self._stats["open_failures"] += 1
            return ""

    def read_text_win32(self, timeout_ms: int = 200) -> str:
        """Read clipboard text via Win32 — always thread-safe."""
        try:
            return self._win32_impl.read_text(timeout_ms)
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
            logger.debug("read_snapshot failed: %s", e, exc_info=True)
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
            logger.debug("restore_snapshot failed: %s", e, exc_info=True)
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
                logger.debug("clipboard listener error: %s", e, exc_info=True)

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
