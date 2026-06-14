"""Launcher popup page animation regressions."""

from types import SimpleNamespace

import pytest

import ui.launcher_popup.popup_search as popup_search_mod
import ui.launcher_popup.popup_window_effect as popup_effect_mod
from core.data_models import Folder, ShortcutItem
from qt_compat import QFont, QPixmap, QPoint, QRect, QWidget
from ui.launcher_popup.popup_window import LauncherPopup
from ui.launcher_popup.popup_window_helpers import IconFlashOverlay
from ui.utils.font_manager import get_font_family
from ui.utils.ui_scale import font_px

pytestmark = pytest.mark.ui


def _popup_for_animation():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.pages = [
        Folder(id="page-1", name="Page 1", items=[ShortcutItem(id="a", name="A")]),
        Folder(id="page-2", name="Page 2", items=[ShortcutItem(id="b", name="B")]),
        Folder(id="page-3", name="Page 3", items=[ShortcutItem(id="c", name="C")]),
    ]
    popup.current_page = 0
    popup._page_position = 0.0
    popup._target_page = 0.0
    popup._indicator_pos = 0.0
    popup._page_target_position = 1.0
    popup._last_wheel_time = 0.0
    popup._last_wheel_page_time = 0.0
    popup._last_wheel_direction = 0
    popup._wheel_accumulator = 0.0
    popup._page_icon_warm_queue = []
    popup._page_icon_warm_keys = set()
    popup._page_icon_warm_timer = None
    popup._page_render_cache = {}
    popup._preload_batch_timer = None
    popup._settings_updates = []
    popup.data_manager = SimpleNamespace(update_settings=lambda **kwargs: popup._settings_updates.append(kwargs))
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

    class _Timer:
        def __init__(self):
            self.active = False

        def isActive(self):
            return self.active

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

    popup._indicator_timer = _Timer()
    return popup


class _WheelPoint:
    def __init__(self, y=0):
        self._y = y

    def y(self):
        return self._y

    def isNull(self):
        return self._y == 0


class _WheelEvent:
    def __init__(self, angle_y=0, pixel_y=0):
        self._angle = _WheelPoint(angle_y)
        self._pixel = _WheelPoint(pixel_y)

    def angleDelta(self):
        return self._angle

    def pixelDelta(self):
        return self._pixel


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


def test_preload_animation_pages_only_queues_pixmaps_after_all_icons_are_ready(monkeypatch):
    popup = _popup_for_animation()
    popup._all_page_icons_preloaded = True

    class _Signal:
        def connect(self, callback):
            self.callback = callback

    class _Timer:
        def __init__(self, *args, **kwargs):
            self.timeout = _Signal()
            self.started = False

        def setInterval(self, interval):
            self.interval = interval

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    monkeypatch.setattr(popup_search_mod, "QTimer", _Timer)

    LauncherPopup._preload_animation_pages(popup)

    assert popup._preload_items_list == []
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


def test_page_animation_pixmaps_keep_static_vertical_origin():
    popup = _popup_for_animation()
    popup.__dict__["_label_font"] = QFont()
    popup.__dict__["_page_offset"] = 0.5
    popup._page_position = 0.5
    popup._body_y_offset = lambda: 46
    popup._get_page_animation_pixmap = lambda page_index, *_args: f"page-{page_index}"

    class _Painter:
        def __init__(self):
            self.clips = []
            self.pixmaps = []

        def setFont(self, _font):
            pass

        def save(self):
            pass

        def restore(self):
            pass

        def setClipRect(self, *args):
            self.clips.append(args)

        def drawPixmap(self, *args):
            self.pixmaps.append(args)

    painter = _Painter()
    LauncherPopup._draw_icons(popup, painter, None, None, None, "theme")

    assert [args[1] for args in painter.pixmaps] == [0, 0]
    assert [args[1] for args in painter.clips] == [46, 46]


def test_wheel_page_delta_clamps_large_angle_steps():
    popup = _popup_for_animation()

    assert LauncherPopup._normalized_page_wheel_delta(popup, _WheelEvent(angle_y=360)) == 1.0
    assert LauncherPopup._normalized_page_wheel_delta(popup, _WheelEvent(angle_y=-360)) == -1.0


def test_high_resolution_wheel_deltas_accumulate_before_page_step():
    popup = _popup_for_animation()
    event = _WheelEvent(angle_y=30)

    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=10.00) == 0
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=10.02) == 0
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=10.04) == 0
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=10.06) == -1


def test_wheel_page_steps_are_rate_limited_during_bursts():
    popup = _popup_for_animation()
    event = _WheelEvent(angle_y=120)

    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=20.00) == -1
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=20.03) == 0
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=20.06) == 0
    assert LauncherPopup._consume_wheel_page_direction(popup, event, now=20.12) == -1


def test_page_switch_uses_continuous_targets_when_wrapping():
    popup = _popup_for_animation()
    popup.current_page = 2
    popup._page_position = 2.0
    popup._target_page = 2.0

    LauncherPopup._queue_page_switch(popup, 1)

    assert popup.current_page == 0
    assert popup._target_page == 3.0
    assert popup._indicator_timer.isActive()
    assert popup._pending_last_page_index == 0
    assert popup._settings_updates == []

    LauncherPopup._persist_last_page_index(popup)

    assert popup._settings_updates[-1] == {"last_page_index": 0, "immediate": False}


def test_page_animation_finish_normalizes_continuous_position():
    popup = _popup_for_animation()
    popup.current_page = 0
    popup._page_position = 3.0
    popup._page_offset = 3.0
    popup._target_page = 3.0
    popup._indicator_pos = 3.0

    LauncherPopup._finish_page_animation(popup)

    assert popup._page_position == 0.0
    assert popup._page_offset == 0.0
    assert popup._target_page == 0.0
    assert popup._indicator_pos == 0.0


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


def test_popup_visibility_animation_ignores_stale_finish_callbacks():
    popup = LauncherPopup.__new__(LauncherPopup)
    popup._visibility_animation_generation = 2
    popup._is_hiding = True
    popup._reveal_progress = 0.4
    opacity = []
    updates = []
    popup.setWindowOpacity = lambda value: opacity.append(value)
    popup.update = lambda: updates.append(True)

    LauncherPopup._finish_show_animation(popup, generation=1)
    LauncherPopup._on_hide_finished(popup, generation=1)

    assert popup._is_hiding is True
    assert popup._reveal_progress == 0.4
    assert opacity == []
    assert updates == []


def test_popup_effect_snapshot_separates_native_windows(monkeypatch):
    class _Screen:
        def name(self):
            return "screen-a"

        def devicePixelRatio(self):
            return 1.25

        def geometry(self):
            return QRect(0, 0, 1600, 900)

        def availableGeometry(self):
            return QRect(0, 0, 1600, 860)

    monkeypatch.setattr(popup_effect_mod, "QApplication", SimpleNamespace(screenAt=lambda _pos: _Screen()))
    monkeypatch.setattr(popup_effect_mod, "is_win10", lambda: False)
    monkeypatch.setattr(popup_effect_mod, "is_win11", lambda: True)

    def make_popup(hwnd: int):
        popup = LauncherPopup.__new__(LauncherPopup)
        popup.settings = SimpleNamespace(theme="dark", bg_mode="theme", corner_radius=8, bg_alpha=90, bg_blur_radius=0)
        popup.width = lambda: 240
        popup.height = lambda: 180
        popup.winId = lambda: hwnd
        popup.frameGeometry = lambda: QRect(20, 30, 240, 180)
        popup.pos = lambda: QPoint(20, 30)
        return popup

    first = LauncherPopup._snapshot_effect_state(make_popup(101))
    second = LauncherPopup._snapshot_effect_state(make_popup(202))

    assert first != second
    assert first[0] == 101
    assert second[0] == 202


def test_icon_flash_overlay_uses_short_dirty_pulse(qapp):
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

    overlay.start()

    assert overlay._duration_ms <= 100
    assert overlay._animation.duration() == overlay._duration_ms
    assert overlay._opacity == overlay._peak_opacity
    assert not overlay._dirty_rect.isNull()
    assert overlay._dirty_rect.width() < overlay.width()

    overlay._set_flash_opacity(0.12)
    assert overlay._opacity == 0.12

    overlay.stop()
    assert overlay._opacity == 0.0
    assert overlay._items == []
    launcher.deleteLater()


def test_popup_label_replaces_sixth_character_with_ellipsis():
    assert LauncherPopup._elided_label("启动器标签") == "启动器标签"
    assert LauncherPopup._elided_label("启动器标签显") == "启动器标签显"
    assert LauncherPopup._elided_label("启动器标签显示") == "启动器标签…"


def test_popup_grid_metrics_keep_smaller_font_and_single_line_height(qapp):
    popup = LauncherPopup.__new__(LauncherPopup)
    popup.settings = SimpleNamespace(icon_size=32)
    popup._label_font = QFont()
    popup.icon_size = 32
    popup.cell_size = 48

    LauncherPopup._update_grid_text_metrics(popup)

    assert popup._label_font.pixelSize() == font_px(9)
    assert popup._label_font.family() == get_font_family()
    assert popup._label_font.weight() == QFont.Weight.Medium
    assert popup._label_font.hintingPreference() == QFont.HintingPreference.PreferFullHinting
    assert popup._label_font.styleStrategy() & QFont.StyleStrategy.PreferAntialias
    assert popup.cell_h == int(popup.cell_size * 1.15)
