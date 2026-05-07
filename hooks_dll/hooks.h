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

    // 鼠标钩子
    HOOKS_API bool InstallMouseHook(MouseCallback callback);
    HOOKS_API void UninstallMouseHook();
    HOOKS_API void SetMousePaused(bool paused);
    HOOKS_API bool IsMousePaused();
    HOOKS_API void SetAltDoubleClickCallback(MouseCallback callback);

    // 键盘钩子
    HOOKS_API bool InstallKeyboardHook(KeyboardCallback altDoubleTapCallback);
    HOOKS_API void UninstallKeyboardHook();
    HOOKS_API bool IsAltHeld();
    HOOKS_API bool IsCtrlHeld();
    HOOKS_API void SetGlobalHotkey(const char* hotkeyStr, KeyboardCallback callback);
    HOOKS_API void ClearGlobalHotkey();

    // 特殊应用列表
    HOOKS_API void SetSpecialApps(const char** apps, int count);
    HOOKS_API void ClearSpecialApps();

    // 工具函数
    HOOKS_API void ReleaseAllModifierKeys();
}
