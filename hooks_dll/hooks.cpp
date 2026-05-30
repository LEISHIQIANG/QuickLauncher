#define HOOKS_EXPORTS
#include "hooks.h"
#include <windows.h>
#include <thread>
#include <chrono>
#include <atomic>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <sstream>
#include <vector>

// 全局变量
static HHOOK g_mouseHook = NULL;
static HHOOK g_keyboardHook = NULL;
static DWORD g_mouseThreadId = 0;
static DWORD g_keyboardThreadId = 0;
static HANDLE g_mouseThreadHandle = NULL;
static HANDLE g_keyboardThreadHandle = NULL;
static HANDLE g_mouseReadyEvent = NULL;
static HANDLE g_keyboardReadyEvent = NULL;
static std::atomic<bool> g_mouseRunning(false);
static std::atomic<bool> g_keyboardRunning(false);
static std::atomic<bool> g_mouseInstalling(false);
static std::atomic<bool> g_keyboardInstalling(false);
static std::atomic<bool> g_mouseThreadAlive(false);
static std::atomic<bool> g_keyboardThreadAlive(false);

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
static MouseCallback g_mouseCallback = nullptr;
static MouseCallback g_altDoubleClickCallback = nullptr;
static KeyboardCallback g_altDoubleTapCallback = nullptr;
static KeyboardCallback g_hotkeyCallback = nullptr;

// 状态
static std::atomic<bool> g_mousePaused(false);
static std::atomic<bool> g_altHeld(false);
static std::atomic<bool> g_ctrlHeld(false);
static std::atomic<bool> g_blockedDown(false);
static std::atomic<DWORD> g_lastHookError(0);

// 时间戳
static double g_lastBlockTime = 0.0;
static double g_altPressTime = 0.0;
static double g_lastAltReleaseTime = 0.0;
static double g_lastDoubleTapTime = 0.0;
static double g_altLClickLastTime = 0.0;
static double g_altLClickLastTrigger = 0.0;
static int g_altTapCount = 0;
static bool g_otherKeyPressed = false;

// 热键配置
static int g_hotkeyModifiers = 0;
static int g_hotkeyVk = 0;
static bool g_hotkeyEnabled = false;
static double g_lastHotkeyTime = 0.0;

// 特殊应用列表
static std::vector<std::string> g_specialApps;
static std::mutex g_specialAppsMutex;
static std::mutex g_debugLogMutex;
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
static KeyboardCallback g_pendingCallback = nullptr;
static std::mutex g_callbackMutex;

// 常量
constexpr double MIN_BLOCK_INTERVAL = 0.025;
constexpr double ALT_DOUBLE_TAP_INTERVAL = 0.40;
constexpr double ALT_TAP_MAX_HOLD_TIME = 0.25;
constexpr double ALT_DOUBLE_TAP_COOLDOWN = 0.50;
constexpr double ALT_LCLICK_DOUBLE_INTERVAL = 0.40;
constexpr double ALT_LCLICK_COOLDOWN = 0.50;
constexpr double BLOCKED_STATE_TIMEOUT = 2.0;  // 2秒超时自动释放
constexpr int HOOKS_VERSION = 4;
constexpr unsigned int HOOKS_CAP_MOUSE = 0x0001;
constexpr unsigned int HOOKS_CAP_KEYBOARD = 0x0002;
constexpr unsigned int HOOKS_CAP_GLOBAL_HOTKEY = 0x0004;
constexpr unsigned int HOOKS_CAP_SPECIAL_APPS = 0x0008;
constexpr unsigned int HOOKS_CAP_DIAGNOSTICS = 0x0010;

inline double GetTime() {
    return GetTickCount64() / 1000.0;
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

// ============================================================
// 回调线程 - 单线程排队执行，避免每次 CreateThread
// ============================================================

// SEH保护的回调执行 — 必须在独立函数中，不能和 C++ 对象（如 lock_guard）共存
static void SafeInvokeCallback(KeyboardCallback cb) {
    __try {
        cb();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        // 忽略回调中的异常
    }
}

static DWORD WINAPI CallbackThreadProc(LPVOID) {
    while (g_callbackThreadRunning.load()) {
        DWORD result = WaitForSingleObject(g_callbackEvent, 500);
        if (!g_callbackThreadRunning.load()) break;
        if (result == WAIT_OBJECT_0) {
            KeyboardCallback cb = nullptr;
            {
                std::lock_guard<std::mutex> lock(g_callbackMutex);
                cb = g_pendingCallback;
                g_pendingCallback = nullptr;
            }
            if (cb) {
                SafeInvokeCallback(cb);
            }
        }
    }
    return 0;
}


static void EnsureCallbackThread() {
    if (g_callbackThreadRunning.load() && g_callbackThread) return;

    if (g_callbackEvent == NULL) {
        g_callbackEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    }
    g_callbackThreadRunning = true;
    g_callbackThread = CreateThread(NULL, 0, CallbackThreadProc, NULL, 0, NULL);
}

static void StopCallbackThread() {
    g_callbackThreadRunning = false;
    if (g_callbackEvent) SetEvent(g_callbackEvent);
    if (g_callbackThread) {
        WaitForSingleObject(g_callbackThread, 1000);
        CloseHandle(g_callbackThread);
        g_callbackThread = NULL;
    }
    if (g_callbackEvent) {
        CloseHandle(g_callbackEvent);
        g_callbackEvent = NULL;
    }
}

static void InvokeKeyboardCallbackAsync(KeyboardCallback callback) {
    if (!callback) return;
    EnsureCallbackThread();
    {
        std::lock_guard<std::mutex> lock(g_callbackMutex);
        g_pendingCallback = callback;
    }
    if (g_callbackEvent) SetEvent(g_callbackEvent);
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
    if (g_debugLogEvent == NULL) {
        g_debugLogEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    }
    g_debugLogThreadRunning = true;
    g_debugLogThread = CreateThread(NULL, 0, DebugLogThreadProc, NULL, 0, NULL);
}

static void StopDebugLogThread() {
    g_debugLogThreadRunning = false;
    if (g_debugLogEvent) SetEvent(g_debugLogEvent);
    if (g_debugLogThread) {
        WaitForSingleObject(g_debugLogThread, 1000);
        CloseHandle(g_debugLogThread);
        g_debugLogThread = NULL;
    }
    if (g_debugLogEvent) {
        CloseHandle(g_debugLogEvent);
        g_debugLogEvent = NULL;
    }
}

static void LogMiddleMouseEvent(const char* phase, WPARAM wParam, const MSLLHOOKSTRUCT* mouse, const char* decision) {
    (void)phase;
    if (!mouse) return;

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

// ============================================================
// 鼠标钩子回调
// ============================================================

LRESULT CALLBACK MouseHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);

    MSLLHOOKSTRUCT* pMouse = (MSLLHOOKSTRUCT*)lParam;
    double now = GetTime();

    // Timeout protection - auto-reset if blocked for too long
    if (g_blockedDown && (now - g_lastBlockTime) > BLOCKED_STATE_TIMEOUT) {
        g_blockedDown = false;
    }

    // Alt+左键双击检测
    if (wParam == WM_LBUTTONDOWN && g_altHeld) {
        double interval = now - g_altLClickLastTime;
        if (interval < ALT_LCLICK_DOUBLE_INTERVAL && g_altLClickLastTime > 0) {
            if ((now - g_altLClickLastTrigger) > ALT_LCLICK_COOLDOWN) {
                g_altLClickLastTrigger = now;
                if (g_altDoubleClickCallback) {
                    g_altDoubleClickCallback(pMouse->pt.x, pMouse->pt.y);
                }
            }
            g_altLClickLastTime = 0.0;
        } else {
            g_altLClickLastTime = now;
        }
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    // 中键处理
    if (wParam != WM_MBUTTONDOWN && wParam != WM_MBUTTONUP) {
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    if (g_mousePaused) {
        return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
    }

    if (wParam == WM_MBUTTONDOWN) {
        if (now - g_lastBlockTime < MIN_BLOCK_INTERVAL) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_debounce");
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        // 特殊应用检测：需要 Ctrl+中键
        bool isSpecial = IsSpecialApp();
        bool ctrlHeldNow = g_ctrlHeld || IsCtrlPressedNow();
        if (isSpecial && !ctrlHeldNow) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_special_requires_ctrl");
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        if (g_mouseCallback) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "trigger_callback_block_down");
            g_mouseCallback(pMouse->pt.x, pMouse->pt.y);
            g_blockedDown = true;
            g_lastBlockTime = now;
            return 1;
        }
        LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_no_callback");
    } else if (wParam == WM_MBUTTONUP) {
        if (g_blockedDown) {
            LogMiddleMouseEvent("mouse", wParam, pMouse, "block_matching_up");
            g_blockedDown = false;
            return 1;
        }
        LogMiddleMouseEvent("mouse", wParam, pMouse, "pass_unmatched_up");
    }

    return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
}

DWORD WINAPI MouseHookThread(LPVOID param) {
    g_mouseThreadAlive = true;
    HANDLE readyEvent = (HANDLE)param;
    g_mouseThreadId = GetCurrentThreadId();
    g_mouseHook = SetWindowsHookEx(WH_MOUSE_LL, MouseHookProc, GetCurrentDllModule(), 0);

    if (!g_mouseHook) {
        g_lastHookError = GetLastError();
        g_mouseRunning = false;
        g_mouseThreadId = 0;
        g_mouseThreadAlive = false;
        if (readyEvent) SetEvent(readyEvent);
        return 1;
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
    g_blockedDown = false;
    g_mouseThreadId = 0;
    g_mouseRunning = false;
    g_mouseThreadAlive = false;
    return 0;
}

// ============================================================
// 键盘钩子回调
// ============================================================

LRESULT CALLBACK KeyboardHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT* pKbd = (KBDLLHOOKSTRUCT*)lParam;
    int vk = pKbd->vkCode;
    double now = GetTime();

    bool isAlt = (vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU);
    bool isCtrl = (vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL);

    // 物理键状态同步 — 修正 g_altHeld 与物理键状态的不一致
    // 当收到非 Alt 键事件时，检查物理 Alt 是否已释放
    if (!isAlt && g_altHeld && !IsAltPressedNow()) {
        g_altHeld = false;
        g_altTapCount = 0;
    }

    if (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN) {
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
            if (g_hotkeyEnabled && vk == g_hotkeyVk) {
                bool altMatch = IsModifierPressedNow(1) == ((g_hotkeyModifiers & 1) != 0);
                bool ctrlMatch = IsModifierPressedNow(2) == ((g_hotkeyModifiers & 2) != 0);
                bool shiftMatch = IsModifierPressedNow(4) == ((g_hotkeyModifiers & 4) != 0);
                bool winMatch = IsModifierPressedNow(8) == ((g_hotkeyModifiers & 8) != 0);
                if (altMatch && ctrlMatch && shiftMatch && winMatch && (now - g_lastHotkeyTime) > 0.25) {
                    g_lastHotkeyTime = now;
                    InvokeKeyboardCallbackAsync(g_hotkeyCallback);
                    // 拦截热键事件，不传递给系统和其它程序
                    return 1;
                }
            }
        }
    } else if (wParam == WM_KEYUP || wParam == WM_SYSKEYUP) {
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
                                InvokeKeyboardCallbackAsync(g_altDoubleTapCallback);
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
        if (g_hotkeyEnabled && vk == g_hotkeyVk) {
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
    HANDLE readyEvent = (HANDLE)param;
    g_keyboardThreadId = GetCurrentThreadId();
    g_keyboardHook = SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardHookProc, GetCurrentDllModule(), 0);

    if (!g_keyboardHook) {
        g_lastHookError = GetLastError();
        g_keyboardRunning = false;
        g_keyboardThreadId = 0;
        g_keyboardThreadAlive = false;
        if (readyEvent) SetEvent(readyEvent);
        return 1;
    }

    // 通知主线程钩子安装成功
    if (readyEvent) SetEvent(readyEvent);

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_keyboardHook) {
        UnhookWindowsHookEx(g_keyboardHook);
        g_keyboardHook = NULL;
    }
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
    g_hotkeyEnabled = false;
    g_keyboardThreadId = 0;
    g_keyboardRunning = false;
    g_keyboardThreadAlive = false;
    return 0;
}

// ============================================================
// 导出函数实现
// ============================================================

bool InstallMouseHook(MouseCallback callback) {
    // 防重入
    bool expected = false;
    if (!g_mouseInstalling.compare_exchange_strong(expected, true)) {
        // 已有安装操作进行中
        return g_mouseHook != NULL;
    }

    g_mouseCallback = callback;

    // 如果旧线程仍在运行，等待其安全退出，防止多线程钩子竞态
    if (g_mouseThreadAlive.load()) {
        int waitCount = 0;
        while (g_mouseThreadAlive.load() && waitCount < 50) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            waitCount++;
        }
    }

    if (g_mouseRunning) {
        g_mouseInstalling = false;
        return g_mouseHook != NULL;
    }

    // 确保回调线程已启动
    EnsureCallbackThread();

    // 创建同步事件
    if (g_mouseReadyEvent) {
        CloseHandle(g_mouseReadyEvent);
    }
    g_mouseReadyEvent = CreateEventW(NULL, TRUE, FALSE, NULL);

    g_mouseRunning = true;

    // 关闭之前的线程句柄（如果有）
    if (g_mouseThreadHandle) {
        CloseHandle(g_mouseThreadHandle);
        g_mouseThreadHandle = NULL;
    }

    g_mouseThreadHandle = CreateThread(NULL, 0, MouseHookThread, g_mouseReadyEvent, 0, NULL);

    if (!g_mouseThreadHandle) {
        g_lastHookError = GetLastError();
        g_mouseRunning = false;
        g_mouseInstalling = false;
        return false;
    }

    // 等待钩子安装完成（最多 2 秒）
    WaitForSingleObject(g_mouseReadyEvent, 2000);

    g_mouseInstalling = false;
    return g_mouseHook != NULL;
}

void UninstallMouseHook() {
    g_mouseRunning = false;
    if (g_mouseThreadId) {
        PostThreadMessage(g_mouseThreadId, WM_QUIT, 0, 0);
    }
    // 等待线程真正退出 (超时设为 500ms 彻底防死锁，同时确保 unhook 完成)
    if (g_mouseThreadHandle) {
        WaitForSingleObject(g_mouseThreadHandle, 500);
        CloseHandle(g_mouseThreadHandle);
        g_mouseThreadHandle = NULL;
    }
    if (g_mouseReadyEvent) {
        CloseHandle(g_mouseReadyEvent);
        g_mouseReadyEvent = NULL;
    }
    StopDebugLogThread();
}

void SetMousePaused(bool paused) {
    g_mousePaused = paused;
    if (paused) g_blockedDown = false;
}

bool IsMousePaused() {
    return g_mousePaused;
}

void SetAltDoubleClickCallback(MouseCallback callback) {
    g_altDoubleClickCallback = callback;
}

bool InstallKeyboardHook(KeyboardCallback altDoubleTapCallback) {
    // 防重入
    bool expected = false;
    if (!g_keyboardInstalling.compare_exchange_strong(expected, true)) {
        return g_keyboardHook != NULL;
    }

    g_altDoubleTapCallback = altDoubleTapCallback;

    // 如果旧线程仍在运行，等待其安全退出，防止多线程钩子竞态
    if (g_keyboardThreadAlive.load()) {
        int waitCount = 0;
        while (g_keyboardThreadAlive.load() && waitCount < 50) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            waitCount++;
        }
    }

    if (g_keyboardRunning) {
        g_keyboardInstalling = false;
        return g_keyboardHook != NULL;
    }

    // 确保回调线程已启动
    EnsureCallbackThread();

    // 创建同步事件
    if (g_keyboardReadyEvent) {
        CloseHandle(g_keyboardReadyEvent);
    }
    g_keyboardReadyEvent = CreateEventW(NULL, TRUE, FALSE, NULL);

    g_keyboardRunning = true;

    // 关闭之前的线程句柄
    if (g_keyboardThreadHandle) {
        CloseHandle(g_keyboardThreadHandle);
        g_keyboardThreadHandle = NULL;
    }

    g_keyboardThreadHandle = CreateThread(NULL, 0, KeyboardHookThread, g_keyboardReadyEvent, 0, NULL);

    if (!g_keyboardThreadHandle) {
        g_lastHookError = GetLastError();
        g_keyboardRunning = false;
        g_keyboardInstalling = false;
        return false;
    }

    // 等待钩子安装完成（最多 2 秒）
    WaitForSingleObject(g_keyboardReadyEvent, 2000);

    g_keyboardInstalling = false;
    return g_keyboardHook != NULL;
}

void UninstallKeyboardHook() {
    g_keyboardRunning = false;
    if (g_keyboardThreadId) {
        PostThreadMessage(g_keyboardThreadId, WM_QUIT, 0, 0);
    }
    // 等待线程真正退出 (超时设为 500ms 彻底防死锁，同时确保 unhook 完成)
    if (g_keyboardThreadHandle) {
        WaitForSingleObject(g_keyboardThreadHandle, 500);
        CloseHandle(g_keyboardThreadHandle);
        g_keyboardThreadHandle = NULL;
    }
    if (g_keyboardReadyEvent) {
        CloseHandle(g_keyboardReadyEvent);
        g_keyboardReadyEvent = NULL;
    }
    g_altHeld = false;
    g_ctrlHeld = false;
    g_altTapCount = 0;
    g_otherKeyPressed = false;
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
    g_hotkeyCallback = callback;
    g_hotkeyEnabled = false;
    if (!hotkeyStr || !callback) return false;

    std::string str(hotkeyStr);
    int mods = 0, vk = 0;
    if (!ParseGlobalHotkey(str, &mods, &vk)) return false;

    g_hotkeyModifiers = mods;
    g_hotkeyVk = vk;
    g_hotkeyEnabled = true;
    return true;
}

void ClearGlobalHotkey() {
    g_hotkeyEnabled = false;
    g_hotkeyCallback = nullptr;
}

void ReleaseAllModifierKeys() {
    // 只释放修饰键，不影响其他键
    INPUT inputs[4] = {0};

    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wVk = VK_MENU;
    inputs[0].ki.dwFlags = KEYEVENTF_KEYUP;

    inputs[1].type = INPUT_KEYBOARD;
    inputs[1].ki.wVk = VK_CONTROL;
    inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;

    inputs[2].type = INPUT_KEYBOARD;
    inputs[2].ki.wVk = VK_SHIFT;
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP;

    inputs[3].type = INPUT_KEYBOARD;
    inputs[3].ki.wVk = VK_LWIN;
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP;

    SendInput(4, inputs, sizeof(INPUT));
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

HOOKS_API int GetHooksVersion() {
    return HOOKS_VERSION;
}

HOOKS_API unsigned int GetHooksCapabilities() {
    return HOOKS_CAP_MOUSE |
           HOOKS_CAP_KEYBOARD |
           HOOKS_CAP_GLOBAL_HOTKEY |
           HOOKS_CAP_SPECIAL_APPS |
           HOOKS_CAP_DIAGNOSTICS;
}

HOOKS_API unsigned long GetLastHookError() {
    return static_cast<unsigned long>(g_lastHookError.load());
}
