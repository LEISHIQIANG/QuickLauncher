# QuickLauncher Plugin Packages

此目录存放可安装的 `.qlzip` 插件包。

- `plugins/` 是 QuickLauncher 运行时插件安装目录。
- `.plugins/` 是发布或测试用的插件包目录。
- 安装测试时，在插件设置页选择这里的 `.qlzip` 文件安装。

官方插件包：

- `api_tester.qlzip`
- `disk_cleaner.qlzip`
- `event_inspector.qlzip`
- `file_tools.qlzip`
- `network_tools.qlzip`
- `process_tools.qlzip`
- `qr_code_scanner.qlzip`
- `screenshot_ocr.qlzip`
- `startup_tools.qlzip`
- `text_tools.qlzip`

说明：

- `screenshot_ocr.qlzip` 自带 OCR 资源和 `wxPython` 运行库。
- 插件包不自带 `python.exe`；编译后的 QuickLauncher 会通过 `--plugin-helper` 子进程加载插件内的 `runtime/site-packages`。
