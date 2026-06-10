# QuickLauncher

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20|%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md)

**按下鼠标中键，随时启动任何东西。**

QuickLauncher 是一款 Windows 桌面快速启动器。你可以在屏幕任意位置按下鼠标中键呼出面板，搜索并启动应用、文件夹、URL 和命令。它轻量、快速，开箱即可使用。

---

## 为什么选择 QuickLauncher？

**一次点击，立即访问。** 不需要记路径，也不需要翻开始菜单。按下中键后直接输入即可搜索，支持模糊匹配和中文拼音搜索，例如输入 `kb` 可以找到和“键盘”相关的内容。

**强大的命令系统。** 支持 CMD、PowerShell、Python、Git Bash 和内置命令，配合结构化参数、动态变量、输出捕获、命名 outputs 和实时结果面板，可以把常用脚本和排障动作沉淀成快捷命令。

**不只是打开文件。** 支持 6 种快捷方式：文件/应用、文件夹、URL、热键、命令、动作链。动作链可以串联多个步骤并传递上一步结果，适合搭建自己的效率工作流。

**多层安全设计。** 命令执行前会进行风险评估和预处理；配置损坏时可从备份恢复；ZIP 导入、图标下载、路径访问等外部输入都会经过安全校验。

**高度可定制。** 支持深色/浅色主题、亚克力毛玻璃、自定义背景图、图标大小、网格间距和列数配置。

**插件扩展。** 支持本地插件、`.qlzip` 打包安装、热加载、权限声明、自定义命令、内置命令入口和搜索源。官方插件包覆盖进程、磁盘、网络、启动项、文本工具和截图 OCR 等场景，可从 `.plugins/` 目录安装测试。

**中英双语界面，可运行时切换。**

## 安装

**推荐：下载安装包**

前往 [Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases) 下载最新版本安装包。

**从源码运行**

```bash
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

> 需要 Windows 10 / 11 和 Python 3.12。

## 30 秒上手

1. 启动后应用会驻留在系统托盘。
2. 按下鼠标中键呼出启动面板。
3. 直接输入关键字搜索，支持拼音、模糊匹配和别名搜索。
4. 输入 `/` 浏览全部可用命令。
5. 双击 Alt 可以暂停或恢复中键触发。

## 功能概览

| 能力 | 说明 |
|------|------|
| 全局触发 | 鼠标中键呼出，兼容 CAD / 3D 软件使用场景 |
| 智能搜索 | 模糊匹配、拼音全拼/首字母、别名、标签和搜索引擎前缀 |
| 命令系统 | CMD / PowerShell / Python / Git Bash、结构化参数、实时输出捕获 |
| 动作链 | 多步骤顺序执行，支持参数绑定、输入绑定、步骤间数据传递和取消 |
| 命令变量 | `{{clipboard}}`、`{{date}}`、`{{lan_ip}}`、`{{wan_ip}}`、`{{input}}` 等 |
| 安全预处理 | 语法、语义、安全扫描、业务规则和审计日志五层管道 |
| 外观定制 | 深色/浅色主题、亚克力背景、自定义图片和布局配置 |
| 插件系统 | 权限管理、热加载、`.qlzip` 打包、自定义命令、内置命令入口与搜索源 |
| 数据安全 | 原子保存、自动备份、20 个配置快照、配置损坏自动恢复 |
| 自动更新 | GitHub Releases 源、Ed25519 发布签名、SHA-256 校验、后台下载和静默安装 |

## 安心使用

| 关注点 | 实际情况 |
|--------|----------|
| 是否需要管理员权限 | 仅在需要时按需提权，不要求长期管理员运行 |
| 是否污染系统盘 | 数据默认保存在应用目录内 |
| 是否写注册表 | 不写注册表；自启动使用任务计划程序 |
| 是否联网 | 除自动更新检查外，不主动联网 |
| 自动更新信任链 | 默认要求发布签名；未配置签名公钥时更新校验失败关闭 |
| 空闲资源占用 | 空闲时 CPU 约 0-2%，内存通常低于 100MB |
| 是否容易卸载 | 删除应用目录即可清理主体文件 |

## 贡献

欢迎提交 Issue 和 PR。

```bash
# 运行测试
py -3.12 -m pytest tests/ -v

# 代码检查
py -3.12 -m ruff check core/ ui/ hooks/ services/
```

插件开发指南见 [plugins/PLUGIN_DEV.md](plugins/PLUGIN_DEV.md)。

## 许可证

[MIT](LICENSE)

---

> **QuickLauncher** - 效率，从指尖开始。
