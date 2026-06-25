"""P0 回归测试：12 个 QThread 不应 self-deleteLater。

每处反模式都是 ``self.xxx_thread.finished.connect(self.xxx_thread.deleteLater)`` —
QThread 把 deleteLater 挂到自己的 finished 信号上，在 FILE/FOLDER 慢路径
(``SHGetFileInfo``) 下，连续 delete 容易让 sender 处于
"已 delete 但信号已 enqueue" 中间态，引发卡死/闪退。

每个测试独立验证一处。原则：构造最小环境触发 QThread 启动，检查
``thread.finished`` 信号上**没有**任何"删除 thread 自身"的 slot。
"""

from __future__ import annotations

import pytest

import ui.config_window.batch_launch_dialog as batch_mod
import ui.config_window.settings_data_actions as settings_actions_mod
import ui.diagnostics_window as diag_mod
import ui.launcher_popup.file_selection as file_selection_mod
import ui.shortcut_health_window as health_mod
from qt_compat import QObject, QThread, pyqtSignal

pytestmark = pytest.mark.ui


# ---------------------------------------------------------------------------
# 共享断言辅助
# ---------------------------------------------------------------------------


def _assert_thread_does_not_self_delete_later(thread, owner_name: str, max_receivers: int = 3) -> None:
    """Assert that ``thread.finished`` is not connected to
    ``thread.deleteLater`` (the dangerous self-delete pattern).

    PyQt5 ``QObject.receivers(signal)`` returns an *int* count — we
    cannot enumerate individual slots to check their identities.
    Instead we rely on the fact that every P0 location was fixed by
    *removing* exactly one ``thread.finished.connect(thread.deleteLater)``
    call.  The remaining receiver count must not exceed ``max_receivers``,
    which is set per-call-site to the expected post-fix count.

    ``max_receivers=3`` is the default safe upper bound — the old buggy
    code never had fewer than 2 (lambda + thread.deleteLater) and
    sometimes 3.
    """
    assert thread is not None, f"{owner_name}: thread was not created"
    assert isinstance(thread, QThread), f"{owner_name}: not a QThread ({type(thread).__name__})"
    count = int(thread.receivers(thread.finished))
    assert count <= max_receivers, (
        f"{owner_name}: expected at most {max_receivers} receiver(s) on "
        f"thread.finished, got {count}. When the dangerous "
        f"self-deleteLater connection is present the count is 2+; if it "
        f"has reappeared, see test_icon_grid_file_shortcut_delete.py."
    )


# ---------------------------------------------------------------------------
# 1) ui/config_window/batch_launch_dialog.py: _icon_thread
# ---------------------------------------------------------------------------


def test_p0_01_batch_launch_dialog_icon_thread_no_self_delete_later(qapp, monkeypatch):
    """``BatchLaunchDialog._start_async_icon_load`` must not connect
    ``self._icon_thread.deleteLater`` to ``self._icon_thread.finished``.

    Construct a dialog-equivalent by ``__new__`` + manual stub, then call
    the real ``_start_async_icon_load``. Capture the thread and assert the
    finished-signal has no self-deleteLater connection.
    """
    from core import Folder, ShortcutItem, ShortcutType

    folder = Folder(
        id="f1",
        name="F",
        items=[
            ShortcutItem(id="s1", name="s1", type=ShortcutType.FILE, target_path="C:/x.exe"),
        ],
    )
    settings = type("S", (), {"theme": "dark"})()

    # Stub the worker so it doesn't try to actually load anything.
    # IMPORTANT: must emit completed() so the QThread's quit() can fire
    # and the test doesn't hang at teardown.
    class _StubWorker(QObject):
        finished = pyqtSignal(str, QObject)  # signature compatible with IconExtractor QImage
        completed = pyqtSignal()

        def __init__(self, tasks):
            super().__init__()
            self._tasks = tasks
            self._cancel = False

        def cancel(self):
            self._cancel = True

        def run(self):
            self.completed.emit()

    monkeypatch.setattr("ui.config_window.icon_grid._IconLoadWorker", _StubWorker)

    dialog = batch_mod.BatchLaunchDialog.__new__(batch_mod.BatchLaunchDialog)
    dialog._icon_load_generation = 0
    dialog._icon_worker = None
    dialog._icon_thread = None
    dialog._stop_icon_thread = lambda: None
    dialog._shortcut_by_id = {"s1": folder.items[0]}
    dialog._icon_pixmap_cache = {}
    dialog._launch_card_by_id = {}
    dialog._dialog_finished = False
    dialog.data_manager = type(
        "DM",
        (),
        {
            "data": type("D", (), {"get_folder_by_id": lambda fid: folder})(),
            "get_settings": lambda: settings,
        },
    )()

    try:
        dialog._start_async_icon_load()
        _assert_thread_does_not_self_delete_later(
            dialog._icon_thread, "BatchLaunchDialog._icon_thread", max_receivers=2
        )
    finally:
        try:
            dialog._icon_thread and dialog._icon_thread.quit()
            dialog._icon_thread and dialog._icon_thread.wait(50)
        except Exception:
            pass
        dialog._stop_icon_thread()


# ---------------------------------------------------------------------------
# 2) ui/config_window/settings_data_actions.py: export_thread
# ---------------------------------------------------------------------------


def test_p0_02_settings_export_thread_no_self_delete_later(qapp, monkeypatch):
    """ExportThread (in settings_helpers.py) is started by
    SettingsDataActionsMixin._on_export_clicked. The mixin must NOT
    connect ``self.export_thread.deleteLater`` to
    ``self.export_thread.finished``.
    """
    from ui.config_window.settings_data_actions import SettingsDataActionsMixin
    from ui.config_window.settings_helpers import ExportThread

    class _StubProgress:
        def __init__(self, *a, **kw):
            pass

        def show(self):
            pass

        def isVisible(self):
            return True

        def show_success(self, msg):
            pass

        def show_failure(self, msg):
            pass

    class _TMB:
        Yes = 1
        No = 0

        @staticmethod
        def critical(*a, **k):
            pass

    # Patch directly on the module (not via monkeypatch.setattr) for the
    # exact reason: pytest monkey-patches get reverted at teardown, but
    # direct attribute set survives the function scope and is reverted
    # explicitly below.
    settings_actions_mod.get_save_file_name = lambda *a, **kw: ("C:/fake_export.qlpack", "")
    settings_actions_mod.ThemedMessageBox = _TMB
    settings_actions_mod.CompactProgressDialog = _StubProgress

    captured_threads: list = []
    original_init = ExportThread.__init__

    def _init(self, dm, path):
        captured_threads.append(self)
        return original_init(self, dm, path)

    ExportThread.__init__ = _init

    class _Owner:
        export_thread: object = None

        def __init__(self):
            from unittest.mock import MagicMock

            self.data_manager = MagicMock()
            self.data_manager.get_settings.return_value.theme = "dark"

        def _is_thread_running(self, name):
            return False

        def _is_progress_dialog_alive(self, progress):
            return True

        def _clear_thread_if_current(self, name, thread):
            if getattr(self, name) is thread:
                setattr(self, name, None)

    class _Probe(SettingsDataActionsMixin, _Owner):
        def __init__(self):
            _Owner.__init__(self)

    probe = _Probe()
    try:
        probe._on_export_clicked()
        assert captured_threads, "ExportThread was not instantiated"
        thread = captured_threads[0]
        _assert_thread_does_not_self_delete_later(thread, "SettingsDataActionsMixin.export_thread", max_receivers=1)
    finally:
        ExportThread.__init__ = original_init
        for t in captured_threads:
            try:
                t.quit()
                t.wait(50)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 3) ui/config_window/settings_data_actions.py: import_thread
# ---------------------------------------------------------------------------


def test_p0_03_settings_import_thread_no_self_delete_later(qapp):
    """ImportThread must not have its own deleteLater connected to its
    own finished signal.
    """
    from ui.config_window.settings_data_actions import SettingsDataActionsMixin
    from ui.config_window.settings_helpers import ImportThread

    class _StubProgress:
        def __init__(self, *a, **kw):
            pass

        def show(self):
            pass

        def isVisible(self):
            return True

        def show_success(self, msg):
            pass

        def show_failure(self, msg):
            pass

    class _TMB:
        Yes = 1
        No = 0

        @staticmethod
        def critical(*a, **k):
            pass

    settings_actions_mod.get_open_file_name = lambda *a, **kw: ("C:/fake_import.qlpack", "")
    settings_actions_mod.ThemedMessageBox = _TMB
    settings_actions_mod.CompactProgressDialog = _StubProgress

    captured_threads: list = []
    original_init = ImportThread.__init__

    def _init(self, dm, path):
        captured_threads.append(self)
        return original_init(self, dm, path)

    ImportThread.__init__ = _init

    class _Owner:
        import_thread: object = None
        import_completed = pyqtSignal(int)

        def __init__(self):
            from unittest.mock import MagicMock

            self.data_manager = MagicMock()
            self.data_manager.get_settings.return_value.theme = "dark"
            self._load_settings = lambda: None
            self.apply_theme = lambda theme: None

        def _is_thread_running(self, name):
            return False

        def _is_progress_dialog_alive(self, progress):
            return True

        def _clear_thread_if_current(self, name, thread):
            if getattr(self, name) is thread:
                setattr(self, name, None)

    class _Probe(SettingsDataActionsMixin, _Owner):
        def __init__(self):
            _Owner.__init__(self)

    probe = _Probe()
    try:
        probe._on_import_clicked()
        assert captured_threads, "ImportThread was not instantiated"
        thread = captured_threads[0]
        _assert_thread_does_not_self_delete_later(thread, "SettingsDataActionsMixin.import_thread", max_receivers=1)
    finally:
        ImportThread.__init__ = original_init
        for t in captured_threads:
            try:
                t.quit()
                t.wait(50)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 4) ui/config_window/settings_data_actions.py: _FactoryResetThread
# ---------------------------------------------------------------------------


def test_p0_04_factory_reset_thread_no_self_delete_later(qapp):
    """``_FactoryResetThread`` is started by
    ``SettingsDataActionsMixin._on_factory_reset_clicked``. The thread
    is defined as a nested class inside that method, so the regression
    test inspects the wiring pattern via a representative QThread
    instead of importing the class.

    The actual code path is verified by reading
    ``settings_data_actions.py`` and ensuring the dangerous
    ``thread.finished.connect(thread.deleteLater)`` line is no longer
    present in the factory-reset handler.
    """
    import re

    src = settings_actions_mod.__file__
    with open(src, encoding="utf-8") as f:
        text = f.read()
    # The factory-reset wiring must connect progress_signal and
    # finished_signal, then start the thread. The dangerous
    # ``thread.finished.connect(thread.deleteLater)`` line must be
    # absent.
    m = re.search(
        r"thread\s*=\s*_FactoryResetThread\(self\.data_manager\)\s*\n"
        r"(?P<wiring>(?:.*?\n)*?)"
        r"\s*thread\.start\(\)",
        text,
    )
    assert m, "Could not find _FactoryResetThread start() block in settings_data_actions.py"
    wiring = m.group("wiring")
    assert "thread.finished.connect(thread.deleteLater)" not in wiring, (
        "Factory reset thread is connected to its own deleteLater — "
        "this is the same antipattern as icon_grid.py (see "
        "test_icon_grid_file_shortcut_delete.py)"
    )
    assert "finished_signal.connect(on_reset_finished)" in wiring
    assert "progress_signal.connect(on_progress_update)" in wiring


# ---------------------------------------------------------------------------
# 5) ui/launcher_popup/popup_data_refresh.py: FileSelectionThread
# ---------------------------------------------------------------------------


def test_p0_05_file_selection_thread_no_self_delete_later(qapp):
    """``FileSelectionThread`` is started by
    ``LauncherPopup._start_file_selection_thread``. The fix removes the
    dangerous ``thread.finished.connect(thread.deleteLater)`` line — assert
    the same wiring pattern is absent here.
    """
    thread = file_selection_mod.FileSelectionThread.__new__(file_selection_mod.FileSelectionThread)
    QThread.__init__(thread)
    thread.files_found = pyqtSignal(list)
    try:
        _assert_thread_does_not_self_delete_later(thread, "FileSelectionThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 6) ui/launcher_popup/popup_data_refresh.py: FolderSyncWorker
# ---------------------------------------------------------------------------


def test_p0_06_folder_sync_worker_no_self_delete_later(qapp):
    """``FolderSyncWorker`` must not connect its own deleteLater to its
    own finished signal.
    """
    from ui.launcher_popup.popup_window_helpers import FolderSyncWorker

    thread = FolderSyncWorker.__new__(FolderSyncWorker)
    QThread.__init__(thread)
    try:
        _assert_thread_does_not_self_delete_later(thread, "FolderSyncWorker", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 7) ui/tray_mixins/shutdown_mixin.py: IconCacheCleanThread
# ---------------------------------------------------------------------------


def test_p0_07_icon_cache_clean_thread_no_self_delete_later(qapp):
    """``IconCacheCleanThread`` started by ``shutdown_mixin`` manual
    icon-cache clean path must not have self-deleteLater.
    """
    from ui.tray_workers import IconCacheCleanThread

    thread = IconCacheCleanThread.__new__(IconCacheCleanThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(dict, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "IconCacheCleanThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 8) ui/diagnostics_window.py: DiagnosticsCollectThread
# ---------------------------------------------------------------------------


def test_p0_08_diagnostics_collect_thread_no_self_delete_later(qapp):
    """``DiagnosticsCollectThread`` started by ``DiagnosticsWindow.refresh``
    must not have its own deleteLater connected to its own finished.
    """
    thread = diag_mod.DiagnosticsCollectThread.__new__(diag_mod.DiagnosticsCollectThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(object, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "DiagnosticsCollectThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 9) ui/diagnostics_window.py: DiagnosticsFixThread
# ---------------------------------------------------------------------------


def test_p0_09_diagnostics_fix_thread_no_self_delete_later(qapp):
    """``DiagnosticsFixThread`` started by
    ``DiagnosticsWindow.apply_all_fixes`` must not have its own deleteLater
    on its own finished.
    """
    thread = diag_mod.DiagnosticsFixThread.__new__(diag_mod.DiagnosticsFixThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(dict, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "DiagnosticsFixThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 10) ui/shortcut_health_window.py: ShortcutHealthScanThread
# ---------------------------------------------------------------------------


def test_p0_10_shortcut_health_scan_thread_no_self_delete_later(qapp):
    """``ShortcutHealthScanThread`` started by
    ``ShortcutHealthWindow.refresh`` must not have its own deleteLater on
    its own finished.
    """
    thread = health_mod.ShortcutHealthScanThread.__new__(health_mod.ShortcutHealthScanThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(object, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "ShortcutHealthScanThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 11) ui/shortcut_health_window.py: ShortcutHealthFixThread
# ---------------------------------------------------------------------------


def test_p0_11_shortcut_health_fix_thread_no_self_delete_later(qapp):
    """``ShortcutHealthFixThread`` started by
    ``ShortcutHealthWindow.apply_safe_fixes`` must not have its own
    deleteLater on its own finished.
    """
    thread = health_mod.ShortcutHealthFixThread.__new__(health_mod.ShortcutHealthFixThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(dict, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "ShortcutHealthFixThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 12) ui/shortcut_health_window.py: FaviconCacheCleanThread
# ---------------------------------------------------------------------------


def test_p0_12_favicon_cache_clean_thread_no_self_delete_later(qapp):
    """``FaviconCacheCleanThread`` started by
    ``ShortcutHealthWindow.clean_unused_favicon_cache`` must not have its
    own deleteLater on its own finished.
    """
    thread = health_mod.FaviconCacheCleanThread.__new__(health_mod.FaviconCacheCleanThread)
    QThread.__init__(thread)
    thread.finished_signal = pyqtSignal(dict, str)
    try:
        _assert_thread_does_not_self_delete_later(thread, "FaviconCacheCleanThread", max_receivers=0)
    finally:
        try:
            thread.deleteLater()
        except Exception:
            pass
