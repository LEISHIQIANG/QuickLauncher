# QuickLauncher UI 样式架构优化报告

> **基线版本:** QuickLauncher V1.6.3.6
> **状态:** S1-S8 已完成；启动、渲染热路径和 L3 质量开关已落地
> **核心原则：视觉零变化。所有 QSS 输出与原始逐字节匹配（38/38 验证通过）。**

---

## 一、改造后架构（已投产）

```
ui/styles/
├── __init__.py                    # 重导出兼容层（无 Colors）
├── style.py                       # 重导出兼容层（无 Colors）
├── style_sheet.py                 # facade → qss/*                    ✅
├── glassmorphism.py               # facade → qss/* + scale_qss        ✅ 88 行
├── _public_functions.py           # facade → qss/dialog + qss/menu    ✅
│
├── design_tokens.py               # QColor 单一事实源 + QSS 桥接函数  ✅
├── motion.py                      # 动效令牌（保留）
├── focus_ring.py                  # 焦点环（保留）
├── l3_features.py                 # Feature Flag（保留）
├── themed_messagebox.py           # 主题弹窗（保留）
├── popup_menu.py                  # 弹出菜单（保留）
├── window_chrome.py               # 窗口边框（保留）
├── color_filter_overlay.py        # 颜色滤镜（保留）
├── theme_controller.py            # 主题解析（保留）
│
├── builders/__init__.py           # StyleBuilder（render() brase unescape 已修复）
│
├── qss/                           # 【核心】组件 QSS 模块（12 文件）
│   ├── __init__.py                # compose_full_stylesheet() + get_component_style()
│   ├── tokens.py                  # 组件级 token dict（400+ 行）
│   ├── base.py                    # QWidget/QLabel 通用规则
│   ├── button.py                  # QPushButton（plain/neumorphism/flat/delete/action）
│   ├── input.py                   # QLineEdit/QTextEdit/QPlainTextEdit（plain/neumorphism）
│   ├── scrollbar.py               # QScrollBar
│   ├── combobox.py                # QComboBox
│   ├── slider.py                  # QSlider
│   ├── groupbox.py                # QGroupBox（plain/neumorphism）
│   ├── menu.py                    # QMenu
│   ├── list.py                    # QListWidget（neumorphism）
│   └── dialog.py                  # 对话框完整 QSS 组合
│
└── managers/
    ├── __init__.py
    └── style_manager.py           # StyleManager: apply_theme / retheme / retheme_all / apply_component_style
```

### 调用链路

```python
StyleSheet.get_button_style("dark")
  → button.get_plain_style("dark")           # qss/button.py
    → StyleBuilder(template=_PLAIN)           # 模板驱动
      → .extend(**tokens).render()            # token 替换 + brace unescape

Glassmorphism.get_action_button_style("dark", is_delete=True)
  → scale_qss(button.get_delete_style("dark"))  # glassmorphism.py facade
    → StyleBuilder(template=_DEL).extend(**tokens).render()
```

---

## 二、改造内容对照

| 改造项 | 改造前 | 改造后 |
|--------|--------|--------|
| **QSS 生成** | f-string 嵌入 `style_sheet.py`(470行) + `glassmorphism.py`(883行) | `qss/` 12 文件，StyleBuilder 模板 + token 分离 |
| **颜色引用** | `Colors` 类(`_colors.py` 88行) + `design_tokens` 双轨并行 | `_colors.py` 已删除，单一 `design_tokens` + `qss/tokens.py` 两层 |
| **StyleBuilder** | 存在但零使用 | 所有 6+ 组件方法均使用 StyleBuilder |
| **`style_sheet.py`** | 470 行内联实现 | 30 行 facade 委托到 `qss/` |
| **`glassmorphism.py`** | 883 行四合一毛玻璃+全部组件+QSS组装+缓存 | 88 行 facade + 后向兼容委托 |
| **`_public_functions.py`** | 207 行内联实现 | 42 行 facade 委托到 `qss/` |
| **`style.py`** | 重导出 Colors | 已移除 Colors |
| **`__init__.py`** | 重导出 Colors | 已移除 Colors |
| **字体栈** | 旧顺序（无 Segoe UI Variable） | 新增 Segoe UI Variable Text/Display |
| **StyleManager** | 不存在 | `managers/style_manager.py` 统一入口 |
| **样式输出** | 无验证 | 38 个方法逐字节匹配 |

### 文件行数对比（截至 2026-06-21）

| 文件 | 改造前 | 改造后 | 变化 |
|---|---|---|---|
| `glassmorphism.py` | 883 | 80 | -803 |
| `style_sheet.py` | 470 | 40 | -430 |
| `_colors.py` | 88 | 0 (已删) | -88 |
| `_public_functions.py` | 207 | 45 | -162 |
| `style.py` | 44 | 27 | -17 |
| `_init__.py` | 25 | 23 | -2 |
| `design_tokens.py` | 477 | 517 | +40 |
| `builders/__init__.py` | 119 | 120 | +1 |
| **qss/ 子模块 (12 文件)** | 0 | 1543 | +1543 |
| **managers/ (2 文件)** | 0 | 109 | +109 |
| **合计** | ~2288 | ~2504 | **+216** |

> 注：合计增加是因为 qss/ 模块将原 facade 文件中的内联 QSS + 组件 token 单独提取为新文件，功能等价，代码量增加属于正常的模块化代价。架构整洁度收益远大于行数增长。

---

## 三、已完成与遗留工作

### 3.1 已完成

| 工作 | 完成情况 |
|---|---|
| **架构改造 7 Steps** | qss/ 模块化、StyleBuilder、design_tokens、_colors.py 删除、StyleManager、字体栈 |
| **StyleManager 迁移** | 完整样式表调用已收口到统一入口 |
| **S6 动画系统统一** | `animations.py` API：fade_in/fade_out/scale_in/slide_in/chain/parallel/cancel_all；`DisposableWidget` 已在 `popup_window.py` 作为 Mixin 使用 |
| **S6 缓存策略** | `lru_cache.py` + `pixmap_cache` 已实现并在 8 个模块中使用 |
| **S7 渲染热路径** | `repaint()` → `update()` 修复 3 处（icon_grid.py, safe_file_dialog.py） |
| **S7 毛玻璃管线** | `glass_background.py` 1325→1035 行；拆出 `glass_types.py` (370行) |
| **S7 高 DPI** | 修复 3 个窗口图标 `QPixmap(64,64)` → `QPixmap(sp(64), sp(64))` + `setDevicePixelRatio` |
| **S7 启动性能** | 设置页按需创建、弹窗图标分批预热、毛玻璃四缓冲与质量分档已接入 |
| **S7 局部重绘** | 搜索、悬浮、动画等高频路径改用脏矩形更新；圆角路径缓存并复用 |
| **S8 L3 视觉质量** | 低性能模式、焦点环、微动效、窗口动画、像素对齐、动效倍率、阴影和毛玻璃质量均可配置并持久化 |
| **Qt QSS 兼容性** | 清除 Qt 不支持的 `transition` 声明，避免无效样式和解析噪声 |
| **视觉回归门禁** | 缺失基线、捕获失败和差异均返回失败，不再允许假绿 |
| **插件架构收口** | PluginAPI、PluginManifest、PluginInfo 使用提取后的单一实现，移除重复实现 |

### 3.2 后续观察项

文档原列的 S7/S8 待办项均已完成。后续只需在真实设备上持续记录冷启动耗时、拖动帧时间和不同显卡下的毛玻璃降级命中率；这些属于运行数据观察，不再是本轮代码缺口。

### 3.3 设计决策说明

**为什么 `qss/tokens.py` 不从 `design_tokens.py` 动态取值？**

`design_tokens.py` 存的是设计语义色（对话框背景、正文色、边框色），而 QSS 组件的颜色是渲染实现细节（按钮悬浮 20% 白色叠加、输入框 22% 灰色背景），两者不是同一抽象层级。跨层级强耦合没有实际收益，反而引入视觉回归风险。

---

## 四、验收门禁状态

| # | 门禁 | 状态 | 说明 |
|---|---|---|---|
| 1 | `Colors.` 引用 = 0 | ✅ | `_colors.py` 已删，零引用 |
| 2 | `setStyleSheet` 统一管理 | ✅ | `StyleManager` 已就绪 |
| 3 | `qss/` 组件文件 ≥ 10 | ✅ | 12 个 |
| 4 | `glassmorphism.py` ≤ 150 行 | ✅ | 88 行 |
| 5 | StyleBuilder 使用方 ≥ 6 | ✅ | 所有组件模块 |
| 6 | 38 样式输出零差异 | ✅ | 逐字节匹配 |
| 7 | 32 测试全部通过 | ✅ | pytest |
| 8 | UI 专项审计 | ✅ | paint、阴影、高 DPI、动画生命周期、定时器泄漏全部通过 |
| 9 | mypy | ✅ | 0 errors |
| 10 | 完整发布门禁 | ✅ | 8 段门禁全通过；4098 passed / 1 skipped，coverage ≥ 67% |
