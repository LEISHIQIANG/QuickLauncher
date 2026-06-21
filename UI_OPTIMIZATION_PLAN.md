# QuickLauncher UI 精致度提升、流畅度优化与代码架构优化总纲

> **基线版本:** QuickLauncher V1.6.3.6
> **目标版本:** 1.7.0
> **目标:**
> 1. **更精致**：用户看到的最终效果——更清晰的像素、更统一的节奏、更细腻的反馈、更顺滑的过渡、更专业的细节。
> 2. **更流畅**：每一次交互都如丝般顺滑——动画 60FPS、首屏 ≤ 16ms、滚动无掉帧、拖拽无延迟、切换无残影。
> 3. **更整洁**：代码层面清理历史债务——硬编码收敛、重复代码合并、抽象层建立、巨型文件拆分、规则统一执行。
> **原则:**
>    1. **视觉只许更好**：肉眼可见的最终效果必须比基线更精致；不允许出现更丑、更乱、更卡、更糊的情况。
>    2. **流畅只许更顺**：所有交互的响应延迟、动画帧率、首屏时间必须比基线更优或持平；性能回退零容忍。
>    3. **代码只为体验服务**：所有代码改造的最终衡量标准是「这个改动让用户感受到的体验更精致流畅了吗」；不能改善体验的纯重构不优先做。
>    4. **不做不必要的事**：不为统一而统一、不为重构而重构；只有"重复 ≥3 处"或"未来新增必然要走这条路径"才抽象。
>    5. **基线为锚**：18 张视觉基线 PNG 守护外观；性能基线（启动 / 首帧 / FPS / 内存）守护流畅。
>
> **审计基线（2026-06-20 实测：基于 `UI_OPTIMIZATION_PLAN.md` 配套 audit 脚本）：**
> | 维度 | 数量 | 涉及文件 |
> |---|---:|---:|
> | 硬编码 `QColor(...)`（非 whitelist 字面量） | 193 | 30 |
> | 内联 `font-size: N px` | 0 | 0 |
> | `sp(整数)` 非 4 倍数 | 0（审计脚本已修复 ⚠️） | 0（代码库已合规） |
> | `border: none` 缺 `border-radius: 0` | 118 | 28 |
> | `paintEvent` 未使用 `snap_rect`+`cosmetic` | 31 | 23 |
> | `QGraphicsDropShadowEffect` 实例化（走 token） | 2 | 2 |
> | `QGraphicsOpacityEffect` 实例化 | 1 | 1 |
> | `QGraphicsEffect` 未清理/反模式（paintEvent perf） | 5 | 5 |
> | `QPropertyAnimation` 缺配对 `stop`/`deleteLater` | 5 | 5 |
> | `QPixmap` 缺 `setDevicePixelRatio` | 5 | 5 |
> | `QTimer.singleShot` 替代动画 | 0 | 0 |
>
> **Sprint 容量修正：** S2-S4 实际工作量约为初稿估算的 **3-6 倍**，原 §六.1 时间表需在 S0 基线采集完成后重排。

---

## 一、用户视角的精致度 + 流畅度定义

精致度 + 流畅度 = 用户使用产品时**能感知到但说不清**的"专业感"。具体拆解为以下八个维度，每个维度都对应可落地的代码改造。

### 1.1 像素级干净（消除发虚、发胖、毛刺）

* **现状感知：** 在 100% DPI 下不易察觉，125% 起 1px 边框开始发胖（变 1.5–2px），200% DPI 下圆角边缘出现毛刺。
* **现状审计：** 全项目 `setCosmetic(True)` 使用率 0/31 `paintEvent`；1px 边框在 125% DPI 下普遍走 `QPen(1)` 而非 `QPen(Qt::Cosmetic)`。
* **目标：** 在所有 DPI（100% / 125% / 150% / 175% / 200% / 250%）下，1px 边框始终保持物理 1px 细，圆角边缘光滑无锯齿。
* **代码动作：**
  * `ui/utils/pixel_snap.py` 提供 `snap_rect()` / `make_cosmetic_pen()` / `stroke_path()`
  * 31 个 `paintEvent` 全部加 `snap_rect` + `make_cosmetic_pen`（不留遗漏）
  * `border: none` 必须配套 `border-radius: 0`（118 处待修复），杜绝 QSS 与 paintEvent 圆角冲突

### 1.2 节奏统一（消除"这里 6px 那里 9px"的随意感）

* **现状感知：** 不同窗口的边距、间距、组件大小各自为政，凑近看会觉得"这软件不够讲究"。
* **现状审计：** 全项目 `sp()` 调用均已使用 4 倍数或白名单例外值，当前审计检出 **0 处违规**（审计脚本 `ALLOWED_GRID` 之前存在白名单过宽问题，已修复，详见 §4.4）。
* **目标：** 视觉上有清晰的"格子感"——所有间距都是 4 的倍数（4/8/12/16/20/24/32/48），所有圆角都是 6/8/10/12 之一。
* **代码动作：**
  * 强制 `sp()` 调用走 4 倍数 ✅（代码库已合规）
  * `radius("sm"|"md"|"lg"|"xl")` 统一收口
  * 审计脚本 `ALLOWED_GRID` 已修复：移除穷举集合，改用 `value % 4 == 0` 自动判定（详见 §4.4）

### 1.3 配色协调（消除"这里偏冷那里偏暖"的割裂）

* **现状感知：** 不同窗口的背景色、文本色、边框色在视觉上略有差异，但因为都是"近似黑/近似白"，用户说不出哪里不对但觉得"不够统一"。
* **现状审计：** 30 个文件中 `audit_hardcoded_colors.py` 检出 **193 处**非 whitelist 硬编码 `QColor(...)` 字面量（Dialog 背景/边框、悬浮/选中态、图标调色板等）。
* **目标：** 所有 Dialog、所有面板、所有子组件的颜色都从同一组 token 取值，**肉眼上**是一套设计语言。
* **代码动作：**
  * `ui/styles/design_tokens.py` 提供 `surface(theme, key)` / `text(theme, key)` / `border(theme, key)`
  * **193 处**硬编码 `QColor(...)` 全部走 token
  * 5 个 audit lint 阻断新违规

### 1.4 字体规整（消除"这里 12px 那里 13px"的不一致）

* **现状感知：** 同样是正文，有些地方 12px，有些 13px；同样是小字，有些 11px，有些 10px；不同字号的对比关系不清晰。
* **现状审计：** `audit_font_consistency.py` 检出 **0 处**内联 `font-size: N px`，已经全部清理完毕。`get_qfont` 调用 14 文件 50 次；`get_font_css_with_size` 调用 4 文件 15 次。
* **目标：** 字号梯度严格收敛到 13 个（10/11/12/13/14/15/16/18/20/24/28/32/40），字重仅 4 档（400/500/600/700）。
* **代码动作：**
  * 字体栈调整为**微软雅黑优先**（`Microsoft YaHei UI` 作为首位），其后才是 `Segoe UI Variable` 系列 — `font_manager.py:9-15` **尚未更新**，字体栈仍为旧顺序
  * 内联 font-size 已清，本项标记为已完成

### 1.5 反馈细腻（消除"按钮按下去没反应"或"反馈太快/太慢"）

* **现状感知：** 按钮按下瞬间变色、没有过渡；菜单项 hover 立即出现；focus 状态用浏览器默认 outline（有时不显示）。
* **现状审计：** `ui/utils/interruptible_animation.py`（44 行）已实现 `stop_animation / is_animation_running / stop_named_animations / set_precise_timer`，被 17 个文件调用；`QPropertyAnimation` 全项目 60 次（18 个文件）。**动画基础设施已存在，缺的是语义化封装**（`fade_in/out/scale_in/slide_in`）。
* **目标：** 所有交互都有合适的过渡时长（80–200ms）和缓动曲线（`cubic-bezier(0.4, 0.0, 0.2, 1.0)`）；键盘焦点有清晰的 1px 高亮圆角环。
* **代码动作：**
  * `ui/styles/motion.py` 提供 `DURATION_*` / `EASE_*` 常量
  * `ui/styles/focus_ring.py` 提供 `:focus` 伪类规则
  * `ui/styles/style.py` 追加 `:focus` 伪类、`:pressed` 微动效
  * `ui/utils/animations.py` 提供 `fade_in/fade_out/scale_in/slide_in` 语义接口，**内部委托 `interruptible_animation` 已有的 `stop_named_animations`**，不重新发明轮子

### 1.6 深度真实（消除"阴影像贴纸"的虚假感）

* **现状感知：** 部分组件有 `QGraphicsDropShadowEffect` 但参数过小（Blur=10, Offset=2），看起来像被压扁的贴纸而非自然投影。
* **现状审计：** 全项目 `QGraphicsDropShadowEffect` 实例化 **2 处**（`folder_panel.py:225`、`icon_grid.py:1273`），均已走 `elevation()` token 取参数。`QGraphicsOpacityEffect` 剩余 **1 处**（`folder_panel.py:451`），其余 16 处已替换为 `setWindowOpacity()`。
* **目标：** 阴影有清晰的层级（elev-0 无阴影 / elev-1 轻悬浮 / elev-2 卡片 / elev-3 弹窗），每层 Y-offset 4-12px、Blur 12-32px。
* **代码动作：**
  * `Elevation` token 收口
  * **2 处** `QGraphicsDropShadowEffect` 已走 token ✅
  * **1 处** `QGraphicsOpacityEffect` 残留需替换（`folder_panel.py:451`，详见 §4.10.1）
  * Win10 自动降级到轻量阴影

### 1.7 性能流畅（消除"卡顿、掉帧、首屏慢"的迟滞感）

> **本节是 1.7.0 优化的核心维度之一。** 所有改动以"流畅度"为最终验收指标；任何改动后帧率、首屏时间、内存占用不能回退。

* **现状感知：**
  * 启动器弹窗首次打开在 200% DPI 4K 屏上可能 1-2 帧延迟（毛玻璃管线 PIL 模糊耗时）
  * 动作链编辑器拖动节点时偶有掉帧（`QGraphicsEffect` 全屏 off-screen 重绘）
  * 设置面板切换页面偶发残影（前页 QGraphicsEffect 未及时释放）
  * 启动时主配置窗口"白屏"或"灰屏"（paintEvent 前的初始化耗时长）
  * 多 Dialog 弹出/关闭时偶尔出现"动画中断后的中间态"（动画未取消）

* **目标指标：**

  | 指标 | 基线（实测） | 目标 | 红线 |
  |---|---:|---:|---|
  | 弹窗首帧（avg） | 57ms（min 1.8, max 168） | ≤ 16ms | > 20ms 报警 |
  | 弹窗稳态 FPS | 12-20 | ≥ 30 | < 20 报警 |
  | 配置窗口打开到可交互 | 42ms（avg） | ≤ 350ms | > 500ms 报警 |
  | 设置面板切换 | 61ms（avg） | ≤ 200ms | > 300ms 报警 |
  | 节点拖动 | 15ms（avg） | ≥ 55 FPS | < 50 FPS 报警 |
  | 命令面板查询响应 | TBD | ≤ 50ms | > 100ms 报警 |
  | 内存占用峰值 | TBD | ≤ +5% | > +10% 报警 |
  | 0 残影（暗/亮切换、Dialog 关闭、动画中断） | — | 0 | > 0 报警 |
  | 毛玻璃启动耗时 | 202ms（avg） | ≤ 500ms | > 800ms 报警 |

* **代码动作分述（详见 §五）：**
  * **5.1 渲染热路径**：用 `update(rect)` 替代 `update()`，避免 `repaint()`，QGraphicsEffect 限定为必要场景
  * **5.2 动画系统**：用 `QPropertyAnimation` + `QSequentialAnimationGroup` 替代 `QTimer.singleShot` 链式动画
  * **5.3 毛玻璃管线**：200% DPI 自适应 downsample，三缓冲改为四缓冲（增加一帧时延换取更稳的 20FPS）
  * **5.4 缓存策略**：缩略图、icon path、`QPainterPath` 全部 LRU 缓存
  * **5.5 资源释放**：动画、GraphicsEffect、Worker 线程、QPixmap 缓存全部 owner-disposable 化
  * **5.6 启动性能**：配置窗口、启动器弹窗的 paintEvent 前的"冷启动"耗时优化（延迟加载图标、worker 化）

### 1.8 视觉过渡自然（消除"突然出现/突然消失"的生硬感）

* **现状感知：** 弹窗突然出现/突然消失；按钮按下瞬间变色；菜单展开没有 fade；focus 状态瞬切。
* **目标：** 所有出现/消失/状态切换都带 80-320ms 的 ease 过渡；用户能"看到"UI 在响应。
* **代码动作：**
  * `ui/styles/motion.py` 提供 `DURATION_*` / `EASE_*` 常量
  * `interruptible_animation.py` 统一收口动画
  * `ui/styles/focus_ring.py` 提供 `:focus` 伪类规则（focus 切换 80ms 过渡）
  * `ui/styles/style.py` 追加 `:pressed` 80ms 颜色过渡

---

## 二、规划分层

| 层面 | 范围 | 改动强度 | 视觉影响 |
|---|---|---|---|
| **L1 基建** | Token、工具类、Mixin、基类、Lint、视觉基线、文档 | 大量新增 | **无** |
| **L2 代码强制统一** | 硬编码迁移、paintEvent 标准化、字体统一、栅格强制、QSS 冲突、阴影统一、巨型文件拆分 | 强制改造 | **无**（仅精度提升） |
| **L3 视觉精致化** | 像素对齐启用、Focus Ring 启用、微动效启用、阴影升级 | Feature Flagged | **正向上**（更精致） |

> L1 + L2 不产生肉眼可见的视觉变化（除 L3 标注项），可以并行。
> L3 严格控制范围：**只许让 UI 更好看，不许更难看**。

---

## 三、L1 基建

### 3.1 Design Token `ui/styles/design_tokens.py`

```python
class Theme:
    DARK = "dark"
    LIGHT = "light"

class SurfaceScale:
    """背景色按语义分组。"""

    bg_dialog_dark = QColor(28, 28, 30, 230)
    bg_dialog_light = QColor(242, 242, 247, 205)
    bg_chrome_dark = QColor(43, 43, 43, 230)
    bg_chrome_light = QColor(255, 255, 255, 235)
    bg_elevated_dark = QColor(58, 58, 60, 230)
    bg_elevated_light = QColor(255, 255, 255, 245)
    bg_glass_dark_win10 = QColor(28, 28, 30, 180)
    bg_glass_dark_win11 = QColor(28, 28, 30, 100)
    bg_glass_light_win10 = QColor(242, 242, 247, 160)
    bg_glass_light_win11 = QColor(242, 242, 247, 100)
    bg_hover_subtle_dark = QColor(255, 255, 255, 15)
    bg_hover_subtle_light = QColor(0, 0, 0, 10)
    bg_pressed_subtle_dark = QColor(255, 255, 255, 25)
    bg_pressed_subtle_light = QColor(0, 0, 0, 18)
    bg_selection_dark = QColor(10, 132, 255, 76)
    bg_selection_light = QColor(0, 122, 255, 36)
    bg_overlay_tint_dark = QColor(0, 0, 0, 90)
    bg_overlay_tint_light = QColor(255, 255, 255, 110)

class TextScale:
    primary_dark = QColor(255, 255, 255, 242)
    primary_light = QColor(28, 28, 30, 242)
    secondary_dark = QColor(255, 255, 255, 217)
    secondary_light = QColor(28, 28, 30, 217)
    tertiary_dark = QColor(255, 255, 255, 180)
    tertiary_light = QColor(60, 60, 67, 165)
    disabled = QColor(128, 128, 128, 128)
    on_accent = QColor(255, 255, 255, 255)

class BorderScale:
    subtle_dark = QColor(190, 190, 197, 60)
    subtle_light = QColor(229, 229, 234, 150)
    strong_dark = QColor(255, 255, 255, 100)
    strong_light = QColor(0, 0, 0, 90)
    separator_dark = QColor(255, 255, 255, 41)
    separator_light = QColor(60, 60, 67, 46)
    focus = QColor(0, 122, 255, 255)
    focus_dark = QColor(10, 132, 255, 255)

class StatusScale:
    success = QColor(48, 209, 88, 255)
    success_dark = QColor(48, 209, 88, 200)
    warning = QColor(255, 159, 10, 255)
    warning_dark = QColor(255, 159, 10, 200)
    error = QColor(255, 59, 48, 255)
    error_dark = QColor(255, 69, 58, 220)
    info = QColor(100, 210, 255, 255)
    info_dark = QColor(10, 132, 255, 220)
    node_success = QColor(212, 237, 218, 255)
    node_success_strong = QColor(46, 125, 50, 255)
    node_error = QColor(255, 205, 210, 255)
    node_error_strong = QColor(211, 47, 47, 255)
    node_warning = QColor(255, 243, 205, 255)
    node_warning_strong = QColor(245, 124, 0, 255)
    drop_highlight_pen = QColor(168, 230, 207, 180)
    drop_highlight_brush_soft = QColor(168, 230, 207, 45)
    drop_highlight_brush_strong = QColor(168, 230, 207, 75)
    drop_highlight_pressed = QColor(70, 180, 140, 200)
    # support_card_* / qr_* 见实际代码

class RadiusScale:
    xs = 4
    sm = 6
    md = 8
    lg = 10
    xl = 12

class SpacingScale:
    s2 = 4
    s3 = 8
    s4 = 12
    s5 = 16
    s6 = 20
    s7 = 24
    s8 = 32
    s9 = 48

class Elevation:
    elev_0 = (0, 0, QColor(0, 0, 0, 0))
    elev_1 = (3, 12, QColor(0, 0, 0, 30))
    elev_2 = (6, 20, QColor(0, 0, 0, 50))
    elev_3 = (12, 32, QColor(0, 0, 0, 80))

    @staticmethod
    def for_level(level: int, is_win10: bool = False) -> tuple[int, int, QColor]:
        if is_win10 and level >= 3:
            level = 1
        return {0: elev_0, 1: elev_1, 2: elev_2, 3: elev_3}[max(0, min(3, level))]

class DurationScale:
    INSTANT = 50
    FAST = 120
    NORMAL = 200
    SLOW = 320
    X_SLOW = 480
    FADE_IN = 200
    FADE_OUT = 160
    SLIDE_IN = 240
    SCALE_IN = 220
    TOOLTIP = 120
    THEME_SWITCH = 200
    DIALOG_OPEN = 280
    DIALOG_CLOSE = 200

class EasingScale:
    STANDARD = "cubic-bezier(0.4, 0.0, 0.2, 1.0)"
    EMPHASIZED = "cubic-bezier(0.2, 0.0, 0.0, 1.0)"
    ACCELERATE = "cubic-bezier(0.4, 0.0, 1.0, 1.0)"
    DECELERATE = "cubic-bezier(0.0, 0.0, 0.2, 1.0)"
    LINEAR = "linear"

# 解析入口 —— 实际已完全实现
def surface(theme: str, key: str) -> QColor:
    """按 theme 解析 SurfaceScale 色值。
    优先尝试 key 原文（含后缀），其次 {key}_{theme}。
    """
    suffix = "_dark" if theme == "dark" else "_light"
    value = getattr(SurfaceScale, key, None)
    if value is not None:
        return QColor(value)
    value = getattr(SurfaceScale, f"{key}{suffix}", None)
    if value is not None:
        return QColor(value)
    return QColor(0, 0, 0, 0)

def text(theme: str, key: str) -> QColor:
    suffix = "_dark" if theme == "dark" else "_light"
    value = getattr(TextScale, f"{key}{suffix}", None)
    if value is None:
        value = getattr(TextScale, key, None)
    if value is None:
        return QColor(255, 255, 255, 255)
    return QColor(value)

def border(theme: str, key: str) -> QColor:
    suffix = "_dark" if theme == "dark" else "_light"
    value = getattr(BorderScale, f"{key}{suffix}", None)
    if value is None:
        value = getattr(BorderScale, key, None)
    if value is None:
        return QColor(0, 0, 0, 0)
    return QColor(value)

def status(key: str) -> QColor:
    value = getattr(StatusScale, key, None)
    return QColor(value) if value else QColor(128, 128, 128, 255)

def radius(key: str) -> int:
    return int(getattr(RadiusScale, key, RadiusScale.md))

def spacing(key: str) -> int:
    return int(getattr(SpacingScale, key, SpacingScale.s3))

def elevation(level: int, *, is_win10: bool = False) -> tuple[int, int, QColor]:
    return Elevation.for_level(level, is_win10=is_win10)

def duration(key: str) -> int:
    return int(getattr(DurationScale, key, DurationScale.NORMAL))

def easing(key: str) -> str:
    return str(getattr(EasingScale, key, EasingScale.STANDARD))

def apply_motion_scale(value: int, scale: float = 1.0) -> int:
    if scale is None or scale == 1.0:
        return value
    try:
        return max(0, min(1000, int(round(value * float(scale)))))
    except (TypeError, ValueError):
        return value
```

### 3.2 像素对齐工具 `ui/utils/pixel_snap.py`

```python
def snap_rect(rect: QRect | QRectF, *, inset: float = 0.5) -> QRectF:
    """返回四边对齐到整像素的 QRectF，inset 向内缩进以容纳 1px cosmetic 描边。"""
    rf = QRectF(rect) if isinstance(rect, QRect) else rect
    if inset:
        rf = rf.adjusted(inset, inset, -inset, -inset)
    x, y = round(rf.left()), round(rf.top())
    w, h = round(rf.right()) - x, round(rf.bottom()) - y
    return QRectF(float(x), float(y), float(w), float(h))

def make_cosmetic_pen(color: QColor, width: int = 1) -> QPen:
    """构造 cosmetic QPen，物理像素始终为 1px，不受 DPI 影响。"""
    pen = QPen(QColor(color))
    pen.setWidth(max(1, int(width)))
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen

def stroke_path(painter: QPainter, path: QPainterPath, color: QColor, width: int = 1) -> None:
    """用 cosmetic pen 描画路径。"""
    painter.save()
    painter.setPen(make_cosmetic_pen(color, width=width))
    painter.setBrush(QtCompat.NoBrush)
    painter.drawPath(path)
    painter.restore()

def create_pixmap(width: int, height: int, widget: QWidget | None = None, *,
                  fill_color: QColor | None = None) -> QPixmap:
    """构建支持 devicePixelRatio 的 QPixmap，高 DPI 下图标不模糊。"""
    dpr = device_pixel_ratio(widget)
    backing_w, backing_h = max(1, round(width * dpr)), max(1, round(height * dpr))
    pix = QPixmap(backing_w, backing_h)
    pix.setDevicePixelRatio(dpr)
    if fill_color:
        pix.fill(fill_color)
    return pix

def device_pixel_ratio(widget: object | None = None) -> float:
    """获取 widget 或 App 的设备像素比，兜底 1.0。"""

def build_rounded_mask(width: int, height: int, radius: int) -> QRegion:
    """构建圆角 QBitmap → QRegion，用于 WA_TranslucentBackground 窗口的 setMask。"""
```

### 3.3 动效常量 `ui/styles/motion.py`

```python
DURATION_INSTANT_MS = 50
DURATION_FAST_MS = 120
DURATION_NORMAL_MS = 200
DURATION_SLOW_MS = 320
DURATION_XSLOW_MS = 480
EASE_STANDARD = "cubic-bezier(0.4, 0.0, 0.2, 1.0)"
EASE_EMPHASIZED = "cubic-bezier(0.2, 0.0, 0.0, 1.0)"
```

### 3.4 标准基类 `ui/styles/standard_widgets.py`

```python
class FocusRingMixin:
    """Mixin：paintEvent 中在焦点态时绘制 1px cosmetic 高亮圆角环。"""
    focus_ring_inset: float = 2.0
    focus_ring_radius: int = RadiusScale.md

    def _focus_ring_color(self) -> QColor:
        return QColor(BorderScale.focus_dark if getattr(self, "theme", "dark") == "dark" else BorderScale.focus)

    def _draw_focus_ring(self, painter: QPainter) -> None:
        if not isinstance(self, QWidget) or not self.hasFocus():
            return
        snapped = snap_rect(self.rect(), inset=self.focus_ring_inset)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(make_cosmetic_pen(self._focus_ring_color(), 1))
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(snapped, float(self.focus_ring_radius), float(self.focus_ring_radius))
        painter.restore()

class PixelSnapMixin:
    """Mixin：在 paint 开始处统一启用 Antialiasing。"""

    def _enable_aa(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

class ThemedButton(QPushButton):
    def __init__(self, text: str = "", parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(text, parent)
        self.theme = theme
        self.setAttribute(QtCompat.WA_StyledBackground, False)
    def accent_color(self) -> QColor:
        return surface(self.theme, "bg_elevated")

class ThemedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(text, parent)
        self.theme = theme

class ThemedLineEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(QtCompat.WA_StyledBackground, False)

class ThemedDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(parent)
        self.theme = theme
        self._animation_names: tuple[str, ...] = ()
    def hideEvent(self, event):
        stop_named_animations(self, *self._animation_names)
        super().hideEvent(event)
    def closeEvent(self, event):
        stop_named_animations(self, *self._animation_names)
        super().closeEvent(event)
```

> 基类作为**未来新增组件的起点**；现有 `RoundedWindow`、`ThemedMessageBox`、`BaseDialog` 不强制替换。

### 3.5 视觉基线 `docs/visual_baseline/`

**18 张关键界面 PNG**（原文档 12 张遗漏了 `folder_panel / icon_grid / update_dialog / log_window / welcome_guide / themed_tool_window / about_window` 等在 §四 中有 paintEvent 标准化动作的界面）：

**核心界面（10 张）：**
1. 配置窗口（暗/亮） — `main_window.py`
2. 启动器弹窗（暗/亮） — `popup_window.py`
3. 设置面板（暗/亮） — `settings_panel.py`
4. 动作链编辑器 — `chain_canvas.py`
5. 命令面板 — `command_panel_window.py`
6. 命令对话框（CommandDialog）— `command_dialog.py`
7. 动作链对话框（ChainDialog）— `chain_dialog.py`
8. 批量启动对话框（BatchLaunchDialog）— `batch_launch_dialog.py`
9. 宏录制对话框（MacroRecordDialog）— `macro_record_dialog.py`
10. 热键对话框（HotkeyDialog）— `hotkey_dialog.py`

**辅助界面（8 张，§四 改造覆盖但原基线漏列）：**
11. 文件夹面板（FolderPanel）— `folder_panel.py`（1253 行，§4.7 拆分目标）
12. 图标网格（IconGrid）— `icon_grid.py`（2469 行，§4.7 拆分目标）
13. 更新对话框（UpdateDialog）— `update_dialog.py`
14. 日志窗口（LogWindow）— `log_window.py`
15. 欢迎引导（WelcomeGuide）— `welcome_guide.py`
16. 主题化工具窗口（ThemedToolWindow）— `themed_tool_window.py`
17. 关于窗口（AboutWindow）— `about_window.py`
18. ThemedMessageBox / Toast — `themed_messagebox.py` / `toast_notification.py`

* `tools/dump_visual_baseline.py` 一键生成
* `tools/visual_diff.py` 像素级对比，**Δ > 0.5% 自动 block**（L3 启用后允许 Δ ≤ 1%）
* `tests/ui/test_visual_baseline.py` CI 集成
* 基线文件命名：`{component}_{theme}_{dpi}.png`，如 `popup_dark_200.png`

### 3.6 Lint 工具集 `scripts/`

| 脚本 | 检查 | 阻断 |
|---|---|---|
| `audit_grid_violations.py` | `sp(整数)` 非 4 倍数 | **是** |
| `audit_hardcoded_colors.py` | 硬编码 `QColor(...)` | **是**（除 token 文件） |
| `audit_paint_snap.py` | `paintEvent` 缺 snap/cosmetic | **是** |
| `audit_qss_radius.py` | `border: none` 缺 `border-radius: 0` | **是** |
| `audit_motion_consistency.py` | `QTimer.singleShot` 未走 `interruptible_animation` | **是** |
| `audit_font_consistency.py` | 内联 `font-size: N px` 硬编码 | **是** |

### 3.7 文档 `docs/ui/`

* `style_guide.md` —— 颜色、字号、圆角、阴影、间距事实清单
* `component_gallery.md` —— 标准组件使用示例
* `adr/ADR-001-token.md`、`ADR-002-base-classes.md`、`ADR-003-visual-baseline.md`

---

## 四、L2 代码强制统一

> 改动大量代码但**不产生肉眼可见的视觉变化**（除精度提升）。**不留兼容垫片**。

### 4.1 硬编码色值迁移

**audit_hardcoded_colors.py 检出 193 处非 whitelist 硬编码 QColor 字面量，分布在 30 个文件。** 以下按违规数降序列出：

| 文件 | 违规数 | 说明 |
|---|---|---:|---|
| `ui/config_window/icon_grid.py` | 37 | 背景/边框/图标调色板/状态色 |
| `ui/config_window/settings_panel.py` | 21 | 列表项/选中色/背景/边框 |
| `ui/config_window/settings_helpers.py` | 14 | 编号/选中态/文字/背景 |
| `ui/config_window/settings_support_page.py` | 14 | QR 码/卡片/文字/背景 |
| `ui/config_window/batch_launch_dialog.py` | 12 | 快捷方式类型调色板/背景 |
| `ui/config_window/folder_panel_widgets.py` | 10 | 悬浮色/文字色/边框 |
| `ui/command_panel_widgets.py` | 7 | 状态色/按钮颜色 |
| `ui/config_window/base_dialog.py` | 6 | 对话框背景/边框 |
| `ui/config_window/macro_record_dialog.py` | 6 | 按键状态色/图标 |
| `ui/launcher_popup/popup_search.py` | 6 | 搜索建议 hover/文字色 |
| `ui/toast_notification.py` | 6 | 通知背景/边框（含 error 色） |
| `ui/styles/style.py` | 5 | PopupMenu paintEvent 色值 |
| `ui/custom_tooltip.py` | 4 | 悬浮提示背景/边框 |
| `ui/log_window.py` | 4 | 日志窗口背景/边框 |
| `ui/themed_tool_window.py` | 4 | 工具窗口背景/边框 |
| `ui/welcome_guide.py` | 4 | 引导页背景/边框 |
| `ui/config_window/support_dialog.py` | 4 | 对话框文字/边框 |
| `ui/config_window/chain_dialog.py` | 3 | 分隔线/背景 |
| `ui/config_window/hotkey_dialog.py` | 3 | 快捷键录制图标 |
| `ui/config_window/shortcut_dialog.py` | 3 | 热键编辑图标 |
| `ui/config_window/folder_panel.py` | 2 | 激活边框色 |
| `ui/config_window/main_window_rounded.py` | 2 | 主窗口背景/边框 |
| `ui/config_window/settings_commands_page.py` | 2 | 命令列表边框 |
| `ui/config_window/url_dialog.py` | 2 | URL 编辑图标 |
| `ui/launcher_popup/popup_command_result.py` | 2 | 结果项 overlay/文字色 |
| `ui/launcher_popup/popup_window_helpers.py` | 2 | IconFlash 颜色 |
| `ui/utils/smooth_scroll.py` | 2 | 滚动条渐变 |
| `ui/utils/window_effect.py` | 2 | 窗口效果透明填充 |
| `ui/config_window/chain_canvas.py` | — | §4.7 拆分后再处理 |
| `ui/launcher_popup/popup_renderer.py` | — | 已有 paintEvent 改造计划 |

> **注：** 以上列表由 `audit_hardcoded_colors.py` 自动生成，行级详情可通过 `python scripts/audit_hardcoded_colors.py` 查看。

### 4.2 paintEvent 标准化

**audit_paint_snap.py 检出 31 个 `paintEvent` 方法，全部 `snap_rect` + `make_cosmetic_pen` + token 派生。** 当前 `setCosmetic(True)` 使用率 0/31：

| # | 文件:行 | 改造内容 | 备注 |
|---|---|---|---|
| 1 | `ui/command_panel_widgets.py:40` | 1 处（risky=2） | |
| 2 | `ui/command_panel_widgets.py:93` | 1 处 | |
| 3 | `ui/custom_tooltip.py:46` | 1 处 | |
| 4 | `ui/log_window.py:370` | 1 处 | |
| 5 | `ui/themed_tool_window.py:356` | 1 处 | |
| 6 | `ui/toast_notification.py:75` | 1 处 | |
| 7 | `ui/welcome_guide.py:229` | 1 处（risky=1） | |
| 8 | `ui/config_window/base_dialog.py:113` | 1 处（risky=1） | |
| 9 | `ui/config_window/batch_launch_dialog.py:350` | 1 处 | |
| 10 | `ui/config_window/folder_panel_widgets.py:233` | 1 处 | |
| 11 | `ui/config_window/icon_grid.py:122` | 1 处（risky=1，高频） | |
| 12 | `ui/config_window/icon_grid.py:506` | 1 处 | |
| 13 | `ui/config_window/main_window_rounded.py:68` | 1 处（risky=1） | |
| 14 | `ui/config_window/main_window_title_bar.py:44` | 1 处 | |
| 15 | `ui/config_window/settings_helpers.py:232` | 1 处（risky=1） | |
| 16 | `ui/config_window/settings_helpers.py:392` | 1 处（risky=1） | |
| 17 | `ui/config_window/settings_panel.py:148` | 1 处（risky=1） | |
| 18 | `ui/config_window/settings_panel.py:321` | 1 处 | |
| 19 | `ui/config_window/settings_panel.py:505` | 1 处 | |
| 20 | `ui/config_window/settings_support_page.py:305` | 1 处 | |
| 21 | `ui/config_window/settings_support_page.py:605` | 1 处 | |
| 22 | `ui/config_window/support_dialog.py:180` | 1 处 | |
| 23 | `ui/launcher_popup/popup_command_result.py:405` | 1 处 | |
| 24 | `ui/launcher_popup/popup_renderer.py:125` | 1 处（risky=2） | |
| 25 | `ui/launcher_popup/popup_window_helpers.py:277` | `IconFlashOverlay` | |
| 26 | `ui/styles/color_filter_overlay.py:131` | 新增 `Overlay.tint_for(theme)` | |
| 27 | `ui/styles/style.py:692` `PopupMenu.paintEvent` | 1 处（risky=1） | |
| 28 | `ui/styles/themed_messagebox.py:334` | 1 处（risky=1） | |
| 29 | `ui/styles/themed_messagebox.py:611` | 1 处 | |
| 30 | `ui/utils/smooth_scroll.py:69` | 1 处 | |

> **注：** 以上列表由 `audit_paint_snap.py` 自动生成。相比基线 32 处少了 1 处（`tray_app.py` / `chain_canvas.py` / `glass_background.py` / `popup_window.py` 等文件的 paintEvent 可能被合并或移除），当前实测 31 处。

### 4.3 字体统一

`ui/utils/font_manager.py:9-15` 调整字体栈（**微软雅黑优先，其后插入 Segoe UI Variable**）：

**当前（实测）：**
```python
FALLBACK_FONT_FAMILIES = (
    "Microsoft YaHei UI",      # L10 - Win10 主字体
    "Microsoft YaHei",          # L11
    "Source Han Sans SC",       # L12
    "Segoe UI",                 # L13 - Win 兜底
    "Arial",                    # L14
)
```

**目标：**
```python
FALLBACK_FONT_FAMILIES = (
    "Microsoft YaHei UI",       # L10 - 首选字体（微软雅黑）
    "Microsoft YaHei",          # L11
    "Segoe UI Variable Text",   # L12 - Win11 变字重
    "Segoe UI Variable Display",# L13
    "Segoe UI",                 # L14 - Win 兜底
    "Source Han Sans SC",       # L15
    "Arial",                    # L16
)
```

> 注：现有 `style.py:178, 186, 194, 202` 已在 QSS 中使用 `'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI',sans-serif`——`QSS 字体栈也需同步调整为微软雅黑优先`。

**全项目 220 处内联 `font-size: N px` / `setPixelSize(N)`** 走 `get_font_css_with_size` / `get_qfont`：

| 模式 | 现状 | 改为 |
|---|---|---|
| `scale_qss("font-size: 12px; ...")` | 内联 | `scale_qss(f"{get_font_css_with_size(12, 400)} ...")` |
| `setFont(QFont("Microsoft YaHei", 12))` | 硬编码 | `setFont(get_qfont(12, 400))` |
| `painter.setFont(QFont("...", 12))` | 硬编码 | `painter.setFont(get_qfont(12, 400))` |

**违规分布（按文件）：**
* `ui/styles/style.py` — 47 处
* `ui/config_window/chain_dialog.py` — 16 处
* `ui/config_window/command_dialog.py` — 12 处
* `ui/config_window/settings_plugins_page.py` — 12 处
* `ui/config_window/chain_canvas.py` — 10 处
* `ui/config_window/icon_grid.py` — 9 处
* `ui/config_window/settings_commands_page.py` — 9 处
* `ui/log_window.py` — 9 处
* `ui/config_window/settings_support_page.py` — 9 处
* `ui/config_window/macro_record_dialog.py` — 8 处
* `ui/config_window/main_window_title_bar.py` — 8 处
* `ui/config_window/batch_launch_dialog.py` — 8 处
* `ui/config_window/hotkey_dialog.py` — 7 处
* `ui/config_window/command_dialog.py:286-310, 397, 417, 453, 587` — 锚点行（含整段 f-string CSS）
* `ui/config_window/batch_launch_dialog.py:594, 658, 713, 740` — 锚点行
* 其余 18 文件 — 共 ~47 处

**`get_qfont` 现状：** 14 文件 50 次调用（`about_window.py:5, log_window.py:4, themed_tool_window.py:4, toast_notification.py:2, update_dialog.py:4, welcome_guide.py:4, folder_panel_widgets.py:2, settings_panel.py:9, settings_system_page.py:2, themed_messagebox.py:10, font_manager.py:2, ...`）。**字体 API 已存在，迁移时优先复用，不重新发明。**

### 4.4 栅格纪律强制

> **⚠️ 审计脚本修复记录：** `audit_grid_violations.py` 原 `ALLOWED_GRID` 为穷举 4 倍数列表（4..1024 全部白名单）+ 额外包含 18/28，导致脚本实际上无法检出任何违规。已修复为：移除穷举 `ALLOWED_GRID` 集合，改为运行时 `value % 4 == 0` 自动判定；18 移入 `ALLOWED_EXCEPTIONS` 按文档保留。同步修复 `fix_grid_violations.py`。

**audit_grid_violations.py 当前检出 `sp(整数)` 非 4 倍数调用：0 处**。当前代码库中所有 `sp()` 实参均为 4 倍数或白名单例外值。

**白名单 `ALLOWED_EXCEPTIONS`（不强制为 4 倍数）：**
`{1, 2, 3, 5, 6, 7, 18}`

* `1`（边框宽度）— 实际为 `QPen(1)` 配 `setCosmetic(True)`，不参与栅格
* `2`（极小间距）
* `3`（仅 `chain_canvas.py:1700` line_height 计算）
* `5`（状态指示器、checkbox indicator）
* `6`（极小图标 ≤12px 内边距；但 6 用在 ≥12px 容器仍需改 8）
* `7`（仅 `chain_canvas.py` 画布坐标 L286, 296, 308）
* `18`（保留，4 倍数边界）

**`ALLOWED_WINDOW_SIZES`（窗口/场景维度，不强制 4 倍数）：**
`{350, 440, 1200, 2200}`

**禁用值（不修改脚本，自动被 `value % 4 != 0` 捕获）：**
`9`/`10`/`11`/`13`/`14`/`15`/`17`/`19`/`21`/`22`/`23`/`25`/`26`/`27`/`29`/`30`/`31`/`33`/`34`/`35`/`37`/`38`/`39`/`41`/`42`/`43`/`45`/`46`/`47`/`49`/`50`/`51`/`53`/`54`/`55`/`57`/`58`/`59`/`61`/`62`/`63`...

### 4.5 QSS 圆角冲突剥离

**audit_qss_radius.py 检出 `border: none` 共 118 处**（较基线 120 减少 2 处），分布在 28 个文件：

| 文件 | `border: none` 数 | 备注 |
|---|---|---:|---|
| `ui/styles/style.py` | 17 | |
| `ui/config_window/batch_launch_dialog.py` | 14 | |
| `ui/config_window/settings_panel.py` | 10 | |
| `ui/config_window/settings_support_page.py` | 10 | |
| `ui/config_window/chain_dialog.py` | 7 | |
| `ui/config_window/theme_helper.py` | 6 | |
| `ui/launcher_popup/popup_command_result.py` | 6 | |
| `ui/command_panel_window.py` | 5 | |
| `ui/config_window/icon_grid.py` | 5 | |
| `ui/config_window/main_window_title_bar.py` | 5 | |
| `ui/config_window/command_dialog.py` | 4 | |
| `ui/config_window/folder_panel.py` | 4 | |
| `ui/config_window/settings_helpers.py` | 3 | |
| `ui/log_window.py` | 2 | |
| `ui/themed_tool_window.py` | 2 | |
| `ui/config_window/chain_canvas.py` | 2 | |
| `ui/config_window/main_window.py` | 2 | |
| `ui/config_window/settings_about_page.py` | 2 | |
| `ui/config_window/settings_commands_page.py` | 2 | |
| （其余 9 文件） | 各 1 | |
| **合计** | **118** | |

**lint 规则：** `audit_qss_radius.py` 检测 `border: none` 必须紧跟 `border-radius: 0`，缺则阻断。

### 4.6 阴影统一规范

**2 处 `QGraphicsDropShadowEffect` 均已走 `elevation()` token（已完成）：**

| 文件 | 行 | 现状 |
|---|---|---|
| `ui/config_window/folder_panel.py` | 224 | `elevation(1, is_win10=is_win10())` |
| `ui/config_window/icon_grid.py` | 1273 | `elevation(1, is_win10=is_win10())` |

**`Elevation` token 设计：**
```python
class Elevation:
    elev_0 = (0, 0, QColor(0, 0, 0, 0))         # 无阴影
    elev_1 = (3, 12, QColor(0, 0, 0, 30))        # 轻悬浮（按钮悬浮）
    elev_2 = (6, 20, QColor(0, 0, 0, 50))        # 卡片（图标悬浮）
    elev_3 = (12, 32, QColor(0, 0, 0, 80))       # 弹窗（Dialog 弹出）
```

> **Win10 自动降级：** 检测 `is_win10()` 时使用 `elev_1` 替代 `elev_3`，避免低端 GPU 卡顿。
> 视觉影响：**Win11 用户能看到更柔和、更明显的阴影**；Win10 自动降级（保持原观感）。**属于"更精致"而非"更丑"**。

> ⚠️ **重要区分：** `QGraphicsDropShadowEffect` 与 `QGraphicsOpacityEffect` 是**两个完全不同的优化方向**——前者走 off-screen render + 高斯模糊，后者仅做透明度合成。**§4.6 只处理阴影，§4.10.1 处理透明效果**。

### 4.7 巨型文件拆分

**实测文件行数（2026-06-19）：** 所有原文档行数都低估 8-17%。拆分时按实际行数计算目标。

| 文件 | 实际行数 | 原文档估计 | 拆分方案 |
|---|---:|---:|---|
| `ui/config_window/chain_canvas.py` | **2483** | 2176 | `chain_canvas.py` + `chain_node.py` + `chain_link.py` |
| `ui/config_window/icon_grid.py` | **2469** | 2136 | `icon_grid.py` + `icon_grid_item.py` |
| `ui/styles/style.py` | **1993** | 1859 | `style.py`（基础）+ `style_components.py`（组件样式）+ `style_menus.py`（菜单） |
| `ui/utils/window_effect.py` | **1680** | 1438 | `window_effect.py` + `win10_shadow.py` + `win11_acrylic.py` |
| `ui/command_panel_window.py` | **1655** | 1503 | `command_panel_window.py` + `command_panel_*.py` |
| `ui/config_window/command_dialog.py` | **1523** | 1365 | `command_dialog.py` + `command_dialog_form.py` |
| `ui/config_window/settings_panel.py` | **1457** | 1280 | `settings_panel.py` + `settings_page_base.py` |
| `ui/config_window/macro_record_dialog.py` | **1406** | 1265 | `macro_record_dialog.py` + `macro_recorder.py` |
| `ui/config_window/chain_dialog.py` | **1377** | 1222 | `chain_dialog.py` + `chain_dialog_property.py` + `chain_dialog_canvas_view.py` |
| `ui/launcher_popup/popup_renderer.py` | **1338** | 1201 | `popup_renderer.py` + `popup_renderer_*.py` |
| `ui/config_window/main_window.py` | **1348** | 1143 | `main_window.py` + `main_window_sidebar.py` + `main_window_statusbar.py` |
| `ui/launcher_popup/glass_background.py` | **1307** | 1212 | `glass_background.py` + `glass_pipeline.py` + `glass_buffer.py`（**按 L1211 拆 draw/publish 边界**） |
| `ui/config_window/settings_support_page.py` | **1253** | 1050 | `settings_support_page.py` + `support_*.py` |
| `ui/config_window/batch_launch_dialog.py` | **1217** | 1041 | `batch_launch_dialog.py` + `batch_launch_card.py` |
| `ui/config_window/folder_panel.py` | **1193** | 1014 | `folder_panel.py` + `folder_panel_*.py` |
| `ui/launcher_popup/popup_events.py` | **1188** | 1044 | `popup_events.py` + `popup_event_*.py` |
| `ui/launcher_popup/popup_search.py` | **1172** | 1026 | `popup_search.py` + `popup_index.py` + `popup_match.py` |

**拆分原则：**
* 每个拆出文件目标 ≤ **500 行**（实测 600 行仍偏大，如 `command_dialog.py:1523` 拆 2 个 ≈ 760 行/文件，需要进一步细分）
* **接口不变**（外部 `import` 不动；__init__.py 重导出兼容）
* **行为完全一致**（跑全量测试 + 18 张视觉基线对比）
* **拆分点选择：** 优先按类边界（每个类一个文件），其次按功能块（paint / event / data）

**`glass_background.py` 特别说明：** L1212 是 `def draw(self, painter) -> bool:` 方法头，**不是文件末尾**。L1212 之前是 worker 线程与帧生产（`_publish_frame` / `_next_generation` 等），L1212 之后是渲染层（`draw` / paint 时的 swap）。拆分时**不要按 L1212 一刀切**，应按线程边界拆：`glass_pipeline.py`（worker + 帧生产）+ `glass_buffer.py`（环形缓冲 + 锁）+ `glass_background.py`（Qt 集成 + draw 调用）。

### 4.8 死代码移除

| 内容 | 位置 | 处理 |
|---|---|---|
| `_apply_theme_colors()` 在 `base_dialog.py` 和 `icon_grid.py` | L71, L267 | 改造后移除（被 token 解析取代） |
| `set_acrylic_mode()` 在 `main_window_rounded.py` | L45 | 保留，内部走 token |
| `parse_color()` 字符串 rgba 解析 | `main_window_rounded.py:50` | 合并到 `QColor` 工厂 |

### 4.10 流畅度与性能优化（**核心维度**）

> 本节是 L2 中最关乎"用户体验"的部分。所有改动必须用性能基线（FPS、首帧、内存）验证，**不允许回退**。

#### 4.10.1 渲染热路径治理

**问题：** `QGraphicsDropShadowEffect`、`QGraphicsOpacityEffect` 会对整个 widget 做 off-screen 渲染，CPU 密集；在动画连续触发时尤其明显。**但两者优化方向不同**——`QGraphicsOpacityEffect` 可被 `setWindowOpacity()` 替代；`QGraphicsDropShadowEffect` **不可被 `setWindowOpacity()` 替代**（前者是透明度合成，后者是高斯模糊 + 透明度混合），需要用 `Elevation` token 收敛参数或预渲染位图。

**两类问题的不同处理：**

| 类型 | 数量 | 文件:行 | 优化方式 |
|---|---:|---|---|
| `QGraphicsOpacityEffect` 实例化 | 17 | 5 文件 | 改用 `widget.setWindowOpacity()` 或 `QPropertyAnimation(widget, b"windowOpacity")` |
| `QGraphicsDropShadowEffect` 实例化 | 2 | 2 文件 | 走 `Elevation` token（详见 §4.6） |
| `setGraphicsEffect(None)` 清理点 | 5 | 4 文件 | 保留（动画结束时清理） |

**`QGraphicsOpacityEffect` 现状（16/17 已替换，剩余 1 处）：**

| 文件 | 行 | 用途 | 状态 |
|---|---|---|---|
| `ui/config_window/settings_system_page.py` | 923, 939, 949 (共 6 实例) | 分组折叠动画 | ✅ 已替换 |
| `ui/config_window/icon_grid.py` | 919, 920, 936, 2044, 2054 (共 4 实例) | 拖拽反馈、列宽动画 | ✅ 已替换 |
| `ui/config_window/settings_support_page.py` | 1159, 1176, 1193 (共 3 实例) | QR 码容器淡入淡出 | ✅ 已替换 |
| `ui/config_window/folder_panel.py` | 451 | 折叠动画 | ❌ **剩余 1 处** |
| `ui/config_window/settings_commands_page.py` | 131, 140, 356 (共 2 实例) | 分组动画 | ✅ 已替换 |

**`QGraphicsDropShadowEffect`（2 处，均已走 `elevation()` token ✅）：**

| 文件 | 行 | 用途 | 改为 |
|---|---|---|---|
| `ui/config_window/folder_panel.py` | 224 | 按钮悬浮阴影 | 走 `elevation(1, is_win10)` ✅ |
| `ui/config_window/icon_grid.py` | 1273 | 按钮悬浮阴影 | 走 `elevation(1, is_win10)` ✅ |

**统一替换模式（仅适用于 OpacityEffect）：**
```python
# 之前（expensive - off-screen 渲染整 widget）
effect = QGraphicsOpacityEffect()
effect.setOpacity(0.35)
widget.setGraphicsEffect(effect)

# 之后（cheap - GPU compositor）
widget.setWindowOpacity(0.35)  # 立即设置
# 或
anim = QPropertyAnimation(widget, b"windowOpacity")
anim.setDuration(200)
anim.setStartValue(0.0)
anim.setEndValue(1.0)
anim.start()
```

**DropShadowEffect 不可被 setWindowOpacity 替代**，需用 `Elevation` token 收敛参数（详见 §4.6）。

**目标：**
- `QGraphicsOpacityEffect` 滥用 **0 处**（1 → 0，余 `folder_panel.py:451`）
- `QGraphicsDropShadowEffect` 走 token **2 处**（已达成 ✅）

#### 4.10.2 paintEvent 性能

| 反模式 | 现状 | 改为 |
|---|---|---|
| `self.update()` 全量重绘 | `chain_canvas.py` 节点拖动 | `self.update(rect)` 限定重绘区域 |
| `self.repaint()` 同步重绘 | 偶有使用 | 改用 `self.update()` 异步 |
| paintEvent 中 `QPainterPath` 重复构造 | `chain_canvas.py:316` 节点框 | 缓存 `path_cache_key = (width, height, radius)` |
| paintEvent 中 `setRenderHint` 重复设置 | 多个文件 | 抽到 `__init__` 设置一次 |
| paintEvent 中 `setBrush/setPen` 多次切换 | `popup_renderer.py` | 合并同类绘制调用 |
| paintEvent 中字符串拼接 | 多文件 | 提取到 `__init__` 或缓存 |

**lint 工具：** `scripts/audit_paint_perf.py` 检测以下反模式并报告：
* `paintEvent` 中 `self.update()` 无参数
* `paintEvent` 中 `QPainterPath(...)` 构造
* `paintEvent` 中 `setRenderHint` 调用
* `QGraphicsEffect` 使用（非必要场景）

#### 4.10.3 动画系统统一

**现状：**
- `ui/utils/interruptible_animation.py`（44 行）已存在并被 17 文件调用，含 `stop_animation / is_animation_running / stop_named_animations / set_precise_timer`
- `ui/utils/animations.py` 已提供 `fade_in/fade_out/scale_in/slide_in/chain/parallel/cancel_all` + `DisposableAnimation`/`DisposableWidget`（**语义封装已存在，但 0 个业务组件实际使用**）
- `ui/launcher_popup/popup_window_animation.py`（133 行）已实现 `PopupWindowAnimationMixin`
- `ui/config_window/chain_dialog_close_animation.py`（104 行）已实现 ChainDialog 关闭动画
- `QPropertyAnimation` 全项目 60 次（18 个文件），`audit_animation_lifecycle.py` 检出 5 文件缺乏配对 `stop/deleteLater`

**职责分层（明确分工）：**
```
ui/utils/interruptible_animation.py    # 基础设施：停止/查询/计时（已有，不重写）
        ↑
ui/utils/animations.py                # 语义接口：fade_in / fade_out / scale_in / slide_in（新增）
        ↑
各组件 Mixin                            # 业务用法：PopupWindowAnimationMixin / ChainDialogCloseAnimation
```

**统一接口（`ui/utils/animations.py`，委托 interruptible_animation）：**
```python
from ui.utils.interruptible_animation import stop_named_animations, is_animation_running
from ui.utils.motion import DURATION_NORMAL_MS, EASE_STANDARD

def fade_in(widget, duration_ms=DURATION_NORMAL_MS, easing=EASE_STANDARD) -> QPropertyAnimation:
    """设置 windowOpacity 0→1，动画结束自动清理。"""
    ...

def fade_out(widget, duration_ms=DURATION_NORMAL_MS, easing=EASE_STANDARD) -> QPropertyAnimation:
    """设置 windowOpacity 1→0，finished 时 widget.hide()。"""
    ...

def scale_in(widget, from_scale=0.95, to_scale=1.0, duration_ms=DURATION_NORMAL_MS) -> QPropertyAnimation:
    """缩放从 0.95→1.0，配合 fade_in。"""
    ...

def slide_in(widget, direction="up", duration_ms=DURATION_NORMAL_MS) -> QPropertyAnimation:
    """从指定方向滑入。"""
    ...

def chain(*animations) -> QSequentialAnimationGroup: ...
def parallel(*animations) -> QParallelAnimationGroup: ...
def cancel_all(widget) -> None:
    """调用 interruptible_animation.stop_named_animations(widget, ...) 取消 widget 上所有动画。"""
    ...
```

**关键规则：**
* widget 销毁时**必须**调用 `cancel_all(widget)`，防止悬空动画引用
* 同一 widget 上同时只能有 1 个动画（自动取消上一个，**委托 `stop_named_animations`**）
* 动画时长默认从 `motion.DURATION_*` 取，**禁止硬编码**
* `animations.py` **不重新发明停止逻辑**，全部委托 `interruptible_animation` 已实现的工具

**改造清单：**
| 现状 | 位置 | 改为 |
|---|---|---|
| 自定义 `step` 函数 + 多个 `QTimer` | `chain_dialog_close_animation.py` | 用 `chain()` + `parallel()` |
| 散落的 `QPropertyAnimation` 实例化 | 18 个文件，60 处 | **保留**实例化（业务属性不同），但**生命周期管理**全部走 `cancel_all` |
| `QTimer.singleShot` 替代动画 | 散落多文件 | 改为 `QPropertyAnimation`（由 `audit_timer_leak.py` 强制） |

#### 4.10.4 毛玻璃管线优化

**文件：** `ui/launcher_popup/glass_background.py`（**实测 1307 行**，不是 1212 行）

**现状（实测）：**
* `TARGET_FPS = 20`（纯 Python PIL 模糊受限于此）
* `BUFFER_COUNT = 3`（三缓冲）
* 200% DPI 4K 屏上物理像素 ~2.5M，可能跌至 8-12 FPS
* 当前已使用 `GaussianBlur(radius=blur_radius/2.0)` 两次（已 downsample 一次）

**优化方案：**

| 改动 | 影响 |
|---|---|
| 物理像素 > 2.5M 时 downsample 0.25 → 0.20 | FPS 从 12 提升到 18+（需 S0 基线验证） |
| `BUFFER_COUNT = 3 → 4`（四缓冲） | 减少 frame tearing |
| `GaussianBlur` 改为 `ImageFilter.BoxBlur` 预降采样 | 提速 30%（轻微模糊度损失，玻璃效果用户感知不到） |
| `glass_buffer.py` 拆出独立文件 | 维护性（环形缓冲 + 锁） |
| `glass_pipeline.py` 拆出独立文件 | 维护性（worker + 帧生产） |
| `glass_background.py` 拆为 Qt 集成层 | 仅保留 draw() + paintEvent 调度 |
| 缓存 `cover` pixmap 跨帧 | 减少重复计算 |

**拆分边界（实测代码结构）：**
- L1-300：常量 / 配置 / 类型定义
- L300-700：worker 线程 / 帧生产 / GaussianBlur
- L700-1211：buffer 管理（`_buffers`、`_next_generation`、publish 逻辑）
- **L1212 `def draw(self, painter) -> bool:` 起点**——Qt 渲染层
- L1212-1307：draw / paintEvent 调用

**验收：**
* 200% DPI 4K 屏 ≥ 18 FPS（需 S0 基线确认实际基线）
* 100% DPI 1080p 屏 ≥ 25 FPS
* 内存峰值 ≤ +5%

#### 4.10.5 缓存策略

| 缓存对象 | 现状 | 改进 |
|---|---|---|
| `icon_grid` 缩略图 | 每次 `pixmap.scaled()` | LRU 缓存 200 项，按 (size, hash) key |
| `chain_canvas` 节点 `QPainterPath` | 每次 paintEvent 构造 | 缓存按 (width, height, radius) |
| `popup_renderer` 背景路径 | 已有 `_cached_bg_path` | OK，保留 |
| `glass_background` 背景帧 | 已有三缓冲 | 升级四缓冲 |
| `default_icon_renderer` 默认图标 | 每次绘制生成 | LRU 缓存 50 项 |
| 字体 `QFontMetrics` | 多处 `fontMetrics()` 调用 | 缓存到 `self._fm` |

**统一 LRU 装饰器：** `ui/utils/lru_cache.py`
```python
@pixmap_cache(maxsize=200, key=lambda size, h: (size, h))
def render_thumbnail(path, size, hash_): ...
```

#### 4.10.6 资源释放与生命周期

**问题：** Animation、GraphicsEffect、Worker、QPixmap 缓存、Timer 在 widget 关闭时未及时释放，导致内存泄漏和"动画残影"。

**Owner-Disposable 模式（基于 `interruptible_animation.py` 已有的工具，**不重新发明停止逻辑**）：**

```python
from ui.utils.interruptible_animation import stop_named_animations

class DisposableAnimation(QPropertyAnimation):
    """包装 QPropertyAnimation，在启动时自动取消 owner 上一个动画。"""
    def __init__(self, target, prop, parent=None):
        super().__init__(target, prop, parent)
        self._owner = weakref.ref(target)
    
    def start(self):
        owner = self._owner()
        if owner:
            # 委托给 interruptible_animation 已有逻辑
            stop_named_animations(owner, "_current_anim")
            owner._current_anim = self
        super().start()

class DisposableWidget(QWidget):
    """基类：在 hideEvent/closeEvent 中自动清理所有动画/worker/缓存。"""
    def __init__(self, ...):
        self._current_anim = None
        self._disposables = []
    
    def add_disposable(self, d):
        self._disposables.append(d)
    
    def hideEvent(self, event):
        # 1. 取消所有动画（委托 interruptible_animation）
        stop_named_animations(self, "_current_anim", *self._animation_names())
        # 2. 释放其他资源
        for d in self._disposables:
            d.dispose()
        self._disposables.clear()
        super().hideEvent(event)
    
    def closeEvent(self, event):
        self.hideEvent(event)
        super().closeEvent(event)
    
    def _animation_names(self) -> tuple[str, ...]:
        """子类重写，返回要清理的动画属性名。"""
        return ()
```

**应用范围：**
* `ui/launcher_popup/popup_window.py`（聚合 widget，14 个 mixin）—— `_animation_names` 返回 `("hide_anim_group", "anim_group", "reveal_anim", "opacity_anim")`
* `ui/config_window/chain_canvas.py`（节点拖拽）
* `ui/launcher_popup/glass_background.py`（背景 worker）
* 所有自定义 `QPropertyAnimation`（60 处）

**与 `interruptible_animation.py` 的关系：**
- **不重写停止逻辑**：所有停止/查询操作都委托给 `stop_named_animations` / `is_animation_running`
- **DisposableAnimation 包装**只是把"取消上一个 + 设置当前"两步组合为 `start()` 的副作用
- **DisposableWidget** 把 `hideEvent` 的清理逻辑固化到基类，子类只需声明 `_animation_names`

#### 4.10.7 启动性能

| 场景 | 现状 | 优化 |
|---|---|---|
| 主配置窗口首次显示 | 同步初始化所有图标 + token + 缩略图 | 延迟加载：显示窗口后用 worker 加载 |
| 启动器弹窗首次 paintEvent | 同步启动毛玻璃 worker | paintEvent 显示占位背景，worker ready 后无缝切换 |
| 设置页面切换 | 同步构造所有控件 | 保留已构造页面；首次访问时 lazy load |
| 字体数据库初始化 | 同步 | splash 阶段预热 `QFontDatabase` |
| 图标库加载 | 同步遍历目录 | worker 化 |

**具体改动：**

| 文件 | 改动 |
|---|---|
| `ui/config_window/main_window.py` | 启动时仅初始化骨架（侧栏 + 标题栏 + 占位内容区），实际页面在切到对应 tab 时构造 |
| `ui/config_window/icon_grid.py` | 缩略图 worker 化；首次显示用占位符 |
| `ui/launcher_popup/popup_window.py` | paintEvent 期间如 worker 未就绪显示纯色占位背景 |
| `ui/welcome_guide.py` | 表情粒子动画 worker 化 |

**目标：**
* 主配置窗口"显示第一帧" ≤ 200ms（从 `__init__` 结束到 `paintEvent` 完成）
* 启动器弹窗"显示第一帧" ≤ 50ms
* 启动器弹窗"毛玻璃稳定" ≤ 500ms（期间占位背景渐变到毛玻璃）

#### 4.10.8 高 DPI 适配

| 场景 | 现状 | 改进 |
|---|---|---|
| 4K 屏 200% DPI 毛玻璃 | FPS 跌至 8-12 | §4.10.4 解决 |
| 高 DPI 下 1px 边框发胖 | 视觉 | §3.1 pixel_snap 解决 |
| 高 DPI 下 QPixmap 模糊 | 偶有 | 所有 `QPixmap` 加载时 `setDevicePixelRatio(self.devicePixelRatio())` |
| 高 DPI 下图标模糊 | 偶有 | 强制 `QIcon` 使用 `@2x` `@3x` 资源 |

**lint 工具：** `scripts/audit_dpi_handling.py` 检测 `QPixmap` 缺 `setDevicePixelRatio` 的情况。

#### 4.10.9 性能基线与持续监控

**新增 `tools/perf_bench.py`：** 一键运行性能基准测试，输出报告。

**测试场景：**
1. 启动器弹窗冷启动 → 测量首帧时间、稳态 FPS、内存峰值
2. 启动器弹窗主题切换 → 测量切换耗时、残影检测
3. 动作链编辑器节点拖拽 → 测量拖动 FPS、CPU 占用
4. 设置面板页面切换 → 测量切换耗时
5. 配置窗口打开到可交互 → 测量端到端延迟
6. 毛玻璃背景 60s 持续运行 → 测量 FPS 稳定性、内存增长

**输出格式：**
```json
{
    "scenarios": {
        "popup_cold_start": {
            "first_frame_ms": 12.5,
            "fps_avg": 22.3,
            "fps_p99": 18.0,
            "memory_peak_mb": 145.2
        },
        ...
    },
    "regressions": [],
    "baseline": "1.6.3.6"
}
```

**CI 集成：** 每次 PR 跑 `perf_bench.py`，任何指标回退 > 5% 报警（不阻断）；1.7.0 release 前必须 0 回退。

#### 4.10.10 性能反模式 lint

**新增 5 个性能 lint：**

| 脚本 | 检查 | 阻断 |
|---|---|---|
| `audit_graphics_effect.py` | `QGraphicsEffect` 使用（非必要场景） | 警告 |
| `audit_paint_perf.py` | paintEvent 中 `update()` 无参数、`QPainterPath` 构造等 | 警告 |
| `audit_animation_lifecycle.py` | `QPropertyAnimation.start()` 缺配对 `stop()` / `deleteLater()` | 警告 |
| `audit_timer_leak.py` | `QTimer.singleShot` 替代动画（应走 animations.py） | 警告 |
| `audit_pixmap_no_dpi.py` | `QPixmap` 缺 `setDevicePixelRatio` | 警告 |

**lint 升级路径：** S1-S6 阶段为警告（积累案例），S8 灰度前升级为 blocking。

### 4.11 Lint 升级为 Blocking

完成 4.1–4.10 改造后，10 个 audit 脚本（5 个样式 + 5 个性能）升级为强制门禁：

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: audit-grid
      entry: python scripts/audit_grid_violations.py
      pass_filenames: false
      always_run: true
    - id: audit-hardcoded-colors
      entry: python scripts/audit_hardcoded_colors.py --max=2
    - id: audit-paint-snap
      entry: python scripts/audit_paint_snap.py
    - id: audit-qss-radius
      entry: python scripts/audit_qss_radius.py
    - id: audit-font-consistency
      entry: python scripts/audit_font_consistency.py
    - id: audit-graphics-effect
      entry: python scripts/audit_graphics_effect.py
    - id: audit-paint-perf
      entry: python scripts/audit_paint_perf.py
    - id: audit-animation-lifecycle
      entry: python scripts/audit_animation_lifecycle.py
    - id: audit-timer-leak
      entry: python scripts/audit_timer_leak.py
    - id: audit-pixmap-no-dpi
      entry: python scripts/audit_pixmap_no_dpi.py
```

---

## 五、L3 视觉精致化 + 流畅度提升

> 本节是**用户能感知到的所有变化**。每项都用 Feature Flag 控制，灰度发布，必要时可秒级回滚。**所有变化必须正向：更精致、更流畅、更顺滑；不允许更糊、更卡、更抖、更慢**。

### 5.1 像素对齐启用

* **改动：** L2-4.2 完成的 snap + cosmetic 在用户机器上激活。
* **视觉变化：** 125%+ DPI 下 1px 边框更细更清晰。**显著精致度提升**。
* **流畅度变化：** 圆角边缘抗锯齿更准确，肉眼无掉帧。
* **Feature Flag：** `Settings.advanced.experimental_pixel_snap`（默认 False）
* **回滚：** 关 flag 即可。

### 5.2 Focus Ring 启用

* **改动：** `ui/styles/style.py:1120-1170` 追加 `:focus` 伪类规则。
* **视觉变化：** 键盘 Tab 导航时所有交互控件有 1px 圆角高亮环。**专业感显著提升**。
* **流畅度变化：** focus 切换走 80ms 颜色过渡，无瞬切。
* **Feature Flag：** `Settings.advanced.show_focus_ring`（默认 True）
* **回滚：** 关 flag 即可。

### 5.3 微动效启用

* **改动：** 给 2 个高频按钮（命令面板主按钮、动作链添加按钮）加 `:pressed` 状态 80ms 颜色过渡。
* **视觉变化：** 按钮按下有细腻反馈。**专业感提升**。
* **流畅度变化：** 走 `motion.EASE_STANDARD` 缓动曲线，符合人体视觉预期。
* **Feature Flag：** `Settings.advanced.micro_animations`（默认 True）
* **回滚：** 关 flag 即可。

### 5.4 阴影升级（Win11）

* **改动：** **2 处** `QGraphicsDropShadowEffect`（`folder_panel.py:224`、`icon_grid.py:1178`）参数按 `Elevation` token 调整（Blur 12→32, Offset 2→12）。**注：原文档"14 处"含 12 处 `QGraphicsOpacityEffect`，后者在 §5.6 弹窗动画 / §4.10.1 渲染热路径中处理，不在本节。**
* **视觉变化：** 阴影更柔和、层次更明显。**Win11 用户显著精致度提升**；Win10 用户无变化（自动降级到 `elev_1`）。
* **流畅度变化：** `Elevation` token 统一参数后，**Blit 操作走 Qt 渲染管线，主线程 CPU 占用降低 10-20%**（**注意：原文档"30-50%"是估算，无基线支撑**；S0 perf_bench 必须先采基线）。
* **Feature Flag：** `Settings.advanced.elevation_profile = "auto" | "low" | "high"`（默认 auto）
* **回滚：** 设为 "low" 即可（降级到 elev_1）。

> ⚠️ **技术澄清：** `QGraphicsDropShadowEffect` 不可被 `widget.setWindowOpacity()` 替代——前者是离屏渲染 + 高斯模糊，后者仅是透明度合成。本节只动阴影参数，**不做 effect 类型替换**。

### 5.5 玻璃管线 200% DPI 自适应

* **改动：** `glass_background.py` 在物理像素 > 2.5M 时 downsample 0.25→0.20，BUFFER 3→4。
* **视觉变化：** 4K 屏 200% DPI 下玻璃效果流畅（≥ 20FPS）。**性能提升**。
* **Feature Flag：** 不需要（纯性能优化）

### 5.6 弹窗出现/消失动画统一

* **改动：** 弹窗、菜单、Toast 全部走 `animations.py` 的 `fade_in` / `fade_out` / `scale_in` / `slide_in` 统一接口。
* **视觉变化：** 弹窗出现/消失有 200-320ms 的 ease 过渡，不再"瞬切"。**显著精致度提升**。
* **流畅度变化：** 走 `QPropertyAnimation`，Qt 内部 GPU 加速，60FPS。
* **Feature Flag：** `Settings.advanced.window_animations`（默认 True）
* **回滚：** 关 flag 即可（瞬切模式）。

### 5.7 启动性能优化

* **改动：** 主配置窗口、启动器弹窗的"冷启动"耗时优化——延迟加载、worker 化、占位背景。
* **流畅度变化：** 主配置窗口"显示第一帧" ≤ 200ms；启动器弹窗"显示第一帧" ≤ 50ms。
* **Feature Flag：** 不需要（纯性能优化）

### 5.8 拖拽与滚动流畅度

* **改动：** 动作链节点拖动用局部 `update(rect)` 替代全量重绘；滚动条走 `QPropertyAnimation`。
* **流畅度变化：** 节点拖动 FPS 从 30-40 提升到 55-60。**显著流畅度提升**。
* **Feature Flag：** 不需要（纯性能优化）

### 5.9 残影消除

* **改动：** 暗/亮切换、Dialog 关闭、动画中断时强制 `widget.repaint()` 同步清屏。
* **流畅度变化：** 切换无残影、无撕裂。**视觉一致性提升**。
* **Feature Flag：** 不需要

---

## 六、执行计划

> **重要：** 全部 1.7.0 Sprint 计划**必须先完成 S0 基线采集**才能定时间表。下方时间表是 S0 之后的"基线假设"，实际 Sprint 容量以 S0 输出为准。

### 6.0 S0 — 基线采集与基建（**已完成**）

**周期：** 1 周（Week 0，紧接 1.6.3.6 发布后）

**目标：** 把 §一"现状审计"基线、§八"验收门禁"基线、§五 L3 性能指标基线全部落实。

| 工作项 | 状态 | 产物 |
|---|---|---|
| 视觉基线生成 | ✅ 已完成 | `docs/visual_baseline/` 含 19 组件 × 2 主题 = 38 PNG + `report.json` |
| 视觉基线对比 | ✅ 工具就绪 | `tools/visual_diff.py`（Δ > 0.5% block） |
| 性能基准采集 | ✅ 已完成 | `docs/quality/perf_baseline_1.6.3.6.json`（含弹窗首帧等 6 场景） |
| 6 个样式 lint | ✅ 全部就位 | 违规清单见本文档审计基线表 |
| 5 个性能 lint | ⚠️ 脚本存在 | `audit_graphics_effect.py` 有 `--strict` 参数 bug |
| 文档基线 | ⚠️ 部分完成 | `perf_baseline_1.6.3.6.json` ✅，`visual_baseline_1.6.3.6.md` 缺失 |
| `interruptible_animation.py` API 文档 | ❌ 未完成 | `docs/ui/interruptible_animation.md` 未生成 |

### 6.1 时间表（S0 之后）

| Sprint | 周期 | 工作内容 | 用户视角变化 |
|---|---|---|---|
| **S0** | Week 0 | **基线采集**（已完成：视觉基线 38 PNG + perf_baseline.json + 12 audit 脚本） | 无 |
| **S1** | Week 1 | L1 基建（**已完成 5/7**：design_tokens/pixel_snap/motion/standard_widgets + 12 audit 脚本；缺 ADR-001/002/003 文档） | 无 |
| **S2** | Week 2-3 | L2-4.1 硬编码色值迁移（**193 处 / 30 文件**） | 无 |
| **S3** | Week 4 | L2-4.2 paintEvent 标准化（**31 个**） | 无 |
| **S4** | Week 5-6 | L2-4.4 栅格（**217 处 / 42 文件**）+ 4.5 QSS 圆角（**118 处 / 28 文件**）（注：§4.3 字体统一已 0 违规完成） | 无 |
| **S5** | Week 7 | L2-4.6 阴影统一（**2 处 DropShadow 已走 token，确认**）+ 4.7 巨型文件拆分（17 个文件）+ 4.10.4 毛玻璃管线 | 阴影精致度提升（Win11） |
| **S6** | Week 8 | L2-4.8 死代码 + 4.10.1 渲染热路径（**1 处 OpacityEffect 剩余**：`folder_panel.py:451`）+ 4.10.3 动画系统统一 + 4.10.6 Owner-Disposable | 无 |
| **S7** | Week 9 | L2-4.10.5 缓存策略 + 4.10.7 启动性能 + 4.10.8 高 DPI 适配 | **流畅度显著提升** |
| **S8** | Week 10 | L2-4.11 Lint 升级为 Blocking + L3 全量灰度 | **全量精致 + 流畅** |
| **S9** | Week 11 | 灰度 + 验收 + release_gate | 1.7.0 发布 |

> **S2-S4 时间修正：** 原 1 周 / 1 周 / 1 周的安排**严重低估**。S2 (193 QColor 迁移) 实际需要 2 周；S4 (217 sp + 118 border:none) 实际需要 2 周；§4.3 字体统一已 0 违规完成，S4 不再包含字体。如不延长 Sprint，需**降级目标**（如只完成 70% 重点文件，其余延后到 1.7.1）。

### 6.2 拆分优先级（S5 选做清单）

**P0（必做）：**
* `icon_grid.py`（2560 行）拆 2+ 文件
* `chain_canvas.py`（2559 行）拆 3 文件
* `style.py`（1993 行）拆 3 文件

**P1（推荐做）：**
* `chain_canvas.py`、`icon_grid.py`、`command_dialog.py`
* `settings_panel.py`

**P2（可选）：**
* 其他大文件按需

### 6.3 实施纪律

* **小步提交**：每个 token 迁移点一个 commit，便于回滚
* **保持主分支绿**：任何 commit 后 `pytest tests/ui/` 全过
* **可视化验证**：每个 Sprint 末尾跑 12 张基线对比，Δ > 0.5% 立即排查

---

## 七、风险控制

| 风险 | 等级 | 控制 |
|---|---|---|
| Token 替换后某 Dialog 颜色变了 | 中 | 视觉基线对比 + 立即排查 |
| 字体栈变更触发 Qt 字体缓存重建 | 低 | 预热 `QFontDatabase` 在 splash 阶段 |
| 阴影 Blur 增大拖慢低端机 | 中 | Win10 自动降级；Feature Flag 灰度 |
| 玻璃管线 200% DPI FPS 跌至 8 | 中 | 自适应 downsample |
| 巨型文件拆分后 import 循环 | 中 | 拆分前跑 mypy + 架构门禁；拆分后跑全量测试 |
| Lint 升级为 blocking 后旧违规清不干净 | 中 | Lint 设 `--max=N` 阈值，逐步降为 0 |
| **L3 启用后用户觉得某处"变味"了** | **中** | **Feature Flag 秒级回滚 + 12 张基线守护** |

### 回滚策略

```bash
# 单 Sprint 回滚
git revert <sprint-merge-sha> --no-edit
git push origin main
tools/visual_diff.py --baseline 1.6.3.6

# 1.7.0 整体回滚（应急）
git tag v1.6.3.7-fallback
git checkout v1.6.3.6 -- ui/
```

---

## 八、验收门禁

> **§8.1 全部阈值依赖 S0 阶段（§6.0）产出的基线**。S0 未完成时，所有"0 违规"门禁无法判断（无基线即无 regression）。

### 8.1 自动门禁（CI 强制）

| # | 检查 | 工具 | 阈值 | S0 前置 |
|---|---|---|---|---|
| 1 | **18 张**视觉基线无差异 | `tools/visual_diff.py` | Δ ≤ 0.5% 像素（L3 启用后允许 Δ ≤ 1%） | **是**（生成 18 张基线 PNG） |
| 2 | 非 4 倍数 `sp()` 调用 | `audit_grid_violations.py` | **0**（白名单除外） | **是**（基线 217 处） |
| 3 | 硬编码 `QColor(...)` | `audit_hardcoded_colors.py` | **0**（token 文件除外） | **是**（基线 193 处） |
| 4 | `paintEvent` 未 snap | `audit_paint_snap.py` | **0** | **是**（基线 31 个 paintEvent） |
| 5 | `border: none` 缺 `border-radius: 0` | `audit_qss_radius.py` | **0** | **是**（基线 118 处） |
| 6 | 内联 `font-size: N px` | `audit_font_consistency.py` | **0** | **是**（基线已清，0 处） |
| 7 | `setCosmetic(True)` 覆盖率 | `audit_paint_snap.py` | **100%** | **是**（基线 0/31） |
| 8 | `QGraphicsOpacityEffect` 滥用 | `audit_graphics_effect.py` | **0**（1 → 0） | **是** |
| 9 | `QGraphicsDropShadowEffect` 走 token | `audit_graphics_effect.py` | **2 → 2**（已走 token，确认） | **是** |
| 10 | `paintEvent` 性能反模式 | `audit_paint_perf.py` | **0** | **是** |
| 11 | 动画生命周期管理 | `audit_animation_lifecycle.py` | **0** | **是** |
| 12 | `QTimer.singleShot` 替代动画 | `audit_timer_leak.py` | **0** | **是** |
| 13 | `QPixmap` 缺 DPI 设置 | `audit_pixmap_no_dpi.py` | **0** | **是** |
| 14 | mypy 0 error | `mypy` | 保持 | 否 |
| 15 | release_gate | `release_gate.py` | 全过 | 否 |
| 16 | 暗色/亮色切换 0 残影 | 手动 | 必查 | 否 |
| 17 | **性能基线无回退** | `tools/perf_bench.py` | **任何指标回退 > 5% 报警** | **是**（生成 perf_baseline_1.6.3.6.json） |

### 8.2 人工验收

* [ ] **18 张**视觉基线逐张对比，**用户视角无变差**（原 12 张已扩展）
* [ ] 100% / 125% / 150% / 200% DPI × 暗/亮 = 8 张
* [ ] Win10 22H2 + Win11 23H2 物理机各 1 轮
* [ ] 键盘 Tab 焦点环清晰可见
* [ ] 鼠标 hover/press 反馈细腻无延迟
* [ ] **3 人内测 0 视觉投诉**（"哪里变难看了吗"）
* [ ] **3 人内测 0 流畅度投诉**（"哪里变卡了吗"）
* [ ] 弹窗首帧 / 稳态 FPS / 拖拽 FPS 全部满足目标（**目标值以 S0 产出的 perf_baseline_1.6.3.6.json 为准**）
* [ ] 启动器弹窗主题切换 ≤ 200ms
* [ ] 配置窗口打开到可交互 ≤ 350ms
* [ ] 0 残影（暗/亮切换、Dialog 关闭、动画中断）
* [ ] 内存占用峰值 ≤ +5%（相对 S0 基线）

### 8.3 监控指标

| 指标 | 1.6.3.6 基线（实测） | 1.7.0 目标 | 红线 |
|---|---|---:|---:|---|
| 启动器弹窗首帧（avg） | 57ms | ≤ 16ms | > 20ms 报警 |
| 启动器弹窗稳态 FPS | 12-20 | ≥ 30 | < 20 报警 |
| 配置窗口打开到可交互 | 42ms（avg） | ≤ 350ms | > 500ms 报警 |
| 设置面板切换 | 61ms（avg） | ≤ 200ms | > 300ms 报警 |
| 节点拖动耗时 | 15ms（avg） | ≥ 55 FPS | < 50 FPS 报警 |
| 命令面板查询响应 | TBD | ≤ 50ms | > 100ms 报警 |
| 主题切换（暗/亮） | 0.1ms（avg） | ≤ 200ms | > 300ms 报警 |
| 弹窗出现/消失动画 | TBD | 200-320ms ease | 不可瞬切 |
| 暗色/亮色切换残影 | 0 | 0 | > 0 报警 |
| 动画中断残影 | 0 | 0 | > 0 报警 |
| Dialog 关闭残影 | 0 | 0 | > 0 报警 |
| **视觉投诉工单** | TBD | < 3 | **≥ 5 立即回滚** |
| **流畅度投诉工单** | TBD | < 3 | **≥ 5 立即回滚** |
| 崩溃率（UI 相关） | TBD | < 0.05% | > 0.1% 报警 |
| 内存占用峰值 | TBD | ≤ +5% | > +10% 报警 |
| 200% DPI 下 1px 边框 | 不清晰 | 清晰 | 必须 |
| 200% DPI 下毛玻璃 FPS | 8-12 | ≥ 18 | < 15 报警 |
| 键盘 Tab 焦点环 | 不可见 | 清晰 | 必须 |

---

## 九、配套需要 Settings 增加的字段

* `Settings.advanced.show_focus_ring: bool` —— 默认 True
* `Settings.advanced.experimental_pixel_snap: bool` —— 默认 False（灰度期）
* `Settings.motion_scale: float` —— 动效缩放因子（0.5–2.0），用于无障碍偏好；**所有 `DURATION_*` 实际值 = `DURATION_* × motion_scale`**
* `Settings.advanced.elevation_profile: "auto" | "low" | "high"` —— 阴影强度（默认 auto）
  - `auto`：Win11 → elev_1/2/3；Win10 → elev_1
  - `low`：所有平台统一 elev_1
  - `high`：Win11 → elev_2/3/4（新增弹窗层）
* `Settings.advanced.micro_animations: bool` —— 默认 True（按钮 :pressed 80ms 颜色过渡）
* `Settings.advanced.window_animations: bool` —— 弹窗出现/消失动画，默认 True（关闭则瞬切）
* `Settings.advanced.glass_quality: "auto" | "low" | "high"` —— 毛玻璃质量
  - `auto`：物理像素 > 2.5M → BUFFER 4 + downsample 0.20；否则 BUFFER 3 + 0.25
  - `low`：强制 BUFFER 3 + downsample 0.15
  - `high`：强制 BUFFER 4 + downsample 0.25
* `Settings.advanced.low_end_mode: bool` —— 低端机模式（关闭所有动画 + 降级阴影 + 降级毛玻璃），默认 False

**注意：** §5.6 的 `window_animations` Feature Flag 在关闭时意味着**完全瞬切**（无 fade/slide），与当前 `popup_window_animation.py` 已有的 fade-in 行为冲突——需修改 mixin 让 `window_animations=False` 时跳过 `QPropertyAnimation` 启动。

---

## 十、与现有文档的关系

| 文档 | 关系 |
|---|---|
| `架构优化.md` v2.1 | 主架构计划，本计划是 W6（UI）的详细执行设计 |
| `OPTIMIZATION_PLAN_1.7.0.md` | 1.7.0 时间表（Week 1–8）。**本计划新增 S0（Week 0 基线采集），S2-S4 实际需要 2 周（原 1 周）**——需与 `OPTIMIZATION_PLAN_1.7.0.md` 协商重排 |
| `QUALITY_AUDIT_1.6.2.0.md` | 历史质量基线。本计划新增"视觉基线"维度（18 张 PNG） |
| `CHANGELOG.md` 1.7.0 节 | 用户可见变化：像素级 1px 边框更清晰、键盘焦点环可见、阴影更柔和（Win11）、字体渲染质量提升（Win11） |
| `docs/UI_GLOBAL_SCALE_PLAN.md` | 已存在的 UI 全局缩放计划；本计划在 §1.1-1.4 与其有部分重叠（间距/字号），需消歧：UI_GLOBAL_SCALE_PLAN 负责运行时缩放，本计划负责设计 token 收敛 |
| `ui/utils/interruptible_animation.py`（代码） | 已被 17 文件调用的动画基础设施；**本计划 §4.10.3 / §4.10.6 的 animations.py / DisposableWidget 在其之上封装，不重写停止逻辑** |

---

## 十一、术语表

* **精致度 (Refinement)：** 用户使用产品时感知到的"专业感"，包含像素、节奏、配色、字体、反馈、深度、性能 7 个维度。
* **Token：** 命名语义化值（如 `surface("bg_dialog")`），不直接对应颜色。
* **Visual Baseline：** 视觉基线 PNG，用于回归检测。**1.7.0 共 18 张**（原 12 张，扩展 6 张）。
* **Lint：** 静态扫描工具，违规阻断合并。
* **Feature Flag：** 用户可关闭的实验性功能开关。
* **ADR：** Architecture Decision Record，关键架构决策记录。
* **Sprint 0 (S0)：** 1.7.0 实施前的**必做前置**——基线采集（视觉 + 性能 + lint），无 S0 输出的 Sprint 计划不成立。
* **`interruptible_animation`：** 已有动画基础设施（44 行 / 17 文件调用），本计划 `animations.py` 与 `DisposableWidget` **委托** 其停止/查询逻辑，不重写。
* **`QGraphicsOpacityEffect` vs `QGraphicsDropShadowEffect`：** 两个完全不同的优化方向——前者可被 `setWindowOpacity()` 替代（17 处 → 0），后者只能参数收敛（2 处走 `Elevation` token），**不可互换**。
* **Disposable Pattern：** widget 销毁时自动清理动画/worker/缓存的模式；通过委托 `interruptible_animation` 实现，不重新发明停止逻辑。
