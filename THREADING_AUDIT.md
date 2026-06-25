# QuickLauncher 线程体系审计与改进方案

> **Threading System Audit & Improvement Plan**
>
> - 审计版本 / Audited Version: `QuickLauncher V1.6.3.7`
> - 审计范围 / Scope: 当前 main 分支所有 `*.py` 文件中与线程、并发、生命周期相关的实现
> - 审计方式 / Method: 全量代码静态扫描 + 关键路径动态分析 + 现有测试交叉验证
> - 适用读者 / Audience: 核心维护者、架构师、稳定性责任人
> - 关联文档 / Related: [`QUALITY_AUDIT_1.6.2.0.md`](./QUALITY_AUDIT_1.6.2.0.md) · [`UI_OPTIMIZATION_PLAN.md`](./UI_OPTIMIZATION_PLAN.md) · [`CHANGELOG.md`](./CHANGELOG.md)
> - **实施状态 / Implementation Status**: ✅ **阶段 1 (P0) 全部完成** + ✅ **阶段 2 (P1) 全部完成** + ✅ **阶段 3 (P2) 核心项已完成**

---

## 目录 / Table of Contents

- [0. 文档信息 / Document Info](#0-文档信息--document-info)
- [1. 现状盘点 / Current State](#1-现状盘点--current-state)
  - [1.1 并发模型分层 / Concurrency Model Layers](#11-并发模型分层--concurrency-model-layers)
  - [1.2 池与线程清单 / Pool & Thread Inventory](#12-池与线程清单--pool--thread-inventory)
  - [1.3 关键文件清单 / Key Files by Layer](#13-关键文件清单--key-files-by-layer)
  - [1.4 已有保护机制 / Existing Protection Mechanisms](#14-已有保护机制--existing-protection-mechanisms)
- [2. 风险清单 / Risk Register](#2-风险清单--risk-register)
  - [2.1 P0 — 崩溃日志缺失 / Crash Logging Gaps](#21-p0--崩溃日志缺失--crash-logging-gaps)
  - [2.2 P1 — 生命周期与竞态 / Lifecycle & Races](#22-p1--生命周期与竞态--lifecycle--races)
  - [2.3 P2 — 抽象与可维护性 / Abstraction & Maintainability](#23-p2--抽象与可维护性--abstraction--maintainability)
- [3. 改进路线 / Improvement Roadmap](#3-改进路线--improvement-roadmap)
  - [3.1 阶段 1：补全崩溃日志 / Stage 1: Crash Logging](#31-阶段-1补全崩溃日志--stage-1-crash-logging)
  - [3.2 阶段 2：线程生命周期安全 / Stage 2: Lifecycle Safety](#32-阶段-2线程生命周期安全--stage-2-lifecycle-safety)
  - [3.3 阶段 3：抽象与统一 / Stage 3: Abstraction Unification](#33-阶段-3抽象与统一--stage-3-abstraction-unification)
  - [3.4 阶段 4：测试守门 / Stage 4: Test Gates](#34-阶段-4测试守门--stage-4-test-gates)
- [4. 风险矩阵 / Risk Matrix](#4-风险矩阵--risk-matrix)
- [5. 附录 / Appendix](#5-附录--appendix)
  - [5.1 关键代码引用索引 / Key Code Reference Index](#51-关键代码引用索引--key-code-reference-index)
  - [5.2 现有测试覆盖矩阵 / Existing Test Coverage Matrix](#52-现有测试覆盖矩阵--existing-test-coverage-matrix)
  - [5.3 不在本次审计范围 / Out of Scope](#53-不在本次审计范围--out-of-scope)

---

## 0. 文档信息 / Document Info

### 审计快照 / Audit Snapshot

| 指标 / Metric | 数量 / Count | 说明 / Notes |
|---|---|---|
| 涉及 `*.py` 文件数 | ~60+ | 含核心 (core)、UI (ui)、插件 (plugins)、测试 (tests) |
| `threading.Thread` / `QThread` 派发点 | ~20+ | 含 raw thread + Qt worker pattern |
| `concurrent.futures.ThreadPoolExecutor` 实例 | 5 (named) + 散落 | 5 个命名池 + 若干 ad-hoc |
| `QThread` 子类数 | ~10 | `FileSelectionThread`、`DiagnosticsCollectThread` 等 |
| `QObject` worker (moveToThread 模式) | 6 | `_IconLoadWorker` 等 |
| `threading.Lock` / `RLock` 实例 | 58 处 | 跨核心/UI/服务层 |
| `threading.Event` 用例 | 10+ | 取消、就绪、关闭 |
| P0 修复回归测试 | 12 项 | `tests/test_qthread_self_delete_later_regression.py` |
| 已识别风险条目 | 14 项 | 分布 P0×4、P1×6、P2×4 |

### 术语约定 / Terminology

| 术语 | 含义 |
|---|---|
| Worker 线程 | 执行实际工作的后台线程（非 GUI 主线程） |
| 主线程 / Main Thread | Qt 事件循环所在的 GUI 线程 |
| 命名池 / Named Pool | `executor_manager` 注册的常驻 `ThreadPoolExecutor` |
| 守护线程 / Daemon Thread | `daemon=True` 的 `threading.Thread`；进程退出时强制终止 |
| 代次号 / Generation | 标识启动批次的单调递增整数，用于丢弃过期回调 |
| 协作取消 / Cooperative Cancellation | 通过 `threading.Event` 通知工作线程主动退出 |
| VEH | Windows Vectored Exception Handler，向量化异常处理器 |

---

## 1. 现状盘点 / Current State

### 1.1 并发模型分层 / Concurrency Model Layers

QuickLauncher 使用 **5 层并发的混合架构 (5-layer hybrid concurrency model)**：

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 5: 进程外常驻 Out-of-process Persistent                    │
│   subprocess + JSON-over-socket + heartbeat + 能力协商           │
│   用于 / Used by: 重量级插件 (QR/OCR 等)                          │
│   代表 / Files:  core/plugin_worker_runtime.py:80                │
├──────────────────────────────────────────────────────────────────┤
│ Layer 4: 进程内长驻 In-process Persistent (daemon threads)       │
│   threading.Thread(daemon=True) + signal/slot bridge             │
│   用于 / Used by: 插件 IPC、QR/OCR 解码                          │
│   代表 / Files:  plugins/qr_code_scanner/qr_worker.py:64         │
│                 plugins/screenshot_ocr/ocr_worker.py:81          │
├──────────────────────────────────────────────────────────────────┤
│ Layer 3: Qt 工作线程 QThread + Worker Pattern                    │
│   QThread + QObject worker (moveToThread) + signal/slot          │
│   用于 / Used by: UI 异步加载、诊断、文件选择                     │
│   代表 / Files:  ui/diagnostics_window.py:49                     │
│                 ui/launcher_popup/file_selection.py:160          │
│                 ui/config_window/icon_grid.py:1606              │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2: 注册后台线程 Registered Background Threads              │
│   threading.Thread + start_background_thread + 弱引用注册表      │
│   用于 / Used by: 通用后台任务、对话框测试                        │
│   代表 / Files:  core/background_tasks.py:29                     │
├──────────────────────────────────────────────────────────────────┤
│ Layer 1: 命名线程池 Named Thread Pools                           │
│   concurrent.futures.ThreadPoolExecutor + ExecutorManager        │
│   用于 / Used by: 命令执行、流 I/O、插件搜索、进程检查            │
│   代表 / Files:  core/executor_manager.py:31                     │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 池与线程清单 / Pool & Thread Inventory

#### Layer 1 — 命名线程池 (`core/executor_manager.py:14-26`)

| 池名 / Pool Name | max_workers | thread_name_prefix | 用途 / Purpose |
|---|---|---|---|
| `command` | 8 | `CmdExecPool` | 短命令执行 |
| `stream-io` | 4 | `CmdStreamIO` | 命令输出捕获 |
| `plugin-search` | 6 | `PluginSearch` | 插件搜索 |
| `plugin-search-coordinator` | 4 | `PluginSearchCoordinator` | 搜索协调 |
| `process-check` | 1 | `QLProcessCheck` | 进程存在性检查 |

#### Layer 2 — 注册后台线程 (`start_background_thread`)

| 调用方 / Caller | 用途 |
|---|---|
| `ui/config_window/test_task_runner.py:46` | 对话框测试任务 |
| (其他 ad-hoc 调用方待补全) | — |

#### Layer 3 — `QThread` 子类清单

| 类名 | 文件:行 | 用途 |
|---|---|---|
| `FileSelectionThread` | `ui/launcher_popup/file_selection.py:160` | Explorer 选中文件探测 |
| `FolderSyncWorker` | `ui/launcher_popup/popup_window_helpers.py` | 文件夹同步 |
| `DiagnosticsCollectThread` | `ui/diagnostics_window.py:49` | 诊断信息收集 |
| `DiagnosticsFixThread` | `ui/diagnostics_window.py:64` | 诊断修复应用 |
| `ShortcutHealthScanThread` | `ui/shortcut_health_window.py:23` | 快捷方式健康扫描 |
| `ShortcutHealthFixThread` | `ui/shortcut_health_window.py:57` | 快捷方式修复 |
| `FaviconCacheCleanThread` | `ui/shortcut_health_window.py:41` | favicon 缓存清理 |
| `IconCacheCleanThread` | `ui/tray_app.py:44` / `ui/tray_workers.py:12` | 图标缓存清理 |
| `ExportThread` | `ui/config_window/settings_helpers.py:41` | 配置导出 |
| `ImportThread` | `ui/config_window/settings_helpers.py:59` | 配置导入 |
| `_BackupThread` | `ui/config_window/settings_data_actions.py:142` | 全量备份 |
| `_RestoreThread` | `ui/config_window/settings_data_actions.py:203` | 全量恢复 |
| `_FactoryResetThread` | `ui/config_window/settings_data_actions.py:363` | 工厂重置 |
| `_IconLoadThread` | `ui/config_window/shortcut_dialog.py:50` | 快捷方式对话框图标加载 |

#### Layer 3 — `QObject` Worker (moveToThread) 清单

| 类名 | 文件:行 | 用途 |
|---|---|---|
| `_IconLoadWorker` | `ui/config_window/icon_grid.py:361` | 图标网格图标加载（grid 版本） |
| `_IconLoadWorker` | `ui/config_window/icon_grid_helpers.py:218` | 图标网格图标加载（helpers 版本） |
| `IconLoadWorker` | `ui/config_window/icon_load_worker.py:13` | 图标加载（独立模块版本） |
| `_BatchFaviconFetchWorker` | `ui/config_window/icon_grid.py:457` | 批量 favicon 获取（grid） |
| `_BatchFaviconFetchWorker` | `ui/config_window/icon_grid_helpers.py:248` | 批量 favicon 获取（helpers） |

> ⚠️ **重复定义警告 / Duplication Warning**: `_IconLoadWorker` / `_BatchFaviconFetchWorker` 存在三处/两处实现，签名/语义高度相似。详见 [§2.3.1](#231-_iconloadworker--_batchfaviconfetchworker-三处重复重复定义)。

#### Layer 4 — 进程内长驻守护线程

| 线程名 / Thread Name | 派发点 | 用途 |
|---|---|---|
| `QrWorkerIPC` | `plugins/qr_code_scanner/qr_worker.py:64` | 监听 host IPC 请求 |
| `QrDecode` | `plugins/qr_code_scanner/qr_worker.py:125` | 一次性 QR 解码 |
| `OcrWorkerIPC` | `plugins/screenshot_ocr/ocr_worker.py:81` | 监听 host IPC 请求 |
| `OcrRecognition` | `plugins/screenshot_ocr/ocr_worker.py:157` | 一次性 OCR 识别 |

#### Layer 5 — 进程外常驻 Plugin Worker

- `PersistentPluginWorker` (`core/plugin_worker_runtime.py:80`)
- 由 `PluginWorkerSupervisor` (`core/plugin/worker_supervisor.py:16`) 管理生命周期
- 故障熔断：`MAX_CONSECUTIVE_FAILURES = 5`、`QUARANTINE_SECONDS = 300`

### 1.3 关键文件清单 / Key Files by Layer

| 层 | 核心文件 | 关键职责 |
|---|---|---|
| L1 | `core/executor_manager.py` | 命名池注册、shutdown、drain |
| L2 | `core/background_tasks.py` | 线程注册表、join、弱引用 |
| L3 | `ui/utils/qt_thread_cleanup.py` | 非阻塞停机、延迟回收列表 |
| L3 | `ui/launcher_popup/popup_data_refresh.py` | 文件检测线程、文件夹同步线程 |
| L3 | `ui/config_window/icon_grid.py` | 图标加载、favicon 批量获取 |
| L3 | `ui/diagnostics_window.py` | 诊断线程 |
| L3 | `ui/shortcut_health_window.py` | 健康扫描/修复线程 |
| L3 | `ui/tray_app.py` / `ui/tray_mixins/shutdown_mixin.py` | 图标缓存清理线程 |
| L3 | `ui/config_window/settings_data_actions.py` | 备份/恢复/重置线程 |
| L4 | `plugins/qr_code_scanner/qr_worker.py` | QR 插件 worker |
| L4 | `plugins/screenshot_ocr/ocr_worker.py` | OCR 插件 worker |
| L5 | `core/plugin_worker_runtime.py` | 进程外 worker runtime |
| L5 | `core/plugin/worker_supervisor.py` | 进程外 worker 监管 |
| 通用 | `core/cancellation.py` | `CancellationToken` |
| 通用 | `core/shortcut_command_exec.py:63` | `MainThreadInvoker` |
| 通用 | `core/command_execution_service.py:49` | `CommandHandle` 取消事件 |
| 崩溃 | `bootstrap/logging_init.py:162` | faulthandler + VEH 安装 |
| 关闭 | `ui/tray_mixins/shutdown_mixin.py` | 进程退出时线程统一停机 |

### 1.4 已有保护机制 / Existing Protection Mechanisms

#### 1.4.1 互斥锁覆盖图 / Lock Coverage Map

下表列出 58 处 `threading.Lock` / `RLock` 实例，按模块归类（完整 file:line 见 [§5.1](#51-关键代码引用索引--key-code-reference-index)）：

| 模块 / Module | 锁数 | 主要保护对象 |
|---|---|---|
| `core/data_manager.py` | 5 | 实例化、保存、写入 |
| `core/config_state.py` | 4 | 状态机 |
| `core/command_registry.py` | 3 | 搜索 future、命令结果、搜索源 |
| `core/plugin_worker_runtime.py` | 3 | socket 发送、请求锁、状态锁 |
| `core/executor_manager.py` | 2 | 池 shutdown、closed 标志 |
| `core/shortcut_executor.py` | 2 | 前台窗口锁、热键锁 |
| `core/command_execution_service.py` | 2 | CommandHandle cancel、futures 集合 |
| `core/plugin_manager.py` | 1 | 插件执行器注册表 |
| `core/plugin/worker_supervisor.py` | 1 | supervisor 全局状态 |
| `core/folder_watcher.py` | 1 | 文件夹监视器 |
| `core/shortcut_command_exec.py` | 7+ | 各种命令子路径 |
| `core/clipboard_service.py` | 1 | 剪贴板状态 |
| `core/search_history.py` | 2 | 历史记录 |
| `core/event_log.py` | 1 | 事件日志 |
| `core/diagnostics.py` | 1 | 脱敏字典 |
| `core/background_tasks.py` | 1 | 注册表 |
| 其他 (~15 处) | 1 each | 限流器、路径安全、COM 探测等 |

#### 1.4.2 协作取消覆盖图 / Cancellation Coverage

| 路径 / Path | 取消机制 | 触发方 |
|---|---|---|
| `CommandHandle._cancel_event` (`core/command_execution_service.py:56`) | `threading.Event` | `CommandHandle.cancel()` |
| `CancellationToken` (`core/cancellation.py:15`) | `threading.Event` 包装 | 显式 `cancel(reason)` |
| `FileSelectionThread.context` (`ui/launcher_popup/file_selection.py:175`) | context 内的 request_id 与 `_file_check_seq` 配合 | 主线程发起新请求 |
| `_IconLoadWorker._cancel_requested` (`ui/config_window/icon_load_worker.py:20`) | 布尔标志 | `stop_qthread_nonblocking` |
| `_BatchFaviconFetchWorker._cancel_requested` (`ui/config_window/icon_grid.py:468`) | 布尔标志 | 同上 |
| `PluginWorkerSupervisor` 熔断 (`core/plugin/worker_supervisor.py:24-25`) | 连续失败计数 + 隔离期 | 5 次连续失败 → 隔离 300s |
| `executor_manager.drain()` (`core/executor_manager.py:62`) | `cancel_futures=True` | shutdown 时 |
| `_process_check_cancel_event` (`ui/tray_app.py`) | `threading.Event` | shutdown_mixin 触发 |

#### 1.4.3 代次号覆盖图 / Generation Counter Coverage

代次号 (Generation Counter) 用于在多轮启动/取消场景下丢弃过期回调：

| 位置 / Location | 计数器 | 用途 |
|---|---|---|
| `ui/config_window/icon_grid.py:1097` | `_icon_load_generation` | 图标加载批次 |
| `ui/config_window/icon_grid.py:1098` | `_favicon_fetch_generation` | favicon 批量获取批次 |
| `ui/launcher_popup/popup_data_refresh.py:575` | `_blank_refresh_generation` | 空白区刷新批次 |
| `ui/launcher_popup/popup_data_refresh.py:640` | `_folder_sync_refresh_seq` | 文件夹同步刷新批次 |
| `ui/launcher_popup/popup_data_refresh.py:283` | `_file_check_seq` | 文件检测请求序列 |
| `ui/launcher_popup/popup_data_refresh.py:386` | `request_id` (SelectionTriggerContext) | 选中文件上下文 |

#### 1.4.4 P0 反模式修复证据 / P0 Anti-pattern Fix Evidence

> **重要成就 / Significant Achievement**: 项目已主动修复 12 处 `QThread.finished.connect(self.deleteLater)` 反模式（self-deleteLater 会导致 sender 处于"已 delete 但信号已 enqueue"中间态）。

相关回归测试：`tests/test_qthread_self_delete_later_regression.py` (461 行)

| 编号 | 修复位置 |
|---|---|
| P0-01 | `ui/config_window/batch_launch_dialog.py:_icon_thread` |
| P0-02 | `ui/config_window/settings_data_actions.py:export_thread` |
| P0-03 | `ui/config_window/settings_data_actions.py:import_thread` |
| P0-04 | `ui/config_window/settings_data_actions.py:_FactoryResetThread` |
| P0-05 | `ui/launcher_popup/file_selection.py:FileSelectionThread` |
| P0-06 | `ui/launcher_popup/popup_window_helpers.py:FolderSyncWorker` |
| P0-07 | `ui/tray_mixins/shutdown_mixin.py:IconCacheCleanThread` |
| P0-08 | `ui/diagnostics_window.py:DiagnosticsCollectThread` |
| P0-09 | `ui/diagnostics_window.py:DiagnosticsFixThread` |
| P0-10 | `ui/shortcut_health_window.py:ShortcutHealthScanThread` |
| P0-11 | `ui/shortcut_health_window.py:ShortcutHealthFixThread` |
| P0-12 | `ui/shortcut_health_window.py:FaviconCacheCleanThread` |

---

## 2. 风险清单 / Risk Register

风险按严重度排序：**P0** (数据/稳定性可能受损) → **P1** (生命周期/竞态) → **P2** (可维护性)。

### 2.1 P0 — 崩溃日志缺失 / Crash Logging Gaps

#### 2.1.1 无 `sys.excepthook` / `threading.excepthook`

| 项 | 值 |
|---|---|
| 严重度 | **P0** |
| 根因定位 | `bootstrap/logging_init.py:162` `setup_faulthandler()` |
| 触发场景 | 任何 raw `threading.Thread` 派发的工作线程抛出未捕获 `Exception`/`BaseException` |
| 当前行为 | `faulthandler` 仅捕获 C 级别 segfault/abort 等硬崩溃；Python `Exception` 被静默吞掉 |
| 影响 | (a) 失败原因无法追溯；(b) 进程可能继续运行在不一致状态；(c) 关键 worker 静默死锁 |
| 受影响路径 | 全部 `start_background_thread` 调用方；`plugins/qr_code_scanner/qr_worker.py:64` IPC 线程；`plugins/screenshot_ocr/ocr_worker.py:81` IPC 线程 |
| 验证证据 | `grep "excepthook" -r .` → 0 matches |
| 修复状态 | ✅ **已修复** — `_install_excepthooks()` 在 `setup_faulthandler()` 中自动安装 |

#### 2.1.2 `start_background_thread` 不捕获 target 异常

| 项 | 值 |
|---|---|
| 严重度 | **P0** |
| 根因定位 | `core/background_tasks.py:43-47` |
| 触发场景 | 通过 `start_background_thread` 启动的目标函数抛出异常 |
| 当前行为 | `_run` 包装器仅在 `finally` 中注销线程，**未捕获** `target(*args, **kwargs)` 的异常 |
| 影响 | Python 自动打印到 stderr（在打包后的 Nuitka/frozen 运行时可能不可见）；注册表正常清理但错误消失 |
| 建议方案 | 增加 `try/except BaseException as exc` → 记录到全局线程错误日志 |
| 修复状态 | ✅ **已修复** — 增加 `try/except BaseException` + `record_thread_error()` + `raise` 继续传播 |

#### 2.1.3 插件解码线程无 try/except

| 项 | 值 |
|---|---|
| 严重度 | **P0** |
| 根因定位 | `plugins/qr_code_scanner/qr_worker.py:125-130` (QrDecode 线程) ；`plugins/screenshot_ocr/ocr_worker.py:157-162` (OcrRecognition 线程) |
| 触发场景 | QR 解码失败 / OCR 引擎异常 / 临时图片损坏 |
| 当前行为 | 守护线程启动 `target=_decode`，无任何异常捕获；解码失败时整个 worker 静默卡死 |
| 影响 | 插件响应永久未到达；上层 UI 一直转圈或超时 |
| 建议方案 | 在 `target=` 入口统一增加 `try/except` 包装，调用统一 `record_thread_error(name, exc)` |
| 修复状态 | ✅ **已修复** — 增加 `_decode_wrapper` / `_recognize_wrapper` 捕获 BaseException |

#### 2.1.4 QThread.run 错误上报不统一

| 项 | 值 |
|---|---|
| 严重度 | **P0** |
| 根因定位 | 10+ 处 `def run(self)` 实现 (详见 [§1.2 Layer 3 清单](#layer-3--qthread-子类清单)) |
| 触发场景 | 任意 QThread 工作函数异常 |
| 当前行为 | 各 QThread 自定义 `finished_signal`/`finished` payload 各异；缺少 `thread_name`/`thread_id`/结构化 `stack` |
| 影响 | 错误归因困难；dignostics 中心无法聚合 |
| 建议方案 | 抽取统一装饰器 `logged_run(thread_name: str)`，强制 `try/except BaseException` + 结构化错误日志 |

### 2.2 P1 — 生命周期与竞态 / Lifecycle & Races

#### 2.2.1 `_deferred_qthreads` 无锁保护

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `ui/utils/qt_thread_cleanup.py:16` |
| 触发场景 | 托盘退出 + 弹窗退出 + 配置窗口退出并发调用 `stop_qthread_nonblocking` |
| 当前行为 | `_deferred_qthreads` 是模块级 `list`，`append/remove` 无锁 |
| 影响 | (a) `remove()` 抛 `ValueError`（已有 try/except 兜底）；(b) 极端时 `list` 内部状态可能损坏 |
| 建议方案 | 引入 `threading.Lock` 包裹所有 `append/remove/iterate` |
| 修复状态 | ✅ **已修复** — 新增 `_DEFERRED_LOCK` 包裹所有写操作 + `deferred_qthread_count()` |

#### 2.2.2 MainThreadInvoker 启动顺序脆弱

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `core/shortcut_command_exec.py:63-84` |
| 触发场景 | 任意 `init_main_thread_invoker()` 调用前执行 `execute_signal.emit` |
| 当前行为 | `_main_thread_invoker` 是模块级单例；`emit` 时如果对象未创建则 `RuntimeError: NoneType has no attribute 'execute_signal'`；如果对象已 GC 则 `underlying C/C++ object has been deleted` |
| 影响 | 启动期竞态 → 关键命令路径崩溃 |
| 建议方案 | 改为 lazy initialization + owner 管理；进程退出时 `deleteLater` 排队 |
| 修复状态 | ✅ **已修复** — 新增 `_ensure_main_thread_invoker()` (lazy + 线程安全 + parent QApplication)；新增 `shutdown_main_thread_invoker()` 接入 teardown 链 |

#### 2.2.3 `background_tasks` weakref 竞态

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `core/background_tasks.py:25-47` |
| 触发场景 | `list_background_tasks()` 与 `join_background_tasks()` 并发执行；线程对象在两次访问之间被 GC |
| 当前行为 | `weakref.ref(thread)`；任务执行完毕后 `weakref()` 返回 `None` 触发清理 |
| 影响 | 偶发 `KeyError`（有 `pop(key, None)` 兜底）；诊断信息可能短暂缺失 |
| 建议方案 | 替换为强引用字典（线程对象小，引用开销可忽略）；保持 `is_alive()` 期间的锁持有时间最小化 |
| 修复状态 | ✅ **已修复** — `_TASKS` 直接存 `threading.Thread` 实例，不再用 `weakref` |

#### 2.2.4 `executor.drain()` 对 running future 失效

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `core/executor_manager.py:62-79` |
| 触发场景 | shutdown 时有已经在执行的 future |
| 当前行为 | `cancel_futures=True` 仅取消**未启动**的 future；`future.cancel()` 对 `RUNNING` 状态返回 False（stdlib 行为） |
| 影响 | (a) `drain(timeout)` 必须等待 future 自然完成；(b) 长任务阻塞 shutdown |
| 建议方案 | 文档明示此行为；新增 `running_futures()` API；下游调用方在提交时主动检查 `CancellationToken` |
| 修复状态 | ✅ **已修复** — `drain()` docstring 已补充 running-future 说明；新增 `running_futures()` API |

#### 2.2.5 COM 初始化配对失衡

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `ui/config_window/icon_load_worker.py:25-66` ；`ui/config_window/icon_grid.py:375-418` |
| 触发场景 | worker `run()` 内调用 `ctypes.windll.ole32.CoInitialize`；外部 cancel 在 init 后、uninit 前发生 |
| 当前行为 | `try/finally` 保证 uninit 一定执行；多个 worker 同时存在时引用计数错误（COM 是 apartment 级） |
| 影响 | 偶发 COM 错误：`CoInitialize has not been called` / `RPC_E_WRONG_THREAD` |
| 建议方案 | 改用 `pythoncom.CoInitialize` + `CoUninitialize` 配对；记录 COM apartment 类型；或改用 Qt 线程（已有自己的 COM 上下文） |
| 修复状态 | ✅ **已修复** — 三处 `_IconLoadWorker` 均改用 `pythoncom.CoInitialize()` + `com_initialize()` 基类方法；`icon_grid_helpers.py` 版本补全了 COM 初始化 |

#### 2.2.6 缺 `aboutToQuit` 统一钩子

| 项 | 值 |
|---|---|
| 严重度 | **P1** |
| 根因定位 | `bootstrap/lifecycle.py` (未注册 `QApplication.aboutToQuit` 统一钩子) |
| 触发场景 | 进程退出时 |
| 当前行为 | 各组件 (`TrayAppShutdownMixin`、`PopupDataRefreshMixin.stop_background_threads`) 各自实现 teardown；调用顺序依赖混入列表 |
| 影响 | (a) 顺序耦合脆弱；(b) 新增组件必须记得接入；(c) `_deferred_qthreads` 没有强制 drain |
| 建议方案 | 在 composition root 注册 `aboutToQuit` 钩子：先 `_deferred_qthreads.drain()` → `shutdown_all_executors` → `plugin_manager.shutdown` → `MainThreadInvoker.deleteLater` |
| 修复状态 | ✅ **已修复** — `qt_thread_cleanup.py` 新增 `drain_deferred_qthreads()`；`shutdown_mixin.py` 在 teardown 链开头调用 |

### 2.3 P2 — 抽象与可维护性 / Abstraction & Maintainability

#### 2.3.1 `_IconLoadWorker` / `_BatchFaviconFetchWorker` 三处重复

| 项 | 值 |
|---|---|
| 严重度 | **P2** |
| 根因定位 | `ui/config_window/icon_grid.py:361` / `ui/config_window/icon_grid.py:457` ；`ui/config_window/icon_load_worker.py:13` ；`ui/config_window/icon_grid_helpers.py:218` / `:248` |
| 触发场景 | 任何修改需要同步 3 处 |
| 当前行为 | 三份实现的信号签名/语义高度相似但细节有差异 |
| 影响 | 维护成本高；bug fix 容易遗漏分支 |
| 建议方案 | 抽取 `BaseLoggedWorker` + 统一信号契约；保留薄包装类提供兼容性 |

#### 2.3.2 代次号 + lambda 模板分散

| 项 | 值 |
|---|---|
| 严重度 | **P2** |
| 根因定位 | 4+ 处：`icon_grid.py:1608-1620`、`popup_data_refresh.py:577/644/665`、`tray_mixins/shutdown_mixin.py:238-244` |
| 触发场景 | 编写任何带 cancel/start 的异步操作 |
| 当前行为 | 每个组件重复实现 "increase generation → start thread → connect signal with lambda gen=... → compare generation in slot" |
| 影响 | 复制粘贴式代码；新人易遗漏 generation 校验 |
| 建议方案 | 抽取 `WorkerController` 统一管理 generation 计数 + lambda 捕获 + cleanup |

#### 2.3.3 `_drain_plugin_executors` 缺中断信号

| 项 | 值 |
|---|---|
| 严重度 | **P2** |
| 根因定位 | `core/plugin_manager.py:84-102` |
| 触发场景 | 插件被 quarantine，但有长命令仍在执行 |
| 当前行为 | 硬 join 5s；超时后线程被抛弃，无后续追踪 |
| 影响 | 抛弃的线程如果仍在写文件 / 持有锁，可能造成死锁或资源泄漏 |
| 建议方案 | 先 set 协作取消事件 → join → 仍未退出则记录到线程错误日志并继续 |

#### 2.3.4 缺统一线程诊断入口

| 项 | 值 |
|---|---|
| 严重度 | **P2** |
| 根因定位 | `core/diagnostics.py` (未集成 executor/background/deferred 状态) |
| 触发场景 | 用户报告"程序卡了"，维护者需要查看线程状态 |
| 当前行为 | diagnostics 中心只展示基本运行时信息；线程池/注册线程/延迟回收/插件 worker 状态未集中暴露 |
| 影响 | 排障时间延长 |
| 建议方案 | 在 `collect_diagnostics()` 中聚合：`executor_manager.snapshot()`、`background_tasks.list_background_tasks()`、`qt_thread_cleanup.deferred_qthread_count()`、`thread_errors.get_thread_error_log()` 摘要 |

---

## 3. 改进路线 / Improvement Roadmap

> **执行原则 / Execution Principle**: 阶段 1 → 阶段 2 → 阶段 3 → 阶段 4 顺序推进。每个阶段完成后跑全量测试再进入下一阶段。

### 3.1 阶段 1：补全崩溃日志 / Stage 1: Crash Logging — ✅ **已完成**

| 编号 | 改动 | 涉及文件 | 状态 |
|---|---|---|---|
| 1.1 | 安装 `sys.excepthook` + `threading.excepthook`，写入 `crash.log` + `thread_errors.jsonl` | `bootstrap/logging_init.py:162` | ✅ 已实现 |
| 1.2 | 新建 `core/thread_errors.py`，提供 `record_thread_error()` + `get_thread_error_log()` + JSONL 持久化 + 旋转策略 | `core/thread_errors.py` (新增) | ✅ 已实现 |
| 1.3 | `_run` 包装器加 `try/except BaseException as exc`，调用 `record_thread_error` 后重新抛出让 `threading.excepthook` 兜底 | `core/background_tasks.py:43-61` | ✅ 已实现 |
| 1.4 | 插件解码线程 `target=_decode` / `target=_recognize` 加 `try/except` 包装 | `plugins/qr_code_scanner/qr_worker.py:125-130` / `plugins/screenshot_ocr/ocr_worker.py:157-162` | ✅ 已实现 |
| 1.5 | `MainThreadInvoker` 改为 lazy init + `_ensure_main_thread_invoker()` + 父对象管理 + `shutdown_main_thread_invoker()` 加入 teardown 链 | `core/shortcut_command_exec.py:63-113` / `ui/tray_mixins/shutdown_mixin.py` | ✅ 已实现 |
| 1.6 | `diagnostics.collect_diagnostics()` 集成 `get_thread_error_log()` 摘要（最近 20 条） | `core/diagnostics.py` | ✅ 已实现 |

### 3.2 阶段 2：线程生命周期安全 / Stage 2: Lifecycle Safety — ✅ **全部完成**

| 编号 | 改动 | 涉及文件 | 状态 |
|---|---|---|---|
| 2.1 | `_deferred_qthreads` 加 `threading.Lock` | `ui/utils/qt_thread_cleanup.py:16` | ✅ 已实现 |
| 2.2 | `MainThreadInvoker` 改为 lazy init + owner 管理 + 退出时 `deleteLater` | `core/shortcut_command_exec.py:63-84` | ✅ 已实现 (与 1.5 合并) |
| 2.3 | `background_tasks` 弱引用改强引用 | `core/background_tasks.py:25-26` | ✅ 已实现 |
| 2.4 | `executor.drain()` 文档补全；新增 `running_futures()` API | `core/executor_manager.py:58-62` | ✅ 已实现 |
| 2.5 | `IconLoadWorker` COM 初始化改进（改用 `pythoncom` + `com_initialize()` 基类方法） | `ui/config_window/icon_load_worker.py` / `ui/config_window/icon_grid.py` / `ui/config_window/icon_grid_helpers.py` | ✅ 已实现 |
| 2.6 | `qt_thread_cleanup` 新增 `drain_deferred_qthreads()`；teardown 链中调用 | `ui/utils/qt_thread_cleanup.py` / `ui/tray_mixins/shutdown_mixin.py` | ✅ 已实现 |

### 3.3 阶段 3：抽象与统一 / Stage 3: Abstraction Unification — ✅ **核心项已完成**

| 编号 | 改动 | 涉及文件 | 状态 |
|---|---|---|---|
| 3.1 | 新建 `core/qt_worker.py`，提供 `BaseLoggedWorker(QObject)`：内置 `error_occurred` 信号、`cancel()` 方法、`name` 属性、自动 `try/except` 包装 `run()` + COM 辅助方法 | `core/qt_worker.py` (新增) | ✅ 已实现 |
| 3.2 | 同上，提供 `WorkerController`：管理 generation 计数、lambda 捕获模板、`stop_and_cleanup()` | `core/qt_worker.py` (新增) | ✅ 已实现 |
| 3.3 | 合并 `_IconLoadWorker` 三处实现 → 改用 `BaseLoggedWorker` 派生 | `ui/config_window/icon_grid.py:361` / `ui/config_window/icon_load_worker.py:13` / `ui/config_window/icon_grid_helpers.py:218` | ✅ 已实现 |
| 3.4 | 合并 `_BatchFaviconFetchWorker` 两处实现 → 改用 `BaseLoggedWorker` 派生 | `ui/config_window/icon_grid.py:457` / `ui/config_window/icon_grid_helpers.py:248` | ✅ 已实现 |
| 3.5 | `_drain_plugin_executors` 先 set cancel event → join → 记录剩余到 `thread_errors.jsonl` | `core/plugin_manager.py:84-102` | ✅ 已实现 |

**预计工作量 / Effort**: 高（10+ 个文件，新文件 1 个）

### 3.4 阶段 4：测试守门 / Stage 4: Test Gates

| 编号 | 测试 | 验证目标 |
|---|---|---|
| 4.1 | `tests/test_thread_excepthook.py` | mock `threading.excepthook` 注入；验证 worker 异常落到 `thread_errors.jsonl` |
| 4.2 | `tests/test_deferred_qthread_locking.py` | 并发 stress `stop_qthread_nonblocking` 100 次 |
| 4.3 | 增强 `tests/test_executor_manager.py` | 补充 `running_futures()`、cancel-on-running 行为 |
| 4.4 | 增强 `tests/test_background_tasks.py` (新建) | 验证 generation 过期回调丢弃 |
| 4.5 | 增强 `tests/test_main_thread_invoker.py` (新建) | 启动期 race 验证 |

---

## 4. 风险矩阵 / Risk Matrix

以 **严重度 (Severity)** × **修复成本 (Fix Cost)** 二维分布。优先级建议：**左上角 → 右下角**。

```
严重度 \ 修复成本     低成本                   中成本                          高成本
─────────────────────────────────────────────────────────────────────────────────────
高 (P0)             2.1.2                  2.1.1                          2.1.3
                    start_background       sys/threading                  插件解码线程
                    _thread try/except     excepthook                     try/except
                                          
                                         2.1.4
                                         QThread.run 统一
                                         装饰器
─────────────────────────────────────────────────────────────────────────────────────
中 (P1)             2.2.5                  2.2.1                          2.2.2
                    COM 配对               _deferred_qthreads              MainThreadInvoker
                                          加锁                            owner 管理
                                          
                                         2.2.3                          2.2.6
                                         background_tasks               aboutToQuit
                                         强引用                          统一钩子
                                          
                                         2.2.4
                                         executor drain
                                         文档 + running_futures
─────────────────────────────────────────────────────────────────────────────────────
低 (P2)                                        2.3.4                         2.3.1
                                              diagnostics 集成               Worker 三处合并
                                              
                                              2.3.2                          2.3.3
                                              WorkerController              drain 中断信号
                                              抽象
─────────────────────────────────────────────────────────────────────────────────────
```

**建议执行顺序 / Recommended Execution Order**:

1. **第一批 (低垂果实 / Quick Wins)**: `2.1.2` → `2.2.5` → `2.2.1` → `2.2.3`
2. **第二批 (核心改进 / Core)**: `2.1.1` → `2.1.4` → `2.2.4` → `2.2.6`
3. **第三批 (结构调整 / Refactor)**: `2.3.1` → `2.3.2` → `2.2.2` → `2.1.3` → `2.3.3` → `2.3.4`

---

## 5. 附录 / Appendix

### 5.1 关键代码引用索引 / Key Code Reference Index

#### 5.1.1 P0 风险代码引用

| 风险编号 | 文件 | 行号 | 关键代码 |
|---|---|---|---|
| 2.1.1 | `bootstrap/logging_init.py` | 162-205 | `setup_faulthandler(log_dir)` — 仅装 faulthandler，无 excepthook |
| 2.1.2 | `core/background_tasks.py` | 43-47 | `def _run() → target(*args) finally unregister` — 无 try/except |
| 2.1.3 | `plugins/qr_code_scanner/qr_worker.py` | 125-130 | `threading.Thread(target=self._decode, name="QrDecode", daemon=True).start()` — 无 try/except |
| 2.1.3 | `plugins/screenshot_ocr/ocr_worker.py` | 157-162 | `threading.Thread(target=self._recognize, name="OcrRecognition", daemon=True).start()` — 无 try/except |
| 2.1.4 | `ui/diagnostics_window.py` | 57-61 | `def run(self)` try/except 结构不统一 |
| 2.1.4 | `ui/shortcut_health_window.py` | 23-55 | 同上 |
| 2.1.4 | `ui/config_window/settings_helpers.py` | 41-72 | 同上 |

#### 5.1.2 P1 风险代码引用

| 风险编号 | 文件 | 行号 | 关键代码 |
|---|---|---|---|
| 2.2.1 | `ui/utils/qt_thread_cleanup.py` | 16 | `_deferred_qthreads: list[dict[str, object]] = []` — 无锁 |
| 2.2.2 | `core/shortcut_command_exec.py` | 63-84 | `MainThreadInvoker` + `_main_thread_invoker` 单例 |
| 2.2.3 | `core/background_tasks.py` | 25-26 | `_TASKS: dict[int, tuple[weakref.ReferenceType[threading.Thread], ...]]` — 弱引用 |
| 2.2.4 | `core/executor_manager.py` | 62-79 | `def drain(self, timeout)` + `cancel_futures=True` 注释 |
| 2.2.5 | `ui/config_window/icon_load_worker.py` | 25-66 | `ctypes.windll.ole32.CoInitialize/CoUninitialize` 配对 |
| 2.2.5 | `ui/config_window/icon_grid.py` | 375-418 | 同上（grid 版本） |
| 2.2.6 | `bootstrap/lifecycle.py` | (整文件) | 无 `aboutToQuit` 钩子注册 |

#### 5.1.3 P2 风险代码引用

| 风险编号 | 文件 | 行号 | 关键代码 |
|---|---|---|---|
| 2.3.1 | `ui/config_window/icon_grid.py` | 361-455 | `_IconLoadWorker` 定义 |
| 2.3.1 | `ui/config_window/icon_load_worker.py` | 13-97 | `IconLoadWorker` 定义 |
| 2.3.1 | `ui/config_window/icon_grid_helpers.py` | 218-246 | `_IconLoadWorker` 定义（helpers 版） |
| 2.3.1 | `ui/config_window/icon_grid.py` | 457-512 | `_BatchFaviconFetchWorker` 定义 |
| 2.3.1 | `ui/config_window/icon_grid_helpers.py` | 248-288 | `_BatchFaviconFetchWorker` 定义（helpers 版） |
| 2.3.2 | `ui/config_window/icon_grid.py` | 1606-1620 | generation + lambda 模板 |
| 2.3.2 | `ui/launcher_popup/popup_data_refresh.py` | 577, 644, 665 | `QTimer.singleShot(..., lambda seq=seq: ...)` |
| 2.3.2 | `ui/tray_mixins/shutdown_mixin.py` | 238-244 | lambda capture + `setattr` 清理 |
| 2.3.3 | `core/plugin_manager.py` | 84-102 | `_drain_plugin_executors` 硬 join |
| 2.3.4 | `core/diagnostics.py` | (整文件) | 未集成线程/池状态 |

#### 5.1.4 已有保护机制引用

**互斥锁 (58 处)**:

| 文件 | 行号 | 锁 |
|---|---|---|
| `core/background_tasks.py` | 26 | `_TASKS_LOCK` |
| `core/clipboard_service.py` | 383 | `_lock` |
| `core/commands_utils.py` | 337 | `_qr_server_lock` |
| `core/command_execution_service.py` | 56, 119 | `CommandHandle._cancel_event` / `_futures_lock` |
| `core/command_results.py` | 36 | `_lock` (RLock) |
| `core/command_registry.py` | 27, 248, 252 | `_active_search_futures_lock` / `_pending_command_result_lock` / `_search_sources_lock` |
| `core/command_exec/launcher_mixin.py` | 40 | `_CMD_CACHE_DIR_LOCK` |
| `core/config_services.py` | 292, 294, 319 | cancel + lock + event |
| `core/config_state.py` | 54, 55, 73, 74 | `save_lock` / `write_lock` |
| `core/data_manager.py` | 53, 69, 70, 416, 417 | 实例锁 / save / write |
| `core/diagnostics.py` | 32 | `_redaction_lock` |
| `core/event_log.py` | 17 | `_lock` |
| `core/executor_manager.py` | 40, 92 | `ManagedExecutor._lock` / `ExecutorManager._lock` |
| `core/folder_watcher.py` | 51 | `_watcher_lock` |
| `core/hotkey_conflict_checker.py` | 12 | `_probe_lock` |
| `core/plugin_manager.py` | 49 | `_PLUGIN_EXECUTOR_REGISTRY_LOCK` |
| `core/plugin_worker_runtime.py` | 39, 103, 104 | `_send_lock` / `_request_lock` / `_state_lock` |
| `core/plugin/executor_tracker.py` | 11 | `_PLUGIN_EXECUTOR_REGISTRY_LOCK` |
| `core/plugin/host_api.py` | 83, 512 | `_persistent_helpers_lock` / `done_event` |
| `core/preprocessing/audit.py` | 13 | `_audit_lock` |
| `core/preprocessing/rate_limiter.py` | 27, 87 | `_lock` / `_limiter_lock` |
| `core/selected_text_service.py` | 95 | `_lock` |
| `core/search_history.py` | 29, 122 | `_lock` / `_history_lock` |
| `core/shortcut_command_exec.py` | 1332, 1537, 1701, 1766, 1911 | cancel_event 参数 + 内部锁 |
| `core/shortcut_executor.py` | 71, 72 | `_foreground_window_lock` (RLock) / `_hotkey_lock` |
| `core/plugin/worker_supervisor.py` | 31 | `self._lock` (RLock) |

**代次号 (Generation Counter)**:

| 文件 | 行号 | 计数器名 |
|---|---|---|
| `ui/config_window/icon_grid.py` | 1097 | `_icon_load_generation` |
| `ui/config_window/icon_grid.py` | 1098 | `_favicon_fetch_generation` |
| `ui/launcher_popup/popup_data_refresh.py` | 575 | `_blank_refresh_generation` |
| `ui/launcher_popup/popup_data_refresh.py` | 640 | `_folder_sync_refresh_seq` |
| `ui/launcher_popup/popup_data_refresh.py` | 283 | `_file_check_seq` |

**已修复的 P0 反模式 (12 处)**:

`tests/test_qthread_self_delete_later_regression.py` 覆盖 12 处 `QThread.finished.connect(self.deleteLater)` 反模式的修复。详见 [§1.4.4](#14-p0-反模式修复证据--p0-anti-pattern-fix-evidence)。

### 5.2 现有测试覆盖矩阵 / Existing Test Coverage Matrix

| 测试文件 | 覆盖范围 | 备注 |
|---|---|---|
| `tests/test_executor_manager.py` | 命名池复用、shutdown 幂等、drain 不死锁 | 68 行，3 个测试 |
| `tests/test_qthread_self_delete_later_regression.py` | 12 处 P0 反模式已修 | 461 行，12 个测试 |
| `tests/test_command_registry.py` | 多线程并发注册（20 个 thread 场景） | 1140+ 行 |
| `tests/test_event_log.py` | 多线程写入事件日志 | 312+ 行 |
| `tests/test_state_store.py` | 2 个并发写线程 | 61 行 |
| `tests/test_plugin_worker_runtime.py` | 进程外 worker 协议 | — |
| `tests/test_plugin_worker_supervisor.py` | 监管者熔断逻辑 | — |
| `tests/test_plugin_process_isolation.py` | 进程隔离 | — |
| `tests/test_shortcut_command_exec.py` | 命令执行 + 取消 | — |
| `tests/test_animation_api_safety.py` | 动画线程安全 | — |
| `tests/test_regression_import_safety.py` | 导入安全 | — |
| `tests/test_run_mode_router.py` | 运行模式路由 | — |

**测试缺口 / Coverage Gaps**:

- ❌ 无 `threading.excepthook` 行为测试
- ❌ 无 `_deferred_qthreads` 并发 stress
- ❌ 无 `MainThreadInvoker` 启动期 race 测试
- ❌ 无 `cancellation` 全局行为测试（仅分散在各业务测试中）
- ❌ 无插件 worker 异常恢复测试

### 5.3 不在本次审计范围 / Out of Scope

下列内容**未**纳入本次审计：

1. **Python 解释器内部线程模型** (CPython GIL、sub-interpreters)
2. **第三方库内部线程模型**（PyQt5、wxPython、zxingcpp、requests 等）
3. **性能基准与 profiling**（本次仅做安全审计，不做性能评估）
4. **Nuitka 编译后行为差异**（除 crash handler 已有专门处理外）
5. **跨平台兼容性**（项目主要目标平台为 Windows；macOS/Linux 不在审计范围）
6. **国际化/本地化中的线程安全**（与线程关系微弱）
7. **数据库/SQLite 线程安全**（本项目使用 JSON 文件，无 DB）
8. **网络层多线程**（HTTP/UDP/TCP 连接复用层，本项目使用 requests + ThreadPoolExecutor）

---

## 文档结束 / End of Document

- 本文档应随代码演进同步更新（建议每个 minor 版本刷新一次）
- 风险条目编号 (2.x.x) 保持稳定，新增条目接续编号
- 改进路线完成后，将对应条目标记为 ✅ RESOLVED
- 维护者变更时请同步本审计的 ownership

**审计责任人 / Audit Owner**: 待定
**最后更新 / Last Updated**: 2026-06-25
**下次复审 / Next Review**: 阶段 1 完成后
