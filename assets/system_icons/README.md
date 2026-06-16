# 系统图标维护说明

`assets/system_icons/` 存放随 QuickLauncher 安装提供的系统图标条目。用户自己的图标仓库保存在运行时 `config/icon_repo.json`，不要写回这里。

当前 `config.json` 包含 17 个系统图标条目：6 个 URL 条目、11 个命令条目。

## 目录结构

```text
assets/system_icons/
├── README.md
├── config.json
└── icons/
    ├── B站.png
    ├── Github.ico
    ├── 设置.ico
    └── ...
```

## 配置结构

```json
{
  "version": "1.0",
  "items": [
    {
      "id": "ac84d097-a21f-4927-96a6-0c2bb6431635",
      "name": "B站",
      "type": "url",
      "order": 1,
      "url": "https://www.bilibili.com/",
      "icon_path": "icons/B站.png"
    }
  ]
}
```

顶层字段：

| 字段 | 说明 |
|---|---|
| `version` | 系统图标配置版本 |
| `items` | 快捷方式条目数组 |

## 条目字段

### 通用字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 唯一 ID，建议 UUID |
| `name` | 是 | 弹窗显示名称，建议短文本 |
| `type` | 是 | 快捷方式类型，当前可用值见下文 |
| `order` | 是 | 排序序号，数字越小越靠前 |
| `enabled` | 否 | 是否启用，未写入时按启用处理 |
| `tags` | 否 | 搜索标签 |
| `alias` | 否 | 搜索别名 |
| `icon_path` | 是 | 相对 `assets/system_icons/` 的图标路径 |
| `icon_data` | 否 | Base64 图标数据，系统图标一般不用 |

### 当前快捷方式类型

系统图标配置可以使用 QuickLauncher 的 7 类快捷方式，但当前内置配置只使用 `url` 和 `command`。

| 类型 | 说明 |
|---|---|
| `file` | 文件或应用 |
| `folder` | 文件夹 |
| `url` | 网址 |
| `hotkey` | 快捷键 |
| `command` | 命令或内置命令 |
| `chain` | 动作链 |
| `batch_launch` | 批量启动 |

### URL 条目

```json
{
  "type": "url",
  "url": "https://github.com/",
  "preferred_browser_path": "",
  "preferred_browser_args": ""
}
```

### 命令条目

```json
{
  "type": "command",
  "command": "show_config_window",
  "command_type": "builtin",
  "trigger_mode": "immediate"
}
```

`command_type` 可为：

- `cmd`
- `powershell`
- `python`
- `bash`
- `builtin`

系统图标里常用的内置命令：

| 命令 | 说明 |
|---|---|
| `show_config_window` | 打开配置窗口 |
| `topmost` / `toggle_topmost` | 切换置顶 |

其他内置命令请以 [core/builtin_command_catalog.py](../../core/builtin_command_catalog.py) 为准。

### 热键条目

```json
{
  "type": "hotkey",
  "hotkey": "Ctrl + Alt + A",
  "hotkey_modifiers": ["ctrl", "alt"],
  "hotkey_key": "A",
  "hotkey_keys": ["A"]
}
```

### 文件 / 文件夹条目

```json
{
  "type": "file",
  "target_path": "C:\\Windows\\System32\\notepad.exe",
  "target_args": "",
  "working_dir": "",
  "run_as_admin": false
}
```

## 图标反色字段

当前数据模型支持新旧字段。新字段优先：

| 字段 | 说明 |
|---|---|
| `icon_invert_light` | 浅色主题下是否反色 |
| `icon_invert_dark` | 深色主题下是否反色 |

旧字段仍会兼容迁移：

| 字段 | 说明 |
|---|---|
| `icon_invert_with_theme` | 旧版随主题反色开关 |
| `icon_invert_current` | 旧版当前主题反色状态 |
| `icon_invert_theme_when_set` | 旧版设置反色时的主题 |

新增条目建议直接使用 `icon_invert_light` / `icon_invert_dark`。

## 图标文件规范

- 推荐 `.ico`，也支持 `.png`、`.jpg`、`.jpeg`、`.bmp`、`.svg`。
- 推荐尺寸 256x256，最小 64x64，最大 512x512。
- 文件名避免 `\ / : * ? " < > |`。
- 单个图标建议小于 500 KB。
- 尽量使用透明背景，确保深色和浅色主题都可读。

## 添加条目流程

1. 把图标文件放入 `assets/system_icons/icons/`。
2. 生成 UUID：

   ```powershell
   [guid]::NewGuid().ToString()
   ```

3. 编辑 `config.json` 的 `items` 数组。
4. 确认 JSON 使用 UTF-8，无注释、无尾逗号。
5. 重启 QuickLauncher 或重新加载配置。

## 当前内置条目

| 名称 | 类型 | 目标 |
|---|---|---|
| B站 | URL | `https://www.bilibili.com/` |
| Github | URL | `https://github.com/` |
| 抖音 | URL | `https://www.douyin.com/` |
| TikTok | URL | `https://www.tiktok.com/` |
| X | URL | `https://x.com/` |
| YouTube | URL | `https://www.youtube.com/` |
| 设置 | builtin command | `show_config_window` |
| 控制面板 | cmd | `control` |
| 注册表 | cmd | `regedit` |
| 置顶 | builtin command | `topmost` |
| 磁盘 | cmd | `diskmgmt.msc` |
| 公网IP | cmd | `curl -s ifconfig.me \| clip` |
| DNS | cmd | `ipconfig /flushdns` |
| 策略组 | cmd | `gpedit.msc` |
| 任务计划 | cmd | `taskschd.msc` |
| 清理 | cmd | `cleanmgr` |
| 网络 | cmd | `ncpa.cpl` |

## 验证建议

```powershell
py -3.12 -m json.tool assets\system_icons\config.json > $null
py -3.12 main.py --safe-mode --smoke-test
```

若修改了字段兼容或图标加载逻辑，还应运行相关 UI / 图标测试。

## 常见问题

| 问题 | 检查点 |
|---|---|
| 图标不显示 | `icon_path` 是否存在、格式是否支持、路径是否使用 `/` 或转义 `\\` |
| 条目不生效 | JSON 是否有效、`items` 是否为数组、`id` 是否重复 |
| 颜色反了 | 检查 `icon_invert_light` / `icon_invert_dark` 或旧反色字段 |
| 命令打不开 | 确认 `command_type` 与 `command` 匹配，内置命令以注册表为准 |
