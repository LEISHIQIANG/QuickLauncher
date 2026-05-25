# Startup Tools

## 插件定位

Startup Tools 用来排查开机启动和环境变量问题。它适合回答：

- 开机启动项有哪些？
- 某些启动项是否指向不存在的文件？
- PATH 里是否有重复目录、缺失目录或异常长的条目？

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `startup_tools.audit` | `startup-audit`、`startup-check`、`启动项` | 无 | 列出常见 Run 注册表项和 Startup 文件夹内容 |
| `startup_tools.path` | `path-audit`、`path-check`、`环境变量检查` | 无 | 检查 PATH 重复项、缺失目录和过长条目 |

## 示例

```text
startup-audit
启动项
path-check
环境变量检查
```

## 权限

| 权限 | 原因 |
|---|---|
| `file.read` | 读取 Startup 文件夹内容和快捷方式目标 |

插件会读取常见启动位置，但不会删除、禁用或修改启动项。

## 图标

当前插件未配置自定义图标，会使用 QuickLauncher 的系统默认命令图标。可以在 `plugin.json` 中添加 `"icon": "icon.png"` 来配置插件默认图标。

## 检查范围

启动项审计会查看：

- `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce`
- `HKLM\Software\Microsoft\Windows\CurrentVersion\Run`
- `HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce`
- 当前用户 Startup 文件夹
- 全局 Startup 文件夹

PATH 检查会查看当前进程环境中的 `PATH`。

## 注意事项

- `HKLM` 某些项可能因权限不足无法读取，插件会跳过而不是报错。
- `.lnk` 快捷方式解析依赖 Windows COM；失败时会退回显示快捷方式路径。
- 插件只读，不会修改注册表或环境变量。
