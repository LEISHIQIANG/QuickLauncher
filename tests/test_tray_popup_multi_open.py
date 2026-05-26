from types import SimpleNamespace

from ui.tray_app import TrayApp


class FakePopup:
    def __init__(self, pinned=True, visible=True):
        self.is_pinned = pinned
        self._visible = visible
        self.closed = False

    def isVisible(self):
        return self._visible

    def width(self):
        if self.closed:
            raise RuntimeError("deleted")
        return 100

    def close(self):
        self.closed = True
        self._visible = False

    def hide(self):
        self._visible = False


def _tray_like(multi_open=True):
    tray = TrayApp.__new__(TrayApp)
    tray._extra_popup_windows = []
    tray._max_extra_popup_windows = 2
    tray.data_manager = SimpleNamespace(get_settings=lambda: SimpleNamespace(popup_multi_open_when_pinned=multi_open))
    tray.popup_window = None
    tray.config_window = None
    tray.log_window = None
    return tray


def test_should_multi_open_only_for_visible_pinned_popup():
    tray = _tray_like(multi_open=True)

    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=True)) is True
    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=False, visible=True)) is False
    assert tray._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=False)) is False

    tray_disabled = _tray_like(multi_open=False)
    assert tray_disabled._should_multi_open_pinned_popup(FakePopup(pinned=True, visible=True)) is False


def test_extra_popup_pool_keeps_at_most_two_old_windows():
    tray = _tray_like(multi_open=True)
    first = FakePopup()
    second = FakePopup()
    third = FakePopup()

    tray._keep_as_extra_popup(first)
    tray._keep_as_extra_popup(second)
    tray._keep_as_extra_popup(third)

    assert first.closed is True
    assert second.closed is False
    assert third.closed is False
    assert tray._extra_popup_windows == [second, third]


def test_extra_popup_pool_ignores_duplicates():
    tray = _tray_like(multi_open=True)
    popup = FakePopup()

    tray._keep_as_extra_popup(popup)
    tray._keep_as_extra_popup(popup)

    assert tray._extra_popup_windows == [popup]


def test_prune_extra_popup_windows_handles_closed_popups():
    tray = _tray_like(multi_open=True)
    first = FakePopup()
    second = FakePopup()
    first.close()
    tray._extra_popup_windows = [first, second]

    tray._prune_extra_popup_windows()

    assert tray._extra_popup_windows == [second]
