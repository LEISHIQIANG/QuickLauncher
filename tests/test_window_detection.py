"""Tests for core.window_detection."""

from unittest.mock import MagicMock, patch

import pytest

MODULE = "core.window_detection"


@pytest.fixture(autouse=True)
def mock_win32gui():
    """Mock win32gui for all tests in this module."""
    with patch(f"{MODULE}.win32gui", MagicMock()) as m:
        yield m


@pytest.fixture(autouse=True)
def ensure_has_win32(mock_win32gui):
    """Ensure HAS_WIN32_SHELL is True for tests that need it."""
    # force the module-level flag after patching
    with patch(f"{MODULE}.HAS_WIN32_SHELL", True):
        yield


class TestImports:
    def test_window_detection_imports(self):
        import core.window_detection as wd

        assert hasattr(wd, "_normalize_window_hwnd")
        assert hasattr(wd, "_get_window_class_name")
        assert hasattr(wd, "_is_explorer_like_window")
        assert hasattr(wd, "_is_desktop_window")
        assert hasattr(wd, "_window_from_point")
        assert hasattr(wd, "_window_selection_kind")
        assert hasattr(wd, "_point_near_window")


class TestNormalizeWindowHwnd:
    def test_normalize_no_parent(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetParent.return_value = 0
        result = wd._normalize_window_hwnd(0x12345)
        assert result == 0x12345
        mock_win32gui.GetParent.assert_called_once_with(0x12345)

    def test_normalize_walks_up_parent_chain(self, mock_win32gui):
        import core.window_detection as wd

        # chain: 0x3 -> parent 0x2 -> parent 0x1 -> parent 0 (stop)
        mock_win32gui.GetParent.side_effect = [0x2, 0x1, 0]
        result = wd._normalize_window_hwnd(0x3)
        assert result == 0x1

    def test_normalize_zero_hwnd(self, mock_win32gui):
        import core.window_detection as wd

        result = wd._normalize_window_hwnd(0)
        assert result == 0
        mock_win32gui.GetParent.assert_not_called()

    def test_normalize_none_hwnd(self, mock_win32gui):
        import core.window_detection as wd

        result = wd._normalize_window_hwnd(None)
        assert result == 0
        mock_win32gui.GetParent.assert_not_called()

    def test_normalize_invalid_type(self, mock_win32gui):
        import core.window_detection as wd

        result = wd._normalize_window_hwnd("not_a_handle")
        assert result == 0
        mock_win32gui.GetParent.assert_not_called()

    def test_normalize_win32gui_raises(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetParent.side_effect = Exception("boom")
        # falls back to returning the original hwnd (or 0)
        result = wd._normalize_window_hwnd(0xABC)
        assert result == 0xABC

    def test_normalize_self_parent_stops(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetParent.return_value = 0x42  # same as input -> break
        # Wait, current=0x42, GetParent returns 0x42 -> parent == current -> break
        result = wd._normalize_window_hwnd(0x42)
        assert result == 0x42

    def test_normalize_without_win32_shell(self, mock_win32gui):
        with patch(f"{MODULE}.HAS_WIN32_SHELL", False):
            import core.window_detection as wd

            result = wd._normalize_window_hwnd(0xDEAD)
            assert result == 0xDEAD
            mock_win32gui.GetParent.assert_not_called()


class TestGetWindowClassName:
    def test_get_class_name(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "CabinetWClass"
        result = wd._get_window_class_name(0x123)
        assert result == "CabinetWClass"
        mock_win32gui.GetClassName.assert_called_once_with(0x123)

    def test_get_class_name_none_hwnd(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = ""
        result = wd._get_window_class_name(None)
        assert result == ""
        mock_win32gui.GetClassName.assert_called_once_with(0)

    def test_get_class_name_zero_hwnd(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = ""
        result = wd._get_window_class_name(0)
        assert result == ""
        mock_win32gui.GetClassName.assert_called_once_with(0)

    def test_get_class_name_win32gui_raises(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.side_effect = Exception("boom")
        result = wd._get_window_class_name(0x123)
        assert result == ""

    def test_get_class_name_without_win32_shell(self, mock_win32gui):
        with patch(f"{MODULE}.HAS_WIN32_SHELL", False):
            import core.window_detection as wd

            result = wd._get_window_class_name(0x123)
            assert result == ""
            mock_win32gui.GetClassName.assert_not_called()


class TestIsExplorerLikeWindow:
    def test_cabinet_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "CabinetWClass"
        assert wd._is_explorer_like_window(0x123) is True

    def test_explore_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "ExploreWClass"
        assert wd._is_explorer_like_window(0x123) is True

    def test_progman_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Progman"
        assert wd._is_explorer_like_window(0x123) is True

    def test_workerw_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "WorkerW"
        assert wd._is_explorer_like_window(0x123) is True

    def test_shell_in_class_name(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Shell_SecondaryTrayWnd"
        assert wd._is_explorer_like_window(0x123) is True

    def test_excluded_tray_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Shell_TrayWnd"
        assert wd._is_explorer_like_window(0x123) is False

    def test_non_explorer_class(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Notepad"
        assert wd._is_explorer_like_window(0x123) is False

    def test_empty_class_name(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = ""
        assert wd._is_explorer_like_window(0x123) is False


class TestIsDesktopWindow:
    def test_progman_is_desktop(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Progman"
        assert wd._is_desktop_window(0x123) is True

    def test_workerw_is_desktop(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "WorkerW"
        assert wd._is_desktop_window(0x123) is True

    def test_cabinet_not_desktop(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "CabinetWClass"
        assert wd._is_desktop_window(0x123) is False

    def test_empty_class_name_not_desktop(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = ""
        assert wd._is_desktop_window(0x123) is False


class TestWindowFromPoint:
    def test_window_from_point(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.WindowFromPoint.return_value = 0xABC
        result = wd._window_from_point(100, 200)
        assert result == 0xABC
        mock_win32gui.WindowFromPoint.assert_called_once_with((100, 200))

    def test_window_from_point_returns_zero(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.WindowFromPoint.return_value = 0
        result = wd._window_from_point(0, 0)
        assert result == 0

    def test_window_from_point_raises(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.WindowFromPoint.side_effect = Exception("boom")
        result = wd._window_from_point(100, 200)
        assert result == 0

    def test_window_from_point_without_win32_shell(self, mock_win32gui):
        with patch(f"{MODULE}.HAS_WIN32_SHELL", False):
            import core.window_detection as wd

            result = wd._window_from_point(100, 200)
            assert result == 0
            mock_win32gui.WindowFromPoint.assert_not_called()


class TestWindowSelectionKind:
    def test_desktop(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Progman"
        assert wd._window_selection_kind(0x123) == "desktop"

    def test_explorer(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "CabinetWClass"
        assert wd._window_selection_kind(0x123) == "explorer"

    def test_other(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Notepad"
        assert wd._window_selection_kind(0x123) == "other"

    def test_excluded_tray_is_other(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetClassName.return_value = "Shell_TrayWnd"
        assert wd._window_selection_kind(0x123) == "other"


class TestPointNearWindow:
    def test_point_inside_window(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        assert wd._point_near_window(0x123, 200, 200) is True

    def test_point_inside_within_margin(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # 80 is within 48px margin of left edge (100)
        assert wd._point_near_window(0x123, 80, 200) is True

    def test_point_outside_margin(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # left - margin = 52. x=50 < 52, so outside the margin zone
        assert wd._point_near_window(0x123, 50, 200) is False

    def test_point_far_outside(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # left - margin = 100 - 48 = 52, x=10 -> 10 < 52 -> True
        # Hmm, let me recalculate: margin=48, left=100, so left-margin=52
        # x=10 <= 52 True, so still near
        # x=0 is still within (0 <= 52 is True)
        # x = -100 -> -100 <= 52 -> True
        # Actually to be "outside margin": x < left - margin  ->  x < 52
        # Or x > right + margin -> x > 348
        assert wd._point_near_window(0x123, 400, 200) is False

    def test_point_far_outside_x_less_than_left_minus_margin(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # left - margin = 52. x=0 < 52 -> True (still near!)
        # Actually to be False: x must be < left - margin? No.
        # Check: (left - margin) <= int(x) <= (right + margin)
        # So x=0: 52 <= 0 is False, so condition fails -> returns False
        assert wd._point_near_window(0x123, 0, 200) is False

    def test_point_far_outside_y(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        assert wd._point_near_window(0x123, 200, 0) is False

    def test_custom_margin(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # x=50 normally within default margin, but with margin=0 it's outside
        assert wd._point_near_window(0x123, 50, 200, margin=0) is False

    def test_negative_margin_clamped_to_zero(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.return_value = (100, 100, 300, 300)
        # margin=-10 should be clamped to 0
        assert wd._point_near_window(0x123, 50, 200, margin=-10) is False

    def test_get_window_rect_raises(self, mock_win32gui):
        import core.window_detection as wd

        mock_win32gui.GetWindowRect.side_effect = Exception("boom")
        assert wd._point_near_window(0x123, 200, 200) is False

    def test_without_win32_shell(self, mock_win32gui):
        with patch(f"{MODULE}.HAS_WIN32_SHELL", False):
            import core.window_detection as wd

            assert wd._point_near_window(0x123, 200, 200) is False
            mock_win32gui.GetWindowRect.assert_not_called()
