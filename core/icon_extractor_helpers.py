"""Icon extraction helpers and constants extracted from icon_extractor.py."""

import ctypes
import hashlib
import logging
import re
from ctypes import wintypes

logger = logging.getLogger(__name__)
_ICON_DEBUG_ENV = "QL_ICON_DEBUG"
_ICON_FAILURE_LOGGED: set[str] = set()

try:
    from qt_compat import (
        QT_LIB,
        QBrush,  # noqa: F401  # used in fallback rendering helpers
        QColor,
        QFont,  # noqa: F401  # used in fallback rendering helpers
        QFontDatabase,  # noqa: F401  # used in font availability probe
        QLinearGradient,  # noqa: F401  # used in fallback rendering helpers
        QPainter,
        QPen,
        QPixmap,
        QPointF,  # noqa: F401  # used in fallback rendering helpers
        QRectF,  # noqa: F401  # used in fallback rendering helpers
        Qt,
    )

    QT_AVAILABLE = True
    logger.debug("icon_extractor: using %s", QT_LIB)
except Exception as e:
    QT_AVAILABLE = False
    logger.debug("Qt compatibility layer is unavailable: %s", e)


HAS_WIN32 = False
try:
    import win32gui as win32gui  # noqa: F401  # capability probe
    import win32ui as win32ui  # noqa: F401  # capability probe

    HAS_WIN32 = True
except ImportError:
    logger.debug("win32gui is not installed; icon extraction will use ctypes/Qt fallbacks")


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HANDLE),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


SHGFI_ICON = 0x100
SHGFI_LARGEICON = 0x0
SHGFI_USEFILEATTRIBUTES = 0x10
SHGFI_PIDL = 0x8
FILE_ATTRIBUTE_NORMAL = 0x80

_TARGET_ICON_EXCLUDED_EXTS = {".exe", ".lnk", ".url"}
_CUSTOM_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}
_CUSTOM_RESOURCE_EXTS = {".exe", ".dll"}

# CJK Unified Ideographs + Japanese kana + Korean Hangul ranges.
# Kept identical to ui.utils.default_icon_renderer._CJK_RANGES so the
# fallback icon looks the same in the launcher, the settings grid, and
# any place :class:`IconExtractor` is asked to produce a default icon.
_DEFAULT_ICON_CJK_RANGES = (
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FFFF),
)

_DEFAULT_ICON_ACCENT_PALETTE = (
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

_LATIN_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI",
    "Segoe UI Variable",
    "SF Pro Text",
    "Inter",
    "Helvetica Neue",
    "Arial",
)
_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "SimHei",
    "Segoe UI",
)

_WHITESPACE_RE = re.compile(r"\s+")
_DEFAULT_ICON_AVAILABLE_FONTS: set[str] | None = None


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch[0])
    return any(start <= code <= end for start, end in _DEFAULT_ICON_CJK_RANGES)


def _default_icon_available_fonts() -> set[str]:
    global _DEFAULT_ICON_AVAILABLE_FONTS
    if _DEFAULT_ICON_AVAILABLE_FONTS is None:
        families = QFontDatabase().families() if hasattr(QFontDatabase(), "families") else set()
        _DEFAULT_ICON_AVAILABLE_FONTS = set(families or [])
    return _DEFAULT_ICON_AVAILABLE_FONTS


def _pick_default_icon_font(candidates: tuple[str, ...]) -> str:
    available = _default_icon_available_fonts()
    for name in candidates:
        if not available or name in available:
            return name
    return candidates[-1]


def _pick_default_accent(name: str) -> tuple[int, int, int]:
    text = (name or "").strip().lower().encode("utf-8", errors="ignore")
    if not text:
        return _DEFAULT_ICON_ACCENT_PALETTE[0]
    digest = hashlib.md5(text, usedforsecurity=False).digest()  # noqa: S324 — non-cryptographic
    return _DEFAULT_ICON_ACCENT_PALETTE[digest[0] % len(_DEFAULT_ICON_ACCENT_PALETTE)]


def _derive_default_icon_text(name: str) -> str:
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


def _shade_channel(channel: int, target: int, factor: float) -> int:
    return int(channel + (target - channel) * factor)


def _lighten(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    factor = max(0.0, min(1.0, factor))
    return (
        _shade_channel(rgb[0], 255, factor),
        _shade_channel(rgb[1], 255, factor),
        _shade_channel(rgb[2], 255, factor),
    )


def _darken(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    factor = max(0.0, min(1.0, factor))
    return (
        int(rgb[0] * (1.0 - factor)),
        int(rgb[1] * (1.0 - factor)),
        int(rgb[2] * (1.0 - factor)),
    )


def _paint_default_background(painter: "QPainter", rect: QRectF, base: tuple[int, int, int]) -> None:
    top = _lighten(base, 0.22)
    bottom = _darken(base, 0.10)

    gradient = QLinearGradient(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
    gradient.setColorAt(0.0, QColor(*top))
    gradient.setColorAt(1.0, QColor(*bottom))
    painter.setPen(Qt.NoPen)  # type: ignore[attr-defined]
    painter.setBrush(QBrush(gradient))
    radius = max(2.0, rect.width() * 0.22)
    painter.drawRoundedRect(rect, radius, radius)

    highlight_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.45)
    highlight = QLinearGradient(QPointF(0, highlight_rect.top()), QPointF(0, highlight_rect.bottom()))
    highlight.setColorAt(0.0, QColor(255, 255, 255, 60))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(highlight))
    painter.drawRoundedRect(highlight_rect, radius, radius)

    # Draw subtle inner border
    painter.setBrush(Qt.NoBrush)  # type: ignore[attr-defined]
    border_color = QColor(255, 255, 255, 30)
    painter.setPen(QPen(border_color, 1))
    border_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    painter.drawRoundedRect(border_rect, radius, radius)


def _paint_default_glyph(painter: "QPainter", rect: QRectF, text: str) -> None:
    if not text:
        return

    is_cjk = _is_cjk_char(text[0])
    font = QFont(_pick_default_icon_font(_CJK_FONT_CANDIDATES if is_cjk else _LATIN_FONT_CANDIDATES))
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

    shadow_color = QColor(0, 0, 0, 50)
    shadow_rect = QRectF(rect)
    shadow_rect.translate(0, max(0.5, rect.height() * 0.03))
    painter.setPen(shadow_color)
    painter.drawText(shadow_rect, Qt.AlignCenter, text)  # type: ignore[attr-defined]

    painter.setPen(QColor(255, 255, 255))
    painter.drawText(rect, Qt.AlignCenter, text)  # type: ignore[attr-defined]


def _render_default_icon_pixmap(name: str, size: int, dpr: float = 1.0) -> "QPixmap | None":
    """Render the polished fallback icon.  Returns ``None`` when Qt is unavailable."""
    if not QT_AVAILABLE or size <= 0:
        return None

    dpr = max(1.0, float(dpr))
    physical_size = int(round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.transparent)  # type: ignore[attr-defined]
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        margin = max(1, int(round(size * 0.06)))
        rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)

        accent = _pick_default_accent(name)
        _paint_default_background(painter, rect, accent)

        display = _derive_default_icon_text(name)
        _paint_default_glyph(painter, rect, display)
    finally:
        painter.end()

    return pixmap


def _default_icon_cache_key(name: str, size: int, dpr: float = 1.0) -> tuple:
    return ((name or "").strip().lower(), int(size), float(dpr))


_SHGETFILEINFO_PROTO = ctypes.WINFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(SHFILEINFO),
    wintypes.UINT,
    wintypes.UINT,
)
