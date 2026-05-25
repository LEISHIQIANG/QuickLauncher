# File Tools

## 插件定位

File Tools 面向文件排查与校验：快速复制资源管理器选中文件路径，或计算文件哈希。它适合确认下载文件完整性、整理路径信息、给别人发送文件位置或校验值。

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `file_tools.copy_path` | `copy-path`、`path`、`复制路径` | `full/name/dir` 可选 | 复制选中文件的完整路径、文件名或目录 |
| `file_tools.hash` | `hash`、`sha256`、`md5` | `[md5|sha1|sha256] <文件路径>` | 计算文件哈希，默认 SHA256 |

## 示例

```text
copy-path
copy-path name
hash sha256 "C:\Downloads\setup.exe"
hash md5
```

`hash` 不传路径时会尝试使用资源管理器选中文件。

## 权限

| 权限 | 原因 |
|---|---|
| `file.read` | 读取选中文件并计算哈希 |
| `clipboard.write` | 提供复制路径/哈希结果按钮 |

## 图标

当前插件未配置自定义图标，会使用 QuickLauncher 的系统默认命令图标。可以在 `plugin.json` 中添加 `"icon": "icon.png"` 来配置插件默认图标。

## 注意事项

- 哈希命令限制单个文件最大 128 MB，避免插件超时。
- 多文件哈希最多展示前 10 个文件。
- 不写入、不修改文件。
