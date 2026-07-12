"""Tests for clipboard service."""

from core.clipboard_service import (
    ClipboardClassification,
    ClipboardEmptyError,
    ClipboardError,
    ClipboardOpenError,
    ClipboardService,
    ClipboardSnapshot,
    Win32ClipboardImpl,
    clipboard_service,
)


class TestClipboardOpenError:
    def test_is_clipboard_error(self):
        err = ClipboardOpenError(code="open_timeout", message="test")
        assert isinstance(err, ClipboardError)
        assert err.code == "open_timeout"

    def test_empty_is_instance(self):
        err = ClipboardEmptyError(code="empty", message="empty")
        assert isinstance(err, ClipboardError)
        assert err.code == "empty"


class TestClipboardSnapshot:
    def test_is_empty_true(self):
        snap = ClipboardSnapshot(sequence=0, captured_at=0.0)
        assert snap.is_empty is True

    def test_is_empty_false_with_text(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="hello")
        assert snap.is_empty is False

    def test_is_empty_false_with_files(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, file_paths=["a.txt"])
        assert snap.is_empty is False

    def test_has_image_true(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, image_info={"width": 100, "height": 200})
        assert snap.has_image is True

    def test_has_image_false(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0)
        assert snap.has_image is False


class TestClipboardClassification:
    def test_default_fields(self):
        cls = ClipboardClassification(kind="url", confidence=0.95, summary="https://example.com")
        assert cls.kind == "url"
        assert cls.confidence == 0.95
        assert not cls.actions

    def test_with_actions(self):
        cls = ClipboardClassification(kind="json", confidence=0.98, summary="JSON object", actions=["format_json"])
        assert "format_json" in cls.actions


class TestClipboardService:
    def test_singleton_exists(self):
        assert clipboard_service is not None
        assert isinstance(clipboard_service, ClipboardService)

    def test_initial_stats(self):
        svc = ClipboardService()
        stats = svc.get_stats()
        assert stats["read_count"] == 0
        assert stats["write_count"] == 0

    def test_reset_stats(self):
        svc = ClipboardService()
        svc._stats["read_count"] = 5
        svc.reset_stats()
        assert svc.get_stats()["read_count"] == 0

    def test_get_sequence_number_returns_int(self):
        seq = clipboard_service.get_sequence_number()
        assert isinstance(seq, int)

    def test_is_format_available(self):
        # CF_UNICODETEXT should be valid as a format check
        result = clipboard_service.is_format_available(13)  # CF_UNICODETEXT
        # Returns truthy value (True or int 1 depending on context)
        assert result is not None

    def test_read_text_returns_string(self):
        text = clipboard_service.read_text()
        assert isinstance(text, str)

    def test_classify_empty(self):
        classification = clipboard_service.classify(ClipboardSnapshot(sequence=0, captured_at=0.0))
        assert classification.kind == "empty"
        assert classification.confidence == 1.0


class TestWin32ClipboardImpl:
    def test_get_sequence_number(self):
        seq = Win32ClipboardImpl.get_sequence_number()
        assert isinstance(seq, int)

    def test_get_available_formats(self):
        formats = Win32ClipboardImpl.get_available_formats()
        assert isinstance(formats, list)
