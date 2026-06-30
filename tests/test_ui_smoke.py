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


def test_base_dialog_crash_trace_disabled_by_default(monkeypatch):
    import builtins

    import ui.config_window.base_dialog as base_dialog

    calls = []

    def fail_open(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("crash trace should not write unless explicitly enabled")

    monkeypatch.delenv("QL_TRACE_DIALOG_CRASH", raising=False)
    monkeypatch.setattr(builtins, "open", fail_open)

    base_dialog._trace_to_crash_log("paintEvent.0: Smoke")

    assert calls == []


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
    from ui.update_dialog import UpdateDialog

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
    from ui.update_dialog import UpdateDialog

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


def test_config_window_animation_callback_is_generation_guarded():
    from ui.config_window.main_window import ConfigWindow

    window = ConfigWindow.__new__(ConfigWindow)
    window._window_animation_generation = 2
    calls = []

    ConfigWindow._run_window_animation_callback(window, 1, lambda: calls.append("stale"))
    ConfigWindow._run_window_animation_callback(window, 2, lambda: calls.append("current"))

    assert calls == ["current"]


def test_config_window_shortcut_dialog_history_is_released():
    from ui.config_window.main_window import ConfigWindow

    window = ConfigWindow.__new__(ConfigWindow)
    window._dialog_history = []
    window._active_file_dialog = None
    ended = []
    accepted = []
    window._end_shortcut_dialog_action = lambda: ended.append(True)
    window._clear_active_dialog_if_current = lambda attr, current: ConfigWindow._clear_active_dialog_if_current(
        window, attr, current
    )

    class _Dialog:
        def exec_(self):
            return 1

        def get_shortcut(self):
            return "shortcut"

    dialog = _Dialog()
    window._active_file_dialog = dialog

    ConfigWindow._run_shortcut_dialog(window, dialog, accepted.append, "_active_file_dialog")

    assert accepted == ["shortcut"]
    assert ended == [True]
    assert window._dialog_history == []
    assert window._active_file_dialog is None


def test_config_window_hidden_active_shortcut_dialog_does_not_block_reopen():
    from ui.config_window.main_window import ConfigWindow

    class HiddenDialog:
        def isVisible(self):
            return False

        def activateWindow(self):
            raise AssertionError("hidden stale dialog should not be activated")

        def raise_(self):
            raise AssertionError("hidden stale dialog should not be raised")

    window = SimpleNamespace(_active_file_dialog=HiddenDialog())

    assert ConfigWindow._activate_existing_dialog(window, "_active_file_dialog") is False
    assert window._active_file_dialog is None


def test_config_window_same_shortcut_button_is_briefly_debounced(monkeypatch):
    import ui.config_window.main_window as main_window_mod
    from ui.config_window.main_window import ConfigWindow

    now = [10.0]
    enabled_states = []
    monkeypatch.setattr(main_window_mod.time, "monotonic", lambda: now[0])
    window = SimpleNamespace(
        _shortcut_edit_active=False,
        _shortcut_action_last_trigger_at={},
        _shortcut_action_debounce_ms=250,
        _set_shortcut_action_buttons_enabled=lambda enabled: enabled_states.append(enabled),
    )

    assert ConfigWindow._begin_shortcut_dialog_action(window, "file") is True
    ConfigWindow._release_shortcut_dialog_action(window)

    now[0] += 0.10
    assert ConfigWindow._begin_shortcut_dialog_action(window, "file") is False

    now[0] += 0.20
    assert ConfigWindow._begin_shortcut_dialog_action(window, "file") is True
    assert enabled_states == [False, True, False]


def test_config_window_bottom_action_buttons_can_reopen_after_dialog_closes(monkeypatch):
    import ui.config_window.command_dialog as command_dialog_mod
    import ui.config_window.hotkey_dialog as hotkey_dialog_mod
    import ui.config_window.main_window as main_window_mod
    import ui.config_window.shortcut_dialog as shortcut_dialog_mod
    import ui.config_window.url_dialog as url_dialog_mod
    from ui.config_window.main_window import ConfigWindow

    class Signal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def emit(self):
            for callback in list(self.callbacks):
                callback()

    created = []

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            self.finished = Signal()
            created.append(type(self).__name__)

        def exec_(self):
            self.finished.emit()
            return 0

        def isVisible(self):
            return False

    class FakeShortcutDialog(FakeDialog):
        pass

    class FakeHotkeyDialog(FakeDialog):
        pass

    class FakeUrlDialog(FakeDialog):
        pass

    class FakeCommandDialog(FakeDialog):
        pass

    monkeypatch.setattr(shortcut_dialog_mod, "ShortcutDialog", FakeShortcutDialog)
    monkeypatch.setattr(hotkey_dialog_mod, "HotkeyDialog", FakeHotkeyDialog)
    monkeypatch.setattr(url_dialog_mod, "UrlDialog", FakeUrlDialog)
    monkeypatch.setattr(command_dialog_mod, "CommandDialog", FakeCommandDialog)
    now = [20.0]
    monkeypatch.setattr(main_window_mod.time, "monotonic", lambda: now[0])

    window = ConfigWindow.__new__(ConfigWindow)
    window._active_file_dialog = None
    window._active_hotkey_dialog = None
    window._active_url_dialog = None
    window._active_command_dialog = None
    window._shortcut_edit_active = False
    window._shortcut_action_last_trigger_at = {}
    window._shortcut_action_debounce_ms = 250
    window._dialog_history = []
    window.icon_grid = SimpleNamespace(current_folder_id="folder", load_folder=lambda _folder_id: None)
    window.data_manager = SimpleNamespace(add_shortcut=lambda *_args: None)
    window.settings_changed = SimpleNamespace(emit=lambda: None)
    window._set_shortcut_action_buttons_enabled = lambda _enabled: None

    actions = (
        ("file", ConfigWindow._on_add_file, FakeShortcutDialog),
        ("hotkey", ConfigWindow._on_add_hotkey, FakeHotkeyDialog),
        ("url", ConfigWindow._on_add_url, FakeUrlDialog),
        ("command", ConfigWindow._on_add_command, FakeCommandDialog),
    )

    for _name, action, dialog_type in actions:
        action(window)
        now[0] += 0.30
        action(window)
        now[0] += 0.30
        assert created.count(dialog_type.__name__) == 2


def test_launcher_popup_initializes_without_dock_items(qapp, tmp_path, monkeypatch):
    import ui.launcher_popup.popup_window as popup_window_mod
    from ui.launcher_popup.popup_window import LauncherPopup

    monkeypatch.setattr(popup_window_mod, "HAS_EXECUTOR", False)
    monkeypatch.setattr(popup_window_mod, "HAS_WIN32_SHELL", False)

    manager = _SmokeManager(tmp_path)
    manager.data.settings.dock_enabled = False

    popup = LauncherPopup(manager, 100, 100, capture_selection=False)
    try:
        assert popup.dock_items == []
        assert popup.dock_height == 0
        assert popup.width() > 0
        assert popup.height() > 0
    finally:
        popup.close()
        qapp.processEvents()


def test_base_dialog_stale_animation_tick_does_not_stop_current_timer():
    from ui.config_window.base_dialog import BaseDialog

    dialog = BaseDialog.__new__(BaseDialog)
    dialog._dialog_animation_generation = 2
    dialog._dialog_finished = False
    stopped = []

    class _Timer:
        def stop(self):
            stopped.append(True)

    dialog._anim_timer = _Timer()

    BaseDialog._on_animation_tick(dialog, generation=1)

    assert stopped == []


def test_settings_panel_global_scale_apply_is_explicit_and_uses_five_percent_steps(qapp, tmp_path, monkeypatch):
    import core.auto_start_manager as auto_start_manager
    from ui.config_window import settings_system_page
    from ui.config_window.settings_panel import SettingsPanel

    monkeypatch.setattr(auto_start_manager, "get_auto_start_check_result", lambda: (False, "smoke"))
    monkeypatch.setattr(
        settings_system_page.ThemedMessageBox,
        "question",
        lambda *args, **kwargs: settings_system_page.ThemedMessageBox.Yes,
    )

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

        qapp.processEvents()
        set_scale(100)
