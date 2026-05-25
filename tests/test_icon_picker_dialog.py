"""Icon picker lifecycle regressions."""

from qt_compat import QImage


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
