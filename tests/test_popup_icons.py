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
        self.created_for = []

    def _create_default_icon(self, item):
        self.created_for.append(item.name)
        return f"default:{item.name}"


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
