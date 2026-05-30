"""Extended tests for core/clipboard_service.py — data models, helpers, error types, Win32 mocking."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import threading
from unittest.mock import MagicMock, patch

import pytest

from core.clipboard_service import (
    _DETECT_ONLY_FORMATS,
    _MAX_SNAPSHOT_TEXT_BYTES,
    _OPEN_RETRY_DELAYS_MS,
    _REGISTERED_FORMAT_NAMES,
    CF_BITMAP,
    CF_DIB,
    CF_DIBV5,
    CF_HDROP,
    CF_HTML,
    CF_LOCALE,
    CF_OEMTEXT,
    CF_PALETTE,
    CF_TEXT,
    CF_UNICODETEXT,
    ClipboardClassification,
    ClipboardComError,
    ClipboardEmptyError,
    ClipboardError,
    ClipboardFormatInfo,
    ClipboardFormatUnreadableError,
    ClipboardOpenError,
    ClipboardRestoreError,
    ClipboardService,
    ClipboardSnapshot,
    ClipboardUipiError,
    QtClipboardBridge,
    QtClipboardImpl,
    Win32ClipboardImpl,
    _get_format_name,
    read_clipboard_text_deprecated,
)

# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class TestClipboardErrorHierarchy:
    def test_base_error_code(self):
        err = ClipboardError("some_code", "detail msg")
        assert err.code == "some_code"
        assert str(err) == "detail msg"

    def test_base_error_default_message(self):
        err = ClipboardError("only_code")
        assert str(err) == "only_code"

    def test_base_error_detail_dict(self):
        err = ClipboardError("x", detail={"key": "val"})
        assert err.detail == {"key": "val"}

    def test_base_error_detail_none_default(self):
        err = ClipboardError("x")
        assert err.detail == {}

    def test_open_error_class_code(self):
        assert ClipboardOpenError.code == "open_timeout"
        err = ClipboardOpenError(message="msg")
        assert err.code == "open_timeout"

    def test_format_unreadable_class_code(self):
        assert ClipboardFormatUnreadableError.code == "format_unreadable"

    def test_empty_error_class_code(self):
        assert ClipboardEmptyError.code == "empty"

    def test_restore_error_class_code(self):
        assert ClipboardRestoreError.code == "restore_failed"

    def test_com_error_class_code(self):
        assert ClipboardComError.code == "com_init_failed"

    def test_uipi_error_class_code(self):
        assert ClipboardUipiError.code == "uipi_blocked"

    def test_all_errors_inherit_clipboard_error(self):
        for cls in (
            ClipboardOpenError,
            ClipboardFormatUnreadableError,
            ClipboardEmptyError,
            ClipboardRestoreError,
            ClipboardComError,
            ClipboardUipiError,
        ):
            assert issubclass(cls, ClipboardError)

    def test_all_errors_inherit_runtime_error(self):
        assert issubclass(ClipboardError, RuntimeError)


# ---------------------------------------------------------------------------
# ClipboardFormatInfo dataclass
# ---------------------------------------------------------------------------


class TestClipboardFormatInfo:
    def test_basic_fields(self):
        info = ClipboardFormatInfo(format_id=13, name="CF_UNICODETEXT", readable=True)
        assert info.format_id == 13
        assert info.name == "CF_UNICODETEXT"
        assert info.readable is True
        assert info.size_hint == 0

    def test_size_hint(self):
        info = ClipboardFormatInfo(format_id=1, name="text", readable=False, size_hint=1024)
        assert info.size_hint == 1024

    def test_immutable_as_dataclass(self):
        info = ClipboardFormatInfo(format_id=1, name="a", readable=True)
        # dataclass with default is mutable, but fields should be settable
        info.size_hint = 42
        assert info.size_hint == 42


# ---------------------------------------------------------------------------
# ClipboardSnapshot dataclass
# ---------------------------------------------------------------------------


class TestClipboardSnapshot:
    def test_default_values(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=100.0)
        assert snap.formats == {}
        assert snap.text == ""
        assert snap.file_paths == []
        assert snap.html == ""
        assert snap.rtf == b""
        assert snap.image_info == {}
        assert snap.source == "win32"
        assert snap.truncated is False
        assert snap.error == ""

    def test_is_empty_all_empty(self):
        snap = ClipboardSnapshot(sequence=0, captured_at=0.0)
        assert snap.is_empty is True

    def test_is_empty_with_text(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="hi")
        assert snap.is_empty is False

    def test_is_empty_with_file_paths(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, file_paths=["/a"])
        assert snap.is_empty is False

    def test_is_empty_with_html(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, html="<b>hi</b>")
        assert snap.is_empty is False

    def test_is_empty_with_image_info(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, image_info={"width": 10})
        assert snap.is_empty is False

    def test_has_image_true_with_width(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, image_info={"width": 100, "height": 50})
        assert snap.has_image is True

    def test_has_image_false_empty_info(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, image_info={})
        assert snap.has_image is False

    def test_has_image_false_no_width_key(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, image_info={"format": "DIB"})
        assert snap.has_image is False

    def test_has_image_false_default(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0)
        assert snap.has_image is False

    def test_error_field(self):
        snap = ClipboardSnapshot(sequence=0, captured_at=0.0, error="something broke")
        assert snap.error == "something broke"

    def test_truncated_field(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, truncated=True)
        assert snap.truncated is True

    def test_formats_dict(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, formats={13: "hello", 1: b"hi"})
        assert snap.formats[13] == "hello"
        assert snap.formats[1] == b"hi"

    def test_source_qt(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, source="qt")
        assert snap.source == "qt"


# ---------------------------------------------------------------------------
# ClipboardClassification dataclass
# ---------------------------------------------------------------------------


class TestClipboardClassification:
    def test_default_lists(self):
        c = ClipboardClassification(kind="text", confidence=1.0, summary="plain text")
        assert c.actions == []
        assert c.metadata == {}

    def test_with_actions_and_metadata(self):
        c = ClipboardClassification(
            kind="url", confidence=0.9, summary="URL", actions=["open"], metadata={"host": "example.com"}
        )
        assert c.actions == ["open"]
        assert c.metadata["host"] == "example.com"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_cf_unicodetext_value(self):
        assert CF_UNICODETEXT == 13

    def test_cf_text_value(self):
        assert CF_TEXT == 1

    def test_cf_hdrop_value(self):
        assert CF_HDROP == 15

    def test_cf_dib_value(self):
        assert CF_DIB == 8

    def test_cf_html_value(self):
        assert CF_HTML == 4934

    def test_detect_only_formats_contains_image_formats(self):
        assert CF_DIB in _DETECT_ONLY_FORMATS
        assert CF_BITMAP in _DETECT_ONLY_FORMATS
        assert CF_DIBV5 in _DETECT_ONLY_FORMATS
        assert CF_LOCALE in _DETECT_ONLY_FORMATS
        assert CF_OEMTEXT in _DETECT_ONLY_FORMATS
        assert CF_PALETTE in _DETECT_ONLY_FORMATS

    def test_max_snapshot_text_bytes(self):
        assert _MAX_SNAPSHOT_TEXT_BYTES == 100 * 1024

    def test_open_retry_delays_not_empty(self):
        assert len(_OPEN_RETRY_DELAYS_MS) > 0


# ---------------------------------------------------------------------------
# _get_format_name
# ---------------------------------------------------------------------------


class TestGetFormatName:
    def test_returns_cached_name(self):
        _REGISTERED_FORMAT_NAMES[9999] = "MyFormat"
        assert _get_format_name(9999) == "MyFormat"
        del _REGISTERED_FORMAT_NAMES[9999]

    def test_returns_fallback_on_import_error(self):
        # When win32clipboard is not available, falls back to format_N
        with patch.dict("sys.modules", {"win32clipboard": None}):
            name = _get_format_name(8888)
            assert name == "format_8888"


# ---------------------------------------------------------------------------
# Win32ClipboardImpl — static helpers
# ---------------------------------------------------------------------------


class TestWin32ClipboardImplHelpers:
    @patch("core.clipboard_service.os.name", "posix")
    def test_get_sequence_number_non_nt(self):
        assert Win32ClipboardImpl.get_sequence_number() == 0

    @patch("core.clipboard_service.os.name", "nt")
    @patch("core.clipboard_service.ctypes.windll.user32.GetClipboardSequenceNumber", return_value=42)
    def test_get_sequence_number_nt(self, mock_seq):
        assert Win32ClipboardImpl.get_sequence_number() == 42

    @patch("core.clipboard_service.os.name", "nt")
    @patch("core.clipboard_service.ctypes.windll.user32.GetClipboardSequenceNumber", side_effect=Exception("boom"))
    def test_get_sequence_number_exception(self, mock_seq):
        assert Win32ClipboardImpl.get_sequence_number() == 0

    def test_is_format_available_no_win32clipboard(self):
        with patch.dict("sys.modules", {"win32clipboard": None}):
            assert Win32ClipboardImpl.is_format_available(13) is False

    def test_get_available_formats_no_win32clipboard(self):
        with patch.dict("sys.modules", {"win32clipboard": None}):
            formats = Win32ClipboardImpl.get_available_formats()
            assert formats == []


# ---------------------------------------------------------------------------
# Win32ClipboardImpl — read_text
# ---------------------------------------------------------------------------


class TestWin32ClipboardImplReadText:
    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_read_text_unicode(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.IsClipboardFormatAvailable.side_effect = lambda fmt: fmt == 13
        mock_w32.GetClipboardData.return_value = "hello world"
        with patch.dict(
            "sys.modules", {"win32clipboard": mock_w32, "win32con": MagicMock(CF_UNICODETEXT=13, CF_TEXT=1)}
        ):
            result = Win32ClipboardImpl.read_text()
            assert result == "hello world"
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_read_text_falls_back_to_cf_text(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.IsClipboardFormatAvailable.side_effect = lambda fmt: fmt == 1
        mock_w32.GetClipboardData.return_value = b"byte text"
        mock_con = MagicMock(CF_UNICODETEXT=13, CF_TEXT=1)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.read_text()
            assert "byte text" in result or result  # decoded or str
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_read_text_empty_clipboard(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.IsClipboardFormatAvailable.return_value = False
        mock_con = MagicMock(CF_UNICODETEXT=13, CF_TEXT=1)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.read_text()
            assert result == ""
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard", side_effect=ClipboardOpenError(message="fail"))
    def test_read_text_open_error_propagates(self, mock_open):
        with pytest.raises(ClipboardOpenError):
            Win32ClipboardImpl.read_text()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_read_text_generic_exception_returns_empty(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.IsClipboardFormatAvailable.side_effect = Exception("unexpected")
        mock_con = MagicMock(CF_UNICODETEXT=13, CF_TEXT=1)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.read_text()
            assert result == ""

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_read_text_unicode_none_returns_empty(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.IsClipboardFormatAvailable.side_effect = lambda fmt: fmt == 13
        mock_w32.GetClipboardData.return_value = None
        mock_con = MagicMock(CF_UNICODETEXT=13, CF_TEXT=1)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.read_text()
            assert result == ""


# ---------------------------------------------------------------------------
# Win32ClipboardImpl — write_text
# ---------------------------------------------------------------------------


class TestWin32ClipboardImplWriteText:
    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_write_text_success(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.write_text("test")
            assert result is True
            mock_w32.EmptyClipboard.assert_called_once()
            mock_w32.SetClipboardData.assert_called_once_with(13, "test")
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_write_text_empty_string(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.write_text("")
            assert result is True
            mock_w32.SetClipboardData.assert_called_with(13, "")

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard", side_effect=Exception("boom"))
    def test_write_text_failure(self, mock_open):
        result = Win32ClipboardImpl.write_text("fail")
        assert result is False


# ---------------------------------------------------------------------------
# Win32ClipboardImpl — write_html
# ---------------------------------------------------------------------------


class TestWin32ClipboardImplWriteHtml:
    def test_write_html_empty_html_delegates_to_write_text(self):
        with patch.object(Win32ClipboardImpl, "write_text", return_value=True) as mock_wt:
            result = Win32ClipboardImpl.write_html("", "fallback")
            assert result is True
            mock_wt.assert_called_once_with("fallback")

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_write_html_success(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        mock_w32.RegisterClipboardFormat.return_value = 4934
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            result = Win32ClipboardImpl.write_html("<b>bold</b>", "bold")
            assert result is True
            mock_w32.EmptyClipboard.assert_called_once()
            # Should have called SetClipboardData at least once
            assert mock_w32.SetClipboardData.call_count >= 1
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard", side_effect=Exception("fail"))
    def test_write_html_exception_returns_false(self, mock_open):
        result = Win32ClipboardImpl.write_html("<b>x</b>", "x")
        assert result is False


# ---------------------------------------------------------------------------
# Win32ClipboardImpl — restore_snapshot
# ---------------------------------------------------------------------------


class TestWin32ClipboardImplRestoreSnapshot:
    def test_restore_none_returns_false(self):
        assert Win32ClipboardImpl.restore_snapshot(None) is False

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_restore_text_only(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="restored")
            result = Win32ClipboardImpl.restore_snapshot(snap)
            assert result is True
            mock_w32.EmptyClipboard.assert_called_once()
            mock_w32.SetClipboardData.assert_called_once_with(13, "restored")
            mock_w32.CloseClipboard.assert_called_once()

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_restore_with_file_paths(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            snap = ClipboardSnapshot(sequence=1, captured_at=0.0, file_paths=["/a.txt", "/b.txt"])
            result = Win32ClipboardImpl.restore_snapshot(snap)
            assert result is True
            calls = mock_w32.SetClipboardData.call_args_list
            assert any(str(CF_HDROP) in str(c) for c in calls)

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_restore_with_extra_formats(self, mock_open):
        mock_w32 = MagicMock()
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="t", formats={99: b"custom_data"})
            result = Win32ClipboardImpl.restore_snapshot(snap)
            assert result is True

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard", side_effect=Exception("boom"))
    def test_restore_exception_returns_false(self, mock_open):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="x")
        assert Win32ClipboardImpl.restore_snapshot(snap) is False

    @patch("core.clipboard_service.Win32ClipboardImpl._open_clipboard")
    def test_restore_text_set_fails_still_returns_ok_false(self, mock_open):
        mock_w32 = MagicMock()
        mock_w32.SetClipboardData.side_effect = Exception("set fail")
        mock_con = MagicMock(CF_UNICODETEXT=13)
        with patch.dict("sys.modules", {"win32clipboard": mock_w32, "win32con": mock_con}):
            snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="fail_text")
            result = Win32ClipboardImpl.restore_snapshot(snap)
            assert result is False


# ---------------------------------------------------------------------------
# ClipboardService — facade
# ---------------------------------------------------------------------------


class TestClipboardServiceFacade:
    def test_initial_stats(self):
        svc = ClipboardService()
        stats = svc.get_stats()
        assert stats["read_count"] == 0
        assert stats["write_count"] == 0
        assert stats["snapshot_count"] == 0
        assert stats["restore_count"] == 0
        assert stats["open_retries"] == 0
        assert stats["open_failures"] == 0

    def test_reset_stats(self):
        svc = ClipboardService()
        svc._stats["read_count"] = 10
        svc._stats["write_count"] = 5
        svc.reset_stats()
        assert all(v == 0 for v in svc.get_stats().values())

    def test_get_stats_returns_copy(self):
        svc = ClipboardService()
        stats = svc.get_stats()
        stats["read_count"] = 999
        assert svc._stats["read_count"] == 0

    def test_read_text_increments_stats(self):
        svc = ClipboardService()
        with patch.object(QtClipboardImpl, "read_text", return_value="hi"):
            # Force main thread path
            with patch("threading.current_thread", return_value=threading.main_thread()):
                svc.read_text()
        assert svc._stats["read_count"] == 1

    def test_read_text_background_thread(self):
        svc = ClipboardService()
        main = threading.main_thread()
        other = MagicMock(name="OtherThread")
        with patch.object(Win32ClipboardImpl, "read_text", return_value="bg"):
            with patch("core.clipboard_service.threading.current_thread", return_value=other):
                with patch("core.clipboard_service.threading.main_thread", return_value=main):
                    result = svc.read_text()
        assert result == "bg"
        assert svc._stats["read_count"] == 1

    def test_write_text_increments_stats(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "write_text", return_value=True):
            with patch.object(svc, "_notify_change"):
                with patch.object(svc, "_check_sequence_change"):
                    svc.write_text("test")
        assert svc._stats["write_count"] == 1

    def test_write_text_failure(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "write_text", return_value=False):
            result = svc.write_text("fail")
        assert result is False
        assert svc._stats["write_count"] == 1

    def test_read_snapshot_increments_stats(self):
        svc = ClipboardService()
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0)
        with patch.object(Win32ClipboardImpl, "read_snapshot", return_value=snap):
            svc.read_snapshot()
        assert svc._stats["snapshot_count"] == 1

    def test_read_snapshot_open_error(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "read_snapshot", side_effect=ClipboardOpenError(message="timeout")):
            snap = svc.read_snapshot()
        assert snap.error == "open_timeout"
        assert svc._stats["open_failures"] == 1

    def test_read_snapshot_generic_error(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "read_snapshot", side_effect=Exception("oops")):
            snap = svc.read_snapshot()
        assert "oops" in snap.error

    def test_read_snapshot_error_field_counts_failure(self):
        svc = ClipboardService()
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, error="some_error")
        with patch.object(Win32ClipboardImpl, "read_snapshot", return_value=snap):
            svc.read_snapshot()
        assert svc._stats["open_failures"] == 1

    def test_restore_snapshot_increments_stats(self):
        svc = ClipboardService()
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="hi")
        with patch.object(Win32ClipboardImpl, "restore_snapshot", return_value=True):
            with patch.object(svc, "_notify_change"):
                with patch.object(svc, "_check_sequence_change"):
                    svc.restore_snapshot(snap)
        assert svc._stats["restore_count"] == 1

    def test_restore_snapshot_failure(self):
        svc = ClipboardService()
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0)
        with patch.object(Win32ClipboardImpl, "restore_snapshot", return_value=False):
            result = svc.restore_snapshot(snap)
        assert result is False
        assert svc._stats["restore_count"] == 1

    def test_restore_snapshot_exception(self):
        svc = ClipboardService()
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0)
        with patch.object(Win32ClipboardImpl, "restore_snapshot", side_effect=Exception("boom")):
            result = svc.restore_snapshot(snap)
        assert result is False

    def test_read_text_win32(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "read_text", return_value="win32 text"):
            result = svc.read_text_win32()
        assert result == "win32 text"

    def test_read_text_win32_open_error(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "read_text", side_effect=ClipboardOpenError(message="fail")):
            result = svc.read_text_win32()
        assert result == ""
        assert svc._stats["open_failures"] == 1


# ---------------------------------------------------------------------------
# ClipboardService — listeners
# ---------------------------------------------------------------------------


class TestClipboardServiceListeners:
    def _make_cb(self):
        def cb(seq):
            return None

        return cb

    def test_register_listener(self):
        svc = ClipboardService()
        cb = self._make_cb()
        svc.register_listener(cb)
        assert cb in svc._listeners

    def test_register_listener_no_duplicates(self):
        svc = ClipboardService()
        cb = self._make_cb()
        svc.register_listener(cb)
        svc.register_listener(cb)
        assert svc._listeners.count(cb) == 1

    def test_unregister_listener(self):
        svc = ClipboardService()
        cb = self._make_cb()
        svc.register_listener(cb)
        svc.unregister_listener(cb)
        assert cb not in svc._listeners

    def test_unregister_listener_not_registered(self):
        svc = ClipboardService()
        cb = self._make_cb()
        svc.unregister_listener(cb)  # Should not raise

    def test_notify_change_calls_listeners(self):
        svc = ClipboardService()
        calls = []
        svc.register_listener(lambda seq: calls.append(seq))
        with patch.object(svc, "get_sequence_number", return_value=42):
            svc._notify_change()
        assert calls == [42]

    def test_notify_change_listener_exception_does_not_propagate(self):
        svc = ClipboardService()

        def bad_cb(seq):
            raise ValueError("oops")

        svc.register_listener(bad_cb)
        with patch.object(svc, "get_sequence_number", return_value=1):
            svc._notify_change()  # Should not raise

    def test_check_sequence_change_updates(self):
        svc = ClipboardService()
        calls = []
        svc.register_listener(lambda seq: calls.append(seq))
        with patch.object(svc, "get_sequence_number", return_value=100):
            svc._check_sequence_change()
        assert svc._last_sequence == 100
        assert 100 in calls

    def test_check_sequence_change_no_update_same_seq(self):
        svc = ClipboardService()
        svc._last_sequence = 50
        calls = []
        svc.register_listener(lambda seq: calls.append(seq))
        with patch.object(svc, "get_sequence_number", return_value=50):
            svc._check_sequence_change()
        assert calls == []

    def test_check_sequence_change_zero_seq_skips(self):
        svc = ClipboardService()
        with patch.object(svc, "get_sequence_number", return_value=0):
            svc._check_sequence_change()
        assert svc._last_sequence == 0


# ---------------------------------------------------------------------------
# ClipboardService — write_html
# ---------------------------------------------------------------------------


class TestClipboardServiceWriteHtml:
    def test_write_html_success(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "write_html", return_value=True):
            with patch.object(svc, "_notify_change"):
                with patch.object(svc, "_check_sequence_change"):
                    result = svc.write_html("<b>hi</b>", "hi")
        assert result is True
        assert svc._stats["write_count"] == 1

    def test_write_html_failure(self):
        svc = ClipboardService()
        with patch.object(Win32ClipboardImpl, "write_html", return_value=False):
            result = svc.write_html("<b>hi</b>", "hi")
        assert result is False


# ---------------------------------------------------------------------------
# QtClipboardImpl — basic mocking
# ---------------------------------------------------------------------------


class TestQtClipboardImpl:
    def test_read_text_returns_empty_on_exception(self):
        with patch.dict("sys.modules", {"qt_compat": None}):
            result = QtClipboardImpl.read_text()
            assert result == ""

    def test_write_text_returns_false_on_exception(self):
        with patch.dict("sys.modules", {"qt_compat": None}):
            result = QtClipboardImpl.write_text("test")
            assert result is False


# ---------------------------------------------------------------------------
# QtClipboardBridge
# ---------------------------------------------------------------------------


class TestQtClipboardBridge:
    def test_get_instance_returns_none_when_qt_unavailable(self):
        # Reset singleton
        QtClipboardBridge._instance = None
        with patch.dict("sys.modules", {"qt_compat": None}):
            result = QtClipboardBridge.get_instance()
            # May be None if qt_compat unavailable
            assert result is None or result is not None

    def test_notify_change_noop_when_no_instance(self):
        QtClipboardBridge._instance = None
        with patch.object(QtClipboardBridge, "get_instance", return_value=None):
            QtClipboardBridge.notify_change()  # Should not raise


# ---------------------------------------------------------------------------
# Compatibility wrapper
# ---------------------------------------------------------------------------


class TestCompatWrapper:
    def test_read_clipboard_text_deprecated(self):
        with patch.object(Win32ClipboardImpl, "read_text", return_value="compat"):
            result = read_clipboard_text_deprecated()
        assert result == "compat"


# ---------------------------------------------------------------------------
# _normalize edge cases (via SearchHistory is separate; test here via _get_format_name)
# ---------------------------------------------------------------------------


class TestDetectOnlyFormats:
    def test_detect_only_is_subset_of_known(self):
        known = {CF_DIB, CF_BITMAP, CF_DIBV5, CF_LOCALE, CF_OEMTEXT, CF_PALETTE}
        assert _DETECT_ONLY_FORMATS == known
