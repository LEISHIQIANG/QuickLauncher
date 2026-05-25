# Network Tools

## 插件定位

Network Tools 提供基础网络连通性检查，适合快速确认主机是否可达、DNS 是否能解析。它是轻量诊断插件，不负责复杂抓包或长期监控。

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `network_tools.ping` | `ping` | 主机名或 IP | 发送 4 个 ping 包并返回摘要 |
| `network_tools.dns` | `dns`、`nslookup` | 域名或 IP | 查询 DNS 解析记录 |

## 示例

```text
ping example.com
dns openai.com
nslookup github.com
```

## 权限

| 权限 | 原因 |
|---|---|
| `network.request` | 执行网络连通性与解析检查 |

## 图标

当前插件未配置自定义图标，会使用 QuickLauncher 的系统默认命令图标。可以在 `plugin.json` 中添加 `"icon": "icon.png"` 来配置插件默认图标。

## 注意事项

- 当前实现会调用系统 `ping` / `nslookup`，并带超时保护。
- 参数会做基本字符过滤，避免把输入拼成任意 shell 命令。
- 网络失败、DNS 被污染或公司代理策略都可能影响结果。
