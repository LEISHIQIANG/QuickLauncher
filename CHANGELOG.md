# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.6.3.0] - Unreleased

### Added

- 新增高级颜色滤镜（Win11），支持黑点、白点、中间调 Gamma、色温、Acrylic 模糊度和底色 Alpha 六项参数分别针对深色/浅色主题独立调节，通过 DWM Acrylic 着色直接生效，不遮挡 UI 内容。
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

- `sleep_mixin.py`：将 `_iter_visible_blocking_widgets()` 生成器末尾的清理逻辑（热键停止、图标缓存释放、`gc.collect()` 等约 60 行）提取为独立方法 `_perform_sleep_cleanup()`，在 `_enter_light_sleep()` 中显式调用，消除 `_mark_activity()` 每次标记活动时意外触发热键停止和 GC 的副作用。
- `chain/registry.py` SSRF 防护：HTTP GET/POST/Download 处理器统一走 `core.network_security.safe_urlopen()`，拦截私有地址、本机地址、链路本地地址和保留地址，逐跳校验重定向目标，限制响应体大小，过滤 `Host`/`Cookie` 等敏感请求头。
- `chain/registry.py` 巨型函数拆分：将 `_execute_extra_processor()`（原 489 行、96 个 if 分支）拆分为 7 个专用处理器模块（`processors_text.py`、`processors_math.py`、`processors_datetime.py`、`processors_encoding.py`、`processors_validation.py`、`processors_data.py`）加 1 个共享助手模块（`_proc_helpers.py`），原函数缩减为 55 行委托分发；HTTP/文件/结构化处理器分别抽离到 `processors_network.py`、`processors_files.py`、`processors_structured.py`；`registry.py` 从 2352 行降至 1922 行。
- `shortcut_command_exec.py` 命令执行去重：将 `_execute_command()` 与 `run_command_capture()` 入口处的值占位符替换、外部变量安全检查、变量解析逻辑统一抽取到 `_prepare_command_for_execution()`；捕获路径的通用失败结果与 builtin 结果包装抽到 `_capture_error_result()` / `_capture_builtin_result()`；`run_command_capture()` 内部 on_update 与 no-on_update 两条路径的重复输出处理逻辑提取为 5 个共享助手（`_decode_capture_output()`、`_build_capture_payload()`、`_build_capture_cancel_result()`、`_build_capture_success_result()`、`_build_bash_fallback_result()`），消除约 270 行重复代码。
- `_check_new_processes()` 进程检测移至后台线程：不再在 GUI 线程调用 `psutil.process_iter()`，改为后台线程扫描后通过 Qt 信号回传主线程处理，消除每 10 秒 100–500 ms 的周期性 UI 卡顿。
- UI 信号连接生命周期治理：修复 `CommandPanelWindow` 全局 `focusChanged` 连接未释放问题；修复 `tooltip_helper`、`custom_tooltip`、`icon_grid`、`config_history_window` 的无父 QTimer 问题（`ui/` 与 `core/` 下已无 `QTimer()` / `QTimer(None)`）；`CommandDialog` / `UrlDialog` 孤儿线程保活列表增加已完成清理和数量上限；为 `chain_dialog.py` 添加 `closeEvent` 清理后台测试线程和动画定时器。
- `tooltip_helper.py` 主题读取优化：Tooltip 主题改为模块级缓存，避免每次显示提示时走 DataManager 实例化流程；首次缓存读取失败时记录 debug 日志；tooltip 延迟定时器绑定到 widget 父对象随销毁自动停止。
- `core/chain/__init__.py` 导出列表合并：合并冲突遗留的两份 `__all__` 定义改为 `_EXTRA_ALL` 与主 `__all__` 合并去重，消除第二份完全覆盖第一份导致子模块引用丢失的问题。
- 生产代码异常日志策略：`core/chain/registry.py` 增强/扩展处理器加载失败改为 `logger.warning()`；对 6 个高危文件（`shortcut_command_exec.py`、`plugin_manager.py`、`windows_service.py`、`window_detection.py`、`popup_mixin.py`、`window_effect.py`）共 29 处 Tier 1 静默异常处理器添加 `logger.debug()` 日志；`tests/test_exception_logging_policy.py` 扩展为全生产 Python 代码门禁，当前仅测试代码保留 3 处容许 `pass`。
- C++ 钩子层重构与 DLL 完整性：`EnsureCallbackThread` 加入互斥锁保护消除并发竞态，共享变量改为 `std::atomic`，Install/Uninstall/ThreadProc 统一为 `HookContext` 结构体（消除约 400 行重复代码），安全调用函数合并为 `SafeInvokeAny`；`hooks.dll` 加载前校验 SHA-256 哈希值，`reset()` 先卸载鼠标/键盘钩子并清理全局热键再释放 DLL 引用，防止悬空钩子回调。
- 12 个 UI 文件移除 `sys.path.insert`（`tray_app.py`、`log_window.py`、`welcome_guide.py`、`main_window.py`、`icon_grid.py`、`folder_panel.py`、`settings_panel.py`、`shortcut_dialog.py`、`batch_launch_dialog.py`、`hotkey_dialog.py`、`url_dialog.py`、`file_selection.py`），`ui/` 下已无 `sys.path.insert` / `sys.path.append`，统一依赖入口点路径管理。
- chain/registry.py 测试覆盖：新增 `tests/test_chain_registry_processors.py`（121 个测试），覆盖全部 8 个新处理器模块及 `_execute_extra_processor()` 委托分发；新增 `tests/test_issue_00_quick_wins.py` 覆盖 SleepMixin、HTTP SSRF、敏感请求头、`__all__` 合并、hooks reset 等快速修复项；配合已有的 `test_enhanced_processors.py`、`test_extended_processors.py`、`test_math_processors.py` 共 304 个测试全部通过。
- 插件系统：命令软超时调整为 30 秒，新增受权限保护的内置命令注册接口，`.qlzip` 安装限制放宽至 150 MB / 1000 文件，HTTP API 收紧请求边界减少注入风险，命令参数白名单同步支持新字段和 outputs 契约。
- 插件分发：发布包不再复制插件源码，截图 OCR 专用依赖从主程序剥离，OCR 插件内置 `wxPython` 但不内置 `python.exe`。
- 命令面板：底部按钮改为自适应网格布局，`hash`/`tls`/`json`/`jwt`/`port` 内置命令补齐结构化参数和标准 outputs。
- 模块注册表支持插件提供的外部 manifest 并在禁用后自动回退，动作链画布运行结果优先按 `node_id` 映射，主配置窗口双击编辑按类型分发到对应编辑器。
- 文件选择统一改为非原生 Qt 对话框并套用项目主题，C++ DLL 钩子回调从单槽挂起改为有界 FIFO 队列。
- 钩子可靠性：安装加入退避重试（500ms/2s/5s）和 `is_installed` 健康检查自动恢复，键盘钩子改为依赖注入（移除 `sys.modules["__main__"]` 耦合），DLL 加载失败支持 `reset()` 重新加载，失败时提供存根类上层无需判空。
- 线程安全：对话框移除 `QThread.terminate()` 改为协作式取消，插件命令改用全局共享线程池避免资源碎片化，启动线程添加 `atexit` 生命周期管理移除 `daemon=True`，跨线程信号连接显式指定 `QueuedConnection`。
- 构建与代码质量：发布门禁新增覆盖率检查（`--cov-fail-under=70`），mypy 全局启用 `check_untyped_defs`，清理 17 处 `is_win11()` 冗余判断，动作链实现版本迁移链框架，配置备份/恢复改用 `QThread` 避免阻塞主线程。
- UI 细节：配置窗口拖拽增加屏幕边界约束，Toast 隐藏时清除单例引用允许 GC，`processEvents()` 滥用全面修复（无效调用移除、重绘制调用替换为 `repaint()`、DPI 同步改用 `ExcludeUserInputEvents` 排除用户输入）。

### Fixed

- 修复所有编辑器中图标反转（浅色/深色）设置无法保存的问题，替换旧版依赖式复选框为独立控制并消除初始化时的意外重置。
- 修复颜色滤镜多个参数和效果问题：12 个字段未注册到 `config_validation._INT_RANGES` 导致启动时被静默重置；滑块调节后不实时反映改用独立 `color_filter_changed` 信号；覆盖层遮挡 UI 文字图标改为 DWM Acrylic 着色；色温系数不足提高至 0.25–0.50；Acrylic 和底色 Alpha 滑块无效扩展取值范围并接入 DWM 合成计算。
- 修复版本比较运算符优先级 bug。
- 修复弹窗和配置窗口双击空白区域刷新时不必要地重建 DWM 窗口效果导致视觉闪烁的问题。
- 修复 Windows 10 兼容性、安装报错及 UI 显示异常。
- 修复 shortcut 命令执行时运行时参数和确认状态写回原始配置导致连续执行串值的问题。
- 修复批量启动窗口图标闪烁、搜索结果慢、编辑时图标丢失/污染、保存后类型引用错误等问题。
- 修复主题链路中父级缺少主题时回退到分散样式的问题，统一按父级、应用属性和暗色默认值解析。
- 修复弹窗和配置子窗口仍可能使用默认系统窗口边框的问题，统一改为自定义窗口外壳。
- 修复插件搜索源跨插件重名互相覆盖的问题，搜索源 ID 自动加命名空间并支持注册失败事务回滚。
- 修复 `ui/tray_app.py` 信号连接使用未导入的 `Qt` 导致启动崩溃（`NameError`）。
- 修复 `ui/utils/global_hotkey.py` 中 `_HotkeyEventFilter` 不是 `QAbstractNativeEventFilter` 子类导致 `installNativeEventFilter()` 报 `unexpected type '_HotkeyEventFilter'` 错误的问题，新增 `tests/test_global_hotkey.py` 防回归。

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
