"""
单显示器/多显示器/多 DPI 场景下的坐标处理工具。

本项目的 DPI 模型（见 ``qt_compat.setup_high_dpi``）：

- 进程注册为 ``DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2``
- Windows 钩子和 ``GetCursorPos`` 返回物理像素
- Qt High-DPI Scaling 返回设备无关逻辑坐标，并通过
  ``QScreen.devicePixelRatio()`` 暴露每屏缩放比例
- ``QScreen.geometry()`` / ``availableGeometry()`` 因此不能直接和 Win32
  物理坐标比较
- 窗口内部布局使用全局 ``sp()`` 缩放（与显示器 DPI 解耦）

因此该模块负责在 Win32 物理坐标和 Qt 逻辑坐标之间建立每显示器映射。

1. 提供一个**单一权威入口**，把鼠标回调中的物理像素归一化为"项目坐标"
   （本项目里就是物理像素本身）。
2. 解决历史 ``_try_convert_win_physical_to_qt`` 的两个问题：
   - ``screen.devicePixelRatio()`` 恒等于 1.0 导致除法退化（误导维护者）
   - 显示器名匹配脆弱（不同 Qt 版本 ``QScreen.name()`` 返回格式不一致）
3. 提供 fallback 路径，不在边缘场景崩溃。

注意：所有函数**不依赖 QApplication 已创建**——在 QApplication 创建之前调用
``normalize_caret_position`` 会安全地返回原始坐标。
"""

from __future__ import annotations

import ctypes
import logging
import re
from ctypes import wintypes
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 显示器名归一化
# ---------------------------------------------------------------------------

# QScreen.name() 在不同 Qt 版本/PyQt 版本/驱动下可能返回：
#   \\.\DISPLAY1     (Qt 5/6 常见)
#   \\\\.\\DISPLAY1 (Python 字符串字面量后)
#   .\\DISPLAY1     (某些 PyQt5 旧版本)
#   DISPLAY1        (极个别精简 Qt 发行版)
# Windows GetMonitorInfoW 的 szDevice 始终是 \\.\DISPLAYX 形式。
# 归一化为大写、剥离所有反斜杠/点号前缀，仅保留 "DISPLAY<数字>" 部分。
# 注意：回退路径 (``re.sub``) 才会剥离中间的空白。
_DEVICE_NAME_RE = re.compile(r"^\\{1,6}\.?\\?(DISPLAY\d+)$", re.IGNORECASE)


def normalize_device_name(name: str) -> str:
    """把 GDI/Qt 返回的显示器名归一化为 ``DISPLAY<n>`` 形式。

    大小写无关、前缀无关。无法识别时返回空字符串。
    """
    if not name:
        return ""
    cleaned = str(name).strip()
    m = _DEVICE_NAME_RE.match(cleaned)
    if m:
        return m.group(1).upper()
    # 退化路径：尝试剥离所有前导反斜杠/点号（**不**剥离空白，
    # 避免把 "  \\\\ .\\\\DISPLAY1  " 误识别为 DISPLAY1）
    stripped = re.sub(r"^[\\.]+", "", cleaned).upper()
    if stripped.startswith("DISPLAY"):
        return stripped
    return ""


# ---------------------------------------------------------------------------
# Windows API 直接调用
# ---------------------------------------------------------------------------

_MONITOR_DEFAULTTONEAREST = 0x00000002
_MDT_EFFECTIVE_DPI = 0


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MonitorInfoExW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def _query_monitor_at(phys_x: int, phys_y: int) -> tuple | None:
    """调用 Win32 API 拿到指定物理坐标所在显示器的元数据。

    Returns:
        (hmon, rcMonitor.left, rcMonitor.top, rcMonitor.right, device_name,
        physical_dpi_x, physical_dpi_y) 或 None
    """
    try:
        user32 = ctypes.windll.user32
        monitor_from_point = user32.MonitorFromPoint
        monitor_from_point.argtypes = [_Point, wintypes.DWORD]
        monitor_from_point.restype = wintypes.HMONITOR

        get_monitor_info = user32.GetMonitorInfoW
        get_monitor_info.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfoExW)]
        get_monitor_info.restype = wintypes.BOOL

        hmon = monitor_from_point(_Point(int(phys_x), int(phys_y)), _MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None

        info = _MonitorInfoExW()
        info.cbSize = ctypes.sizeof(_MonitorInfoExW)
        if not get_monitor_info(hmon, ctypes.byref(info)):
            return None

        device = normalize_device_name(info.szDevice or "")
        rc = info.rcMonitor

        # 物理 DPI：尝试 GetDpiForMonitor，失败时降级到 96
        dpi_x, dpi_y = 96, 96
        try:
            shcore = ctypes.windll.shcore
            dpi_x_c = ctypes.c_uint()
            dpi_y_c = ctypes.c_uint()
            shcore.GetDpiForMonitor(hmon, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x_c), ctypes.byref(dpi_y_c))
            if dpi_x_c.value > 0:
                dpi_x = int(dpi_x_c.value)
            if dpi_y_c.value > 0:
                dpi_y = int(dpi_y_c.value)
        except (OSError, AttributeError) as exc:
            logger.debug("GetDpiForMonitor 不可用，使用默认 96 DPI: %s", exc)

        return (
            int(hmon),
            int(rc.left),
            int(rc.top),
            int(rc.right),
            device,
            dpi_x,
            dpi_y,
        )
    except (OSError, AttributeError) as exc:
        logger.debug("查询显示器元数据失败: %s", exc, exc_info=True)
        return None


def get_monitor_physical_dpi(phys_x: int, phys_y: int) -> tuple[int, int]:
    """返回指定物理坐标所在显示器的物理 DPI (dpi_x, dpi_y)。

    失败时返回 ``(96, 96)``。该函数绕过 Qt 的 ``devicePixelRatio``，
    直接读 Windows 真实硬件 DPI——适用于多 DPI 混合显示器场景。
    """
    meta = _query_monitor_at(int(phys_x), int(phys_y))
    if not meta:
        return (96, 96)
    return (meta[5], meta[6])


def get_monitor_device_name(phys_x: int, phys_y: int) -> str:
    """返回指定物理坐标所在显示器的归一化设备名（``DISPLAY<n>``）。

    失败时返回空字符串。
    """
    meta = _query_monitor_at(int(phys_x), int(phys_y))
    if not meta:
        return ""
    return str(meta[4])


# ---------------------------------------------------------------------------
# QScreen 匹配
# ---------------------------------------------------------------------------


def _screen_display_name(screen: Any) -> str:
    """从 QScreen 提取归一化的 ``DISPLAY<n>`` 名称。"""
    try:
        return normalize_device_name(screen.name() or "")
    except (AttributeError, RuntimeError):
        return ""


def _safe_geometry(screen: Any, attr: str = "geometry"):
    """安全读取 QScreen 的 geometry/availableGeometry，失败返回 None。"""
    try:
        return getattr(screen, attr)()
    except (AttributeError, RuntimeError):
        return None


def find_qscreen_by_device(device_name: str, screens: list | None = None) -> Any | None:
    """在给定的 QScreen 列表中按 ``DISPLAY<n>`` 名称匹配。

    Args:
        device_name: 归一化后的名称（如 ``"DISPLAY1"``），空字符串时返回 None
        screens: ``QApplication.screens()`` 列表；为 None 时尝试获取
    """
    target = normalize_device_name(device_name)
    if not target:
        return None

    if screens is None:
        try:
            from qt_compat import QApplication

            screens = QApplication.screens() or []
        except (ImportError, AttributeError, RuntimeError):
            return None

    for s in screens:
        if _screen_display_name(s) == target:
            return s
    return None


def find_qscreen_containing_point(qt_x: int, qt_y: int, screens: list | None = None) -> Any | None:
    """在 ``QApplication.screens()`` 中找到 ``geometry()`` 包含指定 Qt 逻辑点的屏幕。

    若 ``QApplication`` 未创建或全部 API 失败，返回 None。

    若调用方显式传入 ``screens``，则优先用传入列表（``screenAt`` 也按该列表
    内部模拟），便于单测 mock。QApplication 仅在 ``screens is None`` 时使用。
    """
    own_screens = screens is not None
    if not own_screens:
        try:
            from qt_compat import QApplication

            screens = QApplication.screens() or []
        except (ImportError, AttributeError, RuntimeError):
            return None

    if not screens:
        return None

    try:
        from qt_compat import QApplication, QPoint
    except ImportError:
        return None

    pt = QPoint(int(qt_x), int(qt_y))

    def _contains(s):
        try:
            return s.geometry().contains(pt)
        except (AttributeError, RuntimeError):
            return False

    if own_screens:
        for s in screens:
            if _contains(s):
                return s
    else:
        try:
            screen = QApplication.screenAt(pt)
        except (AttributeError, RuntimeError):
            screen = None
        if screen is not None:
            return screen
        # screenAt 失败时的退化：遍历所有屏幕检查 geometry().contains
        for s in screens:
            if _contains(s):
                return s

    # 所有屏幕都未包含目标点 → 退化到 primary screen
    if own_screens:
        return screens[0]
    try:
        return QApplication.primaryScreen()
    except (AttributeError, RuntimeError):
        return None


# ---------------------------------------------------------------------------
# 单一权威入口：归一化鼠标坐标
# ---------------------------------------------------------------------------


def normalize_caret_position(
    phys_x: int,
    phys_y: int,
    screens: list | None = None,
) -> tuple[int, int]:
    """把 Win32 物理像素映射到目标 ``QScreen`` 的 Qt 逻辑坐标。"""
    px = int(phys_x)
    py = int(phys_y)

    if screens is None:
        try:
            from qt_compat import QApplication

            screens = QApplication.screens() or []
        except (ImportError, AttributeError, RuntimeError):
            screens = []
    if not screens:
        return (px, py)

    monitor_meta = _query_monitor_at(px, py)
    target_screen = None
    if monitor_meta:
        target_screen = find_qscreen_by_device(str(monitor_meta[4]), screens=screens)
    if target_screen is None:
        target_screen = find_qscreen_containing_point(px, py, screens=screens)
    if target_screen is None:
        logger.warning(
            "NORMALIZE_COORD_FALLBACK reason=no_qt_screen pos=(%s,%s) -> 返回原始物理坐标",
            px,
            py,
        )
        return (px, py)

    geo = _safe_geometry(target_screen, "geometry")
    if geo is None:
        logger.debug(
            "NORMALIZE_COORD_GEOMETRY_READ_FAILED screen=%s -> 返回原始物理坐标",
            _screen_display_name(target_screen) or "<unnamed>",
        )
        return (px, py)

    if monitor_meta is None and not geo.contains(px, py):
        logger.warning(
            "NORMALIZE_COORD_FALLBACK reason=point_outside_geometry screen=%s pos=(%s,%s)",
            _screen_display_name(target_screen) or "<unnamed>",
            px,
            py,
        )
        return (px, py)

    try:
        dpr = max(1.0, float(target_screen.devicePixelRatio() or 1.0))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        dpr = 1.0
    if dpr <= 1.001:
        return (px, py)

    if monitor_meta:
        physical_left = int(monitor_meta[1])
        physical_top = int(monitor_meta[2])
        physical_right = int(monitor_meta[3])
        physical_bottom = physical_top + round(geo.height() * dpr)
        physical_width = max(1, physical_right - physical_left)
        physical_height = max(1, physical_bottom - physical_top)
        qt_x = geo.x() + round((px - physical_left) * geo.width() / physical_width)
        qt_y = geo.y() + round((py - physical_top) * geo.height() / physical_height)
        return (int(qt_x), int(qt_y))

    logger.warning(
        "NORMALIZE_COORD_FALLBACK reason=no_win_monitor_metadata screen=%s pos=(%s,%s)",
        _screen_display_name(target_screen) or "<unnamed>",
        px,
        py,
    )
    return (px, py)


# ---------------------------------------------------------------------------
# 弹窗定位：选择最佳锚定屏幕
# ---------------------------------------------------------------------------


def _rect_can_contain(rect: Any, width: int, height: int, margin: int) -> bool:
    """``rect`` 的可用宽高是否能容纳指定尺寸（含 margin）。"""
    try:
        return bool(rect.width() - 2 * margin >= width and rect.height() - 2 * margin >= height)
    except (AttributeError, TypeError):
        return False


def _rect_overlap_area(l1, t1, r1, b1, l2, t2, r2, b2) -> int:
    """两个 [l,t,r,b) 半开半闭区间的重叠面积。"""
    ow = max(0, min(r1, r2) - max(l1, l2))
    oh = max(0, min(b1, b2) - max(t1, t2))
    return int(ow * oh)


def pick_best_screen_for_popup(
    phys_x: int,
    phys_y: int,
    popup_width: int,
    popup_height: int,
    screens: list | None = None,
    margin: int = 0,
) -> Any | None:
    """在多屏场景下选择最适合放置弹窗的 QScreen。

    **核心问题**：当鼠标位于多屏交界处时，``QApplication.screenAt(point)``
    可能因为边界归属歧义而返回"错误"的那一块屏幕——尤其当弹窗比目标屏幕
    还大、或者鼠标刚好压线时，弹窗会跨屏显示。

    选择策略（**优先遵循用户视觉直觉**，再考虑物理约束）：

    1. **首选** ``QApplication.screenAt(鼠标位置)``：这正是用户视觉上
       看到的"鼠标所在屏幕"。如果该屏幕能完整容纳弹窗（``availableGeometry``
       减去 ``margin`` 后仍足够），直接返回。
    2. **次选** ``find_qscreen_containing_point``：``screenAt`` 在某些边缘
       场景（如跨屏、虚拟屏幕外）可能返回 None 或错的屏幕；退回
       "``geometry()`` 包含鼠标点" 的屏幕。同样要求能容纳。
    3. **再选**：以上两者都"放不下"时（如弹窗比单屏大），在所有能容纳的
       屏幕中按"中心距离最小"排序选一个；如果有多个都能容纳，按
       ``screenAt`` 命中者优先。
    4. **再降级**：仍找不到能完全容纳的，选**与目标矩形重叠面积最大**的
       屏幕（避免完全脱离用户的视觉焦点）。
    5. 始终返回 ``QScreen`` 对象（绝不返回 None，确保调用方不崩溃）。

    Args:
        phys_x, phys_y: 鼠标物理坐标（与 ``QApplication.screenAt`` 一致）
        popup_width, popup_height: 弹窗的逻辑像素宽高
        screens: 可选显式传入的 ``QApplication.screens()`` 列表（便于单测）
        margin: 弹窗相对屏幕边的安全距离（容纳 DWM 阴影等装饰）

    Returns:
        ``QScreen`` 对象或 None（所有 API 都不可用时）
    """
    popup_width = max(1, int(popup_width)) if popup_width <= 0 else int(popup_width)
    popup_height = max(1, int(popup_height)) if popup_height <= 0 else int(popup_height)
    margin = max(0, int(margin))

    own_screens = screens is not None
    if not own_screens:
        try:
            from qt_compat import QApplication

            screens = QApplication.screens() or []
        except (ImportError, AttributeError, RuntimeError):
            screens = []
    if not screens:
        return None

    try:
        from qt_compat import QApplication, QPoint
    except ImportError:
        return None

    # 目标矩形：以鼠标为中心的弹窗 rect（half-open [l, t, r, b) 区间）
    target_left = int(phys_x) - popup_width // 2
    target_top = int(phys_y) - popup_height // 2
    target_right = target_left + popup_width
    target_bottom = target_top + popup_height
    target_cx = int(phys_x)
    target_cy = int(phys_y)

    # 1. 首选：QApplication.screenAt(鼠标位置)
    primary_candidate = None
    if not own_screens:
        try:
            primary_candidate = QApplication.screenAt(QPoint(int(phys_x), int(phys_y)))
        except (AttributeError, RuntimeError):
            primary_candidate = None
    if primary_candidate is None:
        primary_candidate = find_qscreen_containing_point(int(phys_x), int(phys_y), screens=screens)

    if primary_candidate is not None:
        avail = _safe_geometry(primary_candidate, "availableGeometry")
        if avail is not None and _rect_can_contain(avail, popup_width, popup_height, margin):
            return primary_candidate

    # 2. 退化：找 geometry().contains(point) 的屏幕（screenAt 在边界处可能误判）
    geo_candidate = find_qscreen_containing_point(int(phys_x), int(phys_y), screens=screens)
    if geo_candidate is not None and geo_candidate is not primary_candidate:
        avail = _safe_geometry(geo_candidate, "availableGeometry")
        if avail is not None and _rect_can_contain(avail, popup_width, popup_height, margin):
            return geo_candidate

    # 3. 仍找不到 → 在所有能容纳的屏幕中按"中心距离"选最近；距离相等时
    #    screenAt 命中的优先
    fit_candidates = []
    for s in screens:
        avail = _safe_geometry(s, "availableGeometry")
        if avail is None or not _rect_can_contain(avail, popup_width, popup_height, margin):
            continue
        avail_cx = (avail.left() + avail.right() + 1) // 2
        avail_cy = (avail.top() + avail.bottom() + 1) // 2
        dist_sq = (avail_cx - target_cx) ** 2 + (avail_cy - target_cy) ** 2
        fit_candidates.append((dist_sq, s is primary_candidate, s))

    if fit_candidates:
        # dist_sq 升序，is_primary 降序（True 排前面）→ screenAt 命中者优先
        fit_candidates.sort(key=lambda t: (t[0], not t[1]))
        return fit_candidates[0][2]

    # 4. 没有屏幕能完整容纳 → 选重叠面积最大的屏幕
    best_screen = None
    best_overlap = -1
    for s in screens:
        avail = _safe_geometry(s, "availableGeometry")
        if avail is None:
            continue
        overlap = _rect_overlap_area(
            target_left,
            target_top,
            target_right,
            target_bottom,
            avail.left(),
            avail.top(),
            avail.right() + 1,
            avail.bottom() + 1,
        )
        if overlap > best_overlap:
            best_overlap = overlap
            best_screen = s

    if best_screen is not None:
        return best_screen

    # 5. 兜底：返回主屏
    try:
        return QApplication.primaryScreen()
    except (AttributeError, RuntimeError):
        return screens[0] if screens else None


__all__ = [
    "normalize_device_name",
    "get_monitor_physical_dpi",
    "get_monitor_device_name",
    "find_qscreen_by_device",
    "find_qscreen_containing_point",
    "normalize_caret_position",
    "pick_best_screen_for_popup",
]
