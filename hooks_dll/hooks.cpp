#define HOOKS_EXPORTS
#define NOMINMAX
#include "hooks.h"
#include <windows.h>
#include <atomic>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <mutex>
#include <sstream>

// 全局变量
static HHOOK g_mouseHook = NULL;
static HHOOK g_keyboardHook = NULL;
static HWND g_rawInputWindow = NULL;
static DWORD g_mouseThreadId = 0;
static DWORD g_keyboardThreadId = 0;
static HANDLE g_mouseThreadHandle = NULL;
static HANDLE g_keyboardThreadHandle = NULL;
static HANDLE g_mouseReadyEvent = NULL;
static HANDLE g_keyboardReadyEvent = NULL;
static HANDLE g_mouseExitedEvent = NULL;
static HANDLE g_keyboardExitedEvent = NULL;
static std::atomic<bool> g_mouseRunning(false);
static std::atomic<bool> g_keyboardRunning(false);
static std::atomic<bool> g_mouseInstalling(false);
static std::atomic<bool> g_keyboardInstalling(false);
static std::atomic<bool> g_mouseThreadAlive(false);
static std::atomic<bool> g_keyboardThreadAlive(false);
static std::atomic<bool> g_rawInputActive(false);
static std::atomic<bool> g_lowLevelMouseHealthy(false);
static std::atomic<bool> g_lowLevelKeyboardHealthy(false);

static HMODULE GetCurrentDllModule() {
    HMODULE hMod = NULL;
    GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCSTR>(&GetCurrentDllModule),
        &hMod
    );
    return hMod;
}

// 回调
static std::atomic<MouseCallback> g_mouseCallback(nullptr);
static std::atomic<MouseCallback> g_altDoubleClickCallback(nullptr);
static std::atomic<KeyboardCallback> g_altDoubleTapCallback(nullptr);
static std::atomic<KeyboardCallback> g_hotkeyCallback(nullptr);
static std::atomic<HotkeyCaptureCallback> g_hotkeyCaptureCallback(nullptr);
static std::atomic<InputEventCallback> g_inputEventCallback(nullptr);

// 状态
static std::atomic<bool> g_mousePaused(false);
static std::atomic<bool> g_altHeld(false);
static std::atomic<bool> g_ctrlHeld(false);
static std::atomic<bool> g_blockedDown(false);
static std::atomic<int> g_blockedButton(0);
static std::atomic<DWORD> g_lastHookError(0);
static std::atomic<unsigned long long> g_lowLevelPhysicalDownCount[5];
static unsigned long long g_rawConsumedLowLevelCount[5] = {0, 0, 0, 0, 0};
static unsigned int g_pendingRawDownCount[5] = {0, 0, 0, 0, 0};
static std::atomic<unsigned long long> g_lastRawFallbackTick[5];
static std::atomic<unsigned long long> g_lowLevelPhysicalKeyboardCount(0);
static unsigned long long g_rawConsumedLowLevelKeyboardCount = 0;
static bool g_rawKeyboardPressed[256] = {false};
struct PendingRawKeyboardEvent {
    int vk;
    bool down;
    bool shouldTrigger;
};
static std::deque<PendingRawKeyboardEvent> g_pendingRawKeyboardEvents;
static std::atomic<unsigned long long> g_lastRawKeyboardFallbackTick(0);
static std::atomic<int> g_lastRawKeyboardFallbackVk(0);

// 时间戳
static double g_lastBlockTime = 0.0;
static double g_altPressTime = 0.0;
static double g_lastAltReleaseTime = 0.0;
static double g_lastDoubleTapTime = 0.0;
static double g_altLClickLastTime = 0.0;
static double g_altLClickLastTrigger = 0.0;
static std::atomic<int> g_altTapCount(0);
static std::atomic<bool> g_otherKeyPressed(false);

// 热键配置
static std::atomic<int> g_hotkeyModifiers(0);
static std::atomic<int> g_hotkeyVk(0);
static std::atomic<bool> g_hotkeyEnabled(false);
static std::atomic<bool> g_registeredHotkeyActive(false);
static double g_lastHotkeyTime = 0.0;
static std::mutex g_hotkeyConfigMutex;
static HANDLE g_hotkeyCommandEvent = NULL;
static std::atomic<bool> g_hotkeyCommandResult(false);

// 快捷键录制模式：启用后吞掉所有键盘事件，只把最终组合回调给 UI。
static std::atomic<bool> g_hotkeyCaptureEnabled(false);
static bool g_hotkeyCaptureCompleted = false;
static DWORD g_hotkeyCaptureStartedTick = 0;
static DWORD g_hotkeyCaptureTimeoutMs = 10000;
static bool g_hotkeyCapturePressed[256] = {false};
static bool g_keyboardPressed[256] = {false};
static int g_hotkeyCaptureSideModifiers = 0;
static std::mutex g_hotkeyCaptureMutex;

// 特殊应用列表
static std::vector<std::string> g_specialApps;
static std::mutex g_specialAppsMutex;

// 触发配置
static int g_normalTriggerMode = 0;        // 0=mouse, 1=keyboard, 2=hybrid
static int g_normalTriggerButton = 4;      // 默认中键
static std::vector<int> g_normalTriggerKeys;  // 键盘按键VK码
static int g_normalTriggerModifiers = 0;   // 默认无修饰键
static int g_specialTriggerMode = 0;
static int g_specialTriggerButton = 4;     // 默认中键
static std::vector<int> g_specialTriggerKeys;
static int g_specialTriggerModifiers = 2;  // 默认Ctrl
static std::mutex g_triggerConfigMutex;

static std::mutex g_debugLogMutex;
static std::mutex g_debugLogStartMutex;
static HANDLE g_debugLogThread = NULL;
static HANDLE g_debugLogEvent = NULL;
static std::atomic<bool> g_debugLogThreadRunning(false);

struct MouseDebugEvent {
    SYSTEMTIME time;
    WPARAM wParam;
    POINT hookPoint;
    POINT cursorPoint;
    DWORD flags;
    DWORD mouseData;
    ULONG_PTR extraInfo;
    SHORT mbState;
    bool blocked;
    bool paused;
    HWND foreground;
    HWND cursorWindow;
    char decision[64];
};

static std::vector<MouseDebugEvent> g_pendingDebugEvents;

// 回调线程 (单线程 + Event 模式，替代每次 CreateThread)
static HANDLE g_callbackThread = NULL;
static HANDLE g_callbackEvent = NULL;
static std::atomic<bool> g_callbackThreadRunning(false);
struct CallbackEvent {
    enum Type {
        AltDoubleTap,
        MouseTrigger,
        AltDoubleClick,
        GlobalHotkey,
        HotkeyCapture
    } type;
    int x;
    int y;
    HotkeyCaptureCallback hotkeyCaptureCallback;
    int vkCode;
    int modifiers;
    int sideModifiers;
};
static std::deque<CallbackEvent> g_pendingCallbacks;
static std::mutex g_callbackMutex;
static std::mutex g_callbackStartMutex;  // 保护 EnsureCallbackThread 的互斥锁
static std::atomic<int> g_callbacksInFlight(0);
static HANDLE g_callbackIdleEvent = NULL;

// 回调队列溢出计数
static std::atomic<unsigned long long> g_queueOverflowCount(0);
static std::atomic<unsigned long long> g_lowLevelMouseEventCount(0);
static std::atomic<unsigned long long> g_rawMouseEventCount(0);
static std::atomic<unsigned long long> g_rawFallbackTriggerCount(0);
static std::atomic<unsigned long long> g_injectedMouseIgnoredCount(0);
static std::atomic<unsigned long long> g_lowLevelKeyboardEventCount(0);
static std::atomic<unsigned long long> g_rawKeyboardEventCount(0);
static std::atomic<unsigned long long> g_injectedKeyboardIgnoredCount(0);
static std::atomic<unsigned long long> g_callbackExceptionCount(0);
static std::atomic<unsigned long long> g_mouseLastEventTick(0);
static std::atomic<unsigned long long> g_keyboardLastEventTick(0);

// 宏输入录制使用独立队列，避免高频移动事件阻塞弹窗/热键回调。
static HANDLE g_inputCaptureThread = NULL;
static HANDLE g_inputCaptureEvent = NULL;
static HANDLE g_inputCaptureIdleEvent = NULL;
static std::atomic<bool> g_inputCaptureThreadRunning(false);
static std::atomic<bool> g_inputCaptureActive(false);
static std::atomic<unsigned int> g_inputCaptureFilter(0);
static std::atomic<unsigned long long> g_inputCaptureSequence(0);
static std::atomic<unsigned long long> g_inputCapturedCount(0);
static std::atomic<unsigned long long> g_inputCaptureDroppedCount(0);
static LARGE_INTEGER g_inputCaptureStartCounter = {};
static LARGE_INTEGER g_performanceFrequency = {};
static std::deque<HookInputEvent> g_pendingInputEvents;
static std::mutex g_inputCaptureMutex;
static std::mutex g_inputCaptureStartMutex;
static std::atomic<int> g_inputCaptureCallbacksInFlight(0);

// 宏回放在独立线程执行，SendInput 事件带专用标记，默认不会被再次录制或触发启动器。
static HANDLE g_macroPlaybackThread = NULL;
static HANDLE g_macroCancelEvent = NULL;
static HANDLE g_macroDoneEvent = NULL;
static std::atomic<bool> g_macroPlaybackActive(false);
static std::atomic<bool> g_macroCancelRequested(false);
static std::atomic<unsigned long long> g_macroTotalEvents(0);
static std::atomic<unsigned long long> g_macroCompletedEvents(0);
static std::atomic<unsigned long long> g_macroPlaybackStartedTick(0);
static std::atomic<unsigned long long> g_macroPlaybackFinishedTick(0);
static std::atomic<DWORD> g_macroLastError(0);
static std::vector<HookMacroEvent> g_macroPlaybackEvents;
static unsigned int g_macroPlaybackOptions = 0;
static std::mutex g_macroPlaybackMutex;
static std::mutex g_macroPressedMutex;
static bool g_macroPressedKeys[256] = {false};
static unsigned int g_macroPressedKeyScanCodes[256] = {0};
static unsigned int g_macroPressedKeyFlags[256] = {0};
static std::vector<unsigned int> g_macroPressedUnicode;
static unsigned int g_macroPressedMouseButtons = 0;

// 常量
constexpr double MIN_BLOCK_INTERVAL = 0.025;
constexpr double ALT_DOUBLE_TAP_INTERVAL = 0.40;
constexpr double ALT_TAP_MAX_HOLD_TIME = 0.25;
constexpr double ALT_DOUBLE_TAP_COOLDOWN = 0.50;
constexpr double ALT_LCLICK_DOUBLE_INTERVAL = 0.40;
constexpr double ALT_LCLICK_COOLDOWN = 0.50;
constexpr double BLOCKED_STATE_TIMEOUT = 2.0;  // 2秒超时自动释放
constexpr int HOOKS_VERSION = 9;
constexpr unsigned int HOOKS_CAP_MOUSE = 0x0001;
constexpr unsigned int HOOKS_CAP_KEYBOARD = 0x0002;
constexpr unsigned int HOOKS_CAP_GLOBAL_HOTKEY = 0x0004;
constexpr unsigned int HOOKS_CAP_SPECIAL_APPS = 0x0008;
constexpr unsigned int HOOKS_CAP_DIAGNOSTICS = 0x0010;
constexpr unsigned int HOOKS_CAP_HEALTH_STATUS = 0x0020;
constexpr unsigned int HOOKS_CAP_HOTKEY_CAPTURE = 0x0040;
constexpr unsigned int HOOKS_CAP_RAW_INPUT_FALLBACK = 0x0080;
constexpr unsigned int HOOKS_CAP_RUNTIME_STATS = 0x0100;
constexpr unsigned int HOOKS_CAP_REGISTER_HOTKEY = 0x0200;
constexpr unsigned int HOOKS_CAP_INPUT_CAPTURE = 0x0400;
constexpr unsigned int HOOKS_CAP_MACRO_PLAYBACK = 0x0800;
constexpr size_t CALLBACK_QUEUE_LIMIT = 256;
constexpr size_t INPUT_CAPTURE_QUEUE_LIMIT = 8192;
constexpr unsigned int MAX_MACRO_EVENTS = 100000;
constexpr DWORD THREAD_JOIN_TIMEOUT_MS = 2000;
constexpr DWORD CALLBACK_DRAIN_TIMEOUT_MS = 1000;
constexpr DWORD HOOK_COMMAND_TIMEOUT_MS = 1000;
constexpr UINT_PTR RAW_FALLBACK_TIMER_BASE = 0x5140;
constexpr UINT_PTR RAW_KEYBOARD_RECONCILE_TIMER = 0x5145;
constexpr UINT RAW_FALLBACK_RECONCILE_MS = 20;
constexpr unsigned long long RAW_FALLBACK_LATE_LL_WINDOW_MS = 80;
constexpr UINT WM_QL_REGISTER_HOTKEY = WM_APP + 0x51;
constexpr UINT WM_QL_CLEAR_HOTKEY = WM_APP + 0x52;
constexpr UINT WM_QL_START_CAPTURE_TIMER = WM_APP + 0x53;
constexpr UINT WM_QL_STOP_CAPTURE_TIMER = WM_APP + 0x54;
constexpr int QL_GLOBAL_HOTKEY_ID = 0x514C;
constexpr UINT_PTR QL_CAPTURE_TIMER_ID = 0x514D;
constexpr unsigned long long QL_MACRO_EXTRA_INFO = 0x514C4D4143524F31ULL;

constexpr unsigned int HOOK_HEALTH_MOUSE_THREAD = 0x0001;
constexpr unsigned int HOOK_HEALTH_MOUSE_LL = 0x0002;
constexpr unsigned int HOOK_HEALTH_RAW_MOUSE = 0x0004;
constexpr unsigned int HOOK_HEALTH_KEYBOARD_THREAD = 0x0008;
constexpr unsigned int HOOK_HEALTH_KEYBOARD_LL = 0x0010;
constexpr unsigned int HOOK_HEALTH_CALLBACK_THREAD = 0x0020;
constexpr unsigned int HOOK_HEALTH_REGISTERED_HOTKEY = 0x0040;
constexpr unsigned int HOOK_HEALTH_RAW_KEYBOARD = 0x0080;

constexpr int HOTKEY_MOD_ALT = 1;
constexpr int HOTKEY_MOD_CTRL = 2;
constexpr int HOTKEY_MOD_SHIFT = 4;
constexpr int HOTKEY_MOD_WIN = 8;

constexpr int HOTKEY_SIDE_LSHIFT = 0x0001;
constexpr int HOTKEY_SIDE_RSHIFT = 0x0002;
constexpr int HOTKEY_SIDE_LCTRL = 0x0004;
constexpr int HOTKEY_SIDE_RCTRL = 0x0008;
constexpr int HOTKEY_SIDE_LALT = 0x0010;
constexpr int HOTKEY_SIDE_RALT = 0x0020;
constexpr int HOTKEY_SIDE_LWIN = 0x0040;
constexpr int HOTKEY_SIDE_RWIN = 0x0080;

static HANDLE EnsureManualResetEvent(HANDLE& eventHandle, BOOL initialState) {
    if (eventHandle == NULL) {
        eventHandle = CreateEventW(NULL, TRUE, initialState, NULL);
    }
    return eventHandle;
}

static bool WaitForHookThreadExit(
    std::atomic<bool>& threadAlive,
    HANDLE exitedEvent,
    HANDLE threadHandle)
{
    if (!threadAlive.load()) return true;
    DWORD result = WAIT_FAILED;
    if (exitedEvent != NULL) {
        result = WaitForSingleObject(exitedEvent, THREAD_JOIN_TIMEOUT_MS);
    } else if (threadHandle != NULL) {
        result = WaitForSingleObject(threadHandle, THREAD_JOIN_TIMEOUT_MS);
    }
    if (result == WAIT_OBJECT_0 || !threadAlive.load()) return true;
    g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
    return false;
}

inline double GetTime() {
    return GetTickCount64() / 1000.0;
}

static unsigned long long GetCaptureTimestampUs() {
    LARGE_INTEGER now = {};
    QueryPerformanceCounter(&now);
    if (g_performanceFrequency.QuadPart <= 0) {
        QueryPerformanceFrequency(&g_performanceFrequency);
    }
    if (g_inputCaptureStartCounter.QuadPart <= 0 || g_performanceFrequency.QuadPart <= 0) {
        return 0;
    }
    unsigned long long delta = static_cast<unsigned long long>(
        now.QuadPart - g_inputCaptureStartCounter.QuadPart);
    return delta * 1000000ULL /
        static_cast<unsigned long long>(g_performanceFrequency.QuadPart);
}

static bool IsOwnMacroInput(ULONG_PTR extraInfo) {
    return static_cast<unsigned long long>(extraInfo) == QL_MACRO_EXTRA_INFO;
}

static bool CaptureFilterAllows(const HookInputEvent& eventData) {
    unsigned int filter = g_inputCaptureFilter.load();
    unsigned int category = 0;
    switch (eventData.type) {
        case HOOK_INPUT_MOUSE_MOVE:
            category = HOOK_CAPTURE_MOUSE_MOVE;
            break;
        case HOOK_INPUT_MOUSE_BUTTON_DOWN:
        case HOOK_INPUT_MOUSE_BUTTON_UP:
            category = HOOK_CAPTURE_MOUSE_BUTTON;
            break;
        case HOOK_INPUT_MOUSE_WHEEL:
        case HOOK_INPUT_MOUSE_HWHEEL:
            category = HOOK_CAPTURE_MOUSE_WHEEL;
            break;
        case HOOK_INPUT_KEY_DOWN:
        case HOOK_INPUT_KEY_UP:
        case HOOK_INPUT_UNICODE_DOWN:
        case HOOK_INPUT_UNICODE_UP:
            category = HOOK_CAPTURE_KEYBOARD;
            break;
        default:
            return false;
    }
    if ((filter & category) == 0) return false;
    if ((eventData.flags & HOOK_INPUT_FLAG_OWN_PLAYBACK) != 0) {
        return (filter & HOOK_CAPTURE_INCLUDE_OWN_PLAYBACK) != 0;
    }
    if ((eventData.flags & HOOK_INPUT_FLAG_INJECTED) != 0) {
        return (filter & HOOK_CAPTURE_INCLUDE_INJECTED) != 0;
    }
    return true;
}

static void SafeInvokeInputEvent(InputEventCallback callback, const HookInputEvent* eventData) {
    if (!callback || !eventData) return;
    __try {
        callback(eventData);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        g_callbackExceptionCount.fetch_add(1);
    }
}

static DWORD WINAPI InputCaptureThreadProc(LPVOID) {
    while (g_inputCaptureThreadRunning.load()) {
        DWORD result = WaitForSingleObject(g_inputCaptureEvent, 500);
        if (!g_inputCaptureThreadRunning.load()) break;
        if (result != WAIT_OBJECT_0) continue;

        std::deque<HookInputEvent> events;
        {
            std::lock_guard<std::mutex> lock(g_inputCaptureMutex);
            events.swap(g_pendingInputEvents);
            if (!events.empty()) {
                if (g_inputCaptureIdleEvent) ResetEvent(g_inputCaptureIdleEvent);
                g_inputCaptureCallbacksInFlight.fetch_add(static_cast<int>(events.size()));
            }
        }
        for (const HookInputEvent& eventData : events) {
            SafeInvokeInputEvent(g_inputEventCallback.load(), &eventData);
            if (g_inputCaptureCallbacksInFlight.fetch_sub(1) == 1 && g_inputCaptureIdleEvent) {
                SetEvent(g_inputCaptureIdleEvent);
            }
        }
    }
    if (g_inputCaptureIdleEvent) SetEvent(g_inputCaptureIdleEvent);
    return 0;
}

static bool EnsureInputCaptureThread() {
    if (g_inputCaptureThreadRunning.load() && g_inputCaptureThread) return true;
    std::lock_guard<std::mutex> lock(g_inputCaptureStartMutex);
    if (g_inputCaptureThreadRunning.load() && g_inputCaptureThread) return true;

    if (g_inputCaptureThread) {
        if (WaitForSingleObject(g_inputCaptureThread, 0) != WAIT_OBJECT_0) {
            return false;
        }
        CloseHandle(g_inputCaptureThread);
        g_inputCaptureThread = NULL;
    }

    if (!g_inputCaptureEvent) {
        g_inputCaptureEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    }
    if (!g_inputCaptureIdleEvent) {
        g_inputCaptureIdleEvent = CreateEventW(NULL, TRUE, TRUE, NULL);
    }
    if (!g_inputCaptureEvent || !g_inputCaptureIdleEvent) {
        g_lastHookError = GetLastError();
        return false;
    }

    g_inputCaptureThreadRunning = true;
    g_inputCaptureThread = CreateThread(NULL, 0, InputCaptureThreadProc, NULL, 0, NULL);
    if (!g_inputCaptureThread) {
        g_lastHookError = GetLastError();
        g_inputCaptureThreadRunning = false;
        return false;
    }
    return true;
}

static bool StopInputCaptureThread() {
    g_inputCaptureActive = false;
    g_inputCaptureThreadRunning = false;
    if (g_inputCaptureEvent) SetEvent(g_inputCaptureEvent);
    if (g_inputCaptureThread) {
        DWORD result = WaitForSingleObject(g_inputCaptureThread, THREAD_JOIN_TIMEOUT_MS);
        if (result != WAIT_OBJECT_0) {
            g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
            return false;
        }
        CloseHandle(g_inputCaptureThread);
        g_inputCaptureThread = NULL;
    }
    if (g_inputCaptureEvent) {
        CloseHandle(g_inputCaptureEvent);
        g_inputCaptureEvent = NULL;
    }
    if (g_inputCaptureIdleEvent) {
        CloseHandle(g_inputCaptureIdleEvent);
        g_inputCaptureIdleEvent = NULL;
    }
    {
        std::lock_guard<std::mutex> lock(g_inputCaptureMutex);
        g_pendingInputEvents.clear();
    }
    g_inputEventCallback = nullptr;
    return true;
}

static void QueueCapturedInput(HookInputEvent eventData) {
    if (!g_inputCaptureActive.load() || !g_inputEventCallback.load()) return;
    if (!CaptureFilterAllows(eventData)) return;

    eventData.size = sizeof(HookInputEvent);
    eventData.timestampUs = GetCaptureTimestampUs();
    eventData.sequence = g_inputCaptureSequence.fetch_add(1) + 1;

    if (!EnsureInputCaptureThread()) {
        g_inputCaptureDroppedCount.fetch_add(1);
        return;
    }
    {
        std::lock_guard<std::mutex> lock(g_inputCaptureMutex);
        if ((g_inputCaptureFilter.load() & HOOK_CAPTURE_COALESCE_MOUSE_MOVE) != 0 &&
            eventData.type == HOOK_INPUT_MOUSE_MOVE &&
            !g_pendingInputEvents.empty() &&
            g_pendingInputEvents.back().type == HOOK_INPUT_MOUSE_MOVE &&
            g_pendingInputEvents.back().flags == eventData.flags) {
            // The newest absolute point is sufficient between non-move events.
            g_pendingInputEvents.back() = eventData;
        } else {
            if (g_pendingInputEvents.size() >= INPUT_CAPTURE_QUEUE_LIMIT) {
                g_pendingInputEvents.pop_front();
                g_inputCaptureDroppedCount.fetch_add(1);
            }
            g_pendingInputEvents.push_back(eventData);
        }
    }
    g_inputCapturedCount.fetch_add(1);
    if (g_inputCaptureEvent) SetEvent(g_inputCaptureEvent);
}

static bool IsAltPressedNow() {
    return (GetAsyncKeyState(VK_MENU) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_LMENU) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_RMENU) & 0x8000) != 0;
}

static bool IsCtrlPressedNow() {
    return (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_LCONTROL) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_RCONTROL) & 0x8000) != 0;
}

static bool IsModifierPressedNow(int bit) {
    if (bit == 1) {
        return IsAltPressedNow();
    }
    if (bit == 2) {
        return IsCtrlPressedNow();
    }
    if (bit == 4) {
        return (GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0 ||
               (GetAsyncKeyState(VK_LSHIFT) & 0x8000) != 0 ||
               (GetAsyncKeyState(VK_RSHIFT) & 0x8000) != 0;
    }
    if (bit == 8) {
        return (GetAsyncKeyState(VK_LWIN) & 0x8000) != 0 ||
               (GetAsyncKeyState(VK_RWIN) & 0x8000) != 0;
    }
    return false;
}

static void InvokeHotkeyCaptureCallbackAsync(HotkeyCaptureCallback callback, int vkCode, int modifiers, int sideModifiers);

static bool IsHotkeyModifierVk(int vk) {
    switch (vk) {
        case VK_SHIFT:
        case VK_LSHIFT:
        case VK_RSHIFT:
        case VK_CONTROL:
        case VK_LCONTROL:
        case VK_RCONTROL:
        case VK_MENU:
        case VK_LMENU:
        case VK_RMENU:
        case VK_LWIN:
        case VK_RWIN:
            return true;
        default:
            return false;
    }
}

static int NormalizeModifierVk(int vk, const KBDLLHOOKSTRUCT* pKbd) {
    if (!pKbd) return vk;
    if (vk == VK_SHIFT) {
        UINT mapped = MapVirtualKeyA(pKbd->scanCode, MAPVK_VSC_TO_VK_EX);
        return mapped == VK_RSHIFT ? VK_RSHIFT : VK_LSHIFT;
    }
    if (vk == VK_CONTROL) {
        return (pKbd->flags & LLKHF_EXTENDED) ? VK_RCONTROL : VK_LCONTROL;
    }
    if (vk == VK_MENU) {
        return (pKbd->flags & LLKHF_EXTENDED) ? VK_RMENU : VK_LMENU;
    }
    return vk;
}

static int HotkeySideBitForVk(int vk) {
    switch (vk) {
        case VK_LSHIFT: return HOTKEY_SIDE_LSHIFT;
        case VK_RSHIFT: return HOTKEY_SIDE_RSHIFT;
        case VK_LCONTROL: return HOTKEY_SIDE_LCTRL;
        case VK_RCONTROL: return HOTKEY_SIDE_RCTRL;
        case VK_LMENU: return HOTKEY_SIDE_LALT;
        case VK_RMENU: return HOTKEY_SIDE_RALT;
        case VK_LWIN: return HOTKEY_SIDE_LWIN;
        case VK_RWIN: return HOTKEY_SIDE_RWIN;
        default: return 0;
    }
}

static int HotkeyModifiersFromSides(int sideModifiers) {
    int modifiers = 0;
    if (sideModifiers & (HOTKEY_SIDE_LALT | HOTKEY_SIDE_RALT)) modifiers |= HOTKEY_MOD_ALT;
    if (sideModifiers & (HOTKEY_SIDE_LCTRL | HOTKEY_SIDE_RCTRL)) modifiers |= HOTKEY_MOD_CTRL;
    if (sideModifiers & (HOTKEY_SIDE_LSHIFT | HOTKEY_SIDE_RSHIFT)) modifiers |= HOTKEY_MOD_SHIFT;
    if (sideModifiers & (HOTKEY_SIDE_LWIN | HOTKEY_SIDE_RWIN)) modifiers |= HOTKEY_MOD_WIN;
    return modifiers;
}

static void ResetHotkeyCaptureStateLocked() {
    std::fill(g_hotkeyCapturePressed, g_hotkeyCapturePressed + 256, false);
    g_hotkeyCaptureSideModifiers = 0;
    g_hotkeyCaptureCompleted = false;
}

static bool AnyHotkeyCaptureKeyPressedLocked() {
    for (bool pressed : g_hotkeyCapturePressed) {
        if (pressed) return true;
    }
    return false;
}

static void StopHotkeyCaptureLocked() {
    g_hotkeyCaptureEnabled = false;
    g_hotkeyCaptureCallback = nullptr;
    ResetHotkeyCaptureStateLocked();
}

static bool HandleHotkeyCapture(int vk, WPARAM wParam, KBDLLHOOKSTRUCT* pKbd) {
    if (!g_hotkeyCaptureEnabled.load()) return false;

    HotkeyCaptureCallback callback = nullptr;
    int callbackVk = 0;
    int callbackModifiers = 0;
    int callbackSideModifiers = 0;
    bool captureWasActive = false;

    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        if (!g_hotkeyCaptureEnabled.load()) return false;
        captureWasActive = true;

        if (g_hotkeyCaptureTimeoutMs > 0) {
            DWORD elapsed = GetTickCount() - g_hotkeyCaptureStartedTick;
            if (elapsed > g_hotkeyCaptureTimeoutMs) {
                StopHotkeyCaptureLocked();
                return true;
            }
        }

        int normalizedVk = NormalizeModifierVk(vk, pKbd);
        bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
        bool isUp = (wParam == WM_KEYUP || wParam == WM_SYSKEYUP);

        if (normalizedVk >= 0 && normalizedVk < 256) {
            if (isDown) {
                g_hotkeyCapturePressed[normalizedVk] = true;
                int sideBit = HotkeySideBitForVk(normalizedVk);
                if (sideBit) g_hotkeyCaptureSideModifiers |= sideBit;

                if (!g_hotkeyCaptureCompleted && !IsHotkeyModifierVk(normalizedVk)) {
                    g_hotkeyCaptureCompleted = true;
                    callback = g_hotkeyCaptureCallback.load();
                    callbackVk = normalizedVk;
                    callbackSideModifiers = g_hotkeyCaptureSideModifiers;
                    callbackModifiers = HotkeyModifiersFromSides(callbackSideModifiers);
                }
            } else if (isUp) {
                g_hotkeyCapturePressed[normalizedVk] = false;
                int sideBit = HotkeySideBitForVk(normalizedVk);
                if (sideBit) g_hotkeyCaptureSideModifiers &= ~sideBit;

                if (g_hotkeyCaptureCompleted && !AnyHotkeyCaptureKeyPressedLocked()) {
                    StopHotkeyCaptureLocked();
                }
            }
        }
    }

    if (callback) {
        InvokeHotkeyCaptureCallbackAsync(callback, callbackVk, callbackModifiers, callbackSideModifiers);
    }
    return captureWasActive;
}

// ============================================================
// 回调线程 - 单线程排队执行，避免每次 CreateThread
// ============================================================

#define SAFE_INVOKE_CALLBACK(call_expr) \
    __try {                             \
        call_expr;                      \
    } __except (EXCEPTION_EXECUTE_HANDLER) { \
        g_callbackExceptionCount.fetch_add(1); \
    }

// SEH保护的回调执行 — 必须在独立函数中，不能和 C++ 对象（如 lock_guard）共存
// 统一处理键盘和鼠标回调，替代原先的两个独立包装函数
static void SafeInvokeAny(const CallbackEvent& ev) {
    if (ev.type == CallbackEvent::AltDoubleTap) {
        KeyboardCallback callback = g_altDoubleTapCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback())
    } else if (ev.type == CallbackEvent::MouseTrigger) {
        MouseCallback callback = g_mouseCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback(ev.x, ev.y))
    } else if (ev.type == CallbackEvent::AltDoubleClick) {
        MouseCallback callback = g_altDoubleClickCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback(ev.x, ev.y))
    } else if (ev.type == CallbackEvent::GlobalHotkey) {
        KeyboardCallback callback = g_hotkeyCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback())
    } else if (ev.type == CallbackEvent::HotkeyCapture && ev.hotkeyCaptureCallback) {
        SAFE_INVOKE_CALLBACK(ev.hotkeyCaptureCallback(ev.vkCode, ev.modifiers, ev.sideModifiers))
    }
}

static DWORD WINAPI CallbackThreadProc(LPVOID) {
    while (g_callbackThreadRunning.load()) {
        DWORD result = WaitForSingleObject(g_callbackEvent, 500);
        if (!g_callbackThreadRunning.load()) break;
        if (result == WAIT_OBJECT_0) {
            std::deque<CallbackEvent> callbacks;
            {
                std::lock_guard<std::mutex> lock(g_callbackMutex);
                callbacks.swap(g_pendingCallbacks);
                if (!callbacks.empty()) {
                    if (g_callbackIdleEvent) ResetEvent(g_callbackIdleEvent);
                    g_callbacksInFlight.fetch_add(static_cast<int>(callbacks.size()));
                }
            }
            for (const auto& callback : callbacks) {
                SafeInvokeAny(callback);
                if (g_callbacksInFlight.fetch_sub(1) == 1 && g_callbackIdleEvent) {
                    SetEvent(g_callbackIdleEvent);
                }
            }
        }
    }
    if (g_callbackIdleEvent) SetEvent(g_callbackIdleEvent);
    return 0;
}


static bool EnsureCallbackThread() {
    // 快速路径：无锁检查
    if (g_callbackThreadRunning.load() && g_callbackThread) return true;

    // 慢路径：加锁 double-checked locking，防止并发创建多个回调线程
    std::lock_guard<std::mutex> lock(g_callbackStartMutex);
    if (g_callbackThreadRunning.load() && g_callbackThread) return true;

    if (g_callbackThread) {
        if (WaitForSingleObject(g_callbackThread, 0) != WAIT_OBJECT_0) {
            return false;
        }
        CloseHandle(g_callbackThread);
        g_callbackThread = NULL;
    }

    if (g_callbackEvent == NULL) {
        g_callbackEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    }
    if (g_callbackIdleEvent == NULL) {
        g_callbackIdleEvent = CreateEventW(NULL, TRUE, TRUE, NULL);
    }
    if (!g_callbackEvent || !g_callbackIdleEvent) {
        g_lastHookError = GetLastError();
        g_callbackThreadRunning = false;
        return false;
    }
    g_callbackThreadRunning = true;
    g_callbackThread = CreateThread(NULL, 0, CallbackThreadProc, NULL, 0, NULL);
    if (!g_callbackThread) {
        g_lastHookError = GetLastError();
        g_callbackThreadRunning = false;
        return false;
    }
    return true;
}

static bool StopCallbackThread() {
    {
        std::lock_guard<std::mutex> lock(g_callbackStartMutex);
        g_callbackThreadRunning = false;
    }
    if (g_callbackEvent) SetEvent(g_callbackEvent);
    if (g_callbackThread) {
        DWORD result = WaitForSingleObject(g_callbackThread, THREAD_JOIN_TIMEOUT_MS);
        if (result != WAIT_OBJECT_0) {
            g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
            return false;
        }
        CloseHandle(g_callbackThread);
        g_callbackThread = NULL;
    }
    if (g_callbackEvent) {
        CloseHandle(g_callbackEvent);
        g_callbackEvent = NULL;
    }
    if (g_callbackIdleEvent) {
        CloseHandle(g_callbackIdleEvent);
        g_callbackIdleEvent = NULL;
    }
    {
        std::lock_guard<std::mutex> lock(g_callbackMutex);
        g_pendingCallbacks.clear();
    }
    return true;
}

static void StopCallbackThreadIfIdle() {
    if (!g_mouseRunning.load() &&
        !g_keyboardRunning.load() &&
        !g_mouseThreadAlive.load() &&
        !g_keyboardThreadAlive.load()) {
        StopCallbackThread();
    }
}

static void EnqueueCallbackEvent(const CallbackEvent& event) {
    if (!EnsureCallbackThread()) {
        g_queueOverflowCount.fetch_add(1);
        return;
    }
    if (!g_callbackThreadRunning.load() || !g_callbackThread || !g_callbackEvent) {
        g_queueOverflowCount.fetch_add(1);
        return;
    }
    {
        std::lock_guard<std::mutex> lock(g_callbackMutex);
        if (g_pendingCallbacks.size() >= CALLBACK_QUEUE_LIMIT) {
            g_pendingCallbacks.pop_front();
            unsigned long long count = g_queueOverflowCount.fetch_add(1);
            if (count % 10 == 0) {
                OutputDebugStringA("[hooks] callback queue overflow, events dropped\n");
            }
        }
        g_pendingCallbacks.push_back(event);
    }
    if (g_callbackEvent) SetEvent(g_callbackEvent);
}

static void PurgeCallbackEvents(CallbackEvent::Type type) {
    std::lock_guard<std::mutex> lock(g_callbackMutex);
    g_pendingCallbacks.erase(
        std::remove_if(
            g_pendingCallbacks.begin(),
            g_pendingCallbacks.end(),
            [type](const CallbackEvent& event) { return event.type == type; }),
        g_pendingCallbacks.end());
}

static void WaitForCallbacksToDrain() {
    if (g_callbacksInFlight.load() <= 0 || !g_callbackIdleEvent) return;
    if (g_callbackThread && GetCurrentThreadId() == GetThreadId(g_callbackThread)) return;
    DWORD result = WaitForSingleObject(g_callbackIdleEvent, CALLBACK_DRAIN_TIMEOUT_MS);
    if (result != WAIT_OBJECT_0) {
        g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
    }
}

// 统一回调入队 — 替代原先的两个独立函数
static void InvokeKeyboardCallbackAsync(CallbackEvent::Type type) {
    EnqueueCallbackEvent(CallbackEvent{type, 0, 0, nullptr, 0, 0, 0});
}

static void InvokeMouseCallbackAsync(CallbackEvent::Type type, int x, int y) {
    EnqueueCallbackEvent(CallbackEvent{type, x, y, nullptr, 0, 0, 0});
}

static void InvokeHotkeyCaptureCallbackAsync(HotkeyCaptureCallback callback, int vkCode, int modifiers, int sideModifiers) {
    if (!callback) return;
    EnqueueCallbackEvent(CallbackEvent{
        CallbackEvent::HotkeyCapture,
        0,
        0,
        callback,
        vkCode,
        modifiers,
        sideModifiers,
    });
}

// ============================================================
// HookContext — 统一鼠标/键盘钩子的安装与卸载
// ============================================================

struct HookContext {
    HHOOK&             hook;
    DWORD&             threadId;
    HANDLE&            threadHandle;
    HANDLE&            readyEvent;
    HANDLE&            exitedEvent;
    std::atomic<bool>& running;
    std::atomic<bool>& installing;
    std::atomic<bool>& threadAlive;
};

// 通用钩子安装：创建事件、启动线程、等待就绪
static bool InstallHookGeneric(
    HookContext&          ctx,
    LPTHREAD_START_ROUTINE threadProc,
    MouseCallback         mouseCb,
    KeyboardCallback      kbdCb)
{
    // 防重入
    bool expected = false;
    if (!ctx.installing.compare_exchange_strong(expected, true)) {
        return ctx.hook != NULL;
    }

    if (mouseCb) g_mouseCallback = mouseCb;
    if (kbdCb)   g_altDoubleTapCallback = kbdCb;

    // 等待旧线程安全退出
    if (!WaitForHookThreadExit(ctx.threadAlive, ctx.exitedEvent, ctx.threadHandle)) {
        ctx.installing = false;
        return false;
    }

    if (ctx.running) {
        ctx.installing = false;
        return ctx.hook != NULL;
    }

    if (!EnsureCallbackThread()) {
        ctx.running = false;
        ctx.installing = false;
        return false;
    }

    // 创建就绪事件
    if (ctx.readyEvent) CloseHandle(ctx.readyEvent);
    ctx.readyEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!ctx.readyEvent) {
        g_lastHookError = GetLastError();
        ctx.running = false;
        ctx.installing = false;
        return false;
    }

    ctx.running = true;
    EnsureManualResetEvent(ctx.exitedEvent, FALSE);
    if (ctx.exitedEvent) ResetEvent(ctx.exitedEvent);

    // 关闭旧线程句柄
    if (ctx.threadHandle) {
        CloseHandle(ctx.threadHandle);
        ctx.threadHandle = NULL;
    }

    ctx.threadHandle = CreateThread(NULL, 0, threadProc, ctx.readyEvent, 0, NULL);
    if (!ctx.threadHandle) {
        g_lastHookError = GetLastError();
        ctx.running = false;
        ctx.installing = false;
        return false;
    }

    // 等待钩子安装完成（最多 2 秒）
    DWORD waitResult = WaitForSingleObject(ctx.readyEvent, 2000);
    if (waitResult == WAIT_TIMEOUT) {
        g_lastHookError = WAIT_TIMEOUT;
        ctx.running = false;
        if (ctx.threadId) PostThreadMessage(ctx.threadId, WM_QUIT, 0, 0);
        DWORD exitResult = WaitForSingleObject(ctx.threadHandle, THREAD_JOIN_TIMEOUT_MS);
        if (exitResult != WAIT_OBJECT_0) {
            g_lastHookError = exitResult == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
        }
        ctx.installing = false;
        return false;
    } else if (waitResult == WAIT_FAILED) {
        g_lastHookError = GetLastError();
        ctx.running = false;
        if (ctx.threadId) PostThreadMessage(ctx.threadId, WM_QUIT, 0, 0);
        ctx.installing = false;
        return false;
    }

    ctx.installing = false;
    return ctx.hook != NULL;
}

// 通用钩子卸载：通知线程退出、清理句柄
static void UninstallHookGeneric(HookContext& ctx) {
    ctx.running = false;
    if (ctx.threadId) {
        if (!PostThreadMessage(ctx.threadId, WM_QUIT, 0, 0)) {
            g_lastHookError = GetLastError();
        }
    }
    if (ctx.threadHandle) {
        DWORD result = WaitForSingleObject(ctx.threadHandle, THREAD_JOIN_TIMEOUT_MS);
        if (result == WAIT_OBJECT_0) {
            CloseHandle(ctx.threadHandle);
            ctx.threadHandle = NULL;
        } else {
            g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
            return;
        }
    }
    if (ctx.readyEvent) {
        CloseHandle(ctx.readyEvent);
        ctx.readyEvent = NULL;
    }
    if (ctx.exitedEvent) {
        CloseHandle(ctx.exitedEvent);
        ctx.exitedEvent = NULL;
    }
}

// ============================================================
// 工具函数
// ============================================================

static std::string ToLowerCopy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

static std::string GetProcessNameForWindow(HWND hwnd) {
    if (!hwnd) return "";

    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (!pid) return "";

    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return "";

    char imagePath[MAX_PATH] = {0};
    DWORD size = MAX_PATH;
    std::string processName;

    if (QueryFullProcessImageNameA(process, 0, imagePath, &size) && size > 0) {
        processName.assign(imagePath, size);
        size_t slashPos = processName.find_last_of("\\/");
        if (slashPos != std::string::npos) {
            processName = processName.substr(slashPos + 1);
        }
    }

    CloseHandle(process);
    return ToLowerCopy(processName);
}

static std::string GetHookDebugLogPath() {
    static std::string path;
    if (!path.empty()) return path;

    HMODULE module = NULL;
    char modulePath[MAX_PATH] = {0};
    if (GetModuleHandleExA(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCSTR>(&GetHookDebugLogPath),
            &module) &&
        GetModuleFileNameA(module, modulePath, MAX_PATH) > 0) {
        path = modulePath;
        size_t slashPos = path.find_last_of("\\/");
        if (slashPos != std::string::npos) {
            path = path.substr(0, slashPos + 1);
        } else {
            path.clear();
        }
    }
    path += "hook_debug.log";
    return path;
}

static std::string WindowSummary(HWND hwnd) {
    if (!hwnd) return "hwnd=0";

    HWND root = GetAncestor(hwnd, GA_ROOT);
    if (root) hwnd = root;

    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);

    char className[128] = {0};
    GetClassNameA(hwnd, className, sizeof(className));

    char title[192] = {0};
    if (pid != GetCurrentProcessId()) {
        GetWindowTextA(hwnd, title, sizeof(title));
    } else {
        lstrcpynA(title, "current_process_window", sizeof(title));
    }

    std::ostringstream oss;
    oss << "hwnd=0x" << std::hex << reinterpret_cast<uintptr_t>(hwnd) << std::dec
        << " pid=" << pid
        << " process=" << GetProcessNameForWindow(hwnd)
        << " class=" << className
        << " title=\"" << title << "\"";
    return oss.str();
}

static void WriteMiddleMouseEvent(const MouseDebugEvent& ev) {
    std::ostringstream oss;
    oss << ev.time.wYear << "-"
        << (ev.time.wMonth < 10 ? "0" : "") << ev.time.wMonth << "-"
        << (ev.time.wDay < 10 ? "0" : "") << ev.time.wDay << " "
        << (ev.time.wHour < 10 ? "0" : "") << ev.time.wHour << ":"
        << (ev.time.wMinute < 10 ? "0" : "") << ev.time.wMinute << ":"
        << (ev.time.wSecond < 10 ? "0" : "") << ev.time.wSecond << "."
        << ev.time.wMilliseconds
        << " msg=" << (ev.wParam == WM_MBUTTONDOWN ? "WM_MBUTTONDOWN" : "WM_MBUTTONUP")
        << " decision=" << ev.decision
        << " hook_pt=(" << ev.hookPoint.x << "," << ev.hookPoint.y << ")"
        << " cursor=(" << ev.cursorPoint.x << "," << ev.cursorPoint.y << ")"
        << " flags=0x" << std::hex << ev.flags
        << " mouseData=0x" << ev.mouseData
        << " extra=0x" << ev.extraInfo
        << " mb_async=0x" << static_cast<unsigned short>(ev.mbState)
        << std::dec
        << " blocked=" << (ev.blocked ? 1 : 0)
        << " paused=" << (ev.paused ? 1 : 0)
        << " fg={" << WindowSummary(ev.foreground) << "}"
        << " cursor_hwnd={" << WindowSummary(ev.cursorWindow) << "}"
        << "\n";

    std::ofstream out(GetHookDebugLogPath(), std::ios::app);
    if (out) out << oss.str();
}

static DWORD WINAPI DebugLogThreadProc(LPVOID) {
    while (g_debugLogThreadRunning.load()) {
        DWORD result = WaitForSingleObject(g_debugLogEvent, 500);
        if (!g_debugLogThreadRunning.load()) break;
        if (result != WAIT_OBJECT_0) continue;

        std::vector<MouseDebugEvent> events;
        {
            std::lock_guard<std::mutex> lock(g_debugLogMutex);
            events.swap(g_pendingDebugEvents);
        }
        for (const auto& ev : events) {
            WriteMiddleMouseEvent(ev);
        }
    }
    return 0;
}

static void EnsureDebugLogThread() {
    if (g_debugLogThreadRunning.load() && g_debugLogThread) return;
    std::lock_guard<std::mutex> startLock(g_debugLogStartMutex);
    if (g_debugLogThreadRunning.load() && g_debugLogThread) return;
    if (g_debugLogThread) {
        if (WaitForSingleObject(g_debugLogThread, 0) != WAIT_OBJECT_0) return;
        CloseHandle(g_debugLogThread);
        g_debugLogThread = NULL;
    }
    if (g_debugLogEvent == NULL) {
        g_debugLogEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    }
    if (!g_debugLogEvent) return;
    g_debugLogThreadRunning = true;
    g_debugLogThread = CreateThread(NULL, 0, DebugLogThreadProc, NULL, 0, NULL);
    if (!g_debugLogThread) {
        g_debugLogThreadRunning = false;
    }
}

static void StopDebugLogThread() {
    g_debugLogThreadRunning = false;
    if (g_debugLogEvent) SetEvent(g_debugLogEvent);
    if (g_debugLogThread) {
        DWORD result = WaitForSingleObject(g_debugLogThread, THREAD_JOIN_TIMEOUT_MS);
        if (result != WAIT_OBJECT_0) {
            g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
            return;
        }
        CloseHandle(g_debugLogThread);
        g_debugLogThread = NULL;
    }
    if (g_debugLogEvent) {
        CloseHandle(g_debugLogEvent);
        g_debugLogEvent = NULL;
    }
}

static bool HookDebugLoggingEnabled() {
    static bool enabled = []() {
        char value[16] = {0};
        DWORD length = GetEnvironmentVariableA(
            "QUICKLAUNCHER_HOOK_DEBUG",
            value,
            static_cast<DWORD>(sizeof(value)));
        if (length == 0 || length >= sizeof(value)) return false;
        std::string normalized = ToLowerCopy(value);
        return normalized == "1" ||
               normalized == "true" ||
               normalized == "yes" ||
               normalized == "on";
    }();
    return enabled;
}

static void LogMiddleMouseEvent(const char* phase, WPARAM wParam, const MSLLHOOKSTRUCT* mouse, const char* decision) {
    (void)phase;
    if (!mouse || !HookDebugLoggingEnabled()) return;

    int eventButton = 0;
    if (wParam == WM_LBUTTONDOWN || wParam == WM_LBUTTONUP) eventButton = 1;
    else if (wParam == WM_RBUTTONDOWN || wParam == WM_RBUTTONUP) eventButton = 2;
    else if (wParam == WM_MBUTTONDOWN || wParam == WM_MBUTTONUP) eventButton = 4;
    else if (wParam == WM_XBUTTONDOWN || wParam == WM_XBUTTONUP) {
        eventButton = HIWORD(mouse->mouseData) == XBUTTON1 ? 8 : 16;
    }

    bool configuredButton = false;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        configuredButton = eventButton == g_normalTriggerButton || eventButton == g_specialTriggerButton;
    }
    bool diagnosticDecision = decision && (
        strstr(decision, "raw_input") != nullptr ||
        strstr(decision, "timeout") != nullptr ||
        strstr(decision, "stale") != nullptr);
    if (!configuredButton && !diagnosticDecision) return;

    MouseDebugEvent ev = {};
    GetLocalTime(&ev.time);
    ev.wParam = wParam;
    ev.hookPoint = mouse->pt;
    ev.cursorPoint = mouse->pt;
    GetCursorPos(&ev.cursorPoint);
    ev.flags = mouse->flags;
    ev.mouseData = mouse->mouseData;
    ev.extraInfo = mouse->dwExtraInfo;
    ev.mbState = GetAsyncKeyState(VK_MBUTTON);
    ev.blocked = g_blockedDown.load();
    ev.paused = g_mousePaused.load();
    ev.foreground = GetForegroundWindow();
    ev.cursorWindow = WindowFromPoint(ev.cursorPoint);
    lstrcpynA(ev.decision, decision ? decision : "", sizeof(ev.decision));

    EnsureDebugLogThread();
    {
        std::lock_guard<std::mutex> lock(g_debugLogMutex);
        if (g_pendingDebugEvents.size() > 512) {
            g_pendingDebugEvents.erase(g_pendingDebugEvents.begin(), g_pendingDebugEvents.begin() + 256);
        }
        g_pendingDebugEvents.push_back(ev);
    }
    if (g_debugLogEvent) SetEvent(g_debugLogEvent);
}

static HWND GetTargetWindowForSpecialAppCheck() {
    POINT point;
    if (GetCursorPos(&point)) {
        HWND hwnd = WindowFromPoint(point);
        if (hwnd) {
            hwnd = GetAncestor(hwnd, GA_ROOT);
            if (hwnd) return hwnd;
        }
        // UIPI: WindowFromPoint 可能对高权限窗口返回 NULL
        // 跳过，使用前台窗口作为更可靠的回退
    }

    HWND hwnd = GetForegroundWindow();
    if (hwnd) {
        hwnd = GetAncestor(hwnd, GA_ROOT);
        if (hwnd) return hwnd;
    }

    return NULL;
}

// 检查当前目标窗口是否为特殊应用
static bool IsSpecialApp() {
    std::vector<std::string> appsSnapshot;
    {
        std::lock_guard<std::mutex> lock(g_specialAppsMutex);
        if (g_specialApps.empty()) return false;
        appsSnapshot = g_specialApps;
    }

    HWND hwnd = GetTargetWindowForSpecialAppCheck();
    if (!hwnd) return false;

    std::string processLower = GetProcessNameForWindow(hwnd);

    char className[256] = {0};
    GetClassNameA(hwnd, className, sizeof(className));
    std::string classLower = ToLowerCopy(className);

    char windowTitle[256] = {0};
    GetWindowTextA(hwnd, windowTitle, sizeof(windowTitle));
    std::string titleLower = ToLowerCopy(windowTitle);

    for (const auto& app : appsSnapshot) {
        std::string appLower = ToLowerCopy(app);
        if (appLower.empty()) continue;

        if ((!processLower.empty() && processLower.find(appLower) != std::string::npos) ||
            classLower.find(appLower) != std::string::npos ||
            titleLower.find(appLower) != std::string::npos) {
            return true;
        }
    }
    return false;
}

// 检查所有指定的键盘按键是否都按下
static bool CheckKeysPressed(const std::vector<int>& vkCodes) {
    if (vkCodes.empty()) {
        return false;
    }
    for (int vk : vkCodes) {
        if (!(GetAsyncKeyState(vk) & 0x8000)) {
            return false;
        }
    }
    return true;
}

static int MouseButtonIndex(int button) {
    switch (button) {
        case 1: return 0;
        case 2: return 1;
        case 4: return 2;
        case 8: return 3;
        case 16: return 4;
        default: return -1;
    }
}

static int CurrentMouseModifiers() {
    int currentMod = 0;
    if (IsCtrlPressedNow()) currentMod |= HOTKEY_MOD_CTRL;
    if (IsAltPressedNow()) currentMod |= HOTKEY_MOD_ALT;
    if (GetAsyncKeyState(VK_SHIFT) & 0x8000) currentMod |= HOTKEY_MOD_SHIFT;
    if ((GetAsyncKeyState(VK_LWIN) & 0x8000) || (GetAsyncKeyState(VK_RWIN) & 0x8000)) {
        currentMod |= HOTKEY_MOD_WIN;
    }
    return currentMod;
}

static bool ShouldTriggerMouseButton(
    int currentButton,
    int* targetButtonOut = nullptr,
    int* currentModifiersOut = nullptr,
    int* targetModifiersOut = nullptr,
    bool* specialOut = nullptr)
{
    int normalBtn, normalMod, normalMode, specialBtn, specialMod, specialMode;
    std::vector<int> normalKeys, specialKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        normalMode = g_normalTriggerMode;
        normalBtn = g_normalTriggerButton;
        normalKeys = g_normalTriggerKeys;
        normalMod = g_normalTriggerModifiers;
        specialMode = g_specialTriggerMode;
        specialBtn = g_specialTriggerButton;
        specialKeys = g_specialTriggerKeys;
        specialMod = g_specialTriggerModifiers;
    }

    int currentMod = CurrentMouseModifiers();
    bool isSpecial = IsSpecialApp();
    int targetMode = isSpecial ? specialMode : normalMode;
    int targetBtn = isSpecial ? specialBtn : normalBtn;
    int targetMod = isSpecial ? specialMod : normalMod;
    const std::vector<int>& targetKeys = isSpecial ? specialKeys : normalKeys;

    if (targetButtonOut) *targetButtonOut = targetBtn;
    if (currentModifiersOut) *currentModifiersOut = currentMod;
    if (targetModifiersOut) *targetModifiersOut = targetMod;
    if (specialOut) *specialOut = isSpecial;

    if (targetMode != 0 && targetMode != 2) {
        return false;
    }
    if (currentButton != targetBtn || currentMod != targetMod) {
        return false;
    }
    return targetMode != 2 || CheckKeysPressed(targetKeys);
}

static int RawKeyboardModifiers() {
    int modifiers = 0;
    if (g_rawKeyboardPressed[VK_LMENU] || g_rawKeyboardPressed[VK_RMENU] ||
        g_rawKeyboardPressed[VK_MENU]) modifiers |= HOTKEY_MOD_ALT;
    if (g_rawKeyboardPressed[VK_LCONTROL] || g_rawKeyboardPressed[VK_RCONTROL] ||
        g_rawKeyboardPressed[VK_CONTROL]) modifiers |= HOTKEY_MOD_CTRL;
    if (g_rawKeyboardPressed[VK_LSHIFT] || g_rawKeyboardPressed[VK_RSHIFT] ||
        g_rawKeyboardPressed[VK_SHIFT]) modifiers |= HOTKEY_MOD_SHIFT;
    if (g_rawKeyboardPressed[VK_LWIN] || g_rawKeyboardPressed[VK_RWIN]) modifiers |= HOTKEY_MOD_WIN;
    return modifiers;
}

static bool ShouldTriggerRawKeyboard(int vk) {
    int normalMode, specialMode, normalMod, specialMod;
    std::vector<int> normalKeys, specialKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        normalMode = g_normalTriggerMode;
        specialMode = g_specialTriggerMode;
        if (normalMode != 1 && specialMode != 1) return false;
        normalKeys = g_normalTriggerKeys;
        normalMod = g_normalTriggerModifiers;
        specialKeys = g_specialTriggerKeys;
        specialMod = g_specialTriggerModifiers;
    }

    bool isSpecial = IsSpecialApp();
    int targetMode = isSpecial ? specialMode : normalMode;
    const std::vector<int>& targetKeys = isSpecial ? specialKeys : normalKeys;
    int targetModifiers = isSpecial ? specialMod : normalMod;
    if (targetMode != 1 || targetKeys.empty() || RawKeyboardModifiers() != targetModifiers) {
        return false;
    }

    bool currentIsTarget = false;
    for (int targetVk : targetKeys) {
        if (targetVk == vk) currentIsTarget = true;
        if (targetVk < 0 || targetVk >= 256 || !g_rawKeyboardPressed[targetVk]) return false;
    }
    return currentIsTarget;
}

static void InvokeRawInputFallback(int button, int buttonIndex) {
    if (g_mousePaused.load() || !g_mouseCallback.load()) return;

    // Raw Input is independent from WH_MOUSE_LL. An unmatched physical event
    // means the low-level hook was skipped or silently removed by Windows.
    g_lowLevelMouseHealthy = false;
    if (!ShouldTriggerMouseButton(button)) return;

    POINT point = {};
    if (!GetCursorPos(&point)) return;
    MSLLHOOKSTRUCT syntheticEvent = {};
    syntheticEvent.pt = point;
    LogMiddleMouseEvent("raw_input", WM_MBUTTONDOWN, &syntheticEvent, "raw_input_fallback");
    g_rawFallbackTriggerCount.fetch_add(1);
    g_lastRawFallbackTick[buttonIndex] = GetTickCount64();
    InvokeMouseCallbackAsync(CallbackEvent::MouseTrigger, point.x, point.y);
}

static void ReconcileRawInputButton(int buttonIndex) {
    if (buttonIndex < 0 || buttonIndex >= 5) return;

    int buttonValues[5] = {1, 2, 4, 8, 16};
    unsigned long long lowLevelCount = g_lowLevelPhysicalDownCount[buttonIndex].load();
    while (g_pendingRawDownCount[buttonIndex] > 0 &&
           g_rawConsumedLowLevelCount[buttonIndex] < lowLevelCount) {
        --g_pendingRawDownCount[buttonIndex];
        ++g_rawConsumedLowLevelCount[buttonIndex];
    }

    while (g_pendingRawDownCount[buttonIndex] > 0) {
        --g_pendingRawDownCount[buttonIndex];
        InvokeRawInputFallback(buttonValues[buttonIndex], buttonIndex);
    }
}

static void QueueRawInputDown(int button) {
    if (g_mousePaused.load()) return;
    int buttonIndex = MouseButtonIndex(button);
    if (buttonIndex < 0) return;

    g_rawMouseEventCount.fetch_add(1);
    ++g_pendingRawDownCount[buttonIndex];

    unsigned long long lowLevelCount = g_lowLevelPhysicalDownCount[buttonIndex].load();
    if (g_rawConsumedLowLevelCount[buttonIndex] < lowLevelCount) {
        ReconcileRawInputButton(buttonIndex);
        return;
    }

    if (g_rawInputWindow) {
        SetTimer(
            g_rawInputWindow,
            RAW_FALLBACK_TIMER_BASE + static_cast<UINT_PTR>(buttonIndex),
            RAW_FALLBACK_RECONCILE_MS,
            NULL);
    }
}

static void ReconcileRawKeyboardEvents() {
    unsigned long long lowLevelCount = g_lowLevelPhysicalKeyboardCount.load();
    while (!g_pendingRawKeyboardEvents.empty() &&
           g_rawConsumedLowLevelKeyboardCount < lowLevelCount) {
        g_pendingRawKeyboardEvents.pop_front();
        ++g_rawConsumedLowLevelKeyboardCount;
    }

    while (!g_pendingRawKeyboardEvents.empty()) {
        PendingRawKeyboardEvent event = g_pendingRawKeyboardEvents.front();
        g_pendingRawKeyboardEvents.pop_front();
        g_lowLevelKeyboardHealthy = false;
        if (!event.down || !event.shouldTrigger || g_mousePaused.load()) continue;

        if (!g_mouseCallback.load()) continue;
        POINT point = {};
        if (!GetCursorPos(&point)) continue;
        g_lastRawKeyboardFallbackVk = event.vk;
        g_lastRawKeyboardFallbackTick = GetTickCount64();
        InvokeMouseCallbackAsync(CallbackEvent::MouseTrigger, point.x, point.y);
    }
}

static void HandleRawMouseInput(HRAWINPUT inputHandle) {
    RAWINPUT input = {};
    UINT size = sizeof(input);
    if (GetRawInputData(inputHandle, RID_INPUT, &input, &size, sizeof(RAWINPUTHEADER)) != size) {
        return;
    }
    if (input.header.dwType == RIM_TYPEMOUSE) {
        USHORT flags = input.data.mouse.usButtonFlags;
        if (flags & RI_MOUSE_LEFT_BUTTON_DOWN) QueueRawInputDown(1);
        if (flags & RI_MOUSE_RIGHT_BUTTON_DOWN) QueueRawInputDown(2);
        if (flags & RI_MOUSE_MIDDLE_BUTTON_DOWN) QueueRawInputDown(4);
        if (flags & RI_MOUSE_BUTTON_4_DOWN) QueueRawInputDown(8);
        if (flags & RI_MOUSE_BUTTON_5_DOWN) QueueRawInputDown(16);
        return;
    }

    if (input.header.dwType == RIM_TYPEKEYBOARD && input.header.hDevice != NULL) {
        int vk = static_cast<int>(input.data.keyboard.VKey);
        if (vk <= 0 || vk >= 256 || vk == 255) return;
        bool down = (input.data.keyboard.Flags & RI_KEY_BREAK) == 0;
        g_rawKeyboardEventCount.fetch_add(1);
        g_rawKeyboardPressed[vk] = down;
        bool shouldTrigger = down && ShouldTriggerRawKeyboard(vk);
        g_pendingRawKeyboardEvents.push_back(PendingRawKeyboardEvent{vk, down, shouldTrigger});

        unsigned long long lowLevelCount = g_lowLevelPhysicalKeyboardCount.load();
        if (g_rawConsumedLowLevelKeyboardCount < lowLevelCount) {
            ReconcileRawKeyboardEvents();
        } else if (g_rawInputWindow) {
            SetTimer(
                g_rawInputWindow,
                RAW_KEYBOARD_RECONCILE_TIMER,
                RAW_FALLBACK_RECONCILE_MS,
                NULL);
        }
    }
}

static LRESULT CALLBACK RawInputWindowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    if (message == WM_INPUT) {
        HandleRawMouseInput(reinterpret_cast<HRAWINPUT>(lParam));
        return DefWindowProcW(hwnd, message, wParam, lParam);
    }
    if (message == WM_TIMER &&
        wParam >= RAW_FALLBACK_TIMER_BASE &&
        wParam < RAW_FALLBACK_TIMER_BASE + 5) {
        KillTimer(hwnd, static_cast<UINT_PTR>(wParam));
        ReconcileRawInputButton(static_cast<int>(wParam - RAW_FALLBACK_TIMER_BASE));
        return 0;
    }
    if (message == WM_TIMER && wParam == RAW_KEYBOARD_RECONCILE_TIMER) {
        KillTimer(hwnd, RAW_KEYBOARD_RECONCILE_TIMER);
        ReconcileRawKeyboardEvents();
        return 0;
    }
    return DefWindowProcW(hwnd, message, wParam, lParam);
}

static bool CreateRawInputWindow() {
    static const wchar_t* className = L"QuickLauncherRawInputSinkV1";
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = RawInputWindowProc;
    wc.hInstance = GetCurrentDllModule();
    wc.lpszClassName = className;

    if (!RegisterClassExW(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        g_lastHookError = GetLastError();
        return false;
    }

    g_rawInputWindow = CreateWindowExW(
        0, className, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, NULL, wc.hInstance, NULL);
    if (!g_rawInputWindow) {
        g_lastHookError = GetLastError();
        return false;
    }

    RAWINPUTDEVICE devices[2] = {};
    devices[0].usUsagePage = 0x01;
    devices[0].usUsage = 0x02;
    devices[0].dwFlags = RIDEV_INPUTSINK;
    devices[0].hwndTarget = g_rawInputWindow;
    devices[1].usUsagePage = 0x01;
    devices[1].usUsage = 0x06;
    devices[1].dwFlags = RIDEV_INPUTSINK;
    devices[1].hwndTarget = g_rawInputWindow;
    if (!RegisterRawInputDevices(devices, 2, sizeof(RAWINPUTDEVICE))) {
        g_lastHookError = GetLastError();
        DestroyWindow(g_rawInputWindow);
        g_rawInputWindow = NULL;
        return false;
    }

    g_rawInputActive = true;
    return true;
}

static void DestroyRawInputWindow() {
    if (g_rawInputActive.load()) {
        RAWINPUTDEVICE devices[2] = {};
        devices[0].usUsagePage = 0x01;
        devices[0].usUsage = 0x02;
        devices[0].dwFlags = RIDEV_REMOVE;
        devices[1].usUsagePage = 0x01;
        devices[1].usUsage = 0x06;
        devices[1].dwFlags = RIDEV_REMOVE;
        RegisterRawInputDevices(devices, 2, sizeof(RAWINPUTDEVICE));
    }
    g_rawInputActive = false;
    if (g_rawInputWindow) {
        for (int i = 0; i < 5; ++i) {
            KillTimer(g_rawInputWindow, RAW_FALLBACK_TIMER_BASE + static_cast<UINT_PTR>(i));
            g_pendingRawDownCount[i] = 0;
        }
        KillTimer(g_rawInputWindow, RAW_KEYBOARD_RECONCILE_TIMER);
        g_pendingRawKeyboardEvents.clear();
        DestroyWindow(g_rawInputWindow);
        g_rawInputWindow = NULL;
    }
}

// ============================================================
// 鼠标钩子回调
// ============================================================

static void CaptureMouseHookEvent(WPARAM wParam, const MSLLHOOKSTRUCT* mouse) {
    if (!mouse || !g_inputCaptureActive.load()) return;

    HookInputEvent eventData = {};
    eventData.x = mouse->pt.x;
    eventData.y = mouse->pt.y;
    eventData.extraInfo = static_cast<unsigned long long>(mouse->dwExtraInfo);
    eventData.flags = HOOK_INPUT_FLAG_ABSOLUTE;
    if (mouse->flags & LLMHF_INJECTED) eventData.flags |= HOOK_INPUT_FLAG_INJECTED;
    if (mouse->flags & LLMHF_LOWER_IL_INJECTED) eventData.flags |= HOOK_INPUT_FLAG_LOWER_IL_INJECTED;
    if (IsOwnMacroInput(mouse->dwExtraInfo)) eventData.flags |= HOOK_INPUT_FLAG_OWN_PLAYBACK;

    switch (wParam) {
        case WM_MOUSEMOVE:
            eventData.type = HOOK_INPUT_MOUSE_MOVE;
            break;
        case WM_LBUTTONDOWN:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_DOWN;
            eventData.data = 1;
            break;
        case WM_LBUTTONUP:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_UP;
            eventData.data = 1;
            break;
        case WM_RBUTTONDOWN:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_DOWN;
            eventData.data = 2;
            break;
        case WM_RBUTTONUP:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_UP;
            eventData.data = 2;
            break;
        case WM_MBUTTONDOWN:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_DOWN;
            eventData.data = 4;
            break;
        case WM_MBUTTONUP:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_UP;
            eventData.data = 4;
            break;
        case WM_XBUTTONDOWN:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_DOWN;
            eventData.data = HIWORD(mouse->mouseData) == XBUTTON1 ? 8 : 16;
            break;
        case WM_XBUTTONUP:
            eventData.type = HOOK_INPUT_MOUSE_BUTTON_UP;
            eventData.data = HIWORD(mouse->mouseData) == XBUTTON1 ? 8 : 16;
            break;
        case WM_MOUSEWHEEL:
            eventData.type = HOOK_INPUT_MOUSE_WHEEL;
            eventData.data = static_cast<SHORT>(HIWORD(mouse->mouseData));
            break;
        case WM_MOUSEHWHEEL:
            eventData.type = HOOK_INPUT_MOUSE_HWHEEL;
            eventData.data = static_cast<SHORT>(HIWORD(mouse->mouseData));
            break;
        default:
            return;
    }
    QueueCapturedInput(eventData);
}

LRESULT CALLBACK MouseHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);

    MSLLHOOKSTRUCT* pMouse = (MSLLHOOKSTRUCT*)lParam;
    double now = GetTime();
    g_lowLevelMouseEventCount.fetch_add(1);
    g_mouseLastEventTick = GetTickCount64();
    g_lowLevelMouseHealthy = true;
    CaptureMouseHookEvent(wParam, pMouse);

    if (pMouse->flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED)) {
        g_injectedMouseIgnoredCount.fetch_add(1);
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    // Timeout protection - auto-reset if blocked for too long
    if (g_blockedDown && (now - g_lastBlockTime) > BLOCKED_STATE_TIMEOUT) {
        LogMiddleMouseEvent("mouse", wParam, pMouse, "auto_reset_blocked_timeout");
        g_blockedDown = false;
        g_blockedButton = 0;
    }

    // Alt+左键双击检测
    if (wParam == WM_LBUTTONDOWN && g_altHeld) {
        double interval = now - g_altLClickLastTime;
        if (interval < ALT_LCLICK_DOUBLE_INTERVAL && g_altLClickLastTime > 0) {
            if ((now - g_altLClickLastTrigger) > ALT_LCLICK_COOLDOWN) {
                g_altLClickLastTrigger = now;
                MouseCallback callback = g_altDoubleClickCallback.load();
                if (callback) {
                    InvokeMouseCallbackAsync(CallbackEvent::AltDoubleClick, pMouse->pt.x, pMouse->pt.y);
                }
            }
            g_altLClickLastTime = 0.0;
        } else {
            g_altLClickLastTime = now;
        }
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    // 检测按键类型
    int currentButton = 0;
    WPARAM downMsg = 0, upMsg = 0;
    if (wParam == WM_LBUTTONDOWN || wParam == WM_LBUTTONUP) {
        currentButton = 1; downMsg = WM_LBUTTONDOWN; upMsg = WM_LBUTTONUP;
    } else if (wParam == WM_RBUTTONDOWN || wParam == WM_RBUTTONUP) {
        currentButton = 2; downMsg = WM_RBUTTONDOWN; upMsg = WM_RBUTTONUP;
    } else if (wParam == WM_MBUTTONDOWN || wParam == WM_MBUTTONUP) {
        currentButton = 4; downMsg = WM_MBUTTONDOWN; upMsg = WM_MBUTTONUP;
    } else if (wParam == WM_XBUTTONDOWN || wParam == WM_XBUTTONUP) {
        int xbutton = HIWORD(pMouse->mouseData);
        currentButton = (xbutton == XBUTTON1) ? 8 : 16;
        downMsg = WM_XBUTTONDOWN; upMsg = WM_XBUTTONUP;
    } else {
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    if (g_mousePaused) {
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    if (wParam == downMsg) {
        int buttonIndex = MouseButtonIndex(currentButton);
        if (buttonIndex >= 0) {
            g_lowLevelPhysicalDownCount[buttonIndex].fetch_add(1);
        }

        // 强制释放过期的 blocked 状态，防止高权限窗口场景下的 2 秒黑名单窗口
        if (g_blockedDown && (now - g_lastBlockTime) > 0.15) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "force_release_stale_blocked");
            g_blockedDown = false;
            g_blockedButton = 0;
        }

        if (now - g_lastBlockTime < MIN_BLOCK_INTERVAL) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_debounce");
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        int targetBtn = 0;
        int currentMod = 0;
        int targetMod = 0;
        bool isSpecial = false;
        bool shouldTrigger = ShouldTriggerMouseButton(
            currentButton, &targetBtn, &currentMod, &targetMod, &isSpecial);

        if (!shouldTrigger) {
            char diagBuf[128];
            snprintf(diagBuf, sizeof(diagBuf), "pass_no_match btn=%d->%d mod=%d->%d special=%d",
                     currentButton, targetBtn, currentMod, targetMod, isSpecial ? 1 : 0);
            LogMiddleMouseEvent("mouse", wParam, pMouse, diagBuf);
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        MouseCallback callback = g_mouseCallback.load();
        if (callback) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "trigger_callback_block_down");
            bool rawAlreadyTriggered = buttonIndex >= 0 &&
                (GetTickCount64() - g_lastRawFallbackTick[buttonIndex].load()) <=
                    RAW_FALLBACK_LATE_LL_WINDOW_MS;
            if (!rawAlreadyTriggered) {
                InvokeMouseCallbackAsync(CallbackEvent::MouseTrigger, pMouse->pt.x, pMouse->pt.y);
            } else {
                LogMiddleMouseEvent("mouse", wParam, pMouse, "suppress_late_ll_after_raw_input");
            }
            g_blockedDown = true;
            g_blockedButton = currentButton;
            g_lastBlockTime = now;
            return 1;
        }
        LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_no_callback");
    } else if (wParam == upMsg) {
        if (g_blockedDown && g_blockedButton.load() == currentButton) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "block_matching_up");
            g_blockedDown = false;
            g_blockedButton = 0;
            return 1;
        }
        LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_unmatched_up");
    }

    return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
}

DWORD WINAPI MouseHookThread(LPVOID param) {
    g_mouseThreadAlive = true;
    if (g_mouseExitedEvent) ResetEvent(g_mouseExitedEvent);
    HANDLE readyEvent = (HANDLE)param;
    g_mouseThreadId = GetCurrentThreadId();
    for (int i = 0; i < 5; ++i) {
        g_lowLevelPhysicalDownCount[i] = 0;
        g_rawConsumedLowLevelCount[i] = 0;
        g_pendingRawDownCount[i] = 0;
        g_lastRawFallbackTick[i] = 0;
    }
    g_rawConsumedLowLevelKeyboardCount = g_lowLevelPhysicalKeyboardCount.load();
    g_pendingRawKeyboardEvents.clear();
    std::fill(g_rawKeyboardPressed, g_rawKeyboardPressed + 256, false);
    g_lastRawKeyboardFallbackTick = 0;
    g_lastRawKeyboardFallbackVk = 0;
    bool rawInputReady = CreateRawInputWindow();
    g_mouseHook = SetWindowsHookEx(WH_MOUSE_LL, MouseHookProc, GetCurrentDllModule(), 0);

    if (!g_mouseHook) {
        g_lastHookError = GetLastError();
        g_lowLevelMouseHealthy = false;
        if (!rawInputReady) {
            g_mouseRunning = false;
            g_mouseThreadId = 0;
            g_mouseThreadAlive = false;
            if (readyEvent) SetEvent(readyEvent);
            if (g_mouseExitedEvent) SetEvent(g_mouseExitedEvent);
            return 1;
        }
    } else {
        g_lowLevelMouseHealthy = true;
        g_lastHookError = ERROR_SUCCESS;
    }

    // 通知主线程钩子安装成功
    if (readyEvent) SetEvent(readyEvent);

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_mouseHook) {
        UnhookWindowsHookEx(g_mouseHook);
        g_mouseHook = NULL;
    }
    DestroyRawInputWindow();
    g_blockedDown = false;
    g_blockedButton = 0;
    g_lowLevelMouseHealthy = false;
    g_mouseThreadId = 0;
    g_mouseRunning = false;
    g_mouseThreadAlive = false;
    if (g_mouseExitedEvent) SetEvent(g_mouseExitedEvent);
    return 0;
}

// ============================================================
// 键盘钩子回调
// ============================================================

static void CaptureKeyboardHookEvent(
    WPARAM wParam,
    const KBDLLHOOKSTRUCT* keyboard,
    bool wasPressed)
{
    if (!keyboard || !g_inputCaptureActive.load()) return;
    bool isDown = wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN;
    bool isUp = wParam == WM_KEYUP || wParam == WM_SYSKEYUP;
    if (!isDown && !isUp) return;

    HookInputEvent eventData = {};
    eventData.type = isDown ? HOOK_INPUT_KEY_DOWN : HOOK_INPUT_KEY_UP;
    eventData.vkCode = keyboard->vkCode;
    eventData.scanCode = keyboard->scanCode;
    eventData.extraInfo = static_cast<unsigned long long>(keyboard->dwExtraInfo);
    if (keyboard->flags & LLKHF_EXTENDED) eventData.flags |= HOOK_INPUT_FLAG_EXTENDED;
    if (keyboard->flags & LLKHF_INJECTED) eventData.flags |= HOOK_INPUT_FLAG_INJECTED;
    if (keyboard->flags & LLKHF_LOWER_IL_INJECTED) {
        eventData.flags |= HOOK_INPUT_FLAG_LOWER_IL_INJECTED;
    }
    if (IsOwnMacroInput(keyboard->dwExtraInfo)) eventData.flags |= HOOK_INPUT_FLAG_OWN_PLAYBACK;
    if (wParam == WM_SYSKEYDOWN || wParam == WM_SYSKEYUP) {
        eventData.flags |= HOOK_INPUT_FLAG_SYSTEM_KEY;
    }
    if (isDown && wasPressed) eventData.flags |= HOOK_INPUT_FLAG_REPEAT;
    QueueCapturedInput(eventData);
}

LRESULT CALLBACK KeyboardHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT* pKbd = (KBDLLHOOKSTRUCT*)lParam;
    int vk = pKbd->vkCode;
    bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
    bool isUp = (wParam == WM_KEYUP || wParam == WM_SYSKEYUP);
    bool wasPressed = vk >= 0 && vk < 256 ? g_keyboardPressed[vk] : false;
    double now = GetTime();
    g_lowLevelKeyboardEventCount.fetch_add(1);
    g_keyboardLastEventTick = GetTickCount64();
    g_lowLevelKeyboardHealthy = true;
    CaptureKeyboardHookEvent(wParam, pKbd, wasPressed);

    if (pKbd->flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED)) {
        g_injectedKeyboardIgnoredCount.fetch_add(1);
        return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
    }
    g_lowLevelPhysicalKeyboardCount.fetch_add(1);

    // 快捷键录制模式拥有最高优先级：录制期间所有键盘事件都不继续传给系统或其它程序。
    if (HandleHotkeyCapture(vk, wParam, pKbd)) {
        return 1;
    }

    bool isAlt = (vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU);
    bool isCtrl = (vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL);
    if (vk >= 0 && vk < 256) {
        if (isDown) g_keyboardPressed[vk] = true;
        if (isUp) g_keyboardPressed[vk] = false;
    }

    // 物理键状态同步 — 修正 g_altHeld 与物理键状态的不一致
    // 当收到非 Alt 键事件时，检查物理 Alt 是否已释放
    if (!isAlt && g_altHeld && !IsAltPressedNow()) {
        g_altHeld = false;
        g_altTapCount = 0;
    }

    if (isDown) {
        if (isAlt) {
            if (!g_altHeld) {
                g_altHeld = true;
                g_altPressTime = now;
                g_otherKeyPressed = false;
            }
        } else if (isCtrl) {
            g_ctrlHeld = true;
        } else {
            if (g_altHeld) g_otherKeyPressed = true;

            // 热键检测
            if (g_hotkeyEnabled.load() && vk == g_hotkeyVk.load()) {
                int hotkeyModifiers = g_hotkeyModifiers.load();
                bool altMatch = IsModifierPressedNow(1) == ((hotkeyModifiers & 1) != 0);
                bool ctrlMatch = IsModifierPressedNow(2) == ((hotkeyModifiers & 2) != 0);
                bool shiftMatch = IsModifierPressedNow(4) == ((hotkeyModifiers & 4) != 0);
                bool winMatch = IsModifierPressedNow(8) == ((hotkeyModifiers & 8) != 0);
                if (altMatch && ctrlMatch && shiftMatch && winMatch) {
                    if (!g_registeredHotkeyActive.load() &&
                        !wasPressed &&
                        (now - g_lastHotkeyTime) > 0.25) {
                        g_lastHotkeyTime = now;
                        InvokeKeyboardCallbackAsync(CallbackEvent::GlobalHotkey);
                    }
                    // 拦截热键事件，不传递给系统和其它程序
                    return 1;
                }
            }

            // keyboard模式触发检测
            int normalMode, specialMode;
            std::vector<int> normalKeys, specialKeys;
            int normalMod, specialMod;
            {
                std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
                normalMode = g_normalTriggerMode;
                normalKeys = g_normalTriggerKeys;
                normalMod = g_normalTriggerModifiers;
                specialMode = g_specialTriggerMode;
                specialKeys = g_specialTriggerKeys;
                specialMod = g_specialTriggerModifiers;
            }

            if (normalMode == 1 || specialMode == 1) {
                bool isSpecial = IsSpecialApp();
                int targetMode = isSpecial ? specialMode : normalMode;
                const std::vector<int>& targetKeys = isSpecial ? specialKeys : normalKeys;
                int targetMod = isSpecial ? specialMod : normalMod;

                if (targetMode == 1 && !targetKeys.empty() && !wasPressed) {  // 纯keyboard模式
                // 检查当前按键是否在目标按键列表中
                bool isTargetKey = false;
                for (int targetVk : targetKeys) {
                    if (vk == targetVk) {
                        isTargetKey = true;
                        break;
                    }
                }

                if (isTargetKey) {
                    // 检查所有目标按键是否都被按下
                    // 对于当前按键，我们知道它肯定被按下了（KEYDOWN事件）
                    bool allKeysPressed = true;
                    for (int targetVk : targetKeys) {
                        if (targetVk != vk) {  // 跳过当前按键
                            if (!(GetAsyncKeyState(targetVk) & 0x8000)) {
                                allKeysPressed = false;
                                break;
                            }
                        }
                    }

                    // 检查修饰键
                    int currentMod = 0;
                    if (IsCtrlPressedNow()) currentMod |= 2;
                    if (IsAltPressedNow()) currentMod |= 1;
                    if (GetAsyncKeyState(VK_SHIFT) & 0x8000) currentMod |= 4;
                    if ((GetAsyncKeyState(VK_LWIN) & 0x8000) || (GetAsyncKeyState(VK_RWIN) & 0x8000)) currentMod |= 8;

                    if (allKeysPressed && currentMod == targetMod) {
                        // 触发弹窗
                        MouseCallback callback = g_mouseCallback.load();
                        if (callback) {
                            POINT pt;
                            GetCursorPos(&pt);
                            bool rawAlreadyTriggered =
                                g_lastRawKeyboardFallbackVk.load() == vk &&
                                (GetTickCount64() - g_lastRawKeyboardFallbackTick.load()) <=
                                    RAW_FALLBACK_LATE_LL_WINDOW_MS;
                            if (!rawAlreadyTriggered) {
                                InvokeMouseCallbackAsync(CallbackEvent::MouseTrigger, pt.x, pt.y);
                            }
                        }
                    }
                }
            }
            }
        }
    } else if (isUp) {
        if (isCtrl) {
            g_ctrlHeld = false;
        } else if (isAlt) {
            if (g_altHeld) {
                g_altHeld = false;
                double holdTime = now - g_altPressTime;

                if (holdTime < ALT_TAP_MAX_HOLD_TIME && !g_otherKeyPressed) {
                    if (g_altTapCount >= 1) {
                        double interval = now - g_lastAltReleaseTime;
                        if (interval < ALT_DOUBLE_TAP_INTERVAL) {
                            if ((now - g_lastDoubleTapTime) > ALT_DOUBLE_TAP_COOLDOWN) {
                                g_lastDoubleTapTime = now;
                                g_altTapCount = 0;
                                InvokeKeyboardCallbackAsync(CallbackEvent::AltDoubleTap);
                            } else {
                                g_altTapCount = 0;
                            }
                        } else {
                            g_altTapCount = 1;
                        }
                    } else {
                        g_altTapCount = 1;
                    }
                    g_lastAltReleaseTime = now;
                } else {
                    g_altTapCount = 0;
                }
            }
        }
        // 热键 KeyUp 时，如果刚触发过热键也拦截（防止 keyup 泄漏给系统）
        if (g_hotkeyEnabled.load() && vk == g_hotkeyVk.load()) {
            // 检查是否在极短时间内刚触发过热键
            if ((now - g_lastHotkeyTime) < 0.30) {
                return 1;
            }
        }
    }

    return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
}

DWORD WINAPI KeyboardHookThread(LPVOID param) {
    g_keyboardThreadAlive = true;
    if (g_keyboardExitedEvent) ResetEvent(g_keyboardExitedEvent);
    HANDLE readyEvent = (HANDLE)param;
    g_keyboardThreadId = GetCurrentThreadId();
    MSG bootstrapMessage;
    PeekMessage(&bootstrapMessage, NULL, WM_USER, WM_USER, PM_NOREMOVE);
    std::fill(g_keyboardPressed, g_keyboardPressed + 256, false);
    g_keyboardHook = SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardHookProc, GetCurrentDllModule(), 0);

    if (!g_keyboardHook) {
        g_lastHookError = GetLastError();
        g_keyboardRunning = false;
        g_keyboardThreadId = 0;
        g_keyboardThreadAlive = false;
        if (readyEvent) SetEvent(readyEvent);
        if (g_keyboardExitedEvent) SetEvent(g_keyboardExitedEvent);
        return 1;
    }
    g_lowLevelKeyboardHealthy = true;
    g_lastHookError = ERROR_SUCCESS;

    if (g_hotkeyEnabled.load() && g_hotkeyModifiers.load() && g_hotkeyVk.load()) {
        bool registered = RegisterHotKey(
            NULL,
            QL_GLOBAL_HOTKEY_ID,
            static_cast<UINT>(g_hotkeyModifiers.load()) | MOD_NOREPEAT,
            static_cast<UINT>(g_hotkeyVk.load()));
        g_registeredHotkeyActive = registered;
        if (!registered) g_lastHookError = GetLastError();
    }

    // 通知主线程钩子安装成功
    if (readyEvent) SetEvent(readyEvent);

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        if (msg.message == WM_QL_REGISTER_HOTKEY) {
            UnregisterHotKey(NULL, QL_GLOBAL_HOTKEY_ID);
            int modifiers = g_hotkeyModifiers.load();
            int vk = g_hotkeyVk.load();
            bool registered = modifiers != 0 && vk != 0 &&
                RegisterHotKey(
                    NULL,
                    QL_GLOBAL_HOTKEY_ID,
                    static_cast<UINT>(modifiers) | MOD_NOREPEAT,
                    static_cast<UINT>(vk));
            g_registeredHotkeyActive = registered;
            g_hotkeyCommandResult = registered;
            if (!registered) g_lastHookError = GetLastError();
            if (g_hotkeyCommandEvent) SetEvent(g_hotkeyCommandEvent);
            continue;
        }
        if (msg.message == WM_QL_CLEAR_HOTKEY) {
            UnregisterHotKey(NULL, QL_GLOBAL_HOTKEY_ID);
            g_registeredHotkeyActive = false;
            g_hotkeyCommandResult = true;
            if (g_hotkeyCommandEvent) SetEvent(g_hotkeyCommandEvent);
            continue;
        }
        if (msg.message == WM_QL_START_CAPTURE_TIMER) {
            KillTimer(NULL, QL_CAPTURE_TIMER_ID);
            SetTimer(NULL, QL_CAPTURE_TIMER_ID, static_cast<UINT>(msg.wParam), NULL);
            continue;
        }
        if (msg.message == WM_QL_STOP_CAPTURE_TIMER) {
            KillTimer(NULL, QL_CAPTURE_TIMER_ID);
            continue;
        }
        if (msg.message == WM_TIMER && msg.wParam == QL_CAPTURE_TIMER_ID) {
            KillTimer(NULL, QL_CAPTURE_TIMER_ID);
            std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
            StopHotkeyCaptureLocked();
            continue;
        }
        if (msg.message == WM_HOTKEY && msg.wParam == QL_GLOBAL_HOTKEY_ID) {
            if (g_hotkeyEnabled.load()) {
                g_lastHotkeyTime = GetTime();
                InvokeKeyboardCallbackAsync(CallbackEvent::GlobalHotkey);
            }
            continue;
        }
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    UnregisterHotKey(NULL, QL_GLOBAL_HOTKEY_ID);
    KillTimer(NULL, QL_CAPTURE_TIMER_ID);
    g_registeredHotkeyActive = false;
    if (g_keyboardHook) {
        UnhookWindowsHookEx(g_keyboardHook);
        g_keyboardHook = NULL;
    }
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
    g_keyboardThreadId = 0;
    g_keyboardRunning = false;
    g_keyboardThreadAlive = false;
    g_lowLevelKeyboardHealthy = false;
    if (g_keyboardExitedEvent) SetEvent(g_keyboardExitedEvent);
    return 0;
}

// ============================================================
// 导出函数实现
// ============================================================

bool InstallMouseHook(MouseCallback callback) {
    g_mouseCallback = nullptr;
    PurgeCallbackEvents(CallbackEvent::MouseTrigger);
    WaitForCallbacksToDrain();
    HookContext ctx{
        g_mouseHook, g_mouseThreadId, g_mouseThreadHandle,
        g_mouseReadyEvent, g_mouseExitedEvent,
        g_mouseRunning, g_mouseInstalling, g_mouseThreadAlive
    };
    InstallHookGeneric(ctx, MouseHookThread, callback, nullptr);
    return g_mouseThreadAlive.load() && (g_mouseHook != NULL || g_rawInputActive.load());
}

void UninstallMouseHook() {
    if (g_inputCaptureActive.load() &&
        (g_inputCaptureFilter.load() &
         (HOOK_CAPTURE_MOUSE_MOVE | HOOK_CAPTURE_MOUSE_BUTTON | HOOK_CAPTURE_MOUSE_WHEEL)) != 0) {
        StopInputCapture();
    }
    HookContext ctx{
        g_mouseHook, g_mouseThreadId, g_mouseThreadHandle,
        g_mouseReadyEvent, g_mouseExitedEvent,
        g_mouseRunning, g_mouseInstalling, g_mouseThreadAlive
    };
    UninstallHookGeneric(ctx);
    PurgeCallbackEvents(CallbackEvent::MouseTrigger);
    PurgeCallbackEvents(CallbackEvent::AltDoubleClick);
    WaitForCallbacksToDrain();
    g_mouseCallback = nullptr;
    g_altDoubleClickCallback = nullptr;
    StopDebugLogThread();
    StopCallbackThreadIfIdle();
}

void SetMousePaused(bool paused) {
    g_mousePaused = paused;
    if (paused) {
        g_blockedDown = false;
        g_blockedButton = 0;
    }
}

bool IsMousePaused() {
    return g_mousePaused;
}

bool IsMouseHookInstalled() {
    return g_mouseHook != NULL &&
           g_lowLevelMouseHealthy.load() &&
           g_mouseRunning.load() &&
           g_mouseThreadAlive.load();
}

bool IsRawInputFallbackActive() {
    return g_rawInputActive.load() && g_mouseRunning.load() && g_mouseThreadAlive.load();
}

void SetAltDoubleClickCallback(MouseCallback callback) {
    g_altDoubleClickCallback = nullptr;
    PurgeCallbackEvents(CallbackEvent::AltDoubleClick);
    WaitForCallbacksToDrain();
    g_altDoubleClickCallback = callback;
}

bool InstallKeyboardHook(KeyboardCallback altDoubleTapCallback) {
    g_altDoubleTapCallback = nullptr;
    PurgeCallbackEvents(CallbackEvent::AltDoubleTap);
    WaitForCallbacksToDrain();
    HookContext ctx{
        g_keyboardHook, g_keyboardThreadId, g_keyboardThreadHandle,
        g_keyboardReadyEvent, g_keyboardExitedEvent,
        g_keyboardRunning, g_keyboardInstalling, g_keyboardThreadAlive
    };
    bool result = InstallHookGeneric(ctx, KeyboardHookThread, nullptr, altDoubleTapCallback);
    return result;
}

void UninstallKeyboardHook() {
    if (g_inputCaptureActive.load() &&
        (g_inputCaptureFilter.load() & HOOK_CAPTURE_KEYBOARD) != 0) {
        StopInputCapture();
    }
    HookContext ctx{
        g_keyboardHook, g_keyboardThreadId, g_keyboardThreadHandle,
        g_keyboardReadyEvent, g_keyboardExitedEvent,
        g_keyboardRunning, g_keyboardInstalling, g_keyboardThreadAlive
    };
    UninstallHookGeneric(ctx);
    PurgeCallbackEvents(CallbackEvent::AltDoubleTap);
    PurgeCallbackEvents(CallbackEvent::GlobalHotkey);
    PurgeCallbackEvents(CallbackEvent::HotkeyCapture);
    WaitForCallbacksToDrain();
    g_altDoubleTapCallback = nullptr;
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureEnabled = false;
        g_hotkeyCaptureCallback = nullptr;
        ResetHotkeyCaptureStateLocked();
    }
    StopCallbackThreadIfIdle();
}

bool IsAltHeld() {
    // 增加物理键状态同步：如果逻辑上是 held 但物理上已释放，立即修正
    if (g_altHeld && !IsAltPressedNow()) {
        g_altHeld = false;
    }
    return g_altHeld;
}

bool IsCtrlHeld() {
    return g_ctrlHeld || IsCtrlPressedNow();
}

bool IsKeyboardHookInstalled() {
    return g_keyboardHook != NULL &&
           g_lowLevelKeyboardHealthy.load() &&
           g_keyboardRunning.load() &&
           g_keyboardThreadAlive.load();
}

static std::string NormalizeHotkeyToken(std::string token) {
    token.erase(std::remove_if(token.begin(), token.end(), ::isspace), token.end());
    std::transform(token.begin(), token.end(), token.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    if (token.length() > 2 && token.front() == '<' && token.back() == '>') {
        token = token.substr(1, token.length() - 2);
    }
    return token;
}

static bool ParseGlobalHotkey(const std::string& hotkeyStr, int* modifiers, int* vk) {
    if (!modifiers || !vk) return false;
    *modifiers = 0;
    *vk = 0;

    size_t start = 0;
    while (start <= hotkeyStr.length()) {
        size_t end = hotkeyStr.find('+', start);
        std::string token = hotkeyStr.substr(
            start,
            end == std::string::npos ? std::string::npos : end - start
        );
        token = NormalizeHotkeyToken(token);

        if (!token.empty()) {
            if (token == "alt") {
                *modifiers |= 1;
            } else if (token == "ctrl" || token == "control") {
                *modifiers |= 2;
            } else if (token == "shift") {
                *modifiers |= 4;
            } else if (token == "win" || token == "windows" || token == "cmd" ||
                       token == "meta" || token == "super") {
                *modifiers |= 8;
            } else if (token.length() == 1 && token[0] >= 'a' && token[0] <= 'z') {
                if (*vk != 0) return false;
                *vk = static_cast<int>(std::toupper(static_cast<unsigned char>(token[0])));
            } else if (token.length() == 1 && token[0] >= '0' && token[0] <= '9') {
                if (*vk != 0) return false;
                *vk = static_cast<int>(token[0]);
            } else if (token == "space") {
                if (*vk != 0) return false;
                *vk = VK_SPACE;
            } else if (token == "tab") {
                if (*vk != 0) return false;
                *vk = VK_TAB;
            } else if (token == "enter" || token == "return") {
                if (*vk != 0) return false;
                *vk = VK_RETURN;
            } else if (token == "esc" || token == "escape") {
                if (*vk != 0) return false;
                *vk = VK_ESCAPE;
            } else if (token == "backspace" || token == "back") {
                if (*vk != 0) return false;
                *vk = VK_BACK;
            } else if (token == "delete" || token == "del") {
                if (*vk != 0) return false;
                *vk = VK_DELETE;
            } else if (token == "insert" || token == "ins") {
                if (*vk != 0) return false;
                *vk = VK_INSERT;
            } else if (token == "home") {
                if (*vk != 0) return false;
                *vk = VK_HOME;
            } else if (token == "end") {
                if (*vk != 0) return false;
                *vk = VK_END;
            } else if (token == "pageup" || token == "pgup") {
                if (*vk != 0) return false;
                *vk = VK_PRIOR;
            } else if (token == "pagedown" || token == "pgdn") {
                if (*vk != 0) return false;
                *vk = VK_NEXT;
            } else if (token == "left") {
                if (*vk != 0) return false;
                *vk = VK_LEFT;
            } else if (token == "up") {
                if (*vk != 0) return false;
                *vk = VK_UP;
            } else if (token == "right") {
                if (*vk != 0) return false;
                *vk = VK_RIGHT;
            } else if (token == "down") {
                if (*vk != 0) return false;
                *vk = VK_DOWN;
            } else if (token == "pause") {
                if (*vk != 0) return false;
                *vk = VK_PAUSE;
            } else if (token == "printscreen" || token == "prtscr") {
                if (*vk != 0) return false;
                *vk = VK_SNAPSHOT;
            } else if (token == "volumeup") {
                if (*vk != 0) return false;
                *vk = VK_VOLUME_UP;
            } else if (token == "volumedown") {
                if (*vk != 0) return false;
                *vk = VK_VOLUME_DOWN;
            } else if (token == "volumemute" || token == "mute") {
                if (*vk != 0) return false;
                *vk = VK_VOLUME_MUTE;
            } else if (token == "medianext") {
                if (*vk != 0) return false;
                *vk = VK_MEDIA_NEXT_TRACK;
            } else if (token == "mediaprev") {
                if (*vk != 0) return false;
                *vk = VK_MEDIA_PREV_TRACK;
            } else if (token == "mediastop") {
                if (*vk != 0) return false;
                *vk = VK_MEDIA_STOP;
            } else if (token == "mediaplay" || token == "playpause") {
                if (*vk != 0) return false;
                *vk = VK_MEDIA_PLAY_PAUSE;
            } else if (token.length() >= 2 && token[0] == 'f') {
                int n = atoi(token.substr(1).c_str());
                if (n < 1 || n > 24 || *vk != 0) return false;
                *vk = VK_F1 + (n - 1);
            } else {
                return false;
            }
        }

        if (end == std::string::npos) break;
        start = end + 1;
    }

    return *vk != 0 && *modifiers != 0;
}

bool SetGlobalHotkey(const char* hotkeyStr, KeyboardCallback callback) {
    if (!hotkeyStr || !callback) return false;

    std::string str(hotkeyStr);
    int mods = 0, vk = 0;
    if (!ParseGlobalHotkey(str, &mods, &vk)) return false;

    {
        std::lock_guard<std::mutex> lock(g_hotkeyConfigMutex);
        g_hotkeyEnabled = false;
        g_hotkeyCallback = nullptr;
    }
    PurgeCallbackEvents(CallbackEvent::GlobalHotkey);
    WaitForCallbacksToDrain();

    std::lock_guard<std::mutex> lock(g_hotkeyConfigMutex);
    g_hotkeyCallback = callback;
    g_hotkeyModifiers = mods;
    g_hotkeyVk = vk;
    g_hotkeyEnabled = true;
    g_hotkeyCommandResult = false;

    if (!g_keyboardThreadId || !g_keyboardThreadAlive.load()) {
        // Keep the parsed configuration. KeyboardHookThread will register it
        // as soon as the hook backend starts.
        return true;
    }
    if (!g_hotkeyCommandEvent) {
        g_hotkeyCommandEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    }
    if (!g_hotkeyCommandEvent) {
        g_lastHookError = GetLastError();
        return false;
    }

    ResetEvent(g_hotkeyCommandEvent);
    if (!PostThreadMessage(g_keyboardThreadId, WM_QL_REGISTER_HOTKEY, 0, 0)) {
        g_lastHookError = GetLastError();
        return IsKeyboardHookInstalled();
    }
    DWORD result = WaitForSingleObject(g_hotkeyCommandEvent, HOOK_COMMAND_TIMEOUT_MS);
    if (result != WAIT_OBJECT_0) {
        g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
    }

    // RegisterHotKey is the preferred independent channel. The low-level
    // keyboard hook remains a functional fallback when registration is denied.
    return g_registeredHotkeyActive.load() || IsKeyboardHookInstalled();
}

void ClearGlobalHotkey() {
    {
        std::lock_guard<std::mutex> lock(g_hotkeyConfigMutex);
        g_hotkeyEnabled = false;
        g_hotkeyCallback = nullptr;
        if (g_keyboardThreadId && g_keyboardThreadAlive.load()) {
            if (!g_hotkeyCommandEvent) {
                g_hotkeyCommandEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
            }
            if (g_hotkeyCommandEvent) {
                ResetEvent(g_hotkeyCommandEvent);
                PostThreadMessage(g_keyboardThreadId, WM_QL_CLEAR_HOTKEY, 0, 0);
                DWORD result = WaitForSingleObject(g_hotkeyCommandEvent, HOOK_COMMAND_TIMEOUT_MS);
                if (result != WAIT_OBJECT_0) {
                    g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
                }
            }
        }
        g_registeredHotkeyActive = false;
        g_hotkeyModifiers = 0;
        g_hotkeyVk = 0;
    }
    PurgeCallbackEvents(CallbackEvent::GlobalHotkey);
    WaitForCallbacksToDrain();
}

HOOKS_API bool StartHotkeyCapture(HotkeyCaptureCallback callback, int timeoutMs) {
    if (!callback) {
        g_lastHookError = ERROR_INVALID_PARAMETER;
        return false;
    }
    if (!IsKeyboardHookInstalled()) {
        g_lastHookError = ERROR_NOT_READY;
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureEnabled = false;
    }
    PurgeCallbackEvents(CallbackEvent::HotkeyCapture);
    WaitForCallbacksToDrain();

    std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
    ResetHotkeyCaptureStateLocked();
    g_hotkeyCaptureCallback = callback;
    g_hotkeyCaptureTimeoutMs = timeoutMs > 0 ? static_cast<DWORD>(timeoutMs) : 10000;
    g_hotkeyCaptureStartedTick = GetTickCount();
    g_hotkeyCaptureEnabled = true;
    PostThreadMessage(
        g_keyboardThreadId,
        WM_QL_START_CAPTURE_TIMER,
        static_cast<WPARAM>(g_hotkeyCaptureTimeoutMs),
        0);
    return true;
}

HOOKS_API void StopHotkeyCapture() {
    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureEnabled = false;
        ResetHotkeyCaptureStateLocked();
    }
    PurgeCallbackEvents(CallbackEvent::HotkeyCapture);
    WaitForCallbacksToDrain();
    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureCallback = nullptr;
    }
    if (g_keyboardThreadId) {
        PostThreadMessage(g_keyboardThreadId, WM_QL_STOP_CAPTURE_TIMER, 0, 0);
    }
}

HOOKS_API bool IsHotkeyCaptureActive() {
    if (g_hotkeyCaptureEnabled.load() && g_hotkeyCaptureTimeoutMs > 0) {
        DWORD elapsed = GetTickCount() - g_hotkeyCaptureStartedTick;
        if (elapsed > g_hotkeyCaptureTimeoutMs) {
            StopHotkeyCapture();
        }
    }
    return g_hotkeyCaptureEnabled.load();
}

static DWORD MouseButtonDownFlag(int button) {
    switch (button) {
        case 1: return MOUSEEVENTF_LEFTDOWN;
        case 2: return MOUSEEVENTF_RIGHTDOWN;
        case 4: return MOUSEEVENTF_MIDDLEDOWN;
        case 8:
        case 16:
            return MOUSEEVENTF_XDOWN;
        default:
            return 0;
    }
}

static DWORD MouseButtonUpFlag(int button) {
    switch (button) {
        case 1: return MOUSEEVENTF_LEFTUP;
        case 2: return MOUSEEVENTF_RIGHTUP;
        case 4: return MOUSEEVENTF_MIDDLEUP;
        case 8:
        case 16:
            return MOUSEEVENTF_XUP;
        default:
            return 0;
    }
}

static bool BuildMacroInput(const HookMacroEvent& eventData, INPUT* input) {
    if (!input) return false;
    *input = {};

    switch (eventData.type) {
        case HOOK_INPUT_MOUSE_MOVE: {
            input->type = INPUT_MOUSE;
            input->mi.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            input->mi.dwFlags = MOUSEEVENTF_MOVE;
            if (eventData.flags & HOOK_INPUT_FLAG_ABSOLUTE) {
                int left = GetSystemMetrics(SM_XVIRTUALSCREEN);
                int top = GetSystemMetrics(SM_YVIRTUALSCREEN);
                int width = std::max(1, GetSystemMetrics(SM_CXVIRTUALSCREEN));
                int height = std::max(1, GetSystemMetrics(SM_CYVIRTUALSCREEN));
                long long dx = static_cast<long long>(eventData.x - left) * 65535LL /
                    std::max(1, width - 1);
                long long dy = static_cast<long long>(eventData.y - top) * 65535LL /
                    std::max(1, height - 1);
                input->mi.dx = static_cast<LONG>(std::clamp(dx, 0LL, 65535LL));
                input->mi.dy = static_cast<LONG>(std::clamp(dy, 0LL, 65535LL));
                input->mi.dwFlags |= MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
            } else {
                input->mi.dx = eventData.x;
                input->mi.dy = eventData.y;
            }
            return true;
        }
        case HOOK_INPUT_MOUSE_BUTTON_DOWN:
        case HOOK_INPUT_MOUSE_BUTTON_UP: {
            DWORD flag = eventData.type == HOOK_INPUT_MOUSE_BUTTON_DOWN
                ? MouseButtonDownFlag(eventData.data)
                : MouseButtonUpFlag(eventData.data);
            if (!flag) return false;
            input->type = INPUT_MOUSE;
            input->mi.dwFlags = flag;
            input->mi.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            if (eventData.data == 8 || eventData.data == 16) {
                input->mi.mouseData = eventData.data == 8 ? XBUTTON1 : XBUTTON2;
            }
            return true;
        }
        case HOOK_INPUT_MOUSE_WHEEL:
        case HOOK_INPUT_MOUSE_HWHEEL:
            input->type = INPUT_MOUSE;
            input->mi.dwFlags = eventData.type == HOOK_INPUT_MOUSE_WHEEL
                ? MOUSEEVENTF_WHEEL
                : MOUSEEVENTF_HWHEEL;
            input->mi.mouseData = static_cast<DWORD>(eventData.data);
            input->mi.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            return true;
        case HOOK_INPUT_KEY_DOWN:
        case HOOK_INPUT_KEY_UP:
            if (eventData.vkCode == 0 && eventData.scanCode == 0) return false;
            input->type = INPUT_KEYBOARD;
            input->ki.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            if (eventData.scanCode != 0) {
                input->ki.wScan = static_cast<WORD>(eventData.scanCode);
                input->ki.dwFlags |= KEYEVENTF_SCANCODE;
            } else {
                input->ki.wVk = static_cast<WORD>(eventData.vkCode);
            }
            if (eventData.flags & HOOK_INPUT_FLAG_EXTENDED) {
                input->ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
            }
            if (eventData.type == HOOK_INPUT_KEY_UP) {
                input->ki.dwFlags |= KEYEVENTF_KEYUP;
            }
            return true;
        case HOOK_INPUT_UNICODE_DOWN:
        case HOOK_INPUT_UNICODE_UP:
            if (eventData.data <= 0 || eventData.data > 0xFFFF) return false;
            input->type = INPUT_KEYBOARD;
            input->ki.wScan = static_cast<WORD>(eventData.data);
            input->ki.dwFlags = KEYEVENTF_UNICODE;
            input->ki.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            if (eventData.type == HOOK_INPUT_UNICODE_UP) {
                input->ki.dwFlags |= KEYEVENTF_KEYUP;
            }
            return true;
        default:
            return false;
    }
}

static void TrackMacroInputState(const HookMacroEvent& eventData) {
    std::lock_guard<std::mutex> lock(g_macroPressedMutex);
    if (eventData.type == HOOK_INPUT_KEY_DOWN && eventData.vkCode < 256) {
        g_macroPressedKeys[eventData.vkCode] = true;
        g_macroPressedKeyScanCodes[eventData.vkCode] = eventData.scanCode;
        g_macroPressedKeyFlags[eventData.vkCode] = eventData.flags;
    } else if (eventData.type == HOOK_INPUT_KEY_UP && eventData.vkCode < 256) {
        g_macroPressedKeys[eventData.vkCode] = false;
        g_macroPressedKeyScanCodes[eventData.vkCode] = 0;
        g_macroPressedKeyFlags[eventData.vkCode] = 0;
    } else if (eventData.type == HOOK_INPUT_UNICODE_DOWN) {
        g_macroPressedUnicode.push_back(static_cast<unsigned int>(eventData.data));
    } else if (eventData.type == HOOK_INPUT_UNICODE_UP) {
        auto it = std::find(
            g_macroPressedUnicode.begin(),
            g_macroPressedUnicode.end(),
            static_cast<unsigned int>(eventData.data));
        if (it != g_macroPressedUnicode.end()) g_macroPressedUnicode.erase(it);
    } else if (eventData.type == HOOK_INPUT_MOUSE_BUTTON_DOWN) {
        g_macroPressedMouseButtons |= static_cast<unsigned int>(eventData.data);
    } else if (eventData.type == HOOK_INPUT_MOUSE_BUTTON_UP) {
        g_macroPressedMouseButtons &= ~static_cast<unsigned int>(eventData.data);
    }
}

HOOKS_API void ReleaseMacroPressedInputs() {
    std::vector<INPUT> inputs;
    {
        std::lock_guard<std::mutex> lock(g_macroPressedMutex);
        for (unsigned int vk = 0; vk < 256; ++vk) {
            if (!g_macroPressedKeys[vk]) continue;
            INPUT input = {};
            input.type = INPUT_KEYBOARD;
            if (g_macroPressedKeyScanCodes[vk] != 0) {
                input.ki.wScan = static_cast<WORD>(g_macroPressedKeyScanCodes[vk]);
                input.ki.dwFlags = KEYEVENTF_SCANCODE;
            } else {
                input.ki.wVk = static_cast<WORD>(vk);
            }
            input.ki.dwFlags = KEYEVENTF_KEYUP;
            if (g_macroPressedKeyScanCodes[vk] != 0) input.ki.dwFlags |= KEYEVENTF_SCANCODE;
            if (g_macroPressedKeyFlags[vk] & HOOK_INPUT_FLAG_EXTENDED) {
                input.ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
            }
            input.ki.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            inputs.push_back(input);
            g_macroPressedKeys[vk] = false;
            g_macroPressedKeyScanCodes[vk] = 0;
            g_macroPressedKeyFlags[vk] = 0;
        }
        for (unsigned int codeUnit : g_macroPressedUnicode) {
            INPUT input = {};
            input.type = INPUT_KEYBOARD;
            input.ki.wScan = static_cast<WORD>(codeUnit);
            input.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
            input.ki.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            inputs.push_back(input);
        }
        g_macroPressedUnicode.clear();
        const int buttons[] = {1, 2, 4, 8, 16};
        for (int button : buttons) {
            if ((g_macroPressedMouseButtons & static_cast<unsigned int>(button)) == 0) continue;
            INPUT input = {};
            input.type = INPUT_MOUSE;
            input.mi.dwFlags = MouseButtonUpFlag(button);
            input.mi.dwExtraInfo = static_cast<ULONG_PTR>(QL_MACRO_EXTRA_INFO);
            if (button == 8 || button == 16) {
                input.mi.mouseData = button == 8 ? XBUTTON1 : XBUTTON2;
            }
            inputs.push_back(input);
        }
        g_macroPressedMouseButtons = 0;
    }
    if (!inputs.empty()) {
        SendInput(static_cast<UINT>(inputs.size()), inputs.data(), sizeof(INPUT));
    }
}

static bool WaitMacroDelay(unsigned int delayUs) {
    if (delayUs == 0) return !g_macroCancelRequested.load();
    HANDLE timer = CreateWaitableTimerW(NULL, TRUE, NULL);
    if (!timer) {
        DWORD waitMs = std::max(1U, (delayUs + 999U) / 1000U);
        return WaitForSingleObject(g_macroCancelEvent, waitMs) == WAIT_TIMEOUT;
    }
    LARGE_INTEGER due = {};
    due.QuadPart = -static_cast<LONGLONG>(delayUs) * 10LL;
    if (!SetWaitableTimer(timer, &due, 0, NULL, NULL, FALSE)) {
        CloseHandle(timer);
        DWORD waitMs = std::max(1U, (delayUs + 999U) / 1000U);
        return WaitForSingleObject(g_macroCancelEvent, waitMs) == WAIT_TIMEOUT;
    }
    HANDLE handles[2] = {g_macroCancelEvent, timer};
    DWORD result = WaitForMultipleObjects(2, handles, FALSE, INFINITE);
    CancelWaitableTimer(timer);
    CloseHandle(timer);
    return result == WAIT_OBJECT_0 + 1;
}

static bool SendOneMacroEvent(const HookMacroEvent& eventData) {
    INPUT inputs[2] = {};
    UINT inputCount = 0;
    bool pointerAction =
        eventData.type == HOOK_INPUT_MOUSE_BUTTON_DOWN ||
        eventData.type == HOOK_INPUT_MOUSE_BUTTON_UP ||
        eventData.type == HOOK_INPUT_MOUSE_WHEEL ||
        eventData.type == HOOK_INPUT_MOUSE_HWHEEL;
    if (pointerAction && (eventData.flags & HOOK_INPUT_FLAG_ABSOLUTE)) {
        HookMacroEvent move = {};
        move.size = sizeof(HookMacroEvent);
        move.type = HOOK_INPUT_MOUSE_MOVE;
        move.flags = HOOK_INPUT_FLAG_ABSOLUTE;
        move.x = eventData.x;
        move.y = eventData.y;
        if (!BuildMacroInput(move, &inputs[inputCount++])) return false;
    }
    if (!BuildMacroInput(eventData, &inputs[inputCount++])) return false;
    if (SendInput(inputCount, inputs, sizeof(INPUT)) != inputCount) {
        g_macroLastError = GetLastError();
        return false;
    }
    TrackMacroInputState(eventData);
    return true;
}

static DWORD WINAPI MacroPlaybackThreadProc(LPVOID) {
    std::vector<HookMacroEvent> events;
    unsigned int options = 0;
    {
        std::lock_guard<std::mutex> lock(g_macroPlaybackMutex);
        events = g_macroPlaybackEvents;
        options = g_macroPlaybackOptions;
    }

    g_macroPlaybackStartedTick = GetTickCount64();
    g_macroPlaybackFinishedTick = 0;
    g_macroCompletedEvents = 0;
    g_macroLastError = ERROR_SUCCESS;

    for (const HookMacroEvent& eventData : events) {
        if (g_macroCancelRequested.load()) break;
        if ((options & HOOK_PLAYBACK_NO_TIMING) == 0 && !WaitMacroDelay(eventData.delayUs)) {
            g_macroCancelRequested = true;
            break;
        }

        INPUT validation = {};
        if (!BuildMacroInput(eventData, &validation)) {
            g_macroLastError = ERROR_INVALID_DATA;
            break;
        }
        if (!SendOneMacroEvent(eventData)) break;
        g_macroCompletedEvents.fetch_add(1);
    }

    bool keepPressed = g_macroCancelRequested.load() &&
        (options & HOOK_PLAYBACK_KEEP_PRESSED_ON_CANCEL) != 0;
    if (!keepPressed) ReleaseMacroPressedInputs();
    g_macroPlaybackFinishedTick = GetTickCount64();
    g_macroPlaybackActive = false;
    if (g_macroDoneEvent) SetEvent(g_macroDoneEvent);
    return 0;
}

HOOKS_API bool StartInputCapture(InputEventCallback callback, unsigned int filterFlags) {
    if (!callback || (filterFlags & HOOK_CAPTURE_ALL_PHYSICAL) == 0) {
        g_lastHookError = ERROR_INVALID_PARAMETER;
        return false;
    }
    bool needsMouse = (filterFlags &
        (HOOK_CAPTURE_MOUSE_MOVE | HOOK_CAPTURE_MOUSE_BUTTON | HOOK_CAPTURE_MOUSE_WHEEL)) != 0;
    bool needsKeyboard = (filterFlags & HOOK_CAPTURE_KEYBOARD) != 0;
    if ((needsMouse && !IsMouseHookInstalled()) ||
        (needsKeyboard && !IsKeyboardHookInstalled())) {
        g_lastHookError = ERROR_NOT_READY;
        return false;
    }
    if (g_inputCaptureActive.load()) {
        StopInputCapture();
    }
    if (!EnsureInputCaptureThread()) return false;

    {
        std::lock_guard<std::mutex> lock(g_inputCaptureMutex);
        g_pendingInputEvents.clear();
    }
    QueryPerformanceFrequency(&g_performanceFrequency);
    QueryPerformanceCounter(&g_inputCaptureStartCounter);
    g_inputCaptureSequence = 0;
    g_inputCapturedCount = 0;
    g_inputCaptureDroppedCount = 0;
    g_inputCaptureFilter = filterFlags;
    g_inputEventCallback = callback;
    g_inputCaptureActive = true;
    g_lastHookError = ERROR_SUCCESS;
    return true;
}

HOOKS_API void StopInputCapture() {
    g_inputCaptureActive = false;
    {
        std::lock_guard<std::mutex> lock(g_inputCaptureMutex);
        g_pendingInputEvents.clear();
    }
    DWORD captureThreadId = g_inputCaptureThread ? GetThreadId(g_inputCaptureThread) : 0;
    if (captureThreadId != 0 && GetCurrentThreadId() == captureThreadId) {
        g_inputEventCallback = nullptr;
        g_inputCaptureThreadRunning = false;
        if (g_inputCaptureEvent) SetEvent(g_inputCaptureEvent);
        return;
    }
    if (g_inputCaptureCallbacksInFlight.load() > 0 && g_inputCaptureIdleEvent) {
        DWORD result = WaitForSingleObject(g_inputCaptureIdleEvent, CALLBACK_DRAIN_TIMEOUT_MS);
        if (result != WAIT_OBJECT_0) {
            g_lastHookError = result == WAIT_TIMEOUT ? WAIT_TIMEOUT : GetLastError();
        }
    }
    StopInputCaptureThread();
}

HOOKS_API bool IsInputCaptureActive() {
    return g_inputCaptureActive.load();
}

HOOKS_API bool PlayMacroEvents(
    const HookMacroEvent* events,
    unsigned int count,
    unsigned int options)
{
    if (!events || count == 0 || count > MAX_MACRO_EVENTS) {
        g_lastHookError = ERROR_INVALID_PARAMETER;
        return false;
    }
    std::lock_guard<std::mutex> lock(g_macroPlaybackMutex);
    if (g_macroPlaybackActive.load()) {
        g_lastHookError = ERROR_BUSY;
        return false;
    }
    if (g_macroPlaybackThread) {
        DWORD result = WaitForSingleObject(g_macroPlaybackThread, THREAD_JOIN_TIMEOUT_MS);
        if (result != WAIT_OBJECT_0) {
            g_lastHookError = result == WAIT_TIMEOUT ? ERROR_BUSY : GetLastError();
            return false;
        }
        CloseHandle(g_macroPlaybackThread);
        g_macroPlaybackThread = NULL;
    }
    if (!g_macroCancelEvent) {
        g_macroCancelEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    }
    if (!g_macroDoneEvent) {
        g_macroDoneEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    }
    if (!g_macroCancelEvent || !g_macroDoneEvent) {
        g_lastHookError = GetLastError();
        return false;
    }

    g_macroPlaybackEvents.clear();
    g_macroPlaybackEvents.reserve(count);
    for (unsigned int i = 0; i < count; ++i) {
        if (events[i].size != 0 && events[i].size < sizeof(HookMacroEvent)) {
            g_lastHookError = ERROR_INVALID_DATA;
            g_macroPlaybackEvents.clear();
            return false;
        }
        INPUT validation = {};
        if (!BuildMacroInput(events[i], &validation)) {
            g_lastHookError = ERROR_INVALID_DATA;
            g_macroPlaybackEvents.clear();
            return false;
        }
        g_macroPlaybackEvents.push_back(events[i]);
    }
    g_macroPlaybackOptions = options;
    g_macroTotalEvents = count;
    g_macroCancelRequested = false;
    ResetEvent(g_macroCancelEvent);
    ResetEvent(g_macroDoneEvent);
    g_macroPlaybackActive = true;
    g_macroPlaybackThread = CreateThread(NULL, 0, MacroPlaybackThreadProc, NULL, 0, NULL);
    if (!g_macroPlaybackThread) {
        g_lastHookError = GetLastError();
        g_macroPlaybackActive = false;
        SetEvent(g_macroDoneEvent);
        return false;
    }
    g_lastHookError = ERROR_SUCCESS;
    return true;
}

HOOKS_API void CancelMacroPlayback() {
    g_macroCancelRequested = true;
    if (g_macroCancelEvent) SetEvent(g_macroCancelEvent);
}

HOOKS_API bool IsMacroPlaybackActive() {
    return g_macroPlaybackActive.load();
}

HOOKS_API bool WaitForMacroPlayback(unsigned int timeoutMs) {
    if (!g_macroPlaybackActive.load()) {
        std::lock_guard<std::mutex> lock(g_macroPlaybackMutex);
        if (g_macroPlaybackThread) {
            DWORD result = WaitForSingleObject(g_macroPlaybackThread, THREAD_JOIN_TIMEOUT_MS);
            if (result != WAIT_OBJECT_0) return false;
            CloseHandle(g_macroPlaybackThread);
            g_macroPlaybackThread = NULL;
        }
        return true;
    }
    if (!g_macroDoneEvent) return false;
    DWORD result = WaitForSingleObject(
        g_macroDoneEvent,
        timeoutMs == 0xFFFFFFFFU ? INFINITE : timeoutMs);
    if (result != WAIT_OBJECT_0) return false;
    std::lock_guard<std::mutex> lock(g_macroPlaybackMutex);
    if (g_macroPlaybackThread && !g_macroPlaybackActive.load()) {
        CloseHandle(g_macroPlaybackThread);
        g_macroPlaybackThread = NULL;
    }
    return true;
}

HOOKS_API bool GetMacroStatus(HookMacroStatus* status, unsigned int statusSize) {
    if (!status || statusSize < sizeof(HookMacroStatus)) {
        g_lastHookError = ERROR_INSUFFICIENT_BUFFER;
        return false;
    }
    HookMacroStatus snapshot = {};
    snapshot.size = sizeof(HookMacroStatus);
    snapshot.active = g_macroPlaybackActive.load() ? 1U : 0U;
    snapshot.cancelRequested = g_macroCancelRequested.load() ? 1U : 0U;
    snapshot.lastError = g_macroLastError.load();
    snapshot.totalEvents = g_macroTotalEvents.load();
    snapshot.completedEvents = g_macroCompletedEvents.load();
    snapshot.capturedEvents = g_inputCapturedCount.load();
    snapshot.captureDropped = g_inputCaptureDroppedCount.load();
    snapshot.playbackStartedTick = g_macroPlaybackStartedTick.load();
    snapshot.playbackFinishedTick = g_macroPlaybackFinishedTick.load();
    memcpy(status, &snapshot, sizeof(snapshot));
    return true;
}

void ReleaseAllModifierKeys() {
    // 只释放修饰键，不影响其他键
    const WORD keys[] = {
        VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
        VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
        VK_MENU, VK_LMENU, VK_RMENU,
        VK_LWIN, VK_RWIN,
    };
    INPUT inputs[sizeof(keys) / sizeof(keys[0])] = {0};

    for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i) {
        inputs[i].type = INPUT_KEYBOARD;
        inputs[i].ki.wVk = keys[i];
        inputs[i].ki.dwFlags = KEYEVENTF_KEYUP;
        if (keys[i] == VK_RCONTROL || keys[i] == VK_RMENU || keys[i] == VK_LWIN || keys[i] == VK_RWIN) {
            inputs[i].ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
        }
    }

    SendInput(static_cast<UINT>(sizeof(inputs) / sizeof(inputs[0])), inputs, sizeof(INPUT));
}

HOOKS_API void SetSpecialApps(const char** apps, int count) {
    std::lock_guard<std::mutex> lock(g_specialAppsMutex);
    g_specialApps.clear();
    for (int i = 0; i < count; i++) {
        if (apps[i]) {
            g_specialApps.push_back(apps[i]);
        }
    }
}

HOOKS_API void ClearSpecialApps() {
    std::lock_guard<std::mutex> lock(g_specialAppsMutex);
    g_specialApps.clear();
}

HOOKS_API void SetTriggerConfig(int normalButton, int normalModifiers, int specialButton, int specialModifiers) {
    std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
    g_normalTriggerButton = normalButton;
    g_normalTriggerModifiers = normalModifiers;
    g_specialTriggerButton = specialButton;
    g_specialTriggerModifiers = specialModifiers;
}

static std::vector<int> ParseVkList(const char* rawKeys) {
    std::vector<int> parsed;
    if (!rawKeys || strlen(rawKeys) == 0) {
        return parsed;
    }

    std::string keys(rawKeys);
    size_t start = 0;
    while (start <= keys.length()) {
        size_t end = keys.find(',', start);
        std::string token = keys.substr(
            start,
            end == std::string::npos ? std::string::npos : end - start
        );

        try {
            if (!token.empty()) {
                int vk = std::stoi(token);
                if (vk > 0 && vk <= 0xFF) {
                    parsed.push_back(vk);
                }
            }
        } catch (...) {
            g_lastHookError = ERROR_INVALID_PARAMETER;
        }

        if (end == std::string::npos) break;
        start = end + 1;
    }
    return parsed;
}

HOOKS_API void SetTriggerConfigEx(int normalMode, int normalButton, const char* normalKeys, int normalModifiers,
                                   int specialMode, int specialButton, const char* specialKeys, int specialModifiers) {
    std::lock_guard<std::mutex> lock(g_triggerConfigMutex);

    g_normalTriggerMode = normalMode;
    g_normalTriggerButton = normalButton;
    g_normalTriggerModifiers = normalModifiers;
    g_specialTriggerMode = specialMode;
    g_specialTriggerButton = specialButton;
    g_specialTriggerModifiers = specialModifiers;

    g_normalTriggerKeys = ParseVkList(normalKeys);
    g_specialTriggerKeys = ParseVkList(specialKeys);
}

HOOKS_API int GetHooksVersion() {
    return HOOKS_VERSION;
}

HOOKS_API unsigned int GetHooksCapabilities() {
    return HOOKS_CAP_MOUSE |
           HOOKS_CAP_KEYBOARD |
           HOOKS_CAP_GLOBAL_HOTKEY |
           HOOKS_CAP_SPECIAL_APPS |
           HOOKS_CAP_DIAGNOSTICS |
           HOOKS_CAP_HEALTH_STATUS |
           HOOKS_CAP_HOTKEY_CAPTURE |
           HOOKS_CAP_RAW_INPUT_FALLBACK |
           HOOKS_CAP_RUNTIME_STATS |
           HOOKS_CAP_REGISTER_HOTKEY |
           HOOKS_CAP_INPUT_CAPTURE |
           HOOKS_CAP_MACRO_PLAYBACK;
}

HOOKS_API unsigned long GetLastHookError() {
    return static_cast<unsigned long>(g_lastHookError.load());
}

HOOKS_API bool GetHooksRuntimeStats(HooksRuntimeStats* stats, unsigned int statsSize) {
    if (!stats || statsSize < sizeof(HooksRuntimeStats)) {
        g_lastHookError = ERROR_INSUFFICIENT_BUFFER;
        return false;
    }

    HooksRuntimeStats snapshot = {};
    snapshot.size = sizeof(HooksRuntimeStats);
    snapshot.version = HOOKS_VERSION;
    if (g_mouseThreadAlive.load()) snapshot.healthFlags |= HOOK_HEALTH_MOUSE_THREAD;
    if (IsMouseHookInstalled()) snapshot.healthFlags |= HOOK_HEALTH_MOUSE_LL;
    if (IsRawInputFallbackActive()) snapshot.healthFlags |= HOOK_HEALTH_RAW_MOUSE;
    if (IsRawInputFallbackActive()) snapshot.healthFlags |= HOOK_HEALTH_RAW_KEYBOARD;
    if (g_keyboardThreadAlive.load()) snapshot.healthFlags |= HOOK_HEALTH_KEYBOARD_THREAD;
    if (IsKeyboardHookInstalled()) snapshot.healthFlags |= HOOK_HEALTH_KEYBOARD_LL;
    if (g_callbackThreadRunning.load() && g_callbackThread) snapshot.healthFlags |= HOOK_HEALTH_CALLBACK_THREAD;
    if (g_registeredHotkeyActive.load()) snapshot.healthFlags |= HOOK_HEALTH_REGISTERED_HOTKEY;
    {
        std::lock_guard<std::mutex> lock(g_callbackMutex);
        snapshot.callbackQueueDepth = static_cast<unsigned int>(g_pendingCallbacks.size());
    }
    snapshot.lowLevelMouseEvents = g_lowLevelMouseEventCount.load();
    snapshot.rawMouseEvents = g_rawMouseEventCount.load();
    snapshot.rawFallbackTriggers = g_rawFallbackTriggerCount.load();
    snapshot.injectedMouseEventsIgnored = g_injectedMouseIgnoredCount.load();
    snapshot.lowLevelKeyboardEvents = g_lowLevelKeyboardEventCount.load();
    snapshot.rawKeyboardEvents = g_rawKeyboardEventCount.load();
    snapshot.injectedKeyboardEventsIgnored = g_injectedKeyboardIgnoredCount.load();
    snapshot.callbackQueueDropped = g_queueOverflowCount.load();
    snapshot.callbackExceptions = g_callbackExceptionCount.load();
    snapshot.mouseLastEventTick = g_mouseLastEventTick.load();
    snapshot.keyboardLastEventTick = g_keyboardLastEventTick.load();
    memcpy(stats, &snapshot, sizeof(snapshot));
    return true;
}

HOOKS_API void ResetHooksRuntimeStats() {
    g_lowLevelMouseEventCount = 0;
    g_rawMouseEventCount = 0;
    g_rawFallbackTriggerCount = 0;
    g_injectedMouseIgnoredCount = 0;
    g_lowLevelKeyboardEventCount = 0;
    g_rawKeyboardEventCount = 0;
    g_injectedKeyboardIgnoredCount = 0;
    g_queueOverflowCount = 0;
    g_callbackExceptionCount = 0;
}
