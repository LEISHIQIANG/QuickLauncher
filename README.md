# QuickLauncher

[![CI](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20|%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md)

**按一下鼠标中键，随时随地启动你想要的一切。**

QuickLauncher 是一款 Windows 桌面快速启动器 —— 在屏幕任意位置按下鼠标中键，即可呼出启动面板，搜索并打开应用、文件夹、网址、执行命令。轻量、快速、开箱即用。

---

## 为什么选择 QuickLauncher？

**按一下中键，即刻触达一切。** 不需要记路径、不需要翻菜单。鼠标中键呼出面板，直接输入就搜索，支持中文拼音匹配 —— 输入 `kb` 就能找到"键盘"相关的内容。

**强大的命令系统，扩展性无限。** 支持 CMD、PowerShell、Python、Git Bash 四种命令运行时，搭配参数化模板和动态变量（剪贴板、日期、IP 等），几乎可以实现你能想到的任何操作。执行结果实时捕获并展示在面板内，超时可控、随时可取消。

**不只是打开文件。** 6 种快捷方式覆盖全部场景：启动应用、打开文件夹、访问网页、发送热键组合、执行脚本命令、串联多步骤动作链自动化工作流。动作链最多 50 步，步骤间可传递数据，适合构建个人效率流水线。

**多维度安全，放心用就好。** 命令执行前自动检测风险并提示你，不是禁止而是让你知情决策。配置文件损坏了？自动从备份恢复，不需要你手动修。ZIP 导入、图标下载等对外操作全部做了安全校验，防注入、防路径穿越，不需要你操心。

**高度自定义，质感拉满。** 深色 / 浅色主题一键切换，毛玻璃亚克力效果、自定义图片背景任选，图标大小、格子间距、列数全部可调，打造属于你的启动面板。

**插件生态，无限扩展。** 支持自定义插件，`.qlzip` 打包一键安装，热加载无需重启。插件可注册斜杠命令和自定义搜索源，权限分级管理。内置 8 个插件覆盖进程管理、磁盘清理、网络诊断等场景。

**中文 / English 双语，运行时切换，无需重启。**

## 快速安装

**下载安装包（推荐）：** 前往 [Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases) 下载最新版，双击安装即可。

**从源码运行：**

```bash
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

> 需要 Python 3.12，Windows 10 / 11。

## 30 秒上手

1. 启动后程序驻留在**系统托盘**
2. **鼠标中键**呼出启动面板
3. 直接输入搜索 —— 支持拼音、模糊匹配、别名搜索
4. 输入 `/` 浏览所有可用命令
5. **Alt 连按两次**暂停 / 恢复中键触发

## 核心功能一览

| 能力 | 说明 |
|------|------|
| 全局呼出 | 鼠标中键一键唤出，自动兼容 CAD / 3D 软件中键操作 |
| 智能搜索 | 模糊匹配 + 拼音（全拼 / 首字母）+ 别名 / 标签 + 引擎前缀 |
| 命令系统 | CMD / PowerShell / Python / Git Bash，参数化模板，输出实时捕获 |
| 动作链 | 多步骤串联执行，步骤间数据传递，适合自动化工作流 |
| 命令变量 | `{{clipboard}}`、`{{date}}`、`{{lan_ip}}`、`{{wan_ip}}`、`{{input}}` 等动态变量 |
| 安全预处理 | 5 层管道：语法 → 语义 → 安全扫描 → 业务规则 → 审计日志 |
| 外观定制 | 深色 / 浅色主题、亚克力背景、自定义图片、布局自由配置 |
| 插件系统 | 权限管理、热加载、`.qlzip` 打包、自定义命令和搜索源 |
| 数据安全 | 原子保存、自动备份、20 个配置快照、损坏自动恢复 |
| 自动更新 | GitHub Releases 源，SHA-256 校验，静默安装 |

## 用得放心

| 你关心的 | 实际情况 |
|----------|----------|
| 需要管理员权限？ | 按需自动申请，不需要常驻管理员运行 |
| 会往 C 盘乱塞文件？ | 所有数据都在程序目录下，不污染系统盘 |
| 写注册表吗？ | 不写。开机自启通过任务计划实现，随时可关 |
| 会偷偷联网？ | 除自动更新检查外无任何联网行为 |
| 后台吃资源？ | 空闲时 CPU 0-2%，内存占用 < 100MB |
| 卸载干净吗？ | 删除程序目录即可，不残留注册表和系统文件 |

## 安全模式

如果程序启动异常（如插件冲突、钩子冲突），可以使用安全模式启动：

```bash
py -3.12 main.py --safe-mode
```

安全模式下以下功能会被禁用：
- 插件系统（不加载任何插件）
- 鼠标钩子和键盘钩子（中键唤出不可用）
- 自动更新检查
- 自定义背景图片

配置和数据不受影响，可以正常修改设置。排除问题后以正常模式重启即可恢复全部功能。

## 参与贡献

欢迎提交 Issue 和 PR！

```bash
# 运行测试
py -3.12 -m pytest tests/ -v

# 代码检查
py -3.12 -m ruff check core/ ui/ hooks/ services/
```

## License

[MIT](LICENSE)

---

> **QuickLauncher** — 让效率从指尖开始。
