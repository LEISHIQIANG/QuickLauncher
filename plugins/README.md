# QuickLauncher Plugins

这个目录存放 QuickLauncher 本地插件。插件会被 `core.plugin_manager.PluginManager` 扫描，启用后把命令注册到统一命令中心，因此可以通过普通搜索或 `/` 命令面板发现。

## 当前插件

| 插件 | 重点能力 | 适合场景 |
|---|---|---|
| `file_tools` | 复制路径、文件哈希 | 校验文件、排查路径、复制选中文件信息 |
| `process_tools` | 进程资源排行、查找进程 | 找高占用进程、确认某个程序是否在运行 |
| `startup_tools` | 启动项审计、PATH 检查 | 排查开机慢、环境变量污染、命令找不到 |
| `network_tools` | Ping、DNS 查询 | 基础网络连通性诊断 |
| `text_tools` | 文本反转、统计、大小写 | 少量通用文本处理 |

## 新建插件

推荐从模板创建：

```text
/plugin new my_plugin
```

或在设置页点击“新建开发插件...”。模板会生成：

```text
plugins/my_plugin/
  plugin.json
  main.py
  README.md
```

README 是必需的维护材料。插件越接近系统能力、文件操作、进程操作，越应该把权限和风险写清楚。

## 图标配置

插件可以配置自己的图标，但不是必选项。

- 不配置 `plugin.json` 的 `icon` 时，QuickLauncher 使用系统默认命令图标。
- 配置 `icon` 时，路径相对于插件目录，例如 `icon.png` 或 `icons/tool.ico`。
- 单个命令也可以通过 `api.register_command(..., icon_path="icons/check.png")` 使用独立图标。
- 命令图标优先于插件默认图标；两者都没有时才使用系统默认图标。

## 设计方向

推荐优先做“实际问题解决型”插件：

- Windows 排障：进程、启动项、PATH、服务、端口、日志。
- 文件诊断：哈希、签名、快捷方式、重复文件、路径健康检查。
- 网络检查：DNS、网卡、代理、证书、路由。
- 报告型命令：把多项检查整理成可复制报告。

不建议让插件系统堆满只依赖剪贴板的小转换器。剪贴板工具可以有，但最好只是某个完整工作流的一部分。

## 结果按钮

命令返回的 `actions` 会显示在独立命令面板的动作区。独立面板会保留完整动作列表；旧中键弹窗结果面板只作为兼容回退，空间有限时只显示前两个动作。

建议优先放“复制结果”“打开目录”这类高频动作，并用 `primary=True`、`danger=True`、`enabled=False` 标记动作状态。不要把“关闭”做成插件动作。

## 结果类型

插件应优先返回结构化 `CommandResult`：

- `display_type="log"`：命令输出、HTTP 响应、长日志，建议 `payload={"window_size": "large", "wrap": False}`。
- `display_type="table"`：进程、端口、文件列表，使用 `payload={"columns": [...], "rows": [...]}`。
- `display_type="list"`：检查报告或多步骤摘要，使用 `payload={"items": [{"title": ..., "status": ..., "detail": ...}]}`。
- `display_type="kv"`：少量键值信息，使用 `payload={"items": [[key, value], ...]}`。

纯文本 `message` 仍然兼容，但报告型命令应把可视数据放进 payload，并提供 `copy` action 保存完整文本。

## 搜索规则

QuickLauncher 会搜索插件清单和命令注册信息：

- 插件 `id/name/description/keywords`
- 命令 `id/title/aliases/description/category`
- `register_command(..., search_terms=[...])`

因此新插件至少要认真填写：

- `plugin.json` 的 `description`
- `plugin.json` 的 `keywords`
- 每个命令的 `aliases`
- 每个命令的 `description`

## 权限原则

只声明实际需要的权限。高风险权限包括：

- `file.write`
- `process.run`
- `admin.required`

带高风险权限的插件应在自己的 README 中写明：

- 为什么需要这个权限
- 会读取或修改哪些对象
- 是否会执行外部程序
- 失败时如何回滚或检查

## 开发文档

完整开发指南见项目根目录：

```text
PLUGIN_DEV.md
```
