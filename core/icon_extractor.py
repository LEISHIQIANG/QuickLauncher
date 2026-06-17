"""Icon extraction helpers."""

import ctypes
import hashlib
import logging
import os
import re
import sys
import time
from collections import OrderedDict
from ctypes import wintypes

logger = logging.getLogger(__name__)
_ICON_DEBUG_ENV = "QL_ICON_DEBUG"
_ICON_FAILURE_LOGGED: set[str] = set()

try:
    from qt_compat import (
        QT_LIB,
        QApplication,
        QBrush,  # noqa: F401  # used in fallback rendering helpers
        QColor,
        QFont,  # noqa: F401  # used in fallback rendering helpers
        QFontDatabase,  # noqa: F401  # used in font availability probe
        QIcon,
        QImage,
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
    import win32gui
    import win32ui

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


class IconExtractor:
    """Small LRU-backed icon extraction utility."""

    _cache = OrderedDict()  # type: ignore[var-annotated]
    _cache_timestamps = {}  # type: ignore[var-annotated]
    _MAX_CACHE_SIZE = 150
    _CACHE_TTL_SECONDS = 30 * 60
    _default_icon_cache = {}  # type: ignore[var-annotated]

    @classmethod
    def _diag(cls, message: str, *args):
        if os.environ.get(_ICON_DEBUG_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
            logger.info("[IconDiag] " + message, *args)
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug("[IconDiag] " + message, *args)

    @classmethod
    def _warn_once(cls, key: str, message: str, *args):
        if key in _ICON_FAILURE_LOGGED:
            return
        _ICON_FAILURE_LOGGED.add(key)
        if len(_ICON_FAILURE_LOGGED) > 200:
            _ICON_FAILURE_LOGGED.clear()
        if os.environ.get(_ICON_DEBUG_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
            logger.info("[IconDiag] " + message, *args)
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug("[IconDiag] " + message, *args)

    @staticmethod
    def _is_valid_icon(icon) -> bool:
        return icon is not None and (not hasattr(icon, "isNull") or not icon.isNull())

    @classmethod
    def _is_visually_empty_icon(cls, icon) -> bool:
        if not cls._is_valid_icon(icon):
            return True
        try:
            image = icon.toImage() if isinstance(icon, QPixmap) else icon
            if not cls._is_valid_icon(image):
                return True
            width = image.width()
            height = image.height()
            if width <= 0 or height <= 0:
                return True
            # 使用像素采样代替逐像素遍历，大幅减少 pixelColor() 调用次数
            # 对于 64x64 图标：原来 4096 次 → 采样约 64 次（64 倍加速）
            step = max(2, min(width, height) // 8)
            visible = 0
            checked = 0
            for y in range(0, height, step):
                for x in range(0, width, step):
                    checked += 1
                    if image.pixelColor(x, y).alpha() > 2:
                        visible += 1
                        if visible >= 2:
                            return False
            return checked > 0
        except Exception:
            return False

    @staticmethod
    def _is_shell_path(path: str) -> bool:
        return bool(path) and str(path).strip().lower().startswith("shell:")

    @staticmethod
    def _is_url_like(path: str) -> bool:
        if not path:
            return False
        lowered = str(path).strip().lower()
        return "://" in lowered or lowered.startswith(("http:", "https:", "mailto:", "ms-"))

    @staticmethod
    def _normcase(path: str) -> str:
        if not path:
            return ""
        try:
            return os.path.normcase(os.path.abspath(path))
        except Exception:
            return os.path.normcase(str(path))

    @staticmethod
    def _clean_path(path: str) -> str:
        if not path:
            return ""
        cleaned = str(path).strip().strip('"')
        return os.path.expandvars(os.path.expanduser(cleaned))

    @classmethod
    def _split_resource_location(cls, icon_path: str):
        text = str(icon_path or "").strip()
        if not text or "," not in text:
            return None

        path_part, index_part = text.rsplit(",", 1)
        path_part = cls._clean_path(path_part.strip())
        index_part = index_part.strip()
        if not path_part or not index_part.lstrip("-").isdigit():
            return None
        return path_part, int(index_part)

    @classmethod
    def _is_pixmap_preferred_resource(cls, icon_path: str) -> bool:
        resource_location = cls._split_resource_location(icon_path)
        if resource_location:
            path_part, _ = resource_location
        else:
            path_part = cls._clean_path(icon_path)
        ext = os.path.splitext(path_part)[1].lower()
        return ext in _CUSTOM_RESOURCE_EXTS

    @classmethod
    def _is_regular_associated_target(cls, path: str) -> bool:
        if not path or cls._is_shell_path(path) or cls._is_url_like(path):
            return False
        if os.path.isdir(path):
            return False
        ext = os.path.splitext(str(path))[1].lower()
        if not ext or ext in _TARGET_ICON_EXCLUDED_EXTS:
            return False
        if os.path.exists(path) and not os.path.isfile(path):
            return False
        return True

    @classmethod
    def _make_extract_cache_key(
        cls,
        file_path: str,
        target_path: str = None,  # type: ignore[assignment]
        size: int = 24,
        return_image: bool = False,
        device_pixel_ratio: float = 1.0,
    ) -> str:
        file_path = cls._clean_path(file_path)
        target_path = cls._clean_path(target_path)
        target = target_path or file_path or ""
        if cls._is_regular_associated_target(target):
            ext = os.path.splitext(str(target))[1].lower()
            return f"assoc:{ext}|{size}|{1 if return_image else 0}|{device_pixel_ratio}"
        return (
            f"extract:{cls._normcase(file_path or '')}|"
            f"{cls._normcase(target_path or '')}|{size}|{1 if return_image else 0}|{device_pixel_ratio}"
        )

    @classmethod
    def get_target_cache_id(
        cls,
        file_path: str,
        target_path: str = None,  # type: ignore[assignment]
        size: int = 24,
        device_pixel_ratio: float = 1.0,
    ) -> str:
        return cls._make_extract_cache_key(file_path, target_path, size, False, device_pixel_ratio)

    @classmethod
    def _get_cached(cls, cache_key):
        cached = cls._cache.get(cache_key)
        if cached is None:
            cls._cache_timestamps.pop(cache_key, None)
            return None

        timestamp = cls._cache_timestamps.get(cache_key, 0)
        if timestamp and time.time() - timestamp > cls._CACHE_TTL_SECONDS:
            cls._cache.pop(cache_key, None)
            cls._cache_timestamps.pop(cache_key, None)
            return None

        cls._cache.move_to_end(cache_key)
        cls._cache_timestamps[cache_key] = time.time()
        return cached

    @classmethod
    def _render_square_icon(cls, source, size: int, return_image: bool = False):
        if not cls._is_valid_icon(source):
            return None

        image = source.toImage() if isinstance(source, QPixmap) else source
        if not cls._is_valid_icon(image):
            return None

        canvas = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)  # type: ignore[unused-ignore, attr-defined]
        scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)  # type: ignore[unused-ignore, attr-defined]

        painter = QPainter(canvas)
        try:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
        except Exception as exc:
            logger.debug("设置合成模式失败: %s", exc, exc_info=True)
        painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()

        cls._diag(
            "render source=%s size=%s return_image=%s src=%sx%s scaled=%sx%s",
            type(source).__name__,
            size,
            return_image,
            image.width(),
            image.height(),
            scaled.width(),
            scaled.height(),
        )

        if return_image:
            return canvas
        return QPixmap.fromImage(canvas)

    @classmethod
    def _remember_cache(cls, cache_key, value):
        cls._cache[cache_key] = value
        cls._cache.move_to_end(cache_key)
        cls._cache_timestamps[cache_key] = time.time()
        while len(cls._cache) > cls._MAX_CACHE_SIZE:
            old_key, _ = cls._cache.popitem(last=False)
            cls._cache_timestamps.pop(old_key, None)

    @classmethod
    def clear_expired_cache(cls, level: str = "light"):
        """Clear expired cache entries. Level controls aggression:
        - light:  TTL-based (default 30 min)
        - moderate: 5 min TTL
        - critical:  clear everything
        """
        if level == "critical":
            count = len(cls._cache)
            cls.clear_cache()
            return count

        ttl = 300 if level == "moderate" else cls._CACHE_TTL_SECONDS  # 5 min for moderate
        now = time.time()
        expired = [key for key, timestamp in cls._cache_timestamps.items() if timestamp and now - timestamp > ttl]
        for key in expired:
            cls._cache.pop(key, None)
            cls._cache_timestamps.pop(key, None)
        return len(expired)

    @classmethod
    def get_cache_stats(cls) -> dict:
        cls.clear_expired_cache()
        return {
            "cache_size": len(cls._cache),
            "default_icon_cache_size": len(cls._default_icon_cache),
            "max_cache_size": cls._MAX_CACHE_SIZE,
            "ttl_seconds": cls._CACHE_TTL_SECONDS,
        }

    @classmethod
    def extract(
        cls,
        file_path: str,
        target_path: str = None,  # type: ignore[assignment]
        size: int = 24,
        return_image: bool = False,
        fallback_to_default: bool = True,
        device_pixel_ratio: float = 1.0,
    ):
        """Extract the icon for a launch target."""
        if not QT_AVAILABLE:
            return None
        try:
            if QApplication.instance() is None:
                return None
        except Exception:
            return None

        file_path = cls._clean_path(file_path)
        target_path = cls._clean_path(target_path or file_path)
        cls._diag(
            "extract start file=%s target=%s size=%s dpr=%s return_image=%s fallback=%s",
            file_path,
            target_path,
            size,
            device_pixel_ratio,
            return_image,
            fallback_to_default,
        )
        if not file_path and not target_path:
            dpr = max(1.0, float(device_pixel_ratio or 1.0))
            return cls._create_default_icon(size, dpr=dpr)

        # Normalize scale factor and calculate the required physical pixel size
        dpr = max(1.0, float(device_pixel_ratio or 1.0))
        physical_size = int(round(size * dpr))

        cache_key = cls._make_extract_cache_key(file_path, target_path, size, return_image, dpr)
        cached = cls._get_cached(cache_key)
        if cached is not None:
            cls._diag(
                "cache hit key=%s size=%s return_image=%s path=%s",
                cache_key,
                size,
                return_image,
                target_path or file_path,
            )
            return cached

        result = cls._extract_target_uncached(file_path, target_path, physical_size, return_image)
        if cls._is_valid_icon(result):
            try:
                result.setDevicePixelRatio(dpr)
            except Exception as exc:
                logger.debug("设置图标设备像素比失败: %s", exc, exc_info=True)
            cls._remember_cache(cache_key, result)
            cls._diag(
                "extract ok key=%s size=%s physical_size=%s return_image=%s image=%sx%s",
                cache_key,
                size,
                physical_size,
                return_image,
                result.width(),
                result.height(),
            )
            return result

        if fallback_to_default:
            cls._warn_once(
                cache_key,
                "extract failed, using default icon path=%s target=%s size=%s return_image=%s",
                file_path,
                target_path,
                size,
                return_image,
            )
            name = None
            for path in (target_path, file_path):
                if path:
                    try:
                        name = os.path.splitext(os.path.basename(path))[0]
                        if name:
                            break
                    except Exception as exc:
                        logger.debug("提取文件名失败: %s", exc, exc_info=True)
            default_icon = cls._create_default_icon(size, name, dpr)  # type: ignore[arg-type]
            return default_icon
        cls._warn_once(
            cache_key,
            "extract failed without default path=%s target=%s size=%s return_image=%s",
            file_path,
            target_path,
            size,
            return_image,
        )
        return None

    @classmethod
    def _extract_target_uncached(
        cls,
        file_path: str,
        target_path: str,
        size: int,
        return_image: bool = False,
    ):
        for path in (target_path, file_path):
            if cls._is_shell_path(path):
                cls._diag("extract branch=shell path=%s size=%s", path, size)
                result = cls._extract_shell_pidl(path, size, return_image=return_image)
                if cls._is_valid_icon(result):
                    cls._diag("source=shell-pidl path=%s size=%s", path, size)
                    return result

        if cls._is_regular_associated_target(target_path):
            cls._diag("extract branch=assoc target=%s size=%s", target_path, size)
            result = cls._extract_associated_file_icon(
                target_path,
                size,
                return_image=return_image,
            )
            if cls._is_valid_icon(result):
                cls._diag("source=assoc ext=%s size=%s", os.path.splitext(str(target_path))[1].lower(), size)
                return result

        paths_to_try = []
        for path in (target_path, file_path):
            if path and path not in paths_to_try and (os.path.exists(path) or os.path.isdir(path)):
                paths_to_try.append(path)

        for path in paths_to_try:
            ext = os.path.splitext(str(path))[1].lower()
            cls._diag("extract probe path=%s ext=%s size=%s", path, ext, size)
            if ext in _CUSTOM_RESOURCE_EXTS:
                result = cls._extract_from_resource(
                    path,
                    0,
                    size,
                    return_image=return_image,
                )
                if cls._is_valid_icon(result) and not cls._is_visually_empty_icon(result):
                    cls._diag("source=resource-preferred path=%s index=0 size=%s", path, size)
                    return result

            result = cls._extract_win32(path, size, return_image=return_image)
            if cls._is_valid_icon(result):
                cls._diag("source=shgetfileinfo path=%s size=%s", path, size)
                return result

        return None

    @classmethod
    def _extract_associated_file_icon(
        cls,
        path: str,
        size: int,
        return_image: bool = False,
    ):
        ext = os.path.splitext(str(path))[1].lower()
        if not ext:
            return None

        probe_name = f"file{ext}"
        result = cls._extract_win32(
            probe_name,
            size,
            return_image=return_image,
            use_file_attributes=True,
        )
        if cls._is_valid_icon(result):
            return result

        return None

    @classmethod
    def _extract_win32(
        cls,
        path: str,
        size: int,
        return_image: bool = False,
        use_file_attributes: bool = False,
    ):
        if not QT_AVAILABLE or sys.platform != "win32":
            return None

        try:
            cls._diag(
                "win32 start path=%s size=%s return_image=%s file_attributes=%s",
                path,
                size,
                return_image,
                use_file_attributes,
            )
            shfi = SHFILEINFO()
            flags = SHGFI_ICON | SHGFI_LARGEICON
            attrs = 0
            if use_file_attributes:
                flags |= SHGFI_USEFILEATTRIBUTES
                attrs = FILE_ATTRIBUTE_NORMAL

            sh_get_file_info = _SHGETFILEINFO_PROTO(("SHGetFileInfoW", ctypes.windll.shell32))
            result = sh_get_file_info(
                path,
                attrs,
                ctypes.byref(shfi),
                ctypes.sizeof(shfi),
                flags,
            )
            if result and shfi.hIcon:
                hicon = shfi.hIcon
                try:
                    icon = cls._hicon_to_pixmap(hicon, size, return_image)
                    cls._diag(
                        "win32 result path=%s hicon=%s icon_valid=%s empty=%s",
                        path,
                        bool(hicon),
                        cls._is_valid_icon(icon),
                        cls._is_visually_empty_icon(icon),
                    )
                    if icon and not cls._is_visually_empty_icon(icon):
                        return icon
                finally:
                    cls._destroy_icon(hicon)
        except Exception as e:
            logger.debug("SHGetFileInfo failed: %s", e)

        if not use_file_attributes:
            resource_icon = cls._extract_from_resource(
                path,
                0,
                size,
                return_image=return_image,
            )
            if cls._is_valid_icon(resource_icon) and not cls._is_visually_empty_icon(resource_icon):
                return resource_icon

        return None

    @classmethod
    def _extract_shell_pidl(
        cls,
        shell_path: str,
        size: int,
        return_image: bool = False,
    ):
        if not QT_AVAILABLE or sys.platform != "win32":
            return None
        try:
            SHParseDisplayName = ctypes.windll.shell32.SHParseDisplayName
            SHParseDisplayName.argtypes = [
                wintypes.LPCWSTR,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
            ]
            pidl = ctypes.c_void_p()
            sfgao = ctypes.c_ulong()
            hr = SHParseDisplayName(shell_path, None, ctypes.byref(pidl), 0, ctypes.byref(sfgao))
            if hr != 0 or not pidl.value:
                return None
            try:
                shfi = SHFILEINFO()
                sh_get_file_info = _SHGETFILEINFO_PROTO(("SHGetFileInfoW", ctypes.windll.shell32))
                result = sh_get_file_info(
                    pidl.value,
                    0,
                    ctypes.byref(shfi),
                    ctypes.sizeof(shfi),
                    SHGFI_ICON | SHGFI_LARGEICON | SHGFI_PIDL,
                )
                if result and shfi.hIcon:
                    hicon = shfi.hIcon
                    try:
                        icon = cls._hicon_to_pixmap(
                            hicon,
                            size,
                            return_image=return_image,
                        )
                        return icon
                    finally:
                        cls._destroy_icon(hicon)
            finally:
                free = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)(("CoTaskMemFree", ctypes.windll.ole32))
                free(pidl.value)
        except Exception as e:
            logger.debug("Shell PIDL icon extraction failed: %s", e)
        return None

    @staticmethod
    def _destroy_icon(hicon):
        if not hicon:
            return
        try:
            destroy_icon = ctypes.windll.user32.DestroyIcon
            destroy_icon.argtypes = [wintypes.HICON]
            destroy_icon.restype = wintypes.BOOL
            destroy_icon(hicon)
        except Exception as exc:
            logger.debug("销毁图标句柄失败: %s", exc, exc_info=True)

    @classmethod
    def _hicon_to_pixmap(
        cls,
        hicon,
        size: int,
        return_image: bool = False,
    ):
        if not QT_AVAILABLE:
            return None

        hicon_handle = hicon.value if hasattr(hicon, "value") else hicon
        if not hicon_handle:
            return None

        # 1. 优先尝试 Qt 原生高效 C++ 接口 QImage.fromHICON
        try:
            if hasattr(QImage, "fromHICON"):
                image = QImage.fromHICON(hicon_handle)
                if image and not image.isNull():
                    cls._diag(
                        "hicon native qimage size=%s return_image=%s image=%sx%s",
                        size,
                        return_image,
                        image.width(),
                        image.height(),
                    )
                    return cls._render_square_icon(image, size, return_image=return_image)
        except Exception as e:
            logger.debug("QImage.fromHICON failed: %s", e)

        # 2. 备选尝试 QtWin 接口
        if not return_image:
            try:
                from qt_compat import QtWin

                pixmap = QtWin.fromHICON(hicon_handle)  # type: ignore[unused-ignore, call-arg]
                if pixmap and not pixmap.isNull():
                    cls._diag(
                        "hicon qtwin size=%s return_image=%s pixmap=%sx%s",
                        size,
                        return_image,
                        pixmap.width(),
                        pixmap.height(),
                    )
                    return cls._render_square_icon(pixmap, size, return_image=return_image)
            except Exception as e:
                logger.debug("QtWin.fromHICON failed: %s", e)

        # 3. 终极备选：有 Win32 接口时，直接读取位图 Bits 字节流，绕过 Pillow PNG 转换
        if HAS_WIN32:
            hbm_mask = None
            hbm_color = None
            hdc = None
            hdc_mem = None
            hdc_mem2 = None
            old_bmp = None
            try:
                info = win32gui.GetIconInfo(hicon_handle)
                hbm_mask = info[3]
                hbm_color = info[4]
                if not hbm_color:
                    if hbm_mask:
                        win32gui.DeleteObject(hbm_mask)
                        hbm_mask = None
                    return None

                bmp = win32ui.CreateBitmapFromHandle(hbm_color)
                bmp_info = bmp.GetInfo()
                width = bmp_info["bmWidth"]
                height = bmp_info["bmHeight"]

                hdc = win32gui.GetDC(0)
                hdc_mem = win32ui.CreateDCFromHandle(hdc)
                hdc_mem2 = hdc_mem.CreateCompatibleDC()
                old_bmp = hdc_mem2.SelectObject(bmp)
                bmp_str = bmp.GetBitmapBits(True)

                # 核心改进：直接用 BGRA 字节数据流构造 QImage，并深拷贝脱离底层句柄依赖
                raw_image = QImage(bmp_str, width, height, QImage.Format_ARGB32)
                image = raw_image.copy()  # 必须深拷贝，防止 C++ 底层引用在函数返回时野指针崩溃

                cls._diag(
                    "hicon win32 raw bits size=%s return_image=%s image=%sx%s",
                    size,
                    return_image,
                    image.width(),
                    image.height(),
                )
                return cls._render_square_icon(image, size, return_image=return_image)
            except Exception as e:
                logger.debug("win32 raw bitmap extraction failed: %s", e)
            finally:
                try:
                    if hdc_mem2 is not None and old_bmp is not None:
                        hdc_mem2.SelectObject(old_bmp)
                except Exception as exc:
                    logger.debug("恢复位图对象失败: %s", exc, exc_info=True)
                try:
                    if hdc_mem2 is not None:
                        hdc_mem2.DeleteDC()
                except Exception as exc:
                    logger.debug("删除内存DC2失败: %s", exc, exc_info=True)
                try:
                    if hdc_mem is not None:
                        hdc_mem.DeleteDC()
                except Exception as exc:
                    logger.debug("删除内存DC失败: %s", exc, exc_info=True)
                try:
                    if hdc is not None:
                        win32gui.ReleaseDC(0, hdc)
                except Exception as exc:
                    logger.debug("释放设备上下文失败: %s", exc, exc_info=True)
                try:
                    if hbm_color is not None:
                        win32gui.DeleteObject(hbm_color)
                except Exception as exc:
                    logger.debug("删除颜色位图失败: %s", exc, exc_info=True)
                try:
                    if hbm_mask is not None:
                        win32gui.DeleteObject(hbm_mask)
                except Exception as exc:
                    logger.debug("删除掩码位图失败: %s", exc, exc_info=True)

        return None

    @classmethod
    def _create_default_icon(cls, size: int, name: str = None, dpr: float = 1.0):  # type: ignore[assignment]
        if not QT_AVAILABLE:
            return None

        cache_key = _default_icon_cache_key(name or "", size, dpr)
        cached = cls._default_icon_cache.get(cache_key)
        if cached is not None:
            return cached

        pixmap = _render_default_icon_pixmap(name or "", size, dpr)
        if pixmap is not None:
            cls._default_icon_cache[cache_key] = pixmap
        return pixmap

    @classmethod
    def get_icon_count(cls, path: str) -> int:
        path = cls._clean_path(path)
        if not path or not os.path.exists(path):
            return 0

        try:
            extract_icon_ex = ctypes.windll.shell32.ExtractIconExW
            extract_icon_ex.argtypes = [
                wintypes.LPCWSTR,
                ctypes.c_int,
                ctypes.POINTER(wintypes.HICON),
                ctypes.POINTER(wintypes.HICON),
                wintypes.UINT,
            ]
            extract_icon_ex.restype = wintypes.UINT
            cnt = extract_icon_ex(path, -1, None, None, 0)
            if cnt > 0:
                return cnt  # type: ignore[no-any-return]
        except Exception as e:
            logger.debug("Failed to count icons: %s", e)

        return 0

    @classmethod
    def _extract_from_resource(
        cls,
        path: str,
        index: int,
        size: int,
        return_image: bool = False,
    ):
        path = cls._clean_path(path)
        if not path:
            return None
        try:
            cls._diag(
                "resource start path=%s index=%s size=%s return_image=%s",
                path,
                index,
                size,
                return_image,
            )
            phicon = wintypes.HICON()
            piconid = wintypes.UINT()
            private_extract_icons = ctypes.windll.user32.PrivateExtractIconsW
            private_extract_icons.argtypes = [
                wintypes.LPCWSTR,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(wintypes.HICON),
                ctypes.POINTER(wintypes.UINT),
                wintypes.UINT,
                wintypes.UINT,
            ]
            private_extract_icons.restype = wintypes.UINT

            ret = private_extract_icons(
                path,
                index,
                size,
                size,
                ctypes.byref(phicon),
                ctypes.byref(piconid),
                1,
                0,
            )

            if ret > 0 and phicon:
                try:
                    result = cls._hicon_to_pixmap(
                        phicon,
                        size,
                        return_image,
                    )
                    cls._diag(
                        "resource result path=%s index=%s ret=%s valid=%s empty=%s",
                        path,
                        index,
                        ret,
                        cls._is_valid_icon(result),
                        cls._is_visually_empty_icon(result),
                    )
                    return result
                finally:
                    cls._destroy_icon(phicon)
        except Exception as e:
            logger.debug("PrivateExtractIcons failed (%s,%s): %s", path, index, e)

        try:
            extract_icon = ctypes.windll.shell32.ExtractIconW
            extract_icon.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
            extract_icon.restype = wintypes.HICON
            hicon = extract_icon(None, path, index)
            if hicon and hicon > 1:
                try:
                    result = cls._hicon_to_pixmap(
                        hicon,
                        size,
                        return_image,
                    )
                    cls._diag(
                        "resource fallback result path=%s index=%s valid=%s empty=%s",
                        path,
                        index,
                        cls._is_valid_icon(result),
                        cls._is_visually_empty_icon(result),
                    )
                    if result:
                        return result
                finally:
                    cls._destroy_icon(hicon)
        except Exception as e:
            logger.debug("ExtractIconW failed (%s,%s): %s", path, index, e)

        return None

    @classmethod
    def from_file(
        cls,
        icon_path: str,
        size: int = 24,
        return_image: bool = False,
        device_pixel_ratio: float = 1.0,
    ):
        """Load a custom icon resource exactly as specified by icon_path."""
        if not QT_AVAILABLE or not icon_path:
            return None

        icon_path = cls._clean_path(icon_path)
        resource_location = cls._split_resource_location(icon_path)
        cls._diag(
            "from_file start path=%s size=%s return_image=%s resource=%s",
            icon_path,
            size,
            return_image,
            resource_location,
        )
        if resource_location:
            path_part, icon_index = resource_location
            icon_path = f"{path_part},{icon_index}"

        cache_key = f"from_file:{icon_path}|{size}|{1 if return_image else 0}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached

        if resource_location:
            result = cls._extract_from_resource(
                path_part,
                icon_index,
                size,
                return_image,
            )
            if cls._is_valid_icon(result):
                cls._remember_cache(cache_key, result)
                cls._diag("custom resource ok path=%s index=%s size=%s", path_part, icon_index, size)
            return result

        if not os.path.exists(icon_path):
            return None

        try:
            ext = os.path.splitext(icon_path)[1].lower()

            if ext == ".ico":
                icon = QIcon(icon_path)
                if not icon.isNull():
                    result = cls._render_square_icon(icon.pixmap(size, size), size, return_image=return_image)
                    cls._remember_cache(cache_key, result)
                    cls._diag("custom ico ok path=%s size=%s", icon_path, size)
                    return result

            if ext in _CUSTOM_IMAGE_EXTS:
                if return_image:
                    image = QImage(icon_path)
                    if not image.isNull():
                        result = cls._render_square_icon(image, size, return_image=True)
                        cls._remember_cache(cache_key, result)
                        cls._diag("custom image ok path=%s size=%s", icon_path, size)
                        return result
                else:
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        result = cls._render_square_icon(pixmap, size, return_image=False)
                        cls._remember_cache(cache_key, result)
                        cls._diag("custom pixmap ok path=%s size=%s", icon_path, size)
                        return result

            if ext in _CUSTOM_RESOURCE_EXTS:
                result = cls._extract_from_resource(
                    icon_path,
                    0,
                    size,
                    return_image,
                )
                if not cls._is_valid_icon(result) or cls._is_visually_empty_icon(result):
                    result = cls._extract_win32(icon_path, size, return_image=return_image)
                if cls._is_valid_icon(result):
                    cls._remember_cache(cache_key, result)
                    cls._diag("custom executable icon ok path=%s size=%s", icon_path, size)
                return result

        except Exception as e:
            logger.debug("Failed to load icon file: %s", e)

        return None

    @staticmethod
    def invert_pixmap(pixmap):
        if not QT_AVAILABLE or not pixmap or pixmap.isNull():
            return pixmap
        image = pixmap.toImage()
        IconExtractor._invert_image_rgb_in_place(image)
        return QPixmap.fromImage(image)

    @staticmethod
    def invert_image(image):
        if not QT_AVAILABLE or not image or image.isNull():
            return image
        result = image.copy()
        IconExtractor._invert_image_rgb_in_place(result)
        return result

    @staticmethod
    def _invert_image_rgb_in_place(image):
        try:
            image.invertPixels(QImage.InvertRgb)
            return
        except Exception:
            logger.debug("QImage.invertPixels unavailable; falling back to pixel loop", exc_info=True)

        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                inverted = QColor(
                    255 - pixel.red(),
                    255 - pixel.green(),
                    255 - pixel.blue(),
                    pixel.alpha(),
                )
                image.setPixelColor(x, y, inverted)

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
        cls._cache_timestamps.clear()
        cls._default_icon_cache.clear()


def should_invert_icon(item, current_theme: str) -> bool:
    # 新版逻辑：根据当前主题检查对应的反转标志
    if current_theme == "light":
        return getattr(item, "icon_invert_light", False)
    elif current_theme == "dark":
        return getattr(item, "icon_invert_dark", False)
    return False


def get_icon_dir() -> str:
    from .data_manager import DataManager

    data_manager = DataManager()
    return str(data_manager.icons_dir)
