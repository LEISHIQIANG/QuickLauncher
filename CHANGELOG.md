# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.6.1.0] - 2026-05-30

### Added

- 命令面板独立化：独立 `CommandPanelWindow`，支持 7 种渲染模式（text/log/table/kv/list/progress/qr）
- 动作链（Action Chain）：支持快捷方式链式执行、变量传递、环路检测
- 配置恢复后端：`ConfigRecoveryReport`、quarantine 机制、配置修剪
- 诊断导出功能：`core/diagnostics.py` 一键导出系统诊断信息
- 快捷方式健康检查：`core/shortcut_health.py`
- 插件隔离/隔离区：`core/plugin_manager.py`
- 事件日志系统：`core/event_log.py`
- `--safe-mode` CLI 参数
- `MAX_CHAIN_STEPS` 统一常量（128）定义于 `core/runtime_constants.py`
- 安全预处理管道：validators / sanitizers / security / rate_limiter

### Changed

- 命令执行引擎重构：`CommandExecutionService`，支持 capture_output / display_type / 参数化
- 搜索支持中文拼音：`core/pinyin_search.py`
- 中键弹窗重构：拆分为 popup_renderer / popup_search / popup_data_refresh 等模块
- qt_compat 翻译包装：QLabel / QPushButton 等控件自动调用 `tr()`

### Fixed

- 静默异常吞没问题排查与部分修复
- CI 环境兼容：mock pynput / win32 模块防止 Session 0 挂起
- 编码断言在不同环境下的兼容性

## [1.6.0.0] - 2026-05-15

### Added

- 插件系统 v2：PluginAPI、权限声明、命令注册
- 8 个内置插件：api_tester / disk_cleaner / event_inspector / file_tools / network_tools / process_tools / startup_tools / text_tools
- 独立进程插件隔离计划（架构准备）

## [1.5.6.8] - 2026-04-20

### Changed

- 移除插件命令全局超时限制，改由插件自行管理
- 插件 handler 在独立线程中运行，不再阻塞 UI

## [1.5.6.7] - 2026-04-01

### Added

- 自动更新系统：update/checker / downloader / installer
- 窗口管理：`core/window_manager.py`

## [1.5.6.6] - 2026-03-15

### Added

- 快捷键冲突检测：`core/hotkey_conflict_checker.py`
- 文件安全检查：`core/import_security.py` / `core/path_security.py`
- 数据导入导出增强

## [1.5.6.5] - 2026-03-01

### Added

- 初始公开版本
- 中键唤出搜索面板
- 应用 / 文件夹 / URL / 快捷键 / 命令支持
- 模糊搜索 + 拼音搜索
- 中英双语界面（zh-CN / en）
- 系统托盘管理
- Nuitka + Inno Setup 构建
