# Disk Cleaner

## 插件定位

Disk Cleaner 提供两个能力：
1. **目录大小分析** — 快速查看指定目录下哪些子目录/文件最占空间
2. **C 盘安全清理** — 扫描和清理不影响系统稳定性的文件：回收站、临时文件、缓存等

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `disk_cleaner.analyze` | `disk-analyze`、`磁盘分析` | 路径（可选） | 扫描目录，按子目录大小排序 |
| `disk_cleaner.scan` | `disk-scan`、`清理扫描` | 无 | 扫描可安全清理项，估算可释放空间 |
| `disk_cleaner.clean` | `disk-clean`、`执行清理` | 类别或 `all` | 执行清理，支持 dry-run 预览 |

## 清理类别

| 类别 ID | 说明 | 风险 |
|---|---|---|
| `recycle` | 回收站 | 无害 |
| `temp` | 用户临时文件 (>7天未访问) | 无害 |
| `prefetch` | Windows Prefetch | 无害，Windows 自动重建 |
| `cache_chrome` | Chrome 浏览器缓存 | 无害 |
| `cache_edge` | Edge 浏览器缓存 | 无害 |
| `recent` | 最近文档历史 | 无害 |
| `delivery_opt` | Windows Update 缓存 | 无害，下次更新自动下载 |
| `thumbcache` | 缩略图缓存 | 无害，自动重建 |

## 示例

```text
disk-analyze C:\Users
disk-analyze D:\Projects
disk-scan
disk-clean temp
disk-clean all
```

## 权限

| 权限 | 原因 | 风险 |
|---|---|---|
| `file.read` | 扫描目录大小、读取可清理项 | 中 |
| `file.write` | 删除临时文件、缓存、清空回收站 | **高** - 只操作上述安全类别 |
| `process.run` | 通过 QuickLauncher 统一启动通道请求系统清理命令 | **高** |
| `admin.required` | Prefetch、Windows Update 缓存等系统目录清理需要管理员权限 | **高** |

## 注意事项

- 目录分析超时 5 秒，大目录会截断
- 清理操作不可撤销，但只清理不影响系统稳定性的文件
- delivery_opt 清理时会自动停止/启动 Windows Update 和 BITS 服务
- 清理 temp 只删除 7 天以上未访问的文件，避免影响正在运行的程序
