"""Polished fallback icon renderer for items without a real icon.

Used by the launcher popup, the settings icon grid, and the low-level
:class:`core.icon_extractor.IconExtractor` so every default icon shares
the same refined look (per-name accent colour, vertical gradient,
subtle top highlight, CJK-friendly typography).
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import hashlib
import logging
import re

from qt_compat import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPointF,
    QRectF,
    QtCompat,
)
from ui.utils.lru_cache import pixmap_cache

logger = logging.getLogger(__name__)

_ACCENT_PALETTE: tuple[tuple[int, int, int], ...] = (
    (64, 130, 217),  # Vibrant Sky Blue
    (46, 179, 112),  # Vibrant Emerald Green
    (237, 106, 76),  # Vibrant Orange-Red / Coral
    (235, 87, 127),  # Vibrant Pink / Rose
    (138, 92, 219),  # Vibrant Violet / Purple
    (44, 179, 186),  # Vibrant Teal
    (242, 169, 53),  # Vibrant Amber
    (120, 194, 66),  # Vibrant Lime
    (82, 102, 224),  # Vibrant Cobalt / Indigo
    (214, 82, 186),  # Vibrant Hot Pink
    (53, 175, 224),  # Vibrant Ocean Cyan
    (235, 126, 61),  # Vibrant Tangerine
    (59, 196, 153),  # Vibrant Mint
    (174, 102, 219),  # Vibrant Orchid
    (219, 79, 79),  # Vibrant Red
    (162, 204, 57),  # Vibrant Pear
)

# CJK Unified Ideographs + extensions + Japanese kana + Korean Hangul.
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x3040, 0x30FF),  # Hiragana / Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2FFFF),  # CJK Extension B–F + supplementary
)

_WHITESPACE_RE = re.compile(r"\s+")
_AVAILABLE_CJK_FONTS: tuple[str, ...] | None = None
_AVAILABLE_LATIN_FONTS: tuple[str, ...] | None = None


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch[0])
    return any(start <= code <= end for start, end in _CJK_RANGES)


def _latin_font_candidates() -> tuple[str, ...]:
    """Return Latin font preferences in priority order (first available wins)."""
    return (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI",
        "Segoe UI Variable",
        "SF Pro Text",
        "Inter",
        "Helvetica Neue",
        "Arial",
    )


def _cjk_font_candidates() -> tuple[str, ...]:
    """Return CJK font preferences in priority order (first available wins)."""
    return (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "PingFang SC",
        "Source Han Sans SC",
        "Noto Sans CJK SC",
        "SimHei",
        "Segoe UI",
    )


def _available_fonts() -> set[str]:
    families = QFontDatabase().families() if hasattr(QFontDatabase(), "families") else set()
    return set(families or [])


def _pick_font(candidates: tuple[str, ...]) -> str:
    available = _available_fonts()
    for name in candidates:
        if not available or name in available:
            return name
    return candidates[-1]


def _resolve_cjk_font() -> str:
    global _AVAILABLE_CJK_FONTS
    if _AVAILABLE_CJK_FONTS is None:
        _AVAILABLE_CJK_FONTS = _cjk_font_candidates()
    return _pick_font(_AVAILABLE_CJK_FONTS)


def _resolve_latin_font() -> str:
    global _AVAILABLE_LATIN_FONTS
    if _AVAILABLE_LATIN_FONTS is None:
        _AVAILABLE_LATIN_FONTS = _latin_font_candidates()
    return _pick_font(_AVAILABLE_LATIN_FONTS)


def _pick_accent(name: str) -> tuple[int, int, int]:
    """Map ``name`` to a stable entry in :data:`_ACCENT_PALETTE`."""
    key = (name or "").strip().lower().encode("utf-8", errors="ignore")
    if not key:
        return _ACCENT_PALETTE[0]
    digest = hashlib.md5(key, usedforsecurity=False).digest()  # noqa: S324 — non-cryptographic
    return _ACCENT_PALETTE[digest[0] % len(_ACCENT_PALETTE)]


def _derive_display_text(name: str) -> str:
    """Pick the most readable 1–2 character label for ``name``."""
    text = (name or "").strip()
    if not text:
        return "?"

    if _is_cjk_char(text[0]):
        return text[0]

    parts = re.split(r"[\s\-_/]+", text)
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        c1 = parts[0][0]
        c2 = parts[1][0]
        if c1.isalnum() and c2.isalnum():
            return (c1 + c2).upper()

    word = parts[0]
    if len(word) >= 2:
        upper_chars = [c for i, c in enumerate(word) if i > 0 and c.isupper()]
        if upper_chars:
            first_char: str = str(word[0])
            second_char: str = str(upper_chars[0])
            if first_char.isalnum() and second_char.isalnum():
                return (first_char + second_char).upper()
        first_char = str(word[0])
        second_char = str(word[1])
        if first_char.isalnum() and second_char.isalnum():
            return (first_char + second_char).upper()

    last_char = str(word[0])
    return last_char.upper() if last_char.isalnum() else last_char


def _lighten(rgb: tuple[int, int, int], factor: float) -> QColor:
    factor = max(0.0, min(1.0, factor))
    return QColor(
        int(rgb[0] + (255 - rgb[0]) * factor),
        int(rgb[1] + (255 - rgb[1]) * factor),
        int(rgb[2] + (255 - rgb[2]) * factor),
    )


def _darken(rgb: tuple[int, int, int], factor: float) -> QColor:
    factor = max(0.0, min(1.0, factor))
    return QColor(
        int(rgb[0] * (1.0 - factor)),
        int(rgb[1] * (1.0 - factor)),
        int(rgb[2] * (1.0 - factor)),
    )


def _draw_background(painter: QPainter, rect: QRectF, base: tuple[int, int, int], theme: str) -> None:
    """Paint a rounded rect with a vertical gradient + subtle top highlight."""
    top = _lighten(base, 0.18 if theme == "dark" else 0.28)
    bottom = _darken(base, 0.12 if theme == "dark" else 0.10)

    gradient = QLinearGradient(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)
    painter.setPen(QtCompat.NoPen)
    painter.setBrush(QBrush(gradient))
    radius = max(2.0, rect.width() * 0.22)
    painter.drawRoundedRect(rect, radius, radius)

    # Soft top highlight: a thin band of translucent white to suggest a
    # glossy surface without being too skeuomorphic.
    highlight_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.45)
    highlight = QLinearGradient(QPointF(0, highlight_rect.top()), QPointF(0, highlight_rect.bottom()))
    highlight.setColorAt(0.0, QColor(255, 255, 255, 60))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(highlight))
    painter.setPen(QtCompat.NoPen)
    painter.drawRoundedRect(highlight_rect, radius, radius)

    # Draw subtle inner border
    painter.setBrush(QtCompat.NoBrush)
    border_color = QColor(255, 255, 255, 30) if theme == "dark" else QColor(0, 0, 0, 20)
    painter.setPen(QPen(border_color, 1))
    border_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    painter.drawRoundedRect(border_rect, radius, radius)


def _draw_glyph(painter: QPainter, rect: QRectF, text: str, is_cjk: bool) -> None:
    """Render ``text`` centred in ``rect`` using the appropriate font family."""
    if not text:
        return

    font = QFont(_resolve_cjk_font() if is_cjk else _resolve_latin_font())
    font.setStyle(QFont.Style.StyleNormal)
    font.setWeight(QFont.Weight.Normal)
    if is_cjk:
        font.setPixelSize(max(10, int(rect.height() * 0.48)))
    elif len(text) >= 2:
        font.setPixelSize(max(10, int(rect.height() * 0.44)))
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 102)
    else:
        font.setPixelSize(max(10, int(rect.height() * 0.52)))
    painter.setFont(font)

    # Soft drop shadow to lift the glyph off the gradient.
    shadow_color = QColor(0, 0, 0, 50)
    shadow_rect = QRectF(rect)
    shadow_rect.translate(0, max(0.5, rect.height() * 0.03))
    painter.setPen(shadow_color)
    painter.drawText(shadow_rect, QtCompat.AlignCenter, text)

    painter.setPen(QColor(255, 255, 255))
    painter.drawText(rect, QtCompat.AlignCenter, text)


@pixmap_cache(
    maxsize=200,
    key=lambda name, size, theme="dark", dpr=1.0: (name, int(size), str(theme or "dark"), float(dpr)),
)
def render_default_icon(
    name: str,
    size: int,
    theme: str = "dark",
    dpr: float = 1.0,
) -> QPixmap:
    """Return a polished fallback icon for an item without a real icon.

    Cached via LRU (maxsize=200) keyed on (name, size, theme, dpr). The
    cache is shared across the launcher popup, the settings icon grid,
    and any other consumer; the underlying ``QPixmap`` is rendered once
    per unique key.

    Args:
        name: Display name of the item.  Used to pick a deterministic accent
            colour and to derive the 1–2 character label shown on the icon.
        size: Edge length of the square pixmap, in device pixels.
        theme: ``"dark"`` or ``"light"`` — controls the gradient lightness and
            the subtle top highlight intensity.
        dpr: Device pixel ratio for High-DPI screens.
    """
    if size <= 0:
        size = 1

    dpr = max(1.0, float(dpr))
    physical_size = int(round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(QtCompat.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QtCompat.Antialiasing, True)
        painter.setRenderHint(QtCompat.TextAntialiasing, True)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        margin = max(1, int(round(size * 0.06)))
        rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)

        accent = _pick_accent(name)
        _draw_background(painter, rect, accent, theme)

        display = _derive_display_text(name)
        is_cjk = bool(display) and _is_cjk_char(display[0])
        _draw_glyph(painter, rect, display, is_cjk)
    finally:
        painter.end()

    return pixmap


def default_icon_cache_key(name: str, size: int, theme: str = "dark", dpr: float = 1.0) -> tuple:
    """Cache key that fully describes the rendered default icon."""
    normalised_name = (name or "").strip().lower()
    return (normalised_name, int(size), str(theme or "dark"), float(dpr))


__all__ = [
    "default_icon_cache_key",
    "render_default_icon",
]
