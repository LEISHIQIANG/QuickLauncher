import ctypes

from core import ShortcutExecutor, shortcut_hotkey


class _FakeUser32:
    def __init__(self, held=()):
        self.held = set(held)

    def GetAsyncKeyState(self, vk):
        return 0x8000 if vk in self.held else 0

    def MapVirtualKeyW(self, vk, _mode):
        return vk & 0xFF


def test_sendinput_helper_sets_extended_flag_on_both_edges(monkeypatch):
    flags = []

    def send_input(_count, input_ptr, _size):
        event = ctypes.cast(input_ptr, ctypes.POINTER(shortcut_hotkey.INPUT)).contents
        flags.append(int(event.union.ki.dwFlags))
        return 1

    monkeypatch.setattr(shortcut_hotkey, "user32", _FakeUser32())
    monkeypatch.setattr(shortcut_hotkey, "SendInput", send_input)

    assert ShortcutExecutor._sendinput_key_event(0x2E, False) is True
    assert ShortcutExecutor._sendinput_key_event(0x2E, True) is True
    assert flags[0] & shortcut_hotkey.KEYEVENTF_EXTENDEDKEY
    assert flags[1] & shortcut_hotkey.KEYEVENTF_EXTENDEDKEY
    assert not flags[0] & shortcut_hotkey.KEYEVENTF_KEYUP
    assert flags[1] & shortcut_hotkey.KEYEVENTF_KEYUP


def test_hotkey_sendinput_uses_matching_extended_key_events(monkeypatch):
    calls = []
    monkeypatch.setattr(shortcut_hotkey, "user32", _FakeUser32())
    monkeypatch.setattr(shortcut_hotkey.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        ShortcutExecutor,
        "_sendinput_key_event",
        staticmethod(lambda vk, is_up: calls.append((vk, is_up)) or True),
    )

    assert ShortcutExecutor._execute_hotkey_sendinput(["ralt"], "delete") is True
    assert calls == [
        (0xA5, False),
        (0x2E, False),
        (0x2E, True),
        (0xA5, True),
    ]


def test_hotkey_sendinput_preserves_physically_held_modifier(monkeypatch):
    calls = []
    monkeypatch.setattr(shortcut_hotkey, "user32", _FakeUser32(held={0xA2}))
    monkeypatch.setattr(shortcut_hotkey.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        ShortcutExecutor,
        "_sendinput_key_event",
        staticmethod(lambda vk, is_up: calls.append((vk, is_up)) or True),
    )

    assert ShortcutExecutor._execute_hotkey_sendinput(["ctrl"], "p") is True
    assert calls == [(0x50, False), (0x50, True)]


def test_hotkey_sendinput_reports_failure_and_releases_only_injected_keys(monkeypatch):
    calls = []

    def send(vk, is_up):
        calls.append((vk, is_up))
        return not (vk == 0x2E and not is_up)

    monkeypatch.setattr(shortcut_hotkey, "user32", _FakeUser32())
    monkeypatch.setattr(shortcut_hotkey.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(ShortcutExecutor, "_sendinput_key_event", staticmethod(send))

    assert ShortcutExecutor._execute_hotkey_sendinput(["rctrl"], "delete") is False
    assert calls == [(0xA3, False), (0x2E, False), (0xA3, True)]
