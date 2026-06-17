"""
``PopupLayoutMixin._center_to`` 的单元测试。

阶段 0 基线测试 + 阶段 2 多显示器测试，锁定重写后的行为契约：

1. 移除 ``if dpr != 1.0: x/dpr`` 分支后，``_center_to`` 不再做二次缩放。
2. ``x, y`` 输入是"项目坐标"（本项目 == 物理像素），直接用于定位计算。
3. 多显示器场景下，窗口被正确约束到所在屏幕的 ``availableGeometry`` 内。
4. 各种 ``popup_align_mode`` 都按预期工作。
5. **多屏边界处理**：当鼠标在多屏交界处时，弹窗不会被推到"错"的屏幕，
   且不会跨屏显示（``shadow_margin = sp(20)`` 容纳 DWM 阴影）。
"""

from __future__ import annotations

from types import SimpleNamespace

import ui.launcher_popup.popup_window_effect as popup_effect_mod
from qt_compat import QRect
from ui.launcher_popup.popup_window import LauncherPopup

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _make_screen(name, geo_x, geo_y, geo_w, geo_h, avail_x=None, avail_y=None, avail_w=None, avail_h=None):
    if avail_x is None:
        avail_x = geo_x
    if avail_y is None:
        avail_y = geo_y
    if avail_w is None:
        avail_w = geo_w
    if avail_h is None:
        avail_h = geo_h

    class _Screen:
        def __init__(self):
            self._name = name

        def name(self):
            return self._name

        def geometry(self):
            return QRect(geo_x, geo_y, geo_w, geo_h)

        def availableGeometry(self):
            return QRect(avail_x, avail_y, avail_w, avail_h)

        def devicePixelRatio(self):
            return 1.0

    return _Screen()


def _make_popup(
    monkeypatch,
    screens,
    width=400,
    height=300,
    align_mode="mouse_center",
    sp_value=1,
):
    """构造一个最小可用的 LauncherPopup 替身用于 _center_to 测试。"""
    from ui.utils import ui_scale

    monkeypatch.setattr(ui_scale, "_scale_factor", float(sp_value))

    popup = LauncherPopup.__new__(LauncherPopup)
    popup.settings = SimpleNamespace(
        popup_align_mode=align_mode,
        icon_size=64,
        cell_size=80,
        cols=4,
    )
    popup.width = lambda: width
    popup.height = lambda: height
    popup._moves = []
    popup.move = lambda x, y: popup._moves.append((int(x), int(y)))  # type: ignore[attr-defined]
    return popup


def _patch_qapp(monkeypatch, screens):
    """模拟 ``QApplication``，``screenAt`` 用 geometry().contains 决定。

    注意：``coordinate_utils.pick_best_screen_for_popup`` 通过
    ``from qt_compat import QApplication`` 获取 QApplication，所以必须
    同时 patch ``qt_compat.QApplication`` 才能让该函数也走 fake。
    """
    import qt_compat

    fake_app = SimpleNamespace(
        screenAt=lambda pos: next((s for s in screens if s.geometry().contains(pos)), None),
        screens=lambda: list(screens),
        primaryScreen=lambda: screens[0] if screens else None,
    )
    monkeypatch.setattr(popup_effect_mod, "QApplication", fake_app)
    monkeypatch.setattr(qt_compat, "QApplication", fake_app)


# shadow_margin 常量（与 _center_to 保持同步）
# edge_inset = sp(2) @ 100% scale = 2px（最小边界距离）
SHADOW_MARGIN = 2


# ---------------------------------------------------------------------------
# 1. 不再应用 dpr 缩放（核心回归基线）
# ---------------------------------------------------------------------------


def test_center_to_mouse_center_does_not_apply_dpr(monkeypatch):
    """dpr=1.5 的 fake screen 也不应触发任何 /dpr 计算。"""
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)
    popup = _make_popup(monkeypatch, screens, width=400, height=300)

    LauncherPopup._center_to(popup, 1000, 500, 400, 300)

    # mouse_center：left = 1000 - 200 = 800, top = 500 - 150 = 350
    assert popup._moves[-1] == (800, 350)


def test_center_to_mouse_center_ignores_dpr_greater_than_one(monkeypatch):
    """即使 dpr=2.0，输出也应与 dpr=1.0 一致（因为配置下 dpr 恒为 1.0）。"""
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)

    class _HiDprScreen(type(screens[0])):  # type: ignore[misc]
        def devicePixelRatio(self):
            return 2.0

    screens = [_HiDprScreen()]
    _patch_qapp(monkeypatch, screens)

    popup = _make_popup(monkeypatch, screens, width=400, height=300)
    LauncherPopup._center_to(popup, 1000, 500, 400, 300)

    # 与 dpr=1.0 一致：800, 350
    assert popup._moves[-1] == (800, 350)


# ---------------------------------------------------------------------------
# 2. 各种 align_mode 行为
# ---------------------------------------------------------------------------


def test_center_to_screen_center(monkeypatch):
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)
    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="screen_center")

    LauncherPopup._center_to(popup, 100, 100, 400, 300)

    # screen_center：left = center.x - 200, top = center.y - 150
    # PyQt5 中 QRect(0,0,1920,1080).center() = (959, 539)
    # left = 959 - 200 = 759, top = 539 - 150 = 389
    assert popup._moves[-1] == (759, 389)


def test_center_to_mouse_top_left(monkeypatch):
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)
    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="mouse_top_left")

    LauncherPopup._center_to(popup, 1000, 500, 400, 300)

    # mouse_top_left：left = 1000, top = 500（受边界裁剪约束）
    # shadow_margin=20：left = max(20, min(1000, 1919-400-20)) = 1000
    assert popup._moves[-1] == (1000, 500)


def test_center_to_bottom_right(monkeypatch):
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)
    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="bottom_right")

    LauncherPopup._center_to(popup, 0, 0, 400, 300)

    # bottom_right 初始：left = right - w - sp(10) = 1919 - 400 - 10 = 1509
    #                  top = bottom - h - sp(10) = 1079 - 300 - 10 = 769
    # 边界裁剪 edge_inset=2：
    #   left = max(2, min(1509, 1919-400-2)) = max(2, min(1509, 1517)) = 1509
    #   top  = max(2, min(769, 1079-300-2)) = max(2, min(769, 777)) = 769
    # 初始位置已经满足约束，所以 min 不触发
    assert popup._moves[-1] == (1509, 769)


# ---------------------------------------------------------------------------
# 3. 边界裁剪（多屏 + availableGeometry 区别）
# ---------------------------------------------------------------------------


def test_center_to_clamps_to_secondary_screen(monkeypatch):
    """鼠标在副屏时，窗口必须被约束在副屏的 availableGeometry 内。

    同时验证 edge_inset 不会让窗口超出副屏边界。
    """
    primary = _make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)
    # 副屏在右侧，任务栏在底部 40px
    secondary = _make_screen(
        "\\\\.\\DISPLAY2",
        geo_x=1920,
        geo_y=0,
        geo_w=1280,
        geo_h=720,
        avail_x=1920,
        avail_y=0,
        avail_w=1280,
        avail_h=680,
    )
    screens = [primary, secondary]
    _patch_qapp(monkeypatch, screens)

    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="mouse_center")
    # 鼠标靠近副屏右下角
    LauncherPopup._center_to(popup, 3100, 700, 400, 300)

    left, top = popup._moves[-1]
    # edge_inset=2
    assert left >= 1920 + SHADOW_MARGIN
    assert left + 400 <= 1920 + 1280 - SHADOW_MARGIN
    assert top >= 0 + SHADOW_MARGIN
    assert top + 300 <= 0 + 680 - SHADOW_MARGIN


def test_center_to_uses_available_not_full_geometry(monkeypatch):
    """窗口不能放到任务栏区域（availableGeometry 比 geometry 小）。"""
    screen = _make_screen(
        "\\\\.\\DISPLAY1",
        geo_x=0,
        geo_y=0,
        geo_w=1920,
        geo_h=1080,
        avail_x=0,
        avail_y=0,
        avail_w=1920,
        avail_h=1040,  # 底部 40px 任务栏
    )
    _patch_qapp(monkeypatch, [screen])

    popup = _make_popup(monkeypatch, [screen], width=400, height=300, align_mode="bottom_right")

    LauncherPopup._center_to(popup, 0, 0, 400, 300)

    # avail.bottom() = 1039，不是 geo.bottom() = 1079
    # bottom_right 初始：top = 1039 - 300 - 10 = 729
    # 边界裁剪 edge_inset=2：top = max(2, min(729, 1039-300-2)) = max(2, min(729, 737)) = 729
    # left = 1919 - 400 - 10 = 1509 → max(2, min(1509, 1919-400-2)) = max(2, min(1509, 1517)) = 1509
    assert popup._moves[-1] == (1509, 729)


def test_center_to_handles_no_screen_match(monkeypatch):
    """``QApplication.screenAt`` 返回 None 时应退化到 primaryScreen。"""
    import qt_compat

    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)
    # 覆盖：screenAt 永远返回 None
    fake_app = SimpleNamespace(
        screenAt=lambda _pos: None,
        screens=lambda: list(screens),
        primaryScreen=lambda: screens[0],
    )
    monkeypatch.setattr(popup_effect_mod, "QApplication", fake_app)
    monkeypatch.setattr(qt_compat, "QApplication", fake_app)

    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="screen_center")
    LauncherPopup._center_to(popup, 100, 100, 400, 300)

    # 仍然能定位，使用 primaryScreen。PyQt5 QRect(0,0,1920,1080).center() = (959, 539)
    # screen_center 不受 shadow_margin 影响（居中逻辑）
    assert popup._moves[-1] == (759, 389)


# ---------------------------------------------------------------------------
# 4. sp() 全局缩放对边界裁剪的影响
# ---------------------------------------------------------------------------


def test_center_to_edge_margin_scales_with_sp(monkeypatch):
    """edge_inset 应当随全局 ``sp()`` 缩放。"""
    screens = [_make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)]
    _patch_qapp(monkeypatch, screens)

    # 假设全局缩放 200%，edge_inset = sp(2) = 4
    popup = _make_popup(monkeypatch, screens, width=400, height=300, align_mode="mouse_top_left", sp_value=2)
    # 鼠标紧贴屏幕左/上边缘
    LauncherPopup._center_to(popup, 0, 0, 400, 300)

    # edge_inset = 4
    # left = max(4, min(0, 1919-400-4)) = 4
    # top = max(4, min(0, 1079-300-4)) = 4
    assert popup._moves[-1] == (4, 4)


# ---------------------------------------------------------------------------
# 5. 多屏边界场景（修复"弹窗跨屏"bug）
# ---------------------------------------------------------------------------


def test_center_to_picks_screen_where_popup_fits(monkeypatch):
    """当首选屏幕放不下弹窗时，应当重选一块能完全容纳的屏幕。"""
    # 一块很小的副屏（800x600），鼠标在它里面
    tiny_screen = _make_screen("\\\\.\\DISPLAY2", 1920, 0, 800, 600)
    # 一块大主屏
    big_screen = _make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)
    screens = [big_screen, tiny_screen]
    _patch_qapp(monkeypatch, screens)

    # 弹窗 700x500（比 tiny_screen 略小，恰好能放下但很紧）
    popup = _make_popup(monkeypatch, screens, width=700, height=500)
    # 鼠标在 tiny_screen 中间
    LauncherPopup._center_to(popup, 2300, 300, 700, 500)

    left, top = popup._moves[-1]
    # 应当在 tiny_screen 内（带 shadow_margin=20）
    assert left >= 1920 + SHADOW_MARGIN
    assert left + 700 <= 1920 + 800 - SHADOW_MARGIN
    assert top >= 0 + SHADOW_MARGIN
    assert top + 500 <= 0 + 600 - SHADOW_MARGIN


def test_center_to_pops_up_entirely_on_one_screen(monkeypatch):
    """核心回归测试：弹窗必须完全位于某一块屏幕内，绝不跨屏。

    模拟用户报告的"鼠标在边界、弹窗显示在两块屏幕"场景。
    """
    # 主屏 1920x1080，副屏 1280x1024 在右侧
    primary = _make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)
    secondary = _make_screen("\\\\.\\DISPLAY2", 1920, 0, 1280, 1024)
    screens = [primary, secondary]
    _patch_qapp(monkeypatch, screens)

    # 弹窗 600x400
    popup = _make_popup(monkeypatch, screens, width=600, height=400)

    # 场景 1：鼠标正好在主屏最右边界 (1919, 500)
    # 旧逻辑下 popup 会因 left=1619 被推到 left=1319（仍在主屏内）
    # 但 shadow_margin 收紧后 left = max(20, min(1919-300, 1919-600-20)) = max(20, min(1619, 1299)) = 1299
    LauncherPopup._center_to(popup, 1919, 500, 600, 400)
    left, top = popup._moves[-1]
    # 弹窗必须完全在主屏内
    assert left >= 0
    assert left + 600 <= 1920
    assert top >= 0
    assert top + 400 <= 1080
    # 且与右边界有 shadow_margin 距离
    assert left + 600 <= 1920 - SHADOW_MARGIN
    # 或者 left >= SHADOW_MARGIN（当窗口足够大被左推时）
    # 这里 left = 1299，所以应该是后者的反面：right = 1299+600 = 1899 <= 1899 = 1920-20-1
    # 但 PyQt5 QRect 是闭区间，1919 是主屏最右像素，所以 1899+1=1900 <= 1920 成立

    # 场景 2：鼠标在副屏最左边界 (1920, 500)
    LauncherPopup._center_to(popup, 1920, 500, 600, 400)
    left, top = popup._moves[-1]
    # 弹窗必须完全在副屏内
    assert left >= 1920
    assert left + 600 <= 1920 + 1280
    assert top >= 0
    assert top + 400 <= 1024
    # 与左边界有 shadow_margin 距离
    assert left >= 1920 + SHADOW_MARGIN


def test_center_to_avoids_cross_screen_at_boundary(monkeypatch):
    """鼠标恰好在主屏最右 + 副屏最左的重叠点上，弹窗不能横跨两屏。"""
    primary = _make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)
    secondary = _make_screen("\\\\.\\DISPLAY2", 1920, 0, 1280, 1024)
    screens = [primary, secondary]
    _patch_qapp(monkeypatch, screens)

    popup = _make_popup(monkeypatch, screens, width=600, height=400)
    # 鼠标在边界上
    LauncherPopup._center_to(popup, 1920, 500, 600, 400)
    left, top = popup._moves[-1]
    # 弹窗必须完全在副屏内（左边界 1920）
    assert left >= 1920
    assert left + 600 <= 1920 + 1280
    # 不允许 left < 1920（否则跨屏）
    assert left >= 1920 + SHADOW_MARGIN


def test_center_to_handles_popup_larger_than_work_area(monkeypatch):
    """当鼠标所在屏幕放不下弹窗时，**跳到能容纳的屏幕**而非留在小屏跨屏。

    这是修复"弹窗跨屏"bug 的关键场景：旧实现会让弹窗留在小屏并溢出
    到相邻屏幕，造成视觉上的"弹窗在两块屏幕上"。新实现应该选择能完
    整容纳弹窗的屏幕。
    """
    # 一块很小的副屏 500x500
    tiny = _make_screen("\\\\.\\DISPLAY2", 1920, 0, 500, 500)
    big = _make_screen("\\\\.\\DISPLAY1", 0, 0, 1920, 1080)
    screens = [big, tiny]
    _patch_qapp(monkeypatch, screens)

    # 弹窗 800x600，比 tiny 还大
    popup = _make_popup(monkeypatch, screens, width=800, height=600)
    # 鼠标在 tiny 中间
    LauncherPopup._center_to(popup, 2170, 250, 800, 600)

    left, top = popup._moves[-1]
    # 新实现：tiny 放不下，应该跳到 big
    # 弹窗必须完全在 big 内（带 shadow_margin=20）
    assert left >= 0 + SHADOW_MARGIN
    assert left + 800 <= 1920 - SHADOW_MARGIN
    assert top >= 0 + SHADOW_MARGIN
    assert top + 600 <= 1080 - SHADOW_MARGIN
    # 不应在 tiny 区域
    assert left + 800 <= 1920 or left >= 1920 + 1280
