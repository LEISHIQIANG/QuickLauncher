from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "hooks_dll" / "hooks.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "hooks_dll" / "hooks.h").read_text(encoding="utf-8")


def test_native_abi_exposes_quiescent_state_and_version_15():
    assert "constexpr int HOOKS_VERSION = 15;" in SOURCE
    assert "HOOKS_API bool AreHooksQuiescent();" in HEADER
    assert "HOOKS_API bool AreHooksQuiescent()" in SOURCE


def test_native_input_capture_rejects_active_replacement():
    start = SOURCE.index("HOOKS_API bool StartInputCapture")
    end = SOURCE.index("HOOKS_API void StopInputCapture", start)
    body = SOURCE[start:end]

    assert "TryClaimCaptureMode(CAPTURE_MODE_INPUT)" in body
    assert "ReleaseCaptureMode(CAPTURE_MODE_INPUT)" in body


def test_capture_modes_use_one_atomic_native_owner():
    assert "static std::atomic<int> g_activeCaptureMode(CAPTURE_MODE_NONE);" in SOURCE
    assert "TryClaimCaptureMode(CAPTURE_MODE_HOTKEY)" in SOURCE
    assert "TryClaimCaptureMode(CAPTURE_MODE_PROTECTED_CHORD)" in SOURCE
    assert "TryClaimCaptureMode(CAPTURE_MODE_INPUT)" in SOURCE
    assert "g_activeCaptureMode.load() == CAPTURE_MODE_NONE" in SOURCE


def test_reinstalling_live_hook_updates_callback_without_waiting_for_exit():
    installer = SOURCE[
        SOURCE.index("static bool InstallHookGeneric") : SOURCE.index("static bool UninstallHookGeneric")
    ]
    live_guard = installer.index("if (ctx.running.load() && ctx.threadAlive.load())")
    callback_update = installer.index("if (mouseCb) g_mouseCallback = mouseCb;", live_guard)
    wait_for_exit = installer.index("WaitForHookThreadExit", live_guard)

    assert live_guard < callback_update < wait_for_exit


def test_keyboard_popup_trigger_blocks_matching_down_and_up():
    assert "static bool HandleKeyboardPopupTrigger" in SOURCE
    assert "if (isUp && g_triggerBlockedKeys[vk])" in SOURCE
    assert "g_triggerBlockedKeys[vk] = true;" in SOURCE
    assert "if (HandleKeyboardPopupTrigger(vk, isDown, isUp, wasPressed))" in SOURCE


def test_keyboard_popup_trigger_uses_hook_state_for_modifier_chords():
    handler = SOURCE[
        SOURCE.index("static bool HandleKeyboardPopupTrigger") : SOURCE.index("static void InvokeRawInputFallback")
    ]

    assert "int currentMod = HookKeyboardModifiers();" in handler
    assert "HookKeyboardKeyPressed(targetVk)" in handler
    assert "GetAsyncKeyState(VK_SHIFT)" not in handler


def test_registered_keyboard_trigger_is_not_swallowed_before_wm_hotkey():
    handler = SOURCE[
        SOURCE.index("static bool HandleKeyboardPopupTrigger") : SOURCE.index("static void InvokeRawInputFallback")
    ]

    registered_guard = handler.index("if (targetMode == 1 && IsActiveKeyboardTriggerRegistered(isSpecial))")
    pass_through = handler.index("return false;", registered_guard)
    fallback_block = handler.index("g_triggerBlockedKeys[vk] = true;")

    assert registered_guard < pass_through < fallback_block


def test_single_key_keyboard_triggers_use_register_hotkey_with_async_state_fallback():
    assert "QL_NORMAL_TRIGGER_HOTKEY_ID" in SOURCE
    assert "QL_SPECIAL_TRIGGER_HOTKEY_ID" in SOURCE
    assert "static void RefreshRegisteredTriggerHotkeys()" in SOURCE
    assert "static bool HandleRegisteredKeyboardTrigger" in SOURCE
    assert "static void PollAsyncKeyboardTrigger()" in SOURCE
    assert "ASYNC_KEYBOARD_TRIGGER_TIMER" in SOURCE
    assert "RegisterHotKey(" in SOURCE


def test_context_specific_hotkeys_are_not_registered_globally():
    refresher = SOURCE[
        SOURCE.index("static void RefreshRegisteredTriggerHotkeys") : SOURCE.index(
            "static bool IsActiveKeyboardTriggerRegistered"
        )
    ]

    assert "bool hasSpecialApps = HasSpecialAppsConfigured();" in refresher
    assert "SingleKeyTriggerConfigEqual(" in refresher
    assert "if (!normalEligible ||" in refresher
    assert refresher.count("RegisterHotKey(") == 2


def test_keyboard_and_mouse_special_app_checks_use_their_own_target_windows():
    assert "static bool IsSpecialAppForMouse()" in SOURCE
    assert "GetCursorTargetWindowForSpecialAppCheck()" in SOURCE
    assert "static bool IsSpecialAppForKeyboard()" in SOURCE
    assert "GetForegroundTargetWindowForSpecialAppCheck()" in SOURCE

    mouse_matcher = SOURCE[
        SOURCE.index("static bool ShouldTriggerMouseButton") : SOURCE.index("static int RawKeyboardModifiers")
    ]
    keyboard_matchers = SOURCE[
        SOURCE.index("static bool HandleRegisteredKeyboardTrigger") : SOURCE.index("static void InvokeRawInputFallback")
    ]
    assert "IsSpecialAppForMouse()" in mouse_matcher
    assert keyboard_matchers.count("IsSpecialAppForKeyboard()") >= 4


def test_special_app_changes_refresh_registered_keyboard_hotkeys():
    setter = SOURCE[SOURCE.index("HOOKS_API void SetSpecialApps") : SOURCE.index("HOOKS_API void SetTriggerConfig")]

    assert setter.count("WM_QL_REFRESH_TRIGGER_HOTKEYS") == 2
    assert setter.count("g_asyncKeyboardTriggerLatched = false;") == 2


def test_keyboard_trigger_channels_are_deduplicated_and_suspended_during_capture():
    assert "g_lastKeyboardTriggerCallbackTick" in SOURCE
    assert "InvokeKeyboardTriggerCallback()" in SOURCE
    poller = SOURCE[
        SOURCE.index("static void PollAsyncKeyboardTrigger") : SOURCE.index("static bool ShouldTriggerMouseButton")
    ]
    registered_handler = SOURCE[
        SOURCE.index("static bool HandleRegisteredKeyboardTrigger") : SOURCE.index(
            "static void PollAsyncKeyboardTrigger"
        )
    ]

    assert "RuntimeTriggerSuppressedByCapture()" in poller
    assert "RuntimeTriggerSuppressedByCapture()" in registered_handler


def test_all_low_level_and_raw_trigger_channels_pause_during_macro_capture():
    mouse_hook = SOURCE[SOURCE.index("LRESULT CALLBACK MouseHookProc") : SOURCE.index("DWORD WINAPI MouseHookThread")]
    keyboard_hook = SOURCE[
        SOURCE.index("LRESULT CALLBACK KeyboardHookProc") : SOURCE.index("DWORD WINAPI KeyboardHookThread")
    ]
    raw_keyboard = SOURCE[
        SOURCE.index("static bool ShouldTriggerRawKeyboard") : SOURCE.index("static bool HandleKeyboardPopupTrigger")
    ]
    raw_mouse = SOURCE[
        SOURCE.index("static void InvokeRawInputFallback") : SOURCE.index("static void ReconcileRawInputButton")
    ]

    assert "if (g_inputCaptureActive.load())" in mouse_hook
    assert "if (g_inputCaptureActive.load())" in keyboard_hook
    assert "RuntimeTriggerSuppressedByCapture()" in raw_keyboard
    assert "RuntimeTriggerSuppressedByCapture()" in raw_mouse


def test_native_capture_file_logging_requires_explicit_debug_switch():
    logger_body = SOURCE[
        SOURCE.index(
            "static void LogProtectedCaptureEvent(", SOURCE.index("static void WriteCaptureDebugEvent")
        ) : SOURCE.index("static void StopDebugLogThread")
    ]

    assert "if (!HookDebugLoggingEnabled()) return;" in logger_body


def test_hotkey_capture_preserves_preexisting_physical_keys():
    assert "g_hotkeyCapturePreexisting[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;" in SOURCE
    assert "if (g_hotkeyCapturePreexisting[normalizedVk])" in SOURCE


def test_capture_timeout_does_not_swallow_the_first_post_timeout_input():
    hotkey_handler = SOURCE[
        SOURCE.index("static bool HandleHotkeyCapture") : SOURCE.index(
            "static void ResetProtectedChordCaptureStateLocked"
        )
    ]
    protected_keyboard = SOURCE[
        SOURCE.index("static bool HandleProtectedChordKeyboard") : SOURCE.index("static int MouseButtonFromMessage")
    ]
    protected_mouse = SOURCE[
        SOURCE.index("static bool HandleProtectedChordMouse") : SOURCE.index("static void SafeInvokeAny")
    ]

    assert "StopHotkeyCaptureLocked();\n                return false;" in hotkey_handler
    assert "ProtectedChordCaptureTimedOutLocked()) {\n            return false;" in protected_keyboard
    assert "ProtectedChordCaptureTimedOutLocked()) {\n            return false;" in protected_mouse
    assert "if (ProtectedChordCaptureTimedOutLocked()) return false;" in protected_keyboard
    assert "if (ProtectedChordCaptureTimedOutLocked()) return false;" in protected_mouse


def test_uninstalling_keyboard_does_not_cancel_mouse_only_protected_capture():
    uninstaller = SOURCE[SOURCE.index("void UninstallKeyboardHook()") : SOURCE.index("bool IsAltHeld()")]

    assert "HOOK_CHORD_CAPTURE_KEYBOARD" in uninstaller
    assert "StopProtectedChordCapture();" in uninstaller
    assert "g_protectedChordCaptureEnabled = false;" not in uninstaller


def test_protected_chord_capture_blocks_keyboard_and_mouse_before_normal_handlers():
    assert "if (HandleProtectedChordKeyboard(vk, wParam, pKbd))" in SOURCE
    assert "if (HandleProtectedChordMouse(wParam, pMouse))" in SOURCE
    assert "HOOKS_API bool StartProtectedChordCapture" in SOURCE
    assert "HOOKS_API bool StartProtectedChordCapture" in HEADER


def test_protected_keyboard_capture_can_filter_injected_input_before_normal_handlers():
    hook_proc = SOURCE[
        SOURCE.index("LRESULT CALLBACK KeyboardHookProc") : SOURCE.index("DWORD WINAPI KeyboardHookThread")
    ]

    protected_capture = hook_proc.index("HandleProtectedChordKeyboard")
    injected_filter = hook_proc.index("LLKHF_INJECTED")

    assert protected_capture < injected_filter
    protected_handler = SOURCE[
        SOURCE.index("static bool HandleProtectedChordKeyboard") : SOURCE.index("static int MouseButtonFromMessage")
    ]
    assert "HOOK_CHORD_CAPTURE_INCLUDE_INJECTED" in protected_handler
    assert '"keyboard_ignored"' in protected_handler


def test_protected_chord_capture_has_cross_process_exclusion():
    assert 'L"Local\\\\QuickLauncher.ProtectedChordCapture.v2"' in SOURCE
    assert "CreateSemaphoreW(" in SOURCE
    assert "AcquireProtectedChordProcessLockLocked()" in SOURCE
    assert "ReleaseProtectedChordProcessLockLocked()" in SOURCE
    assert "ReleaseSemaphore(" in SOURCE


def test_protected_chord_capture_completes_after_all_inputs_are_released():
    keyboard_handler = SOURCE[
        SOURCE.index("static bool HandleProtectedChordKeyboard") : SOURCE.index("static int MouseButtonFromMessage")
    ]
    mouse_handler = SOURCE[
        SOURCE.index("static bool HandleProtectedChordMouse") : SOURCE.index("static void SafeInvokeAny")
    ]

    assert "g_protectedChordCaptureStarted && !AnyProtectedChordInputPressedLocked()" in keyboard_handler
    assert "g_protectedChordCaptureStarted && !AnyProtectedChordInputPressedLocked()" in mouse_handler
    assert "completionCallback" in keyboard_handler
    assert "completionCallback" in mouse_handler
