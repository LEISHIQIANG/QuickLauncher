# 钩子模块 C++ DLL

## 概述

全局键盘、鼠标钩子只由 `hooks.dll` 实现。Python 层通过 `ctypes` 加载 DLL，负责生命周期、诊断和与 Qt 主线程的信号桥接，不作为备用钩子后端。

## 文件结构

```
hooks_dll/
├── hooks.h           # DLL头文件
├── hooks.cpp         # DLL实现
└── build.bat         # 编译脚本

hooks/
├── hooks_wrapper.py      # DLL的Python封装
├── mouse_hook_dll.py     # 鼠标钩子兼容层
└── keyboard_hook_dll.py  # 键盘钩子兼容层
```

## 编译步骤

1. 安装Visual Studio 2022或MinGW-w64
2. 安装CMake (3.10+)
3. 运行编译脚本：
   ```
   cd hooks_dll
   build.bat
   ```
4. 编译完成后，`hooks.dll` 会写入 `hooks/hooks.dll`，供主程序运行时加载。

## 使用方法

### 方式1：直接使用DLL封装

```python
from hooks.hooks_wrapper import HooksDLL

dll = HooksDLL()

def on_middle_click(x, y):
    print(f"中键点击: {x}, {y}")

dll.install_mouse_hook(on_middle_click)
```

### 方式2：使用兼容层（推荐）

```python
from hooks.mouse_hook_dll import MouseHook
from hooks.keyboard_hook_dll import KeyboardHook

# 与原有代码接口完全兼容
mouse_hook = MouseHook()
mouse_hook.install(lambda x, y: print(f"点击: {x}, {y}"))

keyboard_hook = KeyboardHook()
keyboard_hook.install(lambda: print("Alt双击"))
```

## 功能特性

- 鼠标中键拦截
- Alt+左键双击检测
- Alt双击检测
- 自定义热键支持
- 暂停/恢复功能
- 修饰键状态查询（Alt/Ctrl）
- 钩子安装状态查询：`IsMouseHookInstalled()`、`IsKeyboardHookInstalled()`
- 最近错误查询：`GetLastHookError()`
- 能力位查询：`GetHooksCapabilities()`

## 稳定性约束

- 鼠标与键盘低级钩子回调必须快速返回；DLL 内部只记录触发状态，再由独立回调线程调用 Python 回调。
- 回调线程使用有界 FIFO 队列承接键盘、鼠标和热键事件，高频触发时最多保留最近 64 个事件，避免单槽覆盖或无限堆积。
- Python 回调异常不能穿透到低级钩子过程；DLL 回调线程会捕获异常边界并继续运行。
- 安装钩子时等待钩子线程初始化；超时会写入最近错误，供诊断中心显示。
- 主程序重装钩子时应通过 `Uninstall*Hook()` 后再 `Install*Hook()`，不要创建多个 DLL 实例争用全局钩子。

## 性能优势

- 原生C++实现，响应速度更快
- 更低的CPU占用
- 更稳定的钩子机制
- 减少Python GIL影响
