from types import SimpleNamespace

import pytest

from core.data_models import AppData, Folder, ShortcutItem
from core.diagnostics import DiagnosticItem
from services.update.config import UpdateInfo

pytestmark = pytest.mark.ui


class _SmokeManager:
    def __init__(self, tmp_path):
        self.app_dir = tmp_path
        self.config_dir = tmp_path
        self.icons_dir = tmp_path / "icons"
        self.icons_dir.mkdir()
        self.data = AppData(folders=[Folder(id="f", name="Folder", items=[ShortcutItem(id="s", name="Shortcut")])])
        self.flushed = False

    def get_settings(self):
        return self.data.settings

    def get_runtime_revision(self):
        return 1

    def flush_pending_save(self):
        self.flushed = True

    def get_config_status(self):
        return {"status": "ok", "source": "smoke", "issues": []}

    def get_icon_cache_stats(self):
        return {"total_files": 0, "total_size_mb": 0}


def test_diagnostics_window_create_format_close_smoke(qapp, tmp_path, monkeypatch):
    import ui.diagnostics_window as diagnostics_mod
    from ui.diagnostics_window import DiagnosticsWindow

    monkeypatch.setattr(diagnostics_mod, "QTimer", SimpleNamespace(singleShot=lambda _ms, _func: None))
    window = DiagnosticsWindow(_SmokeManager(tmp_path))
    try:
        window._on_collect_finished([DiagnosticItem("Smoke", "ok", "ready", "details")], "")
        assert "Smoke" in window.text.toPlainText()
    finally:
        window.close()
        qapp.processEvents()


def test_update_dialog_available_create_close_smoke(qapp, monkeypatch):
    from qt_compat import QDialog
    from services.update.ui import UpdateDialog

    monkeypatch.setattr(QDialog, "exec_", lambda self: 0)
    called = {"download": False, "skip": False}
    update = UpdateInfo(has_update=True, version="9.9.9", changelog_zh="- 修复问题")

    UpdateDialog.show_update_available(
        update,
        on_download=lambda: called.__setitem__("download", True),
        on_skip=lambda: called.__setitem__("skip", True),
    )

    assert called == {"download": False, "skip": False}


def test_update_status_message_smoke():
    from services.update.ui import UpdateDialog

    assert "50%" in UpdateDialog.show_download_progress_text(5, 10)


def test_themed_messagebox_dialog_icons_are_png(qapp):
    from pathlib import Path

    from PIL import Image

    from ui.styles.themed_messagebox import ThemedMessageBox

    icon_types = (
        ThemedMessageBox.Information,
        ThemedMessageBox.Question,
        ThemedMessageBox.Warning,
        ThemedMessageBox.Critical,
        ThemedMessageBox.Download,
    )

    for icon_type in icon_types:
        path = Path(ThemedMessageBox._get_icon_path(icon_type))
        assert path.suffix == ".png"
        assert path.is_file()

        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == (96, 96)

        pixmap = ThemedMessageBox._get_icon_pixmap(icon_type, 24)
        assert not pixmap.isNull()
        assert pixmap.width() <= 24
        assert pixmap.height() <= 24


def test_config_window_create_close_smoke(qapp, tmp_path, monkeypatch):
    import ui.config_window.main_window as main_window_mod
    from ui.config_window.main_window import ConfigWindow

    monkeypatch.setattr(main_window_mod, "allow_drag_drop_for_widget", lambda _widget: None)
    manager = _SmokeManager(tmp_path)
    window = ConfigWindow(manager)
    try:
        qapp.processEvents()
        assert window.folder_panel.folder_list.count() >= 1
        assert window.icon_grid is not None
    finally:
        window.close()
        qapp.processEvents()

    assert manager.flushed is True
