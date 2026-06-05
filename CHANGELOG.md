# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.6.3.0] - Unreleased

### Added

- 新增独立 `.qlzip` 形式的"截图 OCR"插件包，通过插件 API 注册为内置命令，官方插件从运行时 `plugins/` 目录剥离为 `.plugins/*.qlzip` 安装包，主程序新增 `--plugin-helper` 子进程入口支持插件自带 Python 库。
- 弹窗触发支持自定义触发按键和特殊触发按键，可选键盘、鼠标或混合模式。
- 命令面板新增参数 invocation 快照、runtime shortcut 副本、非敏感参数历史恢复和 `{{input}}` 统一传递，参数表单新增执行预览，敏感参数自动遮罩。
- 命令参数支持 `label`、`placeholder`、`help`、`multiline`、`source`、`validator`、`remember` 等字段，并新增结构化参数编辑弹窗。
- 动作链增强：新增模块型插件扩展点与 `register_chain_processor()` API、完整电池 schema（分类/端口/参数/安全等级）、节点级测试运行快照、属性面板自动生成参数控件、风险分析接入 safety 定义。
- 动作链编辑器新增搜索添加栏、复制/粘贴节点、自动排版（`Ctrl+R`）、撤销/重做（`Ctrl+Z`/`Ctrl+Y`）和中期数据处理电池（列表合并/切片/配对/展开/转文本/JSON 模板渲染）。
- JSON 字段路径增强支持数组索引（如 `items[0].name`），便于 HTTP+JSON 数据链处理。
- 批量启动新增独立 `batch_launch` 快捷方式类型、设置窗口和运行执行器，与动作链编辑器分离。
- UI 主题体系新增统一主题解析与自定义窗口外壳，普通窗口、工具窗口、弹窗和文件对话框统一走主题控制。
- 插件 API 新增受限 HTTP 请求、私有数据目录读写、主程序版本/主题读取、命令执行和动作链处理器注册等稳定接口。
- C++ DLL 钩子新增能力位、健康状态、最近错误与安装状态查询，便于诊断中心判断钩子线程和低级钩子状态。

### Changed

- 插件系统：命令软超时调整为 30 秒，新增受权限保护的内置命令注册接口，`.qlzip` 安装限制放宽至 150 MB / 1000 文件，HTTP API 收紧请求边界减少注入风险，命令参数白名单同步支持新字段和 outputs 契约。
- 插件分发：发布包不再复制插件源码，截图 OCR 专用依赖从主程序剥离，OCR 插件内置 `wxPython` 但不内置 `python.exe`。
- 命令面板：底部按钮改为自适应网格布局，`hash`/`tls`/`json`/`jwt`/`port` 内置命令补齐结构化参数和标准 outputs。
- 模块注册表支持插件提供的外部 manifest 并在禁用后自动回退，动作链画布运行结果优先按 `node_id` 映射，主配置窗口双击编辑按类型分发到对应编辑器。
- 文件选择统一改为非原生 Qt 对话框并套用项目主题，C++ DLL 钩子回调从单槽挂起改为有界 FIFO 队列。
- C++ 钩子层重构：`EnsureCallbackThread` 加入互斥锁保护消除并发竞态，共享变量改为 `std::atomic`，Install/Uninstall/ThreadProc 统一为 `HookContext` 结构体（消除约 400 行重复代码），安全调用函数合并为 `SafeInvokeAny`。
- 钩子可靠性：安装加入退避重试（500ms/2s/5s）和 `is_installed` 健康检查自动恢复，键盘钩子改为依赖注入（移除 `sys.modules["__main__"]` 耦合），DLL 加载失败支持 `reset()` 重新加载，失败时提供存根类上层无需判空。
- 线程安全：对话框移除 `QThread.terminate()` 改为协作式取消，插件命令改用全局共享线程池避免资源碎片化，启动线程添加 `atexit` 生命周期管理移除 `daemon=True`，跨线程信号连接显式指定 `QueuedConnection`。
- 构建与代码质量：发布门禁新增覆盖率检查（`--cov-fail-under=70`），mypy 全局启用 `check_untyped_defs`，清理 17 处 `is_win11()` 冗余判断，动作链实现版本迁移链框架，修复版本比较运算符优先级 bug，配置备份/恢复改用 `QThread` 避免阻塞主线程。
- UI 细节：配置窗口拖拽增加屏幕边界约束，Toast 隐藏时清除单例引用允许 GC，`processEvents()` 滥用全面修复（无效调用移除、重绘制调用替换为 `repaint()`、DPI 同步改用 `ExcludeUserInputEvents` 排除用户输入）。

### Fixed

- 修复 Windows 10 兼容性、安装报错及 UI 显示异常。
- 修复 shortcut 命令执行时运行时参数和确认状态写回原始配置导致连续执行串值的问题。
- 修复批量启动窗口图标闪烁、搜索结果慢、编辑时图标丢失/污染、保存后类型引用错误等问题。
- 修复主题链路中父级缺少主题时回退到分散样式的问题，统一按父级、应用属性和暗色默认值解析。
- 修复弹窗和配置子窗口仍可能使用默认系统窗口边框的问题，统一改为自定义窗口外壳。
- 修复插件搜索源跨插件重名互相覆盖的问题，搜索源 ID 自动加命名空间并支持注册失败事务回滚。
- 修复 `ui/tray_app.py` 信号连接使用未导入的 `Qt` 导致启动崩溃（`NameError`）。
- 修复 `QApplication.processEvents()` 滥用导致的嵌套事件循环重入风险（7 处全面修复）。
- 修复 C++ 回调线程竞态条件导致句柄泄漏和回调队列数据竞争。
- 修复对话框 `QThread.terminate()` 可能损坏 COM 状态、泄漏 GIL 和产生孤儿进程的风险。
- 修复插件命令执行每次创建新线程池导致资源碎片化的问题。
- 修复守护线程无生命周期管理导致进程退出时悬挂线程阻止正常终止。

## [1.6.2.0] - 2026-06-01

### Added

- 新增 1.6.2.0 质量审计 backlog，记录深度体检基线、清理策略和后续修复队列。
- 诊断中心新增环境诊断，展示 Windows 版本、当前进程、管理员状态、系统 Python、`py` 启动器和 Git Bash 可用性。
- 诊断中心升级为一站式诊断修复中心，支持汇总可修复项并批量应用快捷方式健康修复。
- 新增本地发布门禁脚本 `scripts/release_gate.py`。
- 新增 GitHub Actions 源码门禁，覆盖编译、ruff、测试和 release 元数据校验。

### Changed

- 诊断报告和导出包增加快捷方式健康修复统计，包括删除类修复数量和修复动作分布。
- 统一并增强内置解析变量处理：URL 快捷方式补齐 `{{app_dir}}`、`{{config_dir}}`、`{{selected_file}}`、`{{selected_file_name}}`、`{{selected_file_dir}}`、`{{selected_files}}` 等变量解析，并将运行时输入传递到自定义浏览器参数。
- 明确 `raw_mode` 行为：启用后不再展开变量，也不再执行变量引用拦截，保持高级原始命令模式语义一致。
- 优化中键弹窗双击空白区刷新反馈，刷新图标闪烁改为短时属性动画，减少长期运行后受高频定时器抖动影响而变慢的情况。

### Fixed

- 优化图标检查修复逻辑，网站快捷方式图标缺失时批量重新自动获取 favicon，而不是清除图标路径。
- 优化网站图标批量修复体验，使用受控多线程并发刷新 favicon，并将修复过程放到后台线程执行，避免诊断窗口卡顿。
- 修复图标网格批量 UI 测试中的 ruff 违规，保持发布门禁静态检查可通过。
- 清理首批生产内部死代码，包括未引用的托盘调试入口、DLL 强制卸载 helper 和图标网格备用重排/单文件添加入口。
- 修复 URL 协议白名单未实际生效的问题，未知或危险协议会被拒绝。
- 修复 URL 变量解析缺少输入值时静默替换为空的问题，现在会明确返回缺少运行时输入。
- 修复纯 `{{param:*}}` / `{{chain:*}}` 变量在 CMD/PowerShell/Bash 中可能作为整条命令执行的风险。

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
- 8 个官方插件：api_tester / disk_cleaner / event_inspector / file_tools / network_tools / process_tools / startup_tools / text_tools
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
