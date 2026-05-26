# QuickLauncher 开发指南

## 项目概述

QuickLauncher 是一款 Python + PyQt5 的 Windows 桌面快速启动器。用户按鼠标中键弹出面板，可启动程序、打开文件/文件夹/URL、执行命令、发送热键。支持拼音搜索、插件系统、中英双语。

## 架构（三层）

```
UI Layer      → tray_app.py, launcher_popup/, config_window/
Core Layer    → data_manager, shortcut_executor, command_registry, plugin_manager
Bootstrap     → dpi, logging, deps, ipc, venv
```

## 技术栈

- Python 3.12, PyQt5 5.15.11
- C++ hook DLL (`hooks_dll/hooks.cpp`) 用于全局鼠标/键盘钩子
- Nuitka 编译打包, Inno Setup 安装器
- 测试: pytest | Lint: ruff | 格式化: black/ruff

## 开发命令

```bash
python main.py                                    # 运行
python -m pytest tests/ -v --tb=short             # 测试
python -m ruff check core/ ui/ hooks/ services/   # Lint
ruff format core/ ui/ hooks/ services/            # 格式化
```

## 代码规范

- 行宽 120（pyproject.toml）
- 大类拆分用 mixin 模式：文件名 `*_mixin.py`，类名 `*Mixin`，不定义 `__init__`
- 信号(pyqtSignal)定义在主类，mixin 通过 `self.<signal>.emit()` 发射
- 懒加载导入（在方法内 import）用于减少启动时间
- mixin 只导入 qt_compat 和 core，不导入主类模块（避免循环导入）

## 关键文件

| 路径 | 说明 |
|---|---|
| `main.py` | 入口 |
| `ui/tray_app.py` | 托盘应用主控 |
| `ui/tray_mixins/` | TrayApp 的 mixin 拆分 |
| `ui/launcher_popup/popup_window.py` | 弹窗主类 |
| `ui/launcher_popup/popup_*.py` | LauncherPopup 的 mixin 拆分 |
| `ui/config_window/settings_panel.py` | 设置面板 |
| `core/data_manager.py` | 数据管理（单例） |
| `core/shortcut_executor.py` | 快捷方式执行调度 |
| `core/command_registry.py` | 命令注册系统 |
| `core/plugin_manager.py` | 插件管理 |
| `hooks/hooks_dll/` | C++ DLL 源码 |
| `services/update/` | 自动更新系统 |
| `tests/` | 测试（48 个测试文件） |
| `config/data.json` | 用户配置数据 |
