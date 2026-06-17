"""Tests for the P1-06 Stage 1 platform backend abstraction."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from ui.platforms import (
    WindowEffectBackend,
    _NoopBackend,
    _WindowsBackend,
    get_window_effect_backend,
    reset_window_effect_backend,
)

pytestmark = pytest.mark.ui


def test_default_backend_satisfies_protocol():
    """The cached backend must satisfy the :class:`WindowEffectBackend` protocol."""
    reset_window_effect_backend()
    backend = get_window_effect_backend()
    assert isinstance(backend, WindowEffectBackend)


def test_backend_is_cached():
    reset_window_effect_backend()
    a = get_window_effect_backend()
    b = get_window_effect_backend()
    assert a is b


def test_reset_clears_cache():
    a = get_window_effect_backend()
    reset_window_effect_backend()
    b = get_window_effect_backend()
    assert a is not b


def test_noop_backend_reports_unsupported():
    backend = _NoopBackend()
    assert backend.is_supported() is False
    assert backend.is_win10() is False
    assert backend.is_win11() is False
    # paint_win10_rounded_surface is intentionally a no-op.
    assert backend.paint_win10_rounded_surface(None, None, None, None, 0) is None


def test_windows_backend_delegates_to_window_effect():
    backend = _WindowsBackend()
    if sys.platform != "win32":
        # On non-Windows hosts the delegate falls back to False, but the
        # backend is still constructable and exposes the right name.
        assert backend.name == "windows"
        return
    # On Windows the delegate should call the real helpers.  We do
    # not want to assume the host is Win10/Win11; the helper returns
    # a bool and we just exercise the path.
    backend.is_win10()
    backend.is_win11()


def test_detect_backend_non_windows_uses_noop():
    reset_window_effect_backend()
    with patch("ui.platforms.sys.platform", "linux"):
        # Force re-detection by re-importing the detector.
        from ui.platforms import _detect_backend

        assert isinstance(_detect_backend(), _NoopBackend)


def test_paint_win10_rounded_surface_signature_matches():
    """The backend signature mirrors the original helper."""
    backend = get_window_effect_backend()

    # The call must accept painter / widget / colors / radius and the
    # keyword-only advanced options without raising.
    class _Painter:
        def __init__(self):
            self.calls = 0

    class _Widget:
        pass

    painter = _Painter()
    # The noop backend does nothing, the Windows backend calls through
    # to the real helper.  Both must accept the kwargs without raising.
    backend.paint_win10_rounded_surface(
        painter,
        _Widget(),
        "#ff0000",
        "#000000",
        8,
        inset=0.5,
        min_bg_alpha=200,
        max_border_alpha=180,
    )
