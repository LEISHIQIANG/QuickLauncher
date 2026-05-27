# QuickLauncher

[![CI](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-yellow.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20|%2011-lightgrey.svg)](https://www.microsoft.com/windows)

QuickLauncher 是一款 **Python + PyQt5** 构建的 **Windows 桌面快速启动器**。按下鼠标中键即可呼出启动面板，快速启动程序、打开文件/文件夹/URL、执行命令、发送热键，支持拼音搜索、插件系统、中英双语。旨在以最轻量的操作触达最常用的工具，让效率从指尖开始。

---

## 目录

- [核心特性总览](#核心特性总览)
- [启动弹窗系统](#一启动弹窗系统)
- [快捷方式体系](#二快捷方式体系)
- [命令系统与斜杠命令](#三命令系统与斜杠命令)
- [命令变量与模板引擎](#四命令变量与模板引擎)
- [命令风险评估](#五命令风险评估)
- [动作链（CHAIN）](#六动作链chain)
- [配置窗口](#七配置窗口)
- [系统托盘](#八系统托盘)
- [全局钩子与热键系统](#九全局钩子与热键系统)
- [主题与视觉系统](#十主题与视觉系统)
- [插件系统](#十一插件系统)
- [数据管理与安全](#十二数据管理与安全)
- [自动更新系统](#十三自动更新系统)
- [国际化（i18n）](#十四国际化i18n)
- [性能与稳定性](#十五性能与稳定性)
- [项目结构](#十六项目结构)
- [技术栈](#十七技术栈)
- [快速开始](#快速开始)
- [开发指南](#开发指南)
- [CI/CD](#cicd)
- [贡献指南](#贡献指南)
- [致谢](#致谢)

---

## 核心特性总览

| 维度 | 能力 |
|------|------|
| **触发方式** | 鼠标中键全局呼出、Alt 双击暂停/启用、CAD/3D 软件兼容模式 |
| **快捷方式** | 6 种类型：FILE（文件/应用）、FOLDER（文件夹）、URL（网址）、HOTKEY（热键）、COMMAND（命令）、CHAIN（动作链） |
| **搜索能力** | 模糊匹配、拼音搜索（全拼+首字母）、别名/标签搜索、Web 搜索引擎前缀、插件扩展搜索源 |
| **命令系统** | CMD / Python / 内置命令三种模式，50+ 内置命令，命令变量模板，输出捕获，风险评估 |
| **动作链** | 最多 50 步串行动作，步骤间数据传递，错误中断控制，可取消执行 |
| **外观** | 深色/浅色主题、毛玻璃亚克力效果、自定义图片背景、图标/格子/列数自由配置 |
| **插件** | 权限管理、热加载/卸载、.qlzip 打包安装、自定义命令和搜索源注册 |
| **数据** | 原子保存、自动备份、配置历史（20 快照）、完整备份/恢复 ZIP、可分享配置导出、工厂重置 |
| **安全** | 路径边界校防目录穿越、SSRF 防护（Favicon 抓取）、命令变量注入防护、ZIP 炸弹防护、符号链接拒绝 |
| **多语言** | 中文（简体）/ English 双语，运行时切换 |
| **自动更新** | GitHub Releases 源、SHA-256 校验、后台下载、跳过版本、静默安装 |

---

## 一、启动弹窗系统

### 1.1 呼出与关闭

- **鼠标中键**：在桌面任意位置按下鼠标中键，弹出启动面板。弹窗跟随鼠标位置出现，支持多显示器 DPI 感知坐标转换。
- **Alt 双击**：快速按两次 Alt 键，切换鼠标中键的暂停/启用状态（暂停后中键不再触发弹窗）。
- **Escape**：清空搜索框内容；再次按 Escape 关闭弹窗。
- **点击外部区域**：弹窗自动关闭（钉选模式除外）。

### 1.2 弹窗视觉

- **无边框窗口**：采用 `Qt.FramelessWindowHint`，配合 Windows DWM API 实现毛玻璃亚克力效果。
- **Windows 10 / 11 兼容**：Windows 10 使用 `WS_EX_LAYERED` 分层窗口；Windows 11 使用 `DwmSetWindowAttribute` 实现圆角和深色标题栏。
- **三种背景模式**：
  - **跟随主题**：自动匹配深色/浅色主题色
  - **图片背景**：用户选择背景图片，自动模糊处理
  - **亚克力背景**：系统级毛玻璃模糊效果
- **透明度可调**：背景透明度 0-255 可配置，支持 `Ctrl + 滚轮` 实时调整。
- **动画**：弹出/收起 100ms 透明度渐变 + 揭示进度动画，分类切换滑动动画。

### 1.3 搜索系统

弹窗打开后直接输入即可搜索，搜索按以下优先级依次匹配：

1. **Web 搜索引擎前缀**：输入 `g 关键词` 打开 Google 搜索，`b` 百度，`y` Yandex，`e` Bing。
2. **斜杠命令**：输入 `/` 进入命令模式，模糊匹配所有已注册命令。
3. **本地快捷方式**：对名称、别名、标签进行模糊匹配。
4. **拼音搜索**：支持中文全拼和首字母缩写匹配（如输入 `kb` 可匹配"键盘"）。
5. **插件搜索源**：插件可注册自定义搜索源，在弹窗中参与搜索。

### 1.4 图标网格

- **可配置网格**：图标大小 16-64px、格子大小 32-80px、列数 3-12。
- **分类标签页**：快捷方式按文件夹（分类）组织，顶部显示标签栏，支持滚轮翻页。
- **键盘操作**：方向键选择、Enter 执行、Escape 清空/关闭。
- **拖拽支持**：拖拽调整图标顺序、拖拽外部文件创建快捷方式、拖拽快捷方式到其他分类。
- **钉选模式**：钉选弹窗后可保持显示，同时支持最多打开 2 个额外弹窗。

### 1.5 Dock 停靠栏

- 独立的 Dock 面板，显示已固定的常用快捷方式。
- 常驻于弹窗底部或侧边，方便一键访问高频工具。

### 1.6 命令结果内联展示

命令执行结果可直接渲染在弹窗内：

- **展示类型**：文本、表格、键值对、进度条、二维码、色块。
- **文本可选中**：`QTextEdit` 覆盖层支持 `Ctrl+C` 复制、`Ctrl+A` 全选。
- **操作按钮**：复制、打开 URL、打开文件/文件夹、保存文本、保存文件、创建快捷方式、关闭二维码服务器。
- **收藏/星标**：支持对命令结果进行收藏标记。
- **二维码**：支持生成二维码，智能检测剪贴板内容（URL 直接打开、文件路径启动本地 HTTP 文件服务器供手机扫码下载）。

### 1.7 快捷操作

| 操作 | 说明 |
|------|------|
| 鼠标中键 | 呼出/隐藏弹窗 |
| 直接输入 | 搜索快捷方式 |
| Enter | 执行搜索结果 |
| Escape | 清空搜索 / 关闭弹窗 |
| 方向键 | 翻页或选择搜索结果 |
| Alt + 左键点击 | 强制新进程启动 |
| Ctrl + 滚轮 | 调整背景透明度 |
| Shift + 滚轮 | 调整图标透明度 |

---

## 二、快捷方式体系

QuickLauncher 支持 **6 种快捷方式类型**，每种类型有独立的配置对话框：

### 2.1 FILE — 文件/应用

启动应用程序、打开文件或文件夹。

- **目标路径**：支持 `.lnk` 快捷方式自动解析（COM `IShellLink` 接口或 PowerShell 回退）
- **启动参数**：命令行参数传递
- **工作目录**：自定义工作目录
- **管理员运行**：可配置以管理员身份启动
- **窗口激活**：如果目标已在运行，自动将已有窗口提到前台（而非重复启动）
- **权限矩阵**：四象限权限处理——正常→正常、正常→管理员、管理员→正常（通过 Explorer Token 降级通道）、管理员→管理员

### 2.2 FOLDER — 文件夹

打开文件夹并在资源管理器中显示。

- 支持在文件夹中选中特定文件
- 支持链接物理文件夹实现自动同步

### 2.3 URL — 网址

在浏览器中打开 URL。

- **自动补全**：自动补全 `https://` 前缀
- **自定义浏览器**：可指定浏览器路径和启动参数
- **变量支持**：URL 中支持 `{clipboard}`、`{date}`、`{time}` 等变量
- **延迟测试**：通过 HEAD/GET 请求测试 URL 可达性，结果以颜色标识（绿色/黄色/红色）
- **安全 scheme 白名单**：仅允许 `http`、`https`、`file`、`mailto`、`tel`、`ms-settings`、`steam`、`vscode`、`obsidian`；拦截 `javascript`、`data`、`vbscript` 等危险 scheme
- **Favicon 自动获取**：自动抓取网站图标并缓存为 512x512 PNG（含 SSRF 防护、DNS Rebinding 检测、SVG 净化）

### 2.4 HOTKEY — 热键

向当前窗口发送键盘组合键。

- **键录制**：可视化录制组合键
- **修饰键区分**：区分左/右 Ctrl、Alt、Shift
- **触发模式**：
  - `immediate`：立即触发
  - `after_close`：先关闭面板、恢复原窗口焦点后触发
- **支持按键**：所有标准修饰键、功能键、方向键、特殊键（Tab、Enter、Esc、Space 等）
- **底层实现**：优先使用 Windows `SendInput` API + 扫描码映射，`pynput` 作为回退

### 2.5 COMMAND — 命令

执行 CMD、Python 或内置命令。

- **命令子类型**：
  - `cmd`：Windows CMD Shell 命令（默认）
  - `python`：Python 脚本执行
  - `builtin`：内置应用命令
- **执行模式**：
  - **静默模式**（`show_window=False`）：后台执行，`/c` 关闭窗口
  - **显示窗口**（`show_window=True`）：显示 CMD 窗口，`/k` 保持窗口打开
- **输出捕获**：可选捕获 stdout/stderr，支持流式更新（150ms 节流）、可取消、超时控制（默认 10s）、输出截断（默认 20000 字符）
- **编码检测**：自动检测 OEM 代码页 → 首选编码 → gbk → utf-8 → utf-16 → cp437 逐级回退
- **参数化**：支持定义命令参数（文本、下拉选择、布尔值、文件选择、文件夹选择）
- **环境变量**：可配置自定义环境变量
- **多行命令**：多行 CMD 命令自动包装为临时 `.cmd` 文件执行

### 2.6 CHAIN — 动作链

详见 [第六章：动作链](#六动作链chain)。

---

## 三、命令系统与斜杠命令

### 3.1 命令注册架构

QuickLauncher 拥有统一的命令注册系统 `CommandRegistry`：

- **注册去重**：拒绝重复 ID
- **别名映射**：大小写不敏感的别名查找
- **分类索引**：按类别组织命令
- **模糊搜索**：精确匹配 → 前缀匹配 → 子串匹配，搜索范围覆盖 id、title、description、category、aliases、search_terms
- **插件命令**：按 owner 索引，插件卸载时自动清理

### 3.2 内置命令完整列表

#### 应用控制

| 命令 | 别名 | 功能 |
|------|------|------|
| `/quit` | `quit_app` | 退出应用 |
| `/restart` | `restart_app` | 重启应用 |
| `/log` | `show_log` | 查看运行日志 |
| `/about` | `show_about` | 关于对话框 |
| `/help` | `show_help` | 帮助信息 |

#### 窗口管理

| 命令 | 别名 | 功能 |
|------|------|------|
| `/topmost` | `置顶`, `pin`, `toggle_topmost` | 切换窗口置顶 |
| `/pin-on` | `置顶开`, `topmost_on` | 强制开启置顶 |
| `/pin-off` | `置顶关`, `unpin`, `topmost_off` | 强制关闭置顶 |

#### 配置与诊断

| 命令 | 别名 | 功能 |
|------|------|------|
| `/config` | `配置窗口`, `show_config_window` | 打开配置窗口 |
| `/diagnostics` | `诊断`, `zhenduan` | 诊断中心 |
| `/shortcut-health` | `健康检查`, `health`, `icons` | 快捷方式和图标健康检查 |
| `/config-history` | `配置历史`, `peizhi lishi` | 查看配置变更历史 |
| `/clean-icon-cache` | `清理图标`, `icon-cache` | 清理图标缓存 |
| `/clean-cache` | `清理缓存`, `qingli huan cun` | 清理项目缓存（\_\_pycache\_\_、pytest\_cache 等） |
| `/reload-hooks` | `重装钩子`, `hooks`, `chongzhuang gouzi` | 重新加载全局钩子 |

#### Windows 系统快捷方式

| 命令 | 别名 | 功能 |
|------|------|------|
| `/control` | `open_control_panel` | 控制面板 |
| `/thispc` | `open_this_pc` | 此电脑 |
| `/recycle` | `open_recycle_bin` | 回收站 |
| `/taskmgr` | `任务管理器`, `task-manager`, `renwu guanliqi` | 任务管理器 |
| `/ms-settings` | `系统设置`, `windows设置` | Windows 设置 |
| `/services` | `服务`, `services.msc`, `fuwu` | 服务管理控制台 |
| `/devmgmt` | `设备管理器`, `devmgmt.msc`, `shebei guanliqi` | 设备管理器 |
| `/diskmgmt` | `磁盘管理`, `diskmgmt.msc`, `cipan guanli` | 磁盘管理 |
| `/ncpa` | `网络连接`, `ncpa.cpl`, `wangluo lianjie` | 网络连接 |
| `/startup` | `启动文件夹`, `shell-startup`, `qidong wenjianjia` | 启动文件夹 |
| `/msinfo32` | `系统信息`, `systeminfo`, `xitong xinxi` | 系统信息 |

#### 内部路径快捷方式

| 命令 | 别名 | 功能 |
|------|------|------|
| `/config-file` | `data.json`, `配置文件` | 用记事本打开配置文件 |
| `/icons-dir` | `图标目录` | 打开图标目录 |
| `/history-dir` | `历史目录` | 打开历史目录 |
| `/auto-backups` | `备份目录` | 打开自动备份目录 |
| `/error-log` | `错误日志` | 用记事本打开错误日志 |
| `/data-dir` | `数据目录` | 打开应用数据目录 |
| `/install-dir` | `安装目录` | 打开安装目录 |

#### 开发者/运维工具命令

| 命令 | 别名 | 功能 |
|------|------|------|
| `/urlencode` | `编码`, `解码`, `bianma`, `jiema` | URL 编码/解码 |
| `/color` | — | HEX 转 RGB/RGBA 颜色值 |
| `/ip` | — | 查看本机 IP（`local`/`public` 模式） |
| `/copy-path` | — | 从资源管理器复制选中文件路径（`name`/`dir`/完整路径） |
| `/hash` | — | 文件哈希计算（MD5/SHA1/SHA256） |
| `/uuid` | — | 生成 UUID v4 |
| `/timestamp` | — | 当前 Unix 时间戳 / 时间戳转日期 |
| `/base64` | — | Base64 编码/解码（256KB 限制） |
| `/qr` | — | 生成二维码（智能检测剪贴板：URL→打开链接、文件→HTTP 文件服务器） |
| `/json` | — | JSON 美化/压缩/验证（`pretty`/`min`/`validate`） |
| `/jwt` | — | 解码 JWT Token（Header + Payload） |
| `/netdiag` | — | 网络诊断（DNS 解析、TCP 端口连通性、Ping） |
| `/cidr` | — | CIDR 子网计算器（网络/掩码/广播/主机范围，IPv4 & IPv6） |
| `/tls` | — | TLS 证书检查（协议版本、颁发者、有效期、SAN） |
| `/path-audit` | `PATH 体检` | PATH 环境变量审计（无效目录/重复/影子命令） |
| `/wifi` | `wlan`, `无线密码` | 列出已保存的 Wi-Fi 并查询明文密码 |
| `/hosts` | — | 管理员权限打开 hosts 文件 |
| `/port` | `netstat` | 查找占用端口的进程，支持 `kill` 终止 |
| `/dns` | `flushdns` | 刷新 DNS 缓存 |
| `/env` | — | 打开环境变量编辑器 |
| `/git` | `git-status`, `git-pull` | Git 操作（status/branch/log/diff/fetch/pull/checkout） |
| `/process` | — | 进程查看器（按内存/CPU 排序、搜索、kill） |
| `/sysreport` | — | 系统快照（平台、CPU、内存、磁盘、网络、电池） |
| `/plugin list` | — | 列出所有已加载插件 |
| `/plugin reload` | — | 重新加载插件 |
| `/plugin new` | — | 从模板创建新插件 |
| `/conflict` | `冲突` | 热键冲突检测（内部重复、系统快捷键、Windows 全局热键注册） |
| `/god` | — | 打开 Windows God Mode |
| `/explorer` | — | 重启 Windows 资源管理器 |

---

## 四、命令变量与模板引擎

命令快捷方式支持 `{变量名}` 语法进行动态替换。使用 `{{` 和 `}}` 转义为字面花括号。

### 4.1 变量列表

| 变量 | 说明 | 示例输出 |
|------|------|----------|
| `{clipboard}` | 当前剪贴板文本 | `Hello World` |
| `{selected_text}` | 前台窗口选中的文本（`after_close` 模式） | `选中的内容` |
| `{date}` | 当前日期 | `2026-05-27` |
| `{time}` | 当前时间 | `14:30:00` |
| `{app_dir}` | 应用安装目录 | `C:\Program Files\QuickLauncher` |
| `{config_dir}` | 配置目录 | `<app_dir>\config` |
| `{input}` | 运行时用户输入（无提示） | `用户输入的内容` |
| `{input:提示文字}` | 运行时用户输入（带提示） | `用户输入的内容` |
| `{param:参数名}` | 命令参数值 | `自定义值` |
| `{chain:变量名}` | 动作链传递的变量 | `上一步的输出` |

### 4.2 安全引用（`:q` 后缀）

为防止命令注入，在 CMD 类型命令中使用外部输入变量时，**必须**添加 `:q` 后缀进行安全引用：

```
echo {clipboard:q}        ✅ 安全：自动转义
echo {input:文件名:q}      ✅ 安全：自动转义
echo {clipboard}           ❌ 危险：会被拒绝执行
```

- 系统自动检测未引用的外部变量并拒绝执行，提示正确的 `{name:q}` 语法
- 外部输入最大 1MB，自动剥离 Null 字节
- 纯变量命令（如 `{clipboard}` 单独作为命令）会被识别并拒绝——因为它只是字符串而非可执行命令

---

## 五、命令风险评估

执行命令前，系统会自动评估风险等级并提示用户，但不会阻止执行。

### 5.1 信息级提示

| 风险码 | 触发条件 |
|--------|----------|
| `run_as_admin` | 以管理员身份运行 |
| `shell_command` | 通过系统 Shell 执行（CMD 类型） |
| `clipboard_variable` | 使用了剪贴板变量 |
| `selected_text_variable` | 使用了选中文本变量 |

### 5.2 警告级提示

| 风险码 | 匹配模式 | 说明 |
|--------|----------|------|
| `delete_tree` | `rmdir /s`, `rd /s`, `rd /q` | 递归删除目录 |
| `delete_file` | `del /f`, `del /q`, `del /s`, `erase` | 删除文件 |
| `format_disk` | `format [盘符]:` | 格式化磁盘 |
| `shutdown` | `shutdown /s`, `/r`, `/g`, `/p` | 关机/重启 |
| `registry_delete` | `reg delete` | 删除注册表项 |
| `powershell_remove` | `Remove-Item`/`rm` + `-Recurse`/`-Force` | PowerShell 强制删除 |
| `powershell_exec_policy` | `Set-ExecutionPolicy` / `-ExecutionPolicy Bypass` | 绕过执行策略 |
| `service_control` | `sc delete/stop/start` / `net delete/stop/start` | 服务控制 |
| `diskpart` | `diskpart`, `bcdedit`, `bootrec` | 磁盘/引导配置 |
| `takeown_icacls` | `takeown` / `icacls` + `/grant`, `/reset`, `/f` | 修改所有权/ACL |
| `cmd_chain_delete` | `cmd /c del` / `cmd /k rd` | 链式删除 |
| `taskkill_force` | `taskkill /f` | 强制终止进程 |

---

## 六、动作链（CHAIN）

动作链允许将多个快捷方式串联执行，适合自动化工作流。

### 6.1 步骤结构

每个步骤包含：

| 字段 | 说明 |
|------|------|
| `shortcut_id` | 目标快捷方式 ID |
| `enabled` | 是否启用此步骤 |
| `stop_on_error` | 失败时是否中断链（默认 `True`） |
| `delay_ms` | 执行前延迟（0-60000ms） |
| `use_previous_output` | 将上一步输出作为当前步骤的 `{input}` |

### 6.2 执行机制

- 最多 **50 个步骤**，防循环引用（拒绝嵌套链和自引用）
- 每步执行后收集链变量：`{N.success}`、`{N.exit_code}`、`{N.stdout}`、`{N.stderr}`、`{N.output}`，以及 `prev.*` 快捷方式
- 支持**取消执行**（`threading.Event`）
- 步骤间延迟支持取消感知的 sleep
- 返回列表型 `CommandResult`，展示所有步骤状态和耗时

### 6.3 典型场景

```
链：部署检查
  步骤1: /git status           → 检查 Git 状态
  步骤2: /git pull             → 拉取最新代码（延迟 2000ms）
  步骤3: 执行测试命令           → 传入上一步输出
  步骤4: /sysreport            → 生成系统报告
```

---

## 七、配置窗口

### 7.1 打开方式

- 系统托盘左键点击
- 弹窗内输入 `/config`
- 托盘右键菜单 → 设置

### 7.2 窗口特性

- 无边框设计 + 毛玻璃亚克力效果
- 自定义标题栏（支持拖拽、主题化设置齿轮图标）
- 状态栏：管理员状态点（红=管理员、绿=普通、紫=代码模式）、Windows 版本、应用版本
- 240ms 滑入动画

### 7.3 快捷方式管理（Launcher View）

- **可视化编辑器**：文件夹面板 + 图标网格
- **右键菜单**：编辑、删除、移动、复制
- **Ctrl/Shift 多选**：批量删除、移动、启用、禁用、撤销
- **开始菜单/桌面扫描**：自动发现已安装应用
- **图标仓库**：合并展示随软件安装的系统图标与用户自己的图标仓库，支持复制到普通分类后编辑
- **拖拽排序**：拖拽调整图标和分类顺序

### 7.4 设置面板（Settings）

设置面板通过侧边栏导航，包含以下页面：

#### 外观

- 背景模式切换（跟随主题 / 图片背景 / 亚克力背景）
- 图片背景文件选择
- 布局配置：图标大小（16-64px）、格子大小（32-80px）、列数（3-12）
- 主题切换（深色/浅色）

#### 弹窗行为

- 弹窗对齐模式、悬停离开延迟、自动关闭、钉选多开、双击间隔等

#### 系统

- **开机自启**：通过 Windows 任务计划实现（非注册表 Run 键，更可靠）
- **启动时显示设置窗口**
- **硬件加速**：提升进程优先级
- **隐藏托盘图标**（仍可通过 `/config` 命令打开设置）
- **轻睡眠模式**：闲置 10 秒后降低资源占用
- **日志控制**：禁用日志 / 启用调试日志
- **自动更新检查**
- **排序模式**：自定义排序 vs 智能排序（基于使用次数和最近使用时间）

#### 命令管理

- 命令相关设置

#### 插件管理

- 启用/禁用已安装插件

#### 数据

- **完整配置备份/恢复**：ZIP 包含 data.json + 图标 + 背景图片
- **可分享配置导出**：仅导出热键/URL/命令，自动隐藏敏感路径
- **恢复出厂设置**：清除注册表键、图标缓存、应用数据，重置为默认配置
- **配置历史浏览**：20 个压缩 JSON 快照，支持一键恢复

#### 支持 / 关于

- 帮助链接、版本信息、致谢

### 7.5 快捷方式编辑对话框

每种快捷方式类型有专属的编辑对话框：

| 对话框 | 编辑内容 |
|--------|----------|
| **ShortcutDialog** | FILE/FOLDER：名称、目标路径、参数、工作目录、图标、标签、管理员运行 |
| **UrlDialog** | URL：名称、URL、自定义浏览器、图标 |
| **CommandDialog** | COMMAND：名称、命令文本、类型、参数、环境变量、编码、超时、输出捕获 |
| **HotkeyDialog** | HOTKEY：名称、组合键录制、触发模式 |
| **ChainDialog** | CHAIN：步骤列表、每步配置（目标、延迟、错误处理、数据传递） |

---

## 八、系统托盘

### 8.1 托盘图标

- 自定义图标显示在 Windows 系统托盘
- 提示文字：`QuickLauncher\n左键=设置 | 中键=启动器`
- 左键/双击：打开配置窗口
- 右键：弹出自定义菜单（毛玻璃效果 + 内联子菜单）

### 8.2 托盘菜单

| 菜单项 | 功能 |
|--------|------|
| 设置 | 打开配置窗口 |
| 重启 | 重启应用（VBS 脚本机制） |
| 运行日志 | 打开日志查看器 |
| 诊断中心 | 打开诊断窗口 |
| 退出 | 退出应用 |

### 8.3 后台服务

托盘应用运行以下后台定时器：

| 定时器 | 间隔 | 功能 |
|--------|------|------|
| 设置同步 | 120ms 防抖 | 同步设置变更 |
| 内存检查 | 120s | 运行 `MemoryGuard` 内存优化 |
| 进程检查 | 10s | 监控 CAD/3D 等特殊应用进程 |
| 延迟初始化 | 10ms | 预初始化弹窗、预加载图标、初始化文件夹监听 |

---

## 九、全局钩子与热键系统

### 9.1 C++ Hook DLL

QuickLauncher 使用自研的 **C++ DLL**（`hooks/hooks.dll`）处理全局鼠标和键盘钩子，基于 Win32 `SetWindowsHookEx` API：

- **鼠标钩子**：全局捕获 `WM_MBUTTONDOWN`（鼠标中键），触发弹窗
- **键盘钩子**：捕获 Alt 键双击，切换中键暂停/启用状态
- **专用线程管理**：钩子在独立线程上运行，通过 Ready Event 同步
- **互斥锁保护**：特殊应用列表等共享数据通过 mutex 保护

### 9.2 特殊应用兼容

内置 35+ CAD/3D 应用列表（AutoCAD、Revit、3ds Max、Blender、Maya、SolidWorks、CATIA 等），当检测到这些应用运行时：

- 鼠标中键触发改为 **Ctrl + 中键**，避免与 CAD/3D 软件自身的中键操作（如平移、旋转）冲突
- 每 10 秒监控进程状态，检测到特殊应用时自动重装钩子

### 9.3 Python 回退

DLL 不可用时，自动回退到 Python/系统 API 实现钩子功能。

### 9.4 热键冲突检测

`/conflict` 命令可扫描：

- 内部重复热键
- 与 Windows 系统快捷键的冲突
- Windows 全局热键注册碰撞（通过 Windows API 检测）

### 9.5 Alt 双击暂停

快速按两次 Alt 键，切换鼠标中键的启用/暂停状态。暂停后：

- 鼠标中键不再触发弹窗
- 再次 Alt 双击恢复

---

## 十、主题与视觉系统

### 10.1 设计语言

采用 Apple 风格设计系统，包含完整的颜色体系：

- 主色、次色、强调色
- 背景、表面、卡片色
- 文本色（主/次/三级）
- 边框、分割线、阴影色
- 状态色（成功/警告/错误/信息）
- 深色/浅色两套完整色板

### 10.2 主题模式

- **深色主题**（默认）：深色背景 + 浅色文本
- **浅色主题**：浅色背景 + 深色文本
- 设置面板中一键切换

### 10.3 毛玻璃效果

- 基于 Windows DWM API（`dwmapi.dll`）实现
- `DwmExtendFrameIntoClientArea` 扩展客户区到边框
- Windows 11 圆角通过 `DWMWA_WINDOW_CORNER_PREFERENCE` 控制
- 深色标题栏通过 `DWMWA_USE_IMMERSIVE_DARK_MODE` 实现

### 10.4 自定义样式组件

- **按钮**：primary / secondary / danger / ghost 变体
- **输入框**：聚焦状态动画
- **滚动条**：细圆角设计
- **下拉框**：自定义箭头
- **分组框**：标题装饰
- **滑块**：自定义手柄
- **弹出菜单**：毛玻璃背景、内联子菜单、悬停高亮动画、圆角、图标支持

### 10.5 背景定制

| 模式 | 说明 |
|------|------|
| 跟随主题 | 自动匹配当前深色/浅色主题 |
| 图片背景 | 选择本地图片，自动高斯模糊处理 |
| 亚克力背景 | 系统级毛玻璃模糊效果 |

每种模式可独立配置透明度、模糊半径、边缘不透明度。

---

## 十一、插件系统

### 11.1 插件架构

- 插件位于 `plugins/` 目录，每个插件一个子目录
- 入口文件 `main.py` + 清单文件 `manifest.json`
- 使用 `importlib` 动态加载
- 支持热加载/卸载

### 11.2 Plugin API

插件接收 `PluginAPI` 对象，提供以下能力：

| 方法 | 说明 |
|------|------|
| `register_command(def)` | 注册斜杠命令到 CommandRegistry |
| `register_search_source(name, cb)` | 注册自定义搜索源到弹窗 |
| `read_clipboard()` / `write_clipboard(text)` | 剪贴板读写 |
| `get_selected_files()` | 获取资源管理器中选中的文件 |
| `launch_target(target)` | 启动文件/URL |
| `run_command(command_id)` | 执行其他已注册命令 |

### 11.3 权限管理

插件在 `manifest.json` 中声明所需权限：

| 权限 | 说明 | 风险等级 |
|------|------|----------|
| `clipboard.read` | 读取剪贴板 | 普通 |
| `clipboard.write` | 写入剪贴板 | 普通 |
| `file.read` | 读取文件 | 普通 |
| `file.write` | 写入文件 | **高风险** |
| `open.url` | 打开 URL | 普通 |
| `open.file` | 打开文件 | 普通 |
| `process.run` | 执行进程 | **高风险** |
| `network.request` | 网络请求 | 普通 |
| `admin.required` | 需要管理员权限 | **高风险** |

高风险权限需要用户明确授权。

### 11.4 事务化注册

- 命令先收集、再原子提交
- 批量注册失败时自动回滚所有命令
- 按 owner 索引，插件卸载时自动清理

### 11.5 .qlzip 打包安装

- 插件可打包为 `.qlzip` 文件（标准 ZIP 归档）
- 安装流程：备份现有插件 → 解压 → 清单验证
- 安全措施：路径穿越防护、符号链接拒绝

### 11.6 内置插件

| 插件 | 功能 |
|------|------|
| **process_tools** | 进程列表、终止、管理 |
| **startup_tools** | 启动项管理 |
| **file_tools** | 文件操作工具 |
| **event_inspector** | Windows 事件查看 |
| **disk_cleaner** | 磁盘清理工具 |
| **api_tester** | HTTP API 测试工具 |
| **network_tools** | 网络诊断工具 |
| **text_tools** | 文本处理（反转、统计、大小写转换） |

---

## 十二、数据管理与安全

### 12.1 数据存储

配置数据存储在 `config/data.json`，结构如下：

```json
{
  "version": "2.5",
  "settings": { ... },
  "folders": [
    {
      "id": "dock",
      "name": "Dock",
      "is_dock": true,
      "items": [ ... ]
    },
    {
      "id": "default",
      "name": "常用",
      "items": [ ... ]
    }
  ]
}
```

用户自己的图标仓库单独保存在同目录的 `icon_repo.json`；随软件安装的系统图标来自 `assets/system_icons/config.json`：

```json
{
  "version": "1.0",
  "items": [ ... ]
}
```

### 12.2 数据安全机制

| 机制 | 说明 |
|------|------|
| **原子保存** | 写入临时文件后 `os.replace()` 替换，防止崩溃导致数据损坏 |
| **双重锁** | 内存锁 (`RLock`) + I/O 锁分离，避免死锁 |
| **节流保存** | 500ms 防抖，批量快速变更只触发一次磁盘写入 |
| **批量更新** | `batch_update()` 上下文管理器实现事务性多操作 |
| **自动备份** | 每次保存前自动备份，保留最新 5 份（带时间戳） |
| **配置历史** | 最多 20 个压缩 JSON 快照，支持一键恢复到任意历史版本 |

### 12.3 备份与恢复

- **完整备份**：ZIP 包含 data.json + 图标 + 背景图片
- **可分享导出**：仅导出热键/URL/命令类型，自动隐藏敏感路径（如本地文件路径），支持从 EXE/DLL 提取图标
- **恢复出厂**：清除注册表键、图标缓存、应用数据，重置为默认 AppData
- **图标路径重定向**：修复一个缺失图标路径时，自动重定向同一目录下的其他缺失图标

### 12.4 路径安全（path_security）

| 函数 | 说明 |
|------|------|
| `resolve_existing(path)` | 安全路径解析（支持 `~` 展开） |
| `is_safe_child(root, candidate)` | 验证路径是否在根目录内 |
| `resolve_under(root, candidate)` | 路径越界时抛出 `UnsafePathError` |
| `safe_rmtree_child(root, target)` | 安全删除（仅限确认的子路径，拒绝符号链接） |

应用于 ZIP 导入、缓存清理、工厂重置等场景，防止目录穿越攻击。

### 12.5 Favicon 安全抓取

- 阻止 localhost、内网 IP、回环地址等请求（防 SSRF）
- DNS 解析检查防御 DNS Rebinding 攻击
- 重定向限制 5 跳，每跳验证目标
- SVG 净化：移除 `<script>`、`<foreignObject>`、`<image>` 及外部 `href`
- 文件大小限制：图标 5MB、HTML 1MB、Manifest/SVG 512KB
- 图片像素限制：1600 万像素

### 12.6 图标缓存清理

- 移除 EXE/DLL 文件（不应缓存为图标）
- 移除超大文件（>10MB）
- 移除未被任何快捷方式引用的孤立图标
- 移除内容哈希重复的图标（MD5 检测）
- 支持 dry-run 模式预览清理效果

### 12.7 Smart Sort 智能排序

基于 `use_count`（使用次数）和 `last_used_at`（最近使用时间）自动排序，但**不会覆盖用户手动拖拽的自定义顺序**。

---

## 十三、自动更新系统

### 13.1 数据源

- **主源**：GitHub Releases API（`LEISHIQIANG/QuickLauncher`）
- **备源**：通用 API 端点
- 自动从 Release Body 或 Asset Digest 提取 SHA-256 哈希

### 13.2 更新流程

```
启动 → UpdateChecker 后台检查（默认开启）
         ↓
    发现新版本 → 弹出 UpdateNotification 对话框
         ↓
    用户选择：下载 / 跳过此版本
         ↓
    下载 → 进度事件实时更新 → SHA-256 校验
         ↓
    安装 → 启动 Inno Setup 安装器（/VERYSILENT）
         ↓
    退出当前进程，安装器完成更新
```

### 13.3 安全措施

| 措施 | 说明 |
|------|------|
| HTTPS 强制 | 仅允许 HTTPS 下载 |
| 允许主机白名单 | 验证下载 URL 的主机 |
| SHA-256 校验 | 下载后校验文件哈希 |
| 大小验证 | Content-Length 检查 + 最大 200MB 限制 |
| 临时文件 | 使用临时文件 + 原子重命名 |
| 可信目录 | 安装时验证安装包在可信目录内 |

### 13.4 配置

- 自动更新开关（系统设置页）
- 跳过版本记录（`.update_state.json`）
- 开启后每次启动检查一次（非持续轮询）

---

## 十四、国际化（i18n）

### 14.1 支持语言

| 语言 | 标识 |
|------|------|
| 中文（简体） | `zh_CN`（默认） |
| English | `en_US` |

### 14.2 实现

- `core/i18n.py`：字符串键值翻译字典
- `tr(text, **kwargs)`：翻译函数，支持格式化参数（如 `tr("Hello {}", name)`）
- `using_language()`：上下文管理器，临时切换语言
- `normalize_language()`：处理多种输入格式（`zh`、`en`、`zh_CN`、`en_US`）
- 所有 UI 字符串均通过 `tr()` 翻译
- 设置面板中一键切换语言

---

## 十五、性能与稳定性

### 15.1 内存管理

`MemoryGuard` 监控进程 USS 内存，三级清理策略：

| 级别 | 阈值 | 动作 |
|------|------|------|
| 轻度 | 100MB | 基础清理 |
| 中度 | 150MB | 深度清理 |
| 严重 | 200MB | 强制清理 |

每 120 秒检查一次，清理回调包括：图标缓存清理、搜索缓存清理、GC 回收。

### 15.2 轻睡眠模式

闲置超过配置时间（默认 10 秒）后自动进入低功耗状态：

- 降低进程优先级
- 停止内存和进程检查定时器
- 关闭文件夹监听
- 清理图标缓存
- 停止热键管理器
- 执行内存清理

鼠标中键立即唤醒。

### 15.3 文件夹同步与监听

- **Folder Sync**：物理 Windows 文件夹与快捷方式数据库的增量同步
- **Folder Watcher**：基于 `watchdog` 库监听文件夹变化，自动触发增量同步
- 睡眠模式下自动停止监听以节省资源

### 15.4 崩溃防护

- **Python faulthandler**：启用崩溃日志记录
- **Windows VEH**（向量异常处理器）：捕获硬崩溃（访问违规、栈溢出等），通过 Win32 API 直接写入 `crash.log`
- **旋转日志**：2MB × 3 备份的文件日志
- **单实例**：QLocalServer/QLocalSocket 确保仅运行一个实例

### 15.5 DPI 感知

启动时自动适配：

1. `SetProcessDpiAwarenessContext`（Windows 10 1703+）
2. `SetProcessDpiAwareness`（Windows 8.1+）
3. `SetProcessDPIAware`（Windows Vista+）

三级回退确保多显示器环境下的正确缩放。

---

## 十六、项目结构

```
QuickLauncher/
├── main.py                          # 入口
├── CLAUDE.md                        # 开发者指南
├── README.md                        # 项目说明（本文件）
├── pyproject.toml                   # 工具配置（black/ruff）
├── requirements.txt                 # 生产依赖（8 个）
├── requirements-dev.txt             # 开发依赖（6 个）
│
├── bootstrap/                       # 启动引导
│   ├── dpi.py                       #   DPI 感知设置
│   ├── deps.py                      #   依赖自动安装
│   ├── ipc.py                       #   单实例 IPC
│   ├── venv.py                      #   虚拟环境检测
│   └── logging_init.py              #   日志 + 崩溃处理
│
├── core/                            # 核心逻辑（~50 模块）
│   ├── data_models.py               #   数据模型（ShortcutItem, AppSettings 等）
│   ├── data_manager.py              #   数据管理（CRUD、备份、历史、原子保存）
│   ├── command_registry.py          #   命令注册系统
│   ├── commands.py                  #   命令实现
│   ├── builtin_commands.py          #   内置命令别名
│   ├── command_variables.py         #   命令变量模板引擎
│   ├── command_risk.py              #   命令风险评估
│   ├── command_execution_service.py #   命令执行服务
│   ├── shortcut_chain_exec.py       #   动作链执行
│   ├── plugin_manager.py            #   插件管理
│   ├── i18n.py                      #   国际化
│   ├── pinyin_search.py             #   拼音搜索
│   ├── favicon_cache.py             #   Favicon 缓存
│   ├── path_security.py             #   路径安全
│   ├── memory_guard.py              #   内存管理
│   ├── diagnostics.py               #   诊断中心
│   └── ...                          #   更多核心模块
│
├── ui/                              # 用户界面（~70 模块）
│   ├── tray_app.py                  #   托盘应用主控
│   ├── tray_mixins/                 #   TrayApp Mixin 拆分
│   │   ├── update_mixin.py          #     自动更新
│   │   ├── hooks_mixin.py           #     钩子管理
│   │   ├── sleep_mixin.py           #     轻睡眠
│   │   ├── popup_mixin.py           #     弹窗显示
│   │   └── ...
│   ├── launcher_popup/              #   弹窗系统
│   │   ├── popup_window.py          #     弹窗主类
│   │   ├── popup_search.py          #     搜索逻辑
│   │   ├── popup_command_result.py  #     命令结果展示
│   │   └── ...
│   ├── config_window/               #   配置窗口
│   │   ├── main_window.py           #     主窗口
│   │   ├── command_dialog.py        #     命令编辑器
│   │   ├── chain_dialog.py          #     动作链编辑器
│   │   └── ...
│   ├── command_panel_window.py      #   独立命令面板
│   ├── styles/style.py              #   设计系统与主题
│   └── ...
│
├── hooks/                           # Python 钩子封装
│   ├── hooks_wrapper.py             #   DLL 封装
│   ├── mouse_hook_dll.py            #   鼠标钩子
│   ├── keyboard_hook_dll.py         #   键盘钩子
│   └── hotkey_manager.py            #   热键管理
│
├── hooks_dll/                       # C++ Hook DLL 源码
│   ├── hooks.cpp                    #   钩子实现（SetWindowsHookEx）
│   ├── hooks.h                      #   头文件
│   └── build.bat                    #   MSVC 构建脚本
│
├── services/                        # 服务层
│   └── update/                      #   自动更新系统
│       ├── checker.py               #     版本检查
│       ├── downloader.py            #     下载器
│       ├── installer.py             #     安装器
│       └── ui.py                    #     更新通知 UI
│
├── plugins/                         # 插件目录
│   └── text_tools/                  #   文本工具插件（示例）
│
├── tests/                           # 测试（48 个测试文件）
│   ├── test_data_manager.py
│   ├── test_command_registry.py
│   ├── test_shortcut_chain_exec.py
│   └── ...
│
├── assets/                          # 应用图标、系统图标资源
│   └── system_icons/                #   随安装提供的系统图标
├── config/                          # 用户数据（gitignored）
│   ├── data.json                    #   配置数据
│   ├── icon_repo.json               #   用户图标仓库配置
│   └── icons/                       #   图标缓存
│
└── .github/                         # GitHub 配置
    ├── workflows/ci.yml             #   CI 流水线
    ├── ISSUE_TEMPLATE/              #   Issue 模板
    └── PULL_REQUEST_TEMPLATE.md     #   PR 模板
```

---

## 十七、技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.12 |
| **GUI 框架** | PyQt5 5.15.11 |
| **全局钩子** | C++ 17 DLL（Win32 SetWindowsHookEx） |
| **系统交互** | pywin32（COM、注册表、Shell）、psutil（进程/内存）、pynput（输入模拟） |
| **图片处理** | Pillow（PIL）、Qt QImage |
| **文件监听** | watchdog |
| **二维码** | qrcode |
| **打包** | Nuitka（编译）+ Inno Setup（安装器） |
| **代码质量** | ruff（lint）、black（格式化）、mypy（类型检查） |
| **测试** | pytest + pytest-cov |
| **CI** | GitHub Actions（Windows） |

### 生产依赖

| 包 | 版本 | 用途 |
|----|------|------|
| PyQt5 | ==5.15.11 | GUI 框架 |
| PyQt5-Qt5 | ==5.15.2 | Qt5 运行时 |
| pywin32 | >=305 | Windows API / COM |
| Pillow | >=9.0.0 | 图片处理 |
| psutil | >=5.9.0 | 进程/系统监控 |
| pynput | >=1.7.6 | 输入模拟 |
| watchdog | >=3.0.0 | 文件系统监听 |
| qrcode | >=7.4 | 二维码生成 |

---

## 快速开始

### 环境要求

- **操作系统**：Windows 10 / Windows 11
- **Python**：3.12（测试基准），尽量兼容 3.8+

### 安装依赖

```bash
py -3.12 -m pip install -r requirements.txt
```

### 运行

```bash
py -3.12 main.py
```

首次启动后：

1. 自动驻留系统托盘
2. 按**鼠标中键**呼出启动面板
3. 在弹窗中直接输入即可搜索
4. 输入 `/` 查看所有可用命令

### 构建 Hook DLL

```bat
cd hooks_dll
build.bat
```

需要 Visual Studio 2022+ 或 MinGW-w64。构建成功后更新 `hooks/hooks.dll`。

---

## 开发指南

### 运行测试

```bash
py -3.12 -m pytest tests/ -v
py -3.12 -m compileall -q core hooks ui tests main.py
```

### Lint 与格式化

```bash
py -3.12 -m ruff check core/ ui/ hooks/ services/
ruff format core/ ui/ hooks/ services/
```

### 代码规范

- 行宽 120（`pyproject.toml`）
- 大类拆分使用 Mixin 模式：文件名 `*_mixin.py`，类名 `*Mixin`，不定义 `__init__`
- 信号（`pyqtSignal`）定义在主类，mixin 通过 `self.<signal>.emit()` 发射
- 懒加载导入（在方法内 import）减少启动时间
- mixin 只导入 `qt_compat` 和 `core`，避免循环导入

---

## CI/CD

项目配置了 GitHub Actions CI 流水线（`.github/workflows/ci.yml`）：

- **触发条件**：所有 push 和 pull_request
- **运行环境**：`windows-latest` + Python 3.12
- **检查步骤**：
  1. 安装依赖
  2. 编译检查（`compileall`）
  3. Ruff lint（两轮：核心模块 + 全量）
  4. 格式检查
  5. pytest + 覆盖率（最低 30% 阈值）

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

- **Bug 报告**：使用 Bug Report 模板，包含复现步骤、期望/实际行为、环境信息、截图和日志
- **功能请求**：使用 Feature Request 模板
- **Pull Request**：使用 PR 模板，勾选变更类型（Bug 修复/功能/性能/重构/文档），确保通过 ruff、black、mypy 检查

---

> **QuickLauncher** — 让效率从指尖开始。
