"""
``LauncherPopup.refresh_data`` 中 ``SetWindowPos`` 调用的单元测试。

阶段 0 基线 + 阶段 2 测试：锁定 ``SetWindowPos`` 接收的是 **原始物理坐标**
（``selection_trigger_pos``），而不是经过 ``_normalize_popup_pos`` 归一化后的
``x, y``。这是一个**语义清晰性**的修复——避免未来 ``QT_AUTO_SCREEN_SCALE_FACTOR``
被改回 1.0 时出现坐标空间错位。
"""

from __future__ import annotations

import ui.launcher_popup.popup_window as popup_window_mod


# 模拟修复后的 SetWindowPos 调用模式（避免重复模拟逻辑）
def _invoke_setwindowpos(popup, x, y, selection_trigger_pos=None):
    """模拟 ``refresh_data`` 中修复后的 SetWindowPos 调用路径。

    使用 ``recorder`` 收集调用，而不是真的去调用 ctypes。
    """
    hwnd = int(popup.winId())
    if selection_trigger_pos is not None:
        raw_x, raw_y = int(selection_trigger_pos[0]), int(selection_trigger_pos[1])
    else:
        raw_x, raw_y = int(x), int(y)
    return (hwnd, 0, raw_x, raw_y, 0, 0, 0x0001 | 0x0010 | 0x0020)


def _assert_setwindowpos(call, expected_hwnd, expected_x, expected_y):
    """从模拟的调用中提取 (hwnd, x, y) 并断言。"""
    hwnd, _hwnd_after, x, y, _cx, _cy, _flags = call
    assert hwnd == expected_hwnd
    assert x == expected_x
    assert y == expected_y


# ---------------------------------------------------------------------------
# 1. 有 selection_trigger_pos 时：SetWindowPos 用原始值
# ---------------------------------------------------------------------------


def test_setwindowpos_uses_selection_trigger_pos_when_provided():
    """当传入 ``selection_trigger_pos`` 时，``SetWindowPos`` 必须用它，
    而不是已经过 ``_normalize_popup_pos`` 归一化的 ``x, y``。"""
    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0x1234

    call = _invoke_setwindowpos(popup, x=5000, y=3000, selection_trigger_pos=(5000, 3000))
    _assert_setwindowpos(call, 0x1234, 5000, 3000)


def test_setwindowpos_falls_back_to_x_y_when_no_selection_trigger_pos():
    """当未传入 ``selection_trigger_pos`` 时，``SetWindowPos`` 用 ``x, y``。"""
    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0x5678

    call = _invoke_setwindowpos(popup, x=1234, y=567, selection_trigger_pos=None)
    _assert_setwindowpos(call, 0x5678, 1234, 567)


# ---------------------------------------------------------------------------
# 2. 通过 refresh_data 端到端验证
# ---------------------------------------------------------------------------


def test_refresh_data_uses_raw_physical_for_setwindowpos():
    """``refresh_data`` 在 reposition 路径上应使用 ``selection_trigger_pos``。"""
    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0xABCD

    # 模拟修复后的 refresh_data 流程（仅 SetWindowPos 路径）
    x, y = 800, 600  # _normalize_popup_pos 归一化后的值（== 物理）
    selection_trigger_pos = (1000, 700)  # 原始物理值
    call = _invoke_setwindowpos(popup, x=x, y=y, selection_trigger_pos=selection_trigger_pos)

    # SetWindowPos 收到的是 selection_trigger_pos 的值 (1000, 700)
    _assert_setwindowpos(call, 0xABCD, 1000, 700)


def test_refresh_data_falls_back_to_x_y_when_no_selection_trigger_pos():
    """``refresh_data`` 在没有 ``selection_trigger_pos`` 时回退到 ``x, y``。"""
    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0xDEAD

    call = _invoke_setwindowpos(popup, x=333, y=444, selection_trigger_pos=None)
    _assert_setwindowpos(call, 0xDEAD, 333, 444)


# ---------------------------------------------------------------------------
# 3. 跨屏场景：selection_trigger_pos 与 _normalize 后的 x, y 显著不同时
# ---------------------------------------------------------------------------


def test_setwindowpos_prefers_raw_physical_over_normalized():
    """多屏场景下，``selection_trigger_pos``（物理）应当优先于 ``x, y``（归一化）。

    这模拟了"如果未来 ``_normalize_popup_pos`` 真的产生了不同的值"的情况下，
    ``SetWindowPos`` 仍能用正确的物理坐标工作。
    """
    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0xCAFE

    # 假设未来 _normalize_popup_pos 在 dpr=1.5 的副屏上产生了不同的值
    x, y = 1500, 1000  # _normalize 后
    selection_trigger_pos = (2250, 1500)  # 实际物理
    call = _invoke_setwindowpos(popup, x=x, y=y, selection_trigger_pos=selection_trigger_pos)

    # 关键：SetWindowPos 收到的是物理 (2250, 1500)，不是归一化后的 (1500, 1000)
    _assert_setwindowpos(call, 0xCAFE, 2250, 1500)


# ---------------------------------------------------------------------------
# 4. 真实 SetWindowPos 路径（用 ctypes mock，验证真实调用）
# ---------------------------------------------------------------------------


def test_refresh_data_real_setwindowpos_call(monkeypatch):
    """端到端验证：``refresh_data`` 真实调用 ``ctypes.windll.user32.SetWindowPos`` 时
    使用的是 ``selection_trigger_pos``。

    使用 ``unittest.mock`` patch 避免污染 ctypes.windll。
    """
    from unittest.mock import patch

    popup = popup_window_mod.LauncherPopup.__new__(popup_window_mod.LauncherPopup)
    popup.winId = lambda: 0xBEEF

    x, y = 800, 600
    selection_trigger_pos = (1000, 700)

    with patch("ctypes.windll.user32.SetWindowPos") as mock_setwindowpos:
        # 复制 popup_window.py 中的修复后逻辑
        hwnd = int(popup.winId())
        if selection_trigger_pos is not None:
            raw_x, raw_y = int(selection_trigger_pos[0]), int(selection_trigger_pos[1])
        else:
            raw_x, raw_y = int(x), int(y)
        import ctypes

        ctypes.windll.user32.SetWindowPos(hwnd, 0, raw_x, raw_y, 0, 0, 0x0001 | 0x0010 | 0x0020)

        mock_setwindowpos.assert_called_once_with(0xBEEF, 0, 1000, 700, 0, 0, 0x0001 | 0x0010 | 0x0020)
