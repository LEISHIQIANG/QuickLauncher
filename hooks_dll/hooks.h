#pragma once

#ifdef HOOKS_EXPORTS
#define HOOKS_API __declspec(dllexport)
#else
#define HOOKS_API __declspec(dllimport)
#endif

extern "C" {
    // 回调函数类型
    typedef void (*MouseCallback)(int x, int y);
    typedef void (*KeyboardCallback)();
    typedef void (*HotkeyCaptureCallback)(int vkCode, int modifiers, int sideModifiers);

    enum HookInputEventType {
        HOOK_INPUT_MOUSE_MOVE = 1,
        HOOK_INPUT_MOUSE_BUTTON_DOWN = 2,
        HOOK_INPUT_MOUSE_BUTTON_UP = 3,
        HOOK_INPUT_MOUSE_WHEEL = 4,
        HOOK_INPUT_MOUSE_HWHEEL = 5,
        HOOK_INPUT_KEY_DOWN = 6,
        HOOK_INPUT_KEY_UP = 7,
        HOOK_INPUT_UNICODE_DOWN = 8,
        HOOK_INPUT_UNICODE_UP = 9,
    };

    enum HookInputEventFlags {
        HOOK_INPUT_FLAG_EXTENDED = 0x0001,
        HOOK_INPUT_FLAG_INJECTED = 0x0002,
        HOOK_INPUT_FLAG_LOWER_IL_INJECTED = 0x0004,
        HOOK_INPUT_FLAG_OWN_PLAYBACK = 0x0008,
        HOOK_INPUT_FLAG_SYSTEM_KEY = 0x0010,
        HOOK_INPUT_FLAG_REPEAT = 0x0020,
        HOOK_INPUT_FLAG_ABSOLUTE = 0x0040,
    };

    enum HookInputCaptureFilter {
        HOOK_CAPTURE_MOUSE_MOVE = 0x0001,
        HOOK_CAPTURE_MOUSE_BUTTON = 0x0002,
        HOOK_CAPTURE_MOUSE_WHEEL = 0x0004,
        HOOK_CAPTURE_KEYBOARD = 0x0008,
        HOOK_CAPTURE_ALL_PHYSICAL = 0x000F,
        HOOK_CAPTURE_INCLUDE_INJECTED = 0x0100,
        HOOK_CAPTURE_INCLUDE_OWN_PLAYBACK = 0x0200,
        HOOK_CAPTURE_COALESCE_MOUSE_MOVE = 0x0400,
    };

    enum HookMacroPlaybackOptions {
        HOOK_PLAYBACK_DEFAULT = 0x0000,
        HOOK_PLAYBACK_NO_TIMING = 0x0001,
        HOOK_PLAYBACK_KEEP_PRESSED_ON_CANCEL = 0x0002,
    };

    struct HookInputEvent {
        unsigned int size;
        unsigned int type;
        unsigned int flags;
        unsigned int reserved;
        unsigned long long timestampUs;
        unsigned long long sequence;
        int x;
        int y;
        int data;
        unsigned int vkCode;
        unsigned int scanCode;
        unsigned long long extraInfo;
    };

    struct HookMacroEvent {
        unsigned int size;
        unsigned int type;
        unsigned int flags;
        unsigned int delayUs;
        int x;
        int y;
        int data;
        unsigned int vkCode;
        unsigned int scanCode;
    };

    struct HookMacroStatus {
        unsigned int size;
        unsigned int active;
        unsigned int cancelRequested;
        unsigned int lastError;
        unsigned long long totalEvents;
        unsigned long long completedEvents;
        unsigned long long capturedEvents;
        unsigned long long captureDropped;
        unsigned long long playbackStartedTick;
        unsigned long long playbackFinishedTick;
    };

    typedef void (*InputEventCallback)(const HookInputEvent* eventData);

    struct HooksRuntimeStats {
        unsigned int size;
        unsigned int version;
        unsigned int healthFlags;
        unsigned int callbackQueueDepth;
        unsigned long long lowLevelMouseEvents;
        unsigned long long rawMouseEvents;
        unsigned long long rawFallbackTriggers;
        unsigned long long injectedMouseEventsIgnored;
        unsigned long long lowLevelKeyboardEvents;
        unsigned long long rawKeyboardEvents;
        unsigned long long injectedKeyboardEventsIgnored;
        unsigned long long callbackQueueDropped;
        unsigned long long callbackExceptions;
        unsigned long long mouseLastEventTick;
        unsigned long long keyboardLastEventTick;
    };

    // 鼠标钩子
    HOOKS_API bool InstallMouseHook(MouseCallback callback);
    HOOKS_API void UninstallMouseHook();
    HOOKS_API void SetMousePaused(bool paused);
    HOOKS_API bool IsMousePaused();
    HOOKS_API bool IsMouseHookInstalled();
    HOOKS_API bool IsRawInputFallbackActive();
    HOOKS_API void SetAltDoubleClickCallback(MouseCallback callback);

    // 键盘钩子
    HOOKS_API bool InstallKeyboardHook(KeyboardCallback altDoubleTapCallback);
    HOOKS_API void UninstallKeyboardHook();
    HOOKS_API bool IsAltHeld();
    HOOKS_API bool IsCtrlHeld();
    HOOKS_API bool IsKeyboardHookInstalled();
    HOOKS_API bool SetGlobalHotkey(const char* hotkeyStr, KeyboardCallback callback);
    HOOKS_API void ClearGlobalHotkey();
    HOOKS_API bool StartHotkeyCapture(HotkeyCaptureCallback callback, int timeoutMs);
    HOOKS_API void StopHotkeyCapture();
    HOOKS_API bool IsHotkeyCaptureActive();

    // 宏录制与回放基础接口
    HOOKS_API bool StartInputCapture(InputEventCallback callback, unsigned int filterFlags);
    HOOKS_API void StopInputCapture();
    HOOKS_API bool IsInputCaptureActive();
    HOOKS_API bool PlayMacroEvents(const HookMacroEvent* events, unsigned int count, unsigned int options);
    HOOKS_API void CancelMacroPlayback();
    HOOKS_API bool IsMacroPlaybackActive();
    HOOKS_API bool WaitForMacroPlayback(unsigned int timeoutMs);
    HOOKS_API bool GetMacroStatus(HookMacroStatus* status, unsigned int statusSize);
    HOOKS_API void ReleaseMacroPressedInputs();

    // 特殊应用列表
    HOOKS_API void SetSpecialApps(const char** apps, int count);
    HOOKS_API void ClearSpecialApps();

    // 触发配置
    HOOKS_API void SetTriggerConfig(int normalButton, int normalModifiers, int specialButton, int specialModifiers);
    HOOKS_API void SetTriggerConfigEx(int normalMode, int normalButton, const char* normalKeys, int normalModifiers,
                                       int specialMode, int specialButton, const char* specialKeys, int specialModifiers);

    // 工具函数
    HOOKS_API void ReleaseAllModifierKeys();
    HOOKS_API int GetHooksVersion();
    HOOKS_API unsigned int GetHooksCapabilities();
    HOOKS_API unsigned long GetLastHookError();
    HOOKS_API bool GetHooksRuntimeStats(HooksRuntimeStats* stats, unsigned int statsSize);
    HOOKS_API void ResetHooksRuntimeStats();
}
