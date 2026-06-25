#define QLWINDOW_EXPORTS
#include "QLwindow.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <algorithm>

#pragma comment(lib, "psapi.lib")

static thread_local wchar_t g_lastError[512] = L"";

static void setError(const wchar_t* msg) {
    wcsncpy_s(g_lastError, msg ? msg : L"", _TRUNCATE);
}

QLWINDOW_API int QLwindow_version(void) {
    return 1;
}

QLWINDOW_API const wchar_t* QLwindow_lastError(void) {
    return g_lastError;
}

static std::wstring getProcessName(DWORD pid) {
    std::wstring result;
    HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!hProcess) return result;

    wchar_t path[MAX_PATH];
    DWORD size = MAX_PATH;
    if (QueryFullProcessImageNameW(hProcess, 0, path, &size)) {
        std::wstring fullPath(path, size);
        size_t lastSlash = fullPath.find_last_of(L"\\/");
        std::wstring fileName = (lastSlash != std::wstring::npos)
            ? fullPath.substr(lastSlash + 1) : fullPath;
        size_t dotPos = fileName.rfind(L".exe");
        if (dotPos == std::wstring::npos) dotPos = fileName.rfind(L".EXE");
        if (dotPos != std::wstring::npos) fileName = fileName.substr(0, dotPos);
        std::transform(fileName.begin(), fileName.end(), fileName.begin(), ::towlower);
        result = fileName;
    }
    CloseHandle(hProcess);
    return result;
}

static bool matchesBasename(const std::wstring& procName, const std::wstring& targetBase) {
    if (procName.empty() || targetBase.empty()) return false;
    return procName.find(targetBase) == 0;
}

static bool activateHwndInternal(HWND hwnd, BOOL restoreMinimized) {
    if (!IsWindow(hwnd)) return false;

    if (!IsWindowVisible(hwnd))
        ShowWindow(hwnd, SW_SHOW);

    WINDOWPLACEMENT placement = { sizeof(placement) };
    GetWindowPlacement(hwnd, &placement);

    BOOL minimized = (placement.showCmd == SW_MINIMIZE
                   || placement.showCmd == SW_SHOWMINIMIZED
                   || placement.showCmd == SW_SHOWMINNOACTIVE);

    if (minimized && !restoreMinimized) return false;

    SwitchToThisWindow(hwnd, TRUE);
    return true;
}

QLWINDOW_API int QLwindow_Activate(const wchar_t* exePath,
                                    int restoreMinimized,
                                    int* outHwnd) {
    if (!exePath || !*exePath) {
        setError(L"exePath is empty");
        return 3; // QL_WINDOW_FAILED
    }

    std::wstring path(exePath);
    size_t lastSep = path.find_last_of(L"\\/");
    std::wstring base = (lastSep != std::wstring::npos)
        ? path.substr(lastSep + 1) : path;
    size_t dot = base.rfind(L'.');
    if (dot != std::wstring::npos) base = base.substr(0, dot);
    std::transform(base.begin(), base.end(), base.begin(), ::towlower);

    struct Entry { HWND hwnd; DWORD pid; };
    std::vector<Entry> visible;

    EnumWindows([](HWND hwnd, LPARAM lParam) -> BOOL {
        auto* vec = reinterpret_cast<std::vector<Entry>*>(lParam);
        if (!IsWindowVisible(hwnd)) return TRUE;
        wchar_t title[256];
        if (!GetWindowTextW(hwnd, title, 256) || title[0] == L'\0') return TRUE;
        LONG exStyle = GetWindowLongW(hwnd, GWL_EXSTYLE);
        if (exStyle & WS_EX_TOOLWINDOW) return TRUE;
        if (GetWindow(hwnd, GW_OWNER)) return TRUE;
        DWORD pid = 0;
        GetWindowThreadProcessId(hwnd, &pid);
        if (pid) vec->push_back({hwnd, pid});
        return TRUE;
    }, reinterpret_cast<LPARAM>(&visible));

    std::unordered_map<DWORD, std::wstring> nameCache;
    for (auto& e : visible) {
        if (!nameCache.count(e.pid))
            nameCache[e.pid] = getProcessName(e.pid);

        if (matchesBasename(nameCache[e.pid], base)) {
            if (activateHwndInternal(e.hwnd, restoreMinimized != 0)) {
                if (outHwnd) *outHwnd = (int)(INT_PTR)e.hwnd;
                return 0; // QL_WINDOW_OK
            }
        }
    }

    if (outHwnd) *outHwnd = 0;
    return 1; // QL_WINDOW_NOT_FOUND
}

QLWINDOW_API int QLwindow_GetWindowsForPids(const int* pids,
                                             int pidCount,
                                             QLWindowInfo* outInfos,
                                             int maxInfos) {
    if (!pids || pidCount <= 0 || !outInfos || maxInfos <= 0) {
        setError(L"invalid arguments");
        return -1;
    }

    std::unordered_map<DWORD, std::vector<HWND>> byPid;
    for (int i = 0; i < pidCount; i++) byPid[(DWORD)pids[i]];

    EnumWindows([](HWND hwnd, LPARAM lParam) -> BOOL {
        auto* map = reinterpret_cast<std::unordered_map<DWORD, std::vector<HWND>>*>(lParam);
        if (!IsWindowVisible(hwnd)) return TRUE;
        wchar_t title[256];
        if (!GetWindowTextW(hwnd, title, 256) || title[0] == L'\0') return TRUE;
        LONG exStyle = GetWindowLongW(hwnd, GWL_EXSTYLE);
        if (exStyle & WS_EX_TOOLWINDOW) return TRUE;
        if (GetWindow(hwnd, GW_OWNER)) return TRUE;
        DWORD pid = 0;
        GetWindowThreadProcessId(hwnd, &pid);
        auto it = map->find(pid);
        if (it != map->end()) it->second.push_back(hwnd);
        return TRUE;
    }, reinterpret_cast<LPARAM>(&byPid));

    int written = 0;
    for (auto& [pid, hwnds] : byPid) {
        for (HWND h : hwnds) {
            if (written >= maxInfos) return written;
            outInfos[written].hwnd = (int)(INT_PTR)h;
            outInfos[written].pid = (int)pid;
            GetWindowTextW(h, outInfos[written].title, 256);
            written++;
        }
    }
    return written;
}

QLWINDOW_API int QLwindow_GetProcessWindows(int pid,
                                             int* outHwnds,
                                             int maxHwnds) {
    if (pid <= 0 || !outHwnds || maxHwnds <= 0) {
        setError(L"invalid arguments");
        return -1;
    }

    std::vector<HWND> hwnds;
    DWORD targetPid = (DWORD)pid;

    EnumWindows([](HWND hwnd, LPARAM lParam) -> BOOL {
        auto* p = reinterpret_cast<std::pair<DWORD, std::vector<HWND>*>*>(lParam);
        DWORD wpid = 0;
        GetWindowThreadProcessId(hwnd, &wpid);
        if (wpid != p->first) return TRUE;
        if (!IsWindowVisible(hwnd)) return TRUE;
        wchar_t title[256];
        if (!GetWindowTextW(hwnd, title, 256) || title[0] == L'\0') return TRUE;
        LONG exStyle = GetWindowLongW(hwnd, GWL_EXSTYLE);
        if (exStyle & WS_EX_TOOLWINDOW) return TRUE;
        if (GetWindow(hwnd, GW_OWNER)) return TRUE;
        p->second->push_back(hwnd);
        return TRUE;
    }, reinterpret_cast<LPARAM>(&std::make_pair(targetPid, &hwnds)));

    int n = (int)(hwnds.size() < (size_t)maxHwnds ? hwnds.size() : (size_t)maxHwnds);
    for (int i = 0; i < n; i++) outHwnds[i] = (int)(INT_PTR)hwnds[i];
    return n;
}

QLWINDOW_API int QLwindow_ActivateHwnd(int hwnd, int restoreMinimized) {
    HWND h = reinterpret_cast<HWND>((INT_PTR)hwnd);
    return activateHwndInternal(h, restoreMinimized != 0) ? 0 : 3;
}

QLWINDOW_API int QLwindow_IsMinimized(int hwnd) {
    HWND h = reinterpret_cast<HWND>((INT_PTR)hwnd);
    if (!IsWindow(h)) return 0;
    WINDOWPLACEMENT placement = { sizeof(placement) };
    if (!GetWindowPlacement(h, &placement)) return 0;
    return (placement.showCmd == SW_MINIMIZE
         || placement.showCmd == SW_SHOWMINIMIZED
         || placement.showCmd == SW_SHOWMINNOACTIVE) ? 1 : 0;
}
