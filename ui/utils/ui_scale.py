"""
Centralized UI scaling module.

Provides a single source of truth for application-level UI scaling,
independent of Windows/Qt DPI. All UI code should use the helpers
in this module (sp, spf, sqsize, smargins, font_px, scale_qss, etc.)
instead of reading settings.ui_scale_percent directly.

Design principle: most layout px values scale proportionally, while
hairline visual strokes such as QSS borders stay at their authored width
so 150% does not turn 1px borders into heavy 2px outlines.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SCALE_PERCENT = 90
MAX_SCALE_PERCENT = 150
DEFAULT_SCALE_PERCENT = 100

# Minimum font pixel size after scaling – prevents unreadably small text.
_MIN_FONT_PX = 9

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_scale_percent: int = DEFAULT_SCALE_PERCENT
_scale_factor: float = 1.0

# Simple regex: match any  Npx  preceded by colon or whitespace.
# This catches every px value in QSS regardless of property name.
_PX_RE = re.compile(r"(?<=[\s:])(-?\d+)px")

# Protection: skip url(...) segments when scaling
_URL_RE = re.compile(r"url\([^)]*\)")

_UNSCALED_STROKE_PROPERTIES = {
    "border",
    "border-top",
    "border-right",
    "border-bottom",
    "border-left",
    "border-width",
    "border-top-width",
    "border-right-width",
    "border-bottom-width",
    "border-left-width",
    "outline",
    "outline-width",
}

# ---------------------------------------------------------------------------
# Public API – state
# ---------------------------------------------------------------------------


def set_scale(percent: int) -> None:
    """Set the global UI scale percentage. Clamped to [MIN, MAX]."""
    global _scale_percent, _scale_factor
    _scale_percent = max(MIN_SCALE_PERCENT, min(MAX_SCALE_PERCENT, int(percent)))
    _scale_factor = _scale_percent / 100.0


def get_scale_percent() -> int:
    return _scale_percent


def get_scale_factor() -> float:
    return _scale_factor


# ---------------------------------------------------------------------------
# Public API – numeric scaling
# ---------------------------------------------------------------------------


def sp(value: int) -> int:
    """Scale an integer pixel value by the current UI scale factor."""
    if _scale_factor == 1.0:
        return int(value)
    return int(round(value * _scale_factor))


def spf(value: float) -> float:
    """Scale a float pixel value by the current UI scale factor."""
    if _scale_factor == 1.0:
        return value
    return value * _scale_factor


# ---------------------------------------------------------------------------
# Public API – font scaling
# ---------------------------------------------------------------------------


def font_px(px: int) -> int:
    """Scale a font pixel size, enforcing a minimum readable size."""
    scaled = sp(px)
    return max(_MIN_FONT_PX, scaled)


# ---------------------------------------------------------------------------
# Public API – Qt type scaling
# ---------------------------------------------------------------------------


def sqsize(w: int, h: int):
    """Return a scaled QSize."""
    from qt_compat import QSize

    return QSize(sp(w), sp(h))


def smargins(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    """Return scaled margin values as a tuple (left, top, right, bottom)."""
    return (sp(left), sp(top), sp(right), sp(bottom))


def srect(x: int, y: int, w: int, h: int):
    """Return a scaled QRect."""
    from qt_compat import QRect

    return QRect(sp(x), sp(y), sp(w), sp(h))


def srectf(x: float, y: float, w: float, h: float):
    """Return a scaled QRectF."""
    from qt_compat import QRectF

    return QRectF(spf(x), spf(y), spf(w), spf(h))


def spoint(x: int, y: int):
    """Return a scaled QPoint."""
    from qt_compat import QPoint

    return QPoint(sp(x), sp(y))


# ---------------------------------------------------------------------------
# Public API – QSS scaling
# ---------------------------------------------------------------------------


def _qss_property_at(css: str, pos: int) -> str:
    """Return the current QSS declaration property name for a value position."""
    start = max(css.rfind(";", 0, pos), css.rfind("{", 0, pos)) + 1
    colon = css.rfind(":", start, pos)
    if colon < start:
        return ""
    return css[start:colon].strip().lower()


def _is_unscaled_stroke_value(css: str, pos: int) -> bool:
    return _qss_property_at(css, pos) in _UNSCALED_STROKE_PROPERTIES


def scale_qss(css: str) -> str:
    """Scale px values in a QSS string by the current scale factor.

    Scaling rules:
    - Most ``Npx`` values (N != 0) are multiplied by the scale factor.
    - Border/outline stroke widths keep their authored pixel value.
    - ``0px`` is left as-is (0 × anything = 0).
    - Content inside ``url(...)`` is never touched.
    - rgba() / hex colours / numbers without px unit are not affected.
    """
    if _scale_factor == 1.0 or not css:
        return css

    # Collect url(...) spans to protect them from replacement
    protected_spans: list[tuple[int, int]] = []
    for m in _URL_RE.finditer(css):
        protected_spans.append((m.start(), m.end()))

    def _in_protected(pos: int) -> bool:
        for s, e in protected_spans:
            if s <= pos < e:
                return True
        return False

    def _replace_px(m: re.Match) -> str:
        if _in_protected(m.start()):
            return m.group(0)
        val = int(m.group(1))
        if val == 0:
            return m.group(0)
        if _is_unscaled_stroke_value(css, m.start()):
            return m.group(0)
        scaled = sp(val)
        return f"{scaled}px"

    return _PX_RE.sub(_replace_px, css)


# ---------------------------------------------------------------------------
# Public API – context manager
# ---------------------------------------------------------------------------


@contextmanager
def no_scale_scope():
    """Context manager that temporarily sets scale to 100% (factor 1.0).

    Use for DPR-aware image sizing or physical-pixel drawing
    that must not be affected by the application UI scale.
    """
    global _scale_percent, _scale_factor
    old_pct, old_fac = _scale_percent, _scale_factor
    _scale_percent = DEFAULT_SCALE_PERCENT
    _scale_factor = 1.0
    try:
        yield
    finally:
        _scale_percent = old_pct
        _scale_factor = old_fac


def is_default_scale() -> bool:
    """Return True when the scale is 100%."""
    return _scale_factor == 1.0
