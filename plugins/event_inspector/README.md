# Event Inspector

## 插件定位

Event Inspector 让你在 QuickLauncher 中快速查阅 Windows 事件日志（System / Application），无需打开事件查看器逐层点选。

适合排障场景：蓝屏分析、服务崩溃诊断、软件报错定位。

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `event_inspector.recent` | `event-recent`、`最近错误` | 无 | 显示最近 24 小时内的错误/警告摘要 |
| `event_inspector.search` | `event-search`、`搜索事件` | 关键词 | 在系统/应用日志中搜索 EventID、来源、描述等 |
| `event_inspector.source` | `event-source` | 来源名（可选） | 无参数时显示来源聚合排名；有参数时过滤该来源事件 |

## 示例

```text
event-recent
event-search 1001
event-search .NET Runtime
event-source
event-source Application Error
```

## 权限

| 权限 | 原因 |
|---|---|
| `file.read` | 读取 Windows 事件日志文件 |

## 注意事项

- 优先使用 `win32evtlog` 读取（pywin32），失败时自动回退到 `wevtutil`
- 限定最近 24 小时，最多扫描 500 条，返回 30 条
- 需要管理员权限才能读取 Security 日志，当前只扫描 System 和 Application
