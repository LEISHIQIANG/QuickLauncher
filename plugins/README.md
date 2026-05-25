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

命令返回的 `actions` 会显示在结果面板底部。底部空间只保留 2 个插件自定义按钮，系统自带的“关闭”按钮不计入；超过 2 个的动作会被截断，只保留前两个。

建议优先放“复制结果”“打开目录”这类高频动作，不要把“关闭”做成插件动作。

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
