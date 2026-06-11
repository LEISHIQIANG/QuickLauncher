from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.data_models import ShortcutItem, ShortcutType
from ui.launcher_popup.popup_data_refresh import PopupDataRefreshMixin
from ui.launcher_popup.popup_icons import PopupIconMixin

pytestmark = pytest.mark.ui


class _IconHarness(PopupIconMixin):
    def __init__(self):
        self.icon_size = 24
        self.settings = SimpleNamespace(theme="dark")
        self._icon_pixmap_cache = OrderedDict()
        self._default_icon_cache = {}
        self._page_pixmap_cache = {}
        self.created_for = []
        self.updated = 0

    def _create_default_icon(self, item):
        self.created_for.append(item.name)
        return f"default:{item.name}"

    def update(self):
        self.updated += 1


class _VisibleIconPreloadHarness(PopupDataRefreshMixin):
    def __init__(self, visible=False):
        self._visible = visible
        self._visible_icons_preloaded = False
        self._all_page_icons_preloaded = False
        self.cols = 2
        self.fixed_rows = 1
        self.settings = SimpleNamespace(popup_max_rows=1, dock_height_mode=1)
        shared = ShortcutItem(id="shared", name="Shared", type=ShortcutType.COMMAND)
        page_item = ShortcutItem(id="page", name="Page", type=ShortcutType.COMMAND)
        dock_item = ShortcutItem(id="dock", name="Dock", type=ShortcutType.COMMAND)
        second_page_item = ShortcutItem(id="second", name="Second", type=ShortcutType.COMMAND)
        self.pages = [
            SimpleNamespace(items=[shared, page_item]),
            SimpleNamespace(items=[second_page_item]),
        ]
        self.current_page = 0
        self.dock_items = [shared, dock_item]
        self.loaded = []
        self.reserved = []

    def isVisible(self):
        return self._visible

    def _get_icon(self, item):
        self.loaded.append(item.id)

    def _reserve_icon_pixmap_cache(self, item_count):
        self.reserved.append(item_count)


def test_preload_visible_icons_can_warm_hidden_popup_before_show(monkeypatch):
    import ui.launcher_popup.popup_data_refresh as refresh_mod

    monkeypatch.setattr(refresh_mod, "HAS_ICON_EXTRACTOR", True)
    monkeypatch.setattr(refresh_mod, "IconExtractor", object())
    harness = _VisibleIconPreloadHarness(visible=False)

    harness.preload_visible_icons(force=True)

    assert harness.loaded == ["shared", "page", "dock"]
    assert harness._visible_icons_preloaded is True


def test_preload_all_page_icons_warms_each_page_before_show(monkeypatch):
    import ui.launcher_popup.popup_data_refresh as refresh_mod

    monkeypatch.setattr(refresh_mod, "HAS_ICON_EXTRACTOR", True)
    monkeypatch.setattr(refresh_mod, "IconExtractor", object())
    harness = _VisibleIconPreloadHarness(visible=False)

    harness.preload_visible_icons(force=True, all_pages=True)

    assert harness.loaded == ["shared", "page", "second", "dock"]
    assert harness.reserved == [4]
    assert harness._visible_icons_preloaded is True
    assert harness._all_page_icons_preloaded is True


def test_preload_visible_icons_skips_hidden_popup_without_force(monkeypatch):
    import ui.launcher_popup.popup_data_refresh as refresh_mod

    monkeypatch.setattr(refresh_mod, "HAS_ICON_EXTRACTOR", True)
    monkeypatch.setattr(refresh_mod, "IconExtractor", object())
    harness = _VisibleIconPreloadHarness(visible=False)

    harness.preload_visible_icons()

    assert harness.loaded == []
    assert harness._visible_icons_preloaded is False


def test_popup_default_icon_cache_tracks_shortcut_name_initial():
    harness = _IconHarness()
    shortcut = ShortcutItem(id="one", name="Alpha", type=ShortcutType.COMMAND)

    assert harness._get_icon(shortcut) == "default:Alpha"

    shortcut.name = "Beta"

    assert harness._get_icon(shortcut) == "default:Beta"
    assert harness.created_for == ["Alpha", "Beta"]


def test_popup_default_icon_cache_reuses_same_initial():
    harness = _IconHarness()
    shortcut = ShortcutItem(id="one", name="Alpha", type=ShortcutType.COMMAND)

    harness._get_icon(shortcut)
    shortcut.name = "Atom"

    assert harness._get_icon(shortcut) == "default:Alpha"
    assert harness.created_for == ["Alpha"]


def test_popup_icon_for_paint_uses_cache_only(monkeypatch):
    import ui.launcher_popup.popup_icons as icons_mod

    calls = []

    class _IconExtractor:
        @staticmethod
        def from_file(*args, **kwargs):
            calls.append(("from_file", args, kwargs))
            raise AssertionError("paint path must not load icon files")

        @staticmethod
        def extract(*args, **kwargs):
            calls.append(("extract", args, kwargs))
            raise AssertionError("paint path must not extract shell icons")

    monkeypatch.setattr(icons_mod, "HAS_ICON_EXTRACTOR", True)
    monkeypatch.setattr(icons_mod, "IconExtractor", _IconExtractor)

    harness = _IconHarness()
    shortcut = ShortcutItem(
        id="one",
        name="Alpha",
        type=ShortcutType.FILE,
        icon_path="C:/missing.ico",
        target_path="C:/missing.exe",
    )

    assert harness._get_icon_for_paint(shortcut) == "default:Alpha"
    assert calls == []

    harness._icon_pixmap_cache[("target_path", "C:/missing.exe", 24, 48, False)] = "cached-target"
    assert harness._get_icon_for_paint(shortcut) == "cached-target"


def test_popup_icon_for_paint_loads_folder_default(monkeypatch, tmp_path, qapp):
    import ui.launcher_popup.popup_icons as icons_mod
    from qt_compat import QColor, QImage

    icon_path = tmp_path / "folder.png"
    image = QImage(8, 8, QImage.Format_ARGB32)
    image.fill(QColor(70, 130, 180))
    assert image.save(str(icon_path))

    monkeypatch.setattr(icons_mod, "default_folder_icon_path", lambda: str(icon_path))

    harness = _IconHarness()
    shortcut = ShortcutItem(id="folder", name="Docs", type=ShortcutType.FOLDER, target_path=str(tmp_path))

    pixmap = harness._get_icon_for_paint(shortcut)

    assert pixmap and not pixmap.isNull()
    assert harness.created_for == []
    assert ("from_file", str(icon_path), 24, 48, False) in harness._icon_pixmap_cache


def test_popup_icon_cache_change_requests_repaint():
    harness = _IconHarness()
    harness._page_pixmap_cache["page"] = "pixmap"

    harness._mark_icon_cache_changed()

    assert harness._page_pixmap_cache == {}
    assert harness.updated == 1


def test_popup_icon_cache_reservation_prevents_preloaded_pages_from_eviction():
    harness = _IconHarness()
    harness._reserve_icon_pixmap_cache(160)

    for index in range(320):
        harness._icon_pixmap_cache[f"key-{index}"] = index
        harness._trim_icon_pixmap_cache()

    assert harness._icon_pixmap_cache_capacity() == 352
    assert len(harness._icon_pixmap_cache) == 320
    assert "key-0" in harness._icon_pixmap_cache


def test_popup_icon_batch_preload_defers_repaint_until_commit():
    harness = _IconHarness()
    harness._batch_icon_preload_active = True

    harness._mark_icon_cache_changed()

    assert harness.updated == 0
    assert harness._icon_cache_batch_changed is True


def test_popup_entry_points_preload_all_pages_before_show():
    project_root = Path(__file__).resolve().parents[1]
    popup_mixin = (project_root / "ui" / "tray_mixins" / "popup_mixin.py").read_text(encoding="utf-8")
    startup_mixin = (project_root / "ui" / "tray_mixins" / "startup_mixin.py").read_text(encoding="utf-8")

    assert popup_mixin.count("preload_visible_icons(force=True, all_pages=True)") == 2
    assert "preload_visible_icons(force=True, all_pages=False)" not in popup_mixin
    assert "preload_visible_icons(force=True, all_pages=True)" in startup_mixin
