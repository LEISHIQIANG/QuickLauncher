"""
``PopupMixin._normalize_popup_pos`` 的单元测试。

阶段 0 基线测试：锁定重写后的行为契约——``_normalize_popup_pos`` 必须是
``coordinate_utils.normalize_caret_position`` 的薄包装，二者输入输出一致。
"""

from __future__ import annotations

import pytest

from ui.tray_mixins import popup_mixin


class _StubTray(popup_mixin.PopupMixin):
    """仅继承 PopupMixin，不构造完整 TrayApp。"""


@pytest.fixture
def tray():
    return _StubTray()


def test_normalize_popup_pos_delegates_to_coordinate_utils(monkeypatch, tray):
    """重写后 ``_normalize_popup_pos`` 必须委托给 ``coordinate_utils.normalize_caret_position``。"""
    from ui.utils import coordinate_utils

    captured = []

    def fake_normalize(phys_x, phys_y, screens=None):
        captured.append((phys_x, phys_y, screens))
        return (phys_x + 1, phys_y + 1)  # 任意不同值以验证是否被调用

    monkeypatch.setattr(
        coordinate_utils,
        "normalize_caret_position",
        fake_normalize,
    )

    result = tray._normalize_popup_pos(100, 200)
    assert result == (101, 201)
    assert captured == [(100, 200, None)]


def test_normalize_popup_pos_returns_input_when_no_modification(monkeypatch, tray):
    """当 ``coordinate_utils`` 透明返回时（当前配置行为），``_normalize_popup_pos`` 应返回原值。"""
    from qt_compat import QRect

    # 模拟存在一个屏幕包含 (500, 300)
    class _Screen:
        def name(self):
            return "\\\\.\\DISPLAY1"

        def geometry(self):
            return QRect(0, 0, 1920, 1080)

        def availableGeometry(self):
            return self.geometry()

        def devicePixelRatio(self):
            return 1.0

    import qt_compat

    class _FakeApp:
        @staticmethod
        def screens():
            return [_Screen()]

        @staticmethod
        def screenAt(_):
            return _Screen()

        @staticmethod
        def primaryScreen():
            return _Screen()

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)

    # 当前配置下物理 == 项目坐标
    assert tray._normalize_popup_pos(500, 300) == (500, 300)


def test_normalize_popup_pos_handles_negative_coords(monkeypatch, tray):
    """负坐标（屏幕外）应被 ``coordinate_utils`` 捕获并返回原值。"""
    import qt_compat
    from qt_compat import QRect

    class _Screen:
        def name(self):
            return "\\\\.\\DISPLAY1"

        def geometry(self):
            return QRect(0, 0, 1920, 1080)

        def availableGeometry(self):
            return self.geometry()

        def devicePixelRatio(self):
            return 1.0

    class _FakeApp:
        @staticmethod
        def screens():
            return [_Screen()]

        @staticmethod
        def screenAt(_):
            return None  # 屏幕外

        @staticmethod
        def primaryScreen():
            return _Screen()

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)

    assert tray._normalize_popup_pos(-100, -100) == (-100, -100)


def test_normalize_popup_pos_converts_to_int(monkeypatch, tray):
    """输入浮点也应被强转为 int。"""
    from qt_compat import QRect

    class _Screen:
        def name(self):
            return "\\\\.\\DISPLAY1"

        def geometry(self):
            return QRect(0, 0, 1920, 1080)

        def availableGeometry(self):
            return self.geometry()

        def devicePixelRatio(self):
            return 1.0

    import qt_compat

    class _FakeApp:
        @staticmethod
        def screens():
            return [_Screen()]

        @staticmethod
        def screenAt(_):
            return _Screen()

        @staticmethod
        def primaryScreen():
            return _Screen()

    monkeypatch.setattr(qt_compat, "QApplication", _FakeApp)

    # 输入 100.7 / 200.3 → 应被规范化
    result = tray._normalize_popup_pos(100.7, 200.3)
    assert result == (100, 200) or result == (101, 200)  # int 截断即可
    assert isinstance(result[0], int)
    assert isinstance(result[1], int)


def test_legacy_methods_removed():
    """旧的 ``_try_convert_win_physical_to_qt`` / ``_is_point_in_any_qt_screen`` 已被删除。"""
    assert not hasattr(popup_mixin.PopupMixin, "_try_convert_win_physical_to_qt")
    assert not hasattr(popup_mixin.PopupMixin, "_is_point_in_any_qt_screen")
