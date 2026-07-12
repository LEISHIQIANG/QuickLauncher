"""Tests for interaction context."""

from types import SimpleNamespace

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


# ── Extended tests with mock objects ────────────────────────────────────


def _make_trigger(**kwargs):
    defaults = {
        "trigger_method": "hotkey",
        "trigger_pos": (100, 200),
        "foreground_hwnd": 0,
        "foreground_root_hwnd": 0,
        "process_id": 0,
        "process_name": "test.exe",
        "window_title": "Test Window",
        "captured_at": 0.0,
    }
    defaults.update(kwargs)
    return TriggerContext(**defaults)


def _make_clipboard_snapshot(text="hello", file_paths=None, has_image=False):
    return SimpleNamespace(text=text, file_paths=file_paths or [], has_image=has_image)


def _make_classification(kind="text"):
    return SimpleNamespace(kind=kind)


def _make_selected_text(text="selected", method="clipboard"):
    return SimpleNamespace(text=text, method=method)


def test_trigger_context_construction_with_all_fields():
    trigger = _make_trigger()
    assert trigger.trigger_method == "hotkey"
    assert trigger.trigger_pos == (100, 200)
    assert trigger.process_name == "test.exe"
    assert trigger.window_title == "Test Window"
    assert trigger.captured_at == 0.0


def test_trigger_context_default_construction():
    trigger = TriggerContext()
    assert trigger.trigger_method == "unknown"
    assert trigger.trigger_pos is None
    assert trigger.foreground_hwnd == 0
    assert trigger.process_name == ""
    assert trigger.window_title == ""


def test_interaction_context_clipboard_text_with_mock():
    clipboard = _make_clipboard_snapshot(text="mock text")
    ctx = InteractionContext(clipboard=clipboard)
    assert ctx.clipboard_text == "mock text"


def test_interaction_context_clipboard_text_none():
    ctx = InteractionContext(clipboard=None)
    assert ctx.clipboard_text == ""


def test_interaction_context_clipboard_kind_with_mock():
    classification = _make_classification(kind="url")
    ctx = InteractionContext(clipboard_classification=classification)
    assert ctx.clipboard_kind == "url"


def test_interaction_context_clipboard_kind_none():
    ctx = InteractionContext(clipboard_classification=None)
    assert ctx.clipboard_kind == ""


def test_interaction_context_selected_text_with_mock():
    selected = _make_selected_text(text="mock selected", method="clipboard")
    ctx = InteractionContext(selected_text=selected)
    assert ctx.selected_text_text == "mock selected"


def test_interaction_context_selected_text_none():
    ctx = InteractionContext(selected_text=None)
    assert ctx.selected_text_text == ""


def test_interaction_context_to_dict_with_trigger():
    trigger = _make_trigger()
    clipboard = _make_clipboard_snapshot(text="data")
    classification = _make_classification(kind="text")
    selected = _make_selected_text(text="sel", method="clipboard")
    ctx = InteractionContext(
        trigger=trigger,
        clipboard=clipboard,
        clipboard_classification=classification,
        selected_text=selected,
        selected_files=["a.txt", "b.txt"],
        selected_files_status="loaded",
    )
    d = ctx.to_dict()
    assert d["trigger_method"] == "hotkey"
    assert d["trigger_pos"] == (100, 200)
    assert d["foreground_process"] == "test.exe"
    assert d["foreground_window"] == "Test Window"
    assert d["clipboard_kind"] == "text"
    assert d["clipboard_size"] == 4  # len("data")
    assert d["has_clipboard_files"] is False
    assert d["has_clipboard_image"] is False
    assert d["selected_text_length"] == 3  # len("sel")
    assert d["selected_text_method"] == "clipboard"
    assert d["selected_files_count"] == 2
    assert d["selected_files_status"] == "loaded"


def test_interaction_context_to_dict_none_trigger():
    ctx = InteractionContext(trigger=None)
    d = ctx.to_dict()
    assert d["trigger_method"] == ""
    assert d["trigger_pos"] is None
    assert d["foreground_process"] == ""
    assert d["foreground_window"] == ""


def test_interaction_context_to_dict_clipboard_with_files():
    clipboard = _make_clipboard_snapshot(text="", file_paths=["/a/b.txt"])
    ctx = InteractionContext(clipboard=clipboard)
    d = ctx.to_dict()
    assert d["has_clipboard_files"] is True
    assert d["clipboard_size"] == 0


def test_interaction_context_to_dict_clipboard_with_image():
    clipboard = _make_clipboard_snapshot(text="", has_image=True)
    ctx = InteractionContext(clipboard=clipboard)
    d = ctx.to_dict()
    assert d["has_clipboard_image"] is True


def test_interaction_context_to_context_meta_no_trigger_pos():
    trigger = _make_trigger()
    ctx = InteractionContext(trigger=trigger)
    meta = ctx.to_context_meta()
    assert "trigger_pos" not in meta
    assert meta["trigger_method"] == "hotkey"


def test_interaction_context_to_context_meta_none_trigger():
    ctx = InteractionContext(trigger=None)
    meta = ctx.to_context_meta()
    assert "trigger_pos" not in meta
    assert meta["trigger_method"] == ""


def test_interaction_context_all_none():
    ctx = InteractionContext(trigger=None, clipboard=None, clipboard_classification=None, selected_text=None)
    assert ctx.clipboard_text == ""
    assert ctx.clipboard_kind == ""
    assert ctx.selected_text_text == ""
    d = ctx.to_dict()
    assert d["clipboard_size"] == 0
    assert d["selected_text_length"] == 0
    assert d["selected_files_count"] == 0
