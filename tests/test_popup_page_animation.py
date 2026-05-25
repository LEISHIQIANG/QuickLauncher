"""Launcher popup page animation regressions."""

from types import SimpleNamespace

import ui.launcher_popup.popup_window as popup_window_mod
from core.data_models import Folder, ShortcutItem
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

    monkeypatch.setattr(popup_window_mod, "QTimer", _Timer)

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
