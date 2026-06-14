import ctypes
import hashlib
import os
import time

import pytest

from hooks import hooks_wrapper
from hooks.key_map import KEY_TO_VK, MODIFIER_KEY_NAMES


class _FakeFunc:
    def __init__(self, result=None):
        self.result = result
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.result


class _FakeDLL:
    def __init__(self):
        for name in hooks_wrapper.HooksDLL.REQUIRED_EXPORTS:
            setattr(self, name, _FakeFunc(True))
        self.GetHooksVersion = _FakeFunc(hooks_wrapper.HooksDLL.EXPECTED_VERSION)
        self.GetHooksCapabilities = _FakeFunc(0xFF)
        self.GetLastHookError = _FakeFunc(0)
        self.IsMouseHookInstalled = _FakeFunc(True)
        self.IsKeyboardHookInstalled = _FakeFunc(False)
        self.IsRawInputFallbackActive = _FakeFunc(True)
        self.SetSpecialApps = _FakeFunc(None)
        self.ClearSpecialApps = _FakeFunc(None)


class _RuntimeStatsFunc(_FakeFunc):
    def __call__(self, stats_ptr, stats_size):
        stats = ctypes.cast(stats_ptr, ctypes.POINTER(hooks_wrapper.HooksRuntimeStats)).contents
        stats.size = stats_size
        stats.version = hooks_wrapper.HooksDLL.EXPECTED_VERSION
        stats.health_flags = 0xFF
        stats.callback_queue_depth = 2
        stats.low_level_mouse_events = 11
        stats.raw_mouse_events = 7
        stats.callback_queue_dropped = 3
        return True


def test_hooks_wrapper_reports_version_and_capabilities(monkeypatch):
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    dll = hooks_wrapper.HooksDLL("fake.dll")
    diagnostics = dll.get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is True
    assert diagnostics["version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION
    assert diagnostics["capabilities"] == 0xFF
    assert diagnostics["has_hook_health"] is True
    assert diagnostics["has_raw_input_status"] is True
    assert diagnostics["has_hotkey_capture"] is True
    assert diagnostics["mouse_hook_installed"] is True
    assert diagnostics["raw_input_fallback_active"] is True
    assert diagnostics["keyboard_hook_installed"] is False


def test_hooks_wrapper_binds_hotkey_capture_exports(monkeypatch):
    class _StartCaptureFunc(_FakeFunc):
        def __init__(self, owner):
            super().__init__(True)
            self.owner = owner

        def __call__(self, callback, timeout_ms):
            self.owner.start_calls.append((callback, timeout_ms))
            return True

    class _StopCaptureFunc(_FakeFunc):
        def __init__(self, owner):
            super().__init__(None)
            self.owner = owner

        def __call__(self):
            self.owner.stopped = True
            return None

    class CaptureDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            self.start_calls = []
            self.stopped = False
            self.active = True
            self.StartHotkeyCapture = _StartCaptureFunc(self)
            self.StopHotkeyCapture = _StopCaptureFunc(self)
            self.IsHotkeyCaptureActive = _FakeFunc(True)

    fake = CaptureDLL()
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)

    dll = hooks_wrapper.HooksDLL("capture.dll")

    assert dll.get_diagnostics()["has_hotkey_capture"] is True
    assert dll.start_hotkey_capture(lambda vk, mods, sides: None, timeout_ms=1234) is True
    assert fake.start_calls and fake.start_calls[-1][1] == 1234
    assert dll.is_hotkey_capture_active() is True

    dll.stop_hotkey_capture()
    assert fake.stopped is True


def test_hotkey_capture_owner_prevents_stale_recorder_stop(monkeypatch):
    fake = _FakeDLL()
    fake.StartHotkeyCapture = _FakeFunc(True)
    fake.StopHotkeyCapture = _FakeFunc(None)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("capture-owner.dll")
    first_owner = object()
    second_owner = object()

    assert dll.start_hotkey_capture(lambda *_args: None, owner=first_owner) is True
    first_ref = dll._hotkey_capture_callback_ref
    assert dll.start_hotkey_capture(lambda *_args: None, owner=second_owner) is False
    assert dll._hotkey_capture_callback_ref is first_ref
    assert dll.stop_hotkey_capture(owner=second_owner) is False
    assert dll.hotkey_capture_owned_by(first_owner) is True
    assert dll.stop_hotkey_capture(owner=first_owner) is True
    assert dll.hotkey_capture_owned_by(first_owner) is False


def test_protected_chord_capture_uses_flags_and_owner(monkeypatch):
    calls = []
    fake = _FakeDLL()
    fake.StartProtectedChordCapture = lambda callback, flags, timeout: calls.append((callback, flags, timeout)) or True
    fake.StopProtectedChordCapture = _FakeFunc(None)
    fake.IsProtectedChordCaptureActive = _FakeFunc(True)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("protected-chord.dll")
    owner = object()

    assert dll.start_protected_chord_capture(
        lambda *_args: None,
        keyboard=True,
        mouse_buttons=True,
        include_injected=True,
        timeout_ms=4321,
        owner=owner,
    )
    assert calls[-1][1:] == (
        hooks_wrapper.CHORD_CAPTURE_KEYBOARD
        | hooks_wrapper.CHORD_CAPTURE_MOUSE_BUTTON
        | hooks_wrapper.CHORD_CAPTURE_INCLUDE_INJECTED,
        4321,
    )
    assert dll.protected_chord_capture_owned_by(owner) is True
    assert dll.is_protected_chord_capture_active() is True
    assert dll.stop_protected_chord_capture(owner=owner) is True


def test_capture_owners_are_mutually_exclusive_across_capture_types(monkeypatch):
    input_start_calls = []
    fake = _FakeDLL()
    fake.StartHotkeyCapture = _FakeFunc(True)
    fake.IsHotkeyCaptureActive = _FakeFunc(True)
    fake.StartInputCapture = lambda callback, flags: input_start_calls.append((callback, flags)) or True
    fake.StopInputCapture = _FakeFunc(None)
    fake.IsInputCaptureActive = _FakeFunc(True)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("cross-capture-owner.dll")

    assert dll.start_hotkey_capture(lambda *_args: None, owner=object()) is True
    assert dll.start_input_capture(lambda _event: None, owner=object()) is False
    assert input_start_calls == []


def test_native_auto_completion_clears_stale_capture_owner(monkeypatch):
    hotkey_active = _FakeFunc(True)
    protected_calls = []
    fake = _FakeDLL()
    fake.StartHotkeyCapture = _FakeFunc(True)
    fake.IsHotkeyCaptureActive = hotkey_active
    fake.StartProtectedChordCapture = (
        lambda callback, flags, timeout: protected_calls.append((callback, flags, timeout)) or True
    )
    fake.IsProtectedChordCaptureActive = _FakeFunc(False)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("stale-capture-owner.dll")

    assert dll.start_hotkey_capture(lambda *_args: None, owner=object()) is True
    hotkey_active.result = False
    assert dll.start_protected_chord_capture(lambda *_args: None, owner=object()) is True
    assert protected_calls
    assert dll._hotkey_capture_owner is None


def test_hooks_wrapper_reports_runtime_stats(monkeypatch):
    fake = _FakeDLL()
    fake.GetHooksRuntimeStats = _RuntimeStatsFunc()
    fake.ResetHooksRuntimeStats = _FakeFunc(None)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)

    diagnostics = hooks_wrapper.HooksDLL("stats.dll").get_diagnostics()

    assert diagnostics["has_runtime_stats"] is True
    assert diagnostics["runtime_stats"]["version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION
    assert diagnostics["runtime_stats"]["callback_queue_depth"] == 2
    assert diagnostics["runtime_stats"]["low_level_mouse_events"] == 11
    assert diagnostics["runtime_stats"]["callback_queue_dropped"] == 3


def test_captured_events_to_macro_preserves_input_and_scales_timing():
    captured = [
        {
            "type": hooks_wrapper.INPUT_KEY_DOWN,
            "flags": hooks_wrapper.INPUT_FLAG_EXTENDED | hooks_wrapper.INPUT_FLAG_INJECTED,
            "timestamp_us": 1000,
            "vk_code": 0x41,
            "scan_code": 30,
        },
        {
            "type": hooks_wrapper.INPUT_KEY_UP,
            "flags": hooks_wrapper.INPUT_FLAG_EXTENDED,
            "timestamp_us": 5000,
            "vk_code": 0x41,
            "scan_code": 30,
        },
    ]

    macro = hooks_wrapper.HooksDLL.captured_events_to_macro(
        captured,
        speed=2.0,
        preserve_initial_delay=True,
    )

    assert [event["delay_us"] for event in macro] == [500, 2000]
    assert macro[0]["flags"] == hooks_wrapper.INPUT_FLAG_EXTENDED
    assert macro[0]["vk_code"] == 0x41
    assert macro[1]["scan_code"] == 30


def test_captured_events_to_macro_rejects_invalid_speed():
    with pytest.raises(ValueError):
        hooks_wrapper.HooksDLL.captured_events_to_macro([], speed=0)


def test_hooks_wrapper_tolerates_older_dll_without_health_exports(monkeypatch):
    class LegacyDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            del self.IsMouseHookInstalled
            del self.IsKeyboardHookInstalled
            del self.IsRawInputFallbackActive

    monkeypatch.setattr(ctypes, "CDLL", lambda path: LegacyDLL())

    diagnostics = hooks_wrapper.HooksDLL("legacy.dll").get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is True
    assert diagnostics["has_hook_health"] is False
    assert diagnostics["has_raw_input_status"] is False
    assert diagnostics["mouse_hook_installed"] is False
    assert diagnostics["raw_input_fallback_active"] is False
    assert diagnostics["keyboard_hook_installed"] is False


def test_hooks_wrapper_handles_load_failure(monkeypatch):
    def fail(path):
        raise OSError("missing")

    monkeypatch.setattr(ctypes, "CDLL", fail)

    dll = hooks_wrapper.HooksDLL("missing.dll")

    assert dll.install_mouse_hook(lambda x, y: None) is False
    assert dll.get_diagnostics()["loaded"] is False


def test_failed_hotkey_replacement_keeps_previous_callback_alive(monkeypatch):
    fake = _FakeDLL()
    fake.SetGlobalHotkey = _FakeFunc(False)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("hotkey.dll")
    previous_ref = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)
    dll._hotkey_callback_ref = previous_ref

    assert dll.set_hotkey("<ctrl>+a", lambda: None) is False
    assert dll._hotkey_callback_ref is previous_ref


def test_hooks_wrapper_reports_outdated_version(monkeypatch):
    class OutdatedDLL(_FakeDLL):
        def __init__(self):
            super().__init__()
            self.GetHooksVersion = _FakeFunc(hooks_wrapper.HooksDLL.EXPECTED_VERSION - 1)

    monkeypatch.setattr(ctypes, "CDLL", lambda path: OutdatedDLL())

    diagnostics = hooks_wrapper.HooksDLL("old.dll").get_diagnostics()

    assert diagnostics["loaded"] is True
    assert diagnostics["compatible"] is False
    assert diagnostics["expected_version"] == hooks_wrapper.HooksDLL.EXPECTED_VERSION


def test_hooks_wrapper_reports_file_metadata(monkeypatch, tmp_path):
    dll_path = tmp_path / "hooks.dll"
    content = b"fake dll"
    dll_path.write_bytes(content)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    diagnostics = hooks_wrapper.HooksDLL(
        str(dll_path),
        expected_sha256=hashlib.sha256(content).hexdigest(),
    ).get_diagnostics()

    assert diagnostics["exists"] is True
    assert diagnostics["size_bytes"] == len(content)
    assert diagnostics["sha256"] == hashlib.sha256(content).hexdigest()
    assert diagnostics["path_resolved"].endswith("hooks.dll")


def test_hooks_wrapper_rejects_custom_path_hash_mismatch(monkeypatch, tmp_path):
    dll_path = tmp_path / "hooks.dll"
    dll_path.write_bytes(b"unexpected")
    load_calls = []
    monkeypatch.setattr(ctypes, "CDLL", lambda path: load_calls.append(path) or _FakeDLL())

    dll = hooks_wrapper.HooksDLL(str(dll_path))

    assert dll.loaded is False
    assert "SHA-256 mismatch" in dll.load_error
    assert load_calls == []


def test_hooks_wrapper_can_explicitly_skip_custom_integrity_check(monkeypatch, tmp_path):
    dll_path = tmp_path / "hooks.dll"
    dll_path.write_bytes(b"development build")
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    dll = hooks_wrapper.HooksDLL(str(dll_path), verify_integrity=False)

    assert dll.loaded is True
    assert dll.compatible is True


def test_hooks_wrapper_exposes_repeatable_integrity_check(monkeypatch, tmp_path):
    dll_path = tmp_path / "hooks.dll"
    content = b"known native payload"
    dll_path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())

    dll = hooks_wrapper.HooksDLL(str(dll_path), expected_sha256=expected)

    assert dll.expected_sha256 == expected
    assert dll.verify_integrity() is True
    dll_path.write_bytes(b"tampered")
    assert dll.verify_integrity() is False


def test_shutdown_hooks_uses_correct_native_signatures():
    calls = []

    class StrictNoArg:
        def __init__(self, name):
            self.name = name

        def __call__(self):
            calls.append((self.name, ()))

    class StrictTimeout:
        def __call__(self, timeout_ms):
            calls.append(("WaitForMacroPlayback", (timeout_ms,)))
            return True

    fake = type("ShutdownDLL", (), {})()
    for name in (
        "StopInputCapture",
        "CancelMacroPlayback",
        "ReleaseMacroPressedInputs",
        "StopHotkeyCapture",
        "UninstallMouseHook",
        "UninstallKeyboardHook",
        "ClearGlobalHotkey",
    ):
        setattr(fake, name, StrictNoArg(name))
    fake.WaitForMacroPlayback = StrictTimeout()
    fake.AreHooksQuiescent = _FakeFunc(True)

    dll = hooks_wrapper.HooksDLL.__new__(hooks_wrapper.HooksDLL)
    dll.dll = fake
    dll.loaded = True
    dll.compatible = True
    dll._has_input_capture = True
    dll._lifecycle_lock = __import__("threading").RLock()
    dll._retired_callback_refs = __import__("collections").deque(maxlen=64)
    dll._input_capture_filter_flags = 0
    dll._input_capture_owner = None
    for attr_name in (
        "_mouse_callback_ref",
        "_alt_dclick_callback_ref",
        "_keyboard_callback_ref",
        "_hotkey_callback_ref",
        "_hotkey_capture_callback_ref",
        "_input_event_callback_ref",
    ):
        setattr(dll, attr_name, None)

    assert dll.shutdown_hooks() is True

    assert ("StopInputCapture", ()) in calls
    assert ("CancelMacroPlayback", ()) in calls
    assert ("WaitForMacroPlayback", (2000,)) in calls


def test_failed_hook_replacement_keeps_previous_callbacks_alive(monkeypatch):
    fake = _FakeDLL()
    fake.InstallMouseHook = _FakeFunc(False)
    fake.InstallKeyboardHook = _FakeFunc(False)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("replacement.dll")
    mouse_ref = hooks_wrapper.MOUSE_CALLBACK(lambda _x, _y: None)
    keyboard_ref = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)
    dll._mouse_callback_ref = mouse_ref
    dll._keyboard_callback_ref = keyboard_ref

    assert dll.install_mouse_hook(lambda _x, _y: None) is False
    assert dll.install_keyboard_hook(lambda: None) is False
    assert dll._mouse_callback_ref is mouse_ref
    assert dll._keyboard_callback_ref is keyboard_ref


def test_rearm_keyboard_hook_for_capture_reinstalls_existing_hook():
    calls = []
    existing_ref = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)

    class NativeDLL:
        def UninstallKeyboardHook(self):
            calls.append(("uninstall", None))

        def InstallKeyboardHook(self, callback):
            calls.append(("install", callback))
            return True

    dll = hooks_wrapper.HooksDLL.__new__(hooks_wrapper.HooksDLL)
    dll.dll = NativeDLL()
    dll.loaded = True
    dll.compatible = True
    dll._lifecycle_lock = __import__("threading").RLock()
    dll._keyboard_callback_ref = existing_ref

    success, installed_temporarily = dll.rearm_keyboard_hook_for_capture()

    assert success is True
    assert installed_temporarily is False
    assert calls == [("uninstall", None), ("install", existing_ref)]
    assert dll._keyboard_callback_ref is existing_ref


def test_rearm_keyboard_hook_for_capture_tracks_temporary_hook():
    calls = []

    class NativeDLL:
        def UninstallKeyboardHook(self):
            calls.append("uninstall")

        def InstallKeyboardHook(self, callback):
            calls.append(callback)
            return True

    dll = hooks_wrapper.HooksDLL.__new__(hooks_wrapper.HooksDLL)
    dll.dll = NativeDLL()
    dll.loaded = True
    dll.compatible = True
    dll._lifecycle_lock = __import__("threading").RLock()
    dll._keyboard_callback_ref = None

    success, installed_temporarily = dll.rearm_keyboard_hook_for_capture()

    assert success is True
    assert installed_temporarily is True
    assert calls[0] == "uninstall"
    assert dll._keyboard_callback_ref is calls[1]


def test_input_capture_owner_cannot_be_replaced_or_stopped(monkeypatch):
    fake = _FakeDLL()
    fake.StartInputCapture = _FakeFunc(True)
    fake.StopInputCapture = _FakeFunc(None)
    fake.IsInputCaptureActive = _FakeFunc(True)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    dll = hooks_wrapper.HooksDLL("capture-owner.dll")
    first_owner = object()
    second_owner = object()

    assert dll.start_input_capture(lambda _event: None, owner=first_owner) is True
    first_ref = dll._input_event_callback_ref
    assert dll.start_input_capture(lambda _event: None, owner=second_owner) is False
    assert dll._input_event_callback_ref is first_ref
    assert dll.stop_input_capture(owner=second_owner) is False
    assert dll._input_capture_owner is first_owner
    assert dll.stop_input_capture(owner=first_owner) is True
    assert dll._input_capture_owner is None


def test_shutdown_retains_dll_when_native_callbacks_are_not_quiescent(monkeypatch):
    fake = _FakeDLL()
    fake.AreHooksQuiescent = _FakeFunc(False)
    fake.WaitForMacroPlayback = _FakeFunc(True)
    dll = hooks_wrapper.HooksDLL.__new__(hooks_wrapper.HooksDLL)
    dll.dll = fake
    dll.loaded = True
    dll.compatible = True
    dll._has_input_capture = True
    dll._lifecycle_lock = __import__("threading").RLock()
    dll._retired_callback_refs = __import__("collections").deque(maxlen=64)
    dll._input_capture_filter_flags = 0
    dll._input_capture_owner = None
    callback_ref = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)
    for attr_name in (
        "_mouse_callback_ref",
        "_alt_dclick_callback_ref",
        "_keyboard_callback_ref",
        "_hotkey_callback_ref",
        "_hotkey_capture_callback_ref",
        "_input_event_callback_ref",
    ):
        setattr(dll, attr_name, callback_ref if attr_name == "_keyboard_callback_ref" else None)
    ticks = iter((0.0, 3.0))
    monkeypatch.setattr(hooks_wrapper.time, "monotonic", lambda: next(ticks))

    assert dll.shutdown_hooks() is False
    assert dll.dll is fake
    assert dll._keyboard_callback_ref is callback_ref


def test_retired_callback_refs_are_bounded(monkeypatch):
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeDLL())
    dll = hooks_wrapper.HooksDLL("bounded.dll")

    for _ in range(100):
        dll._retire_callback_ref(object())

    assert len(dll._retired_callback_refs) == 64


def test_hooks_wrapper_uses_shared_key_map():
    assert hooks_wrapper.HooksDLL._key_to_vk("VolumeUp") == 0xAF
    assert hooks_wrapper.HooksDLL._key_to_vk("PgDn") == 0x22


def test_dll_global_hotkey_parser_accepts_shared_key_map():
    dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hooks", "hooks.dll"))
    if not os.path.exists(dll_path):
        pytest.skip("hooks.dll is not available")

    dll = hooks_wrapper.HooksDLL(dll_path)
    if not dll.loaded or not dll.compatible:
        pytest.skip(f"hooks.dll unavailable: {dll.load_error or dll.missing_exports}")

    callback = hooks_wrapper.KEYBOARD_CALLBACK(lambda: None)
    rejected = [
        key
        for key in sorted(KEY_TO_VK)
        if key not in MODIFIER_KEY_NAMES and not dll.dll.SetGlobalHotkey(f"ctrl+{key}".encode(), callback)
    ]
    dll.dll.ClearGlobalHotkey()

    assert rejected == []


def test_dll_macro_capture_ignores_normal_filters_and_can_include_own_playback():
    dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hooks", "hooks.dll"))
    if not os.path.exists(dll_path):
        pytest.skip("hooks.dll is not available")

    dll = hooks_wrapper.HooksDLL(dll_path)
    if not dll.loaded or not dll.compatible or not dll.get_diagnostics()["has_input_capture"]:
        pytest.skip(f"macro capture unavailable: {dll.load_error or dll.missing_exports}")

    captured = []
    try:
        assert dll.install_keyboard_hook()
        assert dll.start_input_capture(
            captured.append,
            filter_flags=hooks_wrapper.CAPTURE_KEYBOARD,
            include_own_playback=True,
        )
        assert dll.play_macro(
            [
                {"type": hooks_wrapper.INPUT_KEY_DOWN, "vk_code": 0x87},
                {"type": hooks_wrapper.INPUT_KEY_UP, "vk_code": 0x87},
            ],
            no_timing=True,
        )
        assert dll.wait_for_macro_playback(2000)
        deadline = time.monotonic() + 1.0
        while len(captured) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        dll.stop_input_capture()
        dll.uninstall_keyboard_hook()

    if len(captured) == 0:
        pytest.skip("No keyboard events captured. This may be a headless or non-interactive environment.")

    f24_events = [event for event in captured if event["vk_code"] == 0x87]
    assert [event["type"] for event in f24_events] == [
        hooks_wrapper.INPUT_KEY_DOWN,
        hooks_wrapper.INPUT_KEY_UP,
    ]
    assert all(event["flags"] & hooks_wrapper.INPUT_FLAG_OWN_PLAYBACK for event in f24_events)
