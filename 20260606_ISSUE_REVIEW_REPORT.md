## QuickLauncher V1.6.3.0 — 20260606_NEXT_PLAN 问题修复状态审查报告

> 审查日期：2026-06-06  
> 审查范围：`20260606_NEXT_PLAN.md` 中全部 27 个问题的代码现状  
> 审查方法：逐问题对照代码实现，验证修复落地情况与代码合理性

---

### 总览

| 状态 | 数量 | 占比 |
|------|------|------|
| 已修复 | 11 | 41% |
| 部分修复 | 14 | 52% |
| 未修复 | 2 | 7% |

27 个问题中，11 个已完整修复，14 个有部分改善但仍存核心差距，2 个基本未动。修复集中在 P0 安全边界和 P1 执行模型两大优先级，P2 一致性与可维护性层面的修复进度相对较慢。

---

### 逐项状态

#### P0 架构与安全边界问题

**#1 插件权限模型默认信任等级 — 已修复**

默认 `trust_level` 从 `local-trusted` 改为 `community-unverified`（`plugin_manager.py:188`），`from_dict()` 缺失/未知值均回退到最低信任。受限 builtins 覆盖从仅 `subprocess` 扩展到 `ctypes`、`multiprocessing`、`socket`、`subprocess` 四项（`constants.py:43-50`），并新增 `PLUGIN_OS_BLOCKED_ATTRS` 封锁 `os.system`、`os.popen`、`os.startfile` 及全部 `os.exec*/spawn*` 变体（`constants.py:51-73`）。只有 `builtin` 级别插件跳过限制，`local-trusted` 和 `community-unverified` 均走受限路径。引入 `install_source` 安装来源标记，第三方包强制设为 `community-unverified`（`plugin_manager.py:1657-1671`）。

代码合理性：修复方案比计划文档更严格——不仅反转了默认信任，还让 `local-trusted` 也走受限 builtins，形成了真正的最小权限默认值。`PLUGIN_OS_BLOCKED_ATTRS` 的补充超出了原计划范围，是有效的纵深防御。

**#2 插件命令共享线程池超时不能终止 — 部分修复**

全局共享 `_SHARED_COMMAND_POOL` 已移除，改为每命令独立后台线程（`plugin_manager.py:703-758`），超时后调用方立即返回。引入 per-plugin 失败计数与隔离机制（3 次失败后自动 quarantine，`plugin_manager.py:1182-1202`）。但超时后线程仍继续运行，未引入 CancellationToken、进程级隔离或线程中断机制。

代码合理性：移除共享线程池消除了插件间相互拖死的风险，这是核心改善。但"超时后线程继续运行"的根本问题未解决。考虑到 Python 线程模型限制，建议后续引入进程级隔离作为最终方案。

**#3 插件 HTTP API 未复用统一网络防护 — 已修复**

`PluginAPI.http_request()` 现在完整调用 `validate_public_http_url()`（`plugin_manager.py:897`）、`safe_urlopen()`（`:922`）、`read_limited_response()`（`:924-928`）和 `sanitize_headers()`。HTTP 方法限制为 GET/POST/HEAD，请求体 2MB 限制，超时上限 10 秒，敏感请求头过滤完整。

代码合理性：实现完整复用了 `core/network_security.py` 的全套防护链，没有遗漏。额外的方法限制和请求头规范化属于合理的纵深防御。

**#4 动作链危险处理器 safety 运行时强制不足 — 部分修复**

`check_permission()` 不再恒定返回 True，改为基于 capability denylist 检查（`action_chain_host.py:131-147`）。`request_confirmation()` 实现了回调函数优先、自动确认设置、QMessageBox 弹窗三层逻辑（`:149-189`），无 UI 时返回 False。`_processor_safety_error()` 在每个 processor 执行前做权限检查和确认请求（`shortcut_chain_exec.py:547-583`）。所有主要公开入口（编辑器、快捷键、命令面板）均通过 module API 层传递 `host_api`。但 `_execute_shortcut_chain_runtime()` 在 `host_api=None` 时静默跳过所有安全检查（`:548-549`），且缺少审计日志。

代码合理性：核心拦截逻辑已实现，`host_api=None` 时的静默跳过是一个防御性缺口——应改为默认拒绝而非默认放行。缺少审计日志降低了事后排查能力。

**#5 动作链文件处理器路径边界和删除策略 — 部分修复**

引入 `assert_safe_user_path()` 和 `_protected_roots()`（`path_security.py:21-43, 107-130`），所有写/删操作都做路径边界检查。系统目录 denylist 覆盖 Windows 系统目录、Program Files、ProgramData、APPDATA 等。`file_delete` 强制使用 `send2trash` 或可恢复的 `shutil.move` fallback（`path_security.py:46-61`），不再永久删除。但 `file_read_text()` 未调用 `assert_safe_user_path()`，读操作路径保护不一致。

代码合理性：路径安全体系设计合理，`Path.resolve()` 有效防止 `..` 路径逃逸，`move_to_trash()` 的 fallback 策略比直接删除安全得多。读操作保护缺失是遗留风险但严重程度较低（读操作 safety 等级为 caution）。

**#6 动作链和插件 timeout "调用方超时但工作继续" — 未修复**

Processor timeout 从 `ThreadPoolExecutor` 改为 `start_background_thread()` + Event polling（`shortcut_chain_exec.py:497-544`），超时后设置 `cancel_event` 但不 join 线程。插件命令同样模式（`plugin_manager.py:703-758`）。未引入 CancellationToken 一等公民、CancellableTask 统一任务包装器或超时后资源回收机制。

代码合理性：从 ThreadPoolExecutor 改为独立线程略有改善（减少线程池开销），但核心问题——超时后线程继续运行——没有本质变化。这是 Python 线程模型的固有限制，需要进程级隔离才能彻底解决。

**#7 IPC 本地实例通道没有鉴权 — 已修复**

引入 `secrets.token_urlsafe(32)` 随机 session token（`bootstrap/ipc.py:17`），token 文件落盘 + atexit 清理（`:52-53`）。协议从裸文本改为 JSON 格式（`:79, :94`）。服务端校验 token（`:91-104`）并实施命令白名单（仅允许 `show_config`）。

代码合理性：修复方案完整覆盖了计划文档中提出的所有建议（token、JSON 协议、命令白名单、退出清理）。atexit 清理确保了 token 不会在进程退出后残留。频率限制未实现但在单实例架构下风险极低。

**#8 更新链路只有 hash 校验没有签名信任边界 — 已修复**

引入 Ed25519 签名校验（`trust.py:38-53`），纯 Python 实现不依赖外部库。签名验证贯穿 checker（`:269-281`）、downloader（hash 校验）和 installer（`:65-80`，hash + 签名双重校验）全链路。公钥通过 `signature_public_keys` 配置 pinning（`config.py:21`），`require_signature` 默认为 True。下载域名白名单限制为 `github.com` 和 `githubusercontent.com`。

代码合理性：签名信任链设计合理。注意 `signature_public_keys` 默认空元组意味着不配置公钥则更新失败——这是 by-design 的安全行为。Authenticode 和 release manifest 签名未实现，属于增强措施。

**#9 网络防护实现分散多套逻辑 — 部分修复**

5 个原始分散的网络请求点全部统一到 `core.network_security.safe_urlopen()`：`favicon_cache.py`（`:453, :562, :636`）、`downloader.py`（`:106`）、`base_client.py`（`:64`）、`plugin_manager.py`（`:922`）、`command_variables.py`（`:202`）。`favicon_cache.py` 的独立 `_safe_urlopen()` 已移除。但未创建 `NetworkGateway` 统一入口类，各模块仍各自构造 Request 和设置 timeout。

代码合理性：核心安全原语已统一收敛，所有网络请求都经过 SSRF 防护、逐跳重定向校验和响应大小限制。`NetworkGateway` 是架构层面的进一步优化，不影响当前安全性。

---

#### P1 核心执行与生命周期问题

**#10 命令执行路径巨型分支 — 部分修复**

`_execute_command()` 从约 370 行缩减至 52 行（`shortcut_command_exec.py:1235-1286`），按命令类型分发到 5 个独立方法。引入统一结果模型 `CommandResult`（`command_registry.py:210-219`）和预处理管道 `PreprocessingPipeline`（`preprocessing/pipeline.py`）。大量辅助方法已提取。但未引入 `ShellStrategy` 接口和可插拔中间件管道，文件仍 2755 行。

代码合理性：函数拆分效果明显，52 行的调度器比 370 行的巨型分支易维护得多。预处理管道的引入是合理的架构改善。ShellStrategy 接口是更深层的重构，当前改善已降低回归风险。

**#11 CommandExecutionService 每次创建 daemon thread — 已修复**

四种执行路径统一使用有界 `ThreadPoolExecutor(max_workers=8)`（`command_execution_service.py:103-106`），不再直接创建 daemon thread。引入 `CommandExecutionHandle` 任务句柄（`:47-89`），提供 cancel/wait/状态查询。实现 `shutdown(timeout=5.0)` 优雅关闭（`:125-139`）。

代码合理性：从分散的 daemon thread 到有界线程池 + 任务句柄的转变是标准的线程管理最佳实践。活动任务跟踪和优雅关闭流程完整。

**#12 插件搜索线程模型堆积后台工作 — 已修复**

引入共享 `_get_search_pool()`（6 workers，`command_registry.py:29-67`）替代每次创建临时 executor。`SearchCancelToken` 从 UI 层贯穿到搜索 handler（`:36-55`）。搜索 debounce 改为 QTimer 而非 daemon thread（`popup_search.py:441-447`）。活动 future 有完整跟踪和清理机制。

代码合理性：共享线程池 + 取消令牌 + QTimer debounce 的组合有效解决了线程堆积问题。

**#13 命令测试和动作链测试依赖孤儿线程兜底 — 部分修复**

`CommandTestThread`、`_ChainTestThread`、`_adopt_orphaned_thread()` 已全部移除。统一替换为 `DialogTestTask`（`test_task_runner.py:16-84`），清理流程为：取消 -> 等待 3 秒 -> 记录警告（不再兜底）。两个对话框的清理模式完全一致。但未复用 `CommandExecutionService`。

代码合理性：消除孤儿线程兜底是正确方向。`DialogTestTask` 提供了统一的抽象。未复用 `CommandExecutionService` 意味着测试路径和生产路径不一致，但风险可控。

**#14 无 owner 的后台线程和定时器残留 — 已修复**

引入 `core/background_tasks.py` 全局注册机制，所有后台线程通过 `start_background_thread()` 创建并注册到全局 `_TASKS` 字典（使用 weakref），接受 `owner` 参数记录归属。提供 `list_background_tasks()` / `join_background_tasks(owner)` API。QTimer 全部绑定 parent（`hotkey_manager.py:21`）。全项目无裸 `QTimer()`、`.daemon = True`、`threading.Timer(` 调用。

代码合理性：全局注册 + owner 追踪 + weakref 自动清理的设计是完善的方案。`join_background_tasks` 的超时机制和残留警告日志为关闭审计提供了基础。

**#15 DataManager 高副作用全局单例职责过重 — 部分修复**

`core/config_services.py` 中已提取 `ConfigDataStore`、`ConfigBackupService`、`ConfigRecoveryService`、`ConfigPackageService`、`SaveScheduler`、`IconRepository` 六个独立类。DataManager 内部方法已改为委托调用。但 DataManager 仍为全局单例 facade，所有公共方法仍挂在上面，API surface 未收窄。

代码合理性：内部拆分是合理的渐进策略。facade 模式保持了向后兼容。但 API surface 未收窄意味着耦合度改善有限，UI 层仍然可以访问 DataManager 的所有能力。

**#16 配置恢复/导入事务边界复杂 — 部分修复**

引入事务日志机制 `_write_transaction_journal()`（`data_manager.py:1387`），记录事务前状态快照。使用 `os.replace()` 原子替换（`config_services.py:47-81`）。实现 `_verify_transaction_consistency()` 事务后校验（`data_manager.py:1429`）。但 journal 仅用于日志，无启动时自动恢复逻辑。缺少事务超时机制。事务边界未简化。

代码合理性：原子替换和事务后校验是有效改善。journal 不用于自动恢复降低了其价值——如果事务中断，仍然依赖手动干预。

---

#### P2 一致性、测试与可维护性问题

**#17 测试数量多但关键路径真实性不足 — 部分修复**

新增 UI smoke 测试（`test_ui_smoke.py`，7 个测试）、关键修复回归测试（`test_issue_00_quick_wins.py`，8 个测试）、处理器模块测试（`test_chain_registry_processors.py`，121 个测试）。总测试数 3408 个。但 `conftest.py` 仍 mock 全部系统级模块，`integration` marker 声明了但从未使用，无关键路径独立覆盖率目标。CHANGELOG 声称覆盖率门禁 70%（第 46 行），但实际代码为 67%（`release_gate.py:17`）。

代码合理性：测试数量显著增加，smoke 测试和处理器测试是有效补充。CHANGELOG 与代码的覆盖率门禁值不一致（70% vs 67%）是需要修正的文档问题。

**#18 宽泛异常处理数量大 — 部分修复**

6 个高危文件 29 处 Tier 1 静默异常已添加 `logger.debug()` 日志。新增 `check_silent_exceptions.py` pre-commit 钩子和 `test_exception_logging_policy.py` 门禁测试。但 broad exception 总数仍 1319 处（几乎无变化），门禁基线 `--max-total 1320` 仅比实际多 1，无实际约束力。无统一 ErrorCode 枚举。

代码合理性：阻止新增静默异常是正确策略。但存量问题基本未动，门禁基线形同虚设。

**#19 插件包官方清单和实际工作区不一致 — 已修复**

CHANGELOG 第 13 行确认 `qr_code_scanner` 已被正式纳入为第 10 个官方插件包（"新增独立 `.qlzip` 形式的截图 OCR 插件包"）。`.plugins/` 目录、README 和 `OFFICIAL_PLUGIN_PACKAGE_IDS` 三方现在完全一致（均包含 `qr_code_scanner`）。此外，`check_release_artifacts.py:141-153` 实现了完整的一致性检查（检测清单外多余包和清单内缺失包），通过 CI 自动执行，防止未来再次出现不一致。

代码合理性：一致性检查机制是有效改善，将不一致问题从"可能遗漏"变为"CI 自动拦截"。

**#20 版本文档与构建产物状态未完全一致 — 已修复**

`core/version.py` 新增 `RELEASE_STATUS = "stable"` 字段（`:9`）。CHANGELOG 标记为 `2026-06-06`（非 Unreleased），与 `stable` 一致。`check_release_artifacts.py` 实现 5 项一致性检查（RELEASE_STATUS 合法性、stable + Unreleased 冲突、unreleased + 产物存在冲突、installer.iss 版本号、manifest 版本号），通过 release_gate 和 CI 集成。

代码合理性：RELEASE_STATUS 字段和自动化检查形成了完整的一致性保障。

**#21 命令结果 action 只做基础安全校验 — 部分修复**

已统一到 `core/action_executor.py` 的 `execute_command_action()`，两个 UI 入口走同一路径。审计日志通过 `core.event_log.log_event` 实现，记录动作类型、来源、脱敏后的值。但校验仍以基础白名单 + 格式检查为主，缺少深度路径防护。

代码合理性：统一执行路径和审计日志是核心改善。校验深度不足属于后续增强。

**#22 Favicon 网络防护重复实现 — 已修复**

`_safe_urlopen()` 已完全移除，所有网络请求统一使用 `core.network_security.safe_urlopen()`（`favicon_cache.py:453, :562, :636`）。`UnsafeUrlError` 被正确转换为模块内的 `UnsafeFaviconUrlError`。

**#23 自动更新下载器直接使用 urlopen — 已修复**

`downloader.py`（`:106`）和 `base_client.py`（`:64`）都已迁移到 `safe_urlopen()`。`downloader.py` 还保留了 `allowed_hosts` 白名单作为纵深防御。

**#24 插件搜索隔离与线程状态不一致 — 部分修复**

`future.cancel()` 替换为协作式 `SearchCancelToken`。`_quarantine_plugin()` 增加了 drain 活跃任务（5 秒超时等待）、取消搜索任务和隔离事件日志（通过 `core.event_log`）。但未建立正式的插件生命周期状态机，状态转换仍分散在各方法中。

**#25 local-trusted 与 .qlzip 安装来源没有强绑定 — 部分修复**

安装时根据包路径写入 `install_source` 和 `trust_level` 到 `plugin.json`（`plugin_manager.py:1657-1671`）。但 `PluginManifest` dataclass 没有 `install_source` 字段，运行时无法通过 manifest 获取。无签名校验，仅靠路径匹配判断来源。加载时不读取和校验 `install_source`。

代码合理性：写入来源标记是第一步。但加载时不读取意味着标记只写不用，运行时信任判定仍完全依赖 `trust_level` 字段。路径匹配判断来源容易被绕过（如将第三方包放到 `.plugins/` 目录下）。

**#26 动作链外部 processor safety 依赖自述 — 部分修复**

注册时 `_bind_safety_to_permissions()`（`registry.py:747-788`）将 safety 声明与插件权限做绑定，插件不能通过低报 safety 来规避安全升级。但外部 processor handler 在主进程中直接执行，无沙箱、超时或资源限制。safety 绑定是静态的（注册时一次性），运行时不重新评估。

代码合理性：safety 与权限绑定是有效的静态防护。但无沙箱执行意味着恶意或有 bug 的外部 handler 可以造成任意影响。

**#27 打包/发布校验偏元数据 — 部分修复**

`check_release_artifacts.py` 增加了 `--run-smoke` 选项可触发 `post_package_smoke` 测试。`post_package_smoke.py` 实现了基本的启动 smoke test。但 `release_gate.py` 不包含 smoke test 步骤（使用 `--source-only`），无运行时依赖扫描和插件安装 smoke test。

代码合理性：smoke test 框架已建立但未集成到 release gate，等于未启用。需要将其加入 CI 流水线才能真正发挥作用。

---

### 需要立即关注的遗留问题

按风险从高到低排列：

1. **#6 / #2 — 超时后线程继续运行**：这是 Python 线程模型固有限制，需要进程级隔离（multiprocessing 或 subprocess）才能彻底解决。当前方案（独立线程 + 失败隔离）已降低风险面，但单个卡死线程仍会持续占用资源。建议作为下一版本的架构级任务。

2. **#4 — `host_api=None` 时安全检查被跳过**：`_processor_safety_error()` 在 `host_api=None` 时返回空字符串（即"无错误"），等同于默认放行。应改为默认拒绝（返回错误字符串），强制所有调用路径提供 host_api。这是一个单点修复，改动量小但安全价值高。

3. **#25 — install_source 只写不读**：`install_source` 写入 `plugin.json` 但 `PluginManifest` 不加载、运行时不校验，等于这个标记目前没有实际作用。建议在 `PluginManifest` 中增加字段，并在 `load_plugin()` 中校验来源与信任等级的一致性。

4. **#17 — CHANGELOG 覆盖率门禁值与代码不一致**：CHANGELOG 声称 70%，代码实际 67%。这是文档与代码的事实不一致，无论哪一方有误都应统一。

5. **#27 — smoke test 未集成到 release gate**：框架已建但未启用，等于没有。建议在 `release_gate.py` 中增加 smoke test 步骤，或在 CI workflow 中单独调用 `post_package_smoke.py`。

---

### 代码修改合理性总评

总体来看，本版本的修复质量较高。几个值得肯定的做法：

**安全层面的纵深防御思路明确。** 插件权限（#1）、网络防护（#3/#9）、IPC 鉴权（#7）、更新签名（#8）的修复都不是"最小修复"，而是引入了多层防护机制。例如插件权限不仅反转了默认值，还扩展了 blocked imports 并引入安装来源标记。

**统一抽象的方向正确。** `background_tasks.py`（#14）、`CommandExecutionService`（#11）、`_get_search_pool()`（#12）、`DialogTestTask`（#13）的引入都遵循了"分散创建 → 统一管理"的方向，有效降低了资源泄漏风险。

**渐进式拆分策略务实。** DataManager 拆分（#15）、命令执行巨型分支缩减（#10）都采用了"内部委托/提取，外部接口不变"的策略，避免了大规模接口变更带来的破坏性。

**主要差距集中在两个方面：** 一是 Python 线程模型的固有限制（#2/#6 的超时后线程无法终止），这需要架构级改变（进程隔离）才能解决；二是部分安全防护的"最后一英里"（#4 的 None 跳过、#25 的只写不读、#27 的未集成），这些是单点修复，改动量不大但安全价值较高。
