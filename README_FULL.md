# QuickLauncher 完整文档

[简体中文](README.md) | [English](README_EN.md) | [Full Docs](README_FULL_EN.md)

QuickLauncher 是一款面向 Windows 10 / 11 的桌面快速启动与轻量自动化工具。它以全局弹窗为核心，将应用启动、文件/文件夹访问、URL、热键、命令、动作链、批量启动和本地插件整合到同一个搜索入口。

当前源码版本来自 [core/version.py](core/version.py)：`1.6.3.3`，发布状态为 `stable`。本仓库的安装包/便携包自带运行时；从源码运行和构建需要 64 位 CPython 3.12。

## 目录

- [一、核心能力总览](#一核心能力总览)
- [二、安装与运行](#二安装与运行)
- [三、弹窗触发与搜索](#三弹窗触发与搜索)
- [四、快捷方式模型](#四快捷方式模型)
- [五、命令系统](#五命令系统)
- [六、动作链](#六动作链)
- [七、批量启动](#七批量启动)
- [八、插件系统](#八插件系统)
- [九、设置、主题与 UI](#九设置主题与-ui)
- [十、全局 Hook 与输入录制](#十全局-hook-与输入录制)
- [十一、数据、安全与更新](#十一数据安全与更新)
- [十二、构建、测试与 CI](#十二构建测试与-ci)
- [十三、项目结构](#十三项目结构)
- [十四、维护约定](#十四维护约定)

## 一、核心能力总览

| 模块 | 当前能力 |
|---|---|
| 弹窗入口 | 默认鼠标中键，可改为键盘、鼠标或混合组合；支持特殊应用独立触发配置 |
| 搜索 | 模糊匹配、拼音全拼/首字母、别名、标签、Web 搜索前缀、插件搜索源 |
| 快捷方式 | 7 类：FILE、FOLDER、URL、HOTKEY、COMMAND、CHAIN、BATCH_LAUNCH |
| 命令 | CMD、PowerShell、Python、Git Bash、内置命令；支持模板变量、参数表单、输出捕获和结果动作 |
| 内置命令 | 33 个命令，覆盖开发者工具、网络诊断、系统工具、插件管理和维护任务 |
| 动作链 | 可视化画布、节点连接、参数绑定、节点快照、取消执行、189 个内置处理器 |
| 插件 | `.qlzip` 安装、热加载、启用/禁用、失败隔离、权限声明、内置命令、搜索源、动作链处理器、常驻 worker |
| Hook | C++ `hooks.dll` 管理低级鼠标/键盘钩子、Raw Input 兜底、RegisterHotKey、宏录制/回放 |
| 数据安全 | 原子写入、配置备份、历史快照、导入清洗、路径穿越防护、受控 URL 访问 |
| 发布安全 | GitHub Releases、Ed25519 发布签名、SHA-256 校验、安装器可信目录检查 |

## 二、安装与运行

### 2.1 发布包

前往 [GitHub Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases) 下载：

- `QuickLauncher_Setup_<version>.exe`：安装版，使用 Inno Setup。
- `QuickLauncher_Portable_<version>.zip`：便携版，解压后运行 `QuickLauncher.exe`。

发布包包含 QuickLauncher 自身运行所需的 Python/Qt 运行时。普通用户不需要另行安装 Python。

### 2.2 源码运行

```powershell
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

源码运行要求：

- Windows 10 / 11 x64。
- CPython 3.12。
- `requirements.txt` 中的 PyQt5、pywin32、Pillow、psutil、pynput、watchdog、qrcode 等依赖。

### 2.3 运行模式

```powershell
py -3.12 main.py
py -3.12 main.py --safe-mode
py -3.12 main.py --safe-mode --smoke-test
py -3.12 main.py --plugin-helper <script.py> --plugin-site <site-packages> -- ...
```

`--safe-mode` 会关闭插件、Hook、自动更新和自定义背景，用于排障。`--plugin-helper` 是打包版运行插件自带 Python 库的受控子进程入口。

## 三、弹窗触发与搜索

### 3.1 触发方式

默认触发方式是鼠标中键。设置页可配置：

| 字段 | 说明 |
|---|---|
| `popup_trigger_mode` | 普通触发模式：`mouse`、`keyboard`、`hybrid` |
| `popup_trigger_button` | 鼠标按键：`left`、`right`、`middle`、`x1`、`x2` |
| `popup_trigger_keys` | 键盘主键列表 |
| `popup_trigger_modifiers` | 修饰键：`ctrl`、`alt`、`shift`、`win` |
| `popup_special_trigger_*` | 特殊应用触发配置，默认是 Ctrl+中键 |

特殊应用列表包含 CAD、3D 建模和图形软件。鼠标触发按指针所在窗口判断特殊应用；键盘触发按前台窗口判断特殊应用。

双击 Alt 可以暂停或恢复触发。暂停期间中键、键盘触发和特殊触发都不会打开弹窗。

### 3.2 弹窗行为

- 可配置弹窗位置：鼠标居中、鼠标左上、屏幕居中、右下角。
- 可固定弹窗，固定后支持拖拽移动。
- 可选择鼠标离开后自动关闭，或固定后再次触发是否新开弹窗。
- 搜索框和标题栏可用 Tab 切换默认显示状态。
- Dock 可显示常用项，支持单行、双行和三行高度。

### 3.3 搜索能力

搜索入口会合并以下来源：

- 用户快捷方式名称、别名、标签。
- 拼音全拼和首字母。
- 内置命令及其别名。
- Web 搜索前缀。
- 插件注册的搜索源。
- 系统图标和命令快捷入口。

输入 `/` 会进入内置命令浏览；输入命令别名可以直接触发对应命令。

## 四、快捷方式模型

QuickLauncher 当前支持 7 类快捷方式。数据模型位于 [core/data_models.py](core/data_models.py)。

| 类型 | 用途 | 主要字段 |
|---|---|---|
| `file` | 启动应用或打开文件 | `target_path`、`target_args`、`working_dir`、`run_as_admin` |
| `folder` | 打开文件夹 | `target_path`、`run_as_admin` |
| `url` | 打开网址 | `url`、`preferred_browser_path`、`preferred_browser_args` |
| `hotkey` | 发送快捷键 | `hotkey_modifiers`、`hotkey_key`、`hotkey_keys` |
| `command` | 执行命令或内置命令 | `command`、`command_type`、`command_params`、`capture_output` |
| `chain` | 执行动作链 | `chain_steps`、`chain_canvas`、`chain_data`、`module_id` |
| `batch_launch` | 顺序启动一组目标 | `batch_launch_steps`、`module_id` |

所有快捷方式共有字段包括 `name`、`enabled`、`tags`、`alias`、`icon_path`、`order`、`use_count`、`smart_order`、`trigger_mode`。

### 4.1 命令快捷方式

`command_type` 支持：

- `cmd`
- `powershell`
- `python`
- `bash`
- `builtin`

命令可启用变量模板、输出捕获、超时、输出长度限制、参数表单、环境变量和编码选择。默认命令超时为 10 秒，输出保留上限默认 20,000 字符。

### 4.2 URL 快捷方式

URL 支持默认浏览器，也可以绑定指定浏览器和参数。URL 执行支持变量模板，例如把 `{{input}}` 或选中文件变量拼入 URL。URL 延迟测试使用受控请求路径，避免在 UI 线程阻塞。

### 4.3 权限启动

文件、文件夹、URL 和命令可以请求管理员启动。QuickLauncher 以管理员身份运行而目标不需要管理员时，会通过 Explorer 的普通用户 token 降权启动，避免子进程被 QuickLauncher 的权限和生命周期绑住。安装和更新清理只关闭 QuickLauncher 自身，不会杀掉由 QuickLauncher 启动的其他程序。

## 五、命令系统

### 5.1 命令注册

命令统一进入 `CommandRegistry`：

- 旧式 slash 命令保留为兼容层。
- 新命令由 [core/builtin_command_catalog.py](core/builtin_command_catalog.py) 注册。
- 插件命令按 owner 索引，卸载插件时自动移除。
- 插件内置命令使用 `plugin-builtin:<plugin_id>` 来源隔离。

当前内置命令定义共 33 个：

| 命令 | 标题 | 类别 | 说明 |
|---|---|---|---|
| `uuid` | UUID | developer | 生成 UUID / GUID |
| `timestamp` | 时间戳 | developer | 当前 Unix 时间戳 |
| `base64` | Base64 | developer | Base64 编码 / 解码 |
| `urlencode` | URL 编码 | developer | URL 编码 / 解码 |
| `color` | 颜色 | developer | HEX/RGB/RGBA 转换 |
| `ip` | IP | network | 查询内网和公网 IP |
| `copy-path` | 复制路径 | system | 复制当前路径 |
| `hash` | Hash | developer | 文件 Hash，支持 MD5/SHA1/SHA256/SHA512 |
| `qr` | 二维码 | developer | 生成 QR 二维码 |
| `json` | JSON 工具 | developer | 格式化、压缩、校验 JSON |
| `jwt` | JWT 解码 | developer | 解码 Header 和 Payload，不验证签名 |
| `netdiag` | 网络诊断 | network | DNS、TCP 端口、Ping 延迟 |
| `cidr` | CIDR 子网计算 | network | 网段、掩码、广播地址、可用地址 |
| `tls` | TLS 证书检查 | network | 协议、颁发者、有效期、SAN |
| `path-audit` | PATH 体检 | developer | 失效目录、重复目录、命令遮蔽 |
| `process` | 进程分析 | system | 高占用进程、搜索进程、终止 PID |
| `sysreport` | 系统快照 | system | CPU、内存、磁盘、网络和启动时间 |
| `plugin-list` | 插件列表 | plugin | 列出已加载插件 |
| `plugin-reload` | 重载插件 | plugin | 重载插件 |
| `plugin-new` | 新建插件 | plugin | 创建插件模板 |
| `wifi` | Wi-Fi 密码查询 | system | 查询已保存 Wi-Fi 信息 |
| `hosts` | 编辑 Hosts 文件 | system | 打开 hosts 编辑路径 |
| `port` | 端口占用查询 | developer | 查询端口占用，可执行 kill |
| `dns` | 清理 DNS 缓存 | network | 刷新 Windows DNS 缓存 |
| `clean-cache` | 清理缓存 | internal | 清理项目临时缓存 |
| `config-repair` | 配置修复 | system | 扫描/修复旧配置变量语法 |
| `explorer` | 重启资源管理器 | system | 安全重启 Windows Explorer |
| `conflict` | 热键冲突检查 | system | 检查快捷键冲突和占用 |
| `git` | Git | developer | status、branch、log、diff、fetch、pull、checkout |
| `selected` | 选中文字 | system | 显示当前选中文字信息 |
| `clip` | 剪贴板 | system | 显示剪贴板内容和类型 |
| `env` | 环境变量 | system | 打开 Windows 环境变量编辑器 |
| `god` | 上帝模式 | system | 打开 God Mode 文件夹 |

### 5.2 命令参数与结果

命令参数字段包括 `name`、`type`、`required`、`default`、`choices`、`label`、`placeholder`、`help`、`source`、`validator`、`remember`、`sensitive`、`advanced`。敏感参数不会写入历史。

命令结果使用 `CommandResult`：

- `success` / `message` / `error`
- `display_type`
- `payload`
- `actions`

结果面板支持复制、打开 URL、打开文件/文件夹等动作按钮。

### 5.3 变量模板

常用变量包括：

| 变量 | 说明 |
|---|---|
| `{{clipboard}}` | 剪贴板文本 |
| `{{input}}` | 运行时输入 |
| `{{date}}` / `{{time}}` / `{{datetime}}` | 当前日期时间 |
| `{{lan_ip}}` / `{{wan_ip}}` | 内网 / 公网 IP |
| `{{selected_file}}` | 当前选中文件 |
| `{{selected_files}}` | 当前多个选中文件 |
| `{{selected_file_name}}` | 选中文件名 |
| `{{selected_file_dir}}` | 选中文件目录 |
| `{{app_dir}}` | 应用目录 |
| `{{config_dir}}` | 配置目录 |

命令和 URL 编辑器会高亮模板变量。命令支持 `:q` 之类安全引用语义，避免外部变量未经引用直接拼入命令。

### 5.4 命令预处理与风险

预处理管道包括：

1. 语法检查。
2. 语义检查。
3. 安全扫描。
4. 业务规则。
5. 审计日志。

设置项包括是否启用预处理、严格模式、审计日志、速率限制、危险模式阻断和变量引用要求。

## 六、动作链

动作链是 `chain` 快捷方式类型，由内置模块 `quicklauncher.action_chain` 提供。模块清单位于 [modules/action_chain/module.json](modules/action_chain/module.json)。

### 6.1 能力

- 可视化画布和传统步骤数据兼容。
- 节点可引用快捷方式或处理器。
- 支持参数绑定、输入绑定、步骤开关、错误即停、延迟执行。
- 执行时生成节点级快照。
- 支持取消执行和结果窗口大小设置。
- 禁止链递归和批量启动递归引用。

### 6.2 处理器

当前内置处理器共 189 个，主要类别包括：

- 文本、字符串格式化、正则。
- 数学、数学扩展、列表、集合、字典。
- JSON、HTTP、URL、网络工具。
- 文件与路径。
- 日期时间。
- 编码解码、加密 Hash、数据压缩。
- 数据验证。
- 系统信息、环境变量。
- 图像处理。
- 输入与调试、逻辑控制。

危险处理器会声明安全等级，例如写文件、下载、执行 Python cell 需要确认或权限能力。

## 七、批量启动

批量启动是独立 `batch_launch` 快捷方式类型，不再伪装成动作链。它用于按顺序启动多个已有目标，适合开工环境、一组项目工具或固定排障工具组合。

批量启动执行器会：

- 跳过禁用项。
- 阻止引用自身、动作链或其他批量启动导致递归。
- 复用普通快捷方式执行路径。
- 遵守单步延迟上限。

## 八、插件系统

### 8.1 分发模型

QuickLauncher 本体不再把官方插件源码作为运行时内容预装。当前模型是：

- `.plugins/`：源码仓库中的官方 `.qlzip` 插件包目录。
- `plugins/`：运行时插件安装目录。
- 发布包只包含空的 `plugins/` 目录和 `PLUGIN_DEV.md`，不复制源码插件目录。
- 用户安装 `.qlzip` 后才会解包到 `plugins/<plugin_id>/`。

### 8.2 官方插件包

| 包 | 描述 | 权限重点 |
|---|---|---|
| `api_tester.qlzip` | HTTP API 调试器，支持多种请求方法和格式化响应 | `network.request` |
| `disk_cleaner.qlzip` | 目录大小分析、安全清理回收站/缓存/临时文件 | `file.read`、`file.write`、`process.run`、`admin.required` |
| `event_inspector.qlzip` | Windows 事件日志分析、搜索、按来源聚合 | `file.read`、`process.run` |
| `file_tools.qlzip` | 复制选中文件路径、文件 Hash | `clipboard.write`、`file.read` |
| `network_tools.qlzip` | Ping、DNS 查询 | `network.request`、`process.run` |
| `process_tools.qlzip` | 进程资源排行、名称/PID 查找 | 无高风险权限 |
| `qr_code_scanner.qlzip` | 截图识别二维码，提供复制和打开链接动作 | `builtin.command`、`clipboard.write`、`open.url`、`process.run` |
| `screenshot_ocr.qlzip` | 截图 OCR，结果显示在命令面板 | `builtin.command`、`file.read`、`clipboard.write`、`process.run` |
| `startup_tools.qlzip` | 启动项审计、PATH 体检 | `file.read` |
| `text_tools.qlzip` | 文本反转、统计、大小写转换 | `clipboard.read`、`clipboard.write` |

### 8.3 插件能力

插件入口是 `main.py` 的 `register(api)`。常用 API：

- `register_command(...)`
- `register_builtin_command(...)`
- `register_search_source(...)`
- `register_module(...)`
- `register_chain_processor(...)`
- `read_clipboard()` / `write_clipboard(...)`
- `get_selected_files()`
- `open_url(...)` / `open_file(...)` / `open_folder(...)`
- `read_text_file(...)` / `write_data_file(...)`
- `http_request(...)`
- `run_process_capture(...)`
- `prewarm_persistent_helper(...)`
- `request_persistent_helper(...)`
- `stop_persistent_helper(...)`
- `launch_target(...)`
- `run_command(...)`

插件命令 handler 在共享线程池中运行，软超时为 30 秒。插件失败会记录失败计数，连续失败可能进入隔离状态。

### 8.4 插件包限制

`.qlzip` 安装会校验：

- 必须包含 `plugin.json`。
- 插件 ID 只能使用小写字母、数字、短横线、下划线。
- 禁止路径穿越和加密条目。
- 解压前文件数上限 1000。
- 解压前总大小上限 150 MB。
- 覆盖安装会先备份，失败时回滚。

当前插件仍以兼容模式运行在主进程内。权限声明是风险提示和受控 API 约束，不是强进程隔离。只安装可信插件。

## 九、设置、主题与 UI

设置模型位于 `AppSettings`：

- 主题：深色、浅色、跟随系统。
- 背景：主题背景、图片、纯色、Acrylic。
- 弹窗：透明度、图标大小、格子大小、列数、圆角、最大行数、位置、自动关闭、固定后多开。
- Dock：启用、透明度、高度模式。
- 全局 UI 缩放：90%-150%。
- Win11 高级颜色滤镜：黑点、白点、Gamma、色温、Acrylic、背景 Alpha，深色/浅色独立配置。
- Win10：独立同步阴影窗口，保持与弹窗显示、移动、透明度和动画一致。
- 命令管理：收藏命令、禁用内置命令。
- 插件管理：安装、启用、禁用、重载、开发模式。
- 数据：导入导出、可分享导出、备份恢复、配置历史。
- 支持/关于：版本信息、诊断和帮助入口。

## 十、全局 Hook 与输入录制

全局输入由 [hooks/hooks.dll](hooks/hooks.dll) 提供，C++ 源码在 [hooks_dll/](hooks_dll/)。

### 10.1 运行路径

- 鼠标低级钩子处理中键和五键鼠标。
- 键盘低级钩子处理组合键、Alt 双击、热键录入。
- Raw Input 作为低级钩子漏报或被系统移除时的兜底。
- 单主键键盘触发优先使用 `RegisterHotKey`。
- Python 层通过 `ctypes` 封装 DLL，负责生命周期、诊断和 Qt 主线程桥接。

### 10.2 可靠性约束

- 钩子回调快速返回，真正 Python 回调在线程队列中异步执行。
- 回调队列有界，避免阻塞低级钩子。
- 录制期间暂停运行时弹窗触发，防止“录入成功但立刻触发”。
- 快捷键录制、受保护组合录制、宏输入录制共享会话所有权，同一时刻只允许一种录制。
- DLL 卸载前确认钩子、回放和录制都安静；超时则保留 DLL 和回调引用至进程结束，避免 native crash。

### 10.3 宏能力

Hook DLL 支持：

- 统一键鼠事件录制。
- 垂直/水平滚轮。
- 鼠标移动轨迹。
- 键盘按下/抬起。
- Unicode 输入。
- 组合宏异步回放、取消、等待、状态查询。
- 回放结束或取消后释放仍按住的输入。

## 十一、数据、安全与更新

### 11.1 数据位置

源码运行时，数据通常位于仓库 `config/` 目录。安装/便携运行时以应用目录为根：

- `config/data.json`
- `config/icon_repo.json`
- `config/config_history/`
- `config/auto_backups/`
- `plugins/`
- `temp_icons/`

用户图标仓库和系统图标分离。系统图标来自 [assets/system_icons/config.json](assets/system_icons/config.json)。

### 11.2 配置安全

- 配置写入使用原子保存。
- 导入配置会经过类型、范围、颜色、字符串长度、列表长度和触发配置清洗。
- 快捷方式类型必须属于当前 7 类。
- 配置历史最多保留多个快照，便于恢复。
- 诊断中心可扫描缺失图标、失效路径、重复项、URL 和命令风险。

### 11.3 路径与网络安全

- 插件包安装使用 `resolve_under` 和安全相对路径校验。
- `.qlzip` 禁止路径穿越、重复路径、加密文件和超限包。
- HTTP 处理器和插件 HTTP API 使用受控 URL 访问，拦截本机、私网、链路本地和保留地址。
- Favicon 和 URL 延迟探测走受限读取，避免无限响应体。

### 11.4 自动更新

自动更新默认源是 GitHub Releases：

- 仓库：`LEISHIQIANG/QuickLauncher`
- 最新发布 API：`https://api.github.com/repos/LEISHIQIANG/QuickLauncher/releases/latest`

更新流程：

1. 读取最新 release。
2. 比较版本。
3. 解析安装包 URL、大小和 SHA-256。
4. 校验 URL、哈希和发布签名。
5. 下载到受控目录。
6. 启动安装器。

信任链包含 Ed25519 发布签名和 SHA-256 校验。签名公钥未配置或校验失败时，更新验证会失败关闭。

## 十二、构建、测试与 CI

### 12.1 本地质量门禁

```powershell
py -3.12 -m pip install -r requirements.txt -r requirements-dev.txt
py -3.12 scripts/release_gate.py --skip-smoke
```

`scripts/release_gate.py` 默认执行：

1. `ruff check --no-cache core ui hooks services tests`
2. `pytest`，覆盖 `core`、`services`、`hooks`，覆盖率下限 67
3. `scripts/audit_broad_exceptions.py --exclude-dir plugins --exclude-dir tools --max-total 1373 --max-unlogged 300`
4. `compileall core ui hooks services bootstrap plugins`
5. `scripts/check_release_artifacts.py --source-only --allow-source-runtime-plugins`
6. `scripts/post_package_smoke.py`

CI 使用 Windows runner、Python 3.12，执行 `release_gate.py --skip-tests --skip-smoke`、重点 pytest 子集和 `mypy --follow-imports=skip services/update`。

### 12.2 构建发布包

```powershell
scripts\build_win11_setup.bat
```

构建脚本要求：

- 64 位 CPython 3.12。
- Nuitka。
- PyQt5。
- MSVC/MinGW64 可用构建链。
- Inno Setup 6。
- `hooks/hooks.dll` 已存在，或先运行 `hooks_dll/build.bat`。

输出：

- `dist/QuickLauncher_Setup_<version>.exe`
- `dist/QuickLauncher_Portable_<version>.zip`
- `dist/QuickLauncher_release_<version>.json`
- `dist/QuickLauncher_Setup_<version>.sha256`
- `dist/QuickLauncher_Portable_<version>.sha256`

发布包验证会检查 EXE、Hook DLL、插件目录策略、安装器、便携包和 smoke test。

### 12.3 Hook DLL 构建

```powershell
cd hooks_dll
build.bat
```

脚本通过 Visual Studio / Build Tools 的 MSVC 和 Windows SDK 编译 `hooks.cpp`，输出到 `hooks/hooks.dll`。

## 十三、项目结构

```text
QuickLauncher/
├── main.py                         # 应用入口、单实例、safe-mode、plugin-helper、smoke-test
├── core/                           # 数据模型、执行器、命令、插件、动作链、安全、更新基础逻辑
│   ├── builtin_command_catalog.py   # 33 个内置命令定义
│   ├── command_registry.py          # 命令注册表与 CommandResult
│   ├── data_models.py               # ShortcutItem、AppSettings、AppData
│   ├── plugin_manager.py            # 插件扫描、安装、加载、隔离和 PluginAPI
│   ├── shortcut_command_exec.py     # 命令执行和输出捕获
│   ├── shortcut_executor.py         # 文件/文件夹/URL/热键/链/批量启动分发
│   ├── shortcut_chain_exec.py       # 动作链运行时
│   ├── batch_launch_exec.py         # 批量启动运行时
│   ├── chain/                       # 动作链处理器定义与执行
│   └── plugin/                      # 插件包安装、路径、常量
├── modules/
│   └── action_chain/                # 动作链模块化入口和 manifest
├── ui/                              # PyQt5 界面、弹窗、设置窗口、命令面板、主题组件
├── hooks/                           # hooks.dll Python 封装和兼容层
├── hooks_dll/                       # C++ Hook DLL 源码和构建脚本
├── services/update/                 # 自动更新检查、下载、信任校验和 UI
├── bootstrap/                       # 启动任务、依赖、日志、IPC、虚拟环境辅助
├── assets/                          # 图标、系统图标、资源
├── .plugins/                        # 官方 .qlzip 插件包
├── plugins/                         # 运行时插件目录和插件开发指南
├── scripts/                         # 构建、发布门禁、制品验证、安装器脚本
├── tests/                           # pytest 测试
└── .github/                         # CI 和 GitHub 模板
```

## 十四、维护约定

- 版本号只以 [core/version.py](core/version.py) 为准，安装脚本、manifest 和 release metadata 必须与它一致。
- 发布前优先运行 `py -3.12 scripts/release_gate.py --skip-smoke`。
- 修改发布包策略后运行 `scripts/check_release_artifacts.py --source-only --allow-source-runtime-plugins`。
- 修改插件 API 或官方插件包后同步 [plugins/PLUGIN_DEV.md](plugins/PLUGIN_DEV.md) 和 `.plugins/README.md`。
- 修改 Hook DLL 后同步 [hooks_dll/README.md](hooks_dll/README.md)，并确认 DLL 版本、能力位和 Python wrapper 匹配。
- 修改系统图标格式后同步 [assets/system_icons/README.md](assets/system_icons/README.md)。
- 文档里的功能数量应来自代码或包清单：快捷方式 7 类、内置命令 33 个、动作链处理器 189 个、官方插件包 10 个。

---

> QuickLauncher - 让效率从指尖开始。
