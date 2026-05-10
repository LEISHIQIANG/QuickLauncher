# 内置图标编写说明

本文档详细说明如何自定义编写内置图标，供用户扩展和定制 QuickLauncher 的内置图标库。

## 目录结构

```
builtin_icons/
├── README.md          # 本说明文档
├── config.json        # 图标配置文件
└── icons/             # 图标文件存放目录
    ├── 图标1.ico
    ├── 图标2.png
    └── ...
```

## 配置文件格式

### config.json 结构

```json
{
  "version": "1.0",
  "items": [
    {
      "id": "唯一标识符",
      "name": "显示名称",
      "type": "类型",
      "order": 排序序号,
      "icon_path": "icons/图标文件名.ico",
      "icon_invert_with_theme": true,
      "icon_invert_current": false,
      "icon_invert_theme_when_set": "dark",
      ...其他字段
    }
  ]
}
```

## 字段说明

### 必填字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `id` | string | 唯一标识符，建议使用 UUID | `"09ea1312-0cf2-4cfa-ac0b-ac6ac7bd8b3d"` |
| `name` | string | 显示名称，最多6个字符 | `"设置"` |
| `type` | string | 快捷方式类型 | `"file"`, `"folder"`, `"url"`, `"hotkey"`, `"command"` |
| `order` | number | 排序序号，数字越小越靠前 | `1` |
| `icon_path` | string | 图标文件相对路径 | `"icons/设置.ico"` |

### 图标相关字段

| 字段名 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `icon_invert_with_theme` | boolean | 是否随主题反色 | `false` |
| `icon_invert_current` | boolean | 当前是否反色 | `false` |
| `icon_invert_theme_when_set` | string | 设置反色时的主题 | `"dark"` |
| `icon_data` | string | Base64 编码的图标数据（可选） | `""` |

### 类型特定字段

#### 文件/文件夹类型 (file/folder)

```json
{
  "type": "file",
  "target_path": "C:\\Windows\\System32\\notepad.exe",
  "target_args": "",
  "working_dir": ""
}
```

#### URL 类型 (url)

```json
{
  "type": "url",
  "url": "https://www.example.com"
}
```

#### 热键类型 (hotkey)

```json
{
  "type": "hotkey",
  "hotkey": "Alt + Shift + W",
  "hotkey_modifiers": ["alt", "shift"],
  "hotkey_key": "W"
}
```

#### 命令类型 (command)

```json
{
  "type": "command",
  "command": "show_config_window",
  "command_type": "builtin",
  "trigger_mode": "immediate"
}
```

## 图标文件规范

### 支持的格式

- **推荐格式**: `.ico` (Windows 图标格式)
- **支持格式**: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.svg`

### 尺寸要求

- **推荐尺寸**: 256x256 像素
- **最小尺寸**: 64x64 像素
- **最大尺寸**: 512x512 像素

### 文件命名规范

1. 使用有意义的中文或英文名称
2. 避免使用特殊字符：`\ / : * ? " < > |`
3. 文件名长度不超过 50 个字符
4. 示例：`设置.ico`, `OCR.ico`, `此电脑.ico`

### 图标设计建议

1. **简洁明了**: 图标应该清晰表达功能，避免过于复杂
2. **统一风格**: 保持与现有图标风格一致
3. **高对比度**: 确保在深色和浅色主题下都清晰可见
4. **透明背景**: 使用透明背景以适应不同主题

## 添加新图标步骤

### 步骤 1: 准备图标文件

1. 创建或获取符合规范的图标文件
2. 将图标文件放入 `icons/` 目录
3. 确保文件名清晰易懂

### 步骤 2: 生成唯一 ID

使用在线 UUID 生成器或命令行工具生成唯一标识符：

**Windows PowerShell:**
```powershell
[guid]::NewGuid().ToString()
```

**Python:**
```python
import uuid
print(uuid.uuid4())
```

### 步骤 3: 编辑 config.json

在 `items` 数组中添加新的配置项：

```json
{
  "id": "生成的UUID",
  "name": "图标名称",
  "type": "file",
  "order": 100,
  "target_path": "目标路径",
  "target_args": "",
  "working_dir": "",
  "hotkey": "",
  "hotkey_modifiers": [],
  "hotkey_key": "",
  "url": "",
  "command": "",
  "command_type": "cmd",
  "trigger_mode": "immediate",
  "icon_data": "",
  "icon_invert_with_theme": false,
  "icon_invert_current": false,
  "icon_invert_theme_when_set": "dark",
  "icon_path": "icons/你的图标.ico"
}
```

### 步骤 4: 验证配置

1. 确保 JSON 格式正确（可使用在线 JSON 验证工具）
2. 检查图标文件路径是否正确
3. 确认所有必填字段都已填写

### 步骤 5: 重启应用

重启 QuickLauncher 以加载新的内置图标。

## 完整示例

### 示例 1: 添加记事本快捷方式

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "记事本",
  "type": "file",
  "order": 10,
  "target_path": "C:\\Windows\\System32\\notepad.exe",
  "target_args": "",
  "working_dir": "",
  "hotkey": "",
  "hotkey_modifiers": [],
  "hotkey_key": "",
  "url": "",
  "command": "",
  "command_type": "cmd",
  "trigger_mode": "immediate",
  "icon_data": "",
  "icon_invert_with_theme": false,
  "icon_invert_current": false,
  "icon_invert_theme_when_set": "dark",
  "icon_path": "icons/记事本.ico"
}
```

### 示例 2: 添加网站链接

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "百度",
  "type": "url",
  "order": 20,
  "target_path": "",
  "target_args": "",
  "working_dir": "",
  "hotkey": "",
  "hotkey_modifiers": [],
  "hotkey_key": "",
  "url": "https://www.baidu.com",
  "command": "",
  "command_type": "cmd",
  "trigger_mode": "immediate",
  "icon_data": "",
  "icon_invert_with_theme": false,
  "icon_invert_current": false,
  "icon_invert_theme_when_set": "dark",
  "icon_path": "icons/百度.png"
}
```

### 示例 3: 添加全局热键

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "name": "截图",
  "type": "hotkey",
  "order": 30,
  "target_path": "",
  "target_args": "",
  "working_dir": "",
  "hotkey": "Ctrl + Alt + A",
  "hotkey_modifiers": ["ctrl", "alt"],
  "hotkey_key": "A",
  "url": "",
  "command": "",
  "command_type": "cmd",
  "trigger_mode": "immediate",
  "icon_data": "",
  "icon_invert_with_theme": true,
  "icon_invert_current": false,
  "icon_invert_theme_when_set": "dark",
  "icon_path": "icons/截图.ico"
}
```

## 注意事项

### ⚠️ 重要提示

1. **备份配置**: 修改前请备份 `config.json` 文件
2. **JSON 格式**: 确保 JSON 格式正确，注意逗号和引号
3. **路径分隔符**: Windows 路径使用双反斜杠 `\\` 或单斜杠 `/`
4. **字符编码**: 文件必须使用 UTF-8 编码
5. **唯一 ID**: 每个图标的 ID 必须唯一，不能重复

### 常见错误

#### 1. JSON 格式错误

**错误示例:**
```json
{
  "name": "测试",  // 多余的逗号
}
```

**正确示例:**
```json
{
  "name": "测试"
}
```

#### 2. 路径错误

**错误示例:**
```json
"icon_path": "icons\设置.ico"  // 单反斜杠会被转义
```

**正确示例:**
```json
"icon_path": "icons/设置.ico"
// 或
"icon_path": "icons\\设置.ico"
```

#### 3. 缺少必填字段

确保所有必填字段都存在，即使值为空字符串或空数组。

### 性能优化建议

1. **图标数量**: 建议不超过 100 个内置图标
2. **文件大小**: 单个图标文件不超过 500KB
3. **图标格式**: 优先使用 `.ico` 格式以获得最佳性能
4. **排序序号**: 合理设置 `order` 值，避免频繁调整

## 高级功能

### 图标反色

当 `icon_invert_with_theme` 设置为 `true` 时，图标会随主题自动反色：

- **深色主题**: 图标保持原色或反色（取决于 `icon_invert_current`）
- **浅色主题**: 图标自动反色以适应背景

### 内置命令

`command_type` 为 `builtin` 时，可使用以下内置命令：

- `show_config_window`: 打开配置窗口
- `toggle_topmost`: 切换置顶状态
- `pin_on`: 开启置顶
- `pin_off`: 关闭置顶
- `open_control_panel`: 打开控制面板
- `open_this_pc`: 打开此电脑
- `open_recycle_bin`: 打开回收站

### 触发模式

`trigger_mode` 可选值：

- `immediate`: 立即执行（默认）
- `after_close`: 关闭弹窗后执行

## 故障排查

### 图标不显示

1. 检查图标文件是否存在于 `icons/` 目录
2. 确认 `icon_path` 路径正确
3. 验证图标文件格式是否支持
4. 检查文件权限是否正确

### 配置不生效

1. 验证 JSON 格式是否正确
2. 检查是否有重复的 ID
3. 确认文件编码为 UTF-8
4. 重启应用程序

### 图标显示异常

1. 检查图标尺寸是否符合要求
2. 确认图标文件未损坏
3. 尝试使用 `.ico` 格式
4. 检查 `icon_invert_with_theme` 设置

## 技术支持

如有问题或建议，请通过以下方式联系：

- 提交 Issue 到项目仓库
- 查看项目文档和 FAQ
- 参考现有图标配置示例

## 版本历史

- **v1.0** (2024-03-24): 初始版本，支持基本图标配置

---

**最后更新**: 2024-03-24
