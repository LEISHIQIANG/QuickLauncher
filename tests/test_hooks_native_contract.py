from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "hooks_dll" / "hooks.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "hooks_dll" / "hooks.h").read_text(encoding="utf-8")


def test_native_abi_exposes_quiescent_state_and_version_10():
    assert "constexpr int HOOKS_VERSION = 10;" in SOURCE
    assert "HOOKS_API bool AreHooksQuiescent();" in HEADER
    assert "HOOKS_API bool AreHooksQuiescent()" in SOURCE


def test_native_input_capture_rejects_active_replacement():
    active_guard = SOURCE.index("if (g_inputCaptureActive.load())", SOURCE.index("HOOKS_API bool StartInputCapture"))
    busy_error = SOURCE.index("g_lastHookError = ERROR_BUSY;", active_guard)
    return_false = SOURCE.index("return false;", busy_error)
    assert active_guard < busy_error < return_false


def test_keyboard_popup_trigger_blocks_matching_down_and_up():
    assert "static bool HandleKeyboardPopupTrigger" in SOURCE
    assert "if (isUp && g_triggerBlockedKeys[vk])" in SOURCE
    assert "g_triggerBlockedKeys[vk] = true;" in SOURCE
    assert "if (HandleKeyboardPopupTrigger(vk, isDown, isUp, wasPressed))" in SOURCE


def test_hotkey_capture_preserves_preexisting_physical_keys():
    assert "g_hotkeyCapturePreexisting[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;" in SOURCE
    assert "if (g_hotkeyCapturePreexisting[normalizedVk])" in SOURCE
