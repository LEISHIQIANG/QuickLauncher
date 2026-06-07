# QuickLauncher 插件开发指南

QuickLauncher 插件适合封装"能解决一个明确问题"的本地能力，例如文件校验、进程排查、启动项审计、网络诊断、系统信息整理等。尽量避免把插件做成大量零散的文本转换按钮；如果确实是文本工具，也建议围绕一个具体工作流组织。

## 快速开始

1. 在设置页点击"新建开发插件..."，或输入 `/plugin new my_plugin`。
2. 新插件会生成：

```text
plugins/my_plugin/
  plugin.json
  main.py
  README.md
```

3. 在设置页启用插件，或执行 `/plugin reload my_plugin`。
4. 输入插件名、关键词、命令别名即可搜索命令，例如 `my plugin`、`hello`。

## 推荐插件形态

优先做这些：

- 排障类：进程、端口、启动项、PATH、服务、网络、证书、日志分析。
- 文件类：哈希、签名、重复文件、路径审计、快捷方式检查。
- 系统类：配置巡检、权限状态、环境信息、Windows 小工具聚合。
- 工作流类：把多个本地检查整理成一份可复制报告。

谨慎做这些：

- 单个简单字符串转换。
- 大量依赖剪贴板作为唯一输入来源的命令。
- 长时间后台联网、自动下载或自动修改系统状态的插件。
- 默认需要管理员权限或执行任意命令的插件。

## 官方插件包

QuickLauncher 本体不再预装这些插件源码。官方插件以 `.qlzip` 包放在项目根目录 `.plugins/` 下，安装后才会解包到运行时 `plugins/` 目录。

| 插件 | 重点能力 | 适合场景 |
|---|---|---|
| `api_tester` | HTTP 请求、请求历史 | 接口调试、快速验证 API |
| `disk_cleaner` | 目录大小分析、可清理项扫描 | 排查磁盘占用、清理前评估 |
| `event_inspector` | 最近错误、事件搜索 | 排查 Windows 事件日志 |
| `file_tools` | 复制路径、文件哈希 | 校验文件、排查路径、复制选中文件信息 |
| `network_tools` | Ping、DNS 查询 | 基础网络连通性诊断 |
| `process_tools` | 进程资源排行、查找进程 | 找高占用进程、确认某个程序是否在运行 |
| `screenshot_ocr` | 截图 OCR 内置命令 | 框选屏幕区域并识别文字 |
| `startup_tools` | 启动项审计、PATH 检查 | 排查开机慢、环境变量污染、命令找不到 |
| `text_tools` | 文本反转、统计、大小写 | 少量通用文本处理 |

## plugin.json

`plugin.json` 是插件清单，负责展示、搜索、权限声明和命令元信息。

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "说明插件解决什么实际问题",
  "entry": "main.py",
  "icon": "icon.png",
  "keywords": ["my plugin", "系统排障", "常用别名"],
  "permissions": ["file.read"],
  "commands": [
    {
      "id": "my_plugin.hello",
      "title": "Hello",
      "aliases": ["hello", "my-plugin"],
      "description": "示例命令",
      "category": "自定义插件"
    }
  ]
}
```

| 字段 | 必需 | 说明 |
|---|---|---|
| `id` | 是 | 插件唯一标识，建议小写字母、数字、短横线、下划线 |
| `name` | 是 | 显示名称，也会参与搜索 |
| `version` | 是 | 插件版本 |
| `author` | 否 | 作者或维护者 |
| `description` | 否 | 插件用途说明，也会参与搜索 |
| `entry` | 是 | 入口文件，相对于插件目录，通常是 `main.py` |
| `icon` | 否 | 插件默认图标，相对于插件目录；未配置或路径无效时使用系统默认图标 |
| `keywords` | 否 | 插件级搜索关键词，放英文名、中文名、缩写、常见叫法 |
| `permissions` | 否 | 权限声明列表 |
| `commands` | 否 | 命令展示信息；真实注册仍在 `main.py` 中完成 |

## 图标配置

插件图标是可选项，不是必填项。

不配置图标时：

```json
{
  "icon": ""
}
```

QuickLauncher 会自动使用系统默认命令图标，插件仍然可以正常扫描、启用、搜索和执行。

配置插件默认图标时：

```json
{
  "icon": "icon.png"
}
```

路径相对于插件目录，例如：

```text
plugins/my_plugin/icon.png
plugins/my_plugin/icons/tool.ico
```

如果某个命令需要独立图标，可以在 `main.py` 里注册命令时传入：

```python
api.register_command(
    id="my_plugin.check",
    title="检查",
    aliases=["check"],
    description="执行检查",
    category="排障",
    icon_path="icons/check.png",
    handler=handle_check,
)
```

图标优先级：

1. 命令自己的 `icon_path`
2. `plugin.json` 的插件默认 `icon`
3. 系统默认命令图标

## 搜索规则

QuickLauncher 会搜索插件清单和命令注册信息中的以下字段：

**插件级：** `id`、`name`、`description`、`keywords`

**命令级：** `id`、`title`、`aliases`、`description`、`category`、`search_terms`

建议：

- `aliases` 放用户会直接执行的短词，例如 `proc`、`path-check`。
- `keywords` 放插件级发现词，例如 `process tools`、`进程排查`。
- `search_terms` 放某个命令的补充发现词，例如 `task manager`、`资源占用`。

## main.py

插件入口必须提供 `register(api)`。

```python
from __future__ import annotations

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="my_plugin.hello",
        title="Hello",
        aliases=["hello", "my-plugin"],
        description="示例命令：验证插件已正确加载",
        category="自定义插件",
        search_terms=["plugin example", "插件示例"],
        handler=handle_hello,
    )


def handle_hello(context):
    message = "Hello from plugin!"
    return CommandResult(
        success=True,
        message=message,
        actions=[CommandAction(type="copy", label="复制结果", value=message)],
    )
```

## PluginAPI

| 方法 / 属性 | 说明 | 所需权限 |
|---|---|---|
| `register_command(...)` | 注册命令；支持 `icon_path`、`search_terms` | 无 |
| `register_builtin_command(...)` | 注册到“内置命令”下拉；仅适合主程序级入口 | `builtin.command` |
| `register_search_source(id, handler=None)` | 注册插件搜索源；主程序会自动加插件 ID 命名空间，避免跨插件冲突 | 无 |
| `register_module(module_id, manifest_path="module.json")` | 注册插件内的主程序模块 manifest，用于动作链这类可独立化模块 | 无 |
| `register_chain_processor(definition, handler)` | 注册动作链电池，使用与内置电池一致的 schema | 无 |
| `read_clipboard()` | 读取剪贴板文本 | `clipboard.read` |
| `write_clipboard(text)` | 写入剪贴板 | `clipboard.write` |
| `get_selected_files()` | 获取资源管理器选中文件 | `file.read` |
| `get_theme()` | 获取主程序当前主题，返回 `dark` 或 `light` | 无 |
| `get_app_version()` | 获取主程序版本号 | 无 |
| `open_url(url)` | 打开 `http` / `https` URL | `open.url` |
| `open_file(path)` | 打开已存在文件 | `open.file` |
| `open_folder(path)` | 打开已存在文件夹 | `open.file` |
| `read_text_file(path, encoding="utf-8", max_bytes=2097152)` | 读取有大小上限的文本文件 | `file.read` |
| `write_data_file(relative_path, text, encoding="utf-8", append=False)` | 只写入插件私有 `data/` 目录内的文本文件 | `file.write` |
| `http_request(url, method="GET", headers=None, body=None, timeout=10, max_bytes=2097152)` | 发起有超时、请求体、请求头和响应大小上限的 `GET` / `POST` / `HEAD` 请求 | `network.request` |
| `run_process_capture(args, cwd="", timeout=30, max_bytes=2097152, inherit_environment=False, helper_output_file=False)` | 通过主程序受控执行子进程并返回 `stdout` / `stderr` / `returncode`；截图/GUI helper 可用 `inherit_environment=True` 保留 Qt/wx 运行环境，用 `helper_output_file=True` 兼容打包版 GUI stdout | `process.run` |
| `is_user_admin()` | 判断主程序当前是否具备管理员权限 | 无 |
| `get_recycle_bin_info()` | 查询回收站条目数和估算大小 | `file.read` |
| `empty_recycle_bin()` | 通过主程序清空回收站 | `file.write` |
| `logger` | 插件命名空间日志 | 无 |
| `data_dir` | 插件私有数据目录 `data/` | 无 |
| `check_data_path(path)` | 确认路径在插件 `data/` 下 | 无 |
| `launch_target(target, parameters="", directory="", show_window=True, run_as_admin=False)` | 通过与图标执行相同的通道启动程序或文件 | `process.run`；`run_as_admin=True` 还需要 `admin.required` |
| `run_command(command, cwd="", show_window=False, run_as_admin=False)` | 通过与命令图标相同的通道执行命令 | `process.run`；`run_as_admin=True` 还需要 `admin.required` |

### 注册搜索源

`register_search_source(...)` 用于给主搜索补充插件结果。搜索源 ID 会自动按插件 ID 收敛，例如插件 `my_plugin` 调用 `api.register_search_source("host_scan", handler)`，最终注册 ID 是 `my_plugin_host_scan`。这样两个插件都叫 `host_scan` 也不会互相覆盖。

同一个插件内重复注册同一个搜索源会导致本次注册事务失败，并回滚已经写入的命令和搜索源。`handler(query)` 应快速返回 `list[dict]`；超时或异常会记录到插件失败计数，连续失败可能触发隔离。

### 受控 HTTP 请求

`http_request(...)` 只允许 `http` / `https`，方法限制为 `GET`、`POST`、`HEAD`。请求体只接受 `str`、`bytes` 或 `None`，最大 2 MB；响应默认最大读取 2 MB；请求头必须是 `dict`，最多 64 项，总字符数最多 8192，且会拒绝控制字符和 CRLF 注入。

### 注册为内置命令

普通插件命令使用 `register_command(...)`，会出现在插件命令和命令搜索里。

只有同时满足以下条件的命令，才会进入快捷方式配置里的“内置命令”下拉列表：

- `plugin.json` 声明 `builtin.command` 权限。
- `main.py` 调用 `api.register_builtin_command(...)`。

`register_builtin_command(...)` 的参数与 `register_command(...)` 基本一致，但命令会以 `plugin-builtin:<plugin_id>` 作为来源注册。下拉列表只读取这个来源，不会把所有插件命令混入内置命令。

内置命令 ID 仍建议使用小写字母、数字和短横线，例如 `screenshot-ocr`。如果插件目录必须使用下划线，例如 `screenshot_ocr`，`plugin.json` 的 `id` 仍要与目录名保持一致；命令 ID 可以独立使用短横线。

当插件需要在用户取消选择时不弹出结果面板，可以返回：

```python
CommandResult(
    success=True,
    payload={"_suppress_result_panel": True, "outputs": {"text": ""}},
)
```

## 模块型插件

普通插件注册命令；模块型插件注册一个主程序可调用的模块 API。动作链未来独立发布时就走这条路径。

模块型插件最小结构：

```text
plugins/action_chain/
  plugin.json
  main.py
  module.json
  action_chain_entry.py
```

`main.py` 只负责把模块 manifest 交给主程序：

```python
def register(api):
    api.register_module("quicklauncher.action_chain", "module.json")
```

`module.json` 使用模块契约字段：

```json
{
  "id": "quicklauncher.action_chain",
  "name": "Action Chain",
  "display_name": "动作链",
  "module_version": "0.2.0",
  "schema_version": 1,
  "api_version": "1.0",
  "min_host_version": "1.6.3.0",
  "max_host_version": "",
  "entry": "action_chain_entry:ActionChainModule",
  "license_mode": "plugin",
  "capabilities": ["chain.editor", "chain.runtime", "chain.processors"]
}
```

启用插件后，主程序通过 `core.module_registry` 加载 `module.json` 的 `entry`。禁用插件时，模块 manifest 会被反注册；主程序会回退到内置动作链模块，或在没有内置模块时返回清晰的“模块不可用”结果。

## 动作链电池插件

插件也可以只注册一个或多个动作链电池，不必注册命令。电池会出现在动作链节点库中，执行时走 `core.chain_processors.execute_chain_processor()`，禁用插件后自动从节点库和执行入口移除。

```python
def reverse_text(args):
    text = str(args.get("text", ""))
    return {"outputs": {"output": text[::-1], "length": str(len(text))}}

def register(api):
    api.register_chain_processor(
        {
            "id": "reverse_text",
            "title": "反转文本",
            "category": "插件电池",
            "description": "反转输入文本。",
            "inputs": [{"id": "text", "kind": "text", "required": True}],
            "outputs": [{"id": "output", "kind": "text"}, {"id": "length", "kind": "number"}],
            "params": [{"id": "text", "kind": "text", "required": True}],
            "safety": {"level": "safe", "capability": "chain.processor.reverse_text"},
            "examples": [{"title": "反转文本示例", "args": {"text": "abc"}}],
        },
        reverse_text,
    )
```

如果 `id` 没有点号，主程序会自动按插件 ID 命名空间化，例如插件 `chain_tools` 的 `reverse_text` 会注册为 `chain_tools_reverse_text`，避免和内置电池或其他插件冲突。handler 可以返回 `CommandResult`、字符串，或包含 `outputs`/`payload` 的 dict。

### 提权 / 降权启动

插件不要直接调用 `ShellExecuteW`、`runas`、`CreateProcessWithTokenW` 或自行维护 broker。需要启动程序或执行命令时，统一使用 `PluginAPI` 暴露的接口：

```python
ok, error = api.launch_target(
    r"C:\Tools\App.exe",
    ["--flag", "value"],
    r"C:\Tools",
    show_window=False,
    run_as_admin=True,
)

ok, error = api.run_command(
    "ipconfig /flushdns",
    show_window=False,
    run_as_admin=True,
)
```

这两个接口会复用 QuickLauncher 图标执行的权限边界：

- 提权只使用 Windows 标准 `ShellExecuteW(..., "runas", ...)`，由系统 UAC 处理。
- 降权只使用 Explorer 的普通用户 token；当前 QuickLauncher 以管理员权限运行而插件未要求管理员时，会从这条路径启动。
- 权限边界启动必须快速返回。降权通道内部总等待预算不超过 3 秒；提权请求由系统 UAC 接管，不在插件中阻塞等待子进程完成。

`register_command` 常用参数：

| 参数 | 说明 |
|---|---|
| `id` | 命令 ID |
| `title` | 展示标题 |
| `aliases` | 可输入别名 |
| `description` | 简短说明 |
| `category` | 分类 |
| `handler` | 处理函数 |
| `interaction_mode` | 默认面板模式 |
| `icon_path` | 命令图标，相对于插件目录或绝对路径 |
| `search_terms` | 额外搜索词 |

`params=[...]` 支持的字段：

| 字段 | 说明 |
|---|---|
| `name` | 参数名，用于 `context.args["name"]` 与 `{{param:name}}` |
| `type` | `text`、`textarea`、`password`、`choice`、`bool`、`number`、`file`、`folder` |
| `required` | 是否必填 |
| `default` | 默认值 |
| `choices` | `choice` 可选项 |
| `sensitive` | 敏感参数；不会写入历史，展示为 `******` |
| `label` | 面板表单标签 |
| `placeholder` | 输入提示 |
| `help` | 控件 tooltip |
| `multiline` | 使用多行输入 |
| `remember` | 是否允许写入历史重试；敏感参数会强制为 `False` |
| `source` | 默认值来源：`clipboard`、`selected_text`、`selected_file`、`selected_file_dir`、`last` |
| `validator` | 校验器：`path`、`file`、`folder`、`url`、`domain`、`ip`、`port`、`json`、`regex`、`number` |
| `pattern` | `regex` 校验使用的正则 |
| `min_value` / `max_value` | `number` 校验范围 |
| `advanced` | 高级参数标记，供 UI 分组使用 |

## CommandContext

handler 会收到 `CommandContext`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_input` | `str` | 原始输入 |
| `args_text` | `str` | 命令后的参数文本 |
| `args` | `dict[str, str]` | 命令面板结构化参数 |
| `clipboard_text` | `str` | 剪贴板文本快照 |
| `selected_text` | `str` | 选中文本快照 |
| `selected_files` | `list[str]` | 资源管理器选中文件 |
| `context_meta` | `dict` | 可记录的上下文摘要 |
| `update_callback` | callable | 可选，用于异步/阶段性结果 |

建议优先使用显式参数和选中文件；剪贴板可以作为补充输入，但不要让大量插件都只依赖剪贴板。

## CommandResult

handler 可以返回 `CommandResult`，也可以返回 dict。

```python
CommandResult(
    success=True,
    message="结果文本",
    payload={"outputs": {"name": "结果文本"}},
    actions=[
        CommandAction(type="copy", label="复制结果", value="结果文本"),
        CommandAction(type="open_folder", label="打开目录", value="C:/Temp"),
    ],
)
```

| 字段 | 说明 |
|---|---|
| `success` | 是否成功 |
| `message` | 结果文本 |
| `display_type` | 结果类型，默认 `text` |
| `payload` | 结构化扩展数据 |
| `actions` | 结果动作 |
| `error` | 错误摘要 |

### 结果类型

推荐的 `display_type`：

| display_type | 适用场景 | payload 约定 |
|---|---|---|
| `text` | 普通短文本 | 可选 `window_size` |
| `log` | stdout/stderr、HTTP 响应、长日志 | `{"wrap": false, "window_size": "large"}` |
| `table` | 进程、端口、列表型数据 | `{"columns": [...], "rows": [...]}`，复制用 TSV |
| `kv` | 系统信息、网络摘要 | `{"items": [[key, value], ...]}` |
| `list` | 检查报告、动作链步骤 | `{"items": [{"title": ..., "status": ..., "detail": ...}]}` |
| `progress` | 长任务阶段进度 | `{"current": ..., "total": ..., "detail": ...}` |
| `qr` | 二维码结果 | `{"image_path": ...}` |
| `json` | JSON 对象或格式化 JSON | `{"data": {...}, "formatted": "...", "compact": "..."}` |

`payload["window_size"]` 可以是 `small`、`medium`、`large` 或 `auto`。固定模板用于稳定布局，`auto` 才允许根据内容动态调整。

### 输出契约

插件建议把机器可读产物写入 `payload["outputs"]`：

```python
CommandResult(
    success=True,
    message="Host: example.com",
    display_type="kv",
    payload={
        "items": [["Host", "example.com"]],
        "outputs": {"host": "example.com", "port": "443"},
    },
)
```

`outputs` 会被命令面板历史和动作链使用，并归一化为 `dict[str, str]`。不要把 token、密码、私钥、cookie 等敏感值放入 `outputs`。

### 结果按钮

动作类型：

| type | 说明 |
|---|---|
| `copy` | 复制文本 |
| `open_url` | 打开 URL |
| `open_file` | 打开文件 |
| `open_folder` | 打开文件夹 |
| `save_text` | 保存文本 |
| `save_csv` | 保存 CSV |
| `save_json` | 保存 JSON |
| `copy_table` | 复制表格文本 |
| `copy_json` | 复制 JSON 文本 |
| `rerun` | 重新执行当前命令 |

独立命令面板会保留完整 `actions`。旧中键弹窗结果面板只作为兼容回退，空间有限时只显示前两个动作。

建议给高频动作设置 `primary=True`，危险动作设置 `danger=True`，不可用动作设置 `enabled=False`。不要返回自定义"关闭"按钮；关闭面板由 QuickLauncher 自动提供。

## 权限说明

> **重要**：当前插件以兼容模式（in-process）运行，与 QuickLauncher 主程序共享同一个 Python 进程。
>
> 这意味着：
> 1. 插件的 `permissions` 声明本质上是**高风险提醒**，并非强权限隔离。
> 2. 插件仍可通过原生 Python API（如 `open()`、`subprocess`、`urllib`）绕过 `PluginAPI` 直接访问系统。
> 3. 仅安装您信任的插件。社区插件在启用时需自行判断安全风险。
> 4. 未来版本将引入独立进程插件和强权限 broker，届时权限声明将成为真实的安全边界。

| 权限 | 说明 | 风险 |
|---|---|---|
| `clipboard.read` | 读取剪贴板 | 低 |
| `clipboard.write` | 写入剪贴板 | 低 |
| `file.read` | 读取文件或选中文件 | 中 |
| `file.write` | 写入文件 | 高 |
| `open.url` | 打开网页 | 低 |
| `open.file` | 打开文件 | 中 |
| `process.run` | 执行系统命令 | 高 |
| `network.request` | 网络请求 | 中 |
| `builtin.command` | 注册到“内置命令”下拉 | 中 |
| `admin.required` | 管理员权限 | 高 |

声明高风险权限时，请在插件 README 写清楚为什么需要、会读取或修改什么。

## .qlzip 打包安装

`.qlzip` 本质是 ZIP 包，支持两种结构：

```text
plugin.json
main.py
...
```

或：

```text
my_plugin/
  plugin.json
  main.py
  ...
```

推荐使用第二种结构，目录名与 `plugin.json` 的 `id` 保持一致。安装时会校验清单、路径穿越、加密条目、文件数量和解压后总大小。

当前安装限制：

| 限制项 | 默认值 |
|---|---|
| 解压后总大小 | 150 MB |
| 文件数量 | 1000 个 |

插件应做成独立 `.qlzip`，不要直接放入本体源码 `plugins/` 目录参与主程序打包。这样可以先打包安装本体，再通过设置页安装 `.plugins/` 下的插件包做验证。

需要 GUI 库、OCR 库等大依赖时，优先把依赖放在插件包内，例如：

```text
my_plugin/
  runtime/
    site-packages/
      wx/
```

主程序提供 `--plugin-helper <script.py> --plugin-site <site-packages> -- ...` 子进程入口，插件可以让编译后的 QuickLauncher 加载这些库并运行 helper 脚本。这样用户电脑不需要额外安装 Python；主程序本体也不需要把只服务单个插件的库打进核心依赖。

## 超时控制

插件 handler 在独立线程中运行，不会阻塞 UI。QuickLauncher 会等待插件命令最多 30 秒；超过后返回软超时错误，后台线程仍可能继续运行到自身完成或抛出异常。

- 插件应自行管理长时间操作：对大文件、网络请求、批量 I/O 等任务，建议内部设置比 30 秒更明确的截止时间，避免无限阻塞。
- 如果 handler 超过 30 秒，用户会看到软超时提示；插件内部任务可能仍在后台运行。
- 建议策略：
  - 对可能耗时的操作，分批次执行或使用内部 `timeout` 保护。
  - 捕获超时后返回带错误提示的 `CommandResult`，而不是让线程悬空。
  - 长任务优先通过 `context.update_callback(CommandResult(display_type="progress", ...))` 汇报阶段性状态，最终返回完整结果。

## 最佳实践

- 不要在模块 import 时执行扫描、联网、读大文件等操作。
- 外部命令使用参数数组，不要拼接 shell 字符串。
- 文件路径用 `pathlib.Path`，展示给用户时给出完整路径。
- 异常要转成 `CommandResult(success=False, message=...)`。
- 插件自己的持久化数据放 `api.data_dir`。

## CHANGELOG 记录要求

每次修改插件代码文件后，必须在项目根目录的 `CHANGELOG.md` 中记录变更。格式要求：

- 以日期为章节标题，一天一个章节（**注意**：只有当天有变更时才需要新建章节）
- 每个变更条目注明修改的文件和主要内容
- 同一日期的多条变更归入同一章节

```text
## 2026-05-31

- core/plugin_manager.py：完善插件隔离/隔离区
- PLUGIN_DEV.md：补充 CHANGELOG 记录要求文档
```

## README 编写要求

每个插件都应该带 `README.md`，README 是必需的维护材料。建议包含：

- 插件定位：解决什么实际问题。
- 命令列表：命令 ID、别名、参数、输出。
- 使用示例：用户应该输入什么。
- 权限说明：为什么需要这些权限。
- 风险说明：是否读取文件、运行进程、联网、修改系统。
- 故障排查：常见失败原因。
- 维护信息：版本、作者、兼容性。

插件越接近系统能力、文件操作、进程操作，越应该把权限和风险写清楚。

## 控制台命令

| 命令 | 说明 |
|---|---|
| `/plugin list` | 列出所有插件 |
| `/plugin reload <id>` | 重载插件 |
| `/plugin new <id>` | 创建插件模板 |

## 插件安装包

可以参考项目根目录 `.plugins/` 下的官方 `.qlzip` 包。需要修改插件时，先解包对应 `.qlzip`，修改后重新压回标准包结构。
