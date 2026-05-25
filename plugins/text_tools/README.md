# Text Tools

## 插件定位

Text Tools 是少量通用文本辅助命令，保留给临时文本处理场景。它不是插件系统的主方向；更复杂的文本工作流建议拆成更明确的问题型插件。

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `text_tools.reverse` | `reverse`、`反转` | 文本 | 反转输入文本 |
| `text_tools.count` | `count`、`统计`、`字数` | 文本 | 统计行数、词数、字符数 |
| `text_tools.case` | `case`、`大小写` | `upper/lower` + 文本 | 转换大小写 |

## 示例

```text
reverse hello
count 一段文本
case upper hello
case lower HELLO
```

## 权限

| 权限 | 原因 |
|---|---|
| `clipboard.read` | 参数为空时读取剪贴板作为输入 |
| `clipboard.write` | 提供复制结果按钮 |

## 图标

当前插件未配置自定义图标，会使用 QuickLauncher 的系统默认命令图标。可以在 `plugin.json` 中添加 `"icon": "icon.png"` 来配置插件默认图标。

## 注意事项

- 优先使用显式参数；剪贴板只是兜底输入。
- 不读取文件、不联网、不修改系统状态。
