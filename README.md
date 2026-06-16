# QuickLauncher

[![CI](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md) | [插件开发](plugins/PLUGIN_DEV.md)

**按下鼠标中键，或使用你配置的键盘 / 鼠标组合，随时呼出启动面板。**

QuickLauncher 是一款面向 Windows 10 / 11 的桌面快速启动与轻量自动化工具。它可以启动应用、打开文件夹和 URL、发送热键、运行命令、执行动作链、批量启动一组目标，并通过本地插件继续扩展能力。

当前源码版本以 [core/version.py](core/version.py) 为准：`1.6.3.2` stable。安装包和便携包自带运行时，普通用户不需要在电脑上安装 Python；只有从源码运行或构建时才需要 CPython 3.12。

## 核心能力

| 能力 | 当前实现 |
|---|---|
| 全局触发 | 默认鼠标中键；可配置键盘、鼠标或键鼠混合触发；特殊应用可独立配置 Ctrl+中键等方案 |
| 快捷方式 | 7 类：文件 / 应用、文件夹、URL、热键、命令、动作链、批量启动 |
| 搜索 | 模糊匹配、拼音全拼和首字母、别名、标签、Web 搜索前缀、插件搜索源 |
| 命令系统 | CMD、PowerShell、Python、Git Bash、内置命令；支持参数表单、变量模板、环境变量、实时输出和结果按钮 |
| 内置命令 | 33 个内置命令，覆盖 JSON/JWT/Base64/Hash/TLS/CIDR/Git/进程/端口/Wi-Fi/Hosts/插件管理等场景 |
| 动作链 | 可视化动作链画布，内置 189 个处理器，覆盖文本、数学、列表、JSON、HTTP、文件、系统信息、图像、校验等节点 |
| 批量启动 | 独立 `batch_launch` 快捷方式类型，可按顺序启动多个目标并阻止递归引用 |
| 插件系统 | `.qlzip` 安装包、热加载、启用/禁用、失败隔离、权限声明、内置命令注册、搜索源、动作链处理器和常驻 worker |
| 外观与交互 | 深色/浅色和跟随系统、Acrylic/图片/纯色背景、Win10 阴影、全局 UI 缩放、Dock、固定和拖拽弹窗 |
| 数据安全 | 原子保存、配置历史、自动备份、导入清洗、路径穿越防护、URL 安全抓取、更新签名和 SHA-256 校验 |

## 安装

推荐下载发布包：

1. 打开 [Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases)。
2. 下载 `QuickLauncher_Setup_<version>.exe` 或 `QuickLauncher_Portable_<version>.zip`。
3. 安装版会通过 Inno Setup 安装，便携版解压后运行 `QuickLauncher.exe`。

从源码运行：

```powershell
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

源码运行要求 Windows 10 / 11、64 位 CPython 3.12。

## 30 秒上手

1. 启动后程序驻留在系统托盘。
2. 按鼠标中键呼出启动面板，输入关键字搜索。
3. 输入 `/` 浏览内置命令，或输入命令别名直接执行。
4. 在设置页添加文件、文件夹、URL、热键、命令、动作链或批量启动项。
5. 双击 Alt 暂停 / 恢复触发；在 CAD、3D 建模等特殊应用中可使用特殊触发配置。

## 内置命令示例

| 输入 | 用途 |
|---|---|
| `/json` | 格式化、压缩或校验 JSON |
| `/jwt` | 解码 JWT Header 和 Payload |
| `/hash` | 对选中文件计算 MD5/SHA1/SHA256/SHA512 |
| `/tls` | 检查域名 TLS 协议、证书颁发者和到期时间 |
| `/cidr` | 计算 IPv4 / IPv6 网段、掩码和可用地址范围 |
| `/port` | 查询端口占用，支持 `kill` 动作 |
| `/wifi` | 查询已保存 Wi-Fi 信息 |
| `/hosts` | 以管理员路径编辑 hosts |
| `/git` | 查看 status、branch、log、diff、fetch、pull、checkout |
| `/plugin-list` | 查看已加载插件 |

完整命令和参数见 [README_FULL.md](README_FULL.md)。

## 官方插件包

源码中的 `.plugins/` 目录保存官方 `.qlzip` 插件包；安装后才会解包到运行时 `plugins/` 目录。发布包不会把源码插件目录直接塞进主程序，只保留空的插件安装目录。

| 插件包 | 能力 |
|---|---|
| `api_tester.qlzip` | HTTP API 调试 |
| `disk_cleaner.qlzip` | 磁盘空间分析和安全清理 |
| `event_inspector.qlzip` | Windows 事件日志查看和聚合 |
| `file_tools.qlzip` | 复制选中文件路径、文件哈希 |
| `network_tools.qlzip` | Ping、DNS 查询 |
| `process_tools.qlzip` | 进程资源排行和进程查找 |
| `qr_code_scanner.qlzip` | 截图识别二维码 |
| `screenshot_ocr.qlzip` | 截图 OCR 识别文字 |
| `startup_tools.qlzip` | 启动项审计和 PATH 体检 |
| `text_tools.qlzip` | 文本反转、统计、大小写转换 |

插件开发见 [plugins/PLUGIN_DEV.md](plugins/PLUGIN_DEV.md)。

## 开发与验证

```powershell
# 安装依赖
py -3.12 -m pip install -r requirements.txt -r requirements-dev.txt

# 本地发布门禁：ruff、pytest + coverage、异常审计、compileall、元数据检查、包烟测
py -3.12 scripts/release_gate.py --skip-smoke

# CI 同款轻量门禁
py -3.12 scripts/release_gate.py --skip-tests --skip-smoke
py -3.12 -m mypy --follow-imports=skip services/update

# 安全模式烟测
py -3.12 main.py --safe-mode --smoke-test
```

构建安装包：

```powershell
scripts\build_win11_setup.bat
```

构建链路使用 CPython 3.12、Nuitka、PyQt5、MSVC/MinGW64 编译环境和 Inno Setup 6。

## 项目文档

- [完整中文文档](README_FULL.md)
- [Full English documentation](README_FULL_EN.md)
- [插件开发指南](plugins/PLUGIN_DEV.md)
- [Hook DLL 说明](hooks_dll/README.md)
- [系统图标说明](assets/system_icons/README.md)
- [GitHub 维护指南](.github/GITHUB_GUIDE.md)

## 许可证

[MIT](LICENSE)

---

> QuickLauncher - 效率，从指尖开始。
