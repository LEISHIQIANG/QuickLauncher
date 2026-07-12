"""Public entry point for the P1-06 platform backend package.

The :mod:`ui.platforms` package centralises the platform-specific
implementations of the window chrome / DWM blur / round-corner
helpers that previously lived in :mod:`ui.utils.window_effect`.  The
existing :mod:`ui.utils.window_effect` module is **kept** and remains
the implementation used by the view layer today; the new
:class:`WindowEffectBackend` Protocol is the abstraction that will
let future PRs swap in alternate backends without touching the view
code.

The factory :func:`get_window_effect_backend` inspects the host OS
once at import time and caches the result.
"""

from __future__ import annotations

import sys
from typing import Protocol, runtime_checkable

from ui.utils import window_effect as _window_effect


@runtime_checkable
class WindowEffectBackend(Protocol):
    """Platform-neutral window-effect contract.

    A backend exposes the operations that the view layer invokes
    without knowing whether the implementation is DWM, Cocoa or
    pure-Qt.  The concrete :mod:`ui.utils.window_effect` module is
    the default Windows implementation.
    """

    name: str

    def is_supported(self) -> bool: ...

    def is_win10(self) -> bool: ...

    def is_win11(self) -> bool: ...

    def paint_win10_rounded_surface(
        self,
        painter,
        widget,
        bg_color,
        border_color,
        radius: int,
        *,
        inset: float = 1.0,
        min_bg_alpha: int = 248,
        max_border_alpha: int = 220,
    ) -> None: ...


class _WindowsBackend:
    """Default backend — delegates to :mod:`ui.utils.window_effect`."""

    name = "windows"

    def is_supported(self) -> bool:
        return sys.platform == "win32"

    def is_win10(self) -> bool:
        try:
            return bool(_window_effect.is_win10())
        except Exception:
            return False

    def is_win11(self) -> bool:
        try:
            return bool(_window_effect.is_win11())
        except Exception:
            return False

    def paint_win10_rounded_surface(
        self,
        painter,
        widget,
        bg_color,
        border_color,
        radius: int,
        *,
        inset: float = 1.0,
        min_bg_alpha: int = 248,
        max_border_alpha: int = 220,
    ) -> None:
        _window_effect.paint_win10_rounded_surface(
            painter,
            widget,
            bg_color,
            border_color,
            radius,
            inset=inset,
            min_bg_alpha=min_bg_alpha,
            max_border_alpha=max_border_alpha,
        )


class _NoopBackend:
    """Fallback backend for non-Windows hosts (and unknown versions)."""

    name = "noop"

    def is_supported(self) -> bool:
        return False

    def is_win10(self) -> bool:
        return False

    def is_win11(self) -> bool:
        return False

    def paint_win10_rounded_surface(
        self,
        painter,
        widget,
        bg_color,
        border_color,
        radius: int,
        *,
        inset: float = 1.0,
        min_bg_alpha: int = 248,
        max_border_alpha: int = 220,
    ) -> None:
        return None


def _detect_backend() -> WindowEffectBackend:
    """Pick the appropriate backend for the current host."""
    if sys.platform != "win32":
        return _NoopBackend()
    try:
        version = sys.getwindowsversion()
    except Exception:
        return _NoopBackend()
    if version.major < 6:
        return _NoopBackend()
    return _WindowsBackend()


_BACKEND: WindowEffectBackend | None = None


def get_window_effect_backend() -> WindowEffectBackend:
    """Return the process-wide :class:`WindowEffectBackend`.

    The result is cached after the first call; use
    :func:`reset_window_effect_backend` from tests to force a re-pick.
    """
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _detect_backend()
    return _BACKEND


def reset_window_effect_backend() -> None:
    """Drop the cached backend (used by tests)."""
    global _BACKEND
    _BACKEND = None


__all__ = [
    "WindowEffectBackend",
    "get_window_effect_backend",
    "reset_window_effect_backend",
]
