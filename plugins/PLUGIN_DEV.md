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

## 当前插件

| 插件 | 重点能力 | 适合场景 |
|---|---|---|
| `file_tools` | 复制路径、文件哈希 | 校验文件、排查路径、复制选中文件信息 |
| `process_tools` | 进程资源排行、查找进程 | 找高占用进程、确认某个程序是否在运行 |
| `startup_tools` | 启动项审计、PATH 检查 | 排查开机慢、环境变量污染、命令找不到 |
| `network_tools` | Ping、DNS 查询 | 基础网络连通性诊断 |
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
| `read_clipboard()` | 读取剪贴板文本 | `clipboard.read` |
| `write_clipboard(text)` | 写入剪贴板 | `clipboard.write` |
| `get_selected_files()` | 获取资源管理器选中文件 | `file.read` |
| `logger` | 插件命名空间日志 | 无 |
| `data_dir` | 插件私有数据目录 `data/` | 无 |
| `check_data_path(path)` | 确认路径在插件 `data/` 下 | 无 |
| `launch_target(target, parameters="", directory="", show_window=True, run_as_admin=False)` | 通过与图标执行相同的通道启动程序或文件 | `process.run`；`run_as_admin=True` 还需要 `admin.required` |
| `run_command(command, cwd="", show_window=False, run_as_admin=False)` | 通过与命令图标相同的通道执行命令 | `process.run`；`run_as_admin=True` 还需要 `admin.required` |

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

## CommandContext

handler 会收到 `CommandContext`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_input` | `str` | 原始输入 |
| `args_text` | `str` | 命令后的参数文本 |
| `clipboard_text` | `str` | 剪贴板文本快照 |
| `selected_files` | `list[str]` | 资源管理器选中文件 |
| `update_callback` | callable | 可选，用于异步/阶段性结果 |

建议优先使用显式参数和选中文件；剪贴板可以作为补充输入，但不要让大量插件都只依赖剪贴板。

## CommandResult

handler 可以返回 `CommandResult`，也可以返回 dict。

```python
CommandResult(
    success=True,
    message="结果文本",
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

`payload["window_size"]` 可以是 `small`、`medium`、`large` 或 `auto`。固定模板用于稳定布局，`auto` 才允许根据内容动态调整。

### 结果按钮

动作类型：

| type | 说明 |
|---|---|
| `copy` | 复制文本 |
| `open_url` | 打开 URL |
| `open_file` | 打开文件 |
| `open_folder` | 打开文件夹 |

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
| `admin.required` | 管理员权限 | 高 |

声明高风险权限时，请在插件 README 写清楚为什么需要、会读取或修改什么。

## 超时控制

从 v1.5.6.8 起，QuickLauncher **不再对插件命令设置全局超时限制**。插件 handler 在独立线程中运行，不会阻塞 UI，但运行时长为插件自身控制。

- 插件应自行管理长时间操作：对大文件、网络请求、批量 I/O 等任务，建议内部设置合理的截止时间，避免无限阻塞。
- 如果 handler 长时间不返回，用户仍可关闭弹窗，但插件线程会继续在后台运行直至完成或抛出异常。
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

## 内置示例

可以参考：

- `plugins/file_tools/`
- `plugins/process_tools/`
- `plugins/startup_tools/`
- `plugins/network_tools/`
- `plugins/api_tester/`
- `plugins/disk_cleaner/`
- `plugins/event_inspector/`
- `plugins/text_tools/`
