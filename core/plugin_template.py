"""Shared templates for creating local QuickLauncher plugins."""

from __future__ import annotations

import json
from pathlib import Path


def command_namespace(plugin_id: str) -> str:
    return (plugin_id or "").replace("-", "_").replace(" ", "_")


def display_name(plugin_id: str, plugin_name: str = "") -> str:
    return plugin_name.strip() or plugin_id.replace("_", " ").replace("-", " ").title()


def build_plugin_manifest(
    plugin_id: str,
    plugin_name: str = "",
    author: str = "",
    description: str = "",
) -> dict:
    name = display_name(plugin_id, plugin_name)
    namespace = command_namespace(plugin_id)
    return {
        "id": plugin_id,
        "name": name,
        "version": "1.0.0",
        "author": author,
        "description": description or "请在这里说明插件解决什么问题、适合什么场景",
        "entry": "main.py",
        "icon": "",
        "keywords": [
            plugin_id,
            plugin_id.replace("_", " "),
            plugin_id.replace("-", " "),
            name,
        ],
        "permissions": [],
        "commands": [
            {
                "id": f"{namespace}.hello",
                "title": "Hello",
                "aliases": ["hello", plugin_id, name],
                "description": "示例命令：验证插件已正确加载",
                "category": "自定义插件",
            }
        ],
    }


def build_plugin_main_py(plugin_id: str, plugin_name: str = "") -> str:
    name = display_name(plugin_id, plugin_name)
    namespace = command_namespace(plugin_id)
    search_name = plugin_id.replace("_", " ").replace("-", " ")
    return f'''"""QuickLauncher plugin entry for {name}."""

from __future__ import annotations

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="{namespace}.hello",
        title="Hello",
        aliases=["hello", "{plugin_id}", "{name}"],
        description="示例命令：验证插件已正确加载",
        category="自定义插件",
        search_terms=["{search_name}", "{name}"],
        handler=handle_hello,
    )


def handle_hello(context):
    message = "Hello from {name}!"
    return CommandResult(
        success=True,
        message=message,
        actions=[CommandAction(type="copy", label="复制结果", value=message)],
    )
'''


def build_plugin_readme(
    plugin_id: str,
    plugin_name: str = "",
    author: str = "",
    description: str = "",
) -> str:
    name = display_name(plugin_id, plugin_name)
    namespace = command_namespace(plugin_id)
    author_line = author or "未填写"
    desc = description or "请在这里说明插件解决什么实际问题、适合什么使用场景。"
    return f"""# {name}

## 插件定位

{desc}

这个 README 是插件模板的一部分。建议把它当作插件的使用说明和维护手册，而不只是给用户看的简介。

## 当前命令

| 命令 ID | 常用输入 | 作用 |
|---|---|---|
| `{namespace}.hello` | `hello`、`{plugin_id}`、`{name}` | 示例命令，用来验证插件已经被 QuickLauncher 扫描、启用并注册成功 |

## 使用方式

1. 打开 QuickLauncher。
2. 输入插件关键词，例如 `{plugin_id}` 或 `{name}`。
3. 也可以输入 `/hello` 或 `/{namespace}.hello` 直接执行示例命令。
4. 修改 `main.py` 后，在设置页点击“重载”，或执行 `/plugin reload {plugin_id}`。

## 文件结构

```text
plugins/{plugin_id}/
  plugin.json   # 插件清单：名称、关键词、权限、命令展示信息
  main.py       # 插件入口：register(api) 在这里注册真实命令
  README.md     # 插件说明：用途、命令、权限、维护记录
  icon.png      # 可选：插件默认图标，未配置时使用系统默认图标
  data/         # 可选：插件自己的数据目录，通过 api.data_dir 获取
```

## 图标配置

插件图标不是必选项。`plugin.json` 里的 `icon` 可以留空：

```json
{{
  "icon": ""
}}
```

留空或路径无效时，QuickLauncher 会使用系统默认的命令图标，不影响插件加载和命令执行。

如果想自定义图标，把图标文件放在插件目录下，然后填写相对路径：

```json
{{
  "icon": "icon.png"
}}
```

支持常见图片或图标格式，例如 `.png`、`.ico`。单个命令也可以在 `api.register_command(..., icon_path="icons/check.png")` 中配置自己的图标；命令图标优先于插件默认图标。

## 搜索与发现

QuickLauncher 会搜索这些字段：

- `plugin.json` 中的 `id`、`name`、`description`、`keywords`
- `commands[].id`、`commands[].title`、`commands[].aliases`、`commands[].description`、`commands[].category`
- `main.py` 调用 `api.register_command(..., search_terms=[...])` 传入的额外关键词

建议：

- `keywords` 放插件级别的自然语言关键词，例如英文名、中文名、常见缩写。
- `aliases` 放用户最可能直接输入的命令词，控制在 1-5 个。
- `search_terms` 放不适合当命令别名、但适合被搜索发现的词。

## 权限说明

当前模板没有声明权限。

如果后续使用受控 API，请在 `plugin.json` 的 `permissions` 中声明：

| 权限 | 典型用途 | 风险 |
|---|---|---|
| `clipboard.read` | 读取剪贴板文本 | 低 |
| `clipboard.write` | 写入剪贴板 | 低 |
| `file.read` | 读取用户选中文件或文件内容 | 中 |
| `file.write` | 写入文件 | 高 |
| `open.url` | 打开网页 | 低 |
| `open.file` | 打开文件或目录 | 中 |
| `process.run` | 执行系统命令 | 高 |
| `network.request` | 发起网络请求 | 中 |
| `admin.required` | 需要管理员权限 | 高 |

需要启动程序或执行命令时，优先使用 `api.launch_target(...)` 或 `api.run_command(...)`。它们会复用 QuickLauncher 图标执行的权限通道：提权使用 Windows 标准 `runas`，降权使用 Explorer 普通用户 token。不要在插件里自行调用 `ShellExecuteW`、`CreateProcessWithTokenW` 或维护高权限 broker。

## 开发约定

- 插件入口必须提供 `register(api)`。
- 命令 ID 必须包含点号，例如 `{namespace}.hello`。
- 如果插件 id 使用短横线，例如 `my-plugin`，建议命令命名空间使用下划线：`my_plugin.hello`。
- handler 返回 `CommandResult`，或返回可转换为 `CommandResult` 的 dict。
- 单个 handler 应尽量在 3 秒内返回，避免阻塞弹窗交互。
- 长文本结果要控制长度，并提供 `copy` 动作。
- `CommandResult.actions` 最多放 2 个底部按钮，系统自带“关闭”按钮不计入；超过 2 个会被截断。
- 不要在导入模块时执行耗时逻辑，把工作放到 handler 内。

## 发布前检查

- [ ] `plugin.json` 能被 JSON 解析。
- [ ] `id`、命令 ID、aliases 没有和其他插件冲突。
- [ ] 设置页能扫描到插件。
- [ ] 插件启用后，输入插件名能搜到命令。
- [ ] 命令缺少参数时返回清晰用法，而不是抛异常。
- [ ] 需要读写文件、运行进程或联网时，README 解释了原因和风险。

## 维护信息

- 插件 ID：`{plugin_id}`
- 命令命名空间：`{namespace}`
- 作者：{author_line}
- 初始版本：`1.0.0`
"""


def write_plugin_template(
    plugin_dir: str | Path,
    plugin_id: str,
    plugin_name: str = "",
    author: str = "",
    description: str = "",
) -> None:
    target = Path(plugin_dir)
    target.mkdir(parents=True, exist_ok=True)

    manifest = build_plugin_manifest(plugin_id, plugin_name, author, description)
    (target / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (target / "main.py").write_text(
        build_plugin_main_py(plugin_id, plugin_name),
        encoding="utf-8",
    )
    (target / "README.md").write_text(
        build_plugin_readme(plugin_id, plugin_name, author, description),
        encoding="utf-8",
    )
