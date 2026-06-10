from collections import OrderedDict
from types import SimpleNamespace

import pytest

from core.data_models import ShortcutItem, ShortcutType
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


def test_popup_icon_cache_change_requests_repaint():
    harness = _IconHarness()
    harness._page_pixmap_cache["page"] = "pixmap"

    harness._mark_icon_cache_changed()

    assert harness._page_pixmap_cache == {}
    assert harness.updated == 1
