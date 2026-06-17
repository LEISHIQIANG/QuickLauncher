"""Centralized UI font helpers."""

import logging

from ui.utils.ui_scale import font_px as _font_px

logger = logging.getLogger(__name__)

FALLBACK_FONT_FAMILIES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Source Han Sans SC",
    "Segoe UI",
    "Arial",
)
GLOBAL_FONT_FAMILY = FALLBACK_FONT_FAMILIES[0]


def _available_font_family() -> str:
    try:
        from qt_compat import QApplication, QFontDatabase

        if QApplication.instance() is None:
            return GLOBAL_FONT_FAMILY

        installed = set(QFontDatabase().families())
        for family in FALLBACK_FONT_FAMILIES:
            if family in installed:
                return family
    except Exception as exc:
        logger.debug("Font database lookup failed: %s", exc)
    return GLOBAL_FONT_FAMILY


def get_font_family():
    return _available_font_family()


def get_font_css():
    families = ", ".join(f"'{family}'" for family in FALLBACK_FONT_FAMILIES[:-1])
    return f"font-family: {families}, sans-serif;"


def get_font_css_with_size(size: int, weight: int = 400):
    scaled_size = _font_px(size)
    return f"{get_font_css()} font-size: {scaled_size}px; font-weight: {weight};"


def get_qfont(pixel_size: int = 14, weight: int = 400):
    from qt_compat import QFont

    scaled_px = _font_px(pixel_size)
    font = QFont(_available_font_family())
    font.setPixelSize(scaled_px)
    font.setWeight(QFont.Weight.Normal if weight <= 500 else QFont.Weight.Medium)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setKerning(True)
    return font


def apply_app_font(pixel_size: int = 13, weight: int = 400) -> None:
    """Apply the current UI scale to QApplication's inherited default font."""
    from qt_compat import QApplication

    app = QApplication.instance()
    if app is not None:
        app.setFont(get_qfont(pixel_size, weight))  # type: ignore[unused-ignore, attr-defined]


def tune_font_rendering(widget, pixel_size: int | None = None, weight: int | None = None, recursive: bool = False):
    """Apply consistent UI font rendering to a widget tree."""
    from qt_compat import QFont, QWidget

    targets = [widget]
    if recursive and isinstance(widget, QWidget):
        targets.extend(widget.findChildren(QWidget))

    for target in targets:
        try:
            font = target.font()
            font.setFamily(_available_font_family())
            if pixel_size is not None:
                font.setPixelSize(_font_px(pixel_size))
            if weight is not None:
                font.setWeight(QFont.Weight.Normal if weight <= 500 else QFont.Weight.Medium)
            font.setStyleHint(QFont.StyleHint.SansSerif)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            font.setKerning(True)
            target.setFont(font)
        except Exception as exc:
            logger.debug("Failed to tune font rendering for %r: %s", target, exc)
