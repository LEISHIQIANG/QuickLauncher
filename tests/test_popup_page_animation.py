"""Launcher popup page animation regressions."""

from types import SimpleNamespace

import ui.launcher_popup.popup_search as popup_search_mod
import ui.launcher_popup.popup_window_helpers as popup_helpers_mod
from core.data_models import Folder, ShortcutItem
from qt_compat import QFont, QPixmap, QWidget
from ui.launcher_popup.popup_window_helpers import IconFlashOverlay
from ui.launcher_popup.popup_window import LauncherPopup


def _popup_for_animation():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.pages = [
        Folder(id="page-1", name="Page 1", items=[ShortcutItem(id="a", name="A")]),
        Folder(id="page-2", name="Page 2", items=[ShortcutItem(id="b", name="B")]),
        Folder(id="page-3", name="Page 3", items=[ShortcutItem(id="c", name="C")]),
    ]
    popup.current_page = 0
    popup._page_position = 0.0
    popup._page_target_position = 1.0
    popup._page_icon_warm_queue = []
    popup._page_icon_warm_keys = set()
    popup._page_icon_warm_timer = None
    popup._page_render_cache = {}
    popup._preload_batch_timer = None
    popup.settings = SimpleNamespace(theme="dark", sort_mode="custom")
    popup._model_revision = 1
    popup.cols = 1
    popup.fixed_rows = 8
    popup.icon_size = 32
    popup.cell_size = 44
    popup.content_height = 120
    popup.indicator_y = 128
    popup.dock_y = 170
    popup.width = lambda: 240
    popup.height = lambda: 220
    popup._get_display_items = lambda page: page.items
    return popup


def test_preload_animation_pages_queues_incremental_work(monkeypatch):
    popup = _popup_for_animation()

    class _Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

    class _Timer:
        def __init__(self, *args, **kwargs):
            self.timeout = _Signal()
            self.started = False
            self.interval = None

        def setInterval(self, interval):
            self.interval = interval

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    monkeypatch.setattr(popup_search_mod, "QTimer", _Timer)

    LauncherPopup._preload_animation_pages(popup)

    assert [item.id for item in popup._preload_items_list] == ["a", "b", "c"]
    assert popup._preload_page_queue == [0, 1, 2]
    assert popup._preload_batch_timer.started


def test_page_animation_update_area_stays_above_dock():
    popup = _popup_for_animation()
    updates = []
    popup.update = lambda rect=None: updates.append(rect)

    LauncherPopup._request_page_animation_update(popup)

    assert updates
    assert updates[0].top() == 0
    assert updates[0].bottom() < popup.dock_y


def test_page_animation_pixmap_not_cached_until_icons_are_ready():
    popup = _popup_for_animation()
    popup._page_pixmap_cache = {}
    popup._animation_icon_ready = lambda item: False

    pixmap = LauncherPopup._get_page_animation_pixmap(
        popup,
        0,
        None,
        None,
        None,
        "theme",
    )

    assert pixmap is None
    assert popup._page_pixmap_cache == {}


def test_page_animation_icon_readiness_checks_dict_entries():
    popup = _popup_for_animation()
    item = ShortcutItem(id="dict-item", name="Dict")
    checked = []
    popup._animation_icon_ready = lambda value: checked.append(value) or True

    assert LauncherPopup._page_animation_icons_ready(popup, [{"item": item}])
    assert checked == [item]


def test_popup_lifecycle_generation_drops_stale_callbacks():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup._lifecycle_generation = 1
    popup._closing = False
    calls = []

    assert LauncherPopup._run_if_lifecycle_current(popup, 1, calls.append, "current") is True
    assert calls == ["current"]

    LauncherPopup._next_lifecycle_generation(popup)
    assert LauncherPopup._run_if_lifecycle_current(popup, 1, calls.append, "stale") is False
    assert calls == ["current"]

    popup._closing = True
    assert LauncherPopup._run_if_lifecycle_current(popup, 2, calls.append, "closed") is False
    assert calls == ["current"]


def test_popup_stop_lifecycle_timers_stops_known_timers():
    popup = LauncherPopup.__new__(LauncherPopup)

    class _Timer:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    timers = {
        "_auto_close_timer": _Timer(),
        "_indicator_timer": _Timer(),
        "_search_cursor_timer": _Timer(),
        "_search_anim_timer": _Timer(),
        "_preload_batch_timer": _Timer(),
        "_bg_load_timer": _Timer(),
    }
    popup.__dict__.update(timers)

    LauncherPopup._stop_lifecycle_timers(popup)

    assert all(timer.stopped for timer in timers.values())


def test_icon_flash_overlay_uses_short_dirty_pulse(qapp, monkeypatch):
    item = ShortcutItem(id="refresh", name="Refresh")
    pixmap = QPixmap(24, 24)
    pixmap.fill()

    class _Launcher(QWidget):
        def __init__(self):
            super().__init__()
            self.resize(180, 140)
            self.pages = [Folder(id="page", name="Page", items=[item])]
            self.current_page = 0
            self.cols = 1
            self.fixed_rows = 1
            self.icon_size = 24
            self.cell_size = 44
            self.cell_h = 42
            self.padding = 8
            self.dock_items = []
            self.dock_height = 0
            self.settings = SimpleNamespace(bg_mode="theme", theme="dark", dock_height_mode=1)
            self._label_font = QFont()
            self._default_icon_cache = {}

        def _get_cached_icon_for_animation(self, _item, _need_invert=False):
            return pixmap

        def _default_icon_cache_key(self, shortcut):
            return shortcut.id

    launcher = _Launcher()
    overlay = IconFlashOverlay(launcher)

    monkeypatch.setattr(popup_helpers_mod.time, "perf_counter", lambda: 10.0)
    overlay.start()

    assert overlay._duration_ms <= 120
    assert overlay._timer.interval() == 8
    assert not overlay._dirty_rect.isNull()
    assert overlay._dirty_rect.width() < overlay.width()

    monkeypatch.setattr(popup_helpers_mod.time, "perf_counter", lambda: 10.009)
    overlay._tick()
    attack_opacity = overlay._opacity
    assert 0.0 < attack_opacity < overlay._peak_opacity

    monkeypatch.setattr(popup_helpers_mod.time, "perf_counter", lambda: 10.08)
    overlay._tick()
    assert 0.0 < overlay._opacity < overlay._peak_opacity

    overlay.stop()
    launcher.deleteLater()
