# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.6.3.0] - Unreleased

### Added

- 命令面板新增参数 invocation 快照、runtime shortcut 副本、非敏感参数历史恢复和 `{{input}}` 统一传递。
- 新增命令输出 artifact 与 `payload["outputs"]` 契约，支持输出归一化、截断、动作链命名输出传递和默认结果动作补全。
- 动作链步骤新增 `input_binding`、`param_bindings` 和静态 `args`，编辑器提供最小配置入口。
- 命令参数支持 `label`、`placeholder`、`help`、`multiline`、`source`、`validator`、`remember` 等字段，并新增结构化参数编辑弹窗。
- 命令面板参数表单新增执行预览，敏感参数自动遮罩。
- 动作链新增模块型插件扩展点，插件可通过 `register_module()` 注册动作链模块 manifest。
- 插件 API 新增 `register_chain_processor()`，支持插件按统一 schema 注册动作链电池，并在禁用时自动清理。
- 动作链电池定义扩展为完整 schema，包含分类、描述、端口、参数、安全等级和示例。
- 动作链测试运行新增节点级快照，记录每个节点的输入、输出、状态、耗时和错误。
- 动作链属性面板支持按电池 schema 生成数字、布尔、选项、路径和多行参数控件。
- 动作链风险分析接入电池 safety 定义，可提示脚本执行、网络访问和本地文件读写风险。
- 动作链编辑器新增搜索添加栏，可快速查找并添加电池或已有快捷方式节点。
- 动作链画布支持复制/粘贴选中节点或子图，保留参数和内部连线并清理旧运行状态。
- 动作链画布支持基础自动排版，可用 `Ctrl+R` 按执行顺序整理节点布局。
- 动作链画布新增撤销/重做历史，可用 `Ctrl+Z`/`Ctrl+Y` 恢复节点、连线和布局编辑。
- 动作链新增中期数据处理电池：列表合并、切片、配对、展开、转文本，以及结构化 JSON 模板渲染。
- JSON 字段路径增强支持数组索引，例如 `items[0].name`，便于 HTTP+JSON 数据链处理。
- 批量启动新增独立 `batch_launch` 快捷方式类型、设置窗口和运行执行器，与动作链编辑器及动作链模块分离。

### Changed

- 命令面板底部按钮改为自适应网格布局，按钮等宽铺满，宽度不足时自动换成两行。
- `hash`、`tls`、`json`、`jwt`、`port` 内置命令补齐结构化参数和标准 outputs。
- 插件命令参数白名单与开发文档同步支持新参数字段和 outputs 契约。
- 模块注册表支持插件提供的外部模块 manifest，并在插件禁用后自动回退内置模块。
- 动作链画布运行结果优先按 `node_id` 映射，属性面板可查看选中节点上次运行详情。
- 主配置窗口双击编辑按快捷方式、快捷键、网址、命令、动作链、批量启动分发到对应编辑器。

### Fixed

- shortcut 命令执行不再把运行时参数、输入值、动作链值或危险命令确认状态写回原始配置对象，避免连续执行串值。
- 破坏性命令确认状态只作用于当前 invocation，不进入结果历史，避免历史重试或连续执行继承确认。
- 表格结果保存 CSV 改为标准 CSV 转义，避免逗号、引号等内容导出损坏。
- 修复批量启动窗口右键打开时图标重复抽取导致的小窗口闪烁、搜索结果慢和候选图标不完整问题。
- 修复批量启动编辑时左侧卡片图标丢失、右侧候选图标受占位图污染的问题，优先复用主配置窗口已显示图标。
- 修复批量启动保存后显示为动作链、双击误打开动作链编辑器、弹窗点击启动时找不到步骤引用的问题。

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
