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
static std::atomic<MouseCallback> g_taskbarDoubleClickCallback(nullptr);
static std::atomic<KeyboardCallback> g_altDoubleTapCallback(nullptr);
static std::atomic<KeyboardCallback> g_hotkeyCallback(nullptr);
static std::atomic<HotkeyCaptureCallback> g_hotkeyCaptureCallback(nullptr);
static std::atomic<ProtectedChordCaptureCallback> g_protectedChordCaptureCallback(nullptr);
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
static std::atomic<unsigned long long> g_lowLevelInputCaptureKeyboardCount(0);
static unsigned long long g_rawConsumedLowLevelKeyboardCount = 0;
static unsigned long long g_rawConsumedInputCaptureKeyboardCount = 0;
static bool g_rawKeyboardPressed[256] = {false};
static bool g_inputCaptureKeyboardPressed[256] = {false};
struct PendingRawKeyboardEvent {
    int vk;
    unsigned int scanCode;
    unsigned int flags;
    bool down;
    bool wasPressed;
    bool shouldTrigger;
};
static std::deque<PendingRawKeyboardEvent> g_pendingRawKeyboardEvents;
static std::atomic<unsigned long long> g_lastRawKeyboardFallbackTick(0);
static std::atomic<int> g_lastRawKeyboardFallbackVk(0);
static std::atomic<unsigned long long> g_lastKeyboardTriggerCallbackTick(0);
static std::atomic<bool> g_asyncKeyboardTriggerLatched(false);

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
static std::atomic<DWORD> g_hotkeyCaptureStartedTick(0);
static std::atomic<DWORD> g_hotkeyCaptureTimeoutMs(10000);
static bool g_hotkeyCapturePressed[256] = {false};
static bool g_hotkeyCapturePreexisting[256] = {false};
static bool g_hotkeyCaptureSwallowed[256] = {false};
static bool g_keyboardPressed[256] = {false};
static bool g_triggerBlockedKeys[256] = {false};
static int g_hotkeyCaptureSideModifiers = 0;
static std::mutex g_hotkeyCaptureMutex;

// 受保护组合录制：同时支持键盘与五键鼠标，并吞掉本次组合的按下/抬起事件。
static std::atomic<bool> g_protectedChordCaptureEnabled(false);
static std::atomic<unsigned int> g_protectedChordCaptureFlags(0);
static std::atomic<DWORD> g_protectedChordCaptureStartedTick(0);
static std::atomic<DWORD> g_protectedChordCaptureTimeoutMs(10000);
static bool g_protectedChordCaptureStarted = false;
static bool g_protectedChordPressed[256] = {false};
static bool g_protectedChordPreexisting[256] = {false};
static bool g_protectedChordSwallowed[256] = {false};
static int g_protectedChordMousePressed = 0;
static int g_protectedChordMousePreexisting = 0;
static int g_protectedChordMouseSwallowed = 0;
static int g_protectedChordCurrentSideModifiers = 0;
static int g_protectedChordSeenSideModifiers = 0;
static std::mutex g_protectedChordCaptureMutex;
static HANDLE g_protectedChordProcessLock = NULL;

enum CaptureMode {
    CAPTURE_MODE_NONE = 0,
    CAPTURE_MODE_HOTKEY = 1,
    CAPTURE_MODE_PROTECTED_CHORD = 2,
    CAPTURE_MODE_INPUT = 3,
};
static std::atomic<int> g_activeCaptureMode(CAPTURE_MODE_NONE);

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
static std::atomic<bool> g_normalTriggerHotkeyRegistered(false);
static std::atomic<bool> g_specialTriggerHotkeyRegistered(false);

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

struct CaptureDebugEvent {
    SYSTEMTIME time;
    DWORD processId;
    DWORD threadId;
    char phase[40];
    int inputCode;
    WPARAM message;
    DWORD flags;
    int modifiers;
    int sideModifiers;
    char detail[128];
};

static std::vector<CaptureDebugEvent> g_pendingCaptureDebugEvents;

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
        HotkeyCapture,
        ProtectedChordCapture,
        TaskbarDoubleClick,   // 任务栏双击触发
    } type;
    int x;
    int y;
    HotkeyCaptureCallback hotkeyCaptureCallback;
    ProtectedChordCaptureCallback protectedChordCaptureCallback;
    int vkCode;
    int modifiers;
    int sideModifiers;
};
static std::deque<CallbackEvent> g_pendingCallbacks;

// ========== 任务栏双击检测 ==========
constexpr double TASKBAR_DCLICK_COOLDOWN = 0.50;

static double g_taskbarDClickLastTime = 0.0;
static double g_taskbarDClickLastTrigger = 0.0;
static std::atomic<bool> g_taskbarTriggerEnabled{false};
static std::atomic<bool> g_taskbarTriggerCtrl{false};
static std::atomic<int> g_taskbarDClickIntervalMs{400};

static int ClampTaskbarDoubleClickIntervalMs(int intervalMs) {
    if (intervalMs < 400) return 400;
    if (intervalMs > 2000) return 2000;
    return intervalMs;
}

static bool IsDescendantOfWindow(HWND child, HWND ancestor) {
    if (!child || !ancestor) return false;
    if (child == ancestor) return true;
    HWND parent = GetParent(child);
    while (parent) {
        if (parent == ancestor) return true;
        parent = GetParent(parent);
    }
    return IsChild(ancestor, child) != FALSE;
}

static bool IsPointInTaskbarReservedBand(int x, int y) {
    POINT pt = { x, y };
    HMONITOR monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONULL);
    if (!monitor) return false;

    MONITORINFO info = {};
    info.cbSize = sizeof(info);
    if (!GetMonitorInfoW(monitor, &info)) return false;

    const RECT& rc = info.rcMonitor;
    const RECT& work = info.rcWork;
    if (EqualRect(&rc, &work)) return false;

    bool inMonitor = x >= rc.left && x < rc.right && y >= rc.top && y < rc.bottom;
    bool inWork = x >= work.left && x < work.right && y >= work.top && y < work.bottom;
    return inMonitor && !inWork;
}

static bool IsOnTaskbarTriggerArea(int x, int y) {
    HWND hTaskbar = FindWindowW(L"Shell_TrayWnd", NULL);
    if (hTaskbar && IsWindowVisible(hTaskbar)) {
        RECT rc;
        if (GetWindowRect(hTaskbar, &rc) &&
            x >= rc.left && x <= rc.right &&
            y >= rc.top && y <= rc.bottom) {
            POINT pt = { x, y };
            HWND hWndAtPoint = WindowFromPoint(pt);
            if (!hWndAtPoint) return false;
            // Win11: empty area often returns the taskbar window itself
            if (hWndAtPoint == hTaskbar) return true;
            if (IsDescendantOfWindow(hWndAtPoint, hTaskbar)) return true;
            return IsPointInTaskbarReservedBand(x, y);
        }
    }
    HWND hSecondary = FindWindowW(L"Shell_SecondaryTrayWnd", NULL);
    while (hSecondary) {
        if (IsWindowVisible(hSecondary)) {
            RECT rc;
            if (GetWindowRect(hSecondary, &rc) &&
                x >= rc.left && x <= rc.right &&
                y >= rc.top && y <= rc.bottom) {
                POINT pt = { x, y };
                HWND hWndAtPoint = WindowFromPoint(pt);
                if (!hWndAtPoint) return false;
                if (hWndAtPoint == hSecondary) return true;
                if (IsDescendantOfWindow(hWndAtPoint, hSecondary)) return true;
                return IsPointInTaskbarReservedBand(x, y);
            }
        }
        hSecondary = FindWindowExW(NULL, hSecondary, L"Shell_SecondaryTrayWnd", NULL);
    }
    return IsPointInTaskbarReservedBand(x, y);
}


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
constexpr int HOOKS_VERSION = 15;
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
constexpr unsigned int HOOKS_CAP_PROTECTED_CHORD_CAPTURE = 0x1000;
constexpr size_t CALLBACK_QUEUE_LIMIT = 256;
constexpr size_t INPUT_CAPTURE_QUEUE_LIMIT = 8192;
constexpr unsigned int MAX_MACRO_EVENTS = 100000;
constexpr DWORD THREAD_JOIN_TIMEOUT_MS = 2000;
constexpr DWORD CALLBACK_DRAIN_TIMEOUT_MS = 1000;
constexpr DWORD HOOK_COMMAND_TIMEOUT_MS = 1000;
constexpr UINT_PTR RAW_FALLBACK_TIMER_BASE = 0x5140;
constexpr UINT_PTR RAW_KEYBOARD_RECONCILE_TIMER = 0x5145;
constexpr UINT_PTR ASYNC_KEYBOARD_TRIGGER_TIMER = 0x5146;
constexpr UINT RAW_FALLBACK_RECONCILE_MS = 20;
constexpr UINT ASYNC_KEYBOARD_TRIGGER_POLL_MS = 10;
constexpr unsigned long long RAW_FALLBACK_LATE_LL_WINDOW_MS = 80;
constexpr UINT WM_QL_REGISTER_HOTKEY = WM_APP + 0x51;
constexpr UINT WM_QL_CLEAR_HOTKEY = WM_APP + 0x52;
constexpr UINT WM_QL_START_CAPTURE_TIMER = WM_APP + 0x53;
constexpr UINT WM_QL_STOP_CAPTURE_TIMER = WM_APP + 0x54;
constexpr UINT WM_QL_REFRESH_TRIGGER_HOTKEYS = WM_APP + 0x55;
constexpr int QL_GLOBAL_HOTKEY_ID = 0x514C;
constexpr UINT_PTR QL_CAPTURE_TIMER_ID = 0x514D;
constexpr int QL_NORMAL_TRIGGER_HOTKEY_ID = 0x514E;
constexpr int QL_SPECIAL_TRIGGER_HOTKEY_ID = 0x514F;
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

static bool TryClaimCaptureMode(CaptureMode mode) {
    int expected = CAPTURE_MODE_NONE;
    if (g_activeCaptureMode.compare_exchange_strong(expected, mode)) {
        return true;
    }
    g_lastHookError = ERROR_BUSY;
    return false;
}

static void ReleaseCaptureMode(CaptureMode mode) {
    int expected = mode;
    g_activeCaptureMode.compare_exchange_strong(expected, CAPTURE_MODE_NONE);
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
    ReleaseCaptureMode(CAPTURE_MODE_INPUT);
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

static bool InputCaptureKeyboardPollingEnabled() {
    unsigned int filter = g_inputCaptureFilter.load();
    return g_inputCaptureActive.load() &&
        (filter & HOOK_CAPTURE_KEYBOARD) != 0 &&
        (filter & HOOK_CAPTURE_INCLUDE_INJECTED) != 0;
}

static bool ShouldPollInputCaptureVirtualKey(int vk) {
    switch (vk) {
        case VK_LBUTTON:
        case VK_RBUTTON:
        case VK_CANCEL:
        case VK_MBUTTON:
        case VK_XBUTTON1:
        case VK_XBUTTON2:
        case VK_SHIFT:
        case VK_CONTROL:
        case VK_MENU:
            return false;
        default:
            return vk > 0 && vk < 256;
    }
}

static void ResetInputCaptureKeyboardPollState() {
    for (int vk = 0; vk < 256; ++vk) {
        g_inputCaptureKeyboardPressed[vk] =
            ShouldPollInputCaptureVirtualKey(vk) &&
            ((GetAsyncKeyState(vk) & 0x8000) != 0);
    }
}

static void NoteInputCaptureKeyboardState(int vk, bool down) {
    if (vk > 0 && vk < 256) {
        g_inputCaptureKeyboardPressed[vk] = down;
    }
}

static void PollInputCaptureKeyboardState() {
    if (!InputCaptureKeyboardPollingEnabled()) return;
    for (int vk = 1; vk < 256; ++vk) {
        if (!ShouldPollInputCaptureVirtualKey(vk)) continue;
        bool down = (GetAsyncKeyState(vk) & 0x8000) != 0;
        if (down == g_inputCaptureKeyboardPressed[vk]) continue;

        HookInputEvent eventData = {};
        eventData.type = down ? HOOK_INPUT_KEY_DOWN : HOOK_INPUT_KEY_UP;
        eventData.vkCode = static_cast<unsigned int>(vk);
        QueueCapturedInput(eventData);
        g_inputCaptureKeyboardPressed[vk] = down;
    }
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
static void InvokeProtectedChordCaptureCallbackAsync(
    ProtectedChordCaptureCallback callback,
    int inputCode,
    int modifiers,
    int sideModifiers);
static bool HookDebugLoggingEnabled();
static void LogProtectedCaptureEvent(
    const char* phase,
    int inputCode,
    WPARAM message,
    DWORD flags,
    int modifiers,
    int sideModifiers,
    const char* detail);

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

static int CurrentSideModifiers() {
    int sides = 0;
    if (GetAsyncKeyState(VK_LSHIFT) & 0x8000) sides |= HOTKEY_SIDE_LSHIFT;
    if (GetAsyncKeyState(VK_RSHIFT) & 0x8000) sides |= HOTKEY_SIDE_RSHIFT;
    if (GetAsyncKeyState(VK_LCONTROL) & 0x8000) sides |= HOTKEY_SIDE_LCTRL;
    if (GetAsyncKeyState(VK_RCONTROL) & 0x8000) sides |= HOTKEY_SIDE_RCTRL;
    if (GetAsyncKeyState(VK_LMENU) & 0x8000) sides |= HOTKEY_SIDE_LALT;
    if (GetAsyncKeyState(VK_RMENU) & 0x8000) sides |= HOTKEY_SIDE_RALT;
    if (GetAsyncKeyState(VK_LWIN) & 0x8000) sides |= HOTKEY_SIDE_LWIN;
    if (GetAsyncKeyState(VK_RWIN) & 0x8000) sides |= HOTKEY_SIDE_RWIN;
    return sides;
}

static void ResetHotkeyCaptureStateLocked() {
    std::fill(g_hotkeyCapturePressed, g_hotkeyCapturePressed + 256, false);
    std::fill(g_hotkeyCapturePreexisting, g_hotkeyCapturePreexisting + 256, false);
    std::fill(g_hotkeyCaptureSwallowed, g_hotkeyCaptureSwallowed + 256, false);
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
    ReleaseCaptureMode(CAPTURE_MODE_HOTKEY);
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

        if (g_hotkeyCaptureTimeoutMs.load() > 0) {
            DWORD elapsed = GetTickCount() - g_hotkeyCaptureStartedTick.load();
            if (elapsed > g_hotkeyCaptureTimeoutMs.load()) {
                StopHotkeyCaptureLocked();
                return false;
            }
        }

        int normalizedVk = NormalizeModifierVk(vk, pKbd);
        bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
        bool isUp = (wParam == WM_KEYUP || wParam == WM_SYSKEYUP);

        if (normalizedVk >= 0 && normalizedVk < 256) {
            if (g_hotkeyCapturePreexisting[normalizedVk]) {
                if (isUp) {
                    g_hotkeyCapturePreexisting[normalizedVk] = false;
                }
                return false;
            }
            if (isDown) {
                g_hotkeyCapturePressed[normalizedVk] = true;
                g_hotkeyCaptureSwallowed[normalizedVk] = true;
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
                bool swallowed = g_hotkeyCaptureSwallowed[normalizedVk];
                g_hotkeyCaptureSwallowed[normalizedVk] = false;
                int sideBit = HotkeySideBitForVk(normalizedVk);
                if (sideBit) g_hotkeyCaptureSideModifiers &= ~sideBit;

                if (g_hotkeyCaptureCompleted && !AnyHotkeyCaptureKeyPressedLocked()) {
                    StopHotkeyCaptureLocked();
                }
                if (!swallowed) return false;
            }
        }
    }

    if (callback) {
        InvokeHotkeyCaptureCallbackAsync(callback, callbackVk, callbackModifiers, callbackSideModifiers);
    }
    return captureWasActive;
}

static void ResetProtectedChordCaptureStateLocked() {
    std::fill(g_protectedChordPressed, g_protectedChordPressed + 256, false);
    std::fill(g_protectedChordPreexisting, g_protectedChordPreexisting + 256, false);
    std::fill(g_protectedChordSwallowed, g_protectedChordSwallowed + 256, false);
    g_protectedChordMousePressed = 0;
    g_protectedChordMousePreexisting = 0;
    g_protectedChordMouseSwallowed = 0;
    g_protectedChordCurrentSideModifiers = 0;
    g_protectedChordSeenSideModifiers = 0;
    g_protectedChordCaptureStarted = false;
}

static bool AcquireProtectedChordProcessLockLocked() {
    if (g_protectedChordProcessLock) return true;

    HANDLE lockHandle = CreateSemaphoreW(
        NULL,
        1,
        1,
        L"Local\\QuickLauncher.ProtectedChordCapture.v2");
    if (!lockHandle) {
        g_lastHookError = GetLastError();
        return false;
    }

    DWORD waitResult = WaitForSingleObject(lockHandle, 0);
    if (waitResult != WAIT_OBJECT_0) {
        g_lastHookError = waitResult == WAIT_TIMEOUT ? ERROR_BUSY : GetLastError();
        CloseHandle(lockHandle);
        return false;
    }

    g_protectedChordProcessLock = lockHandle;
    return true;
}

static void ReleaseProtectedChordProcessLockLocked() {
    if (!g_protectedChordProcessLock) return;
    if (!ReleaseSemaphore(g_protectedChordProcessLock, 1, NULL)) {
        g_lastHookError = GetLastError();
    }
    CloseHandle(g_protectedChordProcessLock);
    g_protectedChordProcessLock = NULL;
}

static bool AnyProtectedChordInputPressedLocked() {
    if (g_protectedChordMousePressed != 0) return true;
    for (bool pressed : g_protectedChordPressed) {
        if (pressed) return true;
    }
    return false;
}

static void StopProtectedChordCaptureLocked() {
    g_protectedChordCaptureEnabled = false;
    g_protectedChordCaptureFlags = 0;
    g_protectedChordCaptureCallback = nullptr;
    ResetProtectedChordCaptureStateLocked();
    ReleaseProtectedChordProcessLockLocked();
    ReleaseCaptureMode(CAPTURE_MODE_PROTECTED_CHORD);
}

static bool ProtectedChordCaptureTimedOutLocked() {
    DWORD timeoutMs = g_protectedChordCaptureTimeoutMs.load();
    if (timeoutMs == 0) return false;
    DWORD elapsed = GetTickCount() - g_protectedChordCaptureStartedTick.load();
    if (elapsed <= timeoutMs) return false;
    StopProtectedChordCaptureLocked();
    return true;
}

static bool RuntimeTriggerSuppressedByCapture() {
    if (g_protectedChordCaptureEnabled.load()) {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        if (g_protectedChordCaptureEnabled.load() &&
            !ProtectedChordCaptureTimedOutLocked()) {
            return true;
        }
    }
    if (g_hotkeyCaptureEnabled.load()) {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        if (g_hotkeyCaptureEnabled.load()) {
            DWORD timeoutMs = g_hotkeyCaptureTimeoutMs.load();
            DWORD elapsed = GetTickCount() - g_hotkeyCaptureStartedTick.load();
            if (timeoutMs == 0 || elapsed <= timeoutMs) {
                return true;
            }
            StopHotkeyCaptureLocked();
        }
    }
    return g_inputCaptureActive.load();
}

static bool HandleProtectedChordKeyboard(int vk, WPARAM wParam, KBDLLHOOKSTRUCT* keyboard) {
    if (!g_protectedChordCaptureEnabled.load() ||
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_KEYBOARD) == 0) {
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        if (!g_protectedChordCaptureEnabled.load() ||
            ProtectedChordCaptureTimedOutLocked()) {
            return false;
        }
    }

    bool injected = keyboard &&
        (keyboard->flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED)) != 0;
    if (injected &&
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_INCLUDE_INJECTED) == 0) {
        LogProtectedCaptureEvent(
            "keyboard_ignored",
            vk,
            wParam,
            keyboard->flags,
            0,
            0,
            "injected input is disabled for this capture");
        return false;
    }

    LogProtectedCaptureEvent(
        "keyboard_seen",
        vk,
        wParam,
        keyboard ? keyboard->flags : 0,
        0,
        0,
        "entered protected keyboard handler");

    ProtectedChordCaptureCallback eventCallback = nullptr;
    ProtectedChordCaptureCallback completionCallback = nullptr;
    int eventCode = 0;
    int eventModifiers = 0;
    int eventSideModifiers = 0;
    int completionModifiers = 0;
    int completionSideModifiers = 0;
    bool captureWasActive = false;

    {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        if (!g_protectedChordCaptureEnabled.load()) return false;
        captureWasActive = true;
        if (ProtectedChordCaptureTimedOutLocked()) return false;

        int normalizedVk = NormalizeModifierVk(vk, keyboard);
        bool isDown = wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN;
        bool isUp = wParam == WM_KEYUP || wParam == WM_SYSKEYUP;
        if (normalizedVk < 0 || normalizedVk >= 256) return true;

        if (g_protectedChordPreexisting[normalizedVk]) {
            if (isUp) g_protectedChordPreexisting[normalizedVk] = false;
            return false;
        }

        if (isDown) {
            bool repeated = g_protectedChordPressed[normalizedVk];
            g_protectedChordPressed[normalizedVk] = true;
            g_protectedChordSwallowed[normalizedVk] = true;
            int sideBit = HotkeySideBitForVk(normalizedVk);
            if (sideBit) {
                g_protectedChordCurrentSideModifiers |= sideBit;
                g_protectedChordSeenSideModifiers |= sideBit;
            } else if (!repeated) {
                g_protectedChordCaptureStarted = true;
                eventCallback = g_protectedChordCaptureCallback.load();
                eventCode = normalizedVk;
                eventSideModifiers = g_protectedChordCurrentSideModifiers;
                eventModifiers = HotkeyModifiersFromSides(eventSideModifiers);
            }
        } else if (isUp) {
            bool swallowed = g_protectedChordSwallowed[normalizedVk];
            g_protectedChordPressed[normalizedVk] = false;
            g_protectedChordSwallowed[normalizedVk] = false;
            int sideBit = HotkeySideBitForVk(normalizedVk);
            if (sideBit) g_protectedChordCurrentSideModifiers &= ~sideBit;
            if (!swallowed) return false;

            if (g_protectedChordCaptureStarted && !AnyProtectedChordInputPressedLocked()) {
                completionCallback = g_protectedChordCaptureCallback.load();
                completionSideModifiers = g_protectedChordSeenSideModifiers;
                completionModifiers = HotkeyModifiersFromSides(completionSideModifiers);
                g_protectedChordCaptureEnabled = false;
                g_protectedChordCaptureFlags = 0;
                ResetProtectedChordCaptureStateLocked();
                ReleaseProtectedChordProcessLockLocked();
                ReleaseCaptureMode(CAPTURE_MODE_PROTECTED_CHORD);
            }
        }
    }

    if (eventCallback) {
        LogProtectedCaptureEvent(
            "keyboard_emit",
            eventCode,
            wParam,
            keyboard ? keyboard->flags : 0,
            eventModifiers,
            eventSideModifiers,
            "queue main key callback");
        InvokeProtectedChordCaptureCallbackAsync(
            eventCallback,
            eventCode,
            eventModifiers,
            eventSideModifiers);
    }
    if (completionCallback) {
        LogProtectedCaptureEvent(
            "keyboard_complete",
            0,
            wParam,
            keyboard ? keyboard->flags : 0,
            completionModifiers,
            completionSideModifiers,
            "queue automatic completion callback");
        InvokeProtectedChordCaptureCallbackAsync(
            completionCallback,
            0,
            completionModifiers,
            completionSideModifiers);
    }
    return captureWasActive;
}

static int MouseButtonFromMessage(WPARAM wParam, const MSLLHOOKSTRUCT* mouse) {
    if (wParam == WM_LBUTTONDOWN || wParam == WM_LBUTTONUP) return 1;
    if (wParam == WM_RBUTTONDOWN || wParam == WM_RBUTTONUP) return 2;
    if (wParam == WM_MBUTTONDOWN || wParam == WM_MBUTTONUP) return 4;
    if (wParam == WM_XBUTTONDOWN || wParam == WM_XBUTTONUP) {
        return mouse && HIWORD(mouse->mouseData) == XBUTTON1 ? 8 : 16;
    }
    return 0;
}

static bool HandleProtectedChordMouse(WPARAM wParam, MSLLHOOKSTRUCT* mouse) {
    if (!g_protectedChordCaptureEnabled.load() ||
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_MOUSE_BUTTON) == 0) {
        return false;
    }

    int button = MouseButtonFromMessage(wParam, mouse);
    if (button == 0) return false;
    {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        if (!g_protectedChordCaptureEnabled.load() ||
            ProtectedChordCaptureTimedOutLocked()) {
            return false;
        }
    }
    bool injected = mouse &&
        (mouse->flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED)) != 0;
    if (injected &&
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_INCLUDE_INJECTED) == 0) {
        LogProtectedCaptureEvent(
            "mouse_ignored",
            -button,
            wParam,
            mouse->flags,
            0,
            0,
            "injected input is disabled for this capture");
        return false;
    }
    LogProtectedCaptureEvent(
        "mouse_seen",
        -button,
        wParam,
        mouse ? mouse->flags : 0,
        0,
        0,
        "entered protected mouse handler");
    bool isDown = wParam == WM_LBUTTONDOWN || wParam == WM_RBUTTONDOWN ||
                  wParam == WM_MBUTTONDOWN || wParam == WM_XBUTTONDOWN;
    bool isUp = wParam == WM_LBUTTONUP || wParam == WM_RBUTTONUP ||
                wParam == WM_MBUTTONUP || wParam == WM_XBUTTONUP;
    ProtectedChordCaptureCallback eventCallback = nullptr;
    ProtectedChordCaptureCallback completionCallback = nullptr;
    int eventModifiers = 0;
    int eventSideModifiers = 0;
    int completionModifiers = 0;
    int completionSideModifiers = 0;
    bool captureWasActive = false;

    {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        if (!g_protectedChordCaptureEnabled.load()) return false;
        captureWasActive = true;
        if (ProtectedChordCaptureTimedOutLocked()) return false;

        if ((g_protectedChordMousePreexisting & button) != 0) {
            if (isUp) g_protectedChordMousePreexisting &= ~button;
            return false;
        }

        if (isDown) {
            bool repeated = (g_protectedChordMousePressed & button) != 0;
            g_protectedChordMousePressed |= button;
            g_protectedChordMouseSwallowed |= button;
            if (!repeated) {
                g_protectedChordCaptureStarted = true;
                eventSideModifiers = CurrentSideModifiers();
                g_protectedChordSeenSideModifiers |= eventSideModifiers;
                eventModifiers = HotkeyModifiersFromSides(eventSideModifiers);
                eventCallback = g_protectedChordCaptureCallback.load();
            }
        } else if (isUp) {
            bool swallowed = (g_protectedChordMouseSwallowed & button) != 0;
            g_protectedChordMousePressed &= ~button;
            g_protectedChordMouseSwallowed &= ~button;
            if (!swallowed) return false;
            if (g_protectedChordCaptureStarted && !AnyProtectedChordInputPressedLocked()) {
                completionCallback = g_protectedChordCaptureCallback.load();
                completionSideModifiers = g_protectedChordSeenSideModifiers;
                completionModifiers = HotkeyModifiersFromSides(completionSideModifiers);
                g_protectedChordCaptureEnabled = false;
                g_protectedChordCaptureFlags = 0;
                ResetProtectedChordCaptureStateLocked();
                ReleaseProtectedChordProcessLockLocked();
                ReleaseCaptureMode(CAPTURE_MODE_PROTECTED_CHORD);
            }
        }
    }

    if (eventCallback) {
        LogProtectedCaptureEvent(
            "mouse_emit",
            -button,
            wParam,
            mouse ? mouse->flags : 0,
            eventModifiers,
            eventSideModifiers,
            "queue mouse button callback");
        InvokeProtectedChordCaptureCallbackAsync(
            eventCallback,
            -button,
            eventModifiers,
            eventSideModifiers);
    }
    if (completionCallback) {
        LogProtectedCaptureEvent(
            "mouse_complete",
            0,
            wParam,
            mouse ? mouse->flags : 0,
            completionModifiers,
            completionSideModifiers,
            "queue automatic completion callback");
        InvokeProtectedChordCaptureCallbackAsync(
            completionCallback,
            0,
            completionModifiers,
            completionSideModifiers);
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
    } else if (ev.type == CallbackEvent::TaskbarDoubleClick) {
        MouseCallback callback = g_taskbarDoubleClickCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback(ev.x, ev.y))
    } else if (ev.type == CallbackEvent::GlobalHotkey) {
        KeyboardCallback callback = g_hotkeyCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback())
    } else if (ev.type == CallbackEvent::HotkeyCapture && ev.hotkeyCaptureCallback) {
        SAFE_INVOKE_CALLBACK(ev.hotkeyCaptureCallback(ev.vkCode, ev.modifiers, ev.sideModifiers))
    } else if (ev.type == CallbackEvent::ProtectedChordCapture && ev.protectedChordCaptureCallback) {
        LogProtectedCaptureEvent(
            "callback_invoke",
            ev.vkCode,
            0,
            0,
            ev.modifiers,
            ev.sideModifiers,
            "native callback thread invoking Python callback");
        SAFE_INVOKE_CALLBACK(ev.protectedChordCaptureCallback(ev.vkCode, ev.modifiers, ev.sideModifiers))
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
    EnqueueCallbackEvent(CallbackEvent{type, 0, 0, nullptr, nullptr, 0, 0, 0});
}

static void InvokeMouseCallbackAsync(CallbackEvent::Type type, int x, int y) {
    EnqueueCallbackEvent(CallbackEvent{type, x, y, nullptr, nullptr, 0, 0, 0});
}

static void InvokeHotkeyCaptureCallbackAsync(HotkeyCaptureCallback callback, int vkCode, int modifiers, int sideModifiers) {
    if (!callback) return;
    EnqueueCallbackEvent(CallbackEvent{
        CallbackEvent::HotkeyCapture,
        0,
        0,
        callback,
        nullptr,
        vkCode,
        modifiers,
        sideModifiers,
    });
}

static void InvokeProtectedChordCaptureCallbackAsync(
    ProtectedChordCaptureCallback callback,
    int inputCode,
    int modifiers,
    int sideModifiers)
{
    if (!callback) return;
    EnqueueCallbackEvent(CallbackEvent{
        CallbackEvent::ProtectedChordCapture,
        0,
        0,
        nullptr,
        callback,
        inputCode,
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

    if (ctx.running.load() && ctx.threadAlive.load()) {
        if (mouseCb) g_mouseCallback = mouseCb;
        if (kbdCb) g_altDoubleTapCallback = kbdCb;
        bool installed = ctx.hook != NULL || (mouseCb && g_rawInputActive.load());
        ctx.installing = false;
        return installed;
    }

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

    bool installed = ctx.hook != NULL || (mouseCb && g_rawInputActive.load());
    if (installed) {
        if (mouseCb) g_mouseCallback = mouseCb;
        if (kbdCb) g_altDoubleTapCallback = kbdCb;
    }
    ctx.installing = false;
    return installed;
}

// 通用钩子卸载：通知线程退出、清理句柄
static bool UninstallHookGeneric(HookContext& ctx) {
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
            return false;
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
    return !ctx.threadAlive.load();
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

static std::string GetCaptureDebugLogPath() {
    static std::string path;
    if (!path.empty()) return path;

    HMODULE module = NULL;
    char modulePath[MAX_PATH] = {0};
    if (GetModuleHandleExA(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCSTR>(&GetCaptureDebugLogPath),
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
    path += "capture_debug.log";
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

static const char* CaptureMessageName(WPARAM message) {
    switch (message) {
        case WM_KEYDOWN: return "WM_KEYDOWN";
        case WM_KEYUP: return "WM_KEYUP";
        case WM_SYSKEYDOWN: return "WM_SYSKEYDOWN";
        case WM_SYSKEYUP: return "WM_SYSKEYUP";
        case WM_LBUTTONDOWN: return "WM_LBUTTONDOWN";
        case WM_LBUTTONUP: return "WM_LBUTTONUP";
        case WM_RBUTTONDOWN: return "WM_RBUTTONDOWN";
        case WM_RBUTTONUP: return "WM_RBUTTONUP";
        case WM_MBUTTONDOWN: return "WM_MBUTTONDOWN";
        case WM_MBUTTONUP: return "WM_MBUTTONUP";
        case WM_XBUTTONDOWN: return "WM_XBUTTONDOWN";
        case WM_XBUTTONUP: return "WM_XBUTTONUP";
        default: return "NONE";
    }
}

static void WriteCaptureDebugEvent(const CaptureDebugEvent& ev) {
    std::ostringstream oss;
    oss << ev.time.wYear << "-"
        << (ev.time.wMonth < 10 ? "0" : "") << ev.time.wMonth << "-"
        << (ev.time.wDay < 10 ? "0" : "") << ev.time.wDay << " "
        << (ev.time.wHour < 10 ? "0" : "") << ev.time.wHour << ":"
        << (ev.time.wMinute < 10 ? "0" : "") << ev.time.wMinute << ":"
        << (ev.time.wSecond < 10 ? "0" : "") << ev.time.wSecond << "."
        << ev.time.wMilliseconds
        << " pid=" << ev.processId
        << " tid=" << ev.threadId
        << " phase=" << ev.phase
        << " input=" << ev.inputCode
        << " message=" << CaptureMessageName(ev.message)
        << " flags=0x" << std::hex << ev.flags << std::dec
        << " modifiers=" << ev.modifiers
        << " side_modifiers=" << ev.sideModifiers
        << " detail=\"" << ev.detail << "\""
        << "\n";

    std::ofstream out(GetCaptureDebugLogPath(), std::ios::app);
    if (out) out << oss.str();
}

static DWORD WINAPI DebugLogThreadProc(LPVOID) {
    while (g_debugLogThreadRunning.load()) {
        DWORD result = WaitForSingleObject(g_debugLogEvent, 500);
        if (!g_debugLogThreadRunning.load()) break;
        if (result != WAIT_OBJECT_0) continue;

        std::vector<MouseDebugEvent> events;
        std::vector<CaptureDebugEvent> captureEvents;
        {
            std::lock_guard<std::mutex> lock(g_debugLogMutex);
            events.swap(g_pendingDebugEvents);
            captureEvents.swap(g_pendingCaptureDebugEvents);
        }
        for (const auto& ev : events) {
            WriteMiddleMouseEvent(ev);
        }
        for (const auto& ev : captureEvents) {
            WriteCaptureDebugEvent(ev);
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

static void LogProtectedCaptureEvent(
    const char* phase,
    int inputCode,
    WPARAM message,
    DWORD flags,
    int modifiers,
    int sideModifiers,
    const char* detail)
{
    if (!HookDebugLoggingEnabled()) return;

    CaptureDebugEvent ev = {};
    GetLocalTime(&ev.time);
    ev.processId = GetCurrentProcessId();
    ev.threadId = GetCurrentThreadId();
    ev.inputCode = inputCode;
    ev.message = message;
    ev.flags = flags;
    ev.modifiers = modifiers;
    ev.sideModifiers = sideModifiers;
    lstrcpynA(ev.phase, phase ? phase : "", sizeof(ev.phase));
    lstrcpynA(ev.detail, detail ? detail : "", sizeof(ev.detail));

    EnsureDebugLogThread();
    {
        std::lock_guard<std::mutex> lock(g_debugLogMutex);
        if (g_pendingCaptureDebugEvents.size() > 1024) {
            g_pendingCaptureDebugEvents.erase(
                g_pendingCaptureDebugEvents.begin(),
                g_pendingCaptureDebugEvents.begin() + 512);
        }
        g_pendingCaptureDebugEvents.push_back(ev);
    }
    if (g_debugLogEvent) SetEvent(g_debugLogEvent);
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

static HWND GetCursorTargetWindowForSpecialAppCheck() {
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

static HWND GetForegroundTargetWindowForSpecialAppCheck() {
    HWND hwnd = GetForegroundWindow();
    if (!hwnd) return NULL;
    HWND root = GetAncestor(hwnd, GA_ROOT);
    return root ? root : hwnd;
}

static bool IsSpecialAppWindow(HWND hwnd) {
    std::vector<std::string> appsSnapshot;
    {
        std::lock_guard<std::mutex> lock(g_specialAppsMutex);
        if (g_specialApps.empty()) return false;
        appsSnapshot = g_specialApps;
    }

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

static bool HasSpecialAppsConfigured() {
    std::lock_guard<std::mutex> lock(g_specialAppsMutex);
    return !g_specialApps.empty();
}

// 鼠标触发以指针所在窗口为目标；键盘触发以实际前台窗口为目标。
static bool IsSpecialAppForMouse() {
    return IsSpecialAppWindow(GetCursorTargetWindowForSpecialAppCheck());
}

static bool IsSpecialAppForKeyboard() {
    return IsSpecialAppWindow(GetForegroundTargetWindowForSpecialAppCheck());
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

static bool SingleKeyTriggerConfigEqual(
    int firstMode,
    const std::vector<int>& firstKeys,
    int firstModifiers,
    int secondMode,
    const std::vector<int>& secondKeys,
    int secondModifiers)
{
    return firstMode == 1 &&
           secondMode == 1 &&
           firstKeys.size() == 1 &&
           secondKeys.size() == 1 &&
           firstKeys[0] == secondKeys[0] &&
           firstModifiers == secondModifiers;
}

static void RefreshRegisteredTriggerHotkeys() {
    UnregisterHotKey(NULL, QL_NORMAL_TRIGGER_HOTKEY_ID);
    UnregisterHotKey(NULL, QL_SPECIAL_TRIGGER_HOTKEY_ID);
    g_normalTriggerHotkeyRegistered = false;
    g_specialTriggerHotkeyRegistered = false;

    int normalMode, normalModifiers, specialMode, specialModifiers;
    std::vector<int> normalKeys, specialKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        normalMode = g_normalTriggerMode;
        normalKeys = g_normalTriggerKeys;
        normalModifiers = g_normalTriggerModifiers;
        specialMode = g_specialTriggerMode;
        specialKeys = g_specialTriggerKeys;
        specialModifiers = g_specialTriggerModifiers;
    }

    bool normalEligible = normalMode == 1 && normalKeys.size() == 1;
    bool specialEligible = specialMode == 1 && specialKeys.size() == 1;
    bool hasSpecialApps = HasSpecialAppsConfigured();

    if (!hasSpecialApps) {
        if (normalEligible) {
            bool registered = RegisterHotKey(
                NULL,
                QL_NORMAL_TRIGGER_HOTKEY_ID,
                static_cast<UINT>(normalModifiers) | MOD_NOREPEAT,
                static_cast<UINT>(normalKeys[0]));
            g_normalTriggerHotkeyRegistered = registered;
        }
        return;
    }

    // RegisterHotKey is process-global and cannot be scoped to the active
    // foreground application. Register only when both application contexts
    // use the exact same chord; otherwise the inactive context would still
    // consume its key before the low-level hook can decide whether to trigger.
    if (!normalEligible ||
        !specialEligible ||
        !SingleKeyTriggerConfigEqual(
            normalMode,
            normalKeys,
            normalModifiers,
            specialMode,
            specialKeys,
            specialModifiers)) {
        return;
    }

    bool registered = RegisterHotKey(
        NULL,
        QL_NORMAL_TRIGGER_HOTKEY_ID,
        static_cast<UINT>(normalModifiers) | MOD_NOREPEAT,
        static_cast<UINT>(normalKeys[0]));
    g_normalTriggerHotkeyRegistered = registered;
    g_specialTriggerHotkeyRegistered = registered;
}

static bool IsActiveKeyboardTriggerRegistered(bool isSpecial) {
    return isSpecial
        ? g_specialTriggerHotkeyRegistered.load()
        : g_normalTriggerHotkeyRegistered.load();
}

static bool InvokeKeyboardTriggerCallback() {
    if (g_mousePaused.load() || !g_mouseCallback.load()) return false;

    unsigned long long now = GetTickCount64();
    unsigned long long previous = g_lastKeyboardTriggerCallbackTick.load();
    if (previous != 0 && now - previous <= RAW_FALLBACK_LATE_LL_WINDOW_MS) {
        return false;
    }
    g_lastKeyboardTriggerCallbackTick = now;

    POINT point = {};
    if (!GetCursorPos(&point)) return false;
    InvokeMouseCallbackAsync(CallbackEvent::MouseTrigger, point.x, point.y);
    return true;
}

static bool HandleRegisteredKeyboardTrigger(LPARAM hotkeyData) {
    if (RuntimeTriggerSuppressedByCapture()) {
        return true;
    }

    bool isSpecial = IsSpecialAppForKeyboard();
    int targetMode, targetModifiers;
    std::vector<int> targetKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        targetMode = isSpecial ? g_specialTriggerMode : g_normalTriggerMode;
        targetKeys = isSpecial ? g_specialTriggerKeys : g_normalTriggerKeys;
        targetModifiers = isSpecial ? g_specialTriggerModifiers : g_normalTriggerModifiers;
    }

    int messageModifiers = LOWORD(hotkeyData) & (HOTKEY_MOD_ALT | HOTKEY_MOD_CTRL | HOTKEY_MOD_SHIFT | HOTKEY_MOD_WIN);
    int messageVk = HIWORD(hotkeyData);
    if (targetMode == 1 &&
        targetKeys.size() == 1 &&
        targetKeys[0] == messageVk &&
        targetModifiers == messageModifiers) {
        InvokeKeyboardTriggerCallback();
    }
    return true;
}

static void PollAsyncKeyboardTrigger() {
    if (RuntimeTriggerSuppressedByCapture() ||
        g_mousePaused.load() ||
        !g_mouseCallback.load()) {
        g_asyncKeyboardTriggerLatched = false;
        return;
    }

    int normalMode, normalModifiers, specialMode, specialModifiers;
    std::vector<int> normalKeys, specialKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        normalMode = g_normalTriggerMode;
        normalKeys = g_normalTriggerKeys;
        normalModifiers = g_normalTriggerModifiers;
        specialMode = g_specialTriggerMode;
        specialKeys = g_specialTriggerKeys;
        specialModifiers = g_specialTriggerModifiers;
    }
    if (normalMode != 1 && specialMode != 1) {
        g_asyncKeyboardTriggerLatched = false;
        return;
    }

    static unsigned long long lastSpecialCheckTick = 0;
    static bool cachedSpecial = false;
    unsigned long long now = GetTickCount64();
    if (lastSpecialCheckTick == 0 || now - lastSpecialCheckTick >= 100) {
        cachedSpecial = IsSpecialAppForKeyboard();
        lastSpecialCheckTick = now;
    }

    int targetMode = cachedSpecial ? specialMode : normalMode;
    const std::vector<int>& targetKeys = cachedSpecial ? specialKeys : normalKeys;
    int targetModifiers = cachedSpecial ? specialModifiers : normalModifiers;
    bool matched = targetMode == 1 &&
                   !targetKeys.empty() &&
                   CurrentMouseModifiers() == targetModifiers &&
                   CheckKeysPressed(targetKeys);
    if (!matched) {
        g_asyncKeyboardTriggerLatched = false;
        return;
    }
    if (g_asyncKeyboardTriggerLatched.exchange(true)) return;
    if (IsActiveKeyboardTriggerRegistered(cachedSpecial)) return;
    InvokeKeyboardTriggerCallback();
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
    bool isSpecial = IsSpecialAppForMouse();
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

static bool HookKeyboardKeyPressed(int vk) {
    if (vk < 0 || vk >= 256) return false;
    if (g_keyboardPressed[vk]) return true;
    switch (vk) {
        case VK_SHIFT:
            return g_keyboardPressed[VK_LSHIFT] || g_keyboardPressed[VK_RSHIFT];
        case VK_CONTROL:
            return g_keyboardPressed[VK_LCONTROL] || g_keyboardPressed[VK_RCONTROL];
        case VK_MENU:
            return g_keyboardPressed[VK_LMENU] || g_keyboardPressed[VK_RMENU];
        default:
            return false;
    }
}

static int HookKeyboardModifiers() {
    int modifiers = 0;
    if (HookKeyboardKeyPressed(VK_MENU)) modifiers |= HOTKEY_MOD_ALT;
    if (HookKeyboardKeyPressed(VK_CONTROL)) modifiers |= HOTKEY_MOD_CTRL;
    if (HookKeyboardKeyPressed(VK_SHIFT)) modifiers |= HOTKEY_MOD_SHIFT;
    if (HookKeyboardKeyPressed(VK_LWIN) || HookKeyboardKeyPressed(VK_RWIN)) modifiers |= HOTKEY_MOD_WIN;
    return modifiers;
}

static bool ShouldTriggerRawKeyboard(int vk) {
    if (RuntimeTriggerSuppressedByCapture()) return false;

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

    bool isSpecial = IsSpecialAppForKeyboard();
    int targetMode = isSpecial ? specialMode : normalMode;
    const std::vector<int>& targetKeys = isSpecial ? specialKeys : normalKeys;
    int targetModifiers = isSpecial ? specialMod : normalMod;
    if (IsActiveKeyboardTriggerRegistered(isSpecial)) {
        return false;
    }
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

static bool HandleKeyboardPopupTrigger(int vk, bool isDown, bool isUp, bool wasPressed) {
    if (vk < 0 || vk >= 256) return false;
    if (isUp && g_triggerBlockedKeys[vk]) {
        g_triggerBlockedKeys[vk] = false;
        return true;
    }
    if (!isDown) return false;

    int normalMode, specialMode, normalMod, specialMod;
    std::vector<int> normalKeys, specialKeys;
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        normalMode = g_normalTriggerMode;
        specialMode = g_specialTriggerMode;
        normalKeys = g_normalTriggerKeys;
        specialKeys = g_specialTriggerKeys;
        normalMod = g_normalTriggerModifiers;
        specialMod = g_specialTriggerModifiers;
    }

    bool isSpecial = IsSpecialAppForKeyboard();
    int targetMode = isSpecial ? specialMode : normalMode;
    const std::vector<int>& targetKeys = isSpecial ? specialKeys : normalKeys;
    int targetMod = isSpecial ? specialMod : normalMod;
    if ((targetMode != 1 && targetMode != 2) || targetKeys.empty() || !g_mouseCallback.load()) return false;

    bool isTargetKey = std::find(targetKeys.begin(), targetKeys.end(), vk) != targetKeys.end();
    if (!isTargetKey) return false;

    int currentMod = HookKeyboardModifiers();
    if (currentMod != targetMod) return false;

    if (targetMode == 1 && IsActiveKeyboardTriggerRegistered(isSpecial)) {
        // RegisterHotKey needs the physical key event to reach Windows before it
        // can post WM_HOTKEY back to this thread. Swallowing it here suppresses
        // the registered channel and leaves the trigger silent.
        return false;
    }

    g_triggerBlockedKeys[vk] = true;
    bool allKeysPressed = true;
    for (int targetVk : targetKeys) {
        if (!HookKeyboardKeyPressed(targetVk)) {
            allKeysPressed = false;
            break;
        }
    }
    if (targetMode == 1 && allKeysPressed && !wasPressed) {
        bool rawAlreadyTriggered =
            g_lastRawKeyboardFallbackVk.load() == vk &&
            (GetTickCount64() - g_lastRawKeyboardFallbackTick.load()) <=
                RAW_FALLBACK_LATE_LL_WINDOW_MS;
        if (!rawAlreadyTriggered) {
            InvokeKeyboardTriggerCallback();
        }
    }
    return true;
}

static void InvokeRawInputFallback(int button, int buttonIndex) {
    if (g_mousePaused.load() ||
        !g_mouseCallback.load() ||
        RuntimeTriggerSuppressedByCapture()) {
        return;
    }

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
        if (g_rawConsumedInputCaptureKeyboardCount < g_lowLevelInputCaptureKeyboardCount.load()) {
            ++g_rawConsumedInputCaptureKeyboardCount;
        }
    }

    unsigned long long captureCount = g_lowLevelInputCaptureKeyboardCount.load();
    while (!g_pendingRawKeyboardEvents.empty() &&
           g_rawConsumedInputCaptureKeyboardCount < captureCount) {
        g_pendingRawKeyboardEvents.pop_front();
        ++g_rawConsumedInputCaptureKeyboardCount;
    }

    while (!g_pendingRawKeyboardEvents.empty()) {
        PendingRawKeyboardEvent event = g_pendingRawKeyboardEvents.front();
        g_pendingRawKeyboardEvents.pop_front();
        g_lowLevelKeyboardHealthy = false;
        if (g_inputCaptureActive.load() &&
            (g_inputCaptureFilter.load() & HOOK_CAPTURE_KEYBOARD) != 0) {
            HookInputEvent eventData = {};
            eventData.type = event.down ? HOOK_INPUT_KEY_DOWN : HOOK_INPUT_KEY_UP;
            eventData.flags = event.flags;
            eventData.vkCode = static_cast<unsigned int>(event.vk);
            eventData.scanCode = event.scanCode;
            if (event.down && event.wasPressed) {
                eventData.flags |= HOOK_INPUT_FLAG_REPEAT;
            }
            QueueCapturedInput(eventData);
            NoteInputCaptureKeyboardState(event.vk, event.down);
        }
        if (!event.down || !event.shouldTrigger || g_mousePaused.load()) continue;

        if (!g_mouseCallback.load()) continue;
        g_lastRawKeyboardFallbackVk = event.vk;
        g_lastRawKeyboardFallbackTick = GetTickCount64();
        InvokeKeyboardTriggerCallback();
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
        bool wasPressed = g_rawKeyboardPressed[vk];
        unsigned int eventFlags = 0;
        if (input.data.keyboard.Flags & (RI_KEY_E0 | RI_KEY_E1)) {
            eventFlags |= HOOK_INPUT_FLAG_EXTENDED;
        }
        g_rawKeyboardEventCount.fetch_add(1);
        g_rawKeyboardPressed[vk] = down;
        bool shouldTrigger = down && ShouldTriggerRawKeyboard(vk);
        g_pendingRawKeyboardEvents.push_back(
            PendingRawKeyboardEvent{
                vk,
                static_cast<unsigned int>(input.data.keyboard.MakeCode),
                eventFlags,
                down,
                wasPressed,
                shouldTrigger,
            });

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
    if (message == WM_TIMER && wParam == ASYNC_KEYBOARD_TRIGGER_TIMER) {
        PollInputCaptureKeyboardState();
        PollAsyncKeyboardTrigger();
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
    SetTimer(
        g_rawInputWindow,
        ASYNC_KEYBOARD_TRIGGER_TIMER,
        ASYNC_KEYBOARD_TRIGGER_POLL_MS,
        NULL);
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
        KillTimer(g_rawInputWindow, ASYNC_KEYBOARD_TRIGGER_TIMER);
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

    // 受保护组合录制优先于暂停状态和弹窗触发，确保录制点击不会传给系统或其它程序。
    if (HandleProtectedChordMouse(wParam, pMouse)) {
        return 1;
    }
    if (g_inputCaptureActive.load()) {
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    // Timeout protection - auto-reset if blocked for too long
    if (g_blockedDown && (now - g_lastBlockTime) > BLOCKED_STATE_TIMEOUT) {
        LogMiddleMouseEvent("mouse", wParam, pMouse, "auto_reset_blocked_timeout");
        g_blockedDown = false;
        g_blockedButton = 0;
    }

    // --- 任务栏双击检测 ---
    // 放在 Alt+左键 之前，确保任务栏双击优先级最高
    if (g_taskbarTriggerEnabled.load() && wParam == WM_LBUTTONDOWN) {
        bool ctrlRequired = g_taskbarTriggerCtrl.load();
        bool ctrlHeldNow = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
        if (!ctrlRequired || ctrlHeldNow) {
            bool onTaskbar = IsOnTaskbarTriggerArea(pMouse->pt.x, pMouse->pt.y);
            if (onTaskbar) {
                double dclickNow = GetTime();
                double dclickInterval = dclickNow - g_taskbarDClickLastTime;
                double taskbarDClickInterval = static_cast<double>(
                    ClampTaskbarDoubleClickIntervalMs(g_taskbarDClickIntervalMs.load())) / 1000.0;
                if (HookDebugLoggingEnabled()) {
                    char buf[256];
                    snprintf(buf, sizeof(buf),
                        "[hooks] taskbar click at (%ld,%ld) interval=%.3f limit=%.3f last=%.3f enabled=%d area=%d\n",
                        pMouse->pt.x, pMouse->pt.y, dclickInterval, taskbarDClickInterval,
                        g_taskbarDClickLastTime, (int)g_taskbarTriggerEnabled.load(), (int)onTaskbar);
                    OutputDebugStringA(buf);
                }
                if (dclickInterval < taskbarDClickInterval && g_taskbarDClickLastTime > 0) {
                    if ((dclickNow - g_taskbarDClickLastTrigger) > TASKBAR_DCLICK_COOLDOWN) {
                        g_taskbarDClickLastTrigger = dclickNow;
                        InvokeMouseCallbackAsync(CallbackEvent::TaskbarDoubleClick,
                                                 pMouse->pt.x, pMouse->pt.y);
                    }
                    g_taskbarDClickLastTime = 0.0;
                    return 0;
                }
                g_taskbarDClickLastTime = dclickNow;
            } else {
                g_taskbarDClickLastTime = 0.0;
            }
        } else {
            g_taskbarDClickLastTime = 0.0;
        }
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
    if (CaptureFilterAllows(eventData)) {
        QueueCapturedInput(eventData);
        g_lowLevelInputCaptureKeyboardCount.fetch_add(1);
    }
    NoteInputCaptureKeyboardState(static_cast<int>(keyboard->vkCode), isDown);
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

    // 录制优先于 injected 过滤。部分键盘驱动、远程输入和辅助输入工具
    // 会把真实用户按键标记为 injected，录制窗口仍需捕获并吞掉系统组合键。
    if (HandleProtectedChordKeyboard(vk, wParam, pKbd)) {
        return 1;
    }

    // 旧快捷键录制接口同样保持最高优先级。
    if (HandleHotkeyCapture(vk, wParam, pKbd)) {
        return 1;
    }

    if (pKbd->flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED)) {
        g_injectedKeyboardIgnoredCount.fetch_add(1);
        return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
    }
    g_lowLevelPhysicalKeyboardCount.fetch_add(1);

    bool isAlt = (vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU);
    bool isCtrl = (vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL);
    if (vk >= 0 && vk < 256) {
        if (isDown) g_keyboardPressed[vk] = true;
        if (isUp) g_keyboardPressed[vk] = false;
    }
    if (g_inputCaptureActive.load()) {
        g_altHeld = IsAltPressedNow();
        g_ctrlHeld = IsCtrlPressedNow();
        if (!g_altHeld.load()) {
            g_altTapCount = 0;
            g_otherKeyPressed = false;
        }
        return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
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

            if (HandleKeyboardPopupTrigger(vk, isDown, isUp, wasPressed)) {
                return 1;
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
        if (HandleKeyboardPopupTrigger(vk, isDown, isUp, wasPressed)) {
            return 1;
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
    std::fill(g_triggerBlockedKeys, g_triggerBlockedKeys + 256, false);
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
    RefreshRegisteredTriggerHotkeys();

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
        if (msg.message == WM_QL_REFRESH_TRIGGER_HOTKEYS) {
            RefreshRegisteredTriggerHotkeys();
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
        if (msg.message == WM_HOTKEY &&
            (msg.wParam == QL_NORMAL_TRIGGER_HOTKEY_ID ||
             msg.wParam == QL_SPECIAL_TRIGGER_HOTKEY_ID)) {
            HandleRegisteredKeyboardTrigger(msg.lParam);
            continue;
        }
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    UnregisterHotKey(NULL, QL_GLOBAL_HOTKEY_ID);
    UnregisterHotKey(NULL, QL_NORMAL_TRIGGER_HOTKEY_ID);
    UnregisterHotKey(NULL, QL_SPECIAL_TRIGGER_HOTKEY_ID);
    KillTimer(NULL, QL_CAPTURE_TIMER_ID);
    g_registeredHotkeyActive = false;
    g_normalTriggerHotkeyRegistered = false;
    g_specialTriggerHotkeyRegistered = false;
    if (g_keyboardHook) {
        UnhookWindowsHookEx(g_keyboardHook);
        g_keyboardHook = NULL;
    }
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
    std::fill(g_triggerBlockedKeys, g_triggerBlockedKeys + 256, false);
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
    PurgeCallbackEvents(CallbackEvent::MouseTrigger);
    WaitForCallbacksToDrain();
    HookContext ctx{
        g_mouseHook, g_mouseThreadId, g_mouseThreadHandle,
        g_mouseReadyEvent, g_mouseExitedEvent,
        g_mouseRunning, g_mouseInstalling, g_mouseThreadAlive
    };
    bool result = InstallHookGeneric(ctx, MouseHookThread, callback, nullptr);
    return result && g_mouseThreadAlive.load() && (g_mouseHook != NULL || g_rawInputActive.load());
}

void UninstallMouseHook() {
    if (g_protectedChordCaptureEnabled.load() &&
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_MOUSE_BUTTON) != 0) {
        StopProtectedChordCapture();
    }
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
    bool stopped = UninstallHookGeneric(ctx);
    PurgeCallbackEvents(CallbackEvent::MouseTrigger);
    PurgeCallbackEvents(CallbackEvent::AltDoubleClick);
    WaitForCallbacksToDrain();
    if (stopped) {
        g_mouseCallback = nullptr;
        g_altDoubleClickCallback = nullptr;
    }
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
    if (g_hotkeyCaptureEnabled.load()) {
        StopHotkeyCapture();
    }
    if (g_protectedChordCaptureEnabled.load() &&
        (g_protectedChordCaptureFlags.load() & HOOK_CHORD_CAPTURE_KEYBOARD) != 0) {
        StopProtectedChordCapture();
    }
    if (g_inputCaptureActive.load() &&
        (g_inputCaptureFilter.load() & HOOK_CAPTURE_KEYBOARD) != 0) {
        StopInputCapture();
    }
    HookContext ctx{
        g_keyboardHook, g_keyboardThreadId, g_keyboardThreadHandle,
        g_keyboardReadyEvent, g_keyboardExitedEvent,
        g_keyboardRunning, g_keyboardInstalling, g_keyboardThreadAlive
    };
    bool stopped = UninstallHookGeneric(ctx);
    PurgeCallbackEvents(CallbackEvent::AltDoubleTap);
    PurgeCallbackEvents(CallbackEvent::GlobalHotkey);
    PurgeCallbackEvents(CallbackEvent::HotkeyCapture);
    WaitForCallbacksToDrain();
    if (stopped) g_altDoubleTapCallback = nullptr;
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
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

static int ParseNamedVirtualKey(const std::string& token) {
    if (token.length() == 1 && token[0] >= 'a' && token[0] <= 'z') {
        return static_cast<int>(std::toupper(static_cast<unsigned char>(token[0])));
    }
    if (token.length() == 1 && token[0] >= '0' && token[0] <= '9') {
        return static_cast<int>(token[0]);
    }
    if (token.length() >= 2 && token[0] == 'f') {
        int n = atoi(token.substr(1).c_str());
        if (n >= 1 && n <= 24) return VK_F1 + (n - 1);
    }
    if (token.rfind("vk_", 0) == 0 && token.length() == 5) {
        char* end = nullptr;
        long parsed = strtol(token.substr(3).c_str(), &end, 16);
        if (end && *end == '\0' && parsed > 0 && parsed <= 0xFF) {
            return static_cast<int>(parsed);
        }
    }

    struct NamedVk {
        const char* name;
        int vk;
    };
    static const NamedVk namedKeys[] = {
        {"backspace", VK_BACK}, {"back", VK_BACK}, {"tab", VK_TAB},
        {"clear", VK_CLEAR}, {"enter", VK_RETURN}, {"return", VK_RETURN},
        {"pause", VK_PAUSE}, {"capslock", VK_CAPITAL}, {"caps", VK_CAPITAL}, {"esc", VK_ESCAPE},
        {"escape", VK_ESCAPE}, {"space", VK_SPACE}, {"pageup", VK_PRIOR},
        {"pgup", VK_PRIOR}, {"pagedown", VK_NEXT}, {"pgdn", VK_NEXT},
        {"end", VK_END}, {"home", VK_HOME}, {"left", VK_LEFT},
        {"up", VK_UP}, {"right", VK_RIGHT}, {"down", VK_DOWN},
        {"select", VK_SELECT}, {"print", VK_PRINT}, {"execute", VK_EXECUTE},
        {"printscreen", VK_SNAPSHOT}, {"prtscr", VK_SNAPSHOT},
        {"insert", VK_INSERT}, {"ins", VK_INSERT}, {"delete", VK_DELETE},
        {"del", VK_DELETE}, {"help", VK_HELP}, {"apps", VK_APPS},
        {"sleep", VK_SLEEP}, {"num0", VK_NUMPAD0}, {"numpad0", VK_NUMPAD0},
        {"num1", VK_NUMPAD1}, {"numpad1", VK_NUMPAD1},
        {"num2", VK_NUMPAD2}, {"numpad2", VK_NUMPAD2},
        {"num3", VK_NUMPAD3}, {"numpad3", VK_NUMPAD3},
        {"num4", VK_NUMPAD4}, {"numpad4", VK_NUMPAD4},
        {"num5", VK_NUMPAD5}, {"numpad5", VK_NUMPAD5},
        {"num6", VK_NUMPAD6}, {"numpad6", VK_NUMPAD6},
        {"num7", VK_NUMPAD7}, {"numpad7", VK_NUMPAD7},
        {"num8", VK_NUMPAD8}, {"numpad8", VK_NUMPAD8},
        {"num9", VK_NUMPAD9}, {"numpad9", VK_NUMPAD9},
        {"multiply", VK_MULTIPLY}, {"add", VK_ADD}, {"separator", VK_SEPARATOR},
        {"subtract", VK_SUBTRACT}, {"decimal", VK_DECIMAL}, {"divide", VK_DIVIDE},
        {"numlock", VK_NUMLOCK}, {"scrolllock", VK_SCROLL},
        {"browserback", VK_BROWSER_BACK}, {"browserforward", VK_BROWSER_FORWARD},
        {"browserrefresh", VK_BROWSER_REFRESH}, {"browserstop", VK_BROWSER_STOP},
        {"browsersearch", VK_BROWSER_SEARCH}, {"browserfavorites", VK_BROWSER_FAVORITES},
        {"browserhome", VK_BROWSER_HOME}, {"volumemute", VK_VOLUME_MUTE},
        {"mute", VK_VOLUME_MUTE}, {"volumedown", VK_VOLUME_DOWN},
        {"volumeup", VK_VOLUME_UP}, {"medianext", VK_MEDIA_NEXT_TRACK},
        {"mediaprev", VK_MEDIA_PREV_TRACK}, {"mediastop", VK_MEDIA_STOP},
        {"mediaplay", VK_MEDIA_PLAY_PAUSE}, {"playpause", VK_MEDIA_PLAY_PAUSE},
        {"launchmail", VK_LAUNCH_MAIL}, {"launchmedia", VK_LAUNCH_MEDIA_SELECT},
        {"launchapp1", VK_LAUNCH_APP1}, {"launchapp2", VK_LAUNCH_APP2},
        {";", VK_OEM_1}, {"=", VK_OEM_PLUS}, {",", VK_OEM_COMMA},
        {"-", VK_OEM_MINUS}, {".", VK_OEM_PERIOD}, {"/", VK_OEM_2},
        {"`", VK_OEM_3}, {"[", VK_OEM_4}, {"\\", VK_OEM_5},
        {"]", VK_OEM_6}, {"'", VK_OEM_7}, {"processkey", VK_PROCESSKEY},
        {"packet", VK_PACKET}, {"attn", VK_ATTN}, {"crsel", VK_CRSEL},
        {"exsel", VK_EXSEL}, {"ereof", VK_EREOF}, {"play", VK_PLAY},
        {"zoom", VK_ZOOM}, {"noname", VK_NONAME}, {"pa1", VK_PA1},
        {"oemclear", VK_OEM_CLEAR},
    };
    for (const NamedVk& named : namedKeys) {
        if (token == named.name) return named.vk;
    }
    return 0;
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
            if (token == "alt" || token == "lalt" || token == "ralt") {
                *modifiers |= 1;
            } else if (token == "ctrl" || token == "control" || token == "lctrl" || token == "rctrl") {
                *modifiers |= 2;
            } else if (token == "shift" || token == "lshift" || token == "rshift") {
                *modifiers |= 4;
            } else if (token == "win" || token == "windows" || token == "cmd" ||
                       token == "meta" || token == "super" || token == "lwin" || token == "rwin") {
                *modifiers |= 8;
            } else {
                int parsedVk = ParseNamedVirtualKey(token);
                if (parsedVk == 0 || *vk != 0) return false;
                *vk = parsedVk;
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
    if (!TryClaimCaptureMode(CAPTURE_MODE_HOTKEY)) return false;

    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureEnabled = false;
    }
    PurgeCallbackEvents(CallbackEvent::HotkeyCapture);
    WaitForCallbacksToDrain();

    std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
    ResetHotkeyCaptureStateLocked();
    for (int vk = 0; vk < 256; ++vk) {
        g_hotkeyCapturePreexisting[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;
    }
    g_hotkeyCaptureCallback = callback;
    g_hotkeyCaptureTimeoutMs = timeoutMs > 0 ? static_cast<DWORD>(timeoutMs) : 10000;
    g_hotkeyCaptureStartedTick = GetTickCount();
    g_hotkeyCaptureEnabled = true;
    if (!PostThreadMessage(
        g_keyboardThreadId,
        WM_QL_START_CAPTURE_TIMER,
        static_cast<WPARAM>(g_hotkeyCaptureTimeoutMs.load()),
        0)) {
        g_lastHookError = GetLastError();
    }
    return true;
}

HOOKS_API void StopHotkeyCapture() {
    {
        std::lock_guard<std::mutex> lock(g_hotkeyCaptureMutex);
        g_hotkeyCaptureEnabled = false;
        ResetHotkeyCaptureStateLocked();
        ReleaseCaptureMode(CAPTURE_MODE_HOTKEY);
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
    DWORD timeoutMs = g_hotkeyCaptureTimeoutMs.load();
    if (g_hotkeyCaptureEnabled.load() && timeoutMs > 0) {
        DWORD elapsed = GetTickCount() - g_hotkeyCaptureStartedTick.load();
        if (elapsed > timeoutMs) {
            StopHotkeyCapture();
        }
    }
    return g_hotkeyCaptureEnabled.load();
}

HOOKS_API bool StartProtectedChordCapture(
    ProtectedChordCaptureCallback callback,
    unsigned int captureFlags,
    int timeoutMs)
{
    LogProtectedCaptureEvent(
        "capture_start_request",
        0,
        0,
        0,
        static_cast<int>(captureFlags),
        0,
        "StartProtectedChordCapture called");
    unsigned int supportedFlags =
        HOOK_CHORD_CAPTURE_KEYBOARD |
        HOOK_CHORD_CAPTURE_MOUSE_BUTTON |
        HOOK_CHORD_CAPTURE_INCLUDE_INJECTED;
    captureFlags &= supportedFlags;
    if (!callback || captureFlags == 0) {
        g_lastHookError = ERROR_INVALID_PARAMETER;
        return false;
    }
    if ((captureFlags & HOOK_CHORD_CAPTURE_KEYBOARD) != 0 && !IsKeyboardHookInstalled()) {
        g_lastHookError = ERROR_NOT_READY;
        return false;
    }
    if ((captureFlags & HOOK_CHORD_CAPTURE_MOUSE_BUTTON) != 0 && !IsMouseHookInstalled()) {
        g_lastHookError = ERROR_NOT_READY;
        return false;
    }
    if (!TryClaimCaptureMode(CAPTURE_MODE_PROTECTED_CHORD)) return false;

    PurgeCallbackEvents(CallbackEvent::ProtectedChordCapture);
    WaitForCallbacksToDrain();
    std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
    if (!AcquireProtectedChordProcessLockLocked()) {
        ReleaseCaptureMode(CAPTURE_MODE_PROTECTED_CHORD);
        LogProtectedCaptureEvent(
            "capture_rejected",
            0,
            0,
            0,
            static_cast<int>(captureFlags),
            0,
            "another process owns protected capture");
        return false;
    }
    ResetProtectedChordCaptureStateLocked();
    for (int vk = 0; vk < 256; ++vk) {
        g_protectedChordPreexisting[vk] = (GetAsyncKeyState(vk) & 0x8000) != 0;
    }
    if (GetAsyncKeyState(VK_LBUTTON) & 0x8000) g_protectedChordMousePreexisting |= 1;
    if (GetAsyncKeyState(VK_RBUTTON) & 0x8000) g_protectedChordMousePreexisting |= 2;
    if (GetAsyncKeyState(VK_MBUTTON) & 0x8000) g_protectedChordMousePreexisting |= 4;
    if (GetAsyncKeyState(VK_XBUTTON1) & 0x8000) g_protectedChordMousePreexisting |= 8;
    if (GetAsyncKeyState(VK_XBUTTON2) & 0x8000) g_protectedChordMousePreexisting |= 16;
    g_protectedChordCaptureCallback = callback;
    g_protectedChordCaptureFlags = captureFlags;
    g_protectedChordCaptureTimeoutMs = timeoutMs > 0 ? static_cast<DWORD>(timeoutMs) : 10000;
    g_protectedChordCaptureStartedTick = GetTickCount();
    g_protectedChordCaptureEnabled = true;
    g_lastHookError = ERROR_SUCCESS;
    LogProtectedCaptureEvent(
        "capture_started",
        0,
        0,
        0,
        static_cast<int>(captureFlags),
        0,
        "protected capture is active");
    return true;
}

HOOKS_API void StopProtectedChordCapture() {
    LogProtectedCaptureEvent(
        "capture_stop_request",
        0,
        0,
        0,
        static_cast<int>(g_protectedChordCaptureFlags.load()),
        0,
        "StopProtectedChordCapture called");
    {
        std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
        g_protectedChordCaptureEnabled = false;
        ResetProtectedChordCaptureStateLocked();
        ReleaseProtectedChordProcessLockLocked();
        ReleaseCaptureMode(CAPTURE_MODE_PROTECTED_CHORD);
    }
    PurgeCallbackEvents(CallbackEvent::ProtectedChordCapture);
    WaitForCallbacksToDrain();
    std::lock_guard<std::mutex> lock(g_protectedChordCaptureMutex);
    g_protectedChordCaptureCallback = nullptr;
    g_protectedChordCaptureFlags = 0;
}

HOOKS_API bool IsProtectedChordCaptureActive() {
    DWORD timeoutMs = g_protectedChordCaptureTimeoutMs.load();
    if (g_protectedChordCaptureEnabled.load() && timeoutMs > 0) {
        DWORD elapsed = GetTickCount() - g_protectedChordCaptureStartedTick.load();
        if (elapsed > timeoutMs) {
            StopProtectedChordCapture();
        }
    }
    return g_protectedChordCaptureEnabled.load();
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

static void ApplyAbsoluteMousePosition(const HookMacroEvent& eventData, MOUSEINPUT* mouseInput) {
    if (!mouseInput || (eventData.flags & HOOK_INPUT_FLAG_ABSOLUTE) == 0) return;
    int left = GetSystemMetrics(SM_XVIRTUALSCREEN);
    int top = GetSystemMetrics(SM_YVIRTUALSCREEN);
    int width = std::max(1, GetSystemMetrics(SM_CXVIRTUALSCREEN));
    int height = std::max(1, GetSystemMetrics(SM_CYVIRTUALSCREEN));
    long long dx = static_cast<long long>(eventData.x - left) * 65535LL /
        std::max(1, width - 1);
    long long dy = static_cast<long long>(eventData.y - top) * 65535LL /
        std::max(1, height - 1);
    mouseInput->dx = static_cast<LONG>(std::clamp(dx, 0LL, 65535LL));
    mouseInput->dy = static_cast<LONG>(std::clamp(dy, 0LL, 65535LL));
    mouseInput->dwFlags |= MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
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
            ApplyAbsoluteMousePosition(eventData, &input->mi);
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
    if (!TryClaimCaptureMode(CAPTURE_MODE_INPUT)) return false;
    if (!EnsureInputCaptureThread()) {
        ReleaseCaptureMode(CAPTURE_MODE_INPUT);
        return false;
    }

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
    g_lowLevelInputCaptureKeyboardCount = 0;
    g_rawConsumedInputCaptureKeyboardCount = 0;
    if (needsKeyboard) {
        ResetInputCaptureKeyboardPollState();
    }
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
    std::fill(g_inputCaptureKeyboardPressed, g_inputCaptureKeyboardPressed + 256, false);
    g_lowLevelInputCaptureKeyboardCount = 0;
    g_rawConsumedInputCaptureKeyboardCount = 0;
    ReleaseCaptureMode(CAPTURE_MODE_INPUT);
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
    {
        std::lock_guard<std::mutex> lock(g_specialAppsMutex);
        g_specialApps.clear();
        if (apps && count > 0) {
            for (int i = 0; i < count; i++) {
                if (apps[i]) {
                    g_specialApps.push_back(apps[i]);
                }
            }
        }
    }
    g_asyncKeyboardTriggerLatched = false;
    if (g_keyboardThreadId != 0) {
        PostThreadMessage(g_keyboardThreadId, WM_QL_REFRESH_TRIGGER_HOTKEYS, 0, 0);
    }
}

HOOKS_API void ClearSpecialApps() {
    {
        std::lock_guard<std::mutex> lock(g_specialAppsMutex);
        g_specialApps.clear();
    }
    g_asyncKeyboardTriggerLatched = false;
    if (g_keyboardThreadId != 0) {
        PostThreadMessage(g_keyboardThreadId, WM_QL_REFRESH_TRIGGER_HOTKEYS, 0, 0);
    }
}

HOOKS_API void SetTriggerConfig(int normalButton, int normalModifiers, int specialButton, int specialModifiers) {
    {
        std::lock_guard<std::mutex> lock(g_triggerConfigMutex);
        g_normalTriggerMode = 0;
        g_normalTriggerButton = normalButton;
        g_normalTriggerKeys.clear();
        g_normalTriggerModifiers = normalModifiers;
        g_specialTriggerMode = 0;
        g_specialTriggerButton = specialButton;
        g_specialTriggerKeys.clear();
        g_specialTriggerModifiers = specialModifiers;
    }
    g_asyncKeyboardTriggerLatched = false;
    if (g_keyboardThreadId != 0) {
        PostThreadMessage(g_keyboardThreadId, WM_QL_REFRESH_TRIGGER_HOTKEYS, 0, 0);
    }
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
                if (vk > 0 &&
                    vk <= 0xFF &&
                    std::find(parsed.begin(), parsed.end(), vk) == parsed.end()) {
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
    {
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
    g_asyncKeyboardTriggerLatched = false;
    if (g_keyboardThreadId != 0) {
        PostThreadMessage(g_keyboardThreadId, WM_QL_REFRESH_TRIGGER_HOTKEYS, 0, 0);
    }
}

HOOKS_API bool IsNormalTriggerHotkeyRegistered() {
    return g_normalTriggerHotkeyRegistered.load();
}

HOOKS_API bool IsSpecialTriggerHotkeyRegistered() {
    return g_specialTriggerHotkeyRegistered.load();
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
           HOOKS_CAP_MACRO_PLAYBACK |
           HOOKS_CAP_PROTECTED_CHORD_CAPTURE;
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

static bool IsThreadHandleStopped(HANDLE threadHandle) {
    return threadHandle == NULL || WaitForSingleObject(threadHandle, 0) == WAIT_OBJECT_0;
}

HOOKS_API bool AreHooksQuiescent() {
    return !g_mouseThreadAlive.load() &&
           !g_keyboardThreadAlive.load() &&
           !g_mouseRunning.load() &&
           !g_keyboardRunning.load() &&
           !g_callbackThreadRunning.load() &&
           !g_inputCaptureThreadRunning.load() &&
           !g_debugLogThreadRunning.load() &&
           !g_inputCaptureActive.load() &&
           !g_protectedChordCaptureEnabled.load() &&
           g_activeCaptureMode.load() == CAPTURE_MODE_NONE &&
           !g_macroPlaybackActive.load() &&
           g_callbacksInFlight.load() == 0 &&
           g_inputCaptureCallbacksInFlight.load() == 0 &&
           IsThreadHandleStopped(g_mouseThreadHandle) &&
           IsThreadHandleStopped(g_keyboardThreadHandle) &&
           IsThreadHandleStopped(g_callbackThread) &&
           IsThreadHandleStopped(g_inputCaptureThread) &&
           IsThreadHandleStopped(g_debugLogThread) &&
           IsThreadHandleStopped(g_macroPlaybackThread);
}


// ========== 任务栏触发导出函数 ==========

HOOKS_API void SetTaskbarDoubleClickCallback(MouseCallback callback) {
    g_taskbarDoubleClickCallback = nullptr;
    PurgeCallbackEvents(CallbackEvent::TaskbarDoubleClick);
    WaitForCallbacksToDrain();
    g_taskbarDoubleClickCallback = callback;
}

HOOKS_API void SetTaskbarTriggerEnabled(bool enabled, bool requireCtrl) {
    g_taskbarTriggerEnabled = enabled;
    g_taskbarTriggerCtrl = requireCtrl;
    g_taskbarDClickLastTime = 0.0;
}

HOOKS_API void SetTaskbarTriggerConfig(bool enabled, bool requireCtrl, int doubleClickIntervalMs) {
    g_taskbarTriggerEnabled = enabled;
    g_taskbarTriggerCtrl = requireCtrl;
    g_taskbarDClickIntervalMs = ClampTaskbarDoubleClickIntervalMs(doubleClickIntervalMs);
    g_taskbarDClickLastTime = 0.0;
}

HOOKS_API bool IsTaskbarTriggerAvailable() {
    HWND hTaskbar = FindWindowW(L"Shell_TrayWnd", NULL);
    return hTaskbar != NULL;
}
