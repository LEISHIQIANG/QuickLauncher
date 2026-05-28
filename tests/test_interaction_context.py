"""Tests for interaction context."""

from core.clipboard_service import ClipboardClassification, ClipboardSnapshot
from core.interaction_context import InteractionContext, TriggerContext
from core.selected_text_service import SelectedTextResult


class TestTriggerContext:
    def test_capture_returns_instance(self):
        ctx = TriggerContext.capture_current()
        assert ctx is not None
        assert isinstance(ctx, TriggerContext)
        assert ctx.captured_at > 0

    def test_default_trigger_method(self):
        ctx = TriggerContext()
        assert ctx.trigger_method == "unknown"

    def test_fields_default_to_zero_or_empty(self):
        ctx = TriggerContext()
        assert ctx.foreground_hwnd == 0
        assert ctx.process_name == ""


class TestInteractionContext:
    def test_default_construction(self):
        ctx = InteractionContext()
        assert ctx.trigger is None
        assert ctx.clipboard is None
        assert ctx.clipboard_classification is None
        assert ctx.selected_text is None
        assert ctx.selected_files == []
        assert ctx.selected_files_status == "idle"

    def test_with_trigger(self):
        trigger = TriggerContext(trigger_method="hotkey", process_name="explorer.exe")
        ctx = InteractionContext(trigger=trigger)
        assert ctx.trigger.trigger_method == "hotkey"
        assert ctx.trigger.process_name == "explorer.exe"

    def test_clipboard_text_property(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="hello")
        ctx = InteractionContext(clipboard=snap)
        assert ctx.clipboard_text == "hello"

    def test_clipboard_text_empty_when_no_clipboard(self):
        ctx = InteractionContext()
        assert ctx.clipboard_text == ""

    def test_clipboard_kind_from_classification(self):
        cls = ClipboardClassification(kind="url", confidence=0.95, summary="https://x.com")
        ctx = InteractionContext(clipboard_classification=cls)
        assert ctx.clipboard_kind == "url"

    def test_clipboard_kind_empty_when_no_classification(self):
        ctx = InteractionContext()
        assert ctx.clipboard_kind == ""

    def test_selected_text_text_property(self):
        st = SelectedTextResult(text="selected", success=True, method="clipboard_copy")
        ctx = InteractionContext(selected_text=st)
        assert ctx.selected_text_text == "selected"

    def test_selected_text_empty_when_none(self):
        ctx = InteractionContext()
        assert ctx.selected_text_text == ""

    def test_to_dict_basic(self):
        ctx = InteractionContext()
        d = ctx.to_dict()
        assert "trigger_method" in d
        assert "clipboard_kind" in d
        assert "selected_files_count" in d
        assert isinstance(d, dict)

    def test_to_dict_with_clipboard(self):
        snap = ClipboardSnapshot(sequence=1, captured_at=0.0, text="test data")
        cls = ClipboardClassification(kind="text", confidence=0.9, summary="test")
        ctx = InteractionContext(clipboard=snap, clipboard_classification=cls)
        d = ctx.to_dict()
        assert d["clipboard_kind"] == "text"
        assert d["clipboard_size"] == 9

    def test_to_dict_includes_selected_files_status(self):
        ctx = InteractionContext(selected_files=["a.txt", "b.txt"])
        d = ctx.to_dict()
        assert d["selected_files_count"] == 2

    def test_to_context_meta(self):
        ctx = InteractionContext()
        meta = ctx.to_context_meta()
        assert isinstance(meta, dict)
        assert "trigger_pos" not in meta
