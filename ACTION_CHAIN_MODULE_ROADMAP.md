# QuickLauncher 动作链模块规划

> 目标：把当前动作链从“可串行执行的快捷方式列表 + 初步节点画布”，逐步建设成接近 Grasshopper 思路的模块化编程系统：电池清晰、端口可信、数据流可视、运行可调试、可扩展、可测试、可复用。

## 1. 当前结论

动作链模块已经不再是完全空白的雏形，它已经具备了几个重要基础：

- 有执行器：`core/shortcut_chain_exec.py` 可以按步骤执行动作链，支持取消、延迟、失败中断、输出产物传递、快捷方式执行、处理器节点执行。
- 有数据模型：`core/data_models.py` 保存 `chain_steps` 和 `chain_canvas`，支持旧步骤到画布的兼容转换。
- 有端口契约：`core/chain_contracts.py` 能根据节点类型生成输入/输出端口，并做连接方向、顺序、端口存在性、基础类型兼容校验。
- 有电池库：`core/chain_processors.py` 已有文本、逻辑、列表、数学、JSON、HTTP、文件路径、图像等一批处理器电池，并提供端口 kind、role、说明、参数控件、安全级别和示例。
- 有画布 UI：`ui/config_window/chain_canvas.py` 已经支持节点、端口、连线、拖拽、吸附、选择、删除、属性面板、脚本电池源码编辑、运行状态渲染。
- 有编辑对话框：`ui/config_window/chain_dialog.py` 已有 Grasshopper 风格分组按钮、动作链属性、测试运行、风险提示、保存回写。
- 有测试：`tests/test_shortcut_chain_exec.py`、`tests/test_chain_dialog.py`、`tests/test_math_processors.py` 已覆盖基础执行、绑定、画布编译、处理器结果等。

但它距离“成熟的模块化编程系统”还差几个核心层：

- 图模型还不是执行模型的第一公民，当前仍然是“画布编译成线性步骤，再执行步骤”。
- 电池注册、端口类型、参数 UI 和运行实现仍在同一大文件附近组织，后续应继续拆成 manifest/schema/handler 模块。
- 数据值已经有 `ChainValue`、`typed_chain_values`、`typed_inputs` / `typed_outputs`，但执行入口仍是线性步骤，不是完整图运行时。
- 调试能力已能查看节点输入/输出快照、端口 tooltip 和连线值预览，但还缺少单节点运行、局部运行、时间线和导出诊断包。
- 电池库已有统一 schema、安全分级和契约测试，仍需要为图片、HTTP、文件下载等外部环境电池补更细的 mock/边界测试。
- 缺少动作链模板、子链复用、版本迁移、导入导出、插件扩展电池等成熟能力。

## 2. 成熟形态

成熟后的动作链应该是 QuickLauncher 里的“个人自动化搭建器”，而不是简单的多步骤执行器。

### 2.1 用户体验目标

用户应该能做到：

- 像 Grasshopper 一样拖出电池、连接端口、看到数据流。
- 从快捷方式、命令、文件、剪贴板、选中文本、窗口、网络、AI/API、系统信息等来源取数据。
- 用文本、列表、JSON、文件、条件、循环、分支、错误处理等电池组合流程。
- 单独测试某个电池，或从任意节点开始测试一段流程。
- 点击任意连线/端口查看上一次运行的数据。
- 将常用流程保存为模板，或打包成“子链电池”在其他动作链里复用。
- 安全地执行有风险的操作：删除、覆盖、命令执行、网络请求、管理员权限、脚本执行都应有清晰提示和确认策略。

### 2.2 工程目标

工程上应该形成以下分层：

```text
动作链 UI 层
  - 画布、节点库、属性面板、调试面板、模板面板

动作链图模型层
  - ChainGraph、ChainNode、ChainConnection、ChainPort、ChainValue
  - 负责保存、迁移、校验、编译和布局

动作链运行时层
  - 调度、拓扑排序、取消、超时、重试、错误传播、运行快照

电池注册层
  - 电池 manifest/schema、端口定义、参数 UI 定义、分类、图标、安全级别

电池实现层
  - 内置电池、插件电池、脚本电池、快捷方式电池、子链电池

测试与诊断层
  - 电池单测、契约测试、动作链回放测试、运行日志、导出诊断包
```

## 3. 当前模块诊断

### 3.1 执行器

当前文件：`core/shortcut_chain_exec.py`

优点：

- 线性执行逻辑清晰。
- 支持 `cancel_event`。
- 支持 `delay_ms`。
- 支持 `stop_on_error`。
- 支持 `param_bindings`、`input_binding`、`args`。
- 支持从 `CommandOutputArtifact` 生成 `chain_values`。
- 能执行快捷方式节点和 processor 节点。

不足：

- 执行结果已经包含节点级 `node_snapshots`，并记录 `typed_inputs` / `typed_outputs`、耗时、状态和错误。
- 运行时没有明确的 `ChainRunContext`、`NodeRunContext`、`PortValueStore`。
- `previous_output` 与 `chain_values` 并存，概念容易重复。
- 对 processor 的输入准备和 shortcut 的输入准备混在执行器里。
- 只能顺序执行，虽然当前画布限制了后向连接，但未来分支/汇聚/子图会受限。
- 没有节点级超时、重试、禁用原因、错误传播策略。
- 脚本电池没有取消/超时控制。

### 3.2 电池实现

当前文件：`core/chain_processors.py`

优点：

- 已有较多内置电池。
- 已经有 `ChainProcessorDefinition`。
- 支持 `python_cell` 自定义输入/输出。
- 输出统一放进 `payload["outputs"]`，便于动作链传递。

不足：

- `PROCESSOR_DEFINITIONS`、端口元数据、执行分发、具体实现全在一个文件里，后续会膨胀。
- 电池定义已经包含参数类型、默认值、选择项、说明、示例、安全级别和 capability；下一步应从单文件注册表拆成更清晰的 schema/handler 目录。
- 电池输出类型依赖 `core/chain_contracts.py` 的推断规则，容易出现定义和实现不一致。
- 部分电池名称和行为不够清晰，例如 JSON、列表、图像、HTTP 电池需要明确边界和失败语义。
- 网络、文件、脚本类电池已有风险标记；运行限制还需要继续完善，例如超时、授权禁用、覆盖确认和更细的沙箱边界。
- 脚本电池的 `exec` 沙箱非常轻，适合本地高级用户，但不能当作强安全边界。

### 3.3 端口契约

当前文件：`core/chain_contracts.py`

优点：

- 已有 `ChainPortSpec`。
- 已有方向、端口存在、未来依赖、类型兼容校验。
- 支持快捷方式根据命令参数和变量自动暴露输入端口。
- 支持 processor 动态端口。

不足：

- 端口类型仍是字符串枚举，但运行时已经通过 `ChainValue` 保留结构化值、预览文本和原始值。
- 兼容规则已收紧：普通 `text` 不再自动接到 number/bool/json/file/folder/url/list；只有目标端是字符串时允许安全展示型转换。
- 没有端口多输入的合并策略定义，例如 join、list、first、last。
- 没有端口是否必填、默认值、帮助文案、示例值、敏感值标记。
- 没有连接级 warning，例如“文本转文件路径可能不存在”“HTTP 输出是文本不一定是 JSON”。

### 3.4 画布 UI

当前文件：`ui/config_window/chain_canvas.py`

优点：

- 已有节点与连线基础交互。
- 支持拖拽、吸附、实时连线跟随、键盘删除/移动/多选。
- 支持属性面板展示输入端口、断开连接、编辑静态参数。
- 支持 panel 节点预览运行结果。
- 支持脚本电池源码弹窗。

不足：

- 画布是视觉编辑器，还不是完整调试器。
- 已能通过节点属性和 tooltip 查看端口值、连接来源值和运行输入/输出快照；还需要更完整的数据检查器面板。
- 没有节点搜索、快速添加、收藏、最近使用、模板。
- 没有撤销/重做。
- 没有框选后的批量设置、复制粘贴、复制子图、自动排版。
- 属性面板只按端口生成输入框，缺少按电池 schema 生成专业控件。
- 节点状态只有 ok/failed/skipped，缺少 running、warning、dirty、stale、cached。

### 3.5 编辑对话框

当前文件：`ui/config_window/chain_dialog.py`

优点：

- 已经把 QL 快捷方式和 processor 电池放在顶部模块栏。
- 能保存动作链名称、图标、结果窗口大小。
- 能测试运行并把运行状态映射回节点。
- 有基础风险分析。

不足：

- 顶部模块栏只是按钮集合，缺少搜索、分类说明、图标、文档、参数预览。
- 右侧面板空间利用还不够，调试信息不足。
- 风险分析只覆盖部分情况，没有基于电池安全级别。
- 测试运行只能整链运行，不能局部运行、单节点运行、从此节点运行。
- 保存时仍然依赖 `compile_canvas_to_steps()`，图结构不是最终执行来源。

## 4. 总体路线图

建议分 5 个阶段推进。近期先打地基，不急着堆更多电池；否则电池越多，后面返工越痛。

### 阶段 A：近期稳定化与契约固化，0-8 周

目标：让现有动作链可靠、可调试、可扩展。重点不是“看起来更多”，而是“每个已有能力都能放心用”。

关键成果：

- 电池定义从实现文件中拆出，形成统一 schema。
- 每个电池都有端口类型、参数类型、默认值、说明、示例、安全级别。
- 运行结果产生节点级快照，可在 UI 查看。
- 画布保存、步骤编译、执行结果三者保持一致且可测试。
- 建立电池质量门槛，新增电池必须有单测和契约测试。

### 阶段 B：Grasshopper 风格编辑体验完善，2-4 个月

目标：让用户能快速搭建、看懂、调试和修改动作链。

关键成果：

- 快速搜索添加电池。
- 撤销/重做、复制粘贴、批量移动、自动排版。
- 节点/连线/端口值预览。
- 单节点测试、局部测试、从当前节点测试。
- 错误定位和修复建议。
- 常用动作链模板。

### 阶段 C：图运行时与高级控制流，4-8 个月

目标：从线性步骤升级为图运行时，支持更自然的数据流。

关键成果：

- `ChainGraph` 成为执行入口。
- 拓扑排序、依赖检查、脏节点、缓存、增量运行。
- 条件分支、合并、循环、批处理、map/filter/reduce 类电池。
- 子链电池：一个动作链可以作为另一个动作链的电池。
- 可配置超时、重试、错误分支。

### 阶段 D：电池生态与插件化，8-12 个月

目标：让电池库可持续扩展，内置电池和插件电池使用同一套规则。

关键成果：

- 插件可以注册动作链电池。
- 电池包可以带 manifest、图标、示例、测试。
- 电池市场/个人库/收藏。
- 动作链模板导入导出。
- 电池版本兼容与迁移。

### 阶段 E：成熟产品化，12 个月以上

目标：动作链成为 QuickLauncher 的核心差异化能力。

关键成果：

- 可视化调试器成熟。
- 性能稳定，复杂图不卡顿。
- 安全策略完整。
- 文档、示例库、模板库完善。
- 支持更多外部集成：剪贴板、窗口、网页、API、AI、文件批处理、系统自动化。

## 5. 近期最需要做的内容

下面是最重要的近期路线。建议按顺序执行，不要跳过第 1-3 项。

### 5.1 第 1 优先级：固化电池定义 schema

当前 `ChainProcessorDefinition` 太薄，必须扩展。

建议新增或改造：

```python
@dataclass(frozen=True)
class ChainProcessorDefinition:
    id: str
    title: str
    category: str
    description: str
    inputs: list[ChainPortDefinition]
    outputs: list[ChainPortDefinition]
    params: list[ChainParamDefinition]
    safety: ChainProcessorSafety
    examples: list[ChainProcessorExample]
    source: str = ""
```

建议端口定义：

```python
@dataclass(frozen=True)
class ChainPortDefinition:
    id: str
    label: str
    kind: str
    required: bool = False
    multiple: bool = False
    default: str = ""
    description: str = ""
```

建议参数定义：

```python
@dataclass(frozen=True)
class ChainParamDefinition:
    id: str
    label: str
    kind: str
    default: str = ""
    choices: list[str] = field(default_factory=list)
    multiline: bool = False
    required: bool = False
    placeholder: str = ""
    description: str = ""
```

建议安全定义：

```python
@dataclass(frozen=True)
class ChainProcessorSafety:
    level: str  # safe, caution, dangerous
    reads_files: bool = False
    writes_files: bool = False
    network: bool = False
    executes_code: bool = False
    requires_confirmation: bool = False
```

近期落地任务：

- 在 `core/chain_processors.py` 中先扩展 dataclass，但保持旧调用兼容。
- 把现有 `PROCESSOR_DEFINITIONS` 补齐 category、description、params、safety。
- `processor_input_ports()`、`processor_output_ports()` 继续返回字符串列表，避免一次性影响 UI。
- 新增 `processor_definition(processor_id)`，给 UI 和测试读取完整定义。
- 新增 `tests/test_chain_processor_definitions.py`，检查每个电池 id 唯一、端口 id 唯一、输入输出至少一个、实现存在、参数默认值可序列化。

验收标准：

- 所有现有测试通过。
- 每个内置电池都有完整 definition。
- 新增电池如果缺少定义字段，测试失败。

### 5.2 第 2 优先级：建立节点运行快照

当前测试运行只把 list item 的 detail 映射回节点，信息太少。

建议新增结构：

```python
@dataclass
class ChainNodeRunSnapshot:
    node_id: str
    order: int
    title: str
    status: str
    started_at: float
    duration: float
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    message: str
    error: str
    warnings: list[str]
```

运行结果 payload 建议新增：

```python
payload = {
    "items": [...],
    "duration": 1.23,
    "node_snapshots": {
        "node-id": {
            "status": "ok",
            "inputs": {...},
            "outputs": {...},
            "duration": 0.12,
            "message": "...",
            "error": ""
        }
    }
}
```

近期落地任务：

- 在 `core/shortcut_chain_exec.py` 执行每步前记录 resolved args/input_values。
- 每步执行后记录 artifact outputs、stdout、stderr、files、folders、urls。
- `ChainCanvasWidget.set_run_status()` 优先按 node id 映射，不再只按顺序映射。
- `NodePropertyPanel` 增加“上次运行”区域，显示输入、输出、耗时、错误。
- 对 panel 节点保留大预览，但数据来自 snapshot outputs。

验收标准：

- 运行后每个节点能看到自己的输入和输出。
- 节点顺序改变后，运行结果仍能正确映射到对应节点。
- 错误节点能显示错误原因和失败输入。

### 5.3 第 3 优先级：统一值类型系统

当前值主要是字符串，端口类型只是校验提示。成熟动作链需要可追踪的值。

建议新增：

```python
@dataclass
class ChainValue:
    kind: str
    value: Any
    text: str
    preview: str
    metadata: dict[str, Any]
```

近期不要全面重写，先做轻量过渡：

- 保持 `chain_values` 的字符串 key lookup，兼容现有执行。
- 另外生成 `typed_values`，保存每个端口的 kind 和原始值。
- 输出 artifact 转 chain values 时同时产生文本值和类型值。
- 电池输出先继续返回 `CommandResult`，但 `_ok_outputs()` 支持保留 list/dict 的原始值到 typed snapshot。

近期落地任务：

- 在 `core/chain_contracts.py` 增加 `ChainValueKind` 常量或 enum。
- 在 `core/shortcut_chain_exec.py` 维护 `typed_chain_values`。
- 对 list/json/file/folder/url/number/bool 做标准转换函数。
- 类型不兼容时给 warning 或 fail，由端口定义决定严格程度。

验收标准：

- 列表电池输出到列表输入时，不丢失列表结构。
- JSON 电池输出到 JSON 输入时，不依赖用户手动复制字符串。
- UI 预览能区分文本、列表、JSON、文件路径。

### 5.4 第 4 优先级：拆分电池实现文件

`core/chain_processors.py` 会越来越难维护。建议按类别拆分。

建议目录：

```text
core/chain/
  __init__.py
  definitions.py
  values.py
  runtime.py
  registry.py
  contracts.py
  processors/
    __init__.py
    basic.py
    text.py
    logic.py
    list_math.py
    json_http.py
    file_path.py
    image.py
    script.py
```

近期不要一次性大迁移，先小步：

- 保留 `core/chain_processors.py` 作为兼容 facade。
- 新增 `core/chain/definitions.py` 和 `core/chain/registry.py`。
- 先把 definition 相关代码迁进去。
- 第二步再把实现函数按类别迁移。

验收标准：

- 外部仍可 `from core.chain_processors import execute_chain_processor`。
- 新目录下有清晰分类。
- 每类电池测试可以按文件拆分。

### 5.5 第 5 优先级：电池质量审计

先别急着新增大量电池，应该先把已有电池摸清。

近期为每个电池建立状态表：

| 字段 | 说明 |
| --- | --- |
| id | 电池唯一 id |
| 标题 | UI 显示名 |
| 分类 | 输入、文本、逻辑、列表、文件等 |
| 当前状态 | 可用、待修、实验、危险 |
| 输入端口 | id/kind/required |
| 输出端口 | id/kind |
| 是否写文件 | 是/否 |
| 是否发网络请求 | 是/否 |
| 是否执行代码 | 是/否 |
| 测试覆盖 | 单测、契约测试、UI 测试 |
| 示例链 | 是否有 |

近期落地任务：

- 新建 `docs/action_chain_processors_audit.md` 或生成脚本输出。
- 为每个现有电池跑一次定义检查。
- 对 HTTP、图像、文件写入、脚本电池标记为 caution/dangerous。
- 对实现和端口类型不一致的电池先修。

验收标准：

- 每个电池都有状态。
- 不合格电池不在 UI 默认展示，或标记“实验”。

### 5.6 第 6 优先级：提升属性面板

当前属性面板只是按端口生成输入框。近期应该让它根据 schema 生成控件。

近期控件规则：

- text：单行输入。
- textarea：多行输入。
- number：数字输入。
- bool：复选框。
- choice：下拉框。
- file/folder：路径输入 + 选择按钮。
- json：多行编辑 + 格式化按钮。
- list：多行编辑，每行一项。
- password/sensitive：不记忆、不显示明文。

近期落地任务：

- 在 `NodePropertyPanel.load_node()` 读取 processor definition。
- 对常用参数使用专业控件。
- 连接占用端口时仍显示来源，并允许断开。
- 未连接且有默认值时显示默认值。
- 必填为空时显示轻提示。

验收标准：

- `sleep_node.ms` 用数字输入。
- `bool_value.value` 用复选框或选择。
- `file_read_text.path` 可以选择文件。
- `http_get.headers` 可以多行输入。

### 5.7 第 7 优先级：调试运行体验

近期最有价值的用户体验提升是“看得见数据”。

近期功能：

- 测试运行时节点变成 running。
- 运行完成后节点显示 ok/failed/skipped/warning。
- 点击节点右侧显示输入、输出、错误、耗时。
- 点击端口显示端口最后值。
- 点击连线显示这条连接传递的值。
- 支持“清除运行结果”。

近期落地任务：

- `ChainCanvasWidget` 增加 `set_run_snapshots()`。
- `ConnectionItem` 支持 hover/click tooltip。
- `NodePropertyPanel` 增加运行快照区域。
- `ChainDialog._on_test_result()` 保存 `self._last_run_snapshots`。
- 新增 UI 测试覆盖状态映射和面板展示。

验收标准：

- 用户不需要打开日志就能知道哪个节点错、错在哪里。
- 上游输出和下游输入能对得上。

### 5.8 第 8 优先级：基础画布生产力

近期优先做低成本高收益交互：

- 搜索添加电池。
- 复制/粘贴节点。
- 复制/粘贴选中子图。
- 撤销/重做。
- 自动整理布局。
- 节点右键菜单：测试此节点、从此处运行、禁用、复制、删除、查看文档。
- 连接右键菜单：断开、查看值。

建议先实现：

1. 搜索添加电池。
2. 撤销/重做。
3. 复制/粘贴。
4. 自动排版。

验收标准：

- 用户能用键盘快速添加电池，不必在顶部按钮中找。
- 误删节点能撤销。
- 常用小片段能复制复用。

## 6. 电池库扩展规划

电池库应该按“常用、稳定、可组合”的原则扩展。不要只追求数量。

### 6.1 基础输入与调试

已有：

- 看板
- 文本输入
- 数字输入
- 布尔值
- 脚本电池
- 日志输出
- 等待

近期补强：

- 剪贴板输入
- 选中文本输入
- 当前时间
- 当前日期格式化
- 环境变量读取
- 常量字典/JSON 输入
- 调试断点
- 输出到剪贴板

成熟目标：

- 运行参数输入电池：动作链运行时弹出表单。
- 表单电池：把多个参数组合成一次用户输入。
- 监视器电池：显示任意端口实时值。

### 6.2 文本电池

已有：

- 文本模板
- 文本替换
- 文本裁剪
- 正则提取
- 大小写转换
- 文本合并
- 文本长度
- 文本拆分
- 文本分行

近期补强：

- trim 去空白
- 正则替换
- 多匹配提取
- 文本包含/开头/结尾
- 编码转换
- Base64 编解码
- URL query 解析/构建
- Markdown 转纯文本

成熟目标：

- 模板引擎增强，支持 `{变量}`、默认值、列表循环。
- 文本 diff。
- 文本表格解析。

### 6.3 逻辑与控制流

已有：

- 检查非空
- 空值兜底
- 类型转换
- 条件分支
- 比较判断
- 条件选择
- 布尔逻辑

近期补强：

- switch/case
- 错误转成功
- 成功/失败分流
- assert file exists
- assert json valid
- assert regex match

成熟目标：

- 真正的条件分支节点。
- 错误输出端口。
- try/catch/finally 子图。
- 节点级重试。

### 6.4 列表与数学

已有：

- 等差数列
- 等比数列
- 列表创建
- 获取元素
- 列表长度
- 反转
- 去重
- 排序
- 筛选
- 包含
- 列表套模板
- 基础数学
- 进制转换

近期补强：

- 列表合并
- 列表切片
- 列表 zip
- 列表 flatten
- 列表 join 为文本
- CSV/TSV 行列处理
- 数字格式化
- 随机数

成熟目标：

- map/filter/reduce 子图。
- 批处理文件列表。
- 表格数据电池。

### 6.5 JSON 与网络

已有：

- JSON 取字段
- JSON 设置字段
- JSON 校验格式化
- HTTP GET
- HTTP POST
- URL 编解码
- 文件下载

近期补强：

- HTTP headers builder
- Query params builder
- JSON path 支持数组索引
- JSON to text template
- HTTP 状态码输出
- 请求超时参数
- 响应 JSON 自动解析
- 网络请求安全确认和域名预览

成熟目标：

- API 调用电池模板。
- OAuth/API Key 安全参数。
- OpenAPI 导入生成电池。

### 6.6 文件与路径

已有：

- 文件路径
- 文件夹路径
- 路径拼接
- 拆分路径
- 路径存在
- 创建文件夹
- 读取文本文件
- 写入文本文件

近期补强：

- 文件列表
- 文件复制
- 文件移动
- 文件重命名
- 文件删除到回收站
- 文件哈希
- 文件大小/修改时间
- 路径规范化
- 选择文件/选择文件夹运行时输入

成熟目标：

- 批量文件管线。
- 文件监听触发。
- 安全删除/覆盖策略。

### 6.7 图像

已有：

- 缩放
- 转换格式
- 添加水印
- 裁剪
- 旋转

近期补强：

- 图片信息
- 批量缩放
- 生成缩略图
- 图片压缩
- EXIF 读取/移除
- 图片转 base64

成熟目标：

- 图像批处理模板。
- 视觉预览。
- 多图列表输入输出。

### 6.8 Windows 与 QuickLauncher 专属电池

近期新增方向：

- 获取当前活动窗口标题。
- 获取当前活动窗口进程。
- 窗口置顶/取消置顶。
- 激活窗口。
- 发送热键。
- 打开 QuickLauncher 配置文件/数据目录。
- 执行已有快捷方式。
- 搜索快捷方式。

成熟目标：

- 把 QuickLauncher 自身能力变成可组合电池。
- 动作链不仅能调用快捷方式，也能编排 QuickLauncher 的内部服务。

### 6.9 插件与 AI/API 电池

近期只做预留，不急着大规模实现：

- 插件注册电池接口。
- API 请求电池安全参数。
- AI 文本处理电池接口。

成熟目标：

- 插件可以提供整组电池。
- 用户可以把 API 文档/OpenAPI spec 转成可用电池。
- AI 电池支持摘要、改写、分类、提取字段等。

## 7. 图模型升级计划

### 7.1 当前过渡状态

现在的数据关系是：

```text
chain_canvas -> compile_canvas_to_steps() -> chain_steps -> execute_shortcut_chain()
```

这适合近期稳定，但长期应升级为：

```text
chain_graph -> validate graph -> schedule graph -> execute nodes -> snapshots
```

### 7.2 新图模型建议

```python
@dataclass
class ChainGraph:
    version: int
    nodes: list[ChainNode]
    connections: list[ChainConnection]
    metadata: dict[str, Any]

@dataclass
class ChainNode:
    id: str
    kind: str  # processor, shortcut, subchain, trigger, group
    ref: str
    title: str
    args: dict[str, Any]
    position: tuple[float, float]
    enabled: bool
    policy: ChainNodePolicy

@dataclass
class ChainConnection:
    id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str
    transform: str = ""
```

### 7.3 迁移步骤

近期：

- 保持 `chain_canvas` 版本 1。
- 新增 `ChainGraph` 内部结构，但先由 `chain_canvas` 转换得到。
- 执行器仍可接收 `chain_steps`。

中期：

- `execute_shortcut_chain()` 内部先把步骤转图，再用图运行时执行。
- 保存仍保留 `chain_steps` 兼容字段，但主数据使用 `chain_canvas` 或 `chain_graph`。

长期：

- `chain_steps` 仅作为旧版本兼容字段。
- 新动作链直接保存图模型。

## 8. 运行时升级计划

### 8.1 近期运行时

近期保持线性执行，但补齐上下文：

```python
class ChainRunContext:
    chain_id: str
    run_id: str
    values: dict[str, str]
    typed_values: dict[str, ChainValue]
    snapshots: dict[str, ChainNodeRunSnapshot]
    cancel_event: Any
```

每个节点执行流程：

1. 校验节点是否启用。
2. 根据连接/绑定解析输入。
3. 记录输入快照。
4. 执行节点。
5. 归一化输出 artifact。
6. 写入 values/typed_values。
7. 记录输出快照。
8. 根据错误策略决定继续或停止。

### 8.2 中期图运行时

支持：

- 拓扑排序。
- 多输入等待。
- 节点 dirty 状态。
- 增量运行。
- 缓存纯函数电池输出。
- 分支节点只激活部分路径。

### 8.3 长期运行时

支持：

- 并行执行无依赖节点。
- 节点级超时。
- 节点级重试。
- 子链调用栈。
- 运行历史回放。
- 运行诊断包导出。

## 9. UI 规划

### 9.1 近期 UI

近期重点是可调试和可配置：

- 节点属性按 schema 显示控件。
- 节点运行快照展示。
- 端口值 tooltip。
- 连接值 tooltip。
- 搜索添加电池。
- 清除运行结果。
- 节点文档入口。

### 9.2 中期 UI

中期重点是编辑效率：

- 撤销/重做。
- 复制/粘贴。
- 自动排版。
- 小地图。
- 缩放控制。
- 节点分组。
- 注释框。
- 模板库。
- 收藏电池。

### 9.3 长期 UI

长期重点是专业化：

- 可视化调试器。
- 运行时间轴。
- 断点。
- 单步执行。
- 端口数据检查器。
- 子链展开/折叠。
- 电池搜索命令面板。
- 文档和示例内嵌。

## 10. 安全规划

动作链会越来越强，安全必须早做。

### 10.1 风险等级

建议每个电池和快捷方式节点都能归类：

- safe：纯文本、纯数学、纯列表、不会访问外部系统。
- caution：读文件、访问网络、读取系统信息。
- dangerous：写文件、删除/移动文件、执行命令、执行脚本、管理员权限。

### 10.2 近期安全任务

- 为 processor definition 增加 safety。
- 风险分析读取 safety。
- HTTP、文件写入、脚本电池显示风险。
- 测试运行 dangerous 节点前需要明确确认，或提供“跳过危险节点测试”选项。
- 敏感参数不写入运行快照明文。

### 10.3 中长期安全任务

- 动作链保存时生成风险摘要。
- 首次运行高风险动作链时确认。
- 文件覆盖/删除类电池默认要求确认。
- 插件电池必须声明权限。
- 导入动作链时显示风险清单。

## 11. 测试规划

### 11.1 近期测试

必须新增：

- 电池定义完整性测试。
- 每个电池的输入输出契约测试。
- 运行快照测试。
- 端口值映射测试。
- UI 属性面板 schema 控件测试。
- 风险分析 safety 测试。

建议结构：

```text
tests/
  test_chain_processor_definitions.py
  test_chain_runtime_snapshots.py
  test_chain_value_types.py
  test_chain_safety.py
  test_chain_property_panel.py
```

### 11.2 电池测试矩阵

每个电池至少要有：

- 正常输入。
- 空输入。
- 非法输入。
- 多输入连接。
- 输出字段检查。
- 错误消息检查。
- 类型检查。

文件/网络/脚本类电池额外需要：

- 安全标记检查。
- 超时或限制检查。
- 不可用环境下的失败语义。

### 11.3 回归测试

关键旧行为不能破坏：

- 旧 `chain_steps` 可以加载。
- `chain_canvas` 可以 round-trip。
- 旧动作链不带新字段也能执行。
- 快捷方式节点仍可执行。
- 命令捕获输出仍可传递。
- `use_previous_output` 仍兼容。

## 12. 文档规划

近期文档：

- 动作链用户入门。
- 电池分类说明。
- 端口类型说明。
- 调试运行说明。
- 脚本电池说明。
- 风险说明。

中期文档：

- 电池开发规范。
- 插件注册电池规范。
- 动作链模板制作规范。
- 示例库。

建议根文档结构：

```text
docs/action_chain/
  overview.md
  user_guide.md
  processor_reference.md
  script_cell.md
  safety.md
  developer_guide.md
  examples/
```

## 13. 详细近期排期

### 第 1 周：现状清点与定义 schema

任务：

- 建立电池审计表。
- 扩展 `ChainProcessorDefinition`。
- 为现有电池补齐 category/description/safety。
- 新增 definition 完整性测试。
- 明确每个电池状态：稳定、待修、实验。

产出：

- 完整电池定义。
- 电池审计文档。
- 定义测试。

### 第 2 周：运行快照 MVP

任务：

- 增加节点运行 snapshot。
- 执行器记录输入和输出。
- 测试运行结果 payload 增加 `node_snapshots`。
- UI 节点状态按 node id 映射。
- 属性面板显示上次运行摘要。

产出：

- 用户能看到每个节点输入/输出。
- 运行错位问题降低。

### 第 3 周：值类型过渡层

任务：

- 新增 `ChainValue`。
- artifact 转 typed values。
- list/json/file/folder/url/number/bool 标准化。
- 更新端口兼容测试。
- UI 预览按类型显示。

产出：

- 复杂值不再完全依赖字符串。
- 列表和 JSON 传递更稳定。

### 第 4 周：属性面板 schema 控件

任务：

- 根据 definition params/inputs 生成控件。
- 数字、布尔、choice、file/folder、json/list 控件落地。
- 必填校验。
- 默认值显示。
- 控件测试。

产出：

- 用户配置电池更自然。
- 参数错误减少。

### 第 5 周：调试交互

任务：

- 节点运行中状态。
- 端口 tooltip。
- 连线 tooltip。
- 清除运行结果。
- 节点右键菜单加入测试/禁用/删除/文档。

产出：

- 基础可视化调试体验成型。

### 第 6 周：电池质量修复

任务：

- 修复审计中标记为待修的电池。
- 为高价值电池补足测试。
- HTTP 增加 timeout/status_code 输出。
- 文件写入增加覆盖策略。
- JSON path 增强数组索引。

产出：

- 第一批稳定电池库。

### 第 7 周：编辑效率 MVP

任务：

- 搜索添加电池。
- 撤销/重做基础栈。
- 复制/粘贴节点。
- 自动排版基础版。

产出：

- 搭建动作链速度明显提升。

### 第 8 周：近期版本收口

任务：

- 补齐用户文档。
- 补齐开发规范。
- 跑全量测试。
- 修 UI 细节。
- 做 3-5 个官方示例动作链。

产出：

- 可以作为“动作链 beta”稳定入口。

## 14. 目前最应该立刻做的 10 件事

1. 建立动作链模块 manifest，明确动作链自己的模块 id、版本号、兼容主程序版本、入口和依赖。
2. 收缩主程序与动作链之间的接口，先定义 `ActionChainHostAPI` 和 `ActionChainModuleAPI`。
3. 扩展 `ChainProcessorDefinition`，建立电池 schema。
4. 新增电池定义完整性测试，防止继续无规则增长。
5. 为现有电池做审计表，标记稳定/实验/危险。
6. 在执行器中加入节点运行快照。
7. UI 属性面板显示节点上次运行输入/输出。
8. 将运行状态按 node id 映射，而不是只按顺序。
9. 为文件、HTTP、脚本电池加入安全等级和风险提示。
10. 写 3 个示例动作链：文本处理、文件批处理、HTTP+JSON。

## 15. 建议优先修正的设计点

### 15.1 不要继续让 `core/chain_processors.py` 无限膨胀

这个文件当前承担太多职责。近期先把 definition/registry 拆出去，后续再迁实现。

### 15.2 不要只做更多按钮

Grasshopper 的价值不只是很多电池，而是：

- 电池行为明确。
- 端口语义明确。
- 数据流看得见。
- 调试反馈强。
- 组合之后仍然可理解。

所以近期最重要的是契约、调试、测试，而不是盲目堆电池。

### 15.3 `chain_canvas` 应逐步成为主模型

现在保存时仍编译到 `chain_steps`。短期兼容可以保留，但中长期要让图模型成为执行入口。

### 15.4 脚本电池要明确定位

脚本电池很强，但也危险。建议定位为“高级本地用户能力”，需要：

- 明确风险提示。
- 超时控制。
- 示例模板。
- 不把它伪装成安全沙箱。

### 15.5 电池输出必须稳定

每个电池要明确：

- 成功时输出哪些端口。
- 失败时输出哪些端口。
- 空输入时行为。
- 类型转换失败时行为。
- 是否保留原始值。

## 16. 成熟后的示例场景

### 16.1 文本处理链

```text
选中文本输入 -> trim -> 正则提取 -> 文本模板 -> 复制到剪贴板 -> Toast 提示
```

### 16.2 文件批处理链

```text
选择文件夹 -> 文件列表 -> 筛选 .png -> 批量缩放 -> 保存到输出目录 -> 打开文件夹
```

### 16.3 API 查询链

```text
文本输入关键词 -> URL 编码 -> HTTP GET -> JSON 取字段 -> 文本模板 -> 显示结果
```

### 16.4 开发辅助链

```text
选择项目目录 -> Git 状态 -> 条件判断 -> 运行测试 -> 生成摘要 -> 打开日志
```

### 16.5 QuickLauncher 自身编排

```text
搜索快捷方式 -> 取第一个结果 -> 执行快捷方式 -> 捕获结果 -> 根据结果打开对应工具
```

## 17. 里程碑验收

### 17.1 beta 里程碑

条件：

- 电池 schema 完整。
- 运行快照可见。
- 第一批稳定电池测试充足。
- 风险提示可用。
- 搜索添加电池可用。
- 有 3 个示例动作链。

### 17.2 1.0 里程碑

条件：

- 图模型运行时可用。
- 子链电池可用。
- 局部运行可用。
- 撤销/重做、复制粘贴、自动排版可用。
- 插件电池注册接口可用。
- 文档完整。

### 17.3 成熟里程碑

条件：

- 可视化调试器成熟。
- 电池生态可扩展。
- 模板库成型。
- 安全策略完整。
- 复杂图运行稳定。

## 18. 推荐下一步执行方案

建议下一轮开发不要直接改 UI 外观，而是按下面顺序做一个“小而硬”的版本：

1. `core/chain_processors.py`：扩展 `ChainProcessorDefinition`。
2. `core/chain_contracts.py`：端口类型读取 definition，不再大量硬编码推断。
3. `tests/test_chain_processor_definitions.py`：建立定义质量门槛。
4. `core/shortcut_chain_exec.py`：增加 `node_snapshots`。
5. `ui/config_window/chain_canvas.py`：按 node id 接收运行快照。
6. `ui/config_window/chain_canvas.py`：属性面板显示输入/输出快照。
7. `ui/config_window/chain_dialog.py`：风险分析读取 safety。

这一轮完成后，动作链会从“能连起来跑”升级为“能知道自己为什么这么跑、哪里错、值是什么”。这是走向 Grasshopper 式模块化编程最关键的一步。

## 19. 独立模块与可断开规划

补充目标：动作链未来可能成为付费模块、独立插件模块，或独立更新模块。因此从近期开始就应该避免动作链和主程序深度缠绕。主程序只提供有限能力，动作链模块通过稳定接口调用这些能力。这样后期想独立发布、单独升级、授权开关、甚至从主程序中移除，都不会造成大面积返工。

### 19.1 核心原则

- 动作链拥有自己的模块身份，而不是只作为 `ShortcutType.CHAIN` 的附属功能。
- 动作链拥有自己的版本号、兼容范围、数据 schema 版本和迁移逻辑。
- 主程序不直接了解动作链内部图模型、电池实现和运行细节。
- 动作链不直接读写主程序内部对象，必须通过 Host API 获取快捷方式、执行快捷方式、读取设置、弹窗、日志、文件选择等能力。
- 主程序可以在动作链模块缺失、未授权、版本不兼容、被禁用时正常运行。
- 动作链数据和主程序快捷方式数据要有清晰边界，允许导入导出和独立备份。

### 19.2 模块身份与版本号

建议动作链模块拥有独立 manifest。

建议文件：

```text
modules/action_chain/module.json
```

建议内容：

```json
{
  "id": "quicklauncher.action_chain",
  "name": "Action Chain",
  "display_name": "动作链",
  "module_version": "0.1.0",
  "schema_version": 1,
  "api_version": "1.0",
  "min_host_version": "1.6.3.0",
  "max_host_version": "",
  "entry": "quicklauncher_action_chain.entry:ActionChainModule",
  "license_mode": "builtin",
  "capabilities": [
    "chain.editor",
    "chain.runtime",
    "chain.processors",
    "shortcut.chain_type"
  ]
}
```

版本建议：

- `module_version`：动作链模块自己的发布版本，例如 `0.1.0`、`0.2.0`、`1.0.0`。
- `schema_version`：动作链图数据、节点数据、电池定义的数据版本。
- `api_version`：动作链模块和主程序之间的接口版本。
- `min_host_version`：最低兼容 QuickLauncher 版本。
- `max_host_version`：通常为空，只有重大不兼容时填写。

版本规则建议：

- patch：修 bug，不改变数据 schema 和 Host API。
- minor：新增电池、新增 UI、新增可选字段，保持兼容。
- major：Host API 或数据 schema 有破坏性变化。

### 19.3 主程序接口收缩

当前动作链直接依赖主程序多个内部模块：

- `ShortcutItem`
- `ShortcutType`
- `ShortcutExecutor`
- `data_manager`
- `CommandResult`
- `CommandOutputArtifact`
- 配置窗口和弹窗 UI

这在内置阶段可以工作，但不利于后期独立化。建议把依赖收缩成两个方向。

主程序提供给动作链的 Host API：

```python
class ActionChainHostAPI:
    host_version: str
    api_version: str

    def list_shortcuts(self) -> list[dict]: ...
    def get_shortcut(self, shortcut_id: str) -> dict | None: ...
    def execute_shortcut(self, shortcut_id: str, invocation: dict, cancel_event=None) -> dict: ...

    def get_settings(self) -> dict: ...
    def get_theme(self) -> str: ...
    def show_toast(self, message: str, level: str = "info") -> None: ...
    def choose_file(self, options: dict) -> str: ...
    def choose_folder(self, options: dict) -> str: ...
    def log_event(self, event: dict) -> None: ...

    def check_permission(self, capability: str) -> bool: ...
    def request_confirmation(self, request: dict) -> bool: ...
```

动作链提供给主程序的 Module API：

```python
class ActionChainModuleAPI:
    module_version: str
    schema_version: int
    api_version: str

    def is_available(self) -> bool: ...
    def open_editor(self, parent, chain_data: dict | None = None) -> dict | None: ...
    def execute_chain(self, chain_data: dict, context: dict, cancel_event=None) -> dict: ...
    def validate_chain(self, chain_data: dict) -> list[dict]: ...
    def migrate_chain_data(self, chain_data: dict, from_schema: int) -> dict: ...
    def list_processors(self) -> list[dict]: ...
```

近期落地策略：

- 不必一步拆成真正独立包，先在代码里建立接口层。
- 新增 `core/action_chain_host.py` 或 `core/modules/action_chain_host.py`，封装主程序能力。
- 动作链执行器不再直接拿 `data_manager` 深挖 folders，而是通过 host API 获取快捷方式映射。
- 动作链 UI 不直接依赖主窗口内部结构，而是通过 host API 获取主题、快捷方式列表、文件选择、toast。

### 19.4 建议目录边界

近期可以先把动作链代码归拢，不必立即物理迁移全部文件。

目标目录：

```text
modules/action_chain/
  module.json
  __init__.py
  entry.py
  api.py
  host_contracts.py
  models.py
  graph.py
  runtime.py
  values.py
  contracts.py
  registry.py
  processors/
  ui/
  migrations/
  tests/
```

过渡期兼容 facade：

```text
core/shortcut_chain_exec.py       -> 调用 modules/action_chain/runtime.py
core/chain_processors.py          -> 调用 modules/action_chain/registry.py
core/chain_contracts.py           -> 调用 modules/action_chain/contracts.py
ui/config_window/chain_dialog.py  -> 调用 modules/action_chain/ui/dialog.py
ui/config_window/chain_canvas.py  -> 调用 modules/action_chain/ui/canvas.py
```

这样旧代码路径暂时不坏，新架构也能慢慢成型。

### 19.5 数据边界

当前动作链数据跟 `ShortcutItem` 混在一起：

```python
ShortcutItem(type=ShortcutType.CHAIN, chain_steps=[...], chain_canvas={...})
```

这对内置动作链方便，但如果要作为独立模块，建议逐步抽象为：

```json
{
  "type": "chain",
  "module_id": "quicklauncher.action_chain",
  "module_version": "0.1.0",
  "schema_version": 1,
  "chain_id": "chain-uuid",
  "title": "动作链名称",
  "graph": {},
  "metadata": {},
  "host_bindings": {}
}
```

主程序中的快捷方式项只保存最小引用：

```json
{
  "id": "shortcut-id",
  "type": "chain",
  "name": "动作链名称",
  "module_id": "quicklauncher.action_chain",
  "chain_ref": "chain-uuid"
}
```

近期不建议立刻拆数据文件，但应该预留字段：

- `module_id`
- `module_version`
- `chain_schema_version`
- `chain_ref`
- `chain_data`

中期可以把动作链数据独立保存：

```text
config/action_chains/
  chain-uuid.json
  chain-uuid.history/
```

这样动作链模块禁用或卸载时，主程序只看到“该快捷方式引用的模块不可用”，不会因为无法解析内部图数据而崩。

### 19.6 可断开与降级策略

当动作链模块不存在、未启用、未授权或版本不兼容时，主程序应该这样表现：

- 启动不失败。
- 配置窗口仍可打开。
- 普通快捷方式不受影响。
- 动作链快捷方式显示为“动作链模块不可用”。
- 执行动作链时返回清晰错误，而不是异常。
- 可以保留、导出、删除动作链快捷方式。
- 不尝试解析动作链内部 graph。

建议状态：

```text
available       模块可用
disabled        用户禁用
unlicensed      未授权或付费未开通
missing         模块文件缺失
incompatible    Host API 或模块版本不兼容
broken          模块加载失败
```

主程序处理方式：

```python
if shortcut.type == CHAIN:
    module = module_registry.get("quicklauncher.action_chain")
    if not module or not module.is_available():
        return CommandResult(False, "动作链模块不可用", error="Action chain module unavailable")
    return module.execute_chain(...)
```

### 19.7 付费和授权预留

如果动作链后期作为付费模块，需要提前把授权检查放在模块边界，而不是散落在 UI 和执行器里。

建议授权能力点：

- `chain.editor`：是否允许打开编辑器。
- `chain.runtime`：是否允许执行动作链。
- `chain.advanced_processors`：是否允许使用高级电池。
- `chain.script_cell`：是否允许脚本电池。
- `chain.templates`：是否允许模板库。
- `chain.export_import`：是否允许导入导出。

授权策略建议：

- 免费版可以执行基础动作链和基础电池。
- 付费版开放高级电池、子链、模板、插件电池、批处理、脚本电池等。
- 未授权时不破坏已有数据，只限制编辑/执行/高级节点。
- 动作链运行前做一次能力检查，节点执行前再做节点级能力检查。

近期不要实现复杂付费系统，但要预留：

```python
host.check_permission("chain.runtime")
host.check_permission("chain.processor.http_get")
host.check_permission("chain.script_cell")
```

### 19.8 独立更新规划

动作链模块独立更新需要满足：

- 模块有独立版本号。
- 模块能声明兼容的 Host API。
- 模块有迁移脚本。
- 模块更新失败不影响主程序。
- 模块可以回滚。

建议模块更新流程：

1. 主程序发现动作链模块有新版本。
2. 检查 `min_host_version` 和 `api_version`。
3. 下载到临时目录。
4. 校验 manifest、签名、hash。
5. 备份旧模块。
6. 替换模块。
7. 加载模块并运行自检。
8. 如失败，回滚旧模块。

建议模块自检：

- manifest 可读。
- API 可实例化。
- processor registry 可加载。
- schema migrations 可加载。
- 基础动作链测试可执行。

### 19.9 模块迁移规划

数据迁移必须由动作链模块自己负责。

建议迁移目录：

```text
modules/action_chain/migrations/
  v1_to_v2.py
  v2_to_v3.py
```

迁移入口：

```python
def migrate_chain_data(chain_data: dict, from_schema: int, to_schema: int) -> dict:
    ...
```

迁移原则：

- 主程序不理解动作链 graph 内部结构。
- 主程序只负责调用模块迁移。
- 迁移前备份原始数据。
- 迁移失败时保留旧数据，并把动作链标记为需要旧模块或手动修复。

### 19.10 插件化路径

如果动作链未来作为独立插件模块，推荐分三步：

第 1 步：内置模块化。

- 代码仍在主仓库。
- 通过接口层调用。
- 有 manifest、版本、schema。

第 2 步：半独立模块。

- 代码迁到 `modules/action_chain`。
- 主程序通过 module registry 加载。
- 仍随主程序发布。

第 3 步：独立插件。

- 动作链作为插件包安装。
- 有独立更新通道。
- 可禁用、卸载、回滚。
- 主程序只保留 Host API 和模块入口。

### 19.11 与快捷方式系统的关系

动作链仍可以在主程序里表现为一种快捷方式类型，但内部不要被快捷方式系统绑死。

推荐关系：

```text
主程序快捷方式
  - 负责展示、搜索、触发、图标、使用统计

动作链模块
  - 负责编辑、保存内部图、执行、调试、电池库、迁移

连接方式
  - 快捷方式保存 chain_ref
  - 执行时主程序把 chain_ref 交给动作链模块
```

这样动作链既能融入 QuickLauncher 搜索/启动体验，又可以保持模块独立。

### 19.12 近期必须补进开发计划的任务

新增近期任务：

1. 新增动作链模块 manifest 草案。
2. 新增 Host API 和 Module API 草案。
3. 让动作链执行入口通过模块 API 调用。
4. 让主程序在动作链模块不可用时有降级结果。
5. 给 `ShortcutItem` 预留 `module_id`、`module_version`、`chain_schema_version`、`chain_ref` 或等价字段。
6. 给动作链数据增加 `schema_version` 和迁移入口。
7. 把付费/授权能力点放到模块边界。

这些任务应该排在“继续丰富电池库”之前。

## 20. 修订后的最近 4 周优先级

因为动作链可能成为独立模块，近期优先级需要调整。

### 第 1 周：模块边界先行（已部分完成）

任务：

- 写 `module.json` 草案。
- 定义 `ActionChainHostAPI`。
- 定义 `ActionChainModuleAPI`。
- 新增模块可用性状态：available/disabled/unlicensed/missing/incompatible/broken。
- 主程序执行 CHAIN 时先走模块可用性检查。

验收：

- 动作链模块被模拟禁用时，主程序仍正常启动和执行其他快捷方式。
- 执行动作链返回清晰“模块不可用”错误。

当前状态：

- 已新增 `modules/action_chain/entry.py`，提供模块 manifest/API、权限声明、可用性检查和不可用降级结果。
- 仍需补独立模块目录布局、迁移目录和真实 Host API 边界。

### 第 2 周：数据版本和迁移入口

任务：

- 动作链数据增加 `module_id`、`module_version`、`schema_version`。
- 新增迁移函数入口。
- 保存和加载时保留未知字段，避免未来版本数据被旧版本破坏。
- 写旧数据兼容测试。

验收：

- 旧动作链数据能加载。
- 新动作链数据能 round-trip。
- 未知字段不会被静默删除。

### 第 3 周：电池 schema 和安全能力点（已大部分完成）

任务：

- 扩展 processor definition。
- 增加 safety 和 capability。
- 风险分析读取 safety。
- 授权检查先做空实现，默认全部允许。

验收：

- 文件写入、HTTP、脚本电池能显示风险。
- 禁用某个 capability 时，对应电池不可执行或有明确提示。

当前状态：

- 内置电池已经有端口 kind/role、参数控件、说明、示例、安全级别和 capability。
- 外部电池注册已经增加 schema 质量门槛：未知端口类型、未知 role、重复端口、参数不属于输入端口、非法安全级别和非法 capability 都会被拒绝。
- 风险显示已有基础接入；capability 禁用后的执行阻断仍需继续补全。

### 第 4 周：运行快照和调试（已部分完成）

任务：

- 增加节点运行 snapshot。
- UI 按 node id 显示运行结果。
- 属性面板显示上次输入输出。
- 建立快照测试。

验收：

- 独立模块边界没有阻碍调试体验。
- 后续无论内置还是插件化，运行结果格式都稳定。

当前状态：

- 运行结果已经记录节点快照、typed 输入/输出、耗时和错误。
- 画布端口和连线 tooltip 已显示数据类型、端口角色、说明和上次运行值。
- 仍需补单节点运行、局部运行、端口数据检查器和诊断包导出。
