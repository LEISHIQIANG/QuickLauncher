# Process Tools

## 插件定位

Process Tools 用来做轻量进程排查，不替代任务管理器，但能在 QuickLauncher 里快速回答两个问题：

- 现在谁占资源比较高？
- 某个进程、PID 或路径关键字是否正在运行？

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `process_tools.top` | `proc-top`、`process-top`、`进程排行` | `mem/cpu` 和数量可选 | 按内存或 CPU 输出进程排行 |
| `process_tools.find` | `proc`、`ps`、`查进程` | 进程名、PID、路径关键字 | 查找匹配进程并显示 PID、内存、路径 |

## 示例

```text
proc-top
proc-top cpu 15
proc python
proc explorer
proc 1234
```

## 权限

当前插件不声明 QuickLauncher 高风险权限。它使用项目依赖 `psutil` 读取本机进程快照，不执行外部命令，不结束进程。

## 图标

当前插件未配置自定义图标，会使用 QuickLauncher 的系统默认命令图标。可以在 `plugin.json` 中添加 `"icon": "icon.png"` 来配置插件默认图标。

## 注意事项

- 某些系统进程路径可能因权限不足显示为空。
- CPU 排行依赖 `psutil` 的瞬时采样，适合快速观察，不适合严肃性能分析。
- 插件只读，不会 kill 进程；结束进程应由更明确的高风险命令处理。
