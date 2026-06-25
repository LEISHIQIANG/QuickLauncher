#pragma once

#ifdef QLWINDOW_EXPORTS
#define QLWINDOW_API __declspec(dllexport)
#else
#define QLWINDOW_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

struct QLWindowInfo {
    int hwnd;
    int pid;
    wchar_t title[256];
};

QLWINDOW_API int  QLwindow_version(void);
QLWINDOW_API const wchar_t* QLwindow_lastError(void);

QLWINDOW_API int  QLwindow_Activate(const wchar_t* exePath,
                                     int restoreMinimized,
                                     int* outHwnd);

QLWINDOW_API int  QLwindow_GetWindowsForPids(const int* pids,
                                              int pidCount,
                                              QLWindowInfo* outInfos,
                                              int maxInfos);

QLWINDOW_API int  QLwindow_GetProcessWindows(int pid,
                                              int* outHwnds,
                                              int maxHwnds);

QLWINDOW_API int  QLwindow_ActivateHwnd(int hwnd,
                                         int restoreMinimized);

QLWINDOW_API int  QLwindow_IsMinimized(int hwnd);

#ifdef __cplusplus
}
#endif
