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

    def update_settings(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.data.settings, key):
                setattr(self.data.settings, key, value)

    def reload(self):
        return None

    def get_config_status(self):
        return {"status": "ok", "source": "smoke", "issues": []}

    def get_icon_cache_stats(self):
        return {"total_files": 0, "total_size_mb": 0}

    def _find_shortcut_with_folder(self, shortcut_id):
        for folder in self.data.folders:
            for item in folder.items:
                if item.id == shortcut_id:
                    return folder, item
        return None, None

    def batch_update(self, immediate=False):
        class Ctx:
            def __enter__(self_nonlocal):
                return self

            def __exit__(self_nonlocal, *args):
                return False

        return Ctx()

    def save(self, immediate=False):
        return True

    def _mark_history(self, title, detail):
        return None


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


def test_diagnostics_window_one_click_fix_smoke(qapp, tmp_path, monkeypatch):
    import ui.diagnostics_window as diagnostics_mod
    from ui.diagnostics_window import DiagnosticsWindow

    manager = _SmokeManager(tmp_path)
    manager.data.folders[0].items[0].target_path = str(tmp_path / "missing.exe")
    monkeypatch.setattr(diagnostics_mod, "QTimer", SimpleNamespace(singleShot=lambda _ms, _func: None))
    monkeypatch.setattr(
        diagnostics_mod.ThemedMessageBox,
        "question",
        lambda *args, **kwargs: diagnostics_mod.ThemedMessageBox.Yes,
    )
    infos = []
    monkeypatch.setattr(diagnostics_mod.ThemedMessageBox, "information", lambda *args, **kwargs: infos.append(args))

    window = DiagnosticsWindow(manager)
    try:
        window.refresh = lambda: None
        window._on_collect_finished([DiagnosticItem("图标检查", "error", "bad", "", "", {"fixable": 1})], "")
        assert window.fix_btn.isEnabled()

        window.apply_all_fixes()
        assert "正在后台修复" in window.text.toPlainText()
        if window._fix_thread:
            assert window._fix_thread.wait(5000)
            qapp.processEvents()

        assert manager.data.folders[0].items == []
        assert infos
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


def test_settings_panel_global_scale_apply_is_explicit_and_uses_five_percent_steps(qapp, tmp_path, monkeypatch):
    import core.auto_start_manager as auto_start_manager
    from ui.config_window.settings_panel import SettingsPanel

    monkeypatch.setattr(auto_start_manager, "get_auto_start_check_result", lambda: (False, "smoke"))

    manager = _SmokeManager(tmp_path)
    manager.data.settings.ui_scale_percent = 100

    class FakeTrayApp:
        def __init__(self):
            self.applied = []

        def apply_ui_scale_and_reopen_config(self, percent):
            self.applied.append(percent)

    tray_app = FakeTrayApp()
    panel = SettingsPanel(manager, tray_app=tray_app)
    try:
        panel.ui_scale_edit.setText("127")
        panel._on_ui_scale_text_edited("127")

        assert manager.data.settings.ui_scale_percent == 100
        assert tray_app.applied == []
        assert panel.ui_scale_slider.value() == 125

        panel._on_ui_scale_apply_clicked()

        assert manager.data.settings.ui_scale_percent == 125
        assert tray_app.applied == [125]
        assert panel.ui_scale_edit.text() == "125"
        assert panel.ui_scale_slider.value() == 125
    finally:
        panel.close()
        qapp.processEvents()


def test_command_dialog_line_edits_do_not_double_scale_fonts(qapp):
    from core.data_models import ShortcutItem, ShortcutType
    from ui.config_window.command_dialog import CommandDialog
    from ui.utils.ui_scale import set_scale

    set_scale(150)
    dialog = CommandDialog(shortcut=ShortcutItem(type=ShortcutType.COMMAND))
    try:
        for widget in (dialog.name_edit, dialog.workdir_edit, dialog.test_output):
            style = widget.styleSheet()
            assert "font-size: 20px" in style
            assert "font-size: 30px" not in style
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
        set_scale(100)


def test_chain_node_property_panel_styles_do_not_double_scale(qapp):
    from ui.config_window.chain_canvas import NodePropertyPanel
    from ui.utils.ui_scale import set_scale

    set_scale(150)
    panel = NodePropertyPanel()
    try:
        panel._apply_theme()

        assert "font-size: 20px" in panel.group_box.styleSheet()
        assert "font-size: 30px" not in panel.group_box.styleSheet()
        assert "font-size: 24px" not in panel.source_btn.styleSheet()
    finally:
        panel.deleteLater()
        qapp.processEvents()
        set_scale(100)
