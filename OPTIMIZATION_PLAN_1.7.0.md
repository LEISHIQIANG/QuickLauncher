# QuickLauncher 1.6.3.3 → 1.7.0 优化计划

## 一、问题总览

| 优先级 | 问题 | 严重度 | 可行性 | 当前 | 目标 |
|--------|------|--------|--------|------|------|
| P0 | i18n 翻译质量低 | 用户可见 | 高 | 1098 条中 7% 不可理解 | 全量人工审查通过 |
| P0 | i18n 架构不可扩展 | 未来阻塞 | 中 | 纯字典查表 | 引入 Provider 抽象层 |
| P1 | broad except 泛滥 | 运行时风险 | 高 | 1453 处 | ≤1200 处 |
| P1 | main.py 防御性过度 | 可维护性 | 高 | 750 行 | ≤300 行 |
| P1 | 全局回调表无类型 | 代码质量 | 中 | `_callbacks: dict` | ServiceRegistry + Literal 键 |
| P2 | TYPE_CHECKING 冗余 | 代码质量 | 中 | 15 个文件 | ≤10 个文件 |
| P2 | per-file-ignores 过多 | lint 公信力 | 中 | 10 个 | ≤3 个 |

P3 项目（vendored protobuf / 大文件继续拆分 / e2e 框架）放入 1.8.0 规划，不在本版范围。

---

## 二、P0 项目

### 2.1 i18n 翻译质量修正

**问题**：前 50 行已发现 7 处翻译不可用（`取消`→`X`、`启动失败`→`Fail`、`错误`→`Err` 等）。

**执行**：
1. 遍历 `_EN_US` 字典 1098 条逐条审查，统一为完整英文短句/标准 UI 术语
2. 错误消息必须含操作建议，参考 Windows/macOS 系统级 UI 惯例
3. 用 `check_i18n_coverage.py` 复核未译率（当前 2.16%，目标 ≤1%）

**验收**：英语环境下零中文 fallback；至少 5 个对话框翻译可被英语用户正确理解。

**风险**：无，纯数据修改。

### 2.2 i18n 架构升级

**目标**：在不动现有字典数据的前提下加一层抽象，为插件化翻译源做准备。

**执行**：
1. 定义 `TranslationProvider` Protocol
2. `tr()` / `_repr_en()` 改为走 Provider，默认 `DictionaryProvider`
3. 提供 `register_translation_provider(name, provider)` 接口，支持用户目录 `.po` 自动加载

**验收**：
- 现有行为完全不变
- 第三方可注册翻译源（即便本版不提供第三种语言包）

**不在范围**：复数 / RTL / ICU MessageFormat — 当前用户群无此需求，预留扩展点即可。

---

## 三、P1 项目

### 3.1 broad except 治理

**策略**：分批治理，每批锁定一个子系统的 `--max-total` 阈值。

**第一批**（6 个大文件，预期降 100 处）：

| 目标文件 | 当前 | 目标 |
|----------|------|------|
| `core/shortcut_command_exec.py` | 39 | ≤25 |
| `core/auto_start_manager.py` | 36 | ≤20 |
| `core/plugin_manager.py` | 32 | ≤20 |
| `ui/config_window/main_window.py` | 29 | ≤18 |
| `ui/config_window/icon_grid.py` | 29 | ≤18 |
| `ui/launcher_popup/popup_search.py` | 25 | ≤15 |

**替换规则**（写入 `scripts/audit_broad_exceptions.py`）：
1. OS 调用 → `except OSError`
2. JSON/YAML 序列化 → `except (json.JSONDecodeError, yaml.YAMLError)`
3. 文件 I/O → `except (FileNotFoundError, PermissionError, OSError)`
4. 子进程 → `except (subprocess.SubprocessError, OSError)`

**保留**：`logger.error(...)` 后立即 re-raise 的模式、主事件循环/钩子线程/插件加载入口。

**验收**：
- `release_gate.py` 的 `--max-total` 从 1400 → 1300；`--max-unlogged` 从 300 → 180
- 每个被替换的 except 块以注释记录具体异常类型

### 3.2 main.py 精简

**问题**：750 行，前 120 行中 ~60 行用于环境变量设置。

**执行**：
1. 将 6 处 `safe_execute(lambda: os.environ.setdefault(...), ...)` 合并为 `_apply_default_env_overrides()`
2. `_sanitize_gui_env()` 改为白名单模式（显式保留变量）
3. startup 逻辑抽到 `bootstrap/main_startup.py`

**验收**：启动行为不变；`main.py` ≤300 行；env 设置不超过 20 行。

### 3.3 全局回调注册表类型化

**问题**：`core/__init__.py` 的 `_callbacks: dict` + 字符串键，2 处注册 + 3 处调用。

**注意**：此机制是 Nuitka 冻结模块后绕开动态 import 的 workaround，**不是架构债**，必须保留。

**执行**：
1. 抽到 `bootstrap/service_registry.py`，定义为 `ServiceRegistry` 类（线程安全）
2. 键名改为 `Literal["show_config_window", "show_main_popup", ...]`，IDE/mypy 可检查
3. 旧接口 `core.register_callback()` 保留为兼容适配器

**验收**：注册和调用均记录日志；有类型注解；旧代码无需一次性迁移。

---

## 四、P2 项目

### 4.1 TYPE_CHECKING 清理

- Qt 相关 `TYPE_CHECKING` 保留（PyQt5 `.pyi` 不完善，mypy 必需）
- 逐文件 audit：区分"真解决循环导入"与"偷懒"
- 可推断的改为运行时 `__init__` 直接赋值
- 目标：15 → ≤10 个文件，mypy 严格模式仍 0 错误

### 4.2 per-file-ignores 清理

| 文件 | 规则 | 可修性 |
|------|------|--------|
| `core/__init__.py` | E402 | 可 — lazy import |
| `core/i18n.py` | F601 | **保留**（翻译补丁加载必需） |
| `core/pinyin_search.py` | F601 | **保留**（同上） |
| `tests/test_builtin_commands_suite.py` | E402 | 可 — 调整 import 顺序 |
| `tests/test_popup_search_ui.py` | E402 | 可 |
| `ui/config_window/main_window.py` | E402 | 可 |
| `ui/config_window/settings_panel.py` | E402 | 可 |
| `core/chain/__init__.py` | F401 | 可 — 清理 unused import |
| `ui/launcher_popup/popup_data_refresh.py` | F401 | 可 |
| `ui/launcher_popup/popup_window.py` | F401 | 可 |

**目标**：10 → ≤3 个（保留 i18n.py + pinyin_search.py 两个 F601）。

---

## 五、执行路线

```
Week 1-2:  P0 i18n 翻译修正（1098 条全量审查）
Week 3:    P0 i18n Provider 抽象层
Week 4:    P1 main.py 精简（750→300）
Week 5-6:  P1 broad except 第一批（6 文件，-100 处）
Week 7:    P1 ServiceRegistry 迁移
Week 8:    P2 TYPE_CHECKING + per-file-ignores 清理
          → 1.7.0 Release
```

## 六、度量指标

| 指标 | 当前 | 1.7.0 目标 | 校验工具 |
|------|------|-----------|---------|
| `except Exception` 总数 | 1453 | ≤1200 | `audit_broad_exceptions.py` |
| 未记录日志/未重抛的 except | ~300+ | ≤180 | 同上 |
| i18n 未译率 | 2.16% | ≤1% | `check_i18n_coverage.py` |
| per-file-ignores 文件数 | 10 | ≤3 | `ruff check` |
| TYPE_CHECKING 文件数 | 15 | ≤10 | grep |
| main.py 行数 | 750 | ≤300 | `wc -l` |
| mypy 严格模式 | 0 错误 | 0 错误 | `mypy core/ ui/ hooks/` |
| release_gate | 全过 | 全过（基线更严格） | `release_gate.py --dry-run` |
