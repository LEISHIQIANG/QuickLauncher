"""Tests for the OS precheck that gates the 'glass background' option.

The threshold is intentionally tight (build >= 22000 / Windows 11) because
empirically many Windows 10 22H2 (build 19045) systems also reject
``SetWindowDisplayAffinity(..., WDA_EXCLUDEFROMCAPTURE)`` and the user
would otherwise get a tray error every time the popup is shown.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from ui.utils import window_effect

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def _clear_version_cache():
    """Each test must see a fresh ``get_windows_version`` cache."""
    window_effect._windows_version_cache = None
    yield
    window_effect._windows_version_cache = None


def test_glass_background_supported_on_win11_build_22000():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=22000):
        assert window_effect.is_glass_background_supported() is True


def test_glass_background_supported_on_win11_build_26000():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=26000):
        assert window_effect.is_glass_background_supported() is True


def test_glass_background_unsupported_on_win11_threshold_minus_one():
    """Build 21999 is the last Windows 10 22H2 - must be rejected."""
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=21999):
        assert window_effect.is_glass_background_supported() is False


def test_glass_background_unsupported_on_win10_22h2():
    """Win10 22H2 is build 19045 - the failing case reported in the field."""
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=19045):
        assert window_effect.is_glass_background_supported() is False


def test_glass_background_unsupported_on_win10_2004():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=19041):
        assert window_effect.is_glass_background_supported() is False


def test_glass_background_unsupported_on_old_win10():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=17763):
        assert window_effect.is_glass_background_supported() is False


def test_glass_background_unsupported_on_win7():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=7601):
        assert window_effect.is_glass_background_supported() is False


def test_glass_background_unsupported_when_version_detection_fails():
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=None):
        with patch.object(sys, "getwindowsversion", side_effect=OSError("nope")):
            assert window_effect.is_glass_background_supported() is False


def test_glass_background_falls_back_to_sys_getwindowsversion():
    """When ``RtlGetVersion`` is unavailable, ``sys.getwindowsversion`` is used."""
    fake_version = type("V", (), {"build": 22621})()
    with patch.object(window_effect, "_get_windows_build_from_rtl", return_value=None):
        with patch.object(sys, "getwindowsversion", return_value=fake_version):
            assert window_effect.is_glass_background_supported() is True
