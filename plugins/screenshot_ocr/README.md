# 截图 OCR

`screenshot_ocr` 是 QuickLauncher 官方 `.qlzip` 插件。它注册一个插件内置命令，用于框选屏幕区域并识别文字，结果直接显示在 QuickLauncher 命令结果面板中。

## 命令

| 字段 | 内容 |
|---|---|
| 命令 ID | `screenshot-ocr` |
| 显示名称 | `截图OCR` |
| 别名 | `screenshot_ocr`、`截图ocr` |
| 搜索词 | `screen ocr`、`截图识别`、`文字识别` |
| 结果窗口 | `medium` |

高级参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `show_window` | `false` | 是否显示 helper 执行窗口 |
| `capture_output` | `true` | 是否捕获 helper 输出 |

## 使用

1. 在 QuickLauncher 中输入 `截图ocr` 或 `screenshot_ocr`。
2. 框选要识别的屏幕区域。
3. 插件调用 OCR 服务识别文字。
4. 识别结果显示在命令结果面板，并提供复制动作。

取消截图会静默退出，不弹出错误结果。

## 运行方式

- 插件包内置 OCR 资源、OCR Python 模块、WeChat OCR 运行文件和 `wxPython` 运行库。
- 插件启动后会延迟 2 秒预热 `ocr_worker.py` 常驻 worker。
- 执行命令时优先复用常驻 worker，避免每次截图重新启动完整 OCR 运行时。
- 预热失败时自动回退到单次 `QuickLauncher.exe --plugin-helper` 路径。
- 包内不包含 `python.exe`，打包版由 QuickLauncher 宿主加载插件内 `runtime/site-packages`。

## 权限

| 权限 | 原因 |
|---|---|
| `builtin.command` | 注册为内置命令，出现在命令面板和内置命令下拉中 |
| `file.read` | 读取 OCR 运行资源和模型文件 |
| `clipboard.write` | 提供复制识别结果动作 |
| `process.run` | 通过宿主受控 helper / worker 执行 OCR 流程 |

## 打包

插件以 `screenshot_ocr.qlzip` 发布。标准结构：

```text
screenshot_ocr/
├── plugin.json
├── main.py
├── ocr_runner.py
├── ocr_service.py
├── ocr_worker.py
├── screenshot.py
├── ocrTx/
├── runtime/site-packages/
├── vendor/
└── wx/
```

`plugin.json` 的 `id` 必须保持为 `screenshot_ocr`，安装目录名必须与它一致。命令 ID 使用短横线形式 `screenshot-ocr`。

## 故障排查

- OCR 初始化慢：首次执行会加载模型和原生 DLL，后续应由常驻 worker 复用。
- 常驻 worker 失败：插件会回退到单次 helper；检查日志中是否有 wx/OCR DLL 加载错误。
- 识别为空：尽量框选清晰文本区域，避免过小字体、过低对比度或多窗口遮挡。
