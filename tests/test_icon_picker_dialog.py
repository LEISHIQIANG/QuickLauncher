"""Icon picker lifecycle regressions."""

import pytest

from qt_compat import QImage

pytestmark = pytest.mark.ui


def test_icon_picker_disconnects_loader_signals_on_close(monkeypatch, qapp):
    from core.icon_extractor import IconExtractor
    from ui.config_window.icon_picker_dialog import IconPickerDialog

    monkeypatch.setattr(IconExtractor, "get_icon_count", lambda path: 0)
    dialog = IconPickerDialog(None, "C:/Windows/System32/shell32.dll")

    try:
        dialog.done(0)
        image = QImage(1, 1, QImage.Format_ARGB32)
        dialog._add_icon_item(1, image)

        assert dialog._stop_loading
        assert dialog._closing
        assert dialog.list_widget.count() == 0
    finally:
        dialog.deleteLater()


def test_icon_picker_initial_state(monkeypatch, qapp):
    from core.icon_extractor import IconExtractor
    from ui.config_window.icon_picker_dialog import IconPickerDialog

    monkeypatch.setattr(IconExtractor, "get_icon_count", lambda path: 0)
    dialog = IconPickerDialog(None, "C:/Windows/System32/shell32.dll")

    try:
        assert dialog.file_path == "C:/Windows/System32/shell32.dll"
        assert dialog.selected_index == -1
        assert not dialog._closing
        assert not dialog._stop_loading
        assert dialog.list_widget is not None
    finally:
        dialog.deleteLater()


def test_icon_picker_add_item_updates_list(monkeypatch, qapp):
    from core.icon_extractor import IconExtractor
    from ui.config_window.icon_picker_dialog import IconPickerDialog

    monkeypatch.setattr(IconExtractor, "get_icon_count", lambda path: 0)
    dialog = IconPickerDialog(None, "C:/Windows/System32/shell32.dll")

    try:
        image = QImage(16, 16, QImage.Format_ARGB32)
        dialog._add_icon_item(0, image)
        dialog._add_icon_item(1, image)

        assert dialog.list_widget.count() == 2
    finally:
        dialog.deleteLater()
