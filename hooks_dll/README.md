# 钩子模块 C++ DLL

## 概述

全局键盘、鼠标输入只由 `hooks.dll` 实现。鼠标侧同时使用 `WH_MOUSE_LL` 和后台 Raw Input：低级钩子负责拦截，Raw Input 负责在低级钩子漏报或被 Windows 静默移除时兜底。Python 层通过 `ctypes` 加载 DLL，负责生命周期、诊断和与 Qt 主线程的信号桥接。

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
- Raw Input 后台兜底与物理点击去重
- Alt+左键双击检测
- Alt双击检测
- 自定义热键支持
- 暂停/恢复功能
- 修饰键状态查询（Alt/Ctrl）
- 钩子安装状态查询：`IsMouseHookInstalled()`、`IsKeyboardHookInstalled()`
- Raw Input 状态查询：`IsRawInputFallbackActive()`
- 最近错误查询：`GetLastHookError()`
- 能力位查询：`GetHooksCapabilities()`
- 统一键鼠事件录制：移动、五键鼠标、垂直/水平滚轮、键盘按下/抬起、扫描码与微秒时间戳
- 异步组合宏回放：键盘、鼠标和 Unicode 事件可按同一时间线混排
- 宏回放取消、等待、进度查询，以及取消/异常后的按键和鼠标键自动释放
- 回放事件使用专用 `dwExtraInfo` 标记，默认不触发启动器且不会被宏录制再次采集
- 钩子诊断文件默认不写盘；仅在排障时设置 `QUICKLAUNCHER_HOOK_DEBUG=1`
  才启用 `hooks/hook_debug.log`，避免正常触发路径产生磁盘 I/O

## 宏基础接口

Python 业务层优先使用 `InputMacroBackend`：

```python
from hooks import InputMacroBackend

macro = InputMacroBackend()
macro.start_recording()
# 用户执行键盘和鼠标操作
events = macro.stop_recording()

sequence = macro.build_sequence(speed=1.25)
macro.play(sequence)
macro.wait(5000)
```

底层 DLL 接口包括：

- `StartInputCapture` / `StopInputCapture` / `IsInputCaptureActive`
- `PlayMacroEvents` / `CancelMacroPlayback` / `WaitForMacroPlayback`
- `GetMacroStatus` / `ReleaseMacroPressedInputs`

录制默认只采集物理输入。只有显式设置 `HOOK_CAPTURE_INCLUDE_INJECTED`
或 `HOOK_CAPTURE_INCLUDE_OWN_PLAYBACK` 时才会收到注入事件，从根源上避免宏自录、
递归触发和无限回放。

## 稳定性约束

- 鼠标与键盘低级钩子回调必须快速返回；DLL 内部只记录触发状态，再由独立回调线程调用 Python 回调。
- Raw Input 与低级钩子使用每个鼠标按键的物理事件计数配对，正常情况下不会重复回调；未配对事件会走兜底并将低级钩子标记为待恢复。
- 弹窗/热键回调线程使用 256 项有界 FIFO；宏录制使用独立的 8192 项队列，互不阻塞。
- 鼠标移动默认保留完整轨迹；需要低采样录制时可显式开启连续移动合并。
- Python 回调异常不能穿透到低级钩子过程；DLL 回调线程会捕获异常边界并继续运行。
- 回放采用专用线程和可取消等待，不在低级钩子线程内休眠或调用 Python。
- 宏结束、取消或发送失败时默认释放本次宏仍按住的键，避免出现卡键。
- 安装钩子时等待钩子线程初始化；超时会写入最近错误，供诊断中心显示。
- 主程序重装钩子时应通过 `Uninstall*Hook()` 后再 `Install*Hook()`，不要创建多个 DLL 实例争用全局钩子。
- 同一时刻只允许一个宏录制所有者；新的录制请求不会静默替换正在运行的录制。
- Python 释放 DLL 前必须确认 `AreHooksQuiescent()` 为真；超时时保留 DLL 与回调引用至进程结束。

## 性能优势

- 原生C++实现，响应速度更快
- 更低的CPU占用
- 更稳定的钩子机制
- 减少Python GIL影响
