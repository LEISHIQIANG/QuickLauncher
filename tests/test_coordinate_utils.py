"""
``ui.utils.coordinate_utils`` 的单元测试。

覆盖：
- 显示器名归一化（不同 Qt 版本 ``QScreen.name()`` 返回格式差异）
- ``find_qscreen_by_device`` / ``find_qscreen_containing_point`` 匹配逻辑
- ``normalize_caret_position``（单一权威入口）的 fallback 行为
- ``get_monitor_physical_dpi`` 通过 mock Win32 验证
"""

from __future__ import annotations

import pytest

from qt_compat import QRect
from ui.utils import coordinate_utils
from ui.utils.coordinate_utils import (
    find_qscreen_by_device,
    find_qscreen_containing_point,
    get_monitor_device_name,
    get_monitor_physical_dpi,
    normalize_caret_position,
    normalize_device_name,
    pick_best_screen_for_popup,
)

# ---------------------------------------------------------------------------
# 显示器名归一化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 标准 Windows 形式（GetMonitorInfoW 的 szDevice）
        ("\\\\.\\DISPLAY1", "DISPLAY1"),
        ("\\\\.\\DISPLAY23", "DISPLAY23"),
        # Qt 5/6 常见返回
        ("\\\\.\\DISPLAY1", "DISPLAY1"),
        # 极个别精简 Qt 发行版只返回名字部分
        ("DISPLAY1", "DISPLAY1"),
        ("display2", "DISPLAY2"),
        # 小写
        ("\\\\.\\display1", "DISPLAY1"),
        # 头尾空白
        ("  \\\\ .\\DISPLAY1  ", ""),  # 中间含空格不识别
        ("\\\\.\\DISPLAY1  ", "DISPLAY1"),
        # 空/None
        ("", ""),
        # 异常格式
        ("Monitor 1", ""),
        ("\\\\.\\MONITOR1", ""),
        # 数字部分
        ("\\\\.\\DISPLAY123", "DISPLAY123"),
    ],
)
def test_normalize_device_name_valid_formats(raw, expected):
    assert normalize_device_name(raw) == expected


def test_normalize_device_name_handles_none():
    assert normalize_device_name("") == ""
    # 函数签名上是 str, 但要防御 None 输入
    assert normalize_device_name(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# find_qscreen_by_device
# ---------------------------------------------------------------------------


class _FakeScreen:
    def __init__(self, name, geometry, available_geometry=None):
        self._name = name
        self._geometry = geometry
        self._available_geometry = available_geometry or geometry

    def name(self):
        return self._name

    def geometry(self):
        return self._geometry

    def availableGeometry(self):
        return self._available_geometry


def test_find_qscreen_by_device_matches_full_path():
    """Qt 5/6 常见形式 ``\\\\.\\DISPLAY1`` 应当匹配 ``\\\\.\\DISPLAY1``。"""
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    screens = [primary, secondary]

    assert find_qscreen_by_device("\\\\.\\DISPLAY1", screens) is primary
    assert find_qscreen_by_device("\\\\.\\DISPLAY2", screens) is secondary


def test_find_qscreen_by_device_case_insensitive():
    """大小写无关：``\\\\.\\display1`` 应当匹配 ``\\\\.\\DISPLAY1``。"""
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    screens = [primary]

    assert find_qscreen_by_device("\\\\.\\display1", screens) is primary
    assert find_qscreen_by_device("DISPLAY1", screens) is primary


def test_find_qscreen_by_device_no_match_returns_none():
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    screens = [primary]

    assert find_qscreen_by_device("\\\\.\\DISPLAY99", screens) is None
    assert find_qscreen_by_device("", screens) is None


def test_find_qscreen_by_device_handles_screen_name_error():
    """``QScreen.name()`` 抛异常时不能污染匹配结果。"""
    from qt_compat import QRect

    class _BrokenScreen(_FakeScreen):
        def name(self):
            raise RuntimeError("name() failed")

    broken = _BrokenScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    good = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    screens = [broken, good]

    # 即使第一个屏幕 name() 抛异常，仍应能匹配到第二个
    assert find_qscreen_by_device("\\\\.\\DISPLAY2", screens) is good


# ---------------------------------------------------------------------------
# find_qscreen_containing_point
# ---------------------------------------------------------------------------


def test_find_qscreen_containing_point_primary():
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    screens = [primary, secondary]

    assert find_qscreen_containing_point(500, 300, screens) is primary
    assert find_qscreen_containing_point(2500, 500, screens) is secondary


def test_find_qscreen_containing_point_falls_back_to_primary():
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    screens = [primary, secondary]

    # 负坐标 / 远离任何屏幕的坐标应退化到 primary
    assert find_qscreen_containing_point(-1000, -1000, screens) is primary


# ---------------------------------------------------------------------------
# normalize_caret_position（单一权威入口）
# ---------------------------------------------------------------------------


def _patch_qapp(monkeypatch, screens):
    """把 ``qt_compat.QApplication`` 替换为可配置的 fake。"""
    import qt_compat

    class _FakeApp:
        @staticmethod
        def screens():
            return screens

        @staticmethod
        def screenAt(pos):
            for s in screens:
                if s.geometry().contains(pos):
                    return s
            return None

        @staticmethod
        def primaryScreen():
            return screens[0] if screens else None

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)
    monkeypatch.setattr(coordinate_utils, "_query_monitor_at", lambda _x, _y: None)


def test_normalize_caret_position_returns_raw_when_inside_geometry(monkeypatch):
    """点在某个屏幕 geometry 内时，``normalize_caret_position`` 直接返回原值。

    在当前 ``QT_AUTO_SCREEN_SCALE_FACTOR=0`` + ``PerMonitorV2`` 配置下，
    物理坐标 == 项目坐标。函数不应该做任何缩放。
    """
    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    _patch_qapp(monkeypatch, [primary, secondary])

    # 在主显示器中
    assert normalize_caret_position(500, 300) == (500, 300)
    # 在副显示器中
    assert normalize_caret_position(2400, 400) == (2400, 400)


def test_normalize_caret_position_falls_back_to_raw_when_outside_geometry(monkeypatch, caplog):
    """点不在任何已知 Qt 屏幕 geometry 内时，函数应记录 WARN 并返回原值（不崩溃）。"""
    import logging

    from qt_compat import QRect

    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    _patch_qapp(monkeypatch, [primary])

    with caplog.at_level(logging.WARNING, logger="ui.utils.coordinate_utils"):
        # 负坐标 → 不在任何屏幕里
        result = normalize_caret_position(-100, -100)

    assert result == (-100, -100)
    assert any("NORMALIZE_COORD_FALLBACK" in rec.message for rec in caplog.records)


def test_normalize_caret_position_works_without_qapp(monkeypatch):
    """``QApplication`` 不可用时（如 QApplication 创建之前调用）应安全返回原值。"""
    import qt_compat

    class _BrokenApp:
        @staticmethod
        def screens():
            return []

        @staticmethod
        def screenAt(_):
            return None

        @staticmethod
        def primaryScreen():
            return None

    monkeypatch.setattr(qt_compat, "QApplication", _BrokenApp)

    result = normalize_caret_position(123, 456)
    assert result == (123, 456)


def test_normalize_caret_position_maps_physical_pixels_to_qt_coordinates(monkeypatch):
    from qt_compat import QRect

    class _DprScreen(_FakeScreen):
        def __init__(self, name, geo, dpr):
            super().__init__(name, geo)
            self._dpr = dpr

        def devicePixelRatio(self):
            return self._dpr

    primary = _DprScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080), dpr=1.5)
    _patch_qapp(monkeypatch, [primary])
    monkeypatch.setattr(
        coordinate_utils,
        "_query_monitor_at",
        lambda _x, _y: (0xAB, 0, 0, 2880, "DISPLAY1", 144, 144),
    )

    assert normalize_caret_position(1000, 500) == (667, 333)
    assert normalize_caret_position(0, 0) == (0, 0)


def test_normalize_caret_position_preserves_mixed_dpi_monitor_origin(monkeypatch):
    from qt_compat import QRect

    class _DprScreen(_FakeScreen):
        def devicePixelRatio(self):
            return 1.5

    secondary = _DprScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1707, 960))
    _patch_qapp(monkeypatch, [secondary])
    monkeypatch.setattr(
        coordinate_utils,
        "_query_monitor_at",
        lambda _x, _y: (0xBC, 1920, 0, 4480, "DISPLAY2", 144, 144),
    )

    assert normalize_caret_position(3200, 720) == (2774, 480)


# ---------------------------------------------------------------------------
# get_monitor_physical_dpi（通过 mock Win32 验证）
# ---------------------------------------------------------------------------


def test_get_monitor_physical_dpi_returns_96_on_failure(monkeypatch):
    """Win32 API 不可用时应安全返回 ``(96, 96)``。"""
    monkeypatch.setattr(coordinate_utils, "_query_monitor_at", lambda x, y: None)
    assert get_monitor_physical_dpi(100, 200) == (96, 96)


def test_get_monitor_physical_dpi_returns_value_from_query(monkeypatch):
    monkeypatch.setattr(
        coordinate_utils,
        "_query_monitor_at",
        lambda x, y: (0xAB, 0, 0, 1920, "DISPLAY1", 144, 144),
    )
    assert get_monitor_physical_dpi(100, 200) == (144, 144)


def test_get_monitor_device_name_normalizes(monkeypatch):
    monkeypatch.setattr(
        coordinate_utils,
        "_query_monitor_at",
        lambda x, y: (0xAB, 0, 0, 1920, "DISPLAY1", 96, 96),
    )
    assert get_monitor_device_name(100, 200) == "DISPLAY1"


def test_get_monitor_device_name_empty_on_failure(monkeypatch):
    monkeypatch.setattr(coordinate_utils, "_query_monitor_at", lambda x, y: None)
    assert get_monitor_device_name(100, 200) == ""


# ---------------------------------------------------------------------------
# _query_monitor_at 真实调用 Win32（需要 Windows 平台）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
def test_query_monitor_at_returns_known_fields(monkeypatch):
    """在 Windows 上 ``_query_monitor_at`` 应能拿到真实显示器元数据。"""
    from qt_compat import QGuiApplication  # noqa: F401  触发 QApplication 创建

    meta = coordinate_utils._query_monitor_at(100, 100)
    if meta is None:
        pytest.skip("Win32 MonitorFromPoint 不可用")

    hmon, left, top, right, device, dpi_x, dpi_y = meta
    assert hmon > 0
    assert right > left >= 0
    assert dpi_x >= 96
    assert dpi_y >= 96
    # device 应是归一化后的 DISPLAY<n>，或空字符串（无法识别时）
    assert device == "" or device.startswith("DISPLAY")


# ---------------------------------------------------------------------------
# pick_best_screen_for_popup（多屏弹窗锚定选择）
# ---------------------------------------------------------------------------


def _patch_qapp_screens(monkeypatch, screens):
    """把 ``qt_compat.QApplication`` 替换为带 ``screens()`` / ``screenAt()`` 的 fake。"""
    import qt_compat

    class _FakeApp:
        @staticmethod
        def screens():
            return list(screens)

        @staticmethod
        def screenAt(pos):
            for s in screens:
                if s.geometry().contains(pos):
                    return s
            return None

        @staticmethod
        def primaryScreen():
            return screens[0] if screens else None

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)


def test_pick_best_screen_for_popup_prefers_screenAt_when_fits(monkeypatch):
    """``screenAt`` 拿到的屏幕能放下弹窗时，优先用它。"""
    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    _patch_qapp_screens(monkeypatch, [primary, secondary])

    # 鼠标在主屏中间，弹窗 400x300
    result = pick_best_screen_for_popup(1000, 500, 400, 300, margin=20)
    assert result is primary


def test_pick_best_screen_for_popup_reselects_when_screenAt_too_small(monkeypatch):
    """``screenAt`` 拿到的屏幕放不下弹窗时，重选一块能容纳的屏幕。

    这是修复"弹窗跨屏"bug 的核心场景：
    鼠标在很小的副屏内，弹窗比副屏大 → 必须跳到能容纳的屏幕。
    """
    tiny = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 500, 500))
    big = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    _patch_qapp_screens(monkeypatch, [big, tiny])

    # 鼠标在 tiny 内，弹窗 800x600（比 tiny 略大）
    # margin=20：tiny 的可用尺寸 500-40=460 < 800，容纳不下
    result = pick_best_screen_for_popup(2100, 250, 800, 600, margin=20)
    # 应选 big（重叠面积更大）
    assert result is big


def test_pick_best_screen_for_popup_falls_back_to_geometry_contains(monkeypatch):
    """``screenAt`` 失败时退化到 ``find_qscreen_containing_point``。"""
    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))
    _patch_qapp_screens(monkeypatch, [primary, secondary])

    # 让 screenAt 返回 None，强制走 fallback
    import qt_compat

    class _FakeApp:
        @staticmethod
        def screens():
            return [primary, secondary]

        @staticmethod
        def screenAt(_pos):
            return None

        @staticmethod
        def primaryScreen():
            return primary

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)

    result = pick_best_screen_for_popup(2400, 400, 400, 300, margin=20)
    # 应当走 find_qscreen_containing_point → secondary（2400 在副屏）
    assert result is secondary


def test_pick_best_screen_for_popup_picks_max_overlap_when_no_fit(monkeypatch):
    """所有屏幕都放不下弹窗时，选重叠面积最大的那块。"""
    tiny_a = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 400, 400))
    tiny_b = _FakeScreen("\\\\.\\DISPLAY2", QRect(400, 0, 400, 400))
    _patch_qapp_screens(monkeypatch, [tiny_a, tiny_b])

    # 弹窗 1000x800（两块都放不下）
    # 鼠标在 tiny_a 中心 (200, 200)
    result = pick_best_screen_for_popup(200, 200, 1000, 800, margin=0)
    # tiny_a 的重叠面积 = 400*400 = 160000
    # tiny_b 的重叠面积 = (200,0,600,400) ∩ (400,0,800,400) = 200*400 = 80000
    # 应当选 tiny_a
    assert result is tiny_a


def test_pick_best_screen_for_popup_returns_None_when_no_screens(monkeypatch):
    """没有任何屏幕时返回 None（不崩溃）。"""
    _patch_qapp_screens(monkeypatch, [])
    assert pick_best_screen_for_popup(100, 100, 400, 300) is None


def test_pick_best_screen_for_popup_margin_zero(monkeypatch):
    """margin=0 时按精确矩形匹配。"""
    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    _patch_qapp_screens(monkeypatch, [primary])

    # 弹窗恰好等于屏幕大小
    result = pick_best_screen_for_popup(960, 540, 1920, 1080, margin=0)
    assert result is primary

    # margin=1 时放不下
    result = pick_best_screen_for_popup(960, 540, 1920, 1080, margin=1)
    # 此时 fallback 到最大重叠 → 仍选 primary（因为没有其他屏幕）
    assert result is primary


def test_pick_best_screen_for_popup_handles_qapp_unavailable(monkeypatch):
    """QApplication 不可用时安全返回 None。"""
    import qt_compat

    class _BrokenApp:
        @staticmethod
        def screens():
            raise RuntimeError("no QApplication")

    monkeypatch.setattr(qt_compat, "QApplication", _BrokenApp)
    # 即使 screens 参数为空，也应该走 own_screens 路径返回 None
    assert pick_best_screen_for_popup(100, 100, 400, 300, screens=[]) is None


def test_pick_best_screen_for_popup_uses_passed_screens_list(monkeypatch):
    """显式传入 screens 列表时，使用该列表而非 QApplication.screens()。"""
    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    secondary = _FakeScreen("\\\\.\\DISPLAY2", QRect(1920, 0, 1280, 720))

    # 显式传入 screens（绕开 QApplication）
    result = pick_best_screen_for_popup(2400, 400, 400, 300, screens=[primary, secondary], margin=20)
    # 2400 在 secondary.geometry() 内
    assert result is secondary


def test_pick_best_screen_for_popup_negative_coordinates(monkeypatch):
    """副屏在主屏左侧（负坐标）时也能正确选择。"""
    primary = _FakeScreen("\\\\.\\DISPLAY1", QRect(0, 0, 1920, 1080))
    left_screen = _FakeScreen("\\\\.\\DISPLAY2", QRect(-1280, 0, 1280, 720))
    _patch_qapp_screens(monkeypatch, [primary, left_screen])

    # 鼠标在左侧副屏
    result = pick_best_screen_for_popup(-500, 400, 400, 300, margin=20)
    assert result is left_screen
