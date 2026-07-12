# QuickLauncher Hook DLL

`hooks.dll` 是 QuickLauncher 的原生输入层，负责全局鼠标、键盘、触发、录制和宏回放。Python 层通过 [hooks/hooks_wrapper.py](../hooks/hooks_wrapper.py) 使用 `ctypes` 加载 DLL，并把结果桥接回 Qt 主线程。

当前 Python wrapper 期望 DLL 能力版本不低于 `15`。

## 目录结构

```text
hooks_dll/
├── hooks.h       # 导出接口、结构体和能力位
├── hooks.cpp     # C++17 实现
└── build.bat     # MSVC + Windows SDK 构建脚本

hooks/
├── hooks.dll             # 构建输出，运行时加载
├── hooks_wrapper.py      # ctypes 封装、完整性校验、生命周期管理
├── mouse_hook_dll.py     # 鼠标 Hook 兼容层
└── keyboard_hook_dll.py  # 键盘 Hook 兼容层
```

## 构建

`build.bat` 使用 Visual Studio / Build Tools 的 MSVC 和 Windows SDK，不依赖 CMake。

```powershell
cd hooks_dll
build.bat
```

脚本会：

1. 通过 `vswhere` 或常见安装路径查找 MSVC x64 `cl.exe`。
2. 查找 Windows 10 SDK。
3. 使用 `/LD /O2 /EHsc /std:c++17 /utf-8` 编译 `hooks.cpp`。
4. 输出 `..\hooks\hooks.dll`。
5. 清理临时 `.obj/.exp/.lib` 文件。

构建失败时先确认已安装：

- Visual Studio 2022/2026 或 Build Tools。
- MSVC C++ x64 工具链。
- Windows 10 SDK。

## 运行职责

| 能力 | 说明 |
|---|---|
| 鼠标低级 Hook | 捕获五键鼠标事件，默认中键触发弹窗 |
| 键盘低级 Hook | 捕获 Alt 双击、键盘触发和快捷键录入 |
| Raw Input 兜底 | 当低级 Hook 漏报或被系统移除时兜底，并对物理事件去重 |
| RegisterHotKey | 单主键键盘触发的优先独立通道 |
| 特殊应用分支 | 普通触发和特殊应用触发可独立配置 |
| 录制会话 | 快捷键录制、受保护键鼠组合录制、宏输入录制共享会话所有权 |
| 宏回放 | 支持键盘、鼠标、滚轮、Unicode、移动轨迹和时间线回放 |
| 诊断 | 提供安装状态、能力位、最近错误、运行统计和健康标记 |

## 触发模型

QuickLauncher 的触发配置由 Python 层归一化后写入 DLL：

- 普通触发：`SetTriggerConfigEx(normalMode, normalButton, normalKeys, normalModifiers, ...)`
- 特殊触发：同一接口的 special 参数组
- 模式：`mouse`、`keyboard`、`hybrid`
- 鼠标键：left/right/middle/x1/x2
- 修饰键：Ctrl/Alt/Shift/Win

键盘触发按前台窗口判断特殊应用；鼠标和混合触发按指针所在窗口判断特殊应用。单主键键盘组合优先注册为 Windows 全局热键；上下文不同或组合无法注册时，低级 Hook、Raw Input 和异步键状态轮询会兜底。

录制期间 `RuntimeTriggerSuppressedByCapture()` 会暂停弹窗触发，避免“能录入、能应用，但录入时立即触发”的问题。

## 宏与录制接口

Python 业务层优先使用：

```python
from hooks import InputMacroBackend

macro = InputMacroBackend()
macro.start_recording()
events = macro.stop_recording()

sequence = macro.build_sequence(speed=1.25)
macro.play(sequence)
macro.wait(5000)
```

底层 DLL 接口包括：

- `StartInputCapture` / `StopInputCapture` / `IsInputCaptureActive`
- `PlayMacroEvents` / `CancelMacroPlayback` / `WaitForMacroPlayback`
- `IsMacroPlaybackActive` / `GetMacroStatus`
- `ReleaseMacroPressedInputs`

录制默认只采集物理输入。只有显式设置 include-injected / include-own-playback 选项时才会收到注入事件，从源头避免宏自录和递归触发。

## 生命周期约束

- 低级 Hook 回调必须快速返回；Python 回调在线程队列中异步执行。
- 弹窗/热键回调队列有 256 项上限，宏录制队列有 8192 项上限。
- `Install*Hook()` 可原地更新回调，完整重装应先 `Uninstall*Hook()`。
- `Uninstall*Hook()` 会停止相关录制、取消回放并清理注册热键。
- Python 释放 DLL 前必须确认 `AreHooksQuiescent()` 为真。
- 如果卸载超时，Python wrapper 会保留 DLL 和回调引用到进程退出，优先避免 native crash。
- Hook 调试日志默认不写盘；只有设置 `QUICKLAUNCHER_HOOK_DEBUG=1` 才写 `hooks/hook_debug.log` 和 `hooks/capture_debug.log`。

## 诊断接口

常用导出包括：

- `GetHooksVersion`
- `GetHooksCapabilities`
- `IsMouseHookInstalled`
- `IsKeyboardHookInstalled`
- `IsRawInputFallbackActive`
- `GetLastHookError`
- `GetHooksRuntimeStats`
- `ResetHooksRuntimeStats`
- `AreHooksQuiescent`

诊断中心和测试会通过这些接口确认 DLL 兼容性、安装状态、Raw Input 兜底状态和最近错误。
