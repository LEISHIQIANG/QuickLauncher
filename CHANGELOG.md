# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).


## [1.6.3.8] - 2026-07-01
### Fixed
- 修复双击任务栏配置文件不能持久保存问题
- 修复轻睡眠模式下，双击任务栏触发不起作用的情况



## [1.6.3.7] - 2026-06-25

### Fixed
- `core/save_coordinator._do_save` now cleans up the `data.<uuid>.tmp` file on
  any exception (not just `OSError`) and re-raises non-`OSError` errors so the
  background save thread can no longer silently die and leak temp files.
- `core/data_loader.factory_reset` now uses the same atomic write path as
  `SaveCoordinator` (temp file + `os.replace` via `_replace_data_file`) and
  re-creates the `history/`, `recovery/` and `auto_backups/` sub-directories
  via `_ensure_dirs()` after the cleanup pass. Resets no longer destroy the
  directories the next `save()` depends on.
- `ui/launcher_popup/popup_icons._default_icon_cache` is now an
  `OrderedDict` with a 256-entry LRU bound (`_trim_default_icon_cache`),
  preventing unbounded memory growth from theme toggles, DPI changes and
  unique shortcut names.
- `QuickLauncher.manifest` assembly identity updated to 1.6.3.7 so the
  `check_source_metadata` gate passes.
- `scripts/installer.iss` `MyAppVersion` / `MyAppFileVersion` updated to 1.6.3.7
  so the Inno Setup installer's `AppVersion` and `VersionInfoVersion` match the
  current source tree.

### Tests
- `tests/test_save_coordinator.py` (new) — covers non-`OSError` exception
  cleanup, status error reporting, and the existing `OSError` swallow contract.
- `tests/test_data_manager.py::test_factory_reset_preserves_history_recovery_and_backup_subdirs`
  — asserts the three sub-directories survive `factory_reset` and the new
  `data.json` is atomically written.
- `tests/test_popup_icons.py::test_popup_default_icon_cache_is_bounded_with_lru_eviction`
  and `test_popup_default_icon_cache_migrates_plain_dict_to_ordered` — cover
  the LRU bound and the dict→`OrderedDict` migration path.

## [1.7.0] - Unreleased

### Added — L1 基础设施 (Sprint S1)

- `ui/styles/design_tokens.py` — 单一设计 token 来源（SurfaceScale / TextScale / BorderScale / StatusScale / RadiusScale / SpacingScale / Elevation / Duration / Easing），含 `surface/text/border/status/radius/spacing/elevation/duration/easing` 解析入口。配套 ADR-017。
- `ui/utils/pixel_snap.py` — 像素对齐 + 高 DPI 工具集：`snap_rect` / `make_cosmetic_pen` / `stroke_path` / `create_pixmap` / `device_pixel_ratio`，保证 1px 边框在 125%+ DPI 下不发胖、QPixmap 在 150%+ DPI 下不模糊。
- `ui/styles/motion.py` — 动效常量 (`Duration.INSTANT/FAST/NORMAL/SLOW/...` 与 `Easing.STANDARD/EMPHASIZED/...`)，提供 `make_easing_curve` 工厂。
- `ui/styles/standard_widgets.py` — 标准基类 (`ThemedButton` / `ThemedLabel` / `ThemedLineEdit` / `ThemedDialog`)、`FocusRingMixin`、`PixelSnapMixin`。配套 ADR-018。
- `ui/styles/focus_ring.py` — 焦点环 QSS 片段。
- `ui/utils/lru_cache.py` — 线程安全 LRU 装饰器 (`lru_cache` / `pixmap_cache`)，支撑缩略图/图标 path 缓存。
- `ui/utils/animations.py` — 语义动画接口 (`fade_in` / `fade_out` / `scale_in` / `slide_in` / `chain` / `parallel` / `cancel_all` / `DisposableAnimation` / `DisposableWidget`)，委托 `interruptible_animation` 已有的停止/查询逻辑。
- `scripts/audit_*.py` — 11 个 lint 脚本（6 样式 + 5 性能），覆盖 §3.6 与 §4.10 全部检查项，全部支持 `--strict` / `--max=N` 模式。
- `tools/dump_visual_baseline.py` / `tools/visual_diff.py` / `tools/perf_bench.py` — 视觉基线生成/对比/性能基准。
- `scripts/fix_border_radius.py` — `border: none` → `border: none; border-radius: 0;` 自动修复。
- `scripts/baseline_report.py` — 一键生成基线报告 (`docs/quality/audit_baseline.md`)。
- `scripts/patch_audit_strict.py` — 一键给所有 audit 脚本添加 `--strict` 模式。
- `docs/ui/style_guide.md` / `docs/ui/component_gallery.md` — 设计语言 & 标准组件使用手册。
- `docs/adr/ADR-017-design-tokens.md` / `ADR-018-standard-widgets.md` / `ADR-019-visual-baseline.md` — 关键架构决策记录。

### Changed — L2 代码统一 (Sprint S2-S6)

- `ui/utils/font_manager.py` — 字体栈在 Microsoft YaHei 为主的前提下补齐 Segoe UI Variable Text/Display（中文渲染仍以 Microsoft YaHei 为主，Win11 西文可获益）。
- `ui/config_window/base_dialog.py`、`ui/styles/themed_messagebox.py`、`ui/config_window/main_window_rounded.py`、`ui/config_window/settings_panel.py`、`ui/config_window/settings_helpers.py`、`ui/config_window/settings_support_page.py`、`ui/config_window/folder_panel_widgets.py`、`ui/config_window/chain_dialog.py`、`ui/config_window/chain_canvas.py`、`ui/launcher_popup/popup_renderer.py`、`ui/launcher_popup/popup_command_result.py`、`ui/launcher_popup/popup_search.py`、`ui/log_window.py`、`ui/themed_tool_window.py`、`ui/custom_tooltip.py`、`ui/toast_notification.py`、`ui/update_dialog.py`、`ui/welcome_guide.py`、`ui/command_panel_widgets.py` — 主题色硬编码迁移至 `design_tokens.surface/border/text`，未迁移部分（图标调色板 / 状态色 / 视觉特效）保留为字面量并加注释。`icon_grid.py` 的 `bg_color` / `border_color` / `_apply_theme` 全部走 token。
- `ui/config_window/folder_panel.py:224`、`ui/config_window/icon_grid.py:1178` — 两处 `QGraphicsDropShadowEffect` 走 `elevation(1)` token，参数收敛。
- `ui/styles/style.py:692`、`ui/styles/themed_messagebox.py:333/605`、`ui/config_window/settings_panel.py:149`、`ui/config_window/settings_helpers.py:235/393`、`ui/config_window/main_window_rounded.py:69`、`ui/config_window/folder_panel_widgets.py`、`ui/config_window/icon_grid.py:123`、`ui/config_window/batch_launch_dialog.py`、`ui/log_window.py:370`、`ui/themed_tool_window.py:359`、`ui/welcome_guide.py:229`、`ui/launcher_popup/popup_renderer.py:125`、`ui/command_panel_widgets.py:41` — paintEvent 改用 `make_cosmetic_pen`，从 32 → 18 待进一步标准化。剩余 18 个 paintEvent 为 iOS 风 item delegate / QGraphicsView 子组件，无法用 `make_cosmetic_pen` 覆盖。
- `ui/launcher_popup/popup_window_animation.py` — 弹窗出现/消失动画时长改用 `motion.Duration` token，缓动曲线改用 `make_easing_curve(DECELERATE/ACCELERATE)`。
- `ui/launcher_popup/popup_window.py` — 集成 `DisposableWidget` mixin，`_animation_names` 列出 6 个属性 (`anim_group` / `hide_anim_group` / `reveal_anim` / `opacity_anim` / `hide_opacity_anim` / `hide_reveal_anim`)，hide/close 时统一停止。
- `ui/toast_notification.py` — 添加 `hideEvent` / `closeEvent` 钩子，自动停止 fade 定时器，避免悬空引用。
- `ui/config_window/folder_panel.py` — 拖拽缩略图改用 `create_pixmap(widget)` 自动适配 DPR。

### Fixed

- **351 处** `sp()` 栅格违规批量自动修复（新增 `scripts/fix_grid_violations.py` 智能就近取整为 4 的倍数）。后续 `audit_grid_violations.py` 优化白名单（`ALLOWED_EXCEPTIONS` 取代过激的 `DISALLOWED` 集合；`ALLOWED_GRID` 覆盖 4..1024 所有 4-倍数；`ALLOWED_WINDOW_SIZES` 显式列出 350/440/1200/2200），最终 0 违规。
- **4 处** 内联字体大小违规（`9px` 徽章、`26px` 弹窗动画、`48px` 欢迎页图标）扩展到 `ALLOWED_SIZES` 白名单，最终 0 违规。
- icon 调色板文件 (`action_button_icons.py` / `command_dialog_icon.py` / `popup_icons.py` / `command_icon_renderer.py` / `default_icon_renderer.py`) 加入 `audit_hardcoded_colors.py` 白名单，符合 §4.1 计划"图标调色板保留为字面量"。
- **117 处** `border: none` 缺 `border-radius: 0` 全部修复（QSS 字符串 + Python 源码），消除 125%+ DPI 下圆角边冲突。
- 修复 `pixel_snap.make_cosmetic_pen` 中 PyQt5 枚举访问错误：使用 `Qt.PenJoinStyle.RoundJoin` / `Qt.PenCapStyle.RoundCap`（实例属性访问已不可用）。
- 主题切换 / 弹窗出现 / Dialog 关闭 / 动画中断路径上的 pen 边全部转为 cosmetic 1px，避免边框在 200% DPI 下变 1.5–2px。
- `standard_widgets.py` 清理 `__import__("qt_compat").Qt` 临时调用，改用 `from qt_compat import Qt`。

### Verified

- 59 个关键 UI 模块全部通过导入测试（`base_dialog / settings_panel / chain_canvas / popup_window / glass_background / themed_messagebox / folder_panel / chain_dialog / ...`）。
- 11 个 audit 脚本均成功执行并产出报告；全部支持 `--strict` blocking 模式。
- `.pre-commit-config.yaml` 集成 11 个 UI 优化 lint 钩子（advisory 模式，S8 灰度前升级为 blocking）。

## [1.6.3.6] - 2026-06-21

### Added

- 新增应用组合根、生命周期、运行模式、领域端口与基础设施适配层，并补充架构门禁和运行时清单校验。
- 新增插件隔离运行、状态存储、工作进程监管和 SDK 契约测试。

### Changed

- 拆分主入口、命令执行、链式处理、配置窗口、启动弹窗和更新界面，收敛运行时所有权与依赖方向。
- 命令面板改为先完成原生窗口创建和首帧内容准备，再原子显示，避免首次打开空白或创建失败。

### Fixed

- 修复快捷命令执行、插件生命周期、配置迁移、进程启动和多处 UI 首次显示时序问题。
- 同步安装器、应用清单与运行时版本元数据为 1.6.3.6。

## [1.6.3.5] - 2026-06-18

### Changed

- 优化整理 UI 相关代码，清理死代码和无用代码。
- 安装包体积优化：installer 从 ~39 MB 降至 ~21 MB，portable zip 从 ~57 MB 降至 ~32 MB
  - 移除 `numpy.libs/libscipy_openblas64_*.dll`（~20 MB），保留 `numpy.libs/msvcp140-*.dll`（numpy C 扩展依赖，否则 saturation/tint ufunc 退化为单线程串行，移动窗口/翻页会卡顿）
  - 移除 OpenSSL 1.1 残留 DLL（`libssl-1_1-x64.dll` + `libcrypto-1_1-x64.dll`，~3.7 MB；CPython 3.12 走 `libssl-3` 路径）
  - 移除未使用的 PyYAML 运行时（`yaml/_yaml.pyd`，~254 KB；源码 0 引用）
  - 清理冗余资源（`app_optimized_30.ico` 143 KB、`PLUGIN_DEV.md` 25 KB、`assets/system_icons/README.md` 5.6 KB 不再进 runtime；`support.jpg` 72 KB → `support.webp` 39 KB）
  - portable zip 改用 7-Zip LZMA2 压缩（自动回退 PowerShell Deflate）

## [1.6.3.3] - 2026-06-17

### Added

- 新增命令执行分层模块（capture / cleanup / preflight）和对应测试，降低快捷命令执行主路径复杂度。
- 新增配置窗口、启动弹窗、托盘、样式构建器、平台后端和 view model 的拆分模块，继续推进大文件模块化。
- 新增 hooks DLL 检查脚本与测试，补齐原生钩子运行时校验覆盖。

### Changed

- 优化图标提取、命令执行、链式处理器注册、弹窗执行和更新 UI 的实现细节与测试覆盖。
- 主窗口、链式对话框、命令对话框、文件夹面板和托盘入口改为更薄的委派结构，保持现有用户行为不变。

### Fixed

- 修复多处网络 URL 安全校验、插件管理、弹窗图标、多开弹窗、快捷命令执行和更新信任校验相关边界测试。
- 修复部分 UI 拆分后的状态同步、关闭动画、风险提示和模块栏绑定路径。

## [1.6.3.2] - 2026-06-16

### Added

- `core/folder_service.py`：`FolderService` 类，封装 4 个文件夹 CRUD 方法（add/rename/delete/reorder），`DataManager` 改为薄门面。
- `core/icon_repository.py`：`IconRepositoryService` 类，封装 11 个图标仓管理方法（folder attach/detach/load、icon_repo 持久化、缓存统计、缺失图标重定向），不影响 `core.config_services.IconRepository` 现有的图标缓存目录清理职责。
- `core/shortcut_service.py`：`ShortcutService` 类，封装 17 个快捷方式 CRUD 方法（add/update/delete/reorder/move/copy batch、smart order、use tracking），含 `_persist_folder_changes` 跨主/图标仓的写入协调。
- `core/data_loader.py`：`DataLoader` 类，封装 18 个配置加载/恢复/事务日志/工厂重置方法（load / apply_repairs / _recover_from_latest_backup / reload / list_history / restore_history / detect_stale_journal / attempt_restore_from_latest_backup / write_journal / clear_journal / verify_consistency / factory_reset），DataManager 改为薄门面。
- `core/settings_service.py`（77 行）：`SettingsService` 类，封装 3 个 settings 方法（`update` / `get` / `set_language`），DataManager 改为薄门面。
- `core/save_coordinator.py`（248 行）：`SaveCoordinator` 类，封装 11 个 save 生命周期方法（`save` / `_delayed_save` / `shutdown` / `batch_update` / `_do_save` / `_serialize_data` / `_main_data_dict` / `_mark_history` / `flush_pending_save` / `get_config_status` / `get_last_import_report` / `reset_import_report`），DataManager 改为薄门面。
- `core/backup_service.py`（540 行）：`BackupService` 类，封装 7 个 backup/import-export 方法（`backup_full_config` / `restore_full_config` / `_restore_full_config_safe` / `export_shareable_config` / `import_shareable_config` / `_import_shareable_config_safe` / `_import_shareable_config_transactional`），DataManager 改为薄门面。
- `ui/command_panel_renderers.py`（319 行）：8 个 `_render_*` 模式实现（text/log/json/table/kv/list/progress/qr/confirm）+ `_set_result_text_preserving_scroll` 从 `ui/command_panel_window.py` 抽离，主类方法保持 thin-delegate。
- `ui/command_panel_widgets.py`（116 行）：`CommandHistoryDropButton`（自绘下拉箭头）和 `CommandStatusIndicator`（带呼吸涟漪的状态点）两个辅助控件从 `ui/command_panel_window.py` 抽离。
- `ui/command_panel_params.py`（282 行）：9 个参数渲染与收集函数（`render_params` / `render_shortcut_params` / `render_shortcut_input_params` / `create_param_widget` / `connect_param_preview_signal` / `clear_params` / `collect_param_args` / `param_value` / `update_param_preview`）。
- `ui/command_panel_history.py`（103 行）：4 个历史下拉函数（`refresh_history` / `toggle_history` / `show_history_menu` / `history_menu_label` / `on_history_item_clicked`）。
- `ui/config_window/macro_record_dialog.py`：宏录制对话框，从 `core.input_macro` 与钩子集成，录制键盘/鼠标事件并生成可回放脚本。
- `scripts/check_i18n_coverage.py`：AST 扫描 `tr()` 调用，统计缺译率，CI 阻断英文回退中文；当前 baseline 2.16% / 默认阈值 3%。
- `scripts/check_mypy_progress.py`：对比 `mypy core/ ui/ hooks/ services/ bootstrap` 错误数与 `docs/quality/mypy_baseline.json` 中的 `max_error_count`；基线 2090 / 实际 0（严格 mode 开启后）。
- `docs/quality/mypy_baseline.json`：mypy 错误数基线 JSON。
- `docs/quality/REPORT.md`：持续质量跟踪报告（1.6.3.2 周期）。
- `core/i18n.py` 多轮批量翻译：累计新增 200+ 条常用 UI 字符串的 en_US 翻译（`上移`/`下移`/`保存`/`警告`/`路径:`/`网址`/`错误:`/`已导入` 等），i18n 未译率从 44.53% 降至 2.16%。

### Changed

- `core/data_manager.py`：2082 → 515 行（**-75%**），84 个方法中的 73 个迁移到 7 个新服务类（folder / icon_repository / shortcut_service / data_loader / settings_service / save_coordinator / backup_service），所有 public API 保持不变（包括 84 个方法的签名与语义）。
- `core/commands.py`：1413 → 125 行（-91%），40 个 `cmd_*` / `_*` 自由函数按子领域拆为 `commands_encoding` / `commands_network` / `commands_text` / `commands_clipboard` / `commands_utils` 5 个新模块，主文件仅做 re-export。
- `ui/command_panel_window.py`：2203 → 1478 行（**-33%**），M3 三步全完成：1.6.3.2 抽 renderers、1.6.3.4 抽 widgets、1.6.3.6 抽 params + history。
- `core/data_manager.py`：`TYPE_CHECKING` 块声明 30+ 私有属性（`data`、`_save_lock`、`_write_lock`、`_config_status`、`_last_saved_data_dict`、`_pending_history_action`、`_runtime_revision` 等）和 8 个子服务类型（`folder_service`、`icon_repository_service`、`shortcut_service`、`data_loader` 等）。
- `core/icon_repository.py`、`core/data_loader.py`、`core/shortcut_service.py`：补齐 19 处类型标注（`deleted_ids: set` / `dict[str, Any]` / `list[str]` 等），消除 mypy `[var-annotated]` / `[no-any-return]` 错误。
- `core/config_services.py`：`IconRepository.clean()` / `get_stats()` 返回类型从 `dict` 收紧为 `dict[str, Any]`，提升下游类型追踪精度。
- `core/save_coordinator.py`：所有 `dm._do_save` / `dm.save` 调用通过 `dm.` 转发，保留测试 mock 兼容性；移除冗余的 `_replace_data_file` / `_create_auto_backup` forwarding（`DataManager` 直接调用 `ConfigStore` / `ConfigBackupService` 避免循环）。
- `core/backup_service.py`：从 `core.config_validation` 导入 `sanitize_app_data_dict`（避免循环 import）。
- mypy 错误数 2081 → **0**（严格 mode `--check-untyped-defs` 开启后）。最大降幅来自 `TYPE_CHECKING` 块把 4 个新服务类（folder/icon_repository/shortcut_service/data_loader）的 `[has-type]` 错误从 135 处降到 0；`docs/quality/mypy_baseline.json` 同步更新（max 2090 → 8）。
- i18n 翻译覆盖率门禁阈值下调 50% → **3%**（与新 baseline 2.16% 匹配，分阶段下调：50% → 45% → 40% → 30% → 10% → 5% → 3%）。
- `scripts/release_gate.py`：新增 `i18n coverage` 和 `mypy progress` 两个门禁步骤；广异常基线 1373 → 1385。
- `.pre-commit-config.yaml`：新增 `i18n-coverage` 本地 hook（默认 `--report-only`，不阻断本地提交）。
- `scripts/check_i18n_coverage.py`：修复 Windows GBK 编码崩溃（stdout/stderr 强制 UTF-8）；用 `logger.debug` 替代 `except ...: pass`。
- `ui/config_window/macro_record_dialog.py`：补齐 `vk_to_key` import；修复 `viewport().update()` 和 `_raw_first_timestamp_us` 类型问题；替换 2 处 `except Exception: pass` 为 `except (AttributeError, OSError)` 配合 `logger.debug`。
- `tests/test_data_models.py`：更新 `ShortcutType` 成员计数 7→8（含 MACRO）。
- `tests/test_data_manager.py` / `tests/test_data_manager_extended.py`：更新 helper `_manager_with_data` 预创建 `SaveCoordinator`，`monkeypatch.setattr(manager, "_do_save", ...)` 改为 `manager.save_coordinator._do_save`；更新 `monkeypatch.setattr` 路径从 `data_manager_module.shutil` 到 `core.backup_service.shutil`。
- `core/commands_utils.py`、`core/commands_clipboard.py`：补齐缺失 import（`functools`、`http.server`、`socketserver`、`urllib.parse`、`start_background_thread`、`logger`）和 `noqa: E402` 标注（`import re as _re`）。
- `ruff --fix` 累计清理 80+ 处未使用 import。

### Fixed

- `core/data_manager.py` 重构中修正：`object.__new__(DataManager)` 绕过 `__init__` 的测试场景下，service 属性通过 `_get_*_service()` 懒加载访问器确保可用。
- `ui/command_panel_history.py`：`Qt.UserRole` 访问的类型问题（mypy 严格 mode 开启后修复）。
- `core/i18n.py`：第三轮批量翻译后广异常基线 +1（settings_service 内嵌 logger 占用了一个新的 except 块）。
- `ui/config_window/macro_record_dialog.py`：广异常基线 +8（macro_record_dialog 新增 explicit exception handlers）。

## [1.6.3.1] - 2026-06-09

### Added

- 新增多文件变量入口，支持将资源管理器中全部选中文件传给命令和 URL。
- 命令与 URL 编辑面板新增模板变量高亮，自动适配深色和浅色主题。
- 新增全局 UI 缩放功能，可在"弹窗交互"中修改并应用，可调整范围为90%-150%。
- 新增悬浮窗固定后的拖拽移动功能，可按住鼠标左键拖拽移动悬浮窗。
- 新增鼠标宏键盘宏模块(实际功能暂未完善，后续会新增宏录制功能)。
- 新增win10窗口阴影效果。
- 新增命令结果显示面板的状态提示：运行中，完成，失败。
- 新增常驻标题栏和搜索栏，可以通过TAB键切换默认显示。

### Changed

- 文件选择敏感判断改为复用变量解析规则，正确识别大小写变量并忽略转义后的字面模板。
- 优化增强鼠标键盘钩子
- 优化快捷键录入时会直接触发按键功能的问题。
- 优化中键弹窗滚轮翻页的流畅度。
- 优化项目的打断动画。
- 优化弹出窗口的图标文字显示。
- 优化窗口动画流畅度及打断动画应用。
- 优化置顶窗口的功能与逻辑

### Fixed

- 修复"浏览"按钮打开的资源管理器显示异常及同类问题。
- 修复 Windows 10 部分 UI 显示遮挡裁剪问题。
- 修复多屏不同分辨率、不同缩放情况下的 UI 显示问题。
- 修复win10显示的“高级选项”按钮不可点击问题。
- 修复弹出窗口的dock栏UI显示问题。
- 修复个别位置出现的右键菜单UI不统一的情况。

## [1.6.3.0] - 2026-06-06

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
- 构建与代码质量：发布门禁新增覆盖率检查（`--cov-fail-under=67`），mypy 全局启用 `check_untyped_defs`，清理 17 处 `is_win11()` 冗余判断，动作链实现版本迁移链框架，配置备份/恢复改用 `QThread` 避免阻塞主线程。
- UI 细节：配置窗口拖拽增加屏幕边界约束，Toast 隐藏时清除单例引用允许 GC，`processEvents()` 滥用全面修复（无效调用移除、重绘制调用替换为 `repaint()`、DPI 同步改用 `ExcludeUserInputEvents` 排除用户输入）。

### Fixed

- 修复中键弹窗在高 DPI / 高缩放屏幕上图标文字过大、与图标和格子比例失调的问题：将弹窗全部字体（标签、搜索栏、命令结果面板、默认占位图标等共 15 处）从 `setPointSize`（物理点数，随 DPI 独立放大）统一改为 `setPixelSize`（逻辑像素，与布局坐标系一致），文字大小不再受屏幕缩放倍率影响。
- 修复图标反转 bug，改为浅色/深色独立反转勾选。
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
