"""SelectedTextService — multi-strategy selected text reading.

Provides a unified entry point for reading selected text from the foreground
window. Uses a combination of strategies:
  1. Win32 Edit/RichEdit (non-invasive, no clipboard change)
  2. Clipboard copy fallback (Ctrl+C simulation with clipboard restore)

Usage:
    from core.selected_text_service import selected_text_service
    result = selected_text_service.get_selected_text(trigger_context)
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ── Error types ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class SelectedTextError(RuntimeError):
    """Base for selected text errors."""

    def __init__(self, code: str, message: str = "", detail: dict | None = None):
        self.code = code
        self.detail = detail or {}
        super().__init__(message or code)


# ---------------------------------------------------------------------------
# ── Data models ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@dataclass
class SelectedTextResult:
    text: str
    success: bool
    method: str  # "win32_edit", "clipboard_copy", "uia", "none"
    error: str = ""
    hwnd: int = 0
    process_name: str = ""
    window_title: str = ""
    captured_at: float = 0.0
    clipboard_changed: bool = False
    restored_clipboard: bool = False
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# ── Constants ────────────────────────────────────────────────----------
# ---------------------------------------------------------------------------

# Win32 Edit control class names
_EDIT_CLASS_NAMES = {"Edit", "RichEdit20W", "RICHEDIT50W", "RichEdit20A", "RichEdit"}

# EM_GETSEL
EM_GETSEL = 0x00B0
# WM_GETTEXT
WM_GETTEXT = 0x000D
# WM_GETTEXTLENGTH
WM_GETTEXTLENGTH = 0x000E

# SendMessageTimeout flags
SMTO_ABORTIFHUNG = 0x0002

# Maximum text length for Win32 Edit strategy
_MAX_WIN32_EDIT_LENGTH = 65535

# Clipboard fallback poll parameters
_CLIPBOARD_POLL_INTERVAL = 0.03
_CLIPBOARD_MAX_POLLS = 12

# UIPI integrity check
_HIGH_INTEGRITY_SID = "S-1-16-12288"


# ---------------------------------------------------------------------------
# ── SelectedTextService ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class SelectedTextService:
    """Unified selected text reading service."""

    def __init__(self):
        self._lock = threading.Lock()

    def get_selected_text(
        self,
        foreground_hwnd: int | None = None,
        foreground_process_name: str = "",
        foreground_window_title: str = "",
        *,
        timeout_ms: int = 600,
        allow_clipboard_fallback: bool = True,
        restore_clipboard: bool = True,
    ) -> SelectedTextResult:
        """Read selected text from the foreground window.

        Args:
            foreground_hwnd: The foreground window handle to read from.
            foreground_process_name: Process name for diagnostics.
            foreground_window_title: Window title for diagnostics.
            timeout_ms: Overall timeout.
            allow_clipboard_fallback: Whether to allow Ctrl+C fallback.
            restore_clipboard: Whether to restore clipboard after fallback.

        Returns:
            SelectedTextResult with the selected text and metadata.
        """
        start = time.monotonic()
        captured_at = time.time()

        # Fast path: try Win32 Edit/RichEdit first (non-invasive)
        if foreground_hwnd:
            result = self._try_win32_edit(foreground_hwnd, timeout_ms=200)
            if result and result.success:
                result.captured_at = captured_at
                result.duration_ms = (time.monotonic() - start) * 1000
                return result

        # Fallback: clipboard copy method
        if allow_clipboard_fallback:
            result = self._clipboard_copy_fallback(
                foreground_hwnd=foreground_hwnd,
                timeout_ms=timeout_ms,
                restore_clipboard=restore_clipboard,
            )
            if result:
                result.captured_at = captured_at
                result.duration_ms = (time.monotonic() - start) * 1000
                if not result.text and not result.error:
                    result.error = "no_text"
                return result

        # No strategy succeeded
        return SelectedTextResult(
            text="",
            success=False,
            method="none",
            error="no_strategy",
            hwnd=foreground_hwnd or 0,
            process_name=foreground_process_name,
            window_title=foreground_window_title,
            captured_at=captured_at,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    # ------------------------------------------------------------------
    # Win32 Edit/RichEdit strategy (non-invasive)
    # ------------------------------------------------------------------

    def _try_win32_edit(self, hwnd: int, timeout_ms: int = 200) -> SelectedTextResult | None:
        """Try to read selected text via Win32 Edit/RichEdit messages.

        Non-invasive — does not touch clipboard.
        Only works with standard Edit/RichEdit controls.
        """
        if os.name != "nt" or not hwnd:
            return None

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        try:
            # 1. Get focus control within the window
            focus_hwnd = user32.GetFocus()
            if not focus_hwnd:
                return None

            # 2. Check class name
            class_buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(focus_hwnd, class_buf, 64)
            class_name = class_buf.value or ""

            if class_name not in _EDIT_CLASS_NAMES:
                return None

            # 3. WaitForInputIdle on the target thread
            process_id = ctypes.wintypes.DWORD()
            thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if not thread_id:
                return None

            # Open process with SYNCHRONIZE
            SYNCHRONIZE = 0x00100000
            target_process = kernel32.OpenProcess(SYNCHRONIZE, False, process_id.value)
            if target_process:
                try:
                    WAIT_TIMEOUT = 0x102
                    idle_result = kernel32.WaitForInputIdle(target_process, min(timeout_ms, 100))
                    if idle_result == WAIT_TIMEOUT:
                        kernel32.CloseHandle(target_process)
                        return None
                finally:
                    kernel32.CloseHandle(target_process)

            # 4. AttachThreadInput
            current_id = kernel32.GetCurrentThreadId()
            attached = bool(user32.AttachThreadInput(current_id, thread_id, True))
            if not attached:
                return None

            try:
                # 5. Get selection range via EM_GETSEL (64-bit compatible)
                sel_result = user32.SendMessageW(focus_hwnd, EM_GETSEL, 0, 0)
                sel_start = sel_result & 0xFFFF
                sel_end = (sel_result >> 16) & 0xFFFF

                if sel_start == sel_end:
                    # No selection
                    return None

                # 6. Get text length
                text_length = user32.SendMessageW(focus_hwnd, WM_GETTEXTLENGTH, 0, 0)

                if text_length <= 0:
                    return None

                # 7. For selections spanning very long text, skip Win32 method
                if text_length > _MAX_WIN32_EDIT_LENGTH:
                    return None

                # 8. Get full text via SendMessageTimeout
                buf = ctypes.create_unicode_buffer(text_length + 1)
                result = user32.SendMessageTimeoutW(
                    focus_hwnd,
                    WM_GETTEXT,
                    text_length + 1,
                    buf,
                    SMTO_ABORTIFHUNG,
                    min(timeout_ms, 100),
                )
                if not result:
                    return None

                full_text = buf.value or ""
                selected = full_text[sel_start:sel_end]

                if selected:
                    return SelectedTextResult(
                        text=selected,
                        success=True,
                        method="win32_edit",
                        hwnd=hwnd,
                    )
                return None
            finally:
                user32.AttachThreadInput(current_id, thread_id, False)

        except Exception as e:
            logger.debug("Win32 Edit strategy failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Clipboard copy fallback strategy
    # ------------------------------------------------------------------

    def _clipboard_copy_fallback(
        self,
        foreground_hwnd: int | None = None,
        *,
        timeout_ms: int = 600,
        restore_clipboard: bool = True,
    ) -> SelectedTextResult | None:
        """Fallback: save clipboard, simulate Ctrl+C, read text, restore clipboard."""
        if os.name != "nt":
            return None

        from .clipboard_service import clipboard_service

        # Acquire lock to prevent concurrent clipboard operations
        if not self._lock.acquire(timeout=timeout_ms / 1000.0):
            return SelectedTextResult(
                text="", success=False, method="clipboard_copy", error="lock_timeout"
            )

        try:
            snapshot = clipboard_service.read_snapshot()
            original_sequence = clipboard_service.get_sequence_number()

            # Check for self-window (QuickLauncher window)
            if foreground_hwnd:
                from .shortcut_hotkey import HotkeyExecutionMixin

                # Get foreground window
                current_fg = ctypes.windll.user32.GetForegroundWindow() if os.name == "nt" else 0
                # If we can detect QL window, refuse
                try:
                    from core import call_callback

                    # Check if our window is the foreground
                    if current_fg and current_fg == self._get_self_hwnd():
                        return SelectedTextResult(
                            text="",
                            success=False,
                            method="clipboard_copy",
                            error="self_window",
                        )
                except Exception:
                    pass

            # Restore foreground window and simulate Ctrl+C
            self._restore_window_and_copy(foreground_hwnd)

            # Poll for clipboard change
            text = ""
            clipboard_changed = False
            for _ in range(_CLIPBOARD_MAX_POLLS):
                time.sleep(_CLIPBOARD_POLL_INTERVAL)
                if clipboard_service.get_sequence_number() != original_sequence:
                    clipboard_changed = True
                    break

            if clipboard_changed:
                text = clipboard_service.read_text_win32()

            # Restore clipboard
            restored = True
            if restore_clipboard and snapshot:
                restored = clipboard_service.restore_snapshot(snapshot)

            if text:
                return SelectedTextResult(
                    text=text,
                    success=True,
                    method="clipboard_copy",
                    clipboard_changed=True,
                    restored_clipboard=restored,
                )
            else:
                return SelectedTextResult(
                    text="",
                    success=False,
                    method="clipboard_copy",
                    error="timeout" if not clipboard_changed else "no_text",
                    clipboard_changed=clipboard_changed,
                    restored_clipboard=restored,
                )

        except Exception as e:
            logger.debug("clipboard_copy fallback failed: %s", e)
            return SelectedTextResult(
                text="",
                success=False,
                method="clipboard_copy",
                error=str(e),
            )
        finally:
            self._lock.release()

    def _restore_window_and_copy(self, foreground_hwnd: int | None = None) -> bool:
        """Restore foreground window and execute Ctrl+C."""
        try:
            from core import call_callback

            # Use restore_foreground_window from ShortcutExecutor via callback
            try:
                from core.shortcut_hotkey import HotkeyExecutionMixin as _he
                from core.shortcut_window_control import WindowControlMixin as _wc
            except Exception:
                pass

            # Direct approach: use ctypes
            if os.name == "nt":
                user32 = ctypes.windll.user32
                if foreground_hwnd and foreground_hwnd > 0:
                    user32.SetForegroundWindow(foreground_hwnd)
                    time.sleep(0.08)

                # Send Ctrl+C via keybd_event
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
                ctypes.windll.user32.keybd_event(0x43, 0, 0, 0)  # C down
                time.sleep(0.02)
                ctypes.windll.user32.keybd_event(0x43, 0, 2, 0)  # C up
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)  # Ctrl up
                return True
        except Exception as e:
            logger.debug("window restore and copy failed: %s", e)
        return False

    @staticmethod
    def _get_self_hwnd() -> int:
        """Get QuickLauncher's own window handle, if available."""
        try:
            from qt_compat import QApplication

            app = QApplication.instance()
            if app is None:
                return 0
            for widget in app.topLevelWidgets():
                if hasattr(widget, "winId"):
                    wid = widget.winId()
                    if wid:
                        return int(wid)
        except Exception:
            pass
        return 0

    # ------------------------------------------------------------------
    # UIPI / safety checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_uipi_blocked(hwnd: int) -> bool:
        """Check if the target window is at a higher integrity level than us."""
        if os.name != "nt" or not hwnd:
            return False
        try:
            process_id = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if not process_id.value:
                return False

            # Open process for query information
            PROCESS_QUERY_INFORMATION = 0x0400
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, process_id.value)
            if not handle:
                return False

            try:
                import ntsecuritycon
                import win32security

                # Get process token
                token = win32security.OpenProcessToken(handle, win32security.TOKEN_QUERY)
                try:
                    # Get integrity level
                    labels = win32security.GetTokenInformation(
                        token, ntsecuritycon.TokenIntegrityLevel
                    )
                    sid = win32security.ConvertSidToStringSid(labels)
                    return sid == _HIGH_INTEGRITY_SID
                finally:
                    kernel32.CloseHandle(handle)
            except Exception:
                return False
        except Exception:
            return False

    @staticmethod
    def is_locked_screen() -> bool:
        """Check if the current foreground window is the lock screen."""
        if os.name != "nt":
            return False
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value or ""
            class_buf = ctypes.create_unicode_buffer(64)
            ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 64)
            class_name = class_buf.value or ""
            # Lock screen: LogonUI.exe, class=#32770 or similar
            if "logon" in class_name.lower():
                return True
            if title and ("locked" in title.lower() or "锁屏" in title or "锁定" in title):
                return True
            return False
        except Exception:
            return False


# Global singleton
selected_text_service = SelectedTextService()
