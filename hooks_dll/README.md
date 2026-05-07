# 钩子模块 C++ DLL 重构

## 概述

将原有的Python ctypes实现的键盘鼠标钩子重构为C++ DLL，提升性能和稳定性。

## 文件结构

```
hooks_dll/
├── hooks.h           # DLL头文件
├── hooks.cpp         # DLL实现
├── CMakeLists.txt    # CMake配置
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
4. 编译完成后，hooks.dll会生成在项目根目录

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

## 性能优势

- 原生C++实现，响应速度更快
- 更低的CPU占用
- 更稳定的钩子机制
- 减少Python GIL影响
