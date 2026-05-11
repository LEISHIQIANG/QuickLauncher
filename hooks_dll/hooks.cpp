#define HOOKS_EXPORTS
#include "hooks.h"
#include <windows.h>
#include <thread>
#include <atomic>
#include <string>
#include <vector>
#include <algorithm>
#include <cctype>

// 全局变量
static HHOOK g_mouseHook = NULL;
static HHOOK g_keyboardHook = NULL;
static DWORD g_mouseThreadId = 0;
static DWORD g_keyboardThreadId = 0;
static std::atomic<bool> g_mouseRunning(false);
static std::atomic<bool> g_keyboardRunning(false);

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

// 常量
constexpr double MIN_BLOCK_INTERVAL = 0.025;
constexpr double ALT_DOUBLE_TAP_INTERVAL = 0.40;
constexpr double ALT_TAP_MAX_HOLD_TIME = 0.25;
constexpr double ALT_DOUBLE_TAP_COOLDOWN = 0.50;
constexpr double ALT_LCLICK_DOUBLE_INTERVAL = 0.40;
constexpr double ALT_LCLICK_COOLDOWN = 0.50;
constexpr double BLOCKED_STATE_TIMEOUT = 2.0;  // 2秒超时自动释放

inline double GetTime() {
    return GetTickCount64() / 1000.0;
}

static bool IsCtrlPressedNow() {
    return (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_LCONTROL) & 0x8000) != 0 ||
           (GetAsyncKeyState(VK_RCONTROL) & 0x8000) != 0;
}

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
    if (g_specialApps.empty()) return false;

    HWND hwnd = GetTargetWindowForSpecialAppCheck();
    if (!hwnd) return false;

    std::string processLower = GetProcessNameForWindow(hwnd);

    char className[256] = {0};
    GetClassNameA(hwnd, className, sizeof(className));
    std::string classLower = ToLowerCopy(className);

    char windowTitle[256] = {0};
    GetWindowTextA(hwnd, windowTitle, sizeof(windowTitle));
    std::string titleLower = ToLowerCopy(windowTitle);

    for (const auto& app : g_specialApps) {
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

// 鼠标钩子回调
LRESULT CALLBACK MouseHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);

    MSLLHOOKSTRUCT* pMouse = (MSLLHOOKSTRUCT*)lParam;
    double now = GetTime();

    // Physical state priority - sync logical state with hardware
    SHORT mbState = GetAsyncKeyState(VK_MBUTTON);
    bool mbPhysicallyPressed = (mbState & 0x8000) != 0;
    if (!mbPhysicallyPressed && g_blockedDown) {
        g_blockedDown = false;
    }

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
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        // 特殊应用检测：需要 Ctrl+中键
        bool isSpecial = IsSpecialApp();
        bool ctrlHeldNow = g_ctrlHeld || IsCtrlPressedNow();
        if (isSpecial && !ctrlHeldNow) {
            return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
        }

        if (g_mouseCallback) {
            g_mouseCallback(pMouse->pt.x, pMouse->pt.y);
            g_blockedDown = true;
            g_lastBlockTime = now;
            return 1;
        }
    } else if (wParam == WM_MBUTTONUP) {
        if (g_blockedDown) {
            g_blockedDown = false;
            return 1;
        }
    }

    return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
}

DWORD WINAPI MouseHookThread(LPVOID) {
    g_mouseThreadId = GetCurrentThreadId();
    g_mouseHook = SetWindowsHookEx(WH_MOUSE_LL, MouseHookProc, GetModuleHandle(NULL), 0);

    if (!g_mouseHook) return 1;

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_mouseHook) {
        UnhookWindowsHookEx(g_mouseHook);
        g_mouseHook = NULL;
    }
    return 0;
}

// 键盘钩子回调
LRESULT CALLBACK KeyboardHookProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode < 0) return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT* pKbd = (KBDLLHOOKSTRUCT*)lParam;
    int vk = pKbd->vkCode;
    double now = GetTime();

    bool isAlt = (vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU);
    bool isCtrl = (vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL);

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
                bool altMatch = (bool)(g_hotkeyModifiers & 1) == g_altHeld;
                bool ctrlMatch = (bool)(g_hotkeyModifiers & 2) == g_ctrlHeld;
                if (altMatch && ctrlMatch && (now - g_lastHotkeyTime) > 0.25) {
                    g_lastHotkeyTime = now;
                    if (g_hotkeyCallback) g_hotkeyCallback();
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
                                if (g_altDoubleTapCallback) g_altDoubleTapCallback();
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
    }

    return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
}

DWORD WINAPI KeyboardHookThread(LPVOID) {
    g_keyboardThreadId = GetCurrentThreadId();
    g_keyboardHook = SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardHookProc, GetModuleHandle(NULL), 0);

    if (!g_keyboardHook) return 1;

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    if (g_keyboardHook) {
        UnhookWindowsHookEx(g_keyboardHook);
        g_keyboardHook = NULL;
    }
    return 0;
}

// 导出函数实现
bool InstallMouseHook(MouseCallback callback) {
    g_mouseCallback = callback;
    if (g_mouseRunning) return g_mouseHook != NULL;
    g_mouseRunning = true;
    CreateThread(NULL, 0, MouseHookThread, NULL, 0, NULL);
    Sleep(100);
    return g_mouseHook != NULL;
}

void UninstallMouseHook() {
    g_mouseRunning = false;
    if (g_mouseThreadId) PostThreadMessage(g_mouseThreadId, WM_QUIT, 0, 0);
    Sleep(100);
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
    g_altDoubleTapCallback = altDoubleTapCallback;
    if (g_keyboardRunning) return g_keyboardHook != NULL;
    g_keyboardRunning = true;
    CreateThread(NULL, 0, KeyboardHookThread, NULL, 0, NULL);
    Sleep(100);
    return g_keyboardHook != NULL;
}

void UninstallKeyboardHook() {
    g_keyboardRunning = false;
    if (g_keyboardThreadId) PostThreadMessage(g_keyboardThreadId, WM_QUIT, 0, 0);
    Sleep(100);
}

bool IsAltHeld() {
    return g_altHeld;
}

bool IsCtrlHeld() {
    return g_ctrlHeld || IsCtrlPressedNow();
}

void SetGlobalHotkey(const char* hotkeyStr, KeyboardCallback callback) {
    g_hotkeyCallback = callback;
    g_hotkeyEnabled = false;
    if (!hotkeyStr || !callback) return;

    std::string str(hotkeyStr);
    int mods = 0, vk = 0;

    if (str.find("alt") != std::string::npos) mods |= 1;
    if (str.find("ctrl") != std::string::npos) mods |= 2;

    size_t pos = str.find_last_of("+");
    if (pos != std::string::npos && pos + 1 < str.length()) {
        char key = toupper(str[pos + 1]);
        if (key >= 'A' && key <= 'Z') vk = key;
    }

    if (vk && mods) {
        g_hotkeyModifiers = mods;
        g_hotkeyVk = vk;
        g_hotkeyEnabled = true;
    }
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
    g_specialApps.clear();
    for (int i = 0; i < count; i++) {
        if (apps[i]) {
            g_specialApps.push_back(apps[i]);
        }
    }
}

HOOKS_API void ClearSpecialApps() {
    g_specialApps.clear();
}
