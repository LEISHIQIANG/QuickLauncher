# QuickLauncher

> 一款轻量级的鼠标中键快速启动工具

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

## 简介

QuickLauncher 是一款 Windows 平台的快速启动工具。在任意位置按下鼠标中键，即可呼出应用弹窗，快速启动常用程序、打开文件夹、访问网址等。

## 主要特性

- **鼠标中键呼出**：在任何软件界面使用，包括桌面、浏览器、办公软件等
- **拖拽添加应用**：支持从桌面、文件资源管理器、开始菜单直接拖拽添加
- **多种启动方式**：支持应用程序、文件夹、网址、系统命令
- **智能防误触**：可设置游戏进程黑名单，避免游戏中误操作
- **自定义外观**：支持明暗主题、透明度调节、图标大小等个性化设置
- **配置导入导出**：方便备份和迁移配置

## 下载安装

### 📦 方式一：安装版（推荐）

适合需要开机自启动和系统集成的用户。

1. 访问 [Releases 页面](https://github.com/LEISHIQIANG/QuickLauncher/releases/latest)
2. 下载 `QuickLauncher_Setup_x.x.x.exe`
3. 运行安装程序，按照向导完成安装
4. 安装后自动启动，托盘图标显示运行状态

**特点**：
- ✅ 支持开机自启动
- ✅ 自动创建桌面快捷方式
- ✅ 支持通过控制面板卸载
- ✅ 自动关联文件类型

### 💚 方式二：绿色版（免安装）

适合便携使用或不想安装到系统的用户。

1. 访问 [Releases 页面](https://github.com/LEISHIQIANG/QuickLauncher/releases/latest)
2. 下载 `QuickLauncher_Portable_x.x.x.zip`
3. 解压到任意目录
4. 运行 `QuickLauncher.exe` 即可使用

**特点**：
- ✅ 无需安装，解压即用
- ✅ 便于携带和备份
- ✅ 配置文件保存在程序目录
- ✅ 删除文件夹即可完全卸载

### 开发环境

```bash
# 克隆仓库
git clone https://github.com/yourusername/QuickLauncher.git
cd QuickLauncher

# 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 设置 pre-commit hooks
pre-commit install

# 运行程序
python main.py
```

## 基本操作

### 呼出/隐藏弹窗
- **呼出**：按下鼠标中键（滚轮按下）
- **隐藏**：再次按下中键 / 点击弹窗外部 / 按 Esc 键
- **临时禁用**：双击 Alt 键可临时禁用/启用中键弹窗

### 添加应用
1. **拖拽添加**（推荐）：将 exe 程序、文件夹、快捷方式直接拖入弹窗空白格子
2. **点击添加**：点击空白格子，在文件选择对话框中选择文件

### 图标管理
- **编辑**：右键图标 → 编辑
- **删除**：右键图标 → 删除
- **调整顺序**：长按左键拖动图标到目标位置

## 高级功能

- **强制启动新进程**：Alt + 左键点击图标
- **拖放文件到图标**：将文件拖到程序图标上，用该程序打开文件
- **透明度调节**：Ctrl + 滚轮调节背景透明度，Shift + 滚轮调节图标透明度
- **特殊触发**：Ctrl + 中键触发特殊应用列表
- **锁定弹窗**：右键点击空白区域或点击图钉图标

## 开发

### 代码质量

```bash
# 代码格式化
black .

# 代码检查
ruff check . --fix

# 类型检查
mypy core ui bootstrap

# 运行测试
pytest --cov
```

### 构建

```bash
# Windows 11 构建
scripts\build_win11_setup.bat

# 查看更多构建选项
scripts\
```

## 文档

- [架构文档](docs/architecture.md)
- [开发指南](docs/CONTRIBUTING.md)
- [优化总结](docs/OPTIMIZATION_SUMMARY.md)
- [完整报告](docs/IMPLEMENTATION_REPORT.md)

## 系统要求

- Windows 7 及以上版本
- Python 3.8+ (开发环境)

## 贡献

欢迎贡献！请查看 [贡献指南](docs/CONTRIBUTING.md) 了解详情。

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解版本更新历史。

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 作者

**NAYTON**

## 致谢

感谢所有为本项目做出贡献的开发者。

