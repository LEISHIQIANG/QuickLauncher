# QuickLauncher — Python 源码分析 & C++ 全新项目参考手册

> **Python 参考版本**: v1.6.3.6 | **分析日期**: 2026-06-22 | **Python 代码量**: ~50,047 行 (500+ 源文件) | **测试**: 4095 用例 (213 文件)

> ⚠ **重要声明**
>
> **C++ 版本是全新独立项目，不是 Python 版本的迁移或升级。**
> C++ 版本仅以 Python 版本的功能设计、算法逻辑、数据结构作为参考，从零开始构建，与 Python 版本无代码兼容要求。
>
> | 项目 | 路径 |
> |---|---|
> | Python 参考项目 | `G:\LEI-PLUG\QuickLauncher\QuickLauncher_V1.6.3.6\` |
> | C++ 全新项目 | `G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0\` |

---

## 目录

- [一、Python 源码架构](#一python-源码架构)
  - [1.1 总览与分层目录](#11-总览与分层目录)
  - [1.2 领域层完整数据模型](#12-领域层完整数据模型)
  - [1.3 应用层架构](#13-应用层架构)
  - [1.4 核心层完整功能清单](#14-核心层完整功能清单)
  - [1.5 表现层架构](#15-表现层架构)
  - [1.6 钩子系统](#16-钩子系统)
  - [1.7 基础设施层](#17-基础设施层)
  - [1.8 服务层与扩展层](#18-服务层与扩展层)
- [二、核心算法详解](#二核心算法详解)
  - [2.1 模糊搜索引擎](#21-模糊搜索引擎)
  - [2.2 拼音搜索](#22-拼音搜索)
  - [2.3 命令注册与搜索](#23-命令注册与搜索)
  - [2.4 插件系统](#24-插件系统)
- [三、关键系统详解](#三关键系统详解)
  - [3.1 配置管理生命周期](#31-配置管理生命周期)
  - [3.2 快捷方式执行器](#32-快捷方式执行器)
  - [3.3 安全模块](#33-安全模块)
  - [3.4 自启动管理](#34-自启动管理)
  - [3.5 剪贴板服务](#35-剪贴板服务)
  - [3.6 图标提取系统](#36-图标提取系统)
  - [3.7 样式与主题系统](#37-样式与主题系统)
- [四、C++ 全新项目架构设计](#四c-全新项目架构设计)
  - [4.0 C++ 编码规范](#40-c-编码规范)
  - [4.1 技术选型](#41-技术选型)
  - [4.2 C++ 目录树](#42-c-目录树)
  - [4.3 核心架构差异与转换规则](#43-核心架构差异与转换规则)
  - [4.4 关键设计决策与代码模板](#44-关键设计决策与代码模板)
    - [4.4.1 依赖注入](#441-依赖注入)
    - [4.4.2 端口/适配器](#442-端口适配器)
    - [4.4.3 事件总线](#443-事件总线)
    - [4.4.4 StateStore](#444-statestore)
    - [4.4.5 领域模型](#445-领域模型-c-版)
    - [4.4.6 快捷方式执行器](#446-快捷方式执行器-策略模式)
    - [4.4.7 Hooks DLL 直接集成](#447-hooks-dll-直接集成)
    - [4.4.8 内存管理策略](#448-内存管理策略)
    - [4.4.9 线程模型](#449-线程模型)
    - [4.4.10 错误处理策略](#4410-错误处理策略)
  - [4.5 分功能重构实施指南](#45-分功能重构实施指南)
  - [4.6 层间依赖规则](#46-层间依赖规则)
  - [4.7 数据流示例](#47-数据流示例)
- [五、Python → C++ Win32 API 等价对照表](#五python--c-win32-api-等价对照表)
- [六、数据格式兼容性表](#六数据格式兼容性表)
- [七、C++ 重构推进指南](#七c-重构推进指南)
  - [7.1 推荐推进顺序](#71-推荐推进顺序)
  - [7.2 每个功能的推进步骤](#72-每个功能的推进步骤)
  - [7.3 CMake 项目结构建议](#73-cmake-项目结构建议)
  - [7.4 关键第三方依赖](#74-关键第三方依赖-vcpkg--cmake-fetchcontent)
  - [7.5 开发环境配置](#75-开发环境配置)
- [八、附录](#八附录)
  - [A. Python 源码文件索引](#a-python-源码文件索引-按层)
  - [B. 关键数字速查](#b-关键数字速查)

---

## 一、Python 源码架构

### 1.1 总览与分层目录

```
QuickLauncher_V1.6.3.6/
│
├── main.py                          # 入口点 → ApplicationBootstrap().run()
├── qt_compat.py                     # PyQt5 兼容性导出层 (i18n包装的widget, DPI设置, 693行)
├── runtime_paths.py                 # 源码/打包运行时路径解析
├── run_dev_with_conpty.py           # 开发运行辅助 (ConPTY)
├── runtime_manifest.json            # 构建清单 (Nuitka隐式导入, 数据文件, 插件存储)
├── pyproject.toml                   # Ruff/coverage/mypy 配置
├── requirements.txt                 # PyQt5 5.15.11, pywin32, Pillow, psutil, pynput, watchdog, qrcode
├── requirements-dev.txt             # 开发额外依赖
├── mypy.ini / pytest.ini            # 类型检查/测试配置
├── QuickLauncher.manifest           # Windows 应用程序清单 (DPI感知/长路径)
├── third_party_licenses.json        # 第三方许可清单
│
├── bootstrap/                       # [组合根] 启动编排 (14文件)
├── application/                     # [应用层] 端口/适配器模式, 事件总线, StateStore (15文件)
├── domain/                          # [领域层] 纯数据模型, 零外部依赖 (3文件)
├── core/                            # [核心层] 业务逻辑 (~90文件, 最庞大)
│   ├── core/ (根)                   # 中心服务/管理器  (~60文件)
│   ├── core/plugin/                 # 插件子系统  (16文件)
│   ├── core/command_exec/           # 命令执行子系统  (11文件)
│   ├── core/preprocessing/          # 输入预处理管道  (9文件)
│   └── core/auto_start/             # 自启动  (2文件)
├── ui/                              # [表现层] PyQt5 托盘/弹窗/配置窗口 (130+文件)
├── hooks/                           # [钩子层] 全局鼠标/键盘钩子 DLL 封装 (8文件)
├── infrastructure/                  # [基础设施] 持久化/进程/Shell/Windows适配器 (10文件)
├── services/                        # [服务层] API客户端/自动更新 (8文件)
├── extensions/                      # [扩展层] 插件SDK v1 (1文件)
├── modules/                         # [模块层] 内置模块入口（当前为空，预留扩展）
├── platforms/                       # [平台层] 平台初始化 (2文件)
├── plugins/                         # [插件] QR码扫描 + 截图OCR (10+文件)
├── hooks_dll/                       # C++ 钩子 DLL 源码 (4文件)
├── assets/                          # 应用资源 (~53文件)
├── config/                          # 运行时配置文件 (~5文件)
├── tests/                           # 测试套件 (213测试文件)
├── scripts/                         # 构建/审计/发布脚本 (49文件)
└── docs/                            # 文档 (~90+文件)
```

**运行模式（CLI 分派）**: `gui`, `smoke-test`, `file-dialog`, `plugin-helper`, `plugin-worker`, `install-service`, `uninstall-service`, `service`, `configure-autostart`, `autostart-helper`, `autostart-launch`

---

### 1.2 领域层完整数据模型

#### 1.2.1 常量与归一化函数

```python
# domain/models.py 常量
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 300.0
_DEFAULT_COMMAND_OUTPUT_MAX_CHARS = 2000
BATCH_LAUNCH_MODULE_ID = "quicklauncher.batch_launch"
BATCH_LAUNCH_MODULE_VERSION = "0.1.0"

# 归一化函数
normalize_command_timeout_seconds(value: float | None) -> float   # clamp [1.0, 86400.0]
normalize_command_output_max_chars(value: int) -> int             # clamp [100, 100000]
normalize_chain_step_delay_ms(value: float) -> float              # 批量启动步骤间隔 clamp [0.0, 60000.0]
normalize_trigger_settings(settings: Any) -> Any                  # 返回 settings 或 {}
```

#### 1.2.2 DEFAULT_SPECIAL_APPS（33项）

CAD/3D 建模软件列表，用于特殊窗口处理：
`"acad", "autocad", "revit", "sketchup", "rhino", "rhino8", "blender", "maya", "3dsmax", "zbrush", "substance", "cinema4d", "houdini", "nuke", "aftereffects", "premiere", "fusion360", "solidworks", "catia", "inventor", "navisworks", "gcad", "gstarcad", "zwcad", "caxa", "bricscad", "cadreader", "fastcad", "dwgviewr", "cadsee"`

#### 1.2.3 ShortcutType 枚举（8种）

| 成员 | 值 | 说明 |
|---|---|---|
| FILE | "file" | 文件快捷方式 |
| FOLDER | "folder" | 文件夹快捷方式 |
| URL | "url" | URL 链接 |
| HOTKEY | "hotkey" | 热键快捷方式 |
| COMMAND | "command" | 命令执行 |
| BATCH_LAUNCH | "batch_launch" | 批量启动 |
| MACRO | "macro" | 宏录制 |

#### 1.2.4 ShortcutItem 完整字段（40字段）

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | id | str | uuid4() | 唯一标识 |
| 2 | name | str | "" | 显示名称 |
| 3 | type | ShortcutType | FILE | 快捷方式类型 |
| 4 | order | int | 0 | 排序位置 |
| 5 | enabled | bool | True | 是否启用 |
| 6 | tags | list[str] | [] | 标签列表 |
| 7 | last_used_at | float | 0.0 | 最后使用时间戳 |
| 8 | use_count | int | 0 | 使用次数 |
| 9 | smart_order | int \| None | None | 智能排序值 |
| 10 | target_path | str | "" | 目标路径(文件/文件夹) |
| 11 | target_args | str | "" | 启动参数 |
| 12 | working_dir | str | "" | 工作目录 |
| 13 | hotkey | str | "" | 热键字符串(旧格式) |
| 14 | hotkey_modifiers | list[str] | [] | 热键修饰符 |
| 15 | hotkey_key | str | "" | 热键主键 |
| 16 | hotkey_keys | list[str] | [] | 热键组合键列表 |
| 17 | url | str | "" | URL 地址 |
| 18 | preferred_browser_path | str | "" | 首选浏览器路径 |
| 19 | preferred_browser_args | str | "" | 首选浏览器参数 |
| 20 | command | str | "" | 命令内容 |
| 21 | command_type | str | "cmd" | 命令类型: cmd/powershell/python/bash/builtin |
| 22 | show_window | bool | False | 是否显示窗口 |
| 23 | command_variables_enabled | bool | False | 启用命令变量 |
| 24 | capture_output | bool | False | 捕获输出 |
| 25 | command_timeout_seconds | float | 300.0 | 命令超时 |
| 26 | command_output_max_chars | int | 2000 | 最大输出字符 |
| 27 | command_panel_size | str | "medium" | 面板尺寸: small/medium/large |
| 28 | command_params | list[dict] | [] | 命令参数定义 |
| 29 | command_env | dict | {} | 环境变量 |
| 30 | command_encoding | str | "auto" | 编码: auto/utf-8/gbk/mbcs |
| 31 | module_id | str | "" | 批量启动模块ID |
| 32 | module_version | str | "" | 批量启动模块版本 |
| 33 | batch_launch_steps | list[dict] | [] | 批量启动步骤 |
| 34 | raw_mode | bool | False | 原始模式 |
| 35 | macro_events | list[dict] | [] | 宏事件列表 |
| 36 | macro_speed | float | 1.0 | 宏回放速度 |
| 37 | macro_hide_while_recording | bool | False | 录制时隐藏 |
| 38 | trigger_mode | str | "immediate" | 触发模式 |
| 39 | icon_path | str | "" | 图标路径 |
| 40 | icon_data | str | "" | 图标数据(base64) |
| 41 | alias | str | "" | 搜索别名 |
| 42 | icon_invert_light | bool | False | 亮色主题反转 |
| 43 | icon_invert_dark | bool | False | 暗色主题反转 |
| 44 | icon_invert_with_theme | bool | False | 跟随主题反转 |
| 45 | icon_invert_current | bool | False | 当前反转状态 |
| 46 | icon_invert_theme_when_set | str | "" | 设置时的主题 |
| 47 | run_as_admin | bool | False | 以管理员运行 |

**command_params 有效参数类型**: `"text", "choice", "bool", "file", "folder", "number", "password", "textarea"`
**参数来源(source)**: `"", "clipboard", "selected_text", "selected_file", "selected_file_dir", "last"`
**参数验证器(validator)**: `"", "path", "file", "folder", "url", "domain", "ip", "port", "json", "regex", "number"`

#### 1.2.5 Folder 完整字段（10字段）

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | id | str | uuid4() | 唯一标识 |
| 2 | name | str | "" | 文件夹名称 |
| 3 | order | int | 0 | 排序位置 |
| 4 | is_system | bool | False | 系统文件夹 |
| 5 | is_dock | bool | False | Dock栏文件夹 |
| 6 | is_icon_repo | bool | False | 图标仓库文件夹 |
| 7 | items | list[ShortcutItem] | [] | 包含的快捷方式 |
| 8 | linked_path | str | "" | 链接路径(文件夹同步) |
| 9 | auto_sync | bool | False | 自动同步 |
| 10 | last_sync_time | float | 0.0 | 最后同步时间 |

#### 1.2.6 AppSettings 完整字段（88字段 + 2属性）

**外观/布局类:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 1 | theme | str | "dark" | 主题: dark/light |
| 2 | theme_follow_system | bool | True | 跟随系统主题 |
| 3 | bg_alpha | int | 90 | 背景透明度(0-100) |
| 4 | dock_bg_alpha | int | 90 | Dock透明度 |
| 5 | icon_alpha | float | 1.0 | 图标透明度 |
| 6 | icon_size | int | 24 | 图标尺寸 |
| 7 | cell_size | int | 44 | 单元格尺寸 |
| 8 | cols | int | 5 | 列数 |
| 9 | corner_radius | int | 10 | 圆角半径 |
| 10 | shadow_size | int | 0 | 阴影尺寸 |
| 11 | shadow_distance | int | 0 | 阴影距离 |
| 12 | ui_scale_percent | int | 100 | UI缩放比例(90-150) |

**行为类:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 13 | last_page_index | int | 0 | 上次页面索引 |
| 14 | close_after_launch | bool | True | 启动后关闭弹窗 |
| 15 | show_on_startup | bool | True | 启动时显示 |
| 16 | auto_start | bool | False | 开机自启 |
| 17 | sort_mode | str | "custom" | 排序: custom/smart/name |
| 18 | hardware_acceleration | bool | False | 硬件加速 |
| 19 | hide_tray_icon | bool | False | 隐藏托盘图标 |
| 20 | enable_debug_log | bool | False | 调试日志 |
| 21 | auto_update_enabled | bool | False | 自动更新 |
| 22 | disable_logging | bool | False | 禁用日志 |
| 23 | sleep_mode_enabled | bool | True | 睡眠模式 |
| 24 | sleep_timeout_seconds | int | 10 | 睡眠超时 |
| 25 | show_welcome_guide | bool | True | 欢迎引导 |
| 26 | first_run | bool | True | 首次运行 |
| 27 | last_version | str | "" | 上次版本 |
| 28 | language | str | "zh_CN" | 语言 |

**Dock/弹窗类:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 29 | dock_enabled | bool | True | 启用Dock |
| 30 | dock_height_mode | int | 1 | Dock高度模式 |
| 31 | popup_max_rows | int | 8 | 弹窗最大行数 |
| 32 | popup_align_mode | str | "mouse_center" | 弹窗对齐模式 |
| 33 | hover_leave_delay | int | 200 | 悬停离开延迟(ms) |
| 34 | popup_auto_close | bool | True | 自动关闭 |
| 35 | popup_multi_open_when_pinned | bool | False | 钉住时多开 |
| 36 | double_click_interval | int | 300 | 双击间隔(ms) |
| 37 | search_default_active | bool | False | 默认激活搜索 |

**触发配置类:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 38 | popup_trigger_mode | str | "mouse" | 触发模式: mouse/keyboard |
| 39 | popup_trigger_keys | list[str] | [] | 触发键列表 |
| 40 | popup_trigger_button | str | "middle" | 触发鼠标键 |
| 41 | popup_trigger_modifiers | list[str] | [] | 触发修饰键 |
| 42 | popup_special_trigger_mode | str | "mouse" | 特殊触发模式 |
| 43 | popup_special_trigger_keys | list[str] | [] | 特殊触发键 |
| 44 | popup_special_trigger_button | str | "middle" | 特殊触发按钮 |
| 45 | popup_special_trigger_modifiers | list[str] | ["ctrl"] | 特殊触发修饰键 |

**背景/玻璃效果类（4种背景模式，每种含 alpha/blur/edge_opacity）:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 46 | bg_mode | str | "theme" | 背景模式: theme/image/acrylic/glass |
| 47 | bg_solid_color | str | "#2b2b2b" | 纯色背景 |
| 48 | bg_blur_radius | int | 0 | 模糊半径 |
| 49-51 | theme_bg_alpha/blur_radius/edge_opacity | int/int/float | 90/0/0.0 | 主题背景参数 |
| 52-54 | image_bg_alpha/blur_radius/edge_opacity | int/int/float | 90/0/0.0 | 图片背景参数 |
| 55-57 | acrylic_bg_alpha/blur_radius/edge_opacity | int/int/float | 90/0/0.0 | 亚克力背景参数 |
| 58-60 | glass_bg_alpha/blur_radius/edge_opacity | int/int/float | 30/20/0.9 | 玻璃背景参数 |
| 61 | edge_highlight_color | str | "#ffffff" | 边缘高亮颜色 |
| 62 | edge_highlight_opacity | float | 0.0 | 边缘高亮透明度 |
| 63 | custom_bg_path | str | "" | 自定义背景路径 |

**颜色滤镜类（暗色/亮色各7个参数）:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 64-70 | dark_black_point/white_point/mid_gamma/temperature/acrylic/bg_alpha_filter | int | 50/50/50/50/30/100 | 暗色滤镜 |
| 71-77 | light_black_point/white_point/mid_gamma/temperature/acrylic/bg_alpha_filter | int | 50/50/50/50/30/100 | 亮色滤镜 |

**插件/命令/安全类:**

| # | 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| 78 | enabled_plugins | list[str] | [] | 启用插件ID列表 |
| 79 | favorite_commands | list[str] | [] | 收藏命令 |
| 80 | disabled_builtin_commands | list[str] | [] | 禁用内置命令 |
| 81 | plugin_dev_mode | bool | False | 插件开发模式 |
| 82 | preprocessing_enabled | bool | True | 预处理启用 |
| 83 | preprocessing_strict_mode | bool | False | 严格模式 |
| 84 | preprocessing_audit_enabled | bool | True | 审计日志 |
| 85 | preprocessing_rate_limiting_enabled | bool | True | 速率限制 |
| 86 | security_block_dangerous_patterns | bool | True | 阻止危险模式 |
| 87 | security_require_variable_quoting | bool | True | 变量引号要求 |
| 88 | special_apps | list[str] | DEFAULT_SPECIAL_APPS | 特殊应用列表 |
| 89 | enable_context_detection | bool | True | 上下文检测 |
| 90 | enable_plugins | bool | True | 启用插件 |

**计算属性:**
- `bg_alpha_255 -> int`: `round(bg_alpha * 255 / 100)` — 转换为0-255范围
- `dock_bg_alpha_255 -> int`: `round(dock_bg_alpha * 255 / 100)`

#### 1.2.7 AppData 根容器

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| version | str | "2.5" | 数据格式版本 |
| config_schema_version | int | 1 | Schema 版本 |
| settings | AppSettings | AppSettings() | 应用设置 |
| folders | list[Folder] | [] | 文件夹列表 |

**方法:**
- `__post_init__()`: 若 folders 为空，创建默认文件夹
- `_create_default_folders()`: 创建 "Dock" (is_dock=True) 和 "常用" (is_system=True)
- `get_dock() -> Folder | None`: 获取 Dock 文件夹
- `get_pages() -> list[Folder]`: 获取非 Dock 文件夹
- `get_folder_by_id(folder_id) -> Folder | None`

#### 1.2.8 剪贴板值对象 (domain/clipboard.py)

**ClipboardFormatInfo** (4字段):
`format_id: int`, `name: str`, `readable: bool`, `size_hint: int = 0`

**ClipboardSnapshot** (10字段 + 2属性):
`sequence: int`, `captured_at: float`, `formats: dict[int, object]`, `text: str`, `file_paths: list[str]`, `html: str`, `rtf: bytes`, `image_info: dict`, `source: str = "win32"`, `truncated: bool`, `error: str`
- `has_image -> bool`: image_info 包含 "width"
- `is_empty -> bool`: text/file_paths/html/image_info 全空

**ClipboardClassification** (5字段):
`kind: str`, `confidence: float`, `summary: str`, `actions: list[str]`, `metadata: dict`

---

### 1.3 应用层架构

#### 1.3.1 事件总线 (application/events.py)

```python
class Event:                    # 基类, 含 timestamp = time.monotonic()
class ConfigSaved(Event):       # revision: int, file_path: str
class ConfigLoaded(Event):      # version: str, schema_version: int
class ShortcutExecuted(Event):  # shortcut_id, shortcut_name, shortcut_type

class EventBus:                 # 线程安全 pub/sub (RLock)
    def subscribe(event_type, listener)
    def unsubscribe(event_type, listener)
    def publish(event)          # 同步, 异常被记录并抑制

event_bus = EventBus()          # 全局单例
```

#### 1.3.2 StateStore (application/state/store.py)

```python
class AppSnapshot(frozen=True):  # revision: int, state: Mapping[str, Any]

class StateStore:
    _lock: threading.RLock
    _state: State               # deepcopy of initial_state
    _revision: int

    def snapshot() -> AppSnapshot          # 返回冻结快照
    def submit(command, expected_revision) # 乐观锁, 不匹配抛 RevisionConflict
    def replace(state, expected_revision)  # 整体替换
```

#### 1.3.3 执行契约 (application/execution/contracts.py)

**ExecutionErrorCode** (9值): `VALIDATION`, `PRECONDITION`, `SECURITY`, `CANCELLED`, `TIMEOUT`, `NOT_FOUND`, `PROCESS`, `PLUGIN`, `INTERNAL`

**ExecutionPolicy** (frozen, 4字段): `timeout_seconds=300.0`, `capture_output=True`, `confirm_dangerous=True`, `audit=True`

**CancellationToken**: 基于 `threading.Event` 的协作取消

**ExecutionRequest** (10字段): `command_id`, `args_text`, `raw_input`, `context_meta`, `source`, `shortcut`, `args`, `command_def`, `invocation`, `policy`

**ExecutionResult** (frozen, 5字段): `success`, `message`, `error_code`, `payload`, `duration_seconds`

#### 1.3.4 端口协议 (application/ports/)

**持久化端口:**
- `ConfigRepository`: `load() -> Mapping`, `save(data, expected_revision) -> int`
- `BackupStore`: `create(data, reason) -> str`, `restore(backup_id) -> Mapping`, `list() -> list`
- `HistoryStore`: `append(revision, data, action, summary)`, `list() -> list`
- `SaveScheduler`: `schedule(callback)`, `flush(callback) -> bool`, `cancel()`
- `Clock`: `now() -> float`
- `ConfigStatePort`: `save_lock`, `write_lock`, `runtime_revision`, `batch_depth`, `batch_dirty`

**平台端口:**
- `GlobalHotkeyPort`: `register(hotkey, callback)`, `unregister(hotkey)`
- `WindowPort`: `activate_window(hwnd)`, `find_windows(title)`
- `IconProvider`: `get_icon(path, size) -> bytes`
- `AutoStartPort`: `is_enabled()`, `enable()`, `disable()`

**搜索端口:**
- `SearchPort`: `match(shortcuts, query, sort_mode, limit)`, `resolveSearchUrl(query)`, `findSlashCommands(query)`
- `WebSearchAction`: `engine`, `keyword`, `url_template`

**Shell 端口:**
- `ShellOpenerPort`: `open_path(path)`, `relaunch(argv)`, `run_detached(argv, cwd)`, `launch_with_file(executable, file_path, cwd)`

**UI 动作端口:**
- `UIAction` 枚举: `SHOW_CONFIG`, `SHOW_POPUP`, `SHOW_ABOUT`, `SHOW_LOG`, `SHOW_DIAGNOSTICS`, `SHOW_UPDATE`, `QUIT`, `RESTART`, `TOGGLE_TOPMOST`, `PIN_ON`, `PIN_OFF`, 等
- `UIActions`: `invoke(action: UIAction, **kwargs)`

#### 1.3.5 错误分类 (application/errors.py)

```
ApplicationError (base)
├── DomainError
├── ValidationError
├── InfrastructureError
├── UserCancelled
├── OperationTimeout
├── SecurityViolation
└── RevisionConflict
```

---

### 1.4 核心层完整功能清单

#### 1.4.1 DataManager — 中央数据管理器 (746行, 单例)

**子服务（懒加载单例）:**

| 访问器 | 服务类 | 职责 |
|---|---|---|
| `_get_config_store()` | ConfigDataStore | JSON 读写 data.json |
| `_get_backup_service()` | ConfigBackupService | 时间戳自动备份 |
| `_get_package_service()` | ConfigPackageService | 导入/导出包 |
| `_get_recovery_service()` | ConfigRecoveryService | 崩溃恢复报告 |
| `_get_save_scheduler()` | SaveScheduler | 防抖延迟保存 |
| `_get_icon_repository()` | IconRepository | 图标文件存储 |
| `_get_icon_repository_service()` | IconRepositoryService | 系统+用户图标合并 |
| `_get_folder_service()` | FolderService | 文件夹 CRUD |
| `_get_shortcut_service()` | ShortcutService | 快捷方式 CRUD |
| `_get_settings_service()` | SettingsService | 设置项读写 |
| `_get_save_coordinator()` | SaveCoordinator | 原子保存协调 |
| `_get_data_loader()` | DataLoader | 加载/重载/出厂重置 |
| `_get_backup_service_runner()` | BackupService | 完整备份/恢复/导入 |
| `_get_history_manager()` | ConfigHistoryManager | 历史快照 |

**完整公开方法:**

```python
# 生命周期
save(immediate=False) -> bool
shutdown(timeout=3.0)
reload()
factory_reset(callback=None) -> dict
batch_update(immediate=False)  # 上下文管理器

# 文件夹 CRUD
add_folder(name) -> Folder
rename_folder(folder_id, new_name) -> bool
delete_folder(folder_id) -> bool
reorder_folders(folder_ids: list[str])

# 快捷方式 CRUD
add_shortcut(folder_id, shortcut) -> bool
add_shortcuts(folder_id, shortcuts) -> int
update_shortcut(folder_id, shortcut) -> bool
delete_shortcut(folder_id, shortcut_id) -> bool
get_shortcut_by_id(shortcut_id) -> ShortcutItem | None
reorder_shortcuts(folder_id, shortcut_ids)
move_shortcut_to_folder(shortcut_id, target_folder_id) -> bool

# 批量操作
delete_shortcuts_batch(shortcut_ids) -> dict
move_shortcuts_batch(shortcut_ids, target_folder_id) -> dict
copy_shortcuts_batch(shortcut_ids, target_folder_id) -> dict
set_shortcuts_enabled_batch(shortcut_ids, enabled) -> dict

# 设置
update_settings(*, immediate=True, **kwargs)
get_settings() -> AppSettings
set_language(language, immediate=True) -> str

# 备份/恢复/导入
backup_full_config(save_path) -> bool
restore_full_config(backup_path) -> bool
export_shareable_config(save_path) -> bool
import_shareable_config(import_path, merge=True) -> bool

# 图标缓存
clean_icon_cache(dry_run=False) -> dict
get_icon_cache_stats() -> dict

# 使用跟踪
record_shortcut_used(shortcut_id) -> bool
recalculate_smart_order(folder_id=None) -> dict

# 历史
list_config_history() -> list
restore_config_history(snapshot_id) -> bool

# ConfigState 只读属性
save_lock, write_lock, runtime_revision, batch_depth, batch_dirty
```

#### 1.4.2 CommandRegistry — 命令注册中心 (652行)

**数据结构:**

```python
@dataclass CommandParam:
    name, type="text", required=False, default="", choices: list[str]
    sensitive=False, label="", placeholder="", help="", multiline=False
    remember=True, source="", validator="", pattern=""
    min_value="", max_value="", advanced=False

@dataclass CommandAction:
    type="copy", label="", value="", enabled=True
    danger=False, primary=False, payload: dict

@dataclass CommandContext:
    raw_input, args_text, args: dict, clipboard_text, clipboard_kind
    clipboard_files: list, clipboard_html, selected_text
    selected_text_method, selected_files: list
    context_meta: dict, update_callback: Callable | None

@dataclass CommandResult:
    success=True, message="", display_type="text"
    payload: dict, actions: list[CommandAction]
    error="", is_async=False, progress=0.0, cancellable=False

@dataclass CommandDefinition:
    id, title, aliases: list[str], description, category
    handler: Callable[[CommandContext], CommandResult]
    icon_path="", permission_level="user"
    params: list[CommandParam], source="builtin"
    sensitive=False, interaction_mode="panel"
    search_terms: list[str], result_window_size=""
    metadata: CommandMetadata | dict
```

**公开方法:**
```python
register(cmd) -> bool
get(command_id) -> CommandDefinition | None
get_canonical(alias) -> str
find(query) -> list[CommandDefinition]    # 三级排序: 精确/前缀/子串
list() -> list[CommandDefinition]
list_by_category() -> dict[str, list]
list_by_owner(owner_id) -> list
count() -> int
remove(command_id) -> bool
remove_by_owner(owner_id) -> int
migrate_slash_commands() -> int
migrate_builtin_aliases() -> int
```

**搜索源（插件系统）:**
```python
register_search_source(source_id, source_info) -> bool
remove_search_source(source_id, plugin_id=None) -> bool
execute_search_sources(query, timeout=1.5, *, cancel_token) -> list
# 并发执行, 单源超时1.0s, 总超时1.5s, 每源最多50结果
```

#### 1.4.3 内置命令清单 (builtin_commands.py)

**~140 个别名映射到以下规范命令:**

| 分类 | 命令 |
|---|---|
| 配置/UI | show_config_window, toggle_topmost, pin_on, pin_off |
| 应用控制 | quit_app, restart_app, show_log, show_about, show_help |
| 维护 | show_diagnostics, show_shortcut_health, show_config_history, clean_icon_cache, clean-cache, reload_hooks |
| 路径打开 | open_data_dir, open_install_dir, open_config_file, open_icons_dir, open_history_dir, open_auto_backups_dir, open_error_log |
| Windows 系统 | open_control_panel, open_this_pc, open_recycle_bin, open_task_manager, open_windows_settings, open_services, open_device_manager, open_disk_management, open_network_connections, open_startup_folder, open_system_info |
| 高级工具 | wifi, hosts, port, dns, cidr, tls, path-audit, explorer, conflict, git, env, god |

**33+ 内置命令处理器 (各 commands_*.py 文件):**

| 文件 | 命令集 |
|---|---|
| commands_clipboard.py | 剪贴板操作(复制/粘贴/历史/清除) |
| commands_encoding.py | Base64/URL/HTML编码解码 |
| commands_git.py | Git快捷操作(status/log/diff/branch/stash/pull/push) |
| commands_maintenance.py | 诊断/健康/历史/缓存清理 |
| commands_network.py | WiFi/DNS/CIDR/TLS/端口扫描/网络信息(29K,最大命令文件) |
| commands_plugins.py | 插件管理(启用/禁用/安装/列表) |
| commands_system.py | 系统信息/环境变量/进程 |
| commands_text.py | 文本处理(字数/行计数/JSON格式化/JWT解码/Hash) |
| commands_utils.py | 工具命令(UUID/时间戳/正则测试) |
| commands_windows.py | Windows系统命令(注册表/服务/任务计划) |

#### 1.4.4 斜杠命令 (slash_commands.py)

**27 个 SlashCommand 注册:**

```python
@dataclass SlashCommand:
    canonical: str          # 规范名
    aliases: list[str]      # 别名列表
    description: str        # 描述
    category: str           # 分类
    handler: str            # 回调名(字符串, 非Callable)
    icon_path: str          # 图标路径
    display_name: str       # 显示名
    interaction_mode: str   # "direct" 或 "panel"
```

**分类:** system, internal, help, developer, network, window

#### 1.4.5 搜索引擎 (search_engines.py)

```python
@dataclass(frozen=True) SearchAction:
    engine: str             # "google"/"baidu"/"bing"/"yandex"
    keyword: str            # 搜索关键词
    url_template: str       # URL模板(含{query})

# 引擎注册
"g"/"google" → Google
"b"/"bd"/"baidu" → Baidu
"y"/"yandex" → Yandex
"e"/"bing" → Bing

# 格式: "<prefix> <keyword>" → SearchAction
parse_search_action(text) -> SearchAction | None
build_search_url(action) -> str
```

#### 1.4.6 ShortcutService — 快捷方式 CRUD (426行)

```python
class ShortcutService:
    find_with_folder(shortcut_id) -> tuple[Folder | None, ShortcutItem | None]
    get_by_id(shortcut_id) -> ShortcutItem | None
    add(folder_id, shortcut) -> bool
    add_many(folder_id, shortcuts) -> int
    update(folder_id, shortcut) -> bool
    delete(folder_id, shortcut_id) -> bool
    reorder(folder_id, shortcut_ids)
    move_to_folder(shortcut_id, target_folder_id) -> bool
    delete_batch(shortcut_ids) -> dict      # {requested, success, failed, affected_ids}
    move_batch(shortcut_ids, target_folder_id) -> dict
    copy_batch(shortcut_ids, target_folder_id) -> dict
    set_enabled_batch(shortcut_ids, enabled) -> dict
    record_used(shortcut_id) -> bool
    recalculate_smart_order(folder_id=None) -> dict
```

**智能排序算法 (`_apply_smart_order`):**
排序键: `(-use_count, -last_used_at, order)` → 将索引赋给 `smart_order`

```

#### 1.4.8 插件子系统 (core/plugin/, 16文件)

**插件生命周期状态机:**
```
loaded → enabled → disabled
  |        |         |
  v        v         v
error   quarantined  error
```

**隔离策略:**
- **内置信任** (`trust_level == "builtin"`): 进程内加载, 受限 builtins (阻止危险 os 函数, 需要权限才能 file I/O)
- **非内置**: 进程隔离 (`IsolatedPluginRuntime` — QProcess)

**沙箱限制 (`_make_plugin_builtins`):**
- `__import__`: 阻止 `PLUGIN_BLOCKED_IMPORT_ROOTS` 中的导入, os 模块限制 `PLUGIN_OS_BLOCKED_ATTRS`
- `open`: 需要 `file.read` / `file.write` 权限
- `eval` / `exec`: 设为 None

**失败跟踪与自动隔离:**
- 失败计数 → 达到 `PLUGIN_FAILURE_THRESHOLD` 时自动隔离
- 隔离流程: 排空执行器线程 → 取消搜索任务 → 持久化状态 → 记录事件

**清单验证:**
检查: id/name/version/entry 存在, entry/icon 路径安全, id 字符有效, permissions 已知, command ID 含点号

#### 1.4.9 预处理子系统 (core/preprocessing/, 9文件)

| 文件 | 功能 |
|---|---|
| pipeline.py | 预处理管道: 变量解析 → 安全检查 → 审计 |
| security.py | 命令注入防护 (危险模式检测) |
| sanitizers.py | 输入清洗 (HTML/路径/命令字符清理) |
| validators.py | 输入验证 (长度/格式/范围) |
| audit.py | 审计日志记录 |
| rate_limiter.py | 速率限制 (令牌桶算法) |
| errors.py | 预处理错误类型 |

#### 1.4.10 命令执行子系统 (core/command_exec/, 11文件)

| 文件 | 功能 |
|---|---|
| runtime.py | 执行运行时 (进程管理/超时/取消) |
| launcher_mixin.py | 启动器 mixin (面板/对话框启动) |
| platform_executors.py | 平台执行器 (cmd/powershell/python/bash) |
| profiles.py | 执行配置文件 (窗口尺寸/编码/环境变量) |
| capture.py | 输出捕获 (stdout/stderr 分离, 编码检测) |
| cleanup.py | 执行清理 (临时文件/进程句柄) |
| output.py | 输出处理 (截断/格式化) |
| audit.py | 执行审计 (命令/参数/结果记录) |
| preflight.py | 执行前检查 (路径存在/权限/参数验证) |
| standalone.py | 独立执行模式 (无UI) |

---

### 1.5 表现层架构

#### 1.5.1 TrayApp — 托盘应用主类 (727行, 9 Mixin)

```python
class TrayApp(
    TrayAppMenuMixin,        # 托盘右键菜单
    TrayAppShutdownMixin,    # 优雅关闭/atexit
    UpdateMixin,             # 自动更新检查/下载/安装
    HooksMixin,              # 鼠标+键盘DLL钩子安装
    SleepMixin,              # 空闲睡眠模式
    PopupMixin,              # 弹窗显示/隐藏编排
    StartupMixin,            # 延迟启动任务/插件加载
    WindowsMixin,            # Win32窗口管理
    QObject,
)
```

**关键信号:** `show_popup_signal(int,int)`, `show_config_signal()`, `_alt_double_tap_signal()`, `_update_event_signal`

**关键模式:**
- **快照式设置同步**: 定期快照所有相关设置, diff 对比变更, 避免全量重建
- **内存守卫**: `MemoryGuard(critical_mb=200)`, 120秒周期检查
- **懒加载**: `_get_shortcut_executor()` 延迟导入重量级模块
- **插件安全模式**: `QL_SAFE_MODE` 环境变量 + `enable_plugins` 设置

#### 1.5.2 LauncherPopup — 弹窗启动器 (756行, 16 Mixin)

```python
class LauncherPopup(
    PopupWindowLifecycleMixin,    # 显示/隐藏生命周期
    PopupWindowAnimationMixin,    # 显示/隐藏/翻页动画
    PopupWindowHwndMixin,         # HWND注册(焦点管理)
    PopupEventsMixin,             # 鼠标/键盘/滚轮事件
    PopupDataRefreshMixin,        # 数据重载/文件选择检测
    PopupCommandResultMixin,      # 斜杠命令结果显示
    PopupBackgroundMixin,        # 背景图加载/缓存
    PopupRendererMixin,           # 网格/Dock/指示器绘制
    PopupDragDropMixin,           # 拖放支持
    PopupIconMixin,               # 图标提取/缓存
    PopupSearchMixin,             # 搜索栏+搜索逻辑
    PopupWindowEffectMixin,       # DWM模糊/亚克力/窗口效果
    PopupLayoutMixin,             # 窗口尺寸/居中/网格计算
    DisposableWidget,             # 自动清理QPropertyAnimation
    PopupItemExecutionMixin,      # 快捷方式执行
    QWidget,
)
```

**搜索管线 (PopupSearchMixin):**
1. **Web搜索引擎** (`g cats` → Google搜索)
2. **斜杠命令** (`/help`)
3. **模糊本地搜索** (所有页面 + Dock + 图标仓库)
4. **插件搜索** (异步, 取消令牌)

**防抖**: 100ms 打字停顿后触发搜索

**渲染管线 (PopupRendererMixin):**
```
paintEvent → 背景 → 阴影 → 图标/搜索/Dock/指示器/钉住
```
- **背景模式**: glass (GlassBackgroundRenderer), image (异步加载), acrylic (色调填充), theme (纯色+alpha)
- **翻页动画**: 预渲染页面pixmap交叉渐变, 回退到实时渲染
- **DPI感知**: `GetDpiForMonitor` 物理像素

#### 1.5.3 玻璃背景渲染器 (GlassBackgroundRenderer)

```python
class GlassBackgroundRenderer:
    prepare(timeout_ms=3000)       # WDA_EXCLUDEFROMCAPTURE + 等待首帧
    sync_geometry()                # Win32窗口矩形同步
    configure()                    # 从设置构建渲染配置
    draw(painter)                  # 绘制到QPainter
    stop(destroy)                  # 停止工作线程

    # 内部:
    _worker_main()                 # 20 FPS 捕获循环
    _process_frame()               # BGRA裁剪 → PIL管线
    _render_frame()                # BoxBlur → 饱和度 → 色调 → 径向高光 → 暗边 → 内高光
    _publish_frame()               # 三缓冲发布(生成计数器)
```

**静态层缓存**: 径向高光、暗边、内高光、圆角遮罩按 (size, params) 缓存复用

#### 1.5.4 配置窗口 (ui/config_window/, 61文件)

**主窗口**: `ConfigWindow(QMainWindow)` → `RoundedWindow` → `TitleBar` (圆点式关闭/最小化)

**9个设置页面:**
| 页面 | 功能 |
|---|---|
| SystemPage | 系统设置(自启动/语言/更新/睡眠/硬件加速) |
| PopupPage | 弹窗设置(触发模式/对齐/行高/自动关闭) |
| AppearancePage | 外观设置(主题/背景/圆角/阴影/颜色滤镜) |
| PluginsPage | 插件管理(启用/禁用/安装/详情) |
| CommandsPage | 命令管理(内置/自定义/参数/测试) |
| DataPage | 数据管理(备份/恢复/导入/导出/历史) |
| AboutPage | 关于(版本/许可/第三方) |
| SupportPage | 支持(反馈/捐赠) |

**对话框系统 (15种):**
- ShortcutDialog, CommandDialog, CommandParamDialog
- HotkeyDialog, UrlDialog
- BatchLaunchDialog, MacroRecordDialog
- IconPickerDialog, SupportDialog
- InputTriggerRecorder, MouseKeyRecorder
- TemplateVariableHighlighter

#### 1.5.5 样式系统 (ui/styles/, 21文件)

**设计令牌 (design_tokens.py):**

| 令牌集 | 用途 | 示例 |
|---|---|---|
| SurfaceScale | 背景色 | dialog/chrome/elevated/glass/hover/selection |
| TextScale | 文字色 | primary/secondary/tertiary/disabled |
| BorderScale | 边框色 | subtle/strong/separator/focus |
| StatusScale | 状态色 | success/warning/error/info + 节点状态 |
| GroupIconScale | 导航图标 | 设置面板图标强调色 |
| RadiusScale | 圆角 | xs=4, sm=6, md=8, lg=10, xl=12 |
| SpacingScale | 间距 | s2=4 到 s9=48 |
| Elevation | 阴影层级 | 4级: (y_offset, blur, QColor) |
| DurationScale | 动画时长 | INSTANT=50ms 到 X_SLOW=480ms |
| EasingScale | 缓动曲线 | CSS cubic-bezier 字符串 |

**解析函数:**
```python
surface(theme, key)     # → QColor (dark/light后缀自动)
text(theme, key)        # → QColor
border(theme, key)      # → QColor
status(key)             # → QColor (不区分主题)
radius(key)             # → int
spacing(key)            # → int
elevation(level, is_win10)  # → (y, blur, color) (Win10降级)
duration(key)           # → int (ms)
easing(key)             # → str (cubic-bezier)
```

**QSS 生成 (qss/, 11文件):** 程序化生成 QSS 样式表, 按组件分文件:
`base`, `button`, `combobox`, `dialog`, `groupbox`, `input`, `list`, `menu`, `scrollbar`, `slider`, `tokens`

---

### 1.6 钩子系统

#### 1.6.1 HooksDLL — DLL 封装 (64K, 最大文件)

**ctypes 结构:**

| 结构 | 用途 |
|---|---|
| HooksRuntimeStats | 健康标志/事件计数/队列深度/最后事件时间 |
| HookInputEvent | 捕获输入: type/flags/timestamp_us/sequence/x/y/vk_code/scan_code |
| HookMacroEvent | 回放事件: type/flags/delay_us/x/y/vk_code/scan_code |
| HookMacroStatus | 活跃/取消状态/事件计数/回放计时 |

**回调类型:**
```python
MOUSE_CALLBACK = CFUNCTYPE(None, c_int, c_int)
KEYBOARD_CALLBACK = CFUNCTYPE(None)
HOTKEY_CAPTURE_CALLBACK = CFUNCTYPE(None, c_int, c_int, c_int)
INPUT_EVENT_CALLBACK = CFUNCTYPE(None, POINTER(HookInputEvent))
PROTECTED_CHORD_CAPTURE_CALLBACK = CFUNCTYPE(None, c_int, c_int, c_int)
```

**DLL 契约:**
- `EXPECTED_VERSION = 15`
- `EXPECTED_DLL_SHA256`: 完整性验证
- 19个必需导出 + ~15个可选导出(能力标志)

**必需导出:** InstallMouseHook, UninstallMouseHook, SetMousePaused, IsMousePaused, SetAltDoubleClickCallback, InstallKeyboardHook, UninstallKeyboardHook, IsAltHeld, IsCtrlHeld, SetGlobalHotkey, ClearGlobalHotkey, StartHotkeyCapture, StopHotkeyCapture, IsHotkeyCaptureActive, StartProtectedChordCapture, StopProtectedChordCapture, IsProtectedChordCaptureActive, ReleaseAllModifierKeys, AreHooksQuiescent

**可选导出 (能力标志):**
- 特殊应用: SetSpecialApps, ClearSpecialApps
- 诊断: GetHooksVersion, GetHooksCapabilities, GetLastHookError, IsMouseHookInstalled, IsKeyboardHookInstalled, IsRawInputFallbackActive, GetHooksRuntimeStats, ResetHooksRuntimeStats
- 输入捕获: StartInputCapture, StopInputCapture, IsInputCaptureActive
- 宏回放: PlayMacroEvents, CancelMacroPlayback, IsMacroPlaybackActive, WaitForMacroPlayback, GetMacroStatus, ReleaseMacroPressedInputs
- 触发配置: SetTriggerConfig, SetTriggerConfigEx

**关键模式:**
- **SHA-256 完整性检查**: 加载前验证 DLL 文件哈希
- **线程安全生命周期**: RLock 保护所有 DLL 状态转换
- **回调引用管理**: `_retired_callback_refs` deque(maxlen=64) 防止旧 ctypes thunk 被 GC
- **优雅关闭**: 取消回放 → 停止捕获 → 卸载钩子 → 等待2.5s静止

#### 1.6.2 HotkeyManager — 热键管理器

```python
class HotkeyManager(QObject):
    activated 信号
    set_dll(dll)
    start() / stop()
    set_hotkey(hotkey_str)        # 规范化 + DLL注册
    _normalize_hotkey(hotkey_str) # Ctrl/Alt/Shift/Win 变体统一
    _release_modifier_keys()
    _drain_pending_activated()    # 15ms 防抖合并
```

#### 1.6.3 InputMacroBackend — 宏录制/回放

```python
class InputMacroBackend:
    start_recording(mouse_move, mouse_buttons, mouse_wheel, keyboard,
                    include_injected, include_own_playback,
                    coalesce_mouse_moves, event_filter, on_event)
    stop_recording() -> events
    play(events, speed, no_timing)
    cancel() / wait(timeout_ms) / status()
    build_sequence(speed, preserve_initial_delay)
    # 线程安全 deque(maxlen=100_000)
```

---

### 1.7 基础设施层

#### 1.7.1 持久化适配器

```python
ConfigRepositoryAdapter → ConfigDataStore    # load/save JSON
BackupStoreAdapter → ConfigBackupService     # 创建/恢复/列表备份
HistoryStoreAdapter → ConfigHistoryManager   # 追加/列表快照
```

#### 1.7.2 Shell 打开器

```python
class WindowsShellOpenerAdapter:
    open_path(path)              # os.startfile / xdg-open
    relaunch(argv)               # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
    run_detached(argv, cwd)      # CREATE_NO_WINDOW
    launch_with_file(exe, file, cwd, use_cmd_start)  # 文件关联启动
```

#### 1.7.3 Windows 适配器

- `GlobalHotkeyAdapter`: RegisterHotKey/UnregisterHotKey
- `IconProviderAdapter`: 图标提取桥接
- `AutoStartHelper`: 自启动辅助函数
- `Win32Adapters`: 窗口管理/进程/系统信息

---

### 1.8 服务层与扩展层

#### 1.8.1 自动更新系统 (services/update/)

```python
UpdateConfig     # 更新源URL/检查间隔/版本号
UpdateChecker    # HTTP检查新版本 (QtNetwork)
UpdateDownloader # 下载更新包 (断点续传)
UpdateInstaller  # 安装更新 (静默安装/重启)
UpdateSession    # 会话状态管理
```

#### 1.8.2 API 客户端 (services/api/)

```python
class ApiClient:  # QtNetwork HTTP 客户端基类
    get(url, params) -> response
    post(url, data) -> response
    # 超时/重试/错误处理
```

#### 1.8.3 扩展层 (extensions/)

- `sdk/worker_protocol.py`: 插件 SDK v1 工作进程协议 (JSON-over-stdio)

#### 1.8.4 内置插件

| 插件 | 功能 | 文件 |
|---|---|---|
| qr_code_scanner | QR码扫描 | main.py, capture_qt.py, qr_runner.py, qr_worker.py |
| screenshot_ocr | 截图OCR | main.py, ocr_runner.py, ocr_service.py, ocr_worker.py, screenshot.py + vendor libs |

---

## 二、核心算法详解

### 2.1 模糊搜索引擎

**入口:** `search_shortcuts(pages, query, *, sort_mode="custom", limit=None) -> list[FuzzyMatchResult]`

**结果结构:**
```python
@dataclass FuzzyMatchResult:
    shortcut: object
    folder_id: str
    folder_name: str
    score: float
    original_index: int
    matched_fields: list[str]
```

#### 第一层: 文本归一化

```python
_normalize_text(value)   # NFKC + strip combining + casefold + collapse whitespace (LRU 2048)
_compact_text(value)     # 去除非字母数字 (LRU 2048)
_word_text(value)        # CamelCase断点插空格 + 非alnum替换空格
_word_tokens(value)      # 分词 (LRU 1024)
```

#### 第二层: 字段变体生成 (`_field_variants`)

每个字段值生成6个搜索面 (LRU 1024):
1. 原始值
2. 基名 (路径最后组件)
3. 词干 (去扩展名)
4. 紧凑 (仅字母数字)
5. 词文本 (CamelCase + 标点分割)
6. 拼音变体 (全拼 + 首字母)

#### 第三层: 字段权重 (`_iter_fields`)

| 字段 | 权重 |
|---|---|
| name | 120.0 |
| alias | 110.0 |
| tags | 95.0 |
| target_path | 55.0 |
| url | 50.0 |
| command | 45.0 |
| hotkey | 35.0 |

#### 第四层: 单项评分 (`_single_term_score`)

| 匹配类型 | 基础分 | 公式 |
|---|---|---|
| 完全归一化相等 | 138.0 | `138 + len(term) * 7` |
| 精确token匹配 | 122.0 | `122 + len(term) * 6` |
| Token前缀匹配 | 104.0 | `104 + len(term) * 5 + max(0, 12 - token_len)` |
| 缩写完全匹配 | 118.0 | `118 + len(compact) * 6 + max(0, 12 - shortest_token)` |
| 缩写前缀 | 102.0 | `102 + len(compact) * 5` |
| 缩写子串 | 84.0 | `84 + len(compact) * 4` |
| 紧凑子串 | 76.0 | `76 + len(compact) * 5 + max(0, 12 - pos) + max(0, 24 - compact_len) * 0.5` |
| 子序列(精确子串) | 70.0+ | `70 + len(needle) * 6 + max(0, 20 - pos) + boundary_bonus + (45 if full)` |
| 子序列(分散) | 38.0+ | `38 + len(needle) * 5 + contiguous_pairs * 8 + max(0, 16 - start) + boundary - gaps * 2` |
| 近似词(容错) | 42.0+ | `42 + ratio * 38` (SequenceMatcher ratio ≥ 0.78) |

**词边界加分 (`_word_boundary_bonus`):**
| 条件 | 加分 |
|---|---|
| 位置0 | +18.0 |
| 前字符为分隔符 (` _-./\()[]{}`) | +14.0 |
| CamelCase边界 (小写→大写) | +10.0 |

#### 第五层: 多项快捷方式评分 (`_shortcut_score`)

1. 按空白/标点分词
2. 每项对所有字段取最佳 (field_score + field_weight)
3. **所有项必须匹配** — 任何项无分则整体排除
4. 均值: `total / len(terms)`
5. **短语加分**: 整句重新评分, 若更高则升级
6. **多项加分**: `+min(18, (terms - 1) * 6)`
7. **搜索历史加分**: `search_history_bonus(query, shortcut_id)`

#### 第六层: 使用加分 (仅 "smart" 排序模式)

```
min(35, use_count * 1.8) + 20 * (0.5 ^ (elapsed_seconds / 259200))
```
半衰期约3天的时间衰减。

**最终排序**: `(-score, original_index)`

### 2.2 拼音搜索

**入口:** `pinyin_variants(text) -> list[str]` (LRU 2048)

**三级解析策略:**
1. **pypinyin 库**: `pypinyin.pinyin()` + FIRST_LETTER/NORMAL
2. **xpinyin 库**: `Pinyin.get_pinyin()` + `get_initials()`
3. **内置字典**: ~250字映射 + GB2312区间首字母提取

**`_gb2312_initial(char)`:** 字符→GB2312编码→双字节整数值→查表映射到a-z

**CJK过滤 (`_normalize_search_text`):**
- CJK统一汉字 (U+4E00-U+9FFF)
- CJK扩展A (U+3400-U+4DBF)
- CJK兼容 (U+F900-U+FA5F)
- ASCII字母数字

### 2.3 命令注册与搜索

**三级搜索排序:**
1. **精确匹配** — 任何可搜索词完全等于查询 (不区分大小写)
2. **前缀匹配** — 任何可搜索词以查询开头
3. **子串匹配** — 查询出现在任何可搜索词中

**可搜索词扩展来源:**
id, id(分隔符替换), title, description, category, source, aliases, search_terms, 标点/CamelCase变体

### 2.4 插件系统

**扫描:** `scan_plugins()` → 遍历插件目录 → 解析 manifest.json → 验证

**加载策略:**
```python
if trust_level == "builtin":
    importlib.util.spec_from_file_location()  # 进程内, 受限builtins
else:
    IsolatedPluginRuntime.load()              # QProcess 进程隔离
```

**信任验证:**
- `_is_builtin_plugin_package`: 路径匹配 + SHA-256 校验
- `_validate_install_source_trust`: 声称 builtin 但 install_source 非 builtin → 降级

**禁用序列:**
取消搜索任务 → 卸载隔离运行时 → 清除 sys.modules → 调用 unregister/dispose → 关闭 API → 排空执行器 → 移除命令 → 移除搜索源

---

## 三、关键系统详解

### 3.1 配置管理生命周期

#### 保存协调器 (SaveCoordinator)

```python
save(immediate=False) -> bool
    # batch模式: 标记dirty返回
    # immediate: 直接 _do_save()
    # 否则: SaveScheduler 防抖 (500ms)

_do_save():
    1. 序列化数据 (save_lock下)
    2. 写临时文件 → 自动备份 → 原子替换 (write_lock下)
    3. 成功: 记录历史快照 + 发布 ConfigSaved 事件
    4. 失败: 设置错误状态 + 清理临时文件

batch_update(immediate=False):
    # 进入: 深拷贝快照 + 取消计划保存 + 增加batch深度
    # 异常: 标记失败
    # 退出(depth=0): 失败则完整回滚, 成功则flush/schedule
```

#### 备份服务 (BackupService)

**完整备份 (.qlzip):**
```
data.json + background + icon_repo.json + 额外配置 + icons/
```

**完整恢复 (事务性):**
```
预事务日志 → 安全ZIP索引 → 背景提取 → 图标提取到临时目录
→ 数据反序列化 + 修复 → 原子图标目录交换 → 失败则完整回滚
```

**可分享导出:**
```
热键/命令/URL快捷方式 → 剥离内部数据 → 生成新ID
→ .exe/.dll图标提取为PNG → config.json + icons/
```

#### 配置验证 (config_validation.py)

**验证范围:**
- 30+ 整数设置: clamp到安全范围
- 6个浮点设置: 0.0-1.0
- 6个枚举设置: 白名单验证
- 8个列表设置: 去重 + 最大256项

**Schema验证码:**
`root_not_object`, `settings_not_object`, `folders_not_list`, `folder_{i}_not_object`, `duplicate_folder_id:{id}`, `duplicate_shortcut_id:{id}`, `invalid_shortcut_type:{type}`

#### 历史快照 (config_history.py)

```python
class ConfigHistoryManager:
    record_snapshot(data_dict, action, summary) -> ConfigSnapshot
    # 存储为 {timestamp}_{uuid}.json.gz (gzip压缩)
    list_snapshots() -> list[ConfigSnapshot]  # 最新优先
    load_snapshot_data(snapshot_id) -> dict
    prune()  # 保留 max_snapshots=20 个
```

### 3.2 快捷方式执行器

```python
class ShortcutExecutor(HotkeyExecutionMixin, FileExecutionMixin,
                       UrlExecutionMixin, CommandExecutionMixin,
                       WindowControlMixin):

    execute(shortcut, force_new=False) -> tuple[bool, str]
    execute_with_files(shortcut, files) -> bool
```

**分派逻辑:**

| ShortcutType | 处理器 |
|---|---|
| HOTKEY | `_execute_hotkey_safe` → HooksDLL 发送按键 |
| URL | `_execute_url` → 浏览器打开 (支持首选浏览器) |
| COMMAND | `_execute_command` → 命令执行服务 |
| BATCH_LAUNCH | `execute_batch_launch` → 批量启动 |
| MACRO | `_execute_macro` → InputMacroBackend.play |
| FILE/FOLDER | `_execute_file` → ShellExecuteExW |

**管理员提权:** `run_as_admin` → 检测当前权限 → `ShellExecuteW("runas")` / `PrivilegeLaunchChannel`

**前台窗口管理:**
- `_previous_hwnd`: 弹窗出现前捕获
- `_popup_hwnds`: 活跃弹窗HWND集合(排除)
- `trigger_mode = "after_close"`: 恢复前台窗口后再执行

### 3.3 安全模块

| 模块 | 功能 |
|---|---|
| path_security.py | 文件系统边界检查 (路径遍历防护) |
| import_security.py | ZIP导入安全 (路径遍历/大小限制) |
| network_security.py | 网络SSRF防护 (内网IP检测/代理检测) |
| command_action_safety.py | 命令动作安全评估 (危险模式检测) |
| command_risk.py | 命令风险评分 |
| command_param_validation.py | 命令参数验证 |

### 3.4 自启动管理 (auto_start_manager.py, 51K)

**策略: 仅辅助进程提权**

```
主进程(非提权) → ShellExecuteW("runas") → 辅助进程
辅助进程 → Task Scheduler COM → 创建/删除任务
```

**任务定义:**
- 任务名: `"QuickLauncherAutoStart"`
- 触发器: 登录触发 `TASK_LOGON_INTERACTIVE_TOKEN`
- 运行级别: `TASK_RUNLEVEL_LUA` (非提权)

**管理员启动路径:**
```
Task Scheduler → 辅助进程(--autostart-launch)
→ 获取 explorer.exe token → DuplicateTokenEx
→ CreateProcessWithTokenW (降权到用户完整性级别)
→ QuickLauncher 正常启动
```

**Win32 绑定:**
- user32: GetShellWindow, GetWindowThreadProcessId
- kernel32: GetCurrentProcess, OpenProcess, WaitForSingleObject, TerminateProcess, GetExitCodeProcess
- advapi32: OpenProcessToken, GetTokenInformation, DuplicateTokenEx, CreateProcessWithTokenW
- userenv: CreateEnvironmentBlock, DestroyEnvironmentBlock

**注册表回退:** `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

### 3.5 剪贴板服务 (clipboard_service.py, 35K)

**错误层次:**
```
ClipboardError
├── ClipboardOpenError (open_timeout)
├── ClipboardFormatUnreadableError
├── ClipboardEmptyError
├── ClipboardRestoreError
├── ClipboardComError
└── ClipboardUipiError
```

**双实现:**
- `Win32ClipboardImpl`: 线程安全, STA COM 初始化, 8步**自适应退避**重试 [10,20,50,100,100,100,200,200]ms
- `QtClipboardImpl`: 仅主线程, QApplication.clipboard()

**剪贴板格式常量:**
`CF_UNICODETEXT=13`, `CF_HDROP=15`, `CF_DIB=8`, `CF_HTML=4934`, `CF_RTF=4930`

### 3.6 图标提取系统 (icon_extractor.py, 45K)

**多源提取链:**
```
Win32 SHGetFileInfoW → ExtractIconEx → Qt QIcon → 自定义图片文件 → 生成默认图标
```

**默认图标生成:**
- CJK感知: 检测CJK字符 → 选择适当字体 (Microsoft YaHei/PingFang SC等)
- 确定性强调色: MD5(name) → 16色调色板索引
- 图标文字: 提取1-2字符 (CJK首字/首字母/CamelCase分割)
- 渐变背景 + 首字母渲染

### 3.7 样式与主题系统

**主题解析 (hierarchical):**
```python
resolve_theme(owner, default):
    # 遍历 widget 父链查找 theme/_theme/current_theme 属性
    # 或 data_manager.get_settings().theme
    # 回退到全局 app_theme
```

---

## 四、C++ 全新项目架构设计

> **本章定位**：以 Python 参考项目（`G:\LEI-PLUG\QuickLauncher\QuickLauncher_V1.6.3.6\`）的功能和算法为蓝本，为 C++ 全新项目（`G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0\`）制定架构规范。C++ 版本是独立项目，不与 Python 版本共享代码，也不要求数据格式或API兼容。

### 4.0 C++ 编码规范

统一的编码规范是大型重构项目可维护性的基础，全部 C++ 源码须遵循以下规则。

#### 4.0.1 文件与头文件

| 规则 | 说明 |
|---|---|
| 头文件卫士 | 所有头文件使用 `#pragma once`，不用 `#ifndef` 宏卫士 |
| 头文件扩展名 | `.h`（公开接口）、`.h` 或 `.cpp` 仅限实现细节 |
| 前向声明优先 | 头文件中能前向声明的不包含完整头文件，减少编译依赖 |
| include 顺序 | 对应 `.h` → 标准库 → Qt → 第三方 → 同项目其他头文件（每组空行分隔） |
| 每文件一类 | 一个 `.h`/`.cpp` 对应一个主类，辅助私有类可放同文件 |

```cpp
// 示例：MyClass.h
#pragma once

#include <optional>          // 标准库
#include <QString>           // Qt
#include <nlohmann/json.hpp> // 第三方
#include "core/IFoo.h"       // 项目内
```

#### 4.0.2 命名规范

| 符号类型 | 规范 | 示例 |
|---|---|---|
| 类 / 结构体 / 枚举类 | `PascalCase` | `ShortcutItem`, `ExecutionResult` |
| 纯虚接口类 | `I` 前缀 + `PascalCase` | `ISearchPort`, `IConfigRepository` |
| 成员函数 | `camelCase` | `execute()`, `findById()` |
| 成员变量 | `m_` 前缀 + `camelCase` | `m_revision`, `m_mutex` |
| 静态成员变量 | `s_` 前缀 + `camelCase` | `s_instance` |
| 常量 / `constexpr` | `k` 前缀 + `PascalCase` | `kDefaultTimeout`, `kMaxItems` |
| 枚举值 | `PascalCase`（enum class）| `ShortcutType::File` |
| 函数参数 | `camelCase` | `shortcutId`, `expectedRevision` |
| 宏（仅必要时） | `全大写_下划线` | `QL_ASSERT`, `QL_UNLIKELY` |

#### 4.0.3 类型与语言特性

```cpp
// ✅ 正确
auto item = ShortcutItem{};                  // 统一初始化
std::unique_ptr<IFoo> p = makeFoo();         // 资源所有权明确
QString name = tr("快捷方式");               // Qt 翻译
const auto& settings = m_dataManager->getSettings();  // const 引用避免拷贝
std::optional<int> maybeValue;               // 代替 nullptr 表达"无值"

// ❌ 避免
int* raw = new int(42);   // 裸 new — 用智能指针
#define MAX_LEN 256        // 宏常量 — 用 constexpr
void foo(bool, bool, int); // 连续同类型参数 — 用具名结构体或强类型
```

- **C++ 标准**：C++23（`concepts`, `ranges`, `std::span`, `std::expected`, `[[nodiscard]]`, `[[likely]]`）——VS 2026 / MSVC v14.51 完整支持
- **`auto` 使用**：局部变量、迭代器、lambda 返回类型使用 `auto`；函数签名和成员变量显式写类型
- **`nullptr`**：禁止 `0` 或 `NULL`，统一用 `nullptr`
- **强制检查返回值**：关键函数加 `[[nodiscard]]`（`save()`, `load()`, `execute()` 等）

#### 4.0.4 注释规范

```cpp
/**
 * @brief 根据查询字符串搜索快捷方式。
 *
 * 采用六层评分算法，支持拼音、子序列、词边界加权。
 *
 * @param pages    所有页面文件夹（不含 Dock 文件夹）
 * @param query    用户输入的查询字符串（可为空，返回全量）
 * @param sortMode 排序模式："custom" | "smart" | "name"
 * @param limit    最大返回数量，0 表示不限
 * @return 按得分降序排列的匹配结果列表
 */
[[nodiscard]] std::vector<FuzzyMatchResult> match(
    const std::vector<Folder>& pages,
    const QString& query,
    const QString& sortMode = QStringLiteral("smart"),
    int limit = 50) override;
```

- **公开接口**：必须有 Doxygen `@brief`；复杂算法参数写 `@param`/`@return`
- **实现代码**：只在非显而易见处添加行内注释，解释"为什么"而非"做了什么"
- **TODO 格式**：`// TODO(username): 说明 — GitHub Issue #N`

---

### 4.1 技术选型

| 组件 | 选择 | 版本要求 | 说明 |
|---|---|---|---|
| C++ 标准 | C++23 | — | concepts / ranges / std::span / std::expected / coroutines；VS 2026 MSVC v14.51 完整支持 |
| GUI 框架 | Qt6 | 6.5 LTS+ | PyQt5 的 C++ 原生替代 |
| 构建系统 | CMake | 3.25+ | 支持 `cmake --preset`；vcpkg toolchain 集成 |
| 包管理 | vcpkg | manifest mode | `vcpkg.json` 声明所有依赖，CI 自动还原 |
| 编译器 | MSVC 2022 | 17.8+ (v143) | `/std:c++20 /W4 /WX`；或 Clang 17 with MSVC STL |
| Windows SDK | Windows 10 SDK | 10.0.19041.0+ | Per-Monitor DPI v2 / WDA_EXCLUDEFROMCAPTURE |
| Windows API | Win32 + COM | — | 原生集成，`#include <windows.h>` + `<taskschd.h>` |
| JSON | nlohmann/json | 3.11+ | 配置持久化，`NLOHMANN_DEFINE_TYPE_INTRUSIVE` 宏 |
| 压缩 | zlib | 1.3+ | gzip 历史快照（`qCompress` / `zlib deflate`） |
| ZIP 操作 | minizip-ng | 4.0+ | `.qlzip` 备份包读写，含路径遍历防护 |
| 线程池 | QtConcurrent + std::jthread | — | 后台任务；UI 回调通过信号回主线程 |
| 日志 | spdlog | 1.13+ | `rotating_file_sink`；崩溃时 flush |
| 网络 | QtNetwork | 随 Qt6 | HTTP 更新检查 / 下载断点续传 |
| 加密/哈希 | OpenSSL | 3.0+ | TLS / SHA-256 / MD5；Qt 捆绑优先 |
| 正则 | QRegularExpression | 随 Qt6 | PCRE2 后端 |
| 拼音 | cpp-pinyin | 最新 stable | 模糊搜索；可回退到内置 ~250 字映射表 |
| 图像处理 | Qt QImage + stb_image_resize | stb 最新 | 图标提取 / 背景图缩放 |
| 测试 | GoogleTest + QtTest | GTest 1.14+ | 单元 + UI 冒烟；`ctest --preset ci` |
| 打包 | CPack + NSIS / WiX | WiX 4+ | 安装程序；`windeployqt` 收集 Qt DLL |

### 4.2 C++ 目录树

```
QuickLauncher_V0.0.0.0/               # C++ 重构项目根目录 (G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0)
├── CMakeLists.txt                     # 顶层：C++23, Qt6, vcpkg toolchain
├── CMakePresets.json                  # 预设：windows-debug / windows-release / ci
├── vcpkg.json                         # 依赖清单（manifest mode）
├── cmake/
│   ├── CompilerSettings.cmake         # /W4 /WX; Clang -Wall -Wextra
│   ├── DependencyFinder.cmake         # find_package 封装
│   └── Packaging.cmake                # CPack + windeployqt
├── resources/
│   ├── resources.qrc
│   ├── icons/                         # app.ico, command_icons/, dialog_icons/
│   ├── fonts/                         # 内嵌字体（如 Microsoft YaHei Subset）
│   ├── translations/                  # zh_CN.ts / en.ts → .qm
│   └── styles/
│
├── src/
│   ├── main.cpp
│   ├── bootstrap/      # 组合根 (14文件)
│   ├── domain/         # 纯领域模型 (7文件)
│   ├── application/    # 端口/事件/状态 (12文件)
│   ├── core/           # 核心业务逻辑 (120+文件)
│   │   ├── shortcut/   # 快捷方式子系统 (13文件)
│   │   ├── command/    # 命令子系统 (20文件)
│   │   ├── exec/       # 命令执行子系统 (13文件)
│   │   ├── plugin/     # 插件子系统 (15文件)
│   │   ├── preprocessing/ # 预处理子系统 (7文件)
│   │   ├── service/    # 系统服务 (~40文件)
│   │   └── security/   # 安全模块 (5文件)
│   ├── ui/             # 表现层 (130+文件)
│   │   ├── tray_mixins/ (8文件)
│   │   ├── launcherpopup/ (19文件)
│   │   ├── configwindow/ (60+文件 + pages/9文件)
│   │   ├── commandpanel/ (6文件)
│   │   ├── common/ (14文件)
│   │   ├── adapters/ (3文件)
│   │   ├── styles/ (21+文件)
│   │   ├── utils/ (17文件)
│   │   └── view_models/ (4文件)
│   ├── hooks/          # 全局钩子 (7文件)
│   ├── infrastructure/ # 基础设施 (8文件)
│   ├── services/       # 外部服务 (7文件)
│   ├── extensions/     # 扩展层 (5文件)
│   ├── modules/        # 模块层 (3文件)
│   └── platforms/      # 平台初始化 (1文件)
│
├── plugins/            # 内置插件
├── tests/              # GoogleTest + QtTest (~70文件)
│   ├── unit/
│   ├── integration/
│   ├── ui/
│   └── regression/
└── docs/
```

### 4.3 核心架构差异与转换规则

| Python 模式 | C++ 等价 | 注意事项 |
|---|---|---|
| 动态类型/鸭子类型 | 模板 / 纯虚接口 | 端口协议用 `class IXxx { virtual ~IXxx() = default; ... };` |
| `@dataclass` | `struct` + `NLOHMANN_DEFINE_TYPE_INTRUSIVE` | 自动生成 `to_json`/`from_json`；复杂字段手写 |
| `Optional[T]` | `std::optional<T>` | `std::nullopt` 对应 `None`；访问前判断 `has_value()` |
| `Union[T1, T2]` | `std::variant<T1, T2>` | `std::visit` 访问；`std::get_if<T>` 安全取值 |
| `@property` | `const` 成员函数 | `int width() const { return m_width; }` |
| `@contextmanager` | RAII 守卫类 | 构造获取资源，析构释放；`std::lock_guard` 是典型例子 |
| `NamedTuple` | `struct`（POD）| 加 `[[nodiscard]]` 强制检查返回值 |
| `TypeVar` / `Generic[T]` | `template<typename T>` | C++ 模板，编译期多态 |
| Mixin 多继承 | 虚继承 或 **组合优先** | 菱形继承需 `virtual` 基类；实际建议改为成员组合 |
| `Protocol` | 纯虚基类（接口）| `virtual Method() = 0;` + `virtual ~IXxx() = default;` |
| 单例 | Meyers 单例 / `std::call_once` | `static T& instance() { static T i; return i; }` |
| PyQt `pyqtSignal` | Qt6 `signals:` 标签 | ⚠ Qt6 中用 `signals:` 标签，不是 `Q_SIGNAL` 宏；`connect()` 语法不变 |
| 协程 / `async def` | `QtConcurrent::run()` + `QFuture` | 结果通过 `QFutureWatcher` + 信号回主线程 |
| 动态插件加载 | 进程外 `QProcess` + JSON-over-stdio | ⚠ builtin 插件仍为**进程内**加载（`importlib`等效为直接 include），不使用 `QLibrary`；第三方插件才走 QProcess 隔离 |
| `ctypes` / `pywin32` | 原生 Win32 API | `#include <windows.h>`；链接 `user32 kernel32 advapi32` |
| `dict` 动态配置 | `nlohmann::json` | 类型安全：`j.at("key").get<int>()`；字段缺失用 `.value("k", default)` |
| 异常 | C++ 异常 + `std::expected<T,E>`（C++23）| GUI 事件处理器顶层必须 catch-all；见 4.4.10 |
| GC / 引用计数 | RAII + 智能指针 | `QObject` 用 parent 树；跨模块共享用 `shared_ptr`；见 4.4.8 |
| `@lru_cache` | `std::unordered_map` + 自定义 LRU | 或 `cpp-lru-cache`；线程安全版需加 `std::mutex` |
| `threading.RLock` | `std::recursive_mutex` | ⚠ Qt6 已移除 `QMutex::Recursive`，改用 `QRecursiveMutex` |
| `threading.Event` | `std::condition_variable` + `std::atomic<bool>` | 或 `QWaitCondition` + `QMutex` |
| `time.monotonic()` | `std::chrono::steady_clock::now()` | `duration_cast<milliseconds>(t2-t1).count()` 取毫秒 |
| `uuid.uuid4()` | `QUuid::createUuid().toString(QUuid::WithoutBraces)` | 或 Win32 `UuidCreate` + `UuidToStringW` |
| `os.path` / `pathlib` | `std::filesystem::path`（C++17）| `fs::path`, `fs::exists()`, `fs::canonical()` |
| `json.dump` / `json.load` | `nlohmann::json` | `j.dump(2)` 格式化；`json::parse(str)` 解析 |
| `subprocess.run` | `QProcess` | `QProcess::execute()` 同步；`start()`+信号 异步 |
| `watchdog` | `ReadDirectoryChangesW` + 重叠 I/O | 或 `FindFirstChangeNotification`（简单场景）|
| `PIL` / `Pillow` | `QImage` + `stb_image_resize` | `QImage::save()`/`load()`；大图缩放用 stb |
| `pypinyin` | `cpp-pinyin` 库 | 或内置 ~250 字映射 + GB2312 区间首字母；见 2.2 |
| `secrets.token_urlsafe(n)` | `QRandomGenerator::global()->generate()` × N字节 → `QByteArray::toBase64(QByteArray::Base64UrlEncoding)` | IPC token 生成（`QCryptographicHash` 是哈希函数，不能用于随机生成）|
| `hashlib.md5(b).hexdigest()` | `QCryptographicHash(Algorithm::Md5)` | 图标去重 MD5，输出格式需与 Python 版一致（小写十六进制）|

### 4.4 关键设计决策与代码模板

#### 4.4.1 依赖注入

```cpp
// bootstrap/CompositionRoot.h
#pragma once
#include <memory>
#include "core/DataManager.h"
#include "core/command/CommandRegistry.h"
#include "core/plugin/PluginManager.h"
#include "application/state/StateStore.h"
#include "application/ports/IUiActions.h"

// 所有业务服务由 CompositionRoot 统一组装并持有生命周期
struct ApplicationServices {
    std::unique_ptr<DataManager>      dataManager;
    std::unique_ptr<CommandRegistry>  commandRegistry;
    std::unique_ptr<PluginManager>    pluginManager;
};

// AppContext 是顶层容器，通过引用/指针将服务分发给各模块
// （不按值拷贝 ApplicationServices，避免所有权混乱）
struct AppContext {
    ApplicationServices               services;   // 唯一所有者
    std::unique_ptr<StateStore>       stateStore;
    std::unique_ptr<IUiActions>       uiActions;  // 由 TrayApp 实现，bootstrap 注入
    HANDLE                            instanceMutex{nullptr};  // Win32 单实例互斥量
};

[[nodiscard]] AppContext buildAppContext();  // 工厂函数，仅在 main.cpp 中调用一次
```

#### 4.4.2 端口/适配器

```cpp
// application/ports/ISearchPort.h
#pragma once
#include <optional>
#include <vector>
#include <QString>
#include "domain/models.h"

class ISearchPort {
public:
    virtual ~ISearchPort() = default;

    [[nodiscard]] virtual std::vector<FuzzyMatchResult> match(
        const std::vector<Folder>& pages,
        const QString& query,
        const QString& sortMode = QStringLiteral("smart"),  // ⚠ QStringLiteral，不用裸字符串
        int limit = 50) = 0;

    [[nodiscard]] virtual std::optional<WebSearchAction>
        resolveSearchUrl(const QString& query) = 0;

    [[nodiscard]] virtual std::vector<SlashCommand>
        findSlashCommands(const QString& query) = 0;
};

// application/ports/IConfigRepository.h
#pragma once
#include <expected>    // C++23
#include <QString>
#include <nlohmann/json.hpp>

class IConfigRepository {
public:
    virtual ~IConfigRepository() = default;

    // 返回 expected：读取失败时携带错误消息，不依赖异常
    [[nodiscard]] virtual std::expected<nlohmann::json, QString> load() = 0;

    // 返回新 revision；expectedRevision 不符时抛 RevisionConflict
    [[nodiscard]] virtual int save(
        const nlohmann::json& data, int expectedRevision) = 0;
};
```

#### 4.4.3 事件总线

```cpp
// application/events/EventBus.h
#pragma once
#include <any>
#include <functional>
#include <mutex>
#include <typeindex>
#include <unordered_map>
#include <vector>

/**
 * @brief 线程安全的类型安全事件总线（同步发布）。
 *
 * 使用说明：
 *   auto token = bus.subscribe<ConfigSaved>([](const ConfigSaved& e){ ... });
 *   // token 析构时自动取消订阅
 */
class EventBus {
public:
    // 订阅令牌：析构时自动 unsubscribe，防止悬空回调
    class Token {
    public:
        Token() = default;
        Token(const Token&) = delete;
        Token& operator=(const Token&) = delete;
        Token(Token&&) noexcept = default;
        Token& operator=(Token&&) noexcept = default;
        ~Token() { if (m_unsub) m_unsub(); }
    private:
        friend class EventBus;
        explicit Token(std::function<void()> unsub) : m_unsub(std::move(unsub)) {}
        std::function<void()> m_unsub;
    };

    template<typename T>
    [[nodiscard]] Token subscribe(std::function<void(const T&)> listener) {
        const auto id = m_nextId++;
        {
            std::lock_guard lock(m_mutex);
            m_listeners[typeid(T)].push_back({id,
                [l = std::move(listener)](const std::any& e) {
                    l(std::any_cast<const T&>(e));
                }});
        }
        return Token([this, id, ti = std::type_index(typeid(T))] {
            std::lock_guard lock(m_mutex);
            auto& vec = m_listeners[ti];
            vec.erase(std::remove_if(vec.begin(), vec.end(),
                [id](const Entry& e) { return e.id == id; }), vec.end());
        });
    }

    template<typename T>
    void publish(const T& event) {
        // 持有锁期间只复制 listener 列表，避免回调内再次 publish 或 subscribe 时死锁
        std::vector<std::function<void(const std::any&)>> snapshot;
        {
            std::lock_guard lock(m_mutex);
            auto it = m_listeners.find(typeid(T));
            if (it == m_listeners.end()) return;
            snapshot.reserve(it->second.size());
            for (auto& e : it->second) snapshot.push_back(e.fn);
        }
        const std::any wrapped{event};
        for (auto& fn : snapshot) {
            try { fn(wrapped); } catch (...) { /* 记录并抑制，单个监听器异常不影响其他 */ }
        }
    }

private:
    struct Entry { uint64_t id; std::function<void(const std::any&)> fn; };
    std::mutex m_mutex;
    std::unordered_map<std::type_index, std::vector<Entry>> m_listeners;
    std::atomic<uint64_t> m_nextId{0};
};

inline EventBus g_eventBus;  // 全局单例（或通过 AppContext 注入）
```

> **关键修正**：
> - `subscribe()` 返回 `Token`（RAII），析构时自动 unsubscribe，消除悬空回调
> - `publish()` 先复制 listener 快照再释放锁，回调内可安全再次 `publish`/`subscribe`
> - `m_nextId` 用 `std::atomic` 保证 ID 生成的线程安全

#### 4.4.4 StateStore

```cpp
// application/state/StateStore.h
#pragma once
#include <functional>
#include <shared_mutex>
#include <stdexcept>
#include <nlohmann/json.hpp>

struct RevisionConflict : std::runtime_error {
    int actual, expected;
    RevisionConflict(int a, int e)
        : std::runtime_error("revision conflict"), actual(a), expected(e) {}
};

class StateStore {
public:
    struct Snapshot {
        int revision;
        nlohmann::json state;  // 深拷贝，外部可安全修改
    };

    [[nodiscard]] Snapshot snapshot() const {
        std::shared_lock lock(m_mutex);
        return {m_revision, m_state};
    }

    /**
     * @brief 乐观并发提交：先计算新状态（锁外），再原子替换（锁内）。
     * @throws RevisionConflict 若 expectedRevision 与当前 revision 不符
     */
    [[nodiscard]] Snapshot submit(
        std::function<nlohmann::json(const nlohmann::json&)> command,
        int expectedRevision)
    {
        // 1. 在锁外计算新状态（command 可能耗时，且抛出异常不会污染状态）
        nlohmann::json currentCopy;
        {
            std::shared_lock rlock(m_mutex);
            if (m_revision != expectedRevision)
                throw RevisionConflict(m_revision, expectedRevision);
            currentCopy = m_state;  // 深拷贝供 command 使用
        }
        auto newState = command(currentCopy);  // 可能抛出，此时 m_state 未被修改

        // 2. 再次获写锁提交（需二次检查 revision，防止并发修改）
        std::unique_lock wlock(m_mutex);
        if (m_revision != expectedRevision)
            throw RevisionConflict(m_revision, expectedRevision);
        m_state = std::move(newState);
        ++m_revision;
        return {m_revision, m_state};
    }

    /** @brief 整体替换状态（用于加载/重置场景）。 */
    void replace(nlohmann::json newState, int expectedRevision) {
        std::unique_lock lock(m_mutex);
        if (m_revision != expectedRevision)
            throw RevisionConflict(m_revision, expectedRevision);
        m_state = std::move(newState);
        ++m_revision;
    }

private:
    mutable std::shared_mutex m_mutex;
    nlohmann::json m_state;
    int m_revision{0};
};
```

> **关键修正**：`command(currentCopy)` 在锁外执行，异常时 `m_state` 不受影响（强异常保证）。写锁提交前二次检验 revision，避免并发窗口导致的丢失更新。

#### 4.4.5 领域模型 (C++ 版)

```cpp
// domain/models.h
#pragma once
#include <optional>
#include <QString>
#include <QStringList>
#include <QUuid>
#include <nlohmann/json.hpp>

enum class ShortcutType { File, Folder, Url, Hotkey, Command, BatchLaunch, Macro };

struct ShortcutItem {
    // ── 基础字段 ──────────────────────────────────────────
    QString      id      = QUuid::createUuid().toString(QUuid::WithoutBraces);
    QString      name;
    ShortcutType type    = ShortcutType::File;
    int          order   = 0;
    bool         enabled = true;
    QStringList  tags;
    double       lastUsedAt = 0.0;
    int          useCount   = 0;
    std::optional<int> smartOrder;

    // ── 文件 / 文件夹 ─────────────────────────────────────
    QString targetPath, targetArgs, workingDir;

    // ── 热键 ─────────────────────────────────────────────
    QString     hotkey;
    QStringList hotkeyModifiers, hotkeyKeys;

    // ── URL ──────────────────────────────────────────────
    QString url, preferredBrowserPath, preferredBrowserArgs;

    // ── 命令 ─────────────────────────────────────────────
    QString command;
    QString commandType             = QStringLiteral("cmd");
    bool    showWindow              = false;
    bool    commandVariablesEnabled = false;
    bool    captureOutput           = false;
    double  commandTimeoutSeconds   = 300.0;
    int     commandOutputMaxChars   = 2000;
    QString commandPanelSize        = QStringLiteral("medium");
    nlohmann::json commandParams    = nlohmann::json::array();
    nlohmann::json commandEnv       = nlohmann::json::object();
    QString commandEncoding         = QStringLiteral("auto");

    // ── 批量启动 ─────────────────────────────────────────
    QString moduleId, moduleVersion;
    std::vector<nlohmann::json> batchLaunchSteps;

    // ── 宏录制 ───────────────────────────────────────────
    bool           rawMode              = false;
    nlohmann::json macroEvents          = nlohmann::json::array();
    double         macroSpeed           = 1.0;
    bool           macroHideWhileRecording = false;

    // ── 触发 / 图标 / 权限 ────────────────────────────────
    QString triggerMode             = QStringLiteral("immediate");
    QString iconPath, iconData;
    bool    iconInvertLight         = false;
    bool    iconInvertDark          = false;
    bool    iconInvertWithTheme     = false;
    bool    iconInvertCurrent       = false;
    QString iconInvertThemeWhenSet;
    QString alias;
    bool    runAsAdmin              = false;

    // ── 序列化 ───────────────────────────────────────────
    [[nodiscard]] nlohmann::json toJson() const;
    [[nodiscard]] static ShortcutItem fromJson(const nlohmann::json& j);

    // timestamp = 0.0 时自动取 QDateTime::currentSecsSinceEpoch()
    void markUsed(double timestamp = 0.0);
};
```

#### 4.4.6 快捷方式执行器 (策略模式)

```cpp
// core/shortcut/IExecutionStrategy.h
#pragma once
#include <QString>
#include "domain/models.h"
#include "application/execution/contracts.h"  // ExecutionResult

class IExecutionStrategy {
public:
    virtual ~IExecutionStrategy() = default;
    [[nodiscard]] virtual ExecutionResult execute(const ShortcutItem& item) = 0;
    // 带文件列表的执行（拖放场景）；默认实现调用 execute(item)
    [[nodiscard]] virtual ExecutionResult executeWithFiles(
        const ShortcutItem& item, const QStringList& files)
    { Q_UNUSED(files); return execute(item); }
};

// core/shortcut/ShortcutExecutor.h
#pragma once
#include "IExecutionStrategy.h"

class ShortcutExecutor {
public:
    explicit ShortcutExecutor(/* 注入各策略 */);

    [[nodiscard]] ExecutionResult execute(
        const ShortcutItem& item, bool forceNew = false);

    // Python 版 execute_with_files() 的对应
    [[nodiscard]] ExecutionResult executeWithFiles(
        const ShortcutItem& item, const QStringList& files);

private:
    IExecutionStrategy& strategyFor(ShortcutType type);

    std::unique_ptr<IExecutionStrategy> m_fileExec;
    std::unique_ptr<IExecutionStrategy> m_urlExec;
    std::unique_ptr<IExecutionStrategy> m_hotkeyExec;
    std::unique_ptr<IExecutionStrategy> m_cmdExec;
    std::unique_ptr<IExecutionStrategy> m_batchExec;
    std::unique_ptr<IExecutionStrategy> m_macroExec;
};

// ShortcutExecutor.cpp
ExecutionResult ShortcutExecutor::execute(const ShortcutItem& item, bool /*forceNew*/) {
    return strategyFor(item.type).execute(item);
}
ExecutionResult ShortcutExecutor::executeWithFiles(
    const ShortcutItem& item, const QStringList& files)
{
    return strategyFor(item.type).executeWithFiles(item, files);
}
IExecutionStrategy& ShortcutExecutor::strategyFor(ShortcutType type) {
    switch (type) {
        case ShortcutType::Hotkey:     return *m_hotkeyExec;
        case ShortcutType::Url:        return *m_urlExec;
        case ShortcutType::Command:    return *m_cmdExec;
        case ShortcutType::BatchLaunch:return *m_batchExec;
        case ShortcutType::Macro:      return *m_macroExec;
        default:                       return *m_fileExec;
    }
}
```

#### 4.4.7 Hooks DLL 直接集成

```cpp
// hooks/MouseHook.h — 可直接复用现有 hooks_dll/hooks.cpp
// 只需将 ctypes 调用替换为直接 C++ 函数调用
class MouseHook {
public:
    bool install(std::function<void(int,int)> callback);
    void uninstall();
    bool isPaused() const;
    void setPaused(bool paused);
private:
    HHOOK m_hook = nullptr;
    static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam);
};

// 或直接使用现有 hooks_dll/ 作为 CMake 子目标:
// add_subdirectory(hooks_dll)
// target_link_libraries(quicklauncher PRIVATE hooks_dll)
```

---

### 4.4.8 内存管理策略

C++ 无 GC，需在项目中统一所有权语义，避免泄漏与悬空指针。

| 场景 | 策略 | 理由 |
|---|---|---|
| 业务对象（非 QObject）独占所有权 | `std::unique_ptr<T>` | 零开销，RAII 自动释放 |
| 跨模块共享生命周期 | `std::shared_ptr<T>` | 引用计数；避免循环引用（用 `weak_ptr` 打破） |
| QObject 子对象 | Qt parent 机制（`new Foo(parent)`）| Qt 对象树统一管理，勿混用智能指针 |
| 顶层 QObject（无 parent）| `std::unique_ptr<QObject>` | 明确所有权，析构时调用 `deleteLater` 替代直接 delete |
| 临时借用（不持有） | 裸指针 `T*` 或 `std::span<T>` | 明确语义：观察者不拥有对象 |
| 跨线程共享 | `std::shared_ptr` + `std::atomic` 读写 | `QObject` 不可跨线程直接访问 |

```cpp
// ✅ 正确：业务服务的生命周期由 AppContext 管理
struct AppContext {
    std::unique_ptr<DataManager>    dataManager;
    std::unique_ptr<CommandRegistry> commandRegistry;
    std::unique_ptr<PluginManager>  pluginManager;
};

// ✅ 正确：Qt 子窗口用 parent 管理
auto* btn = new QPushButton(QStringLiteral("确定"), this);  // this 是 parent

// ❌ 错误：QObject 用 unique_ptr 且有 parent，会双重释放
auto btn = std::make_unique<QPushButton>(this);  // 勿用！parent 会再 delete
```

**内存压力监控**：重构保留 `MemoryGuard`（对应 Python 版），120 s 周期检查 `GetProcessMemoryInfo`，超过 `kCriticalMemoryMb = 200` MB 时触发 Qt 内部缓存清理 + 告警日志。

---

### 4.4.9 线程模型

整个程序的线程职责严格分层，禁止随意跨层调用。

```
┌─────────────────────────────────────────────────────────────┐
│  主线程（Qt GUI 线程）                                        │
│  • 所有 QWidget / QObject 访问                               │
│  • 事件循环 QApplication::exec()                             │
│  • 钩子回调通过信号跨线程回主线程                             │
├─────────────────────────────────────────────────────────────┤
│  工作线程（QThreadPool / std::jthread）                       │
│  • 模糊搜索、插件搜索源（并发，cancel_token 控制）            │
│  • 图标提取（IconExtractor，LRU 缓存线程安全保护）            │
│  • 玻璃背景捕获（GlassBackground，20 FPS 独立线程）           │
│  • 配置防抖保存（SaveCoordinator，QTimer → 工作线程写文件）   │
├─────────────────────────────────────────────────────────────┤
│  插件进程（QProcess + JSON-over-stdio）                       │
│  • 每个第三方插件运行在独立进程                               │
│  • 主进程通过 QProcess::readyRead 信号异步接收结果            │
└─────────────────────────────────────────────────────────────┘
```

**跨线程通信规则**：

```cpp
// ✅ 工作线程 → 主线程：通过 Qt 信号（Qt::QueuedConnection，默认）
connect(worker, &SearchWorker::resultsReady,
        this,   &PopupWindow::onSearchResults);  // 自动队列化

// ✅ 工作线程 → 主线程：通过 QMetaObject::invokeMethod
QMetaObject::invokeMethod(this, [this, result]() {
    updateUi(result);  // 在主线程执行
}, Qt::QueuedConnection);

// ❌ 禁止：工作线程直接修改 QWidget
label->setText("done");  // 未定义行为！
```

**取消机制**：长时任务（搜索、插件查询）通过 `std::atomic<bool> cancelled` 协作取消，不使用 `QThread::terminate()`（不安全）。

---

### 4.4.10 错误处理策略

项目采用**分层错误处理**：底层使用异常，UI 层捕获并转为用户友好提示。

```cpp
// application/errors/ApplicationError.h
#pragma once
#include <stdexcept>
#include <string>

struct ApplicationError : std::runtime_error {
    explicit ApplicationError(std::string msg) : std::runtime_error(std::move(msg)) {}
};
struct DomainError        : ApplicationError { using ApplicationError::ApplicationError; };
struct ValidationError    : ApplicationError { using ApplicationError::ApplicationError; };
struct InfrastructureError: ApplicationError { using ApplicationError::ApplicationError; };
struct UserCancelled      : ApplicationError { using ApplicationError::ApplicationError; };
struct OperationTimeout   : ApplicationError { using ApplicationError::ApplicationError; };
struct SecurityViolation  : ApplicationError { using ApplicationError::ApplicationError; };
```

**分层捕获策略**：

| 层级 | 行为 |
|---|---|
| `domain/` | 不抛异常；用返回值（`std::optional`, `std::expected`）表达失败 |
| `core/` | 抛 `ApplicationError` 子类；内部异常在同层记录+重抛或转换 |
| `infrastructure/` | OS/IO 异常包装为 `InfrastructureError` 后向上传递 |
| `ui/` 事件处理器 | **必须** catch-all，失败展示 toast/对话框，不允许异常逃逸 GUI 事件循环 |
| `main()` | 全局 catch-all + `SetUnhandledExceptionFilter` 捕获未处理崩溃，写崩溃日志后退出 |

```cpp
// C++23 std::expected（推荐用于无需栈展开的路径）
[[nodiscard]] std::expected<ShortcutItem, QString>
ShortcutService::findById(const QString& id) const noexcept {
    if (id.isEmpty()) return std::unexpected(QStringLiteral("id 不能为空"));
    auto it = m_index.find(id);
    if (it == m_index.end()) return std::unexpected(QStringLiteral("快捷方式不存在"));
    return it->second;
}

// UI 层捕获
void PopupWindow::onItemClicked(const QString& id) {
    try {
        auto result = m_executor->execute(id);
        if (!result.success) showToast(result.message);
    } catch (const SecurityViolation& e) {
        showWarningDialog(tr("安全限制"), QString::fromStdString(e.what()));
    } catch (const ApplicationError& e) {
        showToast(QString::fromStdString(e.what()));
    } catch (...) {
        spdlog::error("未处理异常于 onItemClicked");
    }
}
```

### 4.5 分功能重构实施指南

#### 功能 1: 项目骨架与构建系统

**目标**: CMake + vcpkg 项目搭建, 编译通过空壳应用

**对应Python文件**: 无直接对应, 基础设施

**实施步骤:**
1. 创建根 `CMakeLists.txt`：C++23，Qt6（Core/Gui/Widgets/Network/Svg/Concurrent），nlohmann_json，spdlog（见7.3完整示例）
2. 创建 `vcpkg.json`：`nlohmann-json`, `spdlog`, `zlib`, `minizip-ng`, `gtest`（⚠ Qt6 通过 Qt Installer 安装，**不经过** vcpkg；见 7.4/7.5）
3. 配置 `cmake/CompilerSettings.cmake`：MSVC `/W4 /WX /utf-8 /std:c++20`；Clang `-Wall -Wextra`
4. 创建 `CMakePresets.json`（见 7.5.3 完整示例）
5. 创建所有 `src/*/CMakeLists.txt` 子目标（每层一个 `add_library(ql_xxx STATIC ...)`）
6. 创建 `src/main.cpp`：仅 `QApplication app(argc, argv); return app.exec();`
7. **验证**：`cmake --preset windows-debug && cmake --build build/debug` 编译通过，空应用窗口启动

#### 功能 2: 领域模型与序列化

**目标**: 所有领域模型 C++ 实现, JSON 序列化与 Python 版完全兼容

**对应Python文件**: `domain/models.py`, `domain/clipboard.py`, `core/data_models.py`

**实施步骤:**
1. 实现 `ShortcutType` 枚举 (8值)
2. 实现 `ShortcutItem` 结构 (46字段) + `to_json/from_json` (含完整字段验证)
3. 实现 `Folder` 结构 (10字段) + 序列化
4. 实现 `AppSettings` 结构 (88字段) + 序列化 (含 clamp/normalize)
5. 实现 `AppData` 根容器 + 默认文件夹创建
6. 实现剪贴板值对象: `ClipboardFormatInfo`, `ClipboardSnapshot`, `ClipboardClassification`
7. 实现归一化函数: `normalize_command_timeout_seconds`, `normalize_command_output_max_chars` 等
8. **验证**: 用 Python 版 `tests/fixtures/config/1.6-normal.json` 加载测试, 确保字段完全匹配

#### 功能 3: 端口接口定义

**目标**: 所有端口协议纯虚接口

**对应Python文件**: `application/ports/*.py`, `application/execution/contracts.py`, `application/errors.py`

**实施步骤:**
1. 定义 `IConfigRepository`, `IBackupStore`, `IHistoryStore`, `ISaveScheduler`, `IClock`, `IConfigStatePort`
2. 定义 `IGlobalHotkeyPort`, `IWindowPort`, `IIconProvider`, `IAutoStartPort`
3. 定义 `ISearchPort` + `WebSearchAction`
4. 定义 `IShellOpenerPort`
5. 定义 `UIAction` 枚举 + `IUiActions`
6. 实现错误层次: `ApplicationError → DomainError/ValidationError/InfrastructureError/UserCancelled/OperationTimeout/SecurityViolation/RevisionConflict`
7. 实现执行契约: `ExecutionPolicy`, `CancellationToken`, `ExecutionRequest`, `ExecutionResult`, `ExecutionErrorCode`

#### 功能 4: 事件总线与状态存储

**目标**: EventBus + StateStore 实现

**对应Python文件**: `application/events.py`, `application/state/store.py`

**实施步骤:**
1. 实现 `Event` 基类（含 `std::chrono::steady_clock` 时间戳）
2. 实现 `EventBus`：`subscribe()`（返回 RAII `Token`，析构自动注销）/ `publish()`（复制快照后释放锁，避免回调中死锁）；见 4.4.3 代码模板
3. 实现内置事件：`ConfigSaved`, `ConfigLoaded`, `ShortcutExecuted`
4. 实现 `AppSnapshot`（frozen struct，`const` 成员）
5. 实现 `StateStore`：`snapshot()`/`submit()`/`replace()`，`std::shared_mutex` 读写锁，乐观修订检查，强异常保证；见 4.4.4 代码模板
6. **验证**：并发读写压力测试，`RevisionConflict` 测试，publish 回调内 subscribe/publish 的死锁测试

#### 功能 5: 启动编排 (Bootstrap)

**目标**: DPI设置 → COM初始化 → 日志 → 单实例IPC → 托盘应用

**对应Python文件**: `bootstrap/*.py` (14文件)

**实施步骤:**
1. `DpiSetup`: `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` + SHCore 回退
2. `LoggingInit`: spdlog 初始化 + RotatingFileSink + `SetUnhandledExceptionFilter` 崩溃处理
3. `IpcServer`: `QLocalServer` + token 鉴权（`QRandomGenerator::global()->generate()` × 32字节 → base64url，等效 `secrets.token_urlsafe(32)`）
4. `acquireInstanceMutex`: `CreateMutexW` 单实例
5. `RunModeRouter`: `QCommandLineParser` 解析 → 分派到对应 handler
6. `ProcessHandlers`: smoke-test/file-dialog/plugin-worker 等非GUI模式
7. `CompositionRoot`: 组装 `ApplicationServices` + `AppContext`
8. `LifecycleManager`: 逆序释放资源 (executors → mutex → IPC → tray)
9. `StartupTasks`: 清理命令缓存/同步自启动/合并特殊应用
10. **验证**: 单实例互斥测试, IPC token 验证测试

#### 功能 6: 数据持久化

**目标**: JSON 配置文件读写, 原子保存, 备份恢复

**对应Python文件**: `core/config_services.py`, `core/save_coordinator.py`, `core/data_loader.py`, `core/backup_service.py`, `core/config_validation.py`, `core/config_history.py`, `core/config_recovery.py`, `core/config_repairs.py`, `core/config_migrator.py`, `core/config_importer.py`, `infrastructure/persistence/adapters.py`

**实施步骤:**
1. `ConfigDataStore`: JSON 序列化/反序列化, 原子文件替换 (`QSaveFile` 或 `MoveFileEx`)
2. `SaveCoordinator`: 防抖保存 (QTimer 500ms), 批量更新上下文管理器, 锁分离 (save_lock + write_lock)
3. `ConfigBackupService`: 时间戳自动备份, 保留策略
4. `ConfigRecoveryService`: 隔离区 + 恢复报告
5. `ConfigValidation`: 30+ 整数范围 clamp, 枚举白名单, Schema 验证
6. `ConfigHistoryManager`: gzip 压缩快照 (QByteArray + qCompress), 保留20个
7. `BackupService`: .qlzip 备份/恢复/导出/导入 (事务性)
8. `ConfigMigrator`: APPDATA → 安装目录迁移
9. `DataLoader`: 加载/重载/出厂重置
10. 持久化适配器实现
11. **验证**: 用 Python 版 data.json 加载测试, 备份恢复循环测试

#### 功能 7: 命令注册与内置命令

**目标**: CommandRegistry + 33+ 内置命令

**对应Python文件**: `core/command_registry.py`, `core/builtin_commands.py`, `core/builtin_command_catalog.py`, `core/commands_*.py` (11文件), `core/slash_commands.py`, `core/search_engines.py`

**实施步骤:**
1. 实现数据结构: `CommandParam`, `CommandAction`, `CommandContext`, `CommandResult`, `CommandDefinition`
2. 实现 `CommandRegistry`: register/get/find/list/remove, 三级搜索排序
3. 实现搜索源系统: register_search_source, execute_search_sources (线程池 + 超时)
4. 实现 `~140` 个别名映射 (`BUILTIN_COMMAND_ALIASES`)
5. 实现 11 个命令文件的所有处理器:
   - `CommandsClipboard`: 剪贴板操作
   - `CommandsEncoding`: Base64/URL/HTML 编码 (OpenSSL/QUrl)
   - `CommandsGit`: Git 快捷操作 (QProcess)
   - `CommandsNetwork`: WiFi/DNS/CIDR/TLS/端口 (QtNetwork + Win32)
   - `CommandsText`: JSON/JWT/Hash/字数统计
   - `CommandsSystem`: 系统信息/环境变量
   - `CommandsWindows`: 注册表/服务/任务计划
   - `CommandsPlugins`: 插件管理
   - `CommandsMaintenance`: 诊断/健康/缓存
   - `CommandsUtils`: UUID/时间戳/正则
6. 实现 27 个斜杠命令
7. 实现 4 个搜索引擎解析
8. **验证**: 命令注册测试, 搜索匹配测试, 每个命令处理器单元测试

#### 功能 8: 模糊搜索引擎

**目标**: 完整还原6层评分算法

**对应Python文件**: `core/fuzzy_search.py`, `core/pinyin_search.py`, `core/search_history.py`

**实施步骤:**
1. 实现文本归一化: NFKC (QString::normalized), casefold (toLower), compact/word/token
2. 实现 LRU 缓存 (自定义或 cpp-lru-cache)
3. 实现字段变体生成 (6个搜索面)
4. 实现字段权重表 (7个字段)
5. 实现单项评分: 10种匹配类型 + 词边界加分
6. 实现多项评分: 全项匹配要求 + 短语加分 + 多项加分
7. 实现使用加分: use_count + 时间衰减 (半衰期3天)
8. 实现拼音搜索: cpp-pinyin 库 或 自建 ~250 字映射 + GB2312 首字母
9. 实现搜索历史积分
10. **验证**: 用 Python 版测试数据验证评分一致性 (允许浮点误差)

#### 功能 9: 快捷方式 CRUD 与执行

**目标**: ShortcutService + ShortcutExecutor + 所有执行器

**对应Python文件**: `core/shortcut_service.py`, `core/shortcut_executor.py`, `core/shortcut_*.py` (10文件), `core/batch_launch_exec.py`

**实施步骤:**
1. `ShortcutService`: find/add/update/delete/reorder/move + 批量操作 + 智能排序
2. `FileExecutionStrategy`: `ShellExecuteExW` + 管理员提权 + 文件关联
3. `UrlExecutionStrategy`: 浏览器打开 + 首选浏览器 + URL延迟检测
4. `HotkeyExecutionStrategy`: 通过 Hooks DLL 发送按键序列
5. `CommandExecutionStrategy`: 命令执行服务 (cmd/powershell/python/bash/builtin)
6. `BatchLaunchStrategy`: 批量启动 + 延迟
7. `MacroExecutionStrategy`: InputMacroBackend.play
9. `WindowControlMixin`: 窗口激活/查找
10. 前台窗口管理: 保存/恢复 HWND
11. **验证**: 每种类型的执行测试, 批量操作测试

#### 功能 10: 命令执行子系统

**目标**: 完整的命令执行管线

**对应Python文件**: `core/command_exec/*.py` (11文件), `core/command_execution_service.py`, `core/command_io.py`, `core/command_results.py`, `core/command_result_actions.py`, `core/command_variables.py`

**实施步骤:**
1. `ProcessRunner`: QProcess 封装 (cmd/powershell/python/bash 4种 shell)
2. `OutputCapture`: stdout/stderr 分离, 编码检测 (auto/utf-8/gbk/mbcs)
3. `Preflight`: 路径存在检查/权限验证/参数验证
4. `Audit`: 命令/参数/结果记录
5. `Profiles`: 窗口尺寸/编码/环境变量配置
6. `Cleanup`: 临时文件/进程句柄清理
7. `CommandVariables`: `{{clipboard}}`, `{{selected_text}}`, `{{selected_file}}` 等变量替换
8. `CommandResults`: 结果格式化/截断/动作
9. **验证**: 各 shell 类型执行测试, 超时测试, 输出捕获测试

#### 功能 11: 插件系统

**目标**: 插件扫描/加载/隔离/生命周期管理

**对应Python文件**: `core/plugin/*.py` (16文件), `core/plugin_manager.py`

**实施步骤:**
1. `PluginModels`: `PluginInfo`, `PluginManifest`
2. `PluginManifest`: JSON 清单解析 + 验证
3. `PluginInstaller`: ZIP 包安装 (路径遍历检查 + 大小限制)
4. `PluginHostAPI`: 暴露给插件的安全 API
5. `PluginIsolatedRuntime`: QProcess 进程隔离 + JSON-over-stdio
6. `PluginWorkerSupervisor`: 心跳/重启
7. `PluginRestrictedModule`: 沙箱限制 (C++ 中通过进程隔离实现)
8. `PluginStateStore`: 状态持久化
9. `PluginManager`: 扫描/加载/启用/禁用/隔离区 + 失败跟踪 + 自动隔离
10. 信任验证: SHA-256 校验 + 来源验证
11. **验证**: 插件加载测试, 隔离测试, 失败跟踪测试

#### 功能 13: 预处理管道

**目标**: 命令输入预处理管线

**对应Python文件**: `core/preprocessing/*.py` (9文件)

**实施步骤:**
1. `Pipeline`: 变量解析 → 安全检查 → 审计
2. `SecurityCheck`: 命令注入模式检测 (危险命令/管道/重定向)
3. `Sanitizers`: HTML/路径/命令字符清理
4. `Validators`: 长度/格式/范围验证
5. `RateLimiter`: 令牌桶算法
6. `AuditLogger`: 预处理审计日志
7. **验证**: 注入防护测试, 速率限制测试

#### 功能 14: 系统服务

**目标**: 所有系统级服务

**对应Python文件**: `core/` 下的 ~40 个服务文件

**实施步骤:**
1. `WindowManager` + `WindowDetection`: FindWindowW/EnumWindows/SetForegroundWindow
2. `AutoStartManager`: Task Scheduler COM + Helper 进程提权 + Token 复制
3. `IconExtractor`: SHGetFileInfoW/ExtractIconEx + Qt QIcon + 默认图标生成
4. `IconRepository`: 图标缓存管理 (MD5去重/孤立清理/大小限制)
5. `ClipboardService`: Win32剪贴板 (8步退避重试) + Qt剪贴板 + 快照/恢复
6. `ClipboardClassifiers`: 内容分类 (文本/图片/文件/颜色/URL等)
7. `FolderService`: 文件夹 CRUD
8. `FolderScanner`: 文件夹扫描快捷方式
9. `FolderSync`: 链接文件夹同步
10. `FolderWatcher`: `ReadDirectoryChangesW` 文件监控
11. `SettingsService`: 设置项读写 + 变更通知
12. `I18nService`: 国际化翻译 (zh_CN/en)
13. `PinyinSearch`: 拼音搜索
14. `SelectedTextService`: 选中文本获取 (COM/剪贴板)
15. `EventLog`: events.jsonl 事件日志
16. `Diagnostics`: 系统诊断工具
17. `ErrorHandler`: 全局错误处理
18. `MemoryGuard`: 内存压力监控 (GetProcessMemoryInfo)
19. `ExecutorManager`: 线程池管理 (QThreadPool)
20. `BackgroundTasks`: 后台任务调度
21. `FaviconCache`: 网站图标缓存
22. `SearchHistory`: 搜索历史积分
23. `ConflictCheckers`: 热键/触发/统一冲突检测
24. `TriggerConfig`: 触发配置标准化
25. `PrivilegeLaunchChannel`: 管理员提权通道
26. **验证**: 每个服务的单元测试

#### 功能 15: 安全模块

**目标**: 所有安全子系统

**对应Python文件**: `core/path_security.py`, `core/import_security.py`, `core/network_security.py`, `core/command_action_safety.py`, `core/command_param_validation.py`, `core/command_risk.py`

**实施步骤:**
1. `PathSecurity`: 路径规范化 + 边界检查 (防 `../` 遍历)
2. `ImportSecurity`: ZIP 路径遍历防护 + 解压大小限制 + 符号链接检查
3. `NetworkSecurity`: SSRF防护 (内网IP检测: 10.x/172.16-31.x/192.168.x/127.x/169.254.x) + 代理检测
4. `CommandActionSafety`: 危险模式检测 (rm/del/format/shutdown等)
5. `CommandParamValidation`: 参数类型/范围/格式验证
6. `CommandRisk`: 风险评分 (0-100)
7. **验证**: 路径遍历测试, SSRF测试, 危险命令测试

#### 功能 16: Hooks DLL 集成

**目标**: 直接集成现有 C++ 钩子 DLL

**对应Python文件**: `hooks/*.py` (8文件), `hooks_dll/*.cpp`

**实施步骤:**
1. 将 `hooks_dll/` 作为 CMake 子项目, 编译为静态库或 DLL
2. 实现 `MouseHook`: `SetWindowsHookEx(WH_MOUSE_LL)` (或复用 hooks.dll)
3. 实现 `KeyboardHook`: `SetWindowsHookEx(WH_KEYBOARD_LL)`
4. 实现 `HotkeyManager`: 热键规范化 + 注册/注销 + 15ms防抖
5. 实现 `InputMacroBackend`: 录制/回放 (deque 100K事件上限)
6. 实现 `KeyMap`: 虚拟键码 → 字符串映射
7. 实现 `HookPause`: 暂停/恢复
8. 实现触发配置: `SetTriggerConfig`/`SetTriggerConfigEx`
9. 实现宏回放: `PlayMacroEvents` + DPI感知坐标重映射
10. **验证**: 钩子安装/卸载测试, 热键注册测试, 宏录制回放测试

#### 功能 17: 基础设施适配器

**目标**: 所有端口实现

**对应Python文件**: `infrastructure/*.py` (10文件)

**实施步骤:**
1. `JsonConfigRepo`: nlohmann::json 读写 + 原子替换
2. `ProcessRuntime`: QProcess 子进程工具
3. `ShellOpener`: ShellExecuteExW + CreateProcessW + DETACHED_PROCESS
4. `SystemClock`: std::chrono 封装
5. `GlobalHotkeyAdapter`: RegisterHotKey/UnregisterHotKey
6. `IconProviderAdapter`: 图标提取桥接
7. `AutoStartHelper`: 自启动辅助
8. `Win32Adapters`: 窗口/进程/系统信息
9. **验证**: 适配器集成测试

#### 功能 18: 托盘应用 + Mixin

**目标**: 系统托盘 + 右键菜单 + 启动编排

**对应Python文件**: `ui/tray_app.py`, `ui/tray_controllers.py`, `ui/tray_workers.py`, `ui/tray_mixins/*.py`

**实施步骤:**
1. `TrayApp(QSystemTrayIcon)`: 9个mixin组合
2. `TrayAppMenuMixin`: 右键菜单构建 (显示弹窗/配置/关于/日志/退出)
3. `HooksMixin`: 鼠标/键盘钩子安装/卸载/健康检查
4. `PopupMixin`: 弹窗显示/隐藏/焦点管理
5. `MenuMixin`: 系统菜单项
6. `ShutdownMixin`: 优雅关闭 + atexit
7. `SleepMixin`: 空闲检测 + 睡眠模式
8. `StartupMixin`: 延迟启动任务 (QTimer)
9. `UpdateMixin`: 自动更新检查/下载/安装
10. `WindowsMixin`: Win32窗口管理
11. `TrayControllers`: 数据/导入/全屏/热键加载控制器
12. `TrayWorkers`: 图标缓存清理线程
13. 快照式设置同步: diff dict/tuple 快照
14. **验证**: 托盘图标显示, 菜单交互, 钩子安装

#### 功能 19: 弹窗启动器

**目标**: 完整弹窗体验 (搜索/网格/Dock/玻璃效果)

**对应Python文件**: `ui/launcher_popup/*.py` (20文件)

**实施步骤:**
1. `PopupWindow(QWidget)`: 16个mixin, Qt::Tool + FramelessWindowHint
2. `PopupWindowLifecycle`: 显示/隐藏生命周期, 生成跟踪
3. `PopupWindowAnimation`: 显示/隐藏/翻页动画 (QPropertyAnimation)
4. `PopupWindowHwnd`: HWND注册, 焦点管理
5. `PopupEvents`: 鼠标/键盘/滚轮事件处理
6. `PopupDataRefresh`: 数据重载, 文件选择检测
7. `PopupCommandResult`: 斜杠命令结果显示
8. `PopupBackground`: 背景图异步加载/两级LRU缓存 (max 3)
9. `PopupRenderer`: 网格/Dock/指示器/搜索栏绘制 (paintEvent)
10. `PopupDragDrop`: 拖放支持
11. `PopupIcon`: 图标提取/缓存
12. `PopupSearch`: 搜索栏 + 三层搜索 + 100ms防抖 + IME支持
13. `PopupWindowEffect`: DWM模糊/SetWindowCompositionAttribute亚克力
14. `PopupLayout`: 网格计算/居中/多显示器DPI
15. `PopupItemExecution`: 快捷方式执行
16. `GlassBackground`: 三缓冲捕获渲染 (20FPS) + PIL管线 → QImage管线
17. `GlassEffects`: 饱和度/径向高光/暗边/内高光
18. `GlassTypes`: 玻璃类型定义
19. **验证**: 弹窗显示/隐藏, 搜索功能, 翻页动画, 玻璃效果

#### 功能 20: 配置窗口

**目标**: 完整配置/编辑体验

**对应Python文件**: `ui/config_window/*.py` (61文件)

**实施步骤:**
1. `MainWindow(QMainWindow)`: RoundedWindow + TitleBar
2. 9个设置页面 (System/Popup/Appearance/Plugins/Commands/Data/About/Support)
3. `FolderPanel`: 文件夹列表 + 拖拽
4. `IconGrid`: 图标网格渲染 + 排序 + 选择
5. `IconWidget`: 单个图标组件
6. `IconPickerDialog`: 图标选择
7. `ShortcutDialog`: 快捷方式编辑
8. `CommandDialog` + `CommandDialogForm` + `CommandDialogIcon` + `CommandDialogTestRunner`
9. `CommandParamDialog`: 命令参数
10. `HotkeyDialog` + `HotkeyCaptureHelpers`: 热键录制
11. `UrlDialog`: URL编辑
12. `BatchLaunchDialog`: 批量启动
13. `MacroRecordDialog` + `MacroRecorderWidget`: 宏录制
14. `MouseKeyRecorder` + `InputTriggerRecorder`: 输入录制
15. `TemplateVariableHighlighter`: 语法高亮 (QSyntaxHighlighter)
16. `BaseDialog`: 对话框基类
17. **验证**: 每个对话框的UI测试

#### 功能 21: 命令面板

**目标**: 独立命令执行面板

**对应Python文件**: `ui/command_panel_window.py` 及相关 (6文件)

**实施步骤:**
1. `CommandPanelWindow`: 独立面板窗口
2. `CommandPanelWidgets`: 面板组件
3. `CommandPanelRenderers`: 面板渲染器
4. `CommandPanelParams`: 参数输入
5. `CommandPanelHistory`: 命令历史
6. `CommandPanelContracts`: 面板契约
7. **验证**: 命令执行面板测试

#### 功能 22: 样式与主题系统

**目标**: 完整设计令牌 + QSS生成 + 主题切换

**对应Python文件**: `ui/styles/*.py` (21+文件)

**实施步骤:**
1. `DesignTokens`: SurfaceScale/TextScale/BorderScale/StatusScale/GroupIconScale/RadiusScale/SpacingScale/Elevation/DurationScale/EasingScale (dark/light 双套)
2. `ThemeController`: 全局主题状态 + 层级解析
3. `Style` / `StyleSheet`: QSS 样式表
4. `WindowChrome`: 自定义窗口边框
5. `ThemedMessageBox`: 主题消息框
6. `StandardWidgets`: 标准组件样式
7. `PopupMenu`: 弹出菜单样式
8. `Motion`: 动效系统
9. `ColorFilterOverlay`: 颜色滤镜
10. `FocusRing`: 焦点环
11. `Glassmorphism`: 玻璃拟态
12. QSS 生成 (11个组件文件): base/button/combobox/dialog/groupbox/input/list/menu/scrollbar/slider/tokens
13. `StyleManager`: 样式管理器
14. **验证**: 主题切换测试, QSS一致性测试

#### 功能 23: UI 工具类

**目标**: 所有UI辅助工具

**对应Python文件**: `ui/utils/*.py` (17文件)

**实施步骤:**
1. `WindowEffect`: DWM模糊/亚克力/阴影 (DwmExtendFrameIntoClientArea, SetWindowCompositionAttribute)
2. `UiScale`: sp() 缩放函数
3. `FontManager`: 字体管理/加载
4. `Animations`: 动画工具
5. `InterruptibleAnimation`: 可中断动画
6. `SmoothScroll`: 平滑滚动
7. `PixelSnap`: 像素对齐
8. `CoordinateUtils`: 坐标工具
9. `GdiMonitor`: GDI资源监控 (GetGuiResources)
10. `GlobalHotkey`: 全局热键
11. `WidgetOpacity`: 组件透明度
12. `DialogHelper`: 对话框辅助
13. `SafeFileDialog`: 安全文件对话框 (子进程)
14. `DefaultIconRenderer`: 默认图标渲染
15. `LruCache`: LRU缓存
16. `QtThreadCleanup`: Qt线程清理
17. **验证**: 工具类单元测试

#### 功能 24: ViewModel 层

**目标**: MVVM ViewModel

**对应Python文件**: `ui/view_models/*.py` (4文件)

**实施步骤:**
1. `ViewModelBase`: 基类 (信号/槽)
2. `Observable`: 可观察属性 (属性变更通知)
3. `IconGridViewModel`: 图标网格数据模型
4. **验证**: ViewModel 单元测试

#### 功能 25: 外部服务

**目标**: 自动更新系统

**对应Python文件**: `services/*.py` (8文件)

**实施步骤:**
1. `ApiClient`: QtNetwork HTTP 客户端 (超时/重试)
2. `UpdateConfig`: 更新源/间隔
3. `UpdateChecker`: HTTP 版本检查
4. `UpdateDownloader`: 下载 (断点续传)
5. `UpdateInstaller`: 静默安装/重启
6. `UpdateSession`: 会话状态
7. **验证**: 更新检查测试, 下载测试

#### 功能 26: 内置插件

**目标**: QR码扫描 + 截图OCR

**对应Python文件**: `plugins/qr_code_scanner/*.py`, `plugins/screenshot_ocr/*.py`

**实施步骤:**
1. QR码扫描: 摄像头捕获 (QtMultimedia) + QR解码 (zxing-cpp 或 zbar)
2. 截图OCR: 屏幕截取 + OCR引擎 (Tesseract 或 Windows OCR API)
3. 插件 manifest + 进程隔离运行时
4. **验证**: 插件功能测试

#### 功能 27: 国际化

**目标**: 中文/英文双语支持

**对应Python文件**: `core/i18n.py` (67K, 最大的单文件之一)

**实施步骤:**
1. 翻译字典 (zh_CN/en 键值对)
2. `tr(key)` 翻译函数
3. Qt .ts/.qm 文件或自建字典
4. 运行时语言切换
5. **验证**: 所有UI文本翻译覆盖测试

#### 功能 28: 测试套件

**目标**: 完整测试覆盖

**对应Python文件**: `tests/` (213文件, 4095测试)

**实施步骤 (优先级):**
1. 领域模型测试: 序列化/反序列化, 默认值, 边界
2. StateStore 测试: 并发, 乐观锁
3. EventBus 测试: 订阅/发布/异常
4. 模糊搜索测试: 评分一致性
5. 命令注册测试: 注册/搜索/别名
6. 配置管理测试: 保存/加载/备份/恢复
7. 批量启动测试: 递归阻断/延迟/取消
8. 插件测试: 加载/隔离/生命周期
9. 安全测试: 路径遍历/SSRF/注入
10. UI 测试: 窗口/弹窗/对话框冒烟
11. 集成测试: 端到端流程
12. 质量门禁: 架构/发布/性能基线

### 4.6 层间依赖规则

依赖关系遵循**依赖倒置原则（DIP）**：上层定义接口（端口），下层实现接口（适配器）；任何层只依赖其下方的接口头文件，不允许依赖具体实现类。

```
bootstrap/        → 所有层（组合根，唯一允许持有具体类型的地方）
application/      → domain/（仅端口接口头文件，无具体实现）
core/             → domain/ + application/ports/（纯虚接口，不 #include 适配器）
infrastructure/   → core/（实现 application/ports 中定义的接口）
ui/               → core/ + application/ports/（实现 IUiActions 等 UI 端口接口）
hooks/            → 独立（仅 Win32 API，无 Qt 依赖，可编译为单独静态库）
services/         → core/（被 core 通过接口调用，而非 core 直接 #include）
extensions/       → core/ + application/ports/
modules/          → core/ + extensions/
platforms/        → 独立（Win32/COM 初始化，无业务逻辑依赖）
plugins/          → core/plugin/（进程外通信：QProcess + JSON-over-stdio 协议）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
禁止的依赖方向（违反会破坏分层架构，CMake 目标间不允许出现循环依赖）：
  domain/         → 任何其他层         纯数据，零外部依赖
  core/           → ui/               业务逻辑不可感知 UI
  core/           → infrastructure/   核心不可依赖具体适配器实现
  infrastructure/ → ui/               基础设施不可感知 UI
  core/           → services/         服务层由上层组合根注入给 core
  plugins/        → core/ 以外的层    插件通过协议访问，不直链宿主
  任何层          → bootstrap/        组合根是单向的终点
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**CMake 目标映射：**

```cmake
# 违规检测：通过 CMake 目标间依赖约束，编译期即暴露违规
add_library(ql_domain      STATIC ...)   # 无 target_link_libraries 依赖
add_library(ql_application STATIC ...)   # 仅 ql_domain
add_library(ql_core        STATIC ...)   # ql_domain + ql_application
add_library(ql_infra       STATIC ...)   # ql_core
add_library(ql_hooks       STATIC ...)   # 无依赖（Win32 only）
add_library(ql_ui          STATIC ...)   # ql_core + Qt6::Widgets
add_executable(QuickLauncher ...)        # 全部，仅 bootstrap/ 和 main.cpp 在此
```

### 4.7 数据流示例

**中键触发弹窗 → 搜索 → 执行:**
```
User中键
  → MouseHook (hooks/)
  → PopupMixin (TrayApp)
  → LauncherPopup.show() (ui/launcherpopup/)
  → 用户输入
  → PopupSearch._refresh_search_results()
    → search_engines.parse_search_action()  [Web搜索]
    → slash_commands.find_matching_commands() [斜杠命令]
    → fuzzy_search.search_shortcuts()        [模糊搜索]
      → pinyin_variants()                    [CJK支持]
      → search_history_bonus()               [个性化]
    → execute_search_sources()               [插件搜索]
  → 用户回车
  → PopupItemExecution
  → ShortcutExecutor.execute()
    → dispatch by ShortcutType
    → ShellExecuteExW / QProcess / HooksDLL / BatchLaunch
  → ShortcutService.record_used()
  → DataManager.save() → SaveCoordinator → debounced write
```

**启动流程:**
```
main()
  → QApplication(argc, argv)
  → RunModeRouter::parse()
  → [GUI模式]:
    → DpiSetup::setupPerMonitorAwareness()     [SetProcessDpiAwarenessContext + SHCore回退]
    → COMInit::initialize()                     [CoInitializeEx(COINIT_APARTMENTTHREADED)]
    //  ⚠ 主(GUI)线程必须 STA；后台工作线程再按需 CoInitializeEx(COINIT_MULTITHREADED)
    → LoggingInit::setup()                      [spdlog + RotatingFileSink + SetUnhandledExceptionFilter]
    → IpcServer::start()                        [QLocalServer + token鉴权]
    → acquireInstanceMutex()                    [CreateMutexW, 已存在则IPC转发退出]
    → FontManager::loadEmbeddedFonts()          [AddFontResourceExW]
    → CompositionRoot::assemble()               [构建ApplicationServices + AppContext]
    → DataLoader::loadAll()                     [JSON配置 + 图标缓存 + 搜索历史]
    → AutoStartManager::syncOnStartup()         [自启动注册表/任务计划同步]
    → TrayApp::init()                           [9个mixin初始化: hooks/popup/menu/update/sleep/startup/shutdown/windows/data]
    → StartupTasks::runDeferred()               [QTimer.singleShot: 缓存预热/插件扫描/更新检查]
    → QApplication::exec()                      [进入事件循环]
  → [非GUI模式]:
    → ProcessHandlers::handle(mode)             [smoke-test/file-dialog/plugin-worker/cli-command]
    → return exitCode
```

**关闭流程:**
```
TrayApp.aboutToQuit()
  → ShutdownMixin::shutdown()
    → LifecycleManager::release() [逆序]:
      1. ExecutorManager::shutdownAll()          [QThreadPool::waitForDone(5000)]
      2. PluginManager::unloadAll()              [QProcess::terminate + waitForFinished(3000)]
      3. HookManager::uninstallAll()             [UnhookWindowsHookEx × N]
      4. HotkeyManager::unregisterAll()          [UnregisterHotKey × N]
      5. IpcServer::stop()                       [QLocalServer::close]
      6. releaseInstanceMutex()                   [CloseHandle(mutex)]
      7. ClipboardService::restoreSnapshot()     [还原剪贴板]
      8. SaveCoordinator::flushPending()         [强制写出待保存数据]
      9. COMInit::uninitialize()                 [CoUninitialize]
  → atexit handlers                             [日志flush/临时文件清理]
```

---

## 五、Python → C++ Win32 API 等价对照表

| Python 调用方式 | C++ 等价 | 备注 |
|---|---|---|
| `win32gui.FindWindowW(cls, title)` | `FindWindowW(cls, title)` | 直接对应 |
| `win32gui.EnumWindows(callback, data)` | `EnumWindows(callback, lParam)` | C++ 用 `WNDENUMPROC` |
| `win32gui.SetForegroundWindow(hwnd)` | `SetForegroundWindow(hwnd)` | 需先 `AttachThreadInput` |
| `win32gui.GetWindowRect(hwnd)` | `GetWindowRect(hwnd, &rect)` | 返回 `RECT` |
| `win32gui.ShowWindow(hwnd, cmd)` | `ShowWindow(hwnd, cmd)` | `SW_SHOW`/`SW_HIDE`/`SW_MINIMIZE` |
| `win32api.ShellExecuteExW(...)` | `ShellExecuteExW(&sei)` | `SHELLEXECUTEINFOW` 结构体 |
| `win32process.CreateProcessW(...)` | `CreateProcessW(...)` | `STARTUPINFOW` + `PROCESS_INFORMATION` |
| `win32clipboard.OpenClipboard()` | `OpenClipboard(hwnd)` | 8步退避重试逻辑照搬 |
| `win32clipboard.GetClipboardData(fmt)` | `GetClipboardData(fmt)` | 需 `GlobalLock`/`GlobalUnlock` |
| `win32api.GetMonitorInfo(hMonitor)` | `GetMonitorInfoW(hMonitor, &mi)` | `MONITORINFOEXW` |
| `win32api.SHGetFileInfoW(path, ...)` | `SHGetFileInfoW(path, attr, &fi, cb, flags)` | 图标提取首选 |
| `win32api.ExtractIconEx(file, idx)` | `ExtractIconExW(file, idx, &large, &small, 1)` | 返回 `HICON` |
| `ctypes.windll.user32.SetWindowsHookExW(...)` | `SetWindowsHookExW(id, proc, hmod, tid)` | 全局钩子 |
| `ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(...)` | `DwmExtendFrameIntoClientArea(hwnd, &margins)` | 玻璃效果 |
| `win32com.client.Dispatch("Schedule.Service")` | `ITaskService` COM 接口 | `#import <taskschd.dll>` 或手动 COM vtable |
| `win32security.GetTokenInformation(...)` | `GetTokenInformation(hToken, cls, buf, len, &retLen)` | 提权场景 |
| `win32api.RegisterHotKey(hwnd, id, mods, vk)` | `RegisterHotKey(hwnd, id, mods, vk)` | 全局热键 |
| `psutil.Process(pid).memory_info()` | `GetProcessMemoryInfo(hProcess, &pmc, cb)` | `PROCESS_MEMORY_COUNTERS` |
| `watchdog.observers.Observer()` | `ReadDirectoryChangesW(hDir, buf, len, subtree, filter, ...)` | 异步重叠I/O |
| `SetProcessDpiAwarenessContext(ctx)` | `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` | Windows 10 1703+; 回退到 `SetProcessDpiAwareness` (SHCore) |
| `SetWindowCompositionAttribute(hwnd, &data)` | 未公开API — 需 `GetProcAddress` 动态获取 | 亚克力/模糊效果 |
| `GetGuiResources(hProcess, GR_GDIOBJECTS)` | `GetGuiResources(hProcess, GR_GDIOBJECTS)` | GDI 资源监控 |
| `ctypes.windll.shcore.GetDpiForMonitor(...)` | `GetDpiForMonitor(hMon, MDT_EFFECTIVE_DPI, &dpiX, &dpiY)` | `<shellscalingapi.h>`；需链接 `shcore.lib` |
| `win32api.GetDpiForWindow(hwnd)` | `GetDpiForWindow(hwnd)` | Windows 10 1607+；返回每窗口 DPI |
| `PIL.ImageGrab.grab(bbox)` | `QScreen::grabWindow(id, x, y, w, h)` | 截屏；或 `BitBlt` + `CreateCompatibleBitmap` |
| `win32api.CreateMutex(None, False, name)` | `CreateMutexW(nullptr, FALSE, name)` | 单实例互斥量；`GetLastError() == ERROR_ALREADY_EXISTS` 表示已有实例 |
| `win32api.GetLastError()` | `GetLastError()` / `HRESULT_FROM_WIN32(err)` | Win32 错误码转 HRESULT |
| `win32api.GetSystemMetrics(SM_CXSCREEN)` | `GetSystemMetrics(SM_CXSCREEN)` | 系统屏幕宽高；多显示器用 `EnumDisplayMonitors` |
| `win32api.CloseHandle(h)` | `CloseHandle(h)` | 关闭 Win32 句柄；RAII 封装建议 `UniqueHandle`/`HandleGuard` |
| `win32api.WaitForSingleObject(h, ms)` | `WaitForSingleObject(h, ms)` | `INFINITE` = 无限等待；返回 `WAIT_OBJECT_0` 表示成功 |

---

## 六、数据格式参考设计

> C++ 版本为全新独立项目，**不要求**读写 Python 版本的历史数据文件。此表仅作**格式参考**，C++ 版可自行定义数据结构，Python 版的字段命名和格式是推荐基准，不是强制约束。

| 文件/格式 | 参考路径 | Python 版格式说明 | 推荐 C++ 库 | 参考说明 |
|---|---|---|---|---|
| `data.json` | 安装目录 | UTF-8 JSON，顶层 `{version, config_schema_version, settings, folders}`；`folders[]` 每项含 `items[]`，每个 item 为46字段的快捷方式对象（⚠ `shortcuts` **不是**顶层字段）| nlohmann::json | 字段名/类型/默认值完全一致；缺失字段用 C++ 端默认值填充；`version` 字符串必须保留原值（当前 `"2.5"`）|
| `events.jsonl` | 安装目录 | 每行一条 JSON 事件 `{ts, type, data}` | nlohmann::json + `std::ifstream` | 追加写入, 不修改已有行 |
| `icon_repo.json` | 安装目录 | `{path: {md5, icon_path, timestamp}}` 映射 | nlohmann::json | MD5 用 `QCryptographicHash` 或 OpenSSL, 与 Python `hashlib.md5` 输出一致 |
| `search_history.json` | 安装目录 | `{query: {count, last_used}}` 映射 | nlohmann::json | `last_used` 为 ISO-8601 时间戳字符串 |
| `config_backup_*.json` | `backups/` | 带时间戳的 `data.json` 完整拷贝 | 文件复制 | 原子替换 (`MoveFileExW` 或 `QSaveFile`) |
| `config_history_*.gz` | `history/` | gzip 压缩的 JSON 快照 | `zlib` / `Qt QCompressionStream` | 与 Python `gzip.compress()` 互通 |
| `.qlzip` | 用户导出 | ZIP 归档: `data.json` + `icons/` + `manifest.json` | `minizip` / `Qt QZipWriter` | Python 用 `zipfile` 生成, C++ 必须能解压; 路径遍历检查 |
| `plugins/*/manifest.json` | `plugins/` | `{name, version, entry, permissions, ...}` | nlohmann::json | 遵循 PluginManifest schema |
| `plugin_state.json` | `plugins/` | `{plugin_name: {enabled, settings, fail_count}}` | nlohmann::json | 失败计数 ≥3 自动隔离 |
| 图标 PNG | `icons/` | 64×64 或 128×128 RGBA PNG | `QImage` / `stb_image` | 与 Python Pillow 生成的 PNG 互通 |
| 默认图标 | 运行时生成 | CJK 首字符 + 彩色圆形背景 | `QPainter` 绘制 | 颜色哈希算法一致 |

---

## 七、C++ 重构推进指南

### 7.1 推荐推进顺序

按照依赖关系从底层到上层推进，每个功能在前一个完成后进行：

```
阶段 1 — 基础骨架 (功能 1~6):
  领域模型 → 应用层合约 → 启动引擎 → 引导编排 → 基础设施端口 → 数据持久化

阶段 2 — 核心业务 (功能 7~12):
  命令注册 → 模糊搜索 → 快捷方式CRUD → 命令执行 → 批量启动 → 插件系统 → 预处理管道

阶段 3 — 系统服务 (功能 14~17):
  系统服务 → 安全模块 → Hooks DLL → 基础设施适配器

阶段 4 — UI 层 (功能 18~24):
  托盘应用 → 弹窗启动器 → 配置窗口 → 命令面板 → 样式主题 → UI工具 → ViewModel

阶段 5 — 外围 (功能 25~28):
  外部服务 → 内置插件 → 国际化 → 测试套件
```

### 7.2 每个功能的推进步骤

对于每个功能，建议严格按以下步骤执行：

1. **阅读对应 Python 源文件** — 本文档已列出每个功能涉及的所有 Python 文件路径
2. **参考本文档的算法/API 描述** — 精确到字段名、参数类型、返回值、边界条件
3. **编写 C++ 头文件 (.h)**
   - 第一行必须是 `#pragma once`
   - 列出所有 `#include`（标准库→Qt→第三方→项目内）
   - 公开接口加 `[[nodiscard]]`
   - 复杂参数/返回值写 Doxygen `@brief`
4. **编写 C++ 实现 (.cpp)** — 按照 Python 逻辑逐一还原，保持相同的算法细节（边界值、clamp 范围、评分权重等）
5. **编写单元测试** — 参照 `tests/` 目录下对应的 Python 测试；将 Python 版测试数据（fixtures）复制到 `tests/fixtures/`
6. **运行验证** — `ctest --preset windows-debug -R <功能名>` 全部通过；若有数值结果（如模糊搜索评分），与 Python 版对比（允许浮点误差 1e-6）
7. **提交** — 每个功能单独 commit：`git commit -m "feat(core): 实现功能N — <名称>"`；不将多个功能混入同一 commit

### 7.3 CMake 项目结构建议

> 目录根为 `G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0\`，与 [4.2](#42-c-目录树) 完全对应。
> 每个 `src/` 子目录括号内为对应的 **CMake 静态库目标名**（对照 [4.6](#46-层间依赖规则) 中的目标映射）。

```
QuickLauncher_V0.0.0.0/
│
│  ── 顶层配置文件 ──────────────────────────────────────────
├── CMakeLists.txt           # 顶层（见下方完整示例）
├── CMakePresets.json        # 构建预设（见7.5.3）
├── vcpkg.json               # 依赖清单（见7.4）
├── .clang-format            # 代码格式化（基于 LLVM 风格，行宽120）
├── .clang-tidy              # 静态分析规则（modernize-* / readability-*）
├── .editorconfig            # 编辑器配置（indent=4, charset=utf-8）
├── .gitignore               # 忽略 build/ .vs/ *.user cmake-build-*/
└── README.md
│
│  ── CMake 模块 ─────────────────────────────────────────────
├── cmake/
│   ├── CompilerSettings.cmake    # MSVC /W4 /WX /utf-8; Clang -Wall -Wextra
│   ├── DependencyFinder.cmake    # find_package(Qt6/spdlog/...) 封装 + 路径检查
│   ├── CodeCoverage.cmake        # OpenCppCoverage / gcov 集成
│   └── Packaging.cmake           # CPack + windeployqt 收集Qt DLL
│
│  ── 资源文件 ───────────────────────────────────────────────
├── resources/
│   ├── CMakeLists.txt            # qt_add_resources(QuickLauncher "app_resources" ...)
│   ├── resources.qrc
│   ├── icons/                    # app.ico  command_icons/  dialog_icons/
│   ├── fonts/                    # 内嵌字体子集（如 MicrosoftYaHei-Subset.ttf）
│   ├── translations/             # zh_CN.ts / en.ts → lupdate/lrelease → .qm
│   └── styles/                   # 内嵌 QSS 基础文件（若有）
│
│  ── 源码（按层分目标）─────────────────────────────────────
├── src/
│   ├── main.cpp                  # 仅 #include "bootstrap/AppEntry.h"，极薄入口
│   │
│   ├── domain/                   # [ql_domain] 纯数据，零依赖
│   │   ├── CMakeLists.txt        #   add_library(ql_domain STATIC ...)
│   │   ├── models.h / models.cpp #   ShortcutItem / Folder / AppSettings / AppData
│   │   ├── clipboard.h / clipboard.cpp  # ClipboardSnapshot / ClipboardClassification
│   │   └── constants.h          #   normalize_*() 函数 + 默认常量
│   │
│   ├── application/              # [ql_application] 端口接口 + 应用契约
│   │   ├── CMakeLists.txt        #   add_library(ql_application STATIC ...)
│   │   ├── errors.h / errors.cpp #   ApplicationError 及其子类
│   │   ├── events/
│   │   │   ├── EventBus.h / EventBus.cpp   # 线程安全 pub/sub（含 Token RAII）
│   │   │   └── AppEvents.h                 # ConfigSaved / ConfigLoaded / ShortcutExecuted
│   │   ├── state/
│   │   │   └── StateStore.h / StateStore.cpp  # 乐观并发，强异常保证
│   │   ├── execution/
│   │   │   └── contracts.h      #   ExecutionRequest / ExecutionResult / CancellationToken
│   │   └── ports/               #   ⚠ 仅头文件，无 .cpp（纯虚接口，零实现）
│   │       ├── IConfigRepository.h
│   │       ├── IBackupStore.h
│   │       ├── IHistoryStore.h
│   │       ├── ISaveScheduler.h
│   │       ├── IGlobalHotkeyPort.h
│   │       ├── IWindowPort.h
│   │       ├── IIconProvider.h
│   │       ├── IAutoStartPort.h
│   │       ├── ISearchPort.h
│   │       ├── IShellOpenerPort.h
│   │       └── IUiActions.h
│   │
│   ├── core/                     # [ql_core] 核心业务逻辑（依赖 ql_domain + ql_application）
│   │   ├── CMakeLists.txt        #   add_library(ql_core STATIC ...)
│   │   ├── data_manager.h / data_manager.cpp
│   │   ├── shortcut/             #   快捷方式子系统（ShortcutService / SmartOrder）
│   │   ├── command/              #   命令子系统（CommandRegistry / BuiltinCommands /
│   │   │                         #   commands_*.h+cpp × 11 / SlashCommands / SearchEngines）
│   │   ├── exec/                 #   命令执行子系统（ProcessRunner / OutputCapture /
│   │   │                         #   Preflight / Audit / CommandVariables）
│   │   ├── batch_launch/         #   批量启动子系统（BatchLaunchStrategy / BatchExecutor）
│   │   ├── plugin/               #   插件子系统（PluginManager / PluginManifest /
│   │   │                         #   PluginIsolatedRuntime / PluginStateStore）
│   │   ├── preprocessing/        #   预处理管道（Pipeline / SecurityCheck /
│   │   │                         #   Sanitizers / Validators / RateLimiter）
│   │   ├── service/              #   系统服务（AutoStartManager / IconExtractor /
│   │   │                         #   ClipboardService / WindowManager / FolderService /
│   │   │                         #   SettingsService / I18nService / MemoryGuard / ...）
│   │   └── security/             #   安全模块（PathSecurity / NetworkSecurity /
│   │                             #   CommandActionSafety / ImportSecurity）
│   │
│   ├── infrastructure/           # [ql_infra] 端口适配器实现（依赖 ql_core）
│   │   ├── CMakeLists.txt        #   add_library(ql_infra STATIC ...)
│   │   ├── persistence/
│   │   │   ├── JsonConfigRepo.h / JsonConfigRepo.cpp   # IConfigRepository 实现
│   │   │   ├── BackupStoreAdapter.h / .cpp
│   │   │   └── HistoryStoreAdapter.h / .cpp
│   │   ├── ShellOpener.h / ShellOpener.cpp      # IShellOpenerPort 实现
│   │   ├── GlobalHotkeyAdapter.h / .cpp         # IGlobalHotkeyPort 实现
│   │   ├── IconProviderAdapter.h / .cpp         # IIconProvider 实现
│   │   ├── AutoStartHelperAdapter.h / .cpp      # IAutoStartPort 实现
│   │   └── Win32Adapters.h / Win32Adapters.cpp  # 窗口 / 进程 / 系统信息
│   │
│   ├── hooks/                    # [ql_hooks] Win32 全局钩子（无 Qt 依赖，仅链接 user32）
│   │   ├── CMakeLists.txt        #   add_library(ql_hooks STATIC ...)
│   │   │                         #   target_link_libraries(ql_hooks PRIVATE user32)
│   │   ├── MouseHook.h / MouseHook.cpp
│   │   ├── KeyboardHook.h / KeyboardHook.cpp
│   │   ├── HotkeyManager.h / HotkeyManager.cpp  # 热键规范化 + 15ms防抖
│   │   ├── InputMacro.h / InputMacro.cpp         # 录制/回放，deque 10万事件上限
│   │   ├── KeyMap.h / KeyMap.cpp                 # VK → 字符串映射
│   │   └── TriggerConfig.h / TriggerConfig.cpp
│   │
│   ├── ui/                       # [ql_ui] Qt Widgets 表现层（依赖 ql_core + Qt6::Widgets）
│   │   ├── CMakeLists.txt        #   add_library(ql_ui STATIC ...)
│   │   ├── tray_mixins/          #   TrayApp + 8 Mixin（Menu/Hooks/Popup/Sleep/Startup/...）
│   │   ├── launcherpopup/        #   LauncherPopup + 16 Mixin（含 GlassBackground 三缓冲）
│   │   ├── configwindow/         #   ConfigWindow + 9 页面 + 16 对话框
│   │   ├── commandpanel/         #   CommandPanelWindow + Widgets + Renderers
│   │   ├── common/               #   BaseDialog / ThemedWidgets / DisposableWidget
│   │   ├── adapters/             #   IUiActions 实现（UI 端口适配器）
│   │   ├── styles/               #   DesignTokens / ThemeController / QSS 生成（11组件）
│   │   ├── utils/                #   WindowEffect / UiScale / FontManager / LruCache /
│   │   │                         #   Animations / SmoothScroll / GdiMonitor / ...
│   │   └── view_models/          #   IconGridViewModel / BatchLaunchViewModel
│   │
│   ├── services/                 # [ql_services] 外部 HTTP 服务
│   │   ├── CMakeLists.txt        #   add_library(ql_services STATIC ...)
│   │   └── update/               #   ApiClient / UpdateChecker / Downloader / Installer
│   │
│   ├── extensions/               # [ql_extensions] 插件 SDK v1
│   │   ├── CMakeLists.txt
│   │   └── ...
│   │
│   ├── modules/                  # [ql_modules] 内置模块入口（当前为空，预留扩展）
│   │   ├── CMakeLists.txt
│   │   └── ...
│   │
│   ├── platforms/                # [ql_platforms] Win32/COM 初始化（无业务逻辑，无Qt）
│   │   ├── CMakeLists.txt        #   add_library(ql_platforms STATIC ...)
│   │   └── WindowsPlatform.h / WindowsPlatform.cpp  # CoInitializeEx / DPI / CrashFilter
│   │
│   └── bootstrap/                # 组合根（仅被 main.cpp include，不单独建 target）
│       ├── CMakeLists.txt        #   直接以 OBJECT 库或 main.cpp 的 PRIVATE 源加入
│       ├── CompositionRoot.h / CompositionRoot.cpp  # 装配所有 ApplicationServices
│       ├── IpcServer.h / IpcServer.cpp
│       └── RunModeRouter.h / RunModeRouter.cpp
│
│  ── 现有 C++ 钩子 DLL（直接复用 Python 版源码）────────────
├── hooks_dll/
│   ├── CMakeLists.txt            # add_library(hooks_dll SHARED hooks.cpp)
│   │                             # → 编译为 QuickLauncherHooks.dll（保持与 Python 版相同 ABI）
│   │                             # ⚠ ql_hooks（src/hooks/）是对该 DLL 的 C++ 封装包装层，
│   │                             #   两者不冲突：DLL 导出19个符号，ql_hooks 通过 LoadLibrary 加载
│   └── src/
│       └── hooks.cpp
│
│  ── 内置插件（进程外，独立可执行文件）────────────────────
├── plugins/
│   ├── CMakeLists.txt            # add_subdirectory(qr_code_scanner) + screenshot_ocr
│   ├── qr_code_scanner/
│   │   ├── CMakeLists.txt        # add_executable(plugin_qr ...) + 独立 vcpkg overlay
│   │   └── src/
│   └── screenshot_ocr/
│       ├── CMakeLists.txt        # add_executable(plugin_ocr ...)
│       └── src/
│
│  ── 测试 ──────────────────────────────────────────────────
├── tests/
│   ├── CMakeLists.txt            # enable_testing(); add_subdirectory × 4; CTest 集成
│   ├── unit/                     # 纯逻辑单元测试（GTest，无 Qt 依赖）
│   │   ├── domain/               #   序列化 / 归一化 / 默认值边界
│   │   ├── core/                 #   模糊搜索评分 / 命令注册 / 安全模块 / 批量启动递归阻断
│   │   └── hooks/                #   热键规范化 / 键码映射
│   ├── integration/              # 跨模块集成测试（含 Qt 事件循环）
│   │   ├── config/               #   保存 / 加载 / 备份 / 恢复
│   │   └── execution/            #   快捷方式端到端执行
│   ├── ui/                       # Qt UI 冒烟测试（QtTest）
│   │   ├── popup/
│   │   └── configwindow/
│   └── fixtures/                 # 测试基准数据（从 Python 版 tests/fixtures/ 复制）
│       ├── config/               #   1.6-normal.json  1.6-legacy.json  corrupt.json
│       └── qlzip/                #   backup.qlzip  shareable.qlzip
│
│  ── 文档 ──────────────────────────────────────────────────
└── docs/
    └── architecture.md           # 本文档（从 Python 版 scripts/ 复制并随重构更新）
```

**顶层 `CMakeLists.txt` 完整示例：**

```cmake
cmake_minimum_required(VERSION 3.25)

project(QuickLauncher
    VERSION 0.0.0.0
    DESCRIPTION "QuickLauncher C++ Rewrite"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── 自动化 MOC/UIC/RCC ─────────────────────────────────────
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

# ── CMake 模块 ─────────────────────────────────────────────
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(CompilerSettings)   # /W4 /WX /utf-8
include(DependencyFinder)   # find_package(Qt6 spdlog nlohmann_json ...)

# ── 第三方依赖（DependencyFinder.cmake 内部调用）────────────
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets Network Svg Concurrent)
find_package(spdlog         REQUIRED)
find_package(nlohmann_json  REQUIRED)
find_package(ZLIB           REQUIRED)  # zlib（Qt 内含，也可独立）

# ── 子目录（按依赖顺序，底层先）────────────────────────────
add_subdirectory(src/domain)        # ql_domain
add_subdirectory(src/application)   # ql_application
add_subdirectory(src/core)          # ql_core
add_subdirectory(src/infrastructure)# ql_infra
add_subdirectory(src/platforms)     # ql_platforms
add_subdirectory(src/hooks)         # ql_hooks
add_subdirectory(src/services)      # ql_services
add_subdirectory(src/extensions)    # ql_extensions
add_subdirectory(src/modules)       # ql_modules
add_subdirectory(src/ui)            # ql_ui
add_subdirectory(hooks_dll)         # hooks_dll (SHARED → QuickLauncherHooks.dll)
add_subdirectory(plugins)           # plugin_qr  plugin_ocr
add_subdirectory(resources)         # resources.qrc

# ── 主可执行文件（bootstrap + main.cpp，链接所有静态库）─────
add_executable(QuickLauncher WIN32
    src/main.cpp
    src/bootstrap/CompositionRoot.cpp
    src/bootstrap/IpcServer.cpp
    src/bootstrap/RunModeRouter.cpp
)
target_link_libraries(QuickLauncher PRIVATE
    ql_ui ql_core ql_infra ql_hooks ql_services
    ql_extensions ql_modules ql_platforms
    ql_application ql_domain
    Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Network Qt6::Svg Qt6::Concurrent
    spdlog::spdlog
    hooks_dll
)
set_target_properties(QuickLauncher PROPERTIES
    WIN32_EXECUTABLE TRUE
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

# ── 测试 ───────────────────────────────────────────────────
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()

# ── 打包 ───────────────────────────────────────────────────
include(Packaging)
```

### 7.4 关键第三方依赖 (vcpkg / CMake FetchContent)

| 依赖 | 目标版本 | 用途 | 引入方式 | vcpkg 包名 |
|---|---|---|---|---|
| Qt6 | 6.5 LTS / 6.8 | GUI / 网络 / 并发 / 多媒体 | 系统安装 (`Qt Online Installer`) | — |
| nlohmann/json | 3.11.3 | JSON 序列化 | `FetchContent` 或 vcpkg | `nlohmann-json` |
| spdlog | 1.13.0 | 高性能旋转日志 | vcpkg | `spdlog` |
| zlib | 1.3.1 | gzip 压缩（历史快照 `.gz`）| vcpkg（Qt 内含，可复用） | `zlib` |
| minizip-ng | 4.0.4 | `.qlzip` 备份包读写（含遍历防护）| vcpkg | `minizip-ng` |
| OpenSSL | 3.3.x | TLS / SHA-256 / MD5 | Qt 捆绑版优先；单独可 vcpkg | `openssl` |
| GoogleTest | 1.14.0 | 单元测试框架 | `FetchContent` | `gtest` |
| cpp-pinyin | latest stable | 拼音搜索（可选；可替换为内置字典）| `FetchContent` | — |
| zxing-cpp | 2.2.1 | QR 码解码（qr_code_scanner 插件）| vcpkg | `zxing-cpp` |
| Tesseract | 5.3.4 | OCR（screenshot_ocr 插件，可选）| vcpkg 或 Windows.Media.Ocr | `tesseract` |
| stb | latest | stb_image_resize（图标缩放）| `FetchContent`（单头文件）| — |

**`vcpkg.json` 示例（仅必要依赖）：**

```json
{
  "name": "quicklauncher",
  "version": "0.0.0.0",
  "dependencies": [
    { "name": "nlohmann-json", "version>=": "3.11.3" },
    { "name": "spdlog",        "version>=": "1.13.0" },
    { "name": "zlib",          "version>=": "1.3.1"  },
    { "name": "minizip-ng",    "version>=": "4.0.4"  },
    { "name": "gtest",         "version>=": "1.14.0" },
    { "name": "zxing-cpp",     "version>=": "2.2.1"  }
  ],
  "builtin-baseline": "最新 commit hash（运行 vcpkg x-update-baseline 获取）"
}
```

### 7.5 开发环境配置

#### 7.5.1 所需环境总览

| 工具 | 最低版本要求 | 用途 |
|---|---|---|
| Visual Studio (带 C++ 桌面开发负载) | VS 2022 17.8+ | 编译器 (MSVC v143)、CMake、Ninja、调试器 |
| Windows 10 SDK | 10.0.19041.0+ | Win32 API / DPI v2 / WDA_EXCLUDEFROMCAPTURE |
| CMake | 3.25+ | 构建系统（可用 VS 内置版） |
| Ninja | 1.11+ | 快速增量构建（可用 VS 内置版） |
| Git | 2.40+ | 版本控制 |
| vcpkg (manifest mode) | 2024.01+ | C++ 包管理，自动还原依赖 |
| Qt6 | 6.5 LTS | GUI 框架（需独立安装，VS 不内置） |
| Python 3.12 | 3.12.x | 构建脚本、测试辅助（对应当前 Python 源码版本） |

#### 7.5.2 当前机器已有环境

经自动检测（2026-06-22），当前开发机器的情况如下：

| 工具 | 状态 | 版本 | 安装路径 |
|---|---|---|---|
| **Visual Studio** | ✅ 已安装 | Community 2026 (18.7.11911.148) | `E:\Visual Studio 2026` |
| **MSVC 工具链** | ✅ 已安装 | v14.51.36231 | `E:\Visual Studio 2026\VC\Tools\MSVC\14.51.36231` |
| **CMake** | ✅ 已安装 (VS 内置) | 4.3.1 | `E:\Visual Studio 2026\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` |
| **Ninja** | ✅ 已安装 (VS 内置) | — | `E:\Visual Studio 2026\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe` |
| **Windows SDK** | ✅ 已安装 | 10.0.26100.0 | `C:\Program Files\Windows Kits\10\` |
| **Git** | ✅ 已安装 | 2.54.0 | `E:\Git\cmd\git.exe` |
| **Python 3.13** | ✅ 已安装 | 3.13.13 | `E:\Python313\python.exe` |
| **Python 3.12** | ✅ 已安装 | 3.12.7 | `E:\Python312\python.exe` |
| **Python 3.11** | ✅ 已安装 | 3.11.9 | `E:\Python311\python.exe` |
| **Qt6** | ❌ 未安装 | — | 需要手动安装（见下方步骤） |
| **vcpkg** | ❌ 未安装 | — | 需要手动安装（见下方步骤） |

> **SDK 版本说明**：已安装的 10.0.26100.0（Windows 11 24H2 对应版本）**远高于**最低要求 10.0.19041.0，所有 Win32 特性（Per-Monitor DPI v2、`WDA_EXCLUDEFROMCAPTURE`）均可用。

#### 7.5.3 尚需安装的环境

**① 安装 Qt 6.5 LTS**

```
下载地址: https://www.qt.io/download-qt-installer
安装器: Qt Online Installer for Windows
选择组件（最小集）:
  ✅ Qt 6.5.x → MSVC 2019 64-bit (兼容 VS 2022/2026 MSVC v14x)
  ✅ Qt 6.5.x → Qt Network / Qt Concurrent / Qt Svg / Qt Multimedia (如需 OCR/QR)
  ✅ Qt 6.5.x → Additional Libraries → Qt Image Formats
  ❌ 其余可选组件（Android/iOS/WebAssembly 等无需勾选）

建议安装路径: E:\Qt   （与 Visual Studio 同盘，便于管理）
安装后 Qt6 根目录示例: E:\Qt\6.5.3\msvc2019_64\
```

**② 安装 vcpkg（manifest mode）**

```powershell
# 推荐安装到 E:\vcpkg（与 VS/Qt 同盘）
cd E:\
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
.\bootstrap-vcpkg.bat -disableMetrics

# 可选：设为系统环境变量（便于 CMake 自动发现）
[Environment]::SetEnvironmentVariable("VCPKG_ROOT", "E:\vcpkg", "Machine")
[Environment]::SetEnvironmentVariable("PATH", "$env:PATH;E:\vcpkg", "Machine")
```

**③ 配置 CMake 使用 VS 内置工具（无需单独安装）**

在 CMakePresets.json 中指定工具链路径，或通过 Visual Studio 直接打开 CMake 项目（IDE 自动配置）：

```json
{
  "version": 6,
  "configurePresets": [
    {
      "name": "windows-debug",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/debug",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_TOOLCHAIN_FILE": "E:/vcpkg/scripts/buildsystems/vcpkg.cmake",
        "CMAKE_PREFIX_PATH":  "E:/Qt/6.5.3/msvc2019_64"
      }
    },
    {
      "name": "windows-release",
      "inherits": "windows-debug",
      "binaryDir": "${sourceDir}/build/release",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "RelWithDebInfo" }
    }
  ]
}
```

#### 7.5.4 项目路径说明

| 项目 | 路径 | 说明 |
|---|---|---|
| **Python 参考项目** | `G:\LEI-PLUG\QuickLauncher\QuickLauncher_V1.6.3.6\` | 功能完整的现有版本，仅作参考，**不修改** |
| **C++ 全新项目** | `G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0\` | 从零构建的独立项目，不继承 Python 代码 |

> C++ 版本是**全新独立项目**，不是 Python 版本的迁移或升级。两者无代码兼容要求，可并行独立开发。

C++ 项目初始化步骤：

```powershell
cd G:\LEI-PLUG\QuickLauncher\QuickLauncher_V0.0.0.0

# 独立 git 仓库（与 Python 版本无关联）
git init
git remote add origin <新仓库URL>   # 按需设置

# 参见 4.5 功能1 实施步骤创建 CMakeLists.txt 等初始文件
```

---

## 八、附录

### A. Python 源码文件索引 (按层)

**domain/ (2 文件)**: `models.py`（含 `ShortcutType` 枚举、`ShortcutItem`/`Folder`/`AppSettings`/`AppData` 全部领域模型）, `clipboard.py`（剪贴板值对象）

> 注：枚举定义在 `models.py` 内，不存在独立的 `enums.py`。

**application/ (~10 文件)**: `events.py`, `state/store.py`, `execution/contracts.py`, `execution/policies.py`, `ports/*.py`

**core/ (~80+ 文件)**:
- 数据: `data_manager.py`, `data_models.py`, `data_loader.py`, `data_validator.py`
- 命令: `command_registry.py`, `builtin_commands.py`, `builtin_command_catalog.py`, `commands_*.py` (11个), `slash_commands.py`, `search_engines.py`
- 搜索: `fuzzy_search.py`, `pinyin_search.py`, `search_history.py`
- 快捷方式: `shortcut_service.py`, `shortcut_executor.py`, `shortcut_*.py` (10个), `batch_launch_exec.py`
- 命令执行: `command_exec/*.py` (11个), `command_execution_service.py`, `command_io.py`, `command_results.py`, `command_result_actions.py`, `command_variables.py`
- 插件: `plugin/*.py` (16个), `plugin_manager.py`
- 配置: `config_services.py`, `save_coordinator.py`, `config_validation.py`, `config_history.py`, `config_recovery.py`, `config_repairs.py`, `config_migrator.py`, `config_importer.py`, `backup_service.py`
- 预处理: `preprocessing/*.py` (9个)
- 系统: `auto_start_manager.py`, `icon_extractor.py`, `clipboard_service.py`, `window_manager.py`, `folder_service.py`, `settings_service.py`, `i18n.py`, `event_log.py`, `diagnostics.py`, `error_handler.py`, `memory_guard.py`, `executor_manager.py`, `background_tasks.py`
- 安全: `path_security.py`, `import_security.py`, `network_security.py`, `command_action_safety.py`, `command_param_validation.py`, `command_risk.py`

**infrastructure/ (~10 文件)**: `persistence/adapters.py`, `shell_opener_adapter.py`, `system_clock_adapter.py`, `hotkey_adapter.py`, `icon_provider_adapter.py`, `autostart_helper_adapter.py`, `win32_adapters.py`

**hooks/ (~8 文件)**: `hooks_wrapper.py`, `hotkey_manager.py`, `input_macro.py`, `mouse_hook.py`, `keyboard_hook.py`, `key_map.py`, `hook_pause.py`, `trigger_config.py`

**ui/ (~100+ 文件)**:
- 托盘: `tray_app.py`, `tray_controllers.py`, `tray_workers.py`, `tray_mixins/*.py` (9个)
- 弹窗: `launcher_popup/*.py` (20个)
- 配置窗口: `config_window/*.py` (61个)
- 命令面板: `command_panel_window.py` 及相关 (6个)
- 样式: `styles/*.py` (21+个)
- 工具: `utils/*.py` (17个)
- ViewModel: `view_models/*.py` (4个)

**services/ (~8 文件)**: `api_client.py`, `update_config.py`, `update_checker.py`, `update_downloader.py`, `update_installer.py`, `update_session.py`

**bootstrap/ (~5 文件)**: `composition_root.py`, `ipc.py`, `run_mode_router.py`, `dpi_setup.py`, `logging_init.py`

### B. 关键数字速查

| 指标 | 数值 |
|---|---|
| Python 源码总行数 | ~50,047 行 |
| 源文件数 | 500+ |
| 测试用例数 | 4,095 |
| ShortcutItem 字段数 | 46 |
| AppSettings 字段数 | 88 |
| ShortcutType 枚举值 | 7 |
| 内置命令别名数 | ~140 |
| 斜杠命令数 | 27 |
| 搜索引擎数 | 4 |
| TrayApp Mixin 数 | 9 |
| LauncherPopup Mixin 数 | 16 |
| 模糊搜索评分层数 | 6 |
| 字段权重数 | 7 |
| Hooks DLL 版本 | 15 |
| DLL 必需导出函数 | 19 |
| DLL 可选导出函数 | ~15 |
| 配置整数范围校验数 | 30+ |
| 插件隔离级别 | 2 (标准/严格) |
| 剪贴板重试步数 | 8 |
| 拼音解析层级 | 3 |
| 设计令牌量表数 | 9 |
| 玻璃效果缓冲区数 | 3 |
| 玻璃效果帧率 | 20 FPS |
| 搜索防抖延迟 | 100ms |
| 保存防抖延迟 | 500ms |
| 配置历史快照上限 | 20 |
| 宏事件存储上限 | 100,000 |
| 热键防抖间隔 | 15ms |
