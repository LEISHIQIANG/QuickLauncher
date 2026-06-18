# QuickLauncher 官方插件包

`.plugins/` 用来保存可安装的官方 `.qlzip` 插件包。它不是运行时插件目录。

## 目录关系

| 路径 | 用途 |
|---|---|
| `.plugins/` | 源码仓库中的插件包目录，供发布前验证和手动安装测试 |
| `plugins/` | QuickLauncher 运行时插件安装目录，安装 `.qlzip` 后才会解包到这里 |
| `plugins/PLUGIN_DEV.md` | 插件开发和打包说明，仅在源码仓库保留，runtime 不打包 |

发布包只创建空的 `plugins/` 安装目录，不直接打包源码插件目录。这样可以先验证主程序，再通过设置页安装 `.plugins/` 下的插件包。

## 当前官方插件包

| 包名 | 插件 ID | 版本 | 说明 |
|---|---|---|---|
| `api_tester.qlzip` | `api_tester` | 1.0.0 | HTTP API 调试器 |
| `disk_cleaner.qlzip` | `disk_cleaner` | 1.0.0 | 目录大小分析和安全清理 |
| `event_inspector.qlzip` | `event_inspector` | 1.0.0 | Windows 事件日志分析 |
| `file_tools.qlzip` | `file_tools` | 1.0.0 | 复制选中文件路径、文件 Hash |
| `network_tools.qlzip` | `network_tools` | 1.0.0 | Ping、DNS 查询 |
| `process_tools.qlzip` | `process_tools` | 1.0.0 | 进程资源排行和进程查找 |
| `qr_code_scanner.qlzip` | `qr_code_scanner` | 1.1.0 | 截图二维码识别 |
| `screenshot_ocr.qlzip` | `screenshot_ocr` | 1.1.0 | 截图 OCR |
| `startup_tools.qlzip` | `startup_tools` | 1.0.0 | 启动项审计和 PATH 体检 |
| `text_tools.qlzip` | `text_tools` | 1.0.0 | 文本反转、统计、大小写转换 |

## 安装验证

1. 启动 QuickLauncher。
2. 打开设置页的插件管理。
3. 选择本目录中的 `.qlzip`。
4. 安装后确认插件出现在运行时 `plugins/<plugin_id>/`。
5. 启用插件并执行对应命令或搜索别名。

## 打包约束

- 插件包必须包含 `plugin.json`。
- 插件 ID 只能包含小写字母、数字、短横线和下划线。
- 解压前文件数上限为 1000。
- 解压前总大小上限为 150 MB。
- 不允许加密 ZIP 条目、路径穿越或重复路径。
- `screenshot_ocr.qlzip` 和 `qr_code_scanner.qlzip` 会通过 `--plugin-helper` / 常驻 worker 使用插件内自带运行库；包内不包含 `python.exe`。
