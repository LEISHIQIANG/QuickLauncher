"""Tests for selected_text_service.py data models, error class, and guard logic."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.ui


class TestSelectedTextError:
    def test_basic(self):
        from core.selected_text_service import SelectedTextError

        err = SelectedTextError("no_text", "No text selected")
        assert err.code == "no_text"
        assert str(err) == "No text selected"
        assert err.detail == {}

    def test_with_detail(self):
        from core.selected_text_service import SelectedTextError

        err = SelectedTextError("lock_timeout", detail={"ms": 500})
        assert err.detail == {"ms": 500}
        assert str(err) == "lock_timeout"

    def test_default_message_uses_code(self):
        from core.selected_text_service import SelectedTextError

        err = SelectedTextError("my_code")
        assert str(err) == "my_code"


class TestSelectedTextResult:
    def test_defaults(self):
        from core.selected_text_service import SelectedTextResult

        r = SelectedTextResult(text="hello", success=True, method="win32_edit")
        assert r.text == "hello"
        assert r.success is True
        assert r.method == "win32_edit"
        assert r.error == ""
        assert r.hwnd == 0
        assert r.process_name == ""
        assert r.window_title == ""
        assert r.captured_at == 0.0
        assert r.clipboard_changed is False
        assert r.restored_clipboard is False
        assert r.duration_ms == 0.0

    def test_explicit_fields(self):
        from core.selected_text_service import SelectedTextResult

        r = SelectedTextResult(
            text="x",
            success=False,
            method="clipboard_copy",
            error="timeout",
            hwnd=12345,
            process_name="notepad",
            window_title="Untitled",
            captured_at=100.0,
            clipboard_changed=True,
            restored_clipboard=True,
            duration_ms=42.5,
        )
        assert r.hwnd == 12345
        assert r.process_name == "notepad"
        assert r.clipboard_changed is True
        assert r.duration_ms == 42.5


class TestGetSelectedTextGuards:
    """Test SelectedTextService.get_selected_text guard paths."""

    def test_no_hwnd_no_clipboard(self):
        from core.selected_text_service import SelectedTextService

        svc = SelectedTextService()
        result = svc.get_selected_text(
            foreground_hwnd=None,
            allow_clipboard_fallback=False,
        )
        assert result.success is False
        assert result.method == "none"
        assert result.error == "no_strategy"

    def test_non_nt_platform_returns_none_for_win32(self):
        from core.selected_text_service import SelectedTextService

        svc = SelectedTextService()
        with patch("core.selected_text_service.os.name", "posix"):
            result = svc._try_win32_edit(hwnd=12345)
            assert result is None

    def test_non_nt_clipboard_fallback_returns_none(self):
        from core.selected_text_service import SelectedTextService

        svc = SelectedTextService()
        with patch("core.selected_text_service.os.name", "posix"):
            result = svc._clipboard_copy_fallback(foreground_hwnd=12345)
            assert result is None

    def test_check_uipi_non_nt(self):
        from core.selected_text_service import SelectedTextService

        with patch("core.selected_text_service.os.name", "posix"):
            assert SelectedTextService.check_uipi_blocked(12345) is False

    def test_check_uipi_zero_hwnd(self):
        from core.selected_text_service import SelectedTextService

        assert SelectedTextService.check_uipi_blocked(0) is False

    def test_is_locked_screen_non_nt(self):
        from core.selected_text_service import SelectedTextService

        with patch("core.selected_text_service.os.name", "posix"):
            assert SelectedTextService.is_locked_screen() is False

    def test_get_self_hwnd_no_app(self):
        from core.selected_text_service import SelectedTextService
        from qt_compat import QApplication

        # Without QApplication, should return 0
        with patch.object(QApplication, "instance", return_value=None):
            result = SelectedTextService._get_self_hwnd()
        assert result == 0

    def test_singleton_exists(self):
        from core.selected_text_service import selected_text_service

        assert selected_text_service is not None


class TestClipboardCopyFallbackLockTimeout:
    """Test clipboard_copy_fallback lock timeout path."""

    def test_lock_timeout(self):
        from core.selected_text_service import SelectedTextService

        svc = SelectedTextService()
        # Acquire the lock so the fallback can't
        svc._lock.acquire()
        try:
            with patch("core.selected_text_service.os.name", "nt"):
                result = svc._clipboard_copy_fallback(timeout_ms=10)
            assert result.success is False
            assert result.error == "lock_timeout"
        finally:
            svc._lock.release()
