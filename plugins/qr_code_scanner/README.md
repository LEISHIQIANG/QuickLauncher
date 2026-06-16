# 截图二维码识别

`qr_code_scanner` 是 QuickLauncher 官方 `.qlzip` 插件。它注册一个插件内置命令，用于框选屏幕区域并识别单个二维码。

## 命令

| 字段 | 内容 |
|---|---|
| 命令 ID | `screenshot-qr` |
| 显示名称 | `截图二维码识别` |
| 别名 | `screenshot_qr`、`qr`、`二维码识别`、`截图二维码` |
| 搜索词 | `qr code`、`qrcode`、`截图识别二维码`、`扫码` |
| 结果窗口 | `medium` |

## 使用

1. 在 QuickLauncher 中输入 `qr`、`二维码识别` 或 `截图二维码`。
2. 框选屏幕上的二维码区域。
3. 插件会把识别结果显示在命令结果面板。
4. 如果内容像 URL，会提供“打开链接”动作；始终提供复制动作。

右键、Esc 或截图窗口取消会退出流程，不弹出错误结果。

## 运行方式

- 插件包只内置二维码解码需要的 `zxingcpp` Windows x64 Python 3.12/3.13 二进制模块。
- 截图窗口复用 QuickLauncher 本体已有的 PyQt5。
- 图像读取复用本体已有的 Pillow。
- 插件启动后会延迟 2.5 秒预热 `qr_worker.py` 常驻 worker。
- 执行命令时优先复用常驻 worker；预热失败时回退到 `QuickLauncher.exe --plugin-helper` 单次 helper。
- 包内不包含 `python.exe`，打包版由 QuickLauncher 宿主加载插件内 `runtime/site-packages`。

## 权限

| 权限 | 原因 |
|---|---|
| `builtin.command` | 注册为内置命令，出现在命令面板和内置命令下拉中 |
| `clipboard.write` | 提供复制识别结果动作 |
| `open.url` | 识别内容为 URL 时提供打开链接动作 |
| `process.run` | 通过宿主受控 helper / worker 执行截图识别流程 |

## 打包

插件以 `qr_code_scanner.qlzip` 发布。标准结构：

```text
qr_code_scanner/
├── plugin.json
├── main.py
├── capture_qt.py
├── qr_runner.py
├── qr_worker.py
└── runtime/site-packages/
```

`plugin.json` 的 `id` 必须保持为 `qr_code_scanner`，安装目录名必须与它一致。

## 故障排查

- 解码组件不可用：确认目标包内有匹配 Python 版本的 `zxingcpp` 二进制模块。
- 截图窗口未出现：确认主程序本体包含 PyQt5，且 helper 子进程未被安全软件拦截。
- 识别为空：尽量只框选二维码本体，避免过大区域、模糊缩放或多二维码混入。
