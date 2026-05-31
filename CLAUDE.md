# QuickLauncher — Claude Code 项目指南

## 项目概述

QuickLauncher 是一个 Windows 桌面快速启动器。按下鼠标中键可在屏幕任意位置唤出搜索面板，支持应用、文件夹、URL、命令、快捷键、动作链、插件，以及中文拼音搜索和中英双语界面。

- **版本**: 1.6.1.0
- **语言**: Python 3.12, PyQt5, C++ (原生钩子 DLL)
- **平台**: Windows 10/11
- **构建**: Nuitka + Inno Setup

## 目录结构速查

```
core/              # 核心业务逻辑（数据管理、搜索、命令、插件、配置、国际化）
ui/                # PyQt5 GUI 层
  config_window/   #   设置界面（35+ 文件）
  launcher_popup/  #   弹出式启动面板
  styles/          #   样式表
  tray_mixins/     #   系统托盘 Mixin 模块
  utils/           #   UI 工具类
hooks/             # 底层鼠标/键盘钩子（Python + DLL）
hooks_dll/         # 原生 C++ 钩子源码
bootstrap/         # 早期初始化（DPI、日志、IPC、依赖检查）
services/          # API 客户端 + 自动更新
plugins/           # 8 个内置插件
tests/             # pytest 测试套件（~100 个测试文件）
scripts/           # 构建、检查、代码生成脚本
docs/              # 按日期组织的设计文档
config/            # 运行时用户数据（不提交到 git）
```

## 代码规范

### 格式化与 Lint

- **Black**: 行宽 120, 目标 Python 3.12
- **Ruff**: 行宽 120, 规则集 E/F/W/I/B/C4/UP, 忽略 E501/B905
- **mypy**: 当前宽松模式（check_untyped_defs=False），正在逐步加固
- **Pre-commit**: black + ruff + 自定义静默异常检查

```bash
# 格式化
black .
ruff check --fix .

# 类型检查
mypy core/ ui/ hooks/ bootstrap/ services/
```

### 导入规范

- 所有 Qt 导入统一从 `qt_compat.py` 获取（不要直接 `from PyQt5 import ...`）
- `qt_compat.py` 提供了自动国际化翻译的包装类（QLabel, QPushButton 等）
- `core/` 不应依赖 `ui/`（架构层边界）

### 命名约定

- Qt 方法使用 camelCase（`setObjectName`, `setText`）——不适用 ruff N802 时加 `# noqa: N802`
- Python 方法/函数使用 snake_case
- 常量使用 UPPER_SNAKE_CASE

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 跳过 UI 测试（无 Qt 环境时）
pytest tests/ -v -m "not ui"

# 仅运行快速测试
pytest tests/ -v -m "not slow"

# 带覆盖率
pytest tests/ --cov=core --cov=ui --cov-report=term-missing
```

- 测试超时: 120 秒（thread 方法）
- UI 测试需 `QT_QPA_PLATFORM=offscreen` 环境变量
- conftest.py 自动 mock pynput 模块

## 架构约定

### Mixin 模式

`ui/tray_app.py` 使用 Mixin 拆分为多个文件（hooks_mixin, popup_mixin, sleep_mixin 等），每个 Mixin 负责一个功能域。

### pyqtSignal 跨线程

- 后台线程通过 `pyqtSignal` 向 UI 线程发送结果
- 禁止在非 UI 线程直接操作 Qt 控件

### 安全预处理管道

`core/preprocessing/` 包含命令执行前的安全检查管道：validators → sanitizers → security → rate_limiter。

### 国际化

- 使用 `core/i18n.py` 的 `tr()` 函数
- `qt_compat.py` 中的包装控件自动调用 `tr()`
- 支持 zh-CN / en 双语

## 常用命令

```bash
# 运行应用
python main.py

# 安全模式启动
python main.py --safe-mode

# 构建（Nuitka + Inno Setup）
scripts\build_win11_setup.bat

# Pre-commit 安装
pre-commit install
```
