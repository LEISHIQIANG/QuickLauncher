import pytest

from ui.config_window.hotkey_capture_helpers import (
    CAPTURE_MOD_ALT,
    CAPTURE_MOD_CTRL,
    CAPTURE_MOD_WIN,
    SIDE_MODIFIER_BITS,
    KeyboardStatePoller,
)


@pytest.mark.parametrize(
    ("pressed", "expected_modifiers", "expected_side_modifiers"),
    [
        ({0x11, 0xA2, 0x51}, CAPTURE_MOD_CTRL, SIDE_MODIFIER_BITS["lctrl"]),
        ({0x12, 0xA4, 0x51}, CAPTURE_MOD_ALT, SIDE_MODIFIER_BITS["lalt"]),
        ({0x5B, 0x51}, CAPTURE_MOD_WIN, SIDE_MODIFIER_BITS["lwin"]),
    ],
)
def test_keyboard_state_poller_captures_modifier_q_and_completes_after_full_release(
    qapp,
    monkeypatch,
    pressed,
    expected_modifiers,
    expected_side_modifiers,
):
    events = []
    poller = KeyboardStatePoller(qapp, lambda *args: events.append(args), log_label="test")
    states = iter(
        [
            set(),
            pressed,
            pressed - {0x51},
            set(),
        ]
    )
    monkeypatch.setattr(poller, "_pressed_vks", lambda: next(states))

    poller.start()
    poller._poll()
    poller._poll()

    assert events == [(0x51, expected_modifiers, expected_side_modifiers)]
    assert poller.is_active() is True

    poller._poll()

    assert events == [
        (0x51, expected_modifiers, expected_side_modifiers),
        (0, expected_modifiers, expected_side_modifiers),
    ]
    assert poller.is_active() is False


def test_keyboard_state_poller_ignores_keys_held_before_recording(qapp, monkeypatch):
    events = []
    poller = KeyboardStatePoller(qapp, lambda *args: events.append(args), log_label="test")
    states = iter(
        [
            {0x11, 0xA2},
            {0x11, 0xA2, 0x51},
            set(),
        ]
    )
    monkeypatch.setattr(poller, "_pressed_vks", lambda: next(states))

    poller.start()
    poller._poll()
    poller._poll()

    assert events == [(0x51, 0, 0), (0, 0, 0)]

    states = iter(
        [
            set(),
            {0x11, 0xA2, 0x51},
            set(),
        ]
    )
    poller.start()
    poller._poll()
    poller._poll()

    assert events[-2:] == [
        (0x51, CAPTURE_MOD_CTRL, SIDE_MODIFIER_BITS["lctrl"]),
        (0, CAPTURE_MOD_CTRL, SIDE_MODIFIER_BITS["lctrl"]),
    ]


def test_keyboard_state_poller_captures_alt_space(qapp, monkeypatch):
    events = []
    poller = KeyboardStatePoller(qapp, lambda *args: events.append(args), log_label="test")
    states = iter(
        [
            set(),
            {0x12, 0xA4},
            {0x12, 0xA4, 0x20},
            set(),
        ]
    )
    monkeypatch.setattr(poller, "_pressed_vks", lambda: next(states))

    poller.start()
    poller._poll()
    poller._poll()
    poller._poll()

    assert events == [
        (0x20, CAPTURE_MOD_ALT, SIDE_MODIFIER_BITS["lalt"]),
        (0, CAPTURE_MOD_ALT, SIDE_MODIFIER_BITS["lalt"]),
    ]
