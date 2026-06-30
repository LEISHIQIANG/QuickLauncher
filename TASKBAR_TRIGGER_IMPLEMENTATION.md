# 任务栏双击触发功能实现指南

## 概述
此功能为 QuickLauncher 新增"任务栏双击空白区域触发弹窗"的能力。

## 已完成的工作 (Python 端)
- `core/data_models.py`: 新增 `popup_trigger_source`, `popup_taskbar_trigger_ctrl` 字段和迁移逻辑
- `core/data_models.py`: 新增特殊触发对应字段
- `ui/config_window/input_trigger_recorder.py`: 新增"预设"按钮和下拉菜单
- `ui/config_window/settings_popup_page.py`: 连接预设信号，支持 taskbar 触发加载/应用
- `hooks/mouse_hook_dll.py`: 新增 `set_taskbar_trigger`, `set_taskbar_callback`, `is_taskbar_trigger_available` 方法 (hasattr 保护)
- `hooks/hooks_wrapper.py`: 新增 DLL 导出函数封装
- `ui/tray_mixins/hooks_mixin.py`: 新增任务栏回调方法和设置应用
- `ui/tray_app.py`: 新增信号和连接

## 待完成的工作 (C++ DLL 端)
需要修改 `hooks_dll/hooks.cpp`，然后重新编译 `hooks.dll`。

### 修改 1: 新增 `TaskbarDoubleClick` 枚举值
**位置**: `hooks.cpp` 第 207-223 行，`CallbackEvent` 结构体中的 `enum Type`

在 `ProtectedChordCapture` 后面加上逗号，然后新增一行：
```cpp
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
    // ... 其他字段
};
```

### 修改 2: 新增常量和全局变量
**位置**: 在 `CallbackEvent` 结构体之后，`g_pendingCallbacks` 声明之前

插入以下代码：
```cpp
// ========== 任务栏双击检测 ==========
constexpr double TASKBAR_DCLICK_INTERVAL = 0.40;   // 双击间隔 400ms
constexpr double TASKBAR_DCLICK_COOLDOWN = 0.50;  // 冷却 500ms

static double g_taskbarDClickLastTime = 0.0;
static double g_taskbarDClickLastTrigger = 0.0;
static std::atomic<bool> g_taskbarTriggerEnabled{false};
static std::atomic<bool> g_taskbarTriggerCtrl{false};  // 是否需按住 Ctrl

// 检测指定点是否在任务栏空白区域
static bool IsOnTaskbarEmptyArea(int x, int y) {
    // 主任务栏
    HWND hTaskbar = FindWindowW(L"Shell_TrayWnd", NULL);
    if (hTaskbar && IsWindowVisible(hTaskbar)) {
        RECT rc;
        if (GetWindowRect(hTaskbar, &rc) &&
            x >= rc.left && x <= rc.right &&
            y >= rc.top && y <= rc.bottom) {
            POINT pt = { x, y };
            HWND hWndAtPoint = WindowFromPoint(pt);
            if (!hWndAtPoint) return false;
            
            WCHAR className[64] = {0};
            GetClassNameW(hWndAtPoint, className, 64);
            
            if (wcsstr(className, L"MSTaskSwWClass")  != NULL) return false;
            if (wcsstr(className, L"MSTaskListWClass") != NULL) return false;
            if (wcsstr(className, L"TrayNotifyWnd")   != NULL) return false;
            if (wcsstr(className, L"TrayClockWClass") != NULL) return false;
            if (wcsstr(className, L"ToolbarWindow32") != NULL) return false;
            return true;
        }
    }
    
    // 副显示器任务栏 (Windows 8+)
    HWND hSecondary = FindWindowW(L"Shell_SecondaryTrayWnd", NULL);
    while (hSecondary) {
        if (IsWindowVisible(hSecondary)) {
            RECT rc;
            if (GetWindowRect(hSecondary, &rc) &&
                x >= rc.left && x <= rc.right &&
                y >= rc.top && y <= rc.bottom) {
                POINT pt = { x, y };
                HWND hWndAtPoint = WindowFromPoint(pt);
                if (hWndAtPoint) {
                    WCHAR className[64] = {0};
                    GetClassNameW(hWndAtPoint, className, 64);
                    if (wcsstr(className, L"MSTaskSwWClass")  != NULL) return false;
                    if (wcsstr(className, L"TrayNotifyWnd")   != NULL) return false;
                    if (wcsstr(className, L"ToolbarWindow32") != NULL) return false;
                    return true;
                }
            }
        }
        hSecondary = FindWindowExW(NULL, hSecondary, L"Shell_SecondaryTrayWnd", NULL);
    }
    return false;
}
```

### 修改 3: 在 `SafeInvokeAny` 中新增处理分支
**位置**: `hooks.cpp` 第 1215 行附近，`SafeInvokeAny` 函数

在 `} else if (ev.type == CallbackEvent::AltDoubleClick) {` 块之后，新增：
```cpp
    } else if (ev.type == CallbackEvent::TaskbarDoubleClick) {
        MouseCallback callback = g_taskbarDoubleClickCallback.load();
        if (callback) SAFE_INVOKE_CALLBACK(callback(ev.x, ev.y))
    }
```

同时需要在文件顶部新增 `g_taskbarDoubleClickCallback` 全局变量声明：
```cpp
static std::atomic<MouseCallback> g_taskbarDoubleClickCallback(nullptr);
```

### 修改 4: 在 `MouseHookProc` 中插入任务栏双击检测
**位置**: `hooks.cpp` 的 `MouseHookProc` 函数中，在 Alt+左键双击检测块**之后**、通用触发检测**之前**

插入以下代码：
```cpp
    // --- 任务栏双击检测 ---
    if (g_taskbarTriggerEnabled.load() && wParam == WM_LBUTTONDOWN) {
        bool ctrlRequired = g_taskbarTriggerCtrl.load();
        bool ctrlHeldNow = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
        if (!ctrlRequired || ctrlHeldNow) {
            if (IsOnTaskbarEmptyArea(pMouse->pt.x, pMouse->pt.y)) {
                double now = GetHighResTime();
                double interval = now - g_taskbarDClickLastTime;
                if (interval < TASKBAR_DCLICK_INTERVAL && g_taskbarDClickLastTime > 0) {
                    if ((now - g_taskbarDClickLastTrigger) > TASKBAR_DCLICK_COOLDOWN) {
                        g_taskbarDClickLastTrigger = now;
                        InvokeMouseCallbackAsync(CallbackEvent::TaskbarDoubleClick, 
                                                 pMouse->pt.x, pMouse->pt.y);
                    }
                    g_taskbarDClickLastTime = 0.0;
                    // 消费此事件，不传递给其他应用
                    return 0;
                }
                g_taskbarDClickLastTime = now;
            }
        }
    }
```

**注意**: 需要把 `GetHighResTime()` 替换为 `hooks.cpp` 中实际使用的高精度时间函数名（可能是 `GetCurrentTime()` 或类似函数）。请搜索文件中已有的时间函数调用。

### 修改 5: 新增导出函数
**位置**: 在 `SetAltDoubleClickCallback` 函数之后（约第 3225 行附近）

插入以下导出函数：
```cpp
// 设置任务栏双击回调
extern "C" HOOKS_EXPORT void SetTaskbarDoubleClickCallback(MouseCallback callback) {
    g_taskbarDoubleClickCallback = nullptr;
    PurgeCallbackEvents(CallbackEvent::TaskbarDoubleClick);
    WaitForCallbacksToDrain();
    g_taskbarDoubleClickCallback = callback;
}

// 启用/禁用任务栏触发
extern "C" HOOKS_EXPORT void SetTaskbarTriggerEnabled(bool enabled, bool requireCtrl) {
    g_taskbarTriggerEnabled = enabled;
    g_taskbarTriggerCtrl = requireCtrl;
}

// 查询任务栏触发是否可用
extern "C" HOOKS_EXPORT bool IsTaskbarTriggerAvailable() {
    HWND hTaskbar = FindWindowW(L"Shell_TrayWnd", NULL);
    return hTaskbar != NULL;
}
```

## 编译步骤
1. 打开 `hooks_dll/hooks.sln`（或对应 CMake 项目）
2. 编译生成 `hooks.dll`
3. 将新 `hooks.dll` 放到 `dist/` 目录（或 Python 能找到的路径）

## 测试步骤
1. 启动 QuickLauncher
2. 打开设置 → 弹窗设置 → 触发按键设置
3. 点击"预设"按钮，选择"任务栏双击"
4. 点击"应用触发设置"
5. 双击任务栏空白区域，验证弹窗是否弹出
