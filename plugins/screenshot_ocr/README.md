# 截图OCR

QuickLauncher 内置命令插件。插件只注册一个内置命令：`截图OCR`。

## 命令

- ID：`screenshot-ocr`
- 名称：`截图OCR`
- 别名：`screenshot_ocr`、`截图ocr`

执行后会立即进入原项目的 wx 截图框选流程，确认选区后调用 OCR，识别文字显示在 QuickLauncher 命令结果面板中。

点击取消时不弹出结果面板。

## 图标用法

新建“运行命令”快捷方式，类型选择“内置命令”，命令选择“截图OCR”，图标可自行搭配。

## 安装包

本插件按独立 `.qlzip` 发布，不跟随 QuickLauncher 本体源码 `plugins/` 目录打包。

安装包结构：

```text
screenshot_ocr/
  plugin.json
  main.py
  ...
```

`plugin.json` 的 `id` 必须保持为 `screenshot_ocr`，因为它需要与安装后的插件目录名一致；注册到“内置命令”的命令 ID 是 `screenshot-ocr`。

## 运行依赖

插件包已包含 OCR 相关资源、OCR Python 模块和 `wxPython` 运行库。QuickLauncher 会在启动空闲期通过常驻 worker 提前加载 wx、OCR DLL 和识别模型。执行命令时复用已经就绪的进程，不再为每次截图重新启动完整主程序。

如果常驻 worker 启动失败，插件会自动回退到原有的单次 `--plugin-helper` 路径，避免因为预热失败导致功能不可用。

## 权限

- `builtin.command`：允许插件把这个命令注册到 QuickLauncher 的内置命令表面。
- `file.read`：读取截图临时文件。
- `clipboard.write`：结果动作允许复制文字。
- `process.run`：OCR 截图流程在宿主管理的独立常驻进程中运行。
