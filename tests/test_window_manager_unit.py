"""Tests for window_manager.py guard paths and helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch


class TestWindowManagerNoWin32:
    def test_try_activate_returns_false_without_win32(self):
        from core import window_manager

        with patch.object(window_manager, "HAS_WIN32", False):
            assert window_manager.WindowManager.try_activate("anything.exe") is False


class TestWindowManagerHelpers:
    def test_try_activate_exception_handling(self):
        from core import window_manager

        with patch.object(window_manager, "HAS_WIN32", True):
            with patch.object(window_manager, "win32gui") as mock_gui:
                mock_gui.EnumWindows.side_effect = Exception("boom")
                result = window_manager.WindowManager.try_activate(r"C:\app.exe")
                assert result is False

    def test_activate_window_invalid_hwnd(self):
        from core import window_manager

        with patch.object(window_manager, "HAS_WIN32", True):
            with patch.object(window_manager, "win32gui") as mock_gui:
                mock_gui.IsWindow.return_value = False
                result = window_manager.WindowManager._activate_window(0)
                assert result is False
