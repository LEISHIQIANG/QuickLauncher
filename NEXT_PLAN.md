# QuickLauncher 下一步开发计划

> 编制日期：2026-05-31
> 版本：v1.6.1.0
> 状态：待确认

---

## 概览

本计划基于 2026-05-30 版做全面复核后更新。通过五项深度专项扫描（安全、性能、重复代码、API、国际化）及后续三轮审核，累计发现 **11 大类 600+ 项可优化点**，覆盖代码质量、安全、性能、国际化、测试、架构等全部维度。

---

## 一、代码质量修复

### 1.1 修复 78 处静默异常吞没

**78 处**。使用项目自带的 `scripts/check_silent_exceptions.py` 检测，覆盖单行 `except: pass` 和两行 `except:\n    pass` 两种模式，均无 `# noqa: S110` 排除。

按目录分布：core/ 32 处、ui/ 31 处、plugins/ 9 处、bootstrap/ 3 处、services/ 2 处、hooks/ 1 处。

最严重的文件（按实际扫描）：

| 文件 | 数量 |
|------|------|
| `ui/config_window/settings_commands_page.py` | **7** |
| `ui/config_window/folder_panel.py` | **6** |
| `ui/config_window/icon_grid.py` | **6** |
| `plugins/disk_cleaner/main.py` | **6** |
| `core/data_manager.py` | **3** |
| `core/shortcut_command_exec.py` | **3** |
| `core/shortcut_parser.py` | **3** |
| `core/event_log.py` | **2** |
| `ui/config_window/main_window.py` | **2** |

其余 40 个文件各 1 处。涉及的异常类型包括 `Exception`、`RuntimeError`、`ValueError`、`OSError`、`FileNotFoundError`、`ImportError`、`json.JSONDecodeError` 等。

**修复方案：** 至少改为 `logger.warning("...", exc_info=True)` 或 `logger.debug("...", exc_info=True)`。按文件分批处理（建议 10-15 个文件/批），每批后运行 `pytest tests/ -v` 确认无回归。

### 1.2 pre-commit hook 脚本验证

`scripts/check_silent_exceptions.py` **已存在**（51 行），实现了单行和两行静默异常检测，支持 `# noqa: S110` 排除。需确认 `.pre-commit-config.yaml` 中已注册为 local hook，且检测逻辑与 1.1 节修复后的代码兼容。

### 1.3 修复层边界违规

`ui/launcher_popup/file_selection.py:20` 从 `core.window_detection` 导入窗口检测函数（`_normalize_window_hwnd`、`_is_desktop_window`、`_window_from_point`、`_window_selection_kind`）。`core/file_selection.py`（89 行）也存在，提供核心层的文件选择逻辑。

**评估：** 需确认 `ui/` 版本对 `core.window_detection` 的依赖是否构成层违规（`ui` → `core` 是允许的），或是否存在反向依赖。

### 1.4 内联 `import traceback` → 改用 `logger.exception()`

共 **23 处**内联 `import traceback` 分布在 18 个文件中：

| 文件 | 行数 |
|------|------|
| `core/shortcut_command_exec.py` | 2335, 2456 |
| `core/__init__.py` | 99 |
| `core/command_registry.py` | 8 |
| `core/plugin_manager.py` | 13 |
| `core/shortcut_executor.py` | 205 |
| `core/shortcut_window_control.py` | 161, 228 |
| `hooks/hotkey_manager.py` | 219 |
| `main.py` | 9 |
| `bootstrap/ipc.py` | 2 |
| `ui/tray_app.py` | 674 |
| `ui/tray_mixins/popup_mixin.py` | 292 |
| `ui/tray_mixins/windows_mixin.py` | 64, 142 |
| `ui/tray_mixins/hooks_mixin.py` | 62, 95 |
| `ui/config_window/main_window.py` | 557, 709 |
| `ui/config_window/settings_system_page.py` | 471 |
| `ui/config_window/theme_helper.py` | 8 |
| `ui/utils/window_effect.py` | 674 |
| `ui/launcher_popup/popup_drag_drop.py` | 273 |

**修复：** 用 `logger.exception()` 替代，或 `logger.error(exc_info=True)`。

### 1.5 `# type: ignore` 检查

经扫描，代码库中所有 12 处 `# type: ignore` 均已带有错误码（`[arg-type]` 或 `[import]`），**不存在裸 `# type: ignore`**。涉及文件：`tests/test_config_repairs.py`（4 处）、`tests/test_config_history.py`（3 处）、`tests/test_preprocessing_sanitizers.py`（4 处）、`scripts/select_build_python.py`（1 处）。

### 1.6 `qt_compat.py` 检查

检查 `qt_compat.py` 是否需要按 PEP 8 clean up（当前有 22 个 unstaged 修改文件之一）。

---

## 二、文档与配置修复

### 2.1 创建 CLAUDE.md

项目使用 Claude Code 但缺少项目级指令文件。**内容要点：** 项目概述、目录结构速查、代码规范（black/ruff/mypy）、测试要求（pytest, `--cov=core --cov=ui`）、架构约定（Mixin 模式、pyqtSignal 跨线程、安全预处理管道）、常用命令。

### 2.2 创建 CHANGELOG.md

使用 Keep a Changelog 格式。从 `git log --oneline` 追溯历史。

### 2.3 修复过时文档

| 文件 | 问题 | 修复 |
|------|------|------|
| `docs/2026_05_29/CONTRIBUTING.md` | 文件位于日期子目录（非 `docs/CONTRIBUTING.md`）；引用版本号为 V1.6.1.0（正确）；无 GitHub Actions 引用 | 确认路径引用正确，无需修改内容 |
| `PLUGIN_DEV.md` | 已列出全部 8 个内置插件（file_tools、process_tools、startup_tools、network_tools、api_tester、disk_cleaner、event_inspector、text_tools） | 无需修改 |
| `.github/ISSUE_TEMPLATE/bug_report.md` | 版本号示例为 `v1.6.1.0`（正确） | 无需修改 |

### 2.4 `.gitignore` 检查缺口

当前忽略了 `config/`、`dist/`、`docs/`、`temp_icons/`、`icons/`、`tools/`、`.claude/`。未忽略：
- `剪切板与选中文字交互完善计划书.md`
- `_test_update_dialog.py`

---

## 三、未完成功能补全

### 3.1 配置恢复中心 UI

后端 `core/config_recovery.py`（127 行）已实现 ConfigRecoveryReport、quarantine、prune。**缺少用户可见的设置页面 UI**。

**具体实现位置：** `ui/config_window/settings_about_page.py` 或新增 `ui/config_window/settings_recovery_page.py`。

### 3.2 插件搜索源异步/超时保护

插件搜索源目前同步运行在 UI 线程上。一个慢速插件搜索源会阻塞整个搜索面板。需要添加异步执行或超时保护。

**建议方案：** 在 `core/plugin_manager.py` 中添加搜索超时机制，或在 `ui/launcher_popup/popup_search.py` 中分离线程。

### 3.3 诊断导出 token 级脱敏

`core/diagnostics.py`（701 行）已定义 `_SENSITIVE_PATTERNS`（第 30-74 行预编译敏感模式），但：
- `redaction_report.json` 未实现
- 需要确认 `_sanitize_text` 是否对所有导出路径生效

### 3.4 RufF 压制项清理

`pyproject.toml` 中 7 条 `per-file-ignores` 应逐个评估：

| 压制项 | 文件 | 评估 |
|--------|------|------|
| `E402`（导入顺序） | `core/__init__.py` | 可能合理（条件导入），需确认 |
| `E402` | `ui/config_window/settings_panel.py` | 同上 |
| `E402` | `tests/test_builtin_commands_suite.py` | 同上 |
| `F601`（字典 key 重定义） | `core/i18n.py` | **可能是 bug**，需检查 |
| `F601` | `core/pinyin_search.py` | **可能是 bug**，需检查 |
| `F401`（未使用导入） | `ui/launcher_popup/popup_data_refresh.py` | 移除未使用的 import |
| `F401` | `ui/launcher_popup/popup_window.py` | 同上 |

---

## 四、测试改进

### 4.1 pytest markers 应用

`pytest.ini`（14 行）已定义 `slow`/`integration`/`ui` 三个 markers（lines 8-11），但测试文件尚未标注。需在约 20+ 个导入了 `qt_compat` 的测试文件中添加 `@pytest.mark.ui` 装饰器：`test_command_panel_window.py`、`test_icon_extractor.py`、`test_popup_*.py`、`test_chain_dialog.py` 等。

### 4.2 浅层测试文件

| 测试文件 | 测试数 | 覆盖目标 | 优先度 |
|----------|--------|---------|--------|
| `test_icon_picker_dialog.py` | 1 | icon_picker_dialog.py | LOW |
| `test_shortcut_folder_exec.py` | 1 | shortcut_folder_exec.py | MEDIUM |
| `test_command_execution_service_chain.py` | 1 | command_execution_service chain | MEDIUM |
| `test_shortcut_parser.py` | 2 | shortcut_parser.py | MEDIUM |

### 4.3 核心模块缺测试

| 模块 | 行数 | 风险 | 说明 |
|------|------|------|------|
| `core/shortcut_executor.py` | ~200 | **HIGH** | 核心执行引擎，**无任何测试** |
| `core/i18n.py` | 527 | MEDIUM | 翻译逻辑，**无测试**，有 F601 压制 |
| `core/commands_maintenance.py` | — | MEDIUM | 命令维护逻辑，**无测试** |

### 4.4 覆盖率配置缺失

- **无 `.coveragerc` 文件**，覆盖率仅通过 CI 命令行配置
- CI 中的 `--cov-fail-under=30`（30%）偏低
- 建议创建 `.coveragerc` 定义 source 目录和最小覆盖率

### 4.5 `qt_compat` 导入模式

`conftest.py` 只有一个 `qapp` fixture（module-scoped），但约 20 个测试文件导入了 `qt_compat`。可能需要：
- 添加 `@pytest.mark.ui()` 到每个需要 Qt 的测试文件
- 创建 `auto_use` fixture 自动初始化 QApplication

---

## 五、代码结构优化

### 5.1 超大文件拆分（实际 12 个超 1000 行）

| 文件 | 行数 | 建议优先级 |
|------|------|-----------|
| `core/shortcut_command_exec.py` | **2267** | 最高优先级，用 Mixin 模式拆分 |
| `core/data_manager.py` | **1700** | 数据持久化 + 导入导出 + 迁移可分离 |
| `ui/config_window/icon_grid.py` | **1589** | 大组件多职责 |
| `ui/command_panel_window.py` | **1565** | 渲染逻辑已按 display_type 分支，可按类型拆文件 |
| `ui/config_window/command_dialog.py` | **1549** | 对话框逻辑可拆分 |
| `ui/styles/style.py` | **1494** | 样式定义 + 逻辑代码分离 |
| `core/commands.py` | **1282** | 命令注册与调度逻辑分离 |
| `ui/config_window/folder_panel.py` | **1193** | 文件夹面板可拆分 |
| `core/plugin_manager.py` | **1172** | 插件加载 + 隔离 + 搜索可分离 |
| `core/auto_start_manager.py` | **1168** | 自启动逻辑可简化 |
| `ui/config_window/main_window.py` | **1159** | 主窗口多职责 |
| `ui/config_window/settings_panel.py` | **1122** | 多个设置页面混在一起 |

### 5.2 mypy 配置加固

当前 mypy.ini：
```ini
check_untyped_defs = False
warn_unused_ignores = False
warn_return_any = False
```

**渐进式加固：** 先开启 `check_untyped_defs = True` 和 `warn_unused_ignores = True`，逐模块修复。

### 5.3 `sys.path.insert` 清理

代码库中共 **36 处** `sys.path.insert` 分布在 35 个文件中（含 main.py 2 处），涉及 core/、ui/、tests/、scripts/ 等目录。应逐步改为相对包导入或统一在入口点设置 `sys.path`。

### 5.4 全局仅 1 处 TODO 注释

代码库仅 1 处 TODO（`core/shortcut_file_exec.py:153`），说明需要引入更系统的 TODO/FIXME 追踪机制。

---

## 六、深度扫描补充

> 以下内容基于 2026-05-31 对代码库的全量安全、性能、重复代码、API、国际化五项专项扫描，覆盖原计划未涉及的领域。

**扫描发现总览：**

| 子章节 | 领域 | 发现数 | 严重-HIGH | 优先级分布 (P0/P1/P2/P3) |
|--------|------|--------|-----------|--------------------------|
| 6.1 | 安全与错误处理 | 31 项 | 7 HIGH | P0:6 P1:1 |
| 6.2 | 代码重复 | 10 项 | 3 HIGH | P1:4 P2:4 P3:2 |
| 6.3 | 性能与资源泄漏 | 40 项 | 1 HIGH | P1:3 P2:2 |
| 6.4 | API 设计与依赖 | 6 项 | 0 HIGH | P2:4 P3:2 |
| 6.5 | 国际化与无障碍 | 287 项 | 0 HIGH | P1:3 P2:3 P3:2 |

**优先级定义：** P0=立即修复（安全漏洞/数据损坏），P1=本迭代修复（严重性能/功能完整），P2=下迭代修复（代码质量/可维护性），P3=待评估（低风险/低影响）

### 6.1 安全与错误处理（31 项发现）

#### [SEC-01] 6.1.1 `subprocess` 使用 `shell=True` — 命令注入风险

- **优先级：P0（安全漏洞）**
- **状态：✅ 已修复**（代码已使用 `shell=False` + list 参数模式）
- **建议耗时：** —（无需操作）

| 文件 | 行 | 当前代码 | 修复确认 |
|------|---|---------|---------|
| `ui/launcher_popup/popup_drag_drop.py` | 248-250 | `subprocess.Popen(["cmd", "/c", "start", "", target, file_path], shell=False)` | ✅ |
| `core/shortcut_file_exec.py` | 288-289 | `ShortcutExecutor._popen_silent(cmd, shell=False)` — list 参数模式 | ✅ |

**验证要点：** 确保所有 `shell=True` 调用——尤其是涉及用户输入/文件路径的——均已改用 list 参数模式或 `os.startfile()`。

#### [SEC-02] 6.1.2 Signal/Slot 连接未断开 — 内存泄漏与崩溃风险

- **优先级：P1（多窗口重建时崩溃）**
- **影响范围：** 全库 336 处 `.connect()` 中仅 12 处 `.disconnect()`
- **建议耗时：** 4h（含全库扫描 + 修复至少 50 处信号在 `closeEvent` 中断开）

| 文件 | 行 | 严重程度 | 问题 |
|------|---|---------|------|
| `ui/tray_mixins/windows_mixin.py` | 25,31,40 | HIGH | `config_window.settings_changed` 连接在窗口重建时不断开，可能触发多次 |
| `ui/launcher_popup/popup_data_refresh.py` | 272 | MEDIUM | 临时线程的 `files_found` 信号无 disconnect |
| `ui/config_window/chain_dialog.py` | 956 | MEDIUM | 测试线程 `result_ready` 连接在对话框关闭时可能指向已销毁对象 |

**修复方案：** 在窗口/对话框的 `closeEvent` 中添加信号断开逻辑；对常驻对象（tray_mixins）使用弱引用信号连接（`Qt.WeakConnection`）。全库搜索策略：`grep -rn "\.connect("|grep -v "\.disconnect\|test_\|\.pyc"` 得到未配对项后按文件修复。→ 见 7.2.1（窗口隐藏泄露）

#### [SEC-03] 6.1.3 `QApplication.processEvents()` 重入风险

- **优先级：P1（可导致栈溢出/死锁）**
- **影响范围：** 6 处调用（popup_window 中 5 处、popup_search 中 1 处）
- **建议耗时：** 2h

| 文件 | 行 | 严重程度 | 问题 |
|------|---|---------|------|
| `ui/launcher_popup/popup_window.py` | 659 | MEDIUM | 数据刷新期间调用，可能触发重入循环 |
| `ui/launcher_popup/popup_window.py` | 770-771 | MEDIUM | 连续两次调用，放大重入风险 |
| `ui/launcher_popup/popup_search.py` | 774 | MEDIUM | 热路径中调用，每次 show/resize 触发 |

**修复：** 用 `_is_processing_events` 重入锁保护，或改用 `QTimer.singleShot(0, ...)` 延迟处理。

```python
# 推荐模式
class PopupWindow(...):
    _is_processing_events = False

    def _safe_process_events(self):
        if self._is_processing_events:
            return
        self._is_processing_events = True
        try:
            QApplication.processEvents()
        finally:
            self._is_processing_events = False
```

#### [SEC-04] 6.1.4 QR 临时文件无清理机制

- **优先级：P1（磁盘空间泄漏）**
- **状态：✅ 已修复**
- **建议耗时：** —（无需操作）

`core/commands.py:533-534` 已注册 `atexit.register(_cleanup_qr_temp_files)`，在 `_cleanup_qr_temp_files()` 中遍历 `_qr_temp_files` 列表删除所有临时 PNG。`commands.py:601` 的 `tempfile.NamedTemporaryFile(delete=False)` 创建的文件在 `atexit` 时统一清理。

**验证要点：** 确认 `_qr_temp_files` 列表在每次 `/qr` 调用后追加，且 `atexit` 或 `_stop_all_qr_file_servers` 关闭服务器时触发清理。

#### [SEC-05] 6.1.5 QR 文件服务器绑定 `0.0.0.0`

- **优先级：P0（安全漏洞，可被局域网访问）**
- **状态：✅ 已修复**
- **建议耗时：** —（无需操作）

`core/commands.py:541,545` 已使用 `socketserver.TCPServer(("127.0.0.1", 0), ...)` 绑定仅本地回环接口。

**验证要点：** 确认 `core/commands.py` 中所有 `TCPServer` 构造均使用 `"127.0.0.1"` 而非 `"0.0.0.0"`。

#### [SEC-06] 6.1.6 `exec()` 代码执行

- **优先级：P0（潜在远程执行）**
- **建议耗时：** 0.5h

`scripts/check_release_artifacts.py:25` — `exec((root / "core" / "version.py").read_text(), namespace)` 读取本地文件执行。建议改用 AST 解析。

```python
# 替代方案
import ast
tree = ast.parse((root / "core" / "version.py").read_text())
# 提取 APP_VERSION 赋值语句
```

#### [SEC-07] 6.1.7 硬编码 Windows 路径

- **优先级：P1（系统兼容性）**
- **状态：✅ 已修复**
- **建议耗时：** —（无需操作）

`plugins/disk_cleaner/main.py:189,294,376` 已使用 `os.environ.get("SystemRoot", r"C:\Windows")` 动态获取系统根目录。→ 另见 7.3.2（部分遗留问题）

**验证要点：** 确认 `plugins/disk_cleaner/main.py` 中所有 Windows 路径均通过 `os.environ.get("SystemRoot", ...)` 拼接，无裸露 `C:\Windows` 字面量。

### 6.2 代码重复（10 项发现，估算可节省 ~850 行）

| ID | 重复模式 | 涉及文件 | 可节省 | 优先级 | 关联章节 |
|----|---------|---------|--------|--------|---------|
| DRY-01 | **无边框对话框窗口效果**（paintEvent/模糊/动画/拖拽）4 份独立实现 | `themed_tool_window.py`、`base_dialog.py`、`log_window.py`、`themed_messagebox.py` | **~400** | **P1** | 5.1（大文件拆分） |
| DRY-02 | JSON 状态 load/save 模式 6+ 份重复 | `plugin_manager.py`、`data_manager.py`、`config_recovery.py`、`shortcut_health.py`、`search_history.py`、`checker.py` | ~120 | P1 | 5.1（大文件拆分） |
| DRY-03 | 主题颜色常量散落在 9+ 个文件 | `themed_tool_window.py`、`log_window.py`、`base_dialog.py`、`themed_messagebox.py`、`hotkey_dialog.py`、`chain_dialog.py` 等 | ~50 | P2 | 6.5.7（颜色硬编码） |
| DRY-04 | Folder 图标路径解析 4 份拷贝 | `popup_icons.py`（2 处）、`icon_grid.py`、`startup_mixin.py` | ~60 | P2 | 6.3.1（磁盘 I/O 优化） |
| DRY-05 | LNK 快捷方式解析 3 种 COM 实现 | `shortcut_health.py`、`shortcut_file_exec.py`、`startup_tools/main.py` | ~50 | P2 | — |
| DRY-06 | VBS 重启脚本生成 2 份 | `settings_system_page.py`、`tray_app.py` | ~50 | P2 | — |
| DRY-07 | 公网 IP 获取 2 份 | `commands.py`、`command_variables.py` | ~30 | P3 | — |
| DRY-08 | App 图标路径解析 3 种实现 | `themed_tool_window.py`、`log_window.py`、`themed_messagebox.py` | ~40 | P2 | DRY-01（同一文件集） |
| DRY-09 | 路径安全验证 3 个模块 | `path_security.py`、`preprocessing/security.py`、`preprocessing/validators.py` | ~40 | P2 | — |
| DRY-10 | `sys.path.insert` 样板 11 处 | `ui/` 下 11 个文件 | ~11 | P3 | 5.3（系统路径清理） |

**修复原则：** 提取共享基类或工具函数，而非复制粘贴修改。DRY-01 收益最高（~400 行），建议优先创建 `BaseBorderlessWindow` 基类。DRY-02 可创建统一 `JsonStore` mixin。

### 6.3 性能与资源泄漏（40 项发现）

#### [PERF-01] 6.3.1 热路径重复磁盘 I/O

- **优先级：P1（用户每次弹出面板均触发，影响感知性能）**
- **建议耗时：** 1h

`ui/launcher_popup/popup_icons.py:79-83,172-176` — 弹出面板每个图标项都重新解析 `Folder.ico` 路径并调用 `os.path.exists()`。这是应用最热的路径。

**修复：** 模块级 `lru_cache` 或一次性计算后缓存。
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def _resolve_folder_ico_path(folder_path: str) -> str | None:
    """缓存图标路径解析结果，避免每次弹窗重复磁盘 I/O"""
    ico_path = os.path.join(folder_path, "Folder.ico")
    return ico_path if os.path.exists(ico_path) else None
```

#### [PERF-02] 6.3.2 QTimer 孤立对象（5 处）

- **优先级：P2（累积内存泄漏，偶发崩溃）**
- **建议耗时：** 2h

| 文件 | 行 | 问题 |
|------|---|------|
| `ui/config_history_window.py` | 113 | 鼠标移动事件中创建 QTimer 无 parent |
| `ui/tooltip_helper.py` | 20 | 每次 enterEvent 创建 QTimer 无 parent |
| `hooks/hotkey_manager.py` | 246 | 错误路径创建孤立 QTimer |

**修复：** 所有 `QTimer()` 改为 `QTimer(self)` 设置 parent；单例工具提示类应重复使用同一个 timer 而非每次重建。→ 见 7.2.2（补充的孤立 QTimer）

#### [PERF-03] 6.3.3 `data_manager._do_save()` 序列化-反序列化往返

- **优先级：P2（每次保存浪费 CPU，高频触发）**
- **建议耗时：** 1h

`core/data_manager.py:516` — 每次保存执行 `json.dumps` → `json.loads` 仅用于比较新旧状态。应改用 dirty flag 或写前计算 SHA256 字符串 hash 比较。

```python
# 推荐方案：dirty flag 模式
def __init__(self):
    self._dirty = False

def _mark_dirty(self):
    self._dirty = True

def _do_save(self):
    if not self._dirty:
        return
    # ... 实际保存 ...
    self._dirty = False
```

#### [PERF-04] 6.3.4 QPixmap/QIcon 重复加载（7 处）

- **优先级：P2（窗口打开性能）**
- **建议耗时：** 2h

`themed_tool_window.py`、`log_window.py`、`folder_panel.py` 等多次从磁盘加载同一图标。应缓存到类级 `QPixmapCache` 或模块级字典。

**修复：** 创建统一 `IconCache` 单例：
```python
class IconCache:
    _cache: dict[str, QIcon] = {}
    def get(self, path: str) -> QIcon:
        if path not in self._cache:
            self._cache[path] = QIcon(path)
        return self._cache[path]
```

#### [PERF-05] 6.3.5 后台线程未 join（9 处）

- **优先级：P2（应用关闭时数据丢失风险）**
- **建议耗时：** 3h

`shortcut_dialog.py`、`chain_dialog.py`、`command_dialog.py`、`url_dialog.py`、`icon_grid.py` 等 9 个文件启动 daemon 线程但不 join。虽不阻塞退出，但关闭时可能丢失未完成工作。

**修复：** 在 `closeEvent` 或析构函数中添加线程 join（超时 2s），记录未完成工作的警告。

### 6.4 API 设计与依赖（关键发现）

#### [API-01] 6.4.1 函数超长（289 个 >50 行）

- **优先级：P2（可维护性）**
- **建议耗时：** 持续，建议每次迭代拆分 2-3 个超长函数

| 严重程度 | 数量 | 说明 |
|---------|------|------|
| CRITICAL | 1 | `run_command_capture`（603 行） |
| HIGH | 16 | 200-500 行函数 |
| MEDIUM | 85 | 100-200 行函数 |

最长函数 Top 5：
1. `core/shortcut_command_exec.py:1551` `run_command_capture` — **603 行**
2. `core/shortcut_command_exec.py:957` `_execute_command` — **379 行**
3. `ui/launcher_popup/popup_item_execution.py:24` `_execute_item` — **370 行**
4. `ui/config_window/command_dialog.py:549` `_setup_ui` — **361 行**
5. `core/diagnostics.py:95` `collect_diagnostics` — **354 行**

**修复原则：** 提取子函数（每个 ≤40 行），使用 Guard Clause 减少缩进嵌套，将条件分支提取为独立方法。→ 见 5.1（大文件拆分）和 8.4.3（God 模块）

#### [API-02] 6.4.2 类超大（25 个 >500 行）

- **优先级：P2（可维护性）**
- **建议耗时：** 持续，建议用 Mixin 模式拆分超大类

4 个 CRITICAL 类超过 1,500 行：
1. `CommandExecutionMixin` — **2,266 行**
2. `DataManager` — **1,877 行**
3. `CommandDialog` — **1,641 行**
4. `CommandPanelWindow` — **1,618 行**

#### [API-03] 6.4.3 类型注解覆盖不均

- **优先级：P2（类型安全）**
- **建议耗时：** 6h（分批次添加）

| 目录 | 覆盖率 | 说明 |
|------|--------|------|
| `core/` | **88.2%** | 良好，保持 |
| `ui/` | **33.9%** | 933 个函数缺注解，重点攻坚 |
| `qt_compat.py` | **0%** | 22 个函数无注解 |

**修复：** 按文件使用率排序，优先添加 `tray_app.py`、`popup_window.py` 等高频文件的类型注解。

#### [API-04] 6.4.4 `from __future__ import annotations` 覆盖不均

- **优先级：P3（渐进式改进）**
- **建议耗时：** 2h

`core/` 67.5% 已导入，`ui/` 仅 **15.8%**（64 个文件缺少）。可用 ruff 的 `from __future__ import annotations` 自动修复规则（`ruff check --fix --select=FA100 ui/`）。

#### [API-05] 6.4.5 `core/__init__.py` 缺少 `__all__`

- **优先级：P2（封装性）**
- **建议耗时：** 0.5h

209 行代码导出 20+ 符号但无 `__all__`，星号导入会暴露内部 `_callbacks`、`logger` 等。

#### [API-06] 6.4.6 依赖版本未设上界

- **优先级：P3（依赖管理）**
- **建议耗时：** 0.5h

`requirements.txt` 中 6 个运行时依赖仅用 `>=`（pywin32、Pillow、psutil、pynput、watchdog、qrcode），可能拉入不兼容的大版本。

**修复：** 使用 `~=` 或 `<major+1` 上界锁定（如 `pywin32>=305,<306`），在 CI 中定期测试新版本兼容性。

### 6.5 国际化与无障碍（287 项发现）

> **策略建议：** 国际化修复可分 3 阶段推进：① 完成 `_EN_US` 字典补全（P1）；② 全局扫描替换中文硬编码为 i18n 调用（P2）；③ 补充无障碍属性（P3）。

#### [I18N-01] 6.5.1 硬编码中文绕过 i18n 系统（117 处）

- **优先级：P1（影响多语言用户核心体验）**
- **建议耗时：** 16h（按文件分批 4 批 × 4h）

| 类型 | 数量 | 示例文件 |
|------|------|---------|
| `setWindowTitle()` 中文 | 3 | `log_window.py`、`settings_plugins_page.py`、`welcome_guide.py` |
| `setText()` 中文 | 20 | `icon_picker_dialog.py`、`hotkey_dialog.py`、`url_dialog.py` 等 |
| `setToolTip()` 中文 | 5 | `settings_system_page.py`、`command_dialog.py`、`command_panel_window.py` |
| `ThemedMessageBox` 中文 | ~60 | `settings_data_actions.py`、`settings_plugins_page.py`、`folder_panel.py` 等 14 个文件 |
| `welcome_guide.py` 全部内容 | 1 文件 | 5 个教程步骤标题+内容全部未翻译 |
| `about_window.py` 全部内容 | 1 文件 | 所有章节标题+正文全部未翻译 |
| `shortcut_health_window.py` HTML | 1 文件 | 状态文本、摘要、问题格式全部未翻译 |
| `config_history_window.py` | 1 文件 | 副标题、按钮、状态全部未翻译 |
| `slash_help_window.py` | 1 文件 | 分组名称、按钮全部未翻译 |
| `diagnostics_window.py` | 1 文件 | 加载文本、按钮、导出消息全部未翻译 |

**影响：** 切换到英文时，欢迎指南、关于窗口、健康检查、诊断导出、历史恢复等整个页面仍显示中文。

**修复模式示例：**
```python
# 之前
self.setWindowTitle("日志查看器")
button.setText("导出诊断信息")

# 之后
from core.i18n import _
self.setWindowTitle(_("log_window.title", "日志查看器"))
button.setText(_("diagnostics.export_btn", "导出诊断信息"))
```

#### [I18N-02] 6.5.2 翻译键缺失（56 个字符串无英文翻译）

- **优先级：P1（英文模式下直接显示中文）**
- **建议耗时：** 3h

`core/i18n.py` 的 `_EN_US` 字典缺少 56 个已在 UI 中使用的中文字符串。英文模式下这些字符串直接显示原始中文。

**修复：** 扫描 UI 代码中所有 `_("key", "default")` 调用中的 default 值，若在 `_EN_US` 中找不到对应的英译，则补充。优先补充 `settings_data_actions.py`（18 个）、`settings_plugins_page.py`（10 个）、`settings_system_page.py`（8 个）、`command_panel_window.py`（5 个）。

**自动化辅助：** 编写 `scripts/check_i18n_coverage.py` 扫描所有 `_("...", "...")` 调用的默认值，对比 `_EN_US` 输出缺失清单。

#### [I18N-03] 6.5.3 直接 PyQt5 导入绕过 qt_compat（8 处，4 个文件）

- **优先级：P1（破坏 PySide6 兼容性）**
- **建议耗时：** 1h

当前仍有 **8 处**直接 `from PyQt5` 导入分布在 **4 个文件**：

| 文件 | 行 | 导入内容 | 需加入 qt_compat |
|------|---|---------|----------------|
| `ui/config_window/chain_dialog.py` | 610 | `QPalette`（QtGui） | `QPalette` |
| `ui/config_window/settings_support_page.py` | 6 | `QRadialGradient`（QtGui） | `QRadialGradient` |
| `core/favicon_cache.py` | 860-861, 943-945 | `QByteArray`, `QGuiApplication`, `QPainter`, `QSvgRenderer` | `QSvgRenderer`（其余已有） |
| `core/icon_extractor.py` | 655 | `QtWin`（QtWinExtras） | `QtWin`（带 try/except） |

**注意：** `safe_file_dialog.py`、`popup_command_result.py`、`themed_messagebox.py`、`file_dialog_subprocess.py` 的直接导入已通过 `qt_compat`。→ 另见 7.1.2（`IMP-02`）

**修复：** 将上表符号加入 `qt_compat.py`，对应文件改为 `from qt_compat import ...`。对 `QtWin` 等平台特有 API 使用 `try: except ImportError:` 封装。

#### [I18N-04] 6.5.4 无障碍支持缺失

- **优先级：P3（辅助功能合规性）**
- **建议耗时：** 持续改进

- **0 处** `setAccessibleName()` / `setAccessibleDescription()` 调用 — 屏幕阅读器无法识别任何控件
- **0 处** `setTabOrder()` 调用 — 对话框 Tab 顺序依赖构造顺序
- **0 处** `setShortcut()` 调用 — 无键盘快捷键
- 仅 **15 处** `setToolTip()` — 大多数交互控件无提示

**建议切入：** 先在 `welcome_guide.py`、`about_window.py` 等静态对话框上增加无障碍属性积累经验，再推广到复杂交互页面。

#### [I18N-05] 6.5.5 固定像素尺寸不随 DPI 缩放（108 处）

- **优先级：P2（高 DPI 屏幕显示异常）**
- **建议耗时：** 8h

`command_dialog.py`（25 处）、`icon_grid.py`（8 处）、`main_window.py`（7 处）等大量使用 `setFixedSize()`/`setFixedWidth()`/`setFixedHeight()` 硬编码像素值。

**修复：** 创建工具函数 `dp(value: int) -> int` 按屏幕缩放比例换算：
```python
from qt_compat import QtCore

def dp(value: int) -> int:
    """按当前屏幕逻辑分辨率缩放像素值"""
    screen = QApplication.primaryScreen()
    ratio = screen.logicalDotsPerInch() / 96.0 if screen else 1.0
    return int(value * ratio)
```

#### [I18N-06] 6.5.6 硬编码窗口尺寸不随屏幕缩放（8 处）

- **优先级：P2（4K 屏幕显示异常）**
- **建议耗时：** 2h

`icon_picker_dialog.py`、`log_window.py`、`diagnostics_window.py`、`welcome_guide.py` 等使用固定 `resize()` 值，在 4K 屏幕上过小，在小屏上可能溢出。

**修复：** 将 `resize(800, 600)` 改为 `resize(dp(800), dp(600))`，或设置最小尺寸而非固定尺寸。

#### [I18N-07] 6.5.7 硬编码颜色值绕过主题系统（144+ 处）

- **优先级：P2（主题切换不完整）**
- **建议耗时：** 6h

`ui/styles/style.py` 定义了 `Colors` 类但极少被引用。暗色/亮色颜色对 `QColor(28,28,30,180)` 等在 9+ 个文件中重复内联定义。→ 见 DRY-03

**修复：** 将 `Colors` 扩展为完整调色板，所有颜色引用从 `self._colors`（由 ThemeManager 注入）获取，消除内联 `QColor()`。

#### [I18N-08] 6.5.8 硬编码字体大小绕过 font_manager（108 处）

- **优先级：P2（DPI 缩放不一致）**
- **建议耗时：** 4h

大量 `QFont("family", size)` 直接调用绕过 `font_manager.get_qfont()`，字体大小不随 DPI 缩放。

**修复：** 全局搜索 `QFont(` 调用并替换为 `font_manager.get_qfont(size=N)`，确保 font_manager 是所有字体的唯一入口。

### 6.6 第六章修复行动路线图

| 优先级 | 任务 ID | 发现 | 建议耗时 | 预计收益 |
|--------|---------|------|---------|---------|
| **P0** | SEC-01 | `subprocess shell=True` 命令注入 | ✅ 已修复 | — |
| **P0** | SEC-05 | QR 服务器绑定 0.0.0.0 | ✅ 已修复 | — |
| **P0** | SEC-06 | `exec()` 代码执行 | 0.5h | 消除安全漏洞 |
| **P1** | SEC-02 | Signal/Slot 连接未断开 | 4h | 消除崩溃/内存泄漏 |
| **P1** | SEC-03 | processEvents() 重入 | 2h | 消除栈溢出风险 |
| **P1** | SEC-04 | QR 临时文件无清理 | 0.5h | 磁盘空间泄漏修复 |
| **P1** | SEC-07 | 硬编码 Windows 路径 | 1h | 系统兼容性修复 |
| **P1** | DRY-01 | 无边框窗口 4 份重复（~400 行） | 8h | 节省 400 行 + 统一修复入口 |
| **P1** | DRY-02 | JSON 状态 6+ 份重复（~120 行） | 4h | 节省 120 行 |
| **P1** | PERF-01 | 热路径重复磁盘 I/O | 1h | 弹窗性能提升 |
| **P1** | I18N-01 | 硬编码中文 117 处 | 16h | 国际化完整覆盖 |
| **P1** | I18N-02 | 翻译键缺失 56 个 | 3h | 英文模式正确显示 |
| **P1** | I18N-03 | 直接 PyQt5 导入 13 处 | 2h | PySide6 兼容性 |
| **P2** | DRY-03~09 | 其余代码重复（~370 行） | 12h | 节省 370 行 |
| **P2** | PERF-02~05 | 性能优化 | 8h | 内存/CPU 改善 |
| **P2** | API-01~06 | API 设计改进 | 10h | 可维护性提升 |
| **P2** | I18N-05~08 | 国际化补全 | 20h | 高 DPI/主题完整 |
| **P3** | I18N-04 | 无障碍支持 | 持续 | 辅助功能合规 |

---

## 七、深度扫描补充 II

> 以下内容基于 2026-05-31 五项专项扫描：导入组织与日志、Qt 控件生命周期、启动序列与平台特性、测试质量、代码约定与构建配置。

**扫描发现总览：**

| 子章节 | 领域 | 发现数 | 严重-HIGH | 优先级分布 |
|--------|------|--------|-----------|-----------|
| 7.1 | 导入组织与日志 | 6 类 | 1 HIGH(PII) | P1:2 P2:3 P3:1 |
| 7.2 | Qt 控件生命周期 | 5 类 | 3 HIGH | P0:1 P1:3 P2:1 |
| 7.3 | 启动序列与平台 | 3 类 | 2 HIGH | P1:2 P2:1 |
| 7.4 | 测试套件质量 | 5 类 | 1 HIGH | P1:2 P2:2 P3:1 |
| 7.5 | 代码约定与构建 | 6 类 | 1 HIGH | P1:1 P2:3 P3:2 |

### 7.1 导入组织与日志一致性

#### [IMP-01] 7.1.1 导入分组不规范

- **优先级：P3（代码风格）**
- **建议耗时：** 1h（可自动化）

**41.5%** 的生产文件（76/183）将所有导入写在一个块中，未用空行分隔标准库/第三方/本地三类。另 **6 个文件** 存在类别交叉（stdlib→第三方→stdlib），包括 `core/shortcut_command_exec.py`、`core/auto_start_manager.py`、`core/clipboard_service.py`、`qt_compat.py`。

**修复：** 运行 `ruff check --fix --select=I` 自动重排导入分组。

#### [IMP-02] 7.1.2 新增 qt_compat 绕过（2 个文件，与 I18N-03 交叉）

- **优先级：P1（阻碍 PySide6 迁移）**
- **建议耗时：** 1h

结合 6.5.3（I18N-03）更新的数据，当前仍有 **2 个文件** 需处理（`safe_file_dialog.py` 已修复）：

| 文件 | 行 | 导入内容 | 状态 |
|------|---|---------|------|
| `core/favicon_cache.py` | 860-861, 943-945 | `QByteArray`, `QGuiApplication`, `QPainter`, `QSvgRenderer` | `QSvgRenderer` 需加入 qt_compat |
| `core/icon_extractor.py` | 655 | `QtWin` | 需加入 qt_compat（带 try/except） |

**修复：** 统一通过 `qt_compat` 导入所有 Qt 符号。对 `QtWin` 等平台特有 API，在 `qt_compat.py` 中用 `try: except ImportError:` 封装。

#### [IMP-03] 7.1.3 生产代码中的 print()（1 处）

- **优先级：P2（调试残留）**
- **状态：✅ 已修复**
- **建议耗时：** —（无需操作）

`ui/config_window/command_dialog.py:1625` 的 `print()` 已在当前代码中移除。建议持续通过 CI lint 规则（`ruff check --select=T20`）防止 `print()` 重新引入。

#### [IMP-04] 7.1.4 PII 在 info 级别日志中泄露（~28 处）

- **优先级：P1（隐私合规风险）**
- **建议耗时：** 3h

**7 个文件** 在 `info` 级别记录用户命令路径、文件路径、目录结构：

| 文件 | 数量 | 泄露内容 | 敏感等级 |
|------|------|---------|---------|
| `core/shortcut_command_exec.py` | 6 | `{exe_path}`, `{command}` | HIGH |
| `core/shortcut_file_exec.py` | 8 | `{folder}`, `{file_path}`, `{cmd_args}` | HIGH |
| `core/config_migrator.py` | 7 | `{old_dir}`, `{new_dir}` | MEDIUM |
| `ui/launcher_popup/popup_drag_drop.py` | 3 | `{target}`, `{file_path}` | HIGH |
| `ui/launcher_popup/popup_item_execution.py` | 2 | `{item.name}` | MEDIUM |

**修复：** 降级到 `debug` 级别，或对路径进行基名截断，或使用 `_sanitize_path()` 工具函数：
```python
def _sanitize_path(path: str) -> str:
    """脱敏路径日志 — 仅保留文件名和父目录"""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if len(parts) <= 2:
        return path
    return f".../{parts[-2]}/{parts[-1]}"
```

#### [IMP-05] 7.1.5 日志器命名不一致

- **优先级：P2（调试/监控困难）**
- **建议耗时：** 1h

`bootstrap/logging_init.py:54` 使用 `logging.getLogger("main")` 而非 `__name__`，破坏了分层命名体系。2 个文件（`hooks/__init__.py`、`services/__init__.py`）使用日志但未定义模块级 logger。

**修复：** `logging_init.py` 中改用 `__name__`；为 `hooks/__init__.py` 和 `services/__init__.py` 添加模块级 `logger = logging.getLogger(__name__)`。

#### [IMP-06] 7.1.6 tray_mixins/__init__.py 导入风格不一致

- **优先级：P3（代码风格）**
- **建议耗时：** 0.25h

`ui/tray_mixins/__init__.py` 使用绝对导入（`from ui.tray_mixins.hooks_mixin import HooksMixin`），而所有同级 `__init__.py` 使用相对导入（`from .module import ...`）。统一为相对导入。

### 7.2 Qt 控件生命周期管理

> **风险说明：** Qt 控件生命周期问题是当前代码库最隐蔽的内存泄漏来源。所有窗口关闭路径必须确保 `deleteLater()` 被调用，避免旧实例通过信号槽闭包保持引用。

#### [QT-01] 7.2.1 隐藏窗口累积泄露（3 处）

- **优先级：P0（内存泄漏，长时间运行后显著）**
- **建议耗时：** 3h

| 文件 | 行 | 问题 | 影响 |
|------|---|------|------|
| `ui/tray_mixins/popup_mixin.py` | 305-336 | `_extra_popup_windows` 调用 `close()` 仅隐藏窗口，无 `deleteLater()`；每个新 popup 创建后旧 popup 累积 | 长时间使用后内存增长 |
| `ui/toast_notification.py` | 124-130 | Toast 单例替换时旧实例仅 `hide()`，2 个 QTimer 通过闭包保持引用 | 频繁 toast 时旧实例累积 |
| `ui/launcher_popup/popup_window.py` | 518-522 | `hideEvent` 中仅 `hide()`，无 `deleteLater()` 或 `WA_DeleteOnClose` | Popup 内存从不释放 |

**修复：** `close()` 后加 `deleteLater()`，或设置 `WA_DeleteOnClose`。
```python
# 推荐模式 — popup_mixin.py
def close(self):
    super().close()
    self.deleteLater()  # 确保 Qt 事件循环最终释放 C++ 对象
```

#### [QT-02] 7.2.2 孤立 QTimer：事件处理器中无 parent（3 处）

- **优先级：P2（偶发崩溃）**
- **建议耗时：** 1h

| 文件 | 行 | 问题 |
|------|---|------|
| `ui/tooltip_helper.py` | 20 | 每次 `enterEvent` 创建 `QTimer()` 无 parent，旧 timer 引用丢失后仍可能触发 |
| `ui/config_history_window.py` | 113 | 鼠标移动事件过滤器中创建 `QTimer()` 无 parent |
| `ui/custom_tooltip.py` | 106 | 类级单例每次 `showToolTip()` 重建 timer，旧 timer 孤立 |

**修复：** 统一改为 `QTimer(self)`；单例类应复用单个 timer 实例而非重建。→ 见 PERF-02

#### [QT-03] 7.2.3 不安全 QThread.terminate() 调用

- **优先级：P1（可能导致进程崩溃）**
- **建议耗时：** 4h

`ui/config_window/shortcut_dialog.py:340-347` — 清理线程路径中使用 `QThread.terminate()`（官方文档标注不安全），`finished.disconnect()` 无保护，`deleteLater()` 在线程可能仍在运行时调用。

`ui/config_window/url_dialog.py:730-746` — 同样模式。

**修复：** 改用 `requestInterruption()` + 线程内定期检查 `isInterruptionRequested()` 的协作取消模式：
```python
# 线程内
def run(self):
    while not self.isInterruptionRequested() and not self._work_done:
        self._do_chunk()

# 调用方
worker.quit()
worker.requestInterruption()
if not worker.wait(3000):
    worker.terminate()  # 仅作为超时后保底
worker.deleteLater()
```

#### [QT-04] 7.2.4 COM 初始化不平衡

- **优先级：P2（COM 资源泄漏）**
- **建议耗时：** 1h

`core/clipboard_service.py:204-213, 264-266` — `pythoncom.CoInitializeEx()` 调用后无对应 `CoUninitialize()`，长期运行线程中 COM 资源泄漏。

**修复：** 使用 `try/finally` 保证配对，或使用上下文管理器：
```python
import pythoncom

class ComScope:
    def __enter__(self):
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        return self
    def __exit__(self, *args):
        pythoncom.CoUninitialize()
```

#### [QT-05] 7.2.5 其他生命周期问题（4 项）

- **优先级：P1-P3 不等**
- **建议耗时：** 2h

| 问题 | 优先级 | 建议 |
|------|--------|------|
| `ui/tray_app.py:474-485` `close()` 后无 `deleteLater()` | P1 | 统一添加 `deleteLater()` |
| `ui/launcher_popup/popup_window.py:557-561` `closeEvent` 无 `deleteLater()` | P1 | 同上 |
| `ui/config_window/settings_plugins_page.py:618-629` lambda 指向已删除对象 | P2 | 使用 `weakref.proxy` 或断开连接 |
| 全库 **~55 处** `except RuntimeError: pass` 过于宽泛 | P3 | 改为仅捕获 `RuntimeError` 中已删除对象错误，其他继续抛出 |

### 7.3 启动序列与 Windows 平台

#### [STARTUP-01] 7.3.1 模块级导入过重（6 项）

- **优先级：P1（影响应用冷启动时间）**
- **建议耗时：** 6h

| 文件 | 问题 | 影响 | 建议 |
|------|------|------|------|
| `core/__init__.py` | 在模块级导入 6+ 个子模块 + 实例化 `CommandRegistry()` | 每次 `import core` 耗时 ~200ms+ | 使用 `__getattr__` 延迟导入 |
| `core/memory_guard.py:7` | 模块级 `import psutil` | psutil 即使未使用也被加载 | 函数内部延迟 import |
| `core/auto_start_manager.py:62-73` | 模块级 `ctypes.windll.user32` 等 5 个 DLL 解析 | 导入即触发 API 解析 | LazyDLL 封装 |
| `core/shortcut_types.py:7-11` | 模块级 `user32`, `shell32` DLL 解析 | 同上 | LazyDLL 封装 |
| `core/shortcut_window_control.py:7-8` | 模块级 DLL 解析 | 同上 | LazyDLL 封装 |
| `core/windows_uipi.py:27-63` | 模块级 DLL 解析 + `argtypes`/`restype` 设置 | 同上 | LazyDLL + 延迟加载 |

**修复：** 
- `core/__init__.py` 改用延迟导入模式（参考 `ui/config_window/__init__.py` 的 `__getattr__` 模式）：
```python
# core/__init__.py
def __getattr__(name):
    if name == "registry":
        from core.command_registry import CommandRegistry
        registry = CommandRegistry()
        globals()["registry"] = registry
        return registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```
- ctypes DLL 加载封装为惰性单例，避免模块级立即解析：
```python
# core/utils/lazy_dll.py
import ctypes

class LazyDLL:
    """延迟加载的 DLL 包装器 — 首次访问属性时才 LoadLibrary"""
    def __init__(self, dll_name: str):
        self._dll_name = dll_name
        self._dll = None

    def __getattr__(self, name):
        if self._dll is None:
            self._dll = ctypes.windll.LoadLibrary(self._dll_name)
        return getattr(self._dll, name)

# 使用（在模块级仅定义常量，不触发加载）
user32 = LazyDLL("user32.dll")   # 实际调用 user32.MessageBeep(0) 时才加载
shell32 = LazyDLL("shell32.dll")
```

#### [STARTUP-02] 7.3.2 硬编码 Windows 路径（⚠️ 部分已修复，见 SEC-07）

- **优先级：P1（系统兼容性/安全性）**
- **建议耗时：** 1h

与 **SEC-07** 重复。`plugins/disk_cleaner/main.py` 中的路径已修复（使用 `os.environ.get("SystemRoot", ...)`）。**仍有 1 处待修复：**

| 文件 | 行 | 当前代码 | 建议 |
|------|---|---------|------|
| `core/commands.py` | ~1144 | `System32\\drivers\\etc\\hosts` 硬编码 | 改为 `os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "drivers", "etc", "hosts")` |

**修复：** 统一使用 `os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", ...)` 拼接路径。

#### [STARTUP-03] 7.3.3 环境变量访问风格不一致

- **优先级：P3（代码风格）**
- **建议耗时：** 0.25h

`main.py:84,90,96` 使用 `os.environ.__setitem__()`（非惯用写法），应改为 `os.environ["KEY"] = val`。

### 7.4 测试套件质量与覆盖缺口

> **策略建议：** 测试修复应优先提升核心模块覆盖率（7.4.2），再解决基础设施问题（sys.path 污染、共享 fixture）。

#### [TEST-01] 7.4.1 sys.path 污染（22 个测试文件）

- **优先级：P1（测试隔离性/可重现性）**
- **建议耗时：** 2h

**22 个测试文件** 在模块级（收集时）修改 `sys.path`，是测试隔离问题。若执行顺序改变或依赖图变化，可能导致难以调试的失败。

**修复：** 在 `conftest.py` 的 `pytest_configure` hook 中集中设置 `sys.path`，删除各测试文件中的 `sys.path.insert`：
```python
# conftest.py
import sys
from pathlib import Path

def pytest_configure(config):
    root = Path(__file__).parent
    for d in ["core", "ui", "scripts"]:
        p = str(root / d)
        if p not in sys.path:
            sys.path.insert(0, p)
```

#### [TEST-02] 7.4.2 源文件-测试文件缺口（~68 个模块无测试）

- **优先级：P1（核心引擎无测试风险极高）**
- **建议耗时：** 24h（分批迭代）

高价值缺测模块（按风险排序）：

| 优先级 | 模块 | 行数 | 风险 | 推荐首个测试 |
|--------|------|------|------|-------------|
| **HIGH** | `core/shortcut_executor.py` | ~200 | 核心执行引擎，无任何测试 | `test_execute_basic_command` |
| **HIGH** | `core/i18n.py` | 527 | 翻译逻辑，有 F601 压制 | `test_translation_roundtrip` |
| **HIGH** | `core/pinyin_search.py` | — | 无任何测试 | `test_pinyin_search_index` |
| **HIGH** | `core/hotkey_manager.py` | — | 无任何测试 | `test_hotkey_register_unregister` |
| **HIGH** | `core/window_detection.py` | — | 无任何测试 | `test_window_from_point` |
| MEDIUM | `core/commands_maintenance.py` | — | 无任何测试 | `test_maintenance_cleanup` |
| MEDIUM | `ui/tray_mixins/` 全部 6 个模块 | — | 无任何测试 | 依次创建 smoke test |
| MEDIUM | `ui/config_window/` settings_* 页面 | — | 无单元测试 | `test_page_loads` |

#### [TEST-03] 7.4.3 无断言的测试函数（5 个）

- **优先级：P2（虚假的测试通过）**
- **建议耗时：** 1h

`test_preprocessing_examples.py` 中 **5 个测试函数** 仅检查"运行无错误"，无任何断言。若函数静默执行错误路径，测试仍会通过。

**修复：** 为每个函数添加至少一个断言验证输出或副作用，或标记为 `pytest.mark.smoke` 表明仅用于冒烟检测。

#### [TEST-04] 7.4.4 Fixture 太少（仅 1 个共享 fixture）

- **优先级：P2（测试代码重复）**
- **建议耗时：** 2h

全局 `conftest.py` 只有一个 `qapp` fixture。测试文件间缺乏共享 fixture，导致大量重复设置代码（`_SmokeManager` 在 2 个文件中分别定义）。

**修复：** 在 `conftest.py` 中添加共享 fixture：`temp_data_dir`、`mock_plugin_manager`、`mock_command_registry`。

#### [TEST-05] 7.4.5 插件缺少 __init__.py

- **优先级：P3（低风险）**
- **建议耗时：** 0.5h

全部 **8 个插件子目录** 缺少 `__init__.py` 文件，Python 3.3+ 虽然支持 namespace packages，但某些导入场景下可能出问题。添加空 `__init__.py` 确保兼容性。

### 7.5 代码约定与构建配置

#### [STYLE-01] 7.5.1 内联魔数（~18 处）

- **优先级：P2（可维护性）**
- **建议耗时：** 2h

`core/commands.py` 中大量阈值使用字面量而非命名常量：

| 位置 | 魔数 | 含义 |
|------|------|------|
| `commands.py:449` | `256 * 1024` | Base64 输入上限 |
| `commands.py:555` | `1024` | QR 码文本长度上限 |
| `commands.py:915` | `8` | SAN 显示条目上限 |
| `commands.py:994,1000` | `10` | 缺失/重复路径显示上限 |
| `commands.py:1443,1503` | `200` | 选中文本/剪贴板预览上限 |
| `fuzzy_search.py:189,194` | `3` | 最小搜索查询/标记长度 |

建议全部提取为模块级 `_MAX_*` 常量（如 `_MAX_BASE64_INPUT = 256 * 1024`）。

#### [STYLE-02] 7.5.2 重复延迟值散落（11 个唯一值）

- **优先级：P2（可维护性/调试困难）**
- **建议耗时：** 1h

`core/shortcut_hotkey.py` 中 `time.sleep()` 使用 9 种不同延迟（2ms~250ms），遍布整个文件。建议定义命名常量如 `KEY_DOWN_DELAY = 0.010`、`KEY_UP_DELAY = 0.005`、`TYPE_INTERVAL = 0.050`。

#### [STYLE-03] 7.5.3 布尔值比较反模式（3 处）

- **优先级：P3（代码风格）**
- **建议耗时：** 0.25h

```python
# PEP 8 禁止直接比较布尔值
core/shortcut_command_exec.py:2254  —  if result is False:   →  if not result:
core/command_registry.py:267         —  if result is False:   →  if not result:
ui/tray_mixins/popup_mixin.py:168   —  if paused_state is True: →  if paused_state:
```

#### [STYLE-04] 7.5.4 版本号硬编码在 5 处

- **优先级：P1（版本升级遗漏风险）**
- **建议耗时：** 1h

| 位置 | 内容 |
|------|------|
| `core/version.py:8` | `APP_VERSION = "1.6.1.0"` ← **唯一来源** |
| `build_win11_setup.bat:18` | `DEFAULT_APP_VERSION=1.6.1.0` |
| `build_encrypted.bat:18` | `DEFAULT_APP_VERSION=1.6.1.0` |
| `installer.iss:6` | `#define MyAppVersion "1.6.1.0"` |
| `installer.iss:15` | `#define MyAppFileVersion "1.6.1.0"` |

**修复：** 构建脚本使用 `.version` 文件或 `python -c "from core.version import APP_VERSION; print(APP_VERSION)"` 读取版本号，消除硬编码回退值。可创建 `pyproject.toml` 中 `[tool.quicklauncher] version` 作为单一事实来源。

#### [STYLE-05] 7.5.5 Qt 方法命名注解缺失（128+ 处）

- **优先级：P3（代码风格）**
- **建议耗时：** 0.5h（可批量替换）

`ui/` 下 128+ 个 Qt 事件重写方法（`paintEvent`、`mousePressEvent` 等）缺少 `# noqa: N802` 注解。项目约定允许 camelCase 但未正确标记。可在 `pyproject.toml` 的 ruff 配置中用 `[tool.ruff.lint.per-file-ignores."ui/**.py"] N802 = true` 全局压制。

#### [STYLE-06] 7.5.6 构建脚本问题（2 处）

- **优先级：P2（构建可靠性）**
- **建议耗时：** 1h

| 问题 | 影响 | 修复 |
|------|------|------|
| `QuickLauncher.spec:95` 硬编码 `python311.dll` | Python 升级后构建失败 | 从 `sys.version_info` 动态获取 Python 版本号 |
| `build_encrypted.bat:226` 排除 `pypinyin` | 拼音搜索功能在加密版本不可用 | 移除排除项或提供配置选项 |

### 7.6 第七章修复行动路线图

| 优先级 | 任务 ID | 发现 | 建议耗时 | 预计收益 |
|--------|---------|------|---------|---------|
| **P0** | QT-01 | 隐藏窗口累积泄露（3 处） | 3h | 消除长时间运行内存增长 |
| **P1** | IMP-02 | 新增 qt_compat 绕过（3 文件） | 1h | PySide6 迁移保障 |
| **P1** | IMP-04 | PII 在 info 日志泄露（~28 处） | 3h | 隐私合规 |
| **P1** | QT-03 | 不安全 QThread.terminate() | 4h | 消除进程崩溃风险 |
| **P1** | QT-05 | 其他生命周期问题（4 项） | 2h | 内存泄漏修复 |
| **P1** | STYLE-04 | 版本号硬编码 5 处 | 1h | 构建一致性 |
| **P2** | IMP-03 | 生产代码 print() | ✅ 已修复 | CI 规则持续预防 |
| **P2** | IMP-05 | 日志器命名不一致 | 1h | 监控能力提升 |
| **P2** | QT-02 | 孤立 QTimer（3 处） | 1h | 偶发崩溃修复 |
| **P2** | QT-04 | COM 初始化不平衡 | 1h | 资源泄漏修复 |
| **P2** | TEST-01 | sys.path 污染（22 文件） | 2h | 测试隔离性 |
| **P2** | TEST-02 | 68 模块缺测试 | 持续 | 质量保障 |
| **P2** | STYLE-01 | 内联魔数（~18 处） | 2h | 可维护性 |
| **P2** | STYLE-02 | 重复延迟值散落 | 1h | 可维护性 |
| **P2** | STYLE-06 | 构建脚本问题（2 处） | 1h | 构建可靠性 |
| **P3** | IMP-01 | 导入分组不规范 | 1h | 代码风格 |
| **P3** | IMP-06 | __init__.py 导入风格 | 0.25h | 代码风格 |
| **P3** | TEST-03 | 无断言测试函数（5 个） | 1h | 测试质量 |
| **P3** | TEST-04 | Fixture 太少 | 2h | 测试效率 |
| **P3** | TEST-05 | 插件缺 __init__.py | 0.5h | 兼容性 |
| **P3** | STYLE-03 | 布尔值比较反模式（3 处） | 0.5h | PEP 8 合规 |
| **P3** | STYLE-05 | Qt 方法命名注解缺失 | 0.5h | lint 正确性 |

---

## 八、深度扫描补充 III

> 以下内容基于 2026-05-31 五项专项扫描：数据模型与配置系统、插件与命令架构、错误处理与韧性、模块耦合与命名、IPC/更新/原生钩子。

**扫描发现总览：**

| 子章节 | 领域 | 发现数 | 严重-HIGH/CRITICAL | 优先级分布 |
|--------|------|--------|-------------------|-----------|
| 8.1 | 数据模型与配置系统 | 3 类 | 1 HIGH | P1:1 P2:2 |
| 8.2 | 插件系统与命令架构 | 8 类 | 4 HIGH | P0:2 P1:2 P2:2 P3:2 |
| 8.3 | 错误处理与系统韧性 | 13 类 | 6 HIGH | P0:1 P1:5 P2:5 P3:2 |
| 8.4 | 模块耦合与文件组织 | 6 类 | 1 HIGH | P1:1 P2:1 P3:4 |
| 8.5 | IPC、更新与原生钩子 | 8 类 | 1 CRITICAL + 3 HIGH | P0:1 P1:3 P2:4 |

### 8.1 数据模型与配置系统

#### [DATA-01] 8.1.1 线程安全缺口：PluginManager 和 CommandRegistry 缺少锁

- **优先级：P1（生产环境竞争条件）**
- **建议耗时：** 4h

`PluginManager`（`core/plugin_manager.py:595`）和 `CommandRegistry`（`core/command_registry.py:288`）的所有变异方法（`enable_plugin`、`disable_plugin`、`register`、`remove` 等）均无实例级锁，同时被 hooks 回调线程和 UI 线程访问时存在竞态条件。

- `PluginManager` 的 `_plugins`、`_loaded_modules`、`_active_apis` 字典无保护
- `CommandRegistry` 的 `_commands`、`_alias_map`、`_category_index` 无保护
- `_search_sources` 是唯一有 `threading.RLock()` 保护的数据

**修复：** 为两个类添加 `threading.Lock`，所有写操作加锁：
```python
class PluginManager:
    def __init__(self):
        self._lock = threading.Lock()

    def enable_plugin(self, plugin_id: str) -> bool:
        with self._lock:
            # ... 原有逻辑 ...
```

#### [DATA-02] 8.1.2 模型序列化不完整（12/20 类缺方向）

- **优先级：P2（持久化/迁移能力不足）**
- **建议耗时：** 4h

| 模型 | 缺失方法 | 所在文件 |
|------|---------|---------|
| `CommandParam`, `CommandAction`, `CommandContext`, `CommandResult`, `CommandDefinition` | 均无 `to_dict()`/`from_dict()` | `core/command_registry.py` |
| `PluginManifest` | 缺 `to_dict()` | `core/plugin_manager.py:90` |
| `PluginInfo` | 均无 | `core/plugin_manager.py:124` |
| `ConfigSnapshot` | 缺 `from_dict()` | `core/config_history.py:19` |
| `RepairIssue` | 缺 `from_dict()` | `core/config_repairs.py:20` |
| `RepairReport` | 缺 `from_dict()` | `core/config_repairs.py:40` |
| `TriggerContext`, `InteractionContext`, `FuzzyMatchResult` | 均无 | 各自文件 |

**修复：** 为每个类实现 `to_dict()` → `from_dict()` 双向序列化，确保未来可以序列化到 JSON/YAML 或生成快照对比。建议使用 `dataclasses` + `dataclasses.asdict()` 简化。

#### [DATA-03] 8.1.3 缺少 OS 级文件锁 ⚠️ 与 RESIL-01 重复

- **优先级：P2（多实例数据损坏）**
- **建议耗时：** —（与 RESIL-01 合并处理）

`DataManager` 使用 `threading.RLock`/`Lock`（进程内），但无跨进程文件锁。两个 QuickLauncher 实例同时写 `data.json` 可能导致数据损坏。→ ⚠️ **与 8.3.1 RESIL-01 完全重复，在 RESIL-01 统一处理**

**修复见 RESIL-01：** 使用 Windows 命名互斥量保护，或使用 `portalocker`：
```python
import portalocker

with portalocker.Lock("data.json", timeout=5):
    with open("data.json", "w") as f:
        json.dump(data, f)
```

### 8.2 插件系统与命令架构

#### [PLUGIN-01] 8.2.1 插件无沙箱隔离

- **优先级：P0（安全架构缺陷）**
- **建议耗时：** 评估（长线架构项）

所有插件运行在同一进程中，可直接 `import core.command_registry` 访问任意模块。权限系统仅在 `PluginAPI` 方法中检查，但插件可通过 `subprocess.run()`（`disk_cleaner`、`network_tools`、`event_inspector`）、`os.scandir`/`os.remove`（`disk_cleaner`）完全绕过。

代码注释自认：`"This is a voluntary check — plugins using raw open() can bypass it"`（`plugin_manager.py:187`）。

**短期缓解：** 添加运行时审计日志，记录插件对敏感 API 的调用（`subprocess`、`os.remove` 等）。**长期方案：** 子进程隔离或嵌入式 Python 沙箱（如 `pybox`）。

#### [PLUGIN-02] 8.2.2 插件无版本兼容检查

- **优先级：P1（API 变更静默破坏）**
- **建议耗时：** 2h

所有 8 个 `plugin.json` 无 `ql_min_version`、`api_version` 或 `manifest_version` 字段。未来 API 变更可能静默破坏插件。

**修复：** 
1. 在 `PluginManifest` 中添加 `api_version: int` 字段，当前定义为 `1`
2. 插件加载时校验 `api_version` 是否在支持范围内
3. 所有 `plugin.json` 补充 `"ql_min_version": "1.6.0.0"` 字段

#### [PLUGIN-03] 8.2.3 插件加载无超时保护

- **优先级：P1（启动阻塞风险）**
- **建议耗时：** 3h

`_do_load()`（`plugin_manager.py:895-940`）中如果插件的 `register()` 函数挂起，将无限期阻塞应用启动。

**修复：** 在独立线程中执行 `register()`，设置超时（默认 10s），超时后标记插件加载失败并继续启动：
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(plugin.register, api)
    try:
        future.result(timeout=PLUGIN_LOAD_TIMEOUT)
    except TimeoutError:
        logger.error(f"Plugin {plugin_id} load timed out")
```

#### [PLUGIN-04] 8.2.4 插件禁用时线程/子进程无清理

- **优先级：P2（禁用插件后残留资源）**
- **建议耗时：** 3h

`disable_plugin()` 清理了命令注册、搜索源和 `sys.modules`，但**不追踪**插件产生的线程、子进程或文件句柄。

**修复：** 在 `PluginAPI` 中增加注册/注销钩子，要求插件提供 `on_disable()` 回调来清理资源。文档明确插件开发者的清理责任。

#### [PLUGIN-05] 8.2.5 `/wifi` 命令注入风险

- **优先级：P1（潜在命令注入）**
- **建议耗时：** 1h

`core/commands.py:1113` — Wi-Fi 名称中如果包含特殊字符，通过 `netsh wlan show profile name={name}` 调用时可能导致命令注入（虽使用 list args 有部分保护，但 `name=` 前缀拼接仍危险）。

**修复：** 使用 `subprocess.Popen([...], shell=False)` 的 list 参数模式完全避免 shell 解释，同时确保参数传递不受特殊字符影响：

```python
# 修复前（当前代码模式 ≈）
subprocess.run(["netsh", "wlan", "show", "profile", f"name={name}"], capture_output=True)

# 修复后 — 将 name 值独立为单独的参数，避免前缀拼接引入注入向量
subprocess.run(
    ["netsh", "wlan", "show", "profile", "name=" + name],  # 或 name 作为独立参数
    capture_output=True,
    shell=False  # 确保非 shell 执行
)

# 更安全的做法：验证 name 格式
import re
if not re.match(r'^[\w\- ]+$', name):
    return CommandResult(success=False, message="无效的 Wi-Fi 名称")
result = subprocess.run(["netsh", "wlan", "show", "profile", f"name={name}"], ...)
```

#### [PLUGIN-06] 8.2.6 内置命令无全局超时

- **优先级：P2（大文件/网络操作阻塞 UI）**
- **建议耗时：** 4h

插件命令有 10s 超时（`ThreadPoolExecutor`），但内置命令（如 `/hash` 处理大文件）运行在 UI 线程上无超时。

**修复：** 将 `/hash` 等可能长时间运行的内置命令迁移到 `QThread` + 超时机制，保持 UI 响应。

#### [PLUGIN-07] 8.2.7 服务层无生命周期管理

- **优先级：P1（优雅关闭缺失）**
- **建议耗时：** 8h（重构 `service_manager.py`）

`core/service_manager.py` 是已废弃的 Windows 服务兼容层（文档标 `@deprecated`），不提供 `start()`/`stop()`/`restart()`、依赖管理或优雅关闭。

- 服务启动顺序隐式且脆弱（无依赖图）
- 无协调关闭：`UpdateChecker.stop()` 存在但从未调用
- 无健康监测：服务崩溃时无自动恢复

**修复：** 重构为 `ServiceRegistry` 单例，支持注册 `start`/`stop` 回调、依赖图解析、健康检查心跳。→ 见 8.3.13（协调关闭序列）

#### [PLUGIN-08] 8.2.8 2 个死命令处理器

- **优先级：P3（低影响）**
- **建议耗时：** 0.5h

`core/commands_windows.py` 中的 `cmd_env` 和 `cmd_god` 被导入但从未注册。`limit_command_result_actions()` 函数是空操作（`core/command_registry.py:87-93`）。建议移除未使用的函数和导入，或为其添加 TODO 注释说明保留理由。

### 8.3 错误处理与系统韧性

#### [RESIL-01] 8.3.1 缺少跨进程文件锁

- **优先级：P1（多实例数据损坏）**
- **建议耗时：** 2h

`DataManager` 的 `threading.Lock`/`RLock` 仅保护同一进程内的并发访问。两个实例同时写 `data.json` 可能数据损坏。建议使用 Windows 命名互斥量。→ 与 DATA-03 重复，应合并处理

**修复：** 使用 `threading.Lock` + Windows 命名 `mutex` 双重保护。

#### [RESIL-02] 8.3.2 窗口几何不持久化

- **优先级：P1（用户体验回归）**
- **建议耗时：** 4h

所有窗口（设置、命令面板、日志）每次打开使用默认位置/大小，用户调整后不保存。无 `QSettings.saveGeometry()`/`restoreGeometry()` 调用。

**修复：** 创建 `GeometryManager` mixin 或基类，自动保存/恢复窗口几何：
```python
class GeometryManager:
    def __init__(self, window_id: str):
        self._window_id = window_id
        self._settings = QSettings("QuickLauncher", "Geometry")

    def save(self, window):
        self._settings.setValue(f"{self._window_id}/geometry", window.saveGeometry())

    def restore(self, window):
        geo = self._settings.value(f"{self._window_id}/geometry")
        if geo:
            window.restoreGeometry(geo)
```

#### [RESIL-03] 8.3.3 无离线模式

- **优先级：P1（网络错误用户体验差）**
- **建议耗时：** 6h

网络操作（公网 IP 查询、更新检查、favicon 下载）失败时直接显示异常给用户，无优雅降级或无缓存回退。

**修复：** 为所有网络操作添加 `try/except` + 缓存回退。缓存有效期根据操作类型不同（IP 查询缓存 5min，favicon 缓存 24h）。网络不可用时显示"当前处于离线模式"友好提示而非异常堆栈。

#### [RESIL-04] 8.3.4 `except Exception` 过度使用（~1240 处）

- **优先级：P1（吞掉关键系统异常）**
- **建议耗时：** 持续（每次迭代修复 50-100 处）

全库约 **1240** 个 `except Exception` 块。`popup_renderer.py`（17 个）、`popup_data_refresh.py`（16 个）、`popup_window.py`（20+ 个）最严重。可能意外吞掉 `MemoryError`、`KeyboardInterrupt` 或 `SystemExit`。

**修复原则：** 
1. 将裸 `except Exception: pass` 改为 `except SpecificError: logger.warning(...)`
2. 确定不需要捕获的块使用 `except Exception: raise` 重新抛出
3. 事件处理器中使用 `except Exception: logger.error(exc_info=True)`

#### [RESIL-05] 8.3.5 `None` vs 异常返回值不一致

- **优先级：P2（使用方需猜测行为）**
- **建议耗时：** 3h

部分函数返回 `None` 表示失败，部分抛出异常，无统一约定。例如 `get_plugin()` 返回 `None` 而 `remove_plugin_record()` 抛出 `ValueError`（`core/plugin_manager.py:1264,1273`）。

**修复：** 制定项目约定：查询类函数返回 `Optional[T]`（失败返回 `None`），命令类函数抛出 `PluginError` 等自定义异常。逐步统一现有 API。

#### [RESIL-06] 8.3.6 自定义异常类使用不一致

- **优先级：P2（错误处理脆弱）**
- **建议耗时：** 2h

`core/plugin_manager.py` 抛出通用 `ValueError`、`FileNotFoundError`、`RuntimeError` 而非自定义异常。`core/data_manager.py` 抛出 `RuntimeError` 而非 `ConfigSaveError`。

**修复：** 在 `core/exceptions.py` 中定义异常层次体系，各模块使用专有异常：
```python
class QuickLauncherError(Exception): ...
class PluginError(QuickLauncherError): ...
class ConfigError(QuickLauncherError): ...
class ConfigSaveError(ConfigError): ...
```

#### [RESIL-07] 8.3.7 文件 I/O 无重试逻辑

- **优先级：P2（防病毒软件冲突场景）**
- **建议耗时：** 2h

关键文件写操作（config 保存、icon 缓存写）在防病毒软件保持文件句柄时可能失败，无重试机制。剪贴板已有 `_OPEN_RETRY_DELAYS_MS` 模式但文件操作未复用。

**修复：** 创建通用重试装饰器：
```python
def retry_on_failure(max_retries=3, delay_ms=100):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (IOError, OSError) as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay_ms / 1000)
        return wrapper
    return decorator
```

#### [RESIL-08] 8.3.8 表单验证仅工具提示

- **优先级：P2（用户体验）**
- **建议耗时：** 3h

验证错误通过 `setToolTip()` 显示（需悬停），无内联红色边框或图标指示。

**修复：** 为表单控件添加自定义验证样式（红色边框 + 错误图标 + 状态栏错误消息），使用 `QValidator` 或 `QLineEdit.textChanged` 信号实时验证。

#### [RESIL-09] 8.3.9 撤销功能有限

- **优先级：P3（增强功能）**
- **建议耗时：** 评估

仅 `icon_grid.py` 有批量快照式撤销，无 `QUndoStack` 集成，无 Ctrl+Z 支持，无法撤销单个编辑操作。

#### [RESIL-10] 8.3.10 更新系统无安装回滚

- **优先级：P1（更新失败后应用损坏）**
- **建议耗时：** 4h

`services/update/installer.py:95` — `sys.exit(0)` 无条件执行，不验证子进程是否成功启动。安装失败后无机制从备份恢复。

**修复：** 安装前备份 `%LOCALAPPDATA%/QuickLauncher` 到临时目录，安装后验证启动是否正常，失败则自动恢复备份。

#### [RESIL-11] 8.3.11 更新下载无断点续传

- **优先级：P2（大文件下载体验）**
- **建议耗时：** 3h

中断下载被完全丢弃，需重新下载全部内容。无 `Range` header 支持。

**修复：**
```python
headers = {"Range": f"bytes={downloaded}-"}
requests.get(url, headers=headers, stream=True)
```

#### [RESIL-12] 8.3.12 更新无重试机制

- **优先级：P2（瞬时网络失败）**
- **建议耗时：** 2h

瞬时网络失败直接上报，无指数退避重试。

**修复：** 使用 `tenacity` 库或自定义指数退避：`retry(max=3, delay=1, backoff=2)`。

#### [RESIL-13] 8.3.13 无协调关闭序列

- **优先级：P1（资源泄漏/状态不一致）**
- **建议耗时：** 4h

`main.py` 无 `atexit` 或 `app.aboutToQuit` 处理器来协调关闭 IPC 服务器、hooks、更新定时器和剪贴板 STA 线程。

**修复：** 在 `main.py` 中注册关闭序列：
```python
def shutdown_sequence():
    """按依赖顺序关闭各子系统"""
    services.update_service.stop()       # 1. 停止更新定时器
    ipc_server.shutdown()                # 2. 关闭 IPC
    hooks_manager.uninstall()            # 3. 卸载全局钩子
    clipboard_service.stop()             # 4. 退出剪贴板 STA 线程
    data_manager.save()                  # 5. 最终保存

app.aboutToQuit.connect(shutdown_sequence)
```

### 8.4 模块耦合与文件组织

#### [ARCH-01] 8.4.1 `core/diagnostics.py` 违反层边界

- **优先级：P1（架构原则违反）**
- **建议耗时：** 4h

`core/diagnostics.py` 从 `services/`（update session）和 `hooks/`（HooksDLL）导入。`core/` 是 UI 无关的业务层，不应依赖 services 或 hooks。

**修复：** 
- **短期：** 通过依赖注入将 `services` 和 `hooks` 引用传入
- **长期：** 将 `core/diagnostics.py` 移到独立的 `diagnostics/` 包，减少 `core/` 的耦合

#### [ARCH-02] 8.4.2 `core/__init__.py` 过重（209 行）

- **优先级：P2（启动性能 & 循环导入风险）**
- **建议耗时：** 3h

在模块级：导入 6+ 个子模块、定义全局状态（`_callbacks`、`registry = CommandRegistry()`）、执行初始化函数。每次 `import core` 触发大量副作用。→ 见 STARTUP-01

**修复：** 采用延迟导入模式，将 `registry = CommandRegistry()` 延迟到首次访问：
```python
# core/__init__.py
def __getattr__(name):
    if name == "registry":
        from core.command_registry import CommandRegistry
        registry = CommandRegistry()
        globals()["registry"] = registry
        return registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

#### [ARCH-03] 8.4.3 三个 God 模块

- **优先级：P2（变更影响面广）**
- **建议耗时：** 长期架构重构

`core/command_registry.py`、`core/commands.py`、`core/data_models.py` 分别有 60、55、52 个模块依赖它们（fan-in）。单一变更影响面极广。

**修复：** 逐步拆分 God 模块：`command_registry.py` 抽取出 `command_loader.py`、`command_index.py`；`commands.py` 按功能域拆分为 `commands_network.py`、`commands_file.py`、`commands_system.py`。

#### [ARCH-04] 8.4.4 自导入模式

- **优先级：P3（低影响但引起混淆）**
- **建议耗时：** 0.5h

`core/clipboard_service.py:9` 和 `core/selected_text_service.py:9` 各自在模块顶部 `from core.clipboard_service import clipboard_service`（导入自身），这是冗余的自我引用。

**修复：** 改为模块级 `clipboard_service = None` 占位，在 `init_app()` 中注入真实实例。

#### [ARCH-05] 8.4.5 缺少 `__init__.py`

- **优先级：P3（兼容性）**
- **建议耗时：** 0.5h

- `ui/utils/` — 6 个文件无包 init
- `tests/` — 113 个测试文件无包 init（影响 pytest namespace packaging）
- 全部 8 个插件目录无 `__init__.py`

#### [ARCH-06] 8.4.6 注释掉的代码（7 块）

- **优先级：P3（代码整洁）**
- **建议耗时：** 1h

| 文件 | 行 | 内容 |
|------|---|------|
| `ui/launcher_popup/popup_window.py` | 798-810 | 13 行注释掉的调试代码 |
| `core/shortcut_file_exec.py` | 656-660 | 5 行注释代码 |
| `ui/config_window/settings_support_page.py` | 48-52 | 5 行注释代码 |
| `ui/config_window/support_dialog.py` | 76-80 | 5 行注释代码 |
| `ui/utils/window_effect.py` | 650-654 | 5 行注释代码 |
| `core/command_registry.py` | 250-255 | 6 行注释代码 |
| `scripts/rebuild_popup.py` | 201-206 | 6 行注释代码 |

另 `safe_file_dialog.py` 和 `themed_messagebox.py` 各有 15/10 行注释掉的 `logger.debug` 语句。如确认无用则删除；如有保留价值则添加 TODO 注释说明理由。

### 8.5 IPC、更新系统与原生钩子 DLL

#### [NATIVE-01] 8.5.1 C++ 原生钩子：回调指针竞态条件

- **优先级：P0（可能造成进程崩溃）**
- **建议耗时：** 4h

`hooks_dll/hooks.cpp` 中 `g_mouseCallback`、`g_altDoubleClickCallback`、`g_altDoubleTapCallback`、`g_hotkeyCallback` 四个回调函数指针在被写入时无同步保护。Hook 线程可能读到半写入或空指针导致崩溃。

**修复：** 使用 `std::atomic` 存储所有回调指针：
```cpp
// hooks.cpp
#include <atomic>
std::atomic<MouseCallback> g_mouseCallback{nullptr};

void SetMouseCallback(MouseCallback cb) {
    g_mouseCallback.store(cb, std::memory_order_release);
}

// Hook 线程中读取
auto cb = g_mouseCallback.load(std::memory_order_acquire);
if (cb) cb(param);
```

#### [NATIVE-02] 8.5.2 C++ 全局变量混乱

- **优先级：P1（可维护性/线程安全）**
- **建议耗时：** 6h

`hooks.cpp` 约 **50 个全局变量**分散在整个模块，无 class/struct 封装。初始化顺序和线程安全性难以推理。

**修复：** 将全局变量封装到 `HookContext` 结构体中，使用 `std::unique_ptr<HookContext>` 全局实例管理生命周期。

#### [NATIVE-03] 8.5.3 C++ 内核句柄无 RAII

- **优先级：P1（句柄泄漏）**
- **建议耗时：** 4h

`CreateEvent`、`CreateThread`、`OpenProcess` 句柄手动管理，部分路径（如 `InstallMouseHook` 中途返回前未释放 `g_mouseReadyEvent`）泄漏句柄。

**修复：** 使用 RAII 包装器：
```cpp
class AutoHandle {
    HANDLE h_;
public:
    AutoHandle(HANDLE h = nullptr) : h_(h) {}
    ~AutoHandle() { if (h_) CloseHandle(h_); }
    AutoHandle(const AutoHandle&) = delete;
    AutoHandle& operator=(const AutoHandle&) = delete;
    HANDLE get() const { return h_; }
};
```

#### [NATIVE-04] 8.5.4 IPC 无协议版本号

- **优先级：P2（协议演进兼容性）**
- **建议耗时：** 2h

`QLocalServer` 的管道名硬编码 `"QuickLauncherInstance_v3"`，但消息体无版本字段。客户端和服务器必须完全锁步。

**修复：** 在 IPC 消息首部添加版本字段（如 `{"version": 1, "type": "open_url", ...}`），服务端校验版本，不兼容时返回 `VERSION_MISMATCH` 错误。

#### [NATIVE-05] 8.5.5 IPC 异常处理过于宽泛

- **优先级：P2（可能吞掉退出信号）**
- **建议耗时：** 1h

`bootstrap/ipc.py:38` 的 `except Exception` 会捕捉 `KeyboardInterrupt` 或 `SystemExit`。`finally` 块中才执行清理可能被跳过。

**修复：** 改为 `except (ConnectionError, TimeoutError, OSError):` 限定捕获类型。

#### [NATIVE-06] 8.5.6 选中文本服务：`keybd_event` 已弃用

- **优先级：P2（Windows 11 兼容性）**
- **建议耗时：** 2h

`core/selected_text_service.py:362-366` 使用 `keybd_event`（微软建议改用 `SendInput`），在 Windows 11 增强滚动等功能上可能失效。

**修复：** 改用 `ctypes.windll.user32.SendInput` 发送键盘事件，或使用 `pynput` 库替代低层级模拟。

#### [NATIVE-07] 8.5.7 剪贴板服务：STA 线程无退出信号

- **优先级：P2（线程泄漏）**
- **建议耗时：** 2h

`clipboard_service.py:257-278` 的 STA 工作线程在队列上无超时等待，主线程崩溃后该线程永久运行。

**修复：** 添加 `threading.Event` 退出信号：
```python
self._stop_event = threading.Event()

# 工作线程循环
while not self._stop_event.is_set():
    try:
        msg = self._queue.get(timeout=1.0)
        self._process_message(msg)
    except queue.Empty:
        continue

# 清理时
self._stop_event.set()
```

#### [NATIVE-08] 8.5.8 HooksMixin：`hotkey_manager` 可能为 None

- **优先级：P1（可能导致 AttributeError 崩溃）**
- **建议耗时：** 1h

`ui/tray_mixins/hooks_mixin.py:99-105` — `_install_keyboard_hook_and_hotkey` 在 `sleep_mixin.py:205` 被调用时 `self.hotkey_manager` 可能尚未初始化。

**修复：** 在 `_install_keyboard_hook_and_hotkey` 方法开头添加守卫检查，同时在 `sleep_mixin.py` 中调整调用时序确保初始化完成：

```python
# hooks_mixin.py — 守卫检查
def _install_keyboard_hook_and_hotkey(self):
    if self.hotkey_manager is None:
        logger.warning("hotkey_manager 尚未初始化，跳过键盘钩子安装")
        return
    # ... 原有逻辑 ...

# sleep_mixin.py — 改进调用时序（确保 hooks_mixin 先完成初始化）
def _on_sleep_resume(self):
    if hasattr(self, '_install_keyboard_hook_and_hotkey'):
        self._install_keyboard_hook_and_hotkey()
```

### 8.6 第八章修复行动路线图

| 优先级 | 任务 ID | 发现 | 建议耗时 | 预计收益 |
|--------|---------|------|---------|---------|
| **P0** | DATA-01 | PluginManager/CommandRegistry 缺少锁 | 4h | 消除竞态条件崩溃 |
| **P0** | PLUGIN-01 | 插件无沙箱隔离 | 16h | 安全基座 |
| **P0** | PLUGIN-05 | `/wifi` 命令注入风险 | 1h | 消除注入漏洞 |
| **P1** | DATA-03 | 缺少 OS 级文件锁 | 2h | 多实例数据安全 |
| **P1** | PLUGIN-02 | 插件无版本兼容检查 | 2h | 未来兼容性 |
| **P1** | PLUGIN-07 | 服务层无生命周期管理 | 8h | 优雅关闭 |
| **P1** | RESIL-01 | 跨进程文件锁（同 DATA-03） | 2h | — |
| **P1** | RESIL-02 | 窗口几何不持久化 | 4h | 用户体验 |
| **P1** | RESIL-03 | 无离线模式 | 6h | 网络容错 |
| **P1** | RESIL-04 | except Exception 过度使用（开始） | 8h | 渐进修复 |
| **P1** | RESIL-10 | 更新系统无安装回滚 | 4h | 更新可靠性 |
| **P1** | RESIL-13 | 无协调关闭序列 | 4h | 资源正确释放 |
| **P1** | COUPLE-01 | core/diagnostics.py 层边界违规 | 2h | 架构清晰 |
| **P1** | IPC-08 | HooksMixin hotkey_manager 可能为 None | 1h | 启动时序安全 |
| **P2** | DATA-02 | 模型序列化不完整（12/20 类） | 4h | 可序列化性 |
| **P2** | PLUGIN-03 | 插件加载无超时 | 2h | 启动可靠性 |
| **P2** | PLUGIN-04 | 插件禁用无清理 | 3h | 资源泄漏修复 |
| **P2** | PLUGIN-06 | 内置命令无全局超时 | 4h | UI 响应性 |
| **P2** | RESIL-05~09 | 错误处理改进 | 12h | 系统韧性提升 |
| **P2** | RESIL-11~12 | 更新下载改进 | 6h | 更新体验 |
| **P2** | IPC-01~03 | C++ 钩子安全加固 | 8h | 原生代码可靠性 |
| **P2** | IPC-04~07 | IPC/服务改进 | 6h | 通信可靠性 |
| **P3** | PLUGIN-08 | 死命令处理器清理 | 0.5h | 代码整洁 |
| **P3** | COUPLE-02~06 | 模块耦合优化 | 6h | 可维护性 |

### 8.7 总结：总体行动路线

本计划涵盖 **11 大类 600+ 项可优化点**，建议按以下节奏推进：

| 阶段 | 范围 | 预计耗时 | 目标 |
|------|------|---------|------|
| **Sprint 1（安全急救）** | P0 项（SEC-01/05/06, QT-01, DATA-01, PLUGIN-01/05） | ~2 周 | 消除已知安全漏洞和崩溃 |
| **Sprint 2（核心加固）** | P1 安全+生命周期+国际化 | ~4 周 | 隐私合规、内存安全、国际化覆盖 |
| **Sprint 3（质量提升）** | P2 项 + 测试补全 | ~6 周 | 代码可维护性、测试覆盖率 >50% |
| **Sprint 4（架构优化）** | 大文件拆分 + 模块解耦 + C++ 重构 | ~8 周 | 构建可靠性、架构清晰度 |
| **持续** | P3 项 | 各迭代穿插 | 渐进式代码整洁 |

**关键验收标准：**
1. `pytest tests/ --cov=core --cov=ui --cov-fail-under=50` 通过
2. `ruff check --select=E,F,W,I,B4,C4,UP,FA --fix` 零错误
3. 安全扫描无 P0 级别漏洞
4. 英文模式下所有 UI 字符串正确显示英文
5. 应用连续运行 48h 无内存增长


