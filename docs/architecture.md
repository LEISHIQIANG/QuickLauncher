# QuickLauncher 架构文档

## 系统概述

QuickLauncher 是一款基于 Python + PyQt5 的 Windows 桌面应用，采用分层架构设计，提供鼠标中键快速启动功能。

## 架构分层

```
┌─────────────────────────────────────┐
│         UI Layer (用户界面层)         │
│  - TrayApp (托盘应用)                │
│  - LauncherPopup (启动弹窗)          │
│  - ConfigWindow (配置窗口)           │
└─────────────────────────────────────┘
              ↓↑
┌─────────────────────────────────────┐
│        Core Layer (核心业务层)        │
│  - DataManager (数据管理)            │
│  - ShortcutExecutor (快捷方式执行)   │
│  - IconExtractor (图标提取)          │
│  - ServiceManager (服务管理)         │
└─────────────────────────────────────┘
              ↓↑
┌─────────────────────────────────────┐
│     Bootstrap Layer (引导层)         │
│  - DPI 感知设置                      │
│  - 日志初始化                        │
│  - 依赖管理                          │
│  - IPC 单实例控制                    │
└─────────────────────────────────────┘
```

## 核心组件

### 1. Bootstrap Layer (引导层)

**职责**: 应用启动初始化

**关键模块**:
- `bootstrap/dpi.py` - DPI 感知配置
- `bootstrap/logging_init.py` - 日志系统初始化
- `bootstrap/deps.py` - 依赖检查和安装
- `bootstrap/ipc.py` - 进程间通信，确保单实例运行
- `bootstrap/venv.py` - 虚拟环境管理

**启动流程**:
1. 设置 DPI 感知
2. 初始化日志系统
3. 检查虚拟环境
4. 安装缺失依赖
5. 初始化 Qt 应用
6. 创建 IPC 服务器
7. 启动托盘应用

### 2. Core Layer (核心业务层)

**职责**: 业务逻辑处理

**关键模块**:

#### 数据管理
- `core/data_manager.py` - 配置数据管理（单例模式）
- `core/data_models.py` - 数据模型定义
- `core/config_migrator.py` - 配置迁移

#### 快捷方式执行
- `core/shortcut_executor.py` - 快捷方式执行调度
- `core/shortcut_file_exec.py` - 文件/文件夹执行
- `core/shortcut_command_exec.py` - 命令执行
- `core/shortcut_url_exec.py` - URL 执行
- `core/shortcut_hotkey_exec.py` - 热键执行

#### 系统集成
- `core/icon_extractor.py` - 图标提取（LRU 缓存）
- `core/auto_start_manager.py` - 自启动管理
- `core/service_manager.py` - Windows 服务管理
- `core/task_scheduler_manager.py` - 任务计划管理

#### 扫描与监控
- `core/app_scanner.py` - 应用扫描
- `core/folder_scanner.py` - 文件夹扫描
- `core/folder_watcher.py` - 文件夹监控

### 3. UI Layer (用户界面层)

**职责**: 用户交互界面

**关键模块**:

#### 主界面
- `ui/tray_app.py` - 托盘应用（主控制器）
- `ui/launcher_popup/` - 启动弹窗
- `ui/search_window/` - 搜索窗口

#### 配置界面
- `ui/config_window/` - 配置窗口（15+ 子模块）
  - `main_window.py` - 主窗口
  - `shortcut_tab.py` - 快捷方式标签页
  - `settings_tab.py` - 设置标签页
  - `appearance_tab.py` - 外观标签页

#### 辅助界面
- `ui/log_window.py` - 日志窗口
- `ui/toast_notification.py` - 通知提示
- `ui/welcome_guide.py` - 欢迎向导

## 关键流程

### 启动流程

```
main.py
  ├─> setup_dpi_awareness()
  ├─> setup_logging()
  ├─> maybe_reexec_in_venv()
  ├─> bootstrap_requirements()
  ├─> QApplication 初始化
  ├─> create_ipc_server()
  └─> TrayApp()
```

### 快捷方式执行流程

```
用户按下中键
  ↓
LauncherPopup 显示
  ↓
用户点击图标
  ↓
ShortcutExecutor.execute()
  ├─> 判断类型
  ├─> 调用对应执行器
  │   ├─> FileExecutor (文件/文件夹)
  │   ├─> CommandExecutor (命令)
  │   ├─> URLExecutor (网址)
  │   └─> HotkeyExecutor (热键)
  └─> 记录执行历史
```

### 配置管理流程

```
ConfigWindow 修改配置
  ↓
DataManager.update_settings()
  ├─> 更新内存数据
  ├─> 触发保存（节流 500ms）
  ├─> 写入 data.json
  └─> 创建自动备份
```

## 数据流

### 配置数据流

```
config/data.json
  ↓ (加载)
DataManager (单例)
  ↓ (读取)
UI Components
  ↓ (修改)
DataManager.update_settings()
  ↓ (保存)
config/data.json
  ↓ (备份)
config/auto_backups/
```

### 图标缓存流程

```
IconExtractor.extract(path)
  ├─> 检查缓存 (LRU, max=130)
  ├─> 缓存命中 → 返回
  └─> 缓存未命中
      ├─> 提取图标
      ├─> 存入缓存
      └─> 返回
```

## 性能优化

### 1. 图标缓存
- LRU 缓存，最大 130 个
- TTL 30 分钟
- 使用 OrderedDict 实现

### 2. 数据保存节流
- 500ms 内的连续保存合并
- 批量操作支持
- 线程安全锁

### 3. 启动优化
- 延迟加载非关键模块
- 虚拟环境重用
- 依赖缓存

## 安全考虑

### 1. 命令执行安全
- 使用 shlex 解析命令参数
- 避免 shell=True
- 路径验证

### 2. 权限管理
- UIPI 检查
- 管理员权限提升
- 服务模式隔离

### 3. 数据安全
- 配置文件自动备份
- 异常恢复机制
- 日志脱敏

## 扩展性

### 添加新的快捷方式类型

1. 在 `core/data_models.py` 添加新类型枚举
2. 创建新的执行器 `core/shortcut_xxx_exec.py`
3. 在 `core/shortcut_executor.py` 注册执行器
4. 在 UI 添加对应的编辑界面

### 添加新的配置项

1. 在 `core/data_models.py` 的 `AppSettings` 添加字段
2. 在 `ui/config_window/settings_tab.py` 添加 UI 控件
3. 在 `core/data_manager.py` 添加迁移逻辑（如需要）

## 依赖关系

```
main.py
  ├─> bootstrap/*
  ├─> core/data_manager
  └─> ui/tray_app
      ├─> ui/launcher_popup
      ├─> ui/config_window
      ├─> core/shortcut_executor
      └─> core/icon_extractor
```

## 测试策略

- 单元测试: core/* 模块
- 集成测试: 启动流程、执行流程
- UI 测试: pytest-qt
- 覆盖率目标: >70%

---

**版本**: 1.5.6.5  
**更新时间**: 2026-05-10
