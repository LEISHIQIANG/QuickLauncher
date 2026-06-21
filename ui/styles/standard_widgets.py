"""Standard widget base classes for QuickLauncher UI.

This module hosts the *optional* :class:`ThemedButton`, :class:`ThemedLabel`,
:class:`ThemedLineEdit` and :class:`ThemedDialog` classes referenced in
§3.4 of ``UI_OPTIMIZATION_PLAN.md``. The classes are designed as a
starting point for **new** components; existing widgets continue to
inherit from their current parents so we don't break the visual baseline.

Mixins (:class:`FocusRingMixin`, :class:`PixelSnapMixin`) provide opt-in
optical quality-of-life improvements. New code is encouraged to mix them
in; legacy code can adopt them incrementally.
"""

from __future__ import annotations

import logging

from qt_compat import (
    QCloseEvent,
    QColor,
    QDialog,
    QHideEvent,
    QLabel,
    QLineEdit,
    QPainter,
    QPushButton,
    QtCompat,
    QWidget,
)
from ui.styles.design_tokens import BorderScale, RadiusScale, surface, text
from ui.utils.interruptible_animation import stop_named_animations
from ui.utils.pixel_snap import make_cosmetic_pen, snap_rect

logger = logging.getLogger(__name__)

__all__ = [
    "ThemedButton",
    "ThemedLabel",
    "ThemedLineEdit",
    "ThemedDialog",
    "FocusRingMixin",
    "PixelSnapMixin",
]


class FocusRingMixin:
    """Mixin that draws a 1-px cosmetic focus ring on top of the widget.

    The ring is drawn in :meth:`paintEvent` only when ``hasFocus()`` is
    true. Subclasses must call ``super().paintEvent(event)`` first.
    """

    focus_ring_inset: float = 2.0
    focus_ring_radius: int = RadiusScale.md

    def _focus_ring_color(self) -> QColor:
        theme = getattr(self, "theme", "dark")
        if theme == "dark":
            return QColor(BorderScale.focus_dark)
        return QColor(BorderScale.focus)

    def _draw_focus_ring(self, painter: QPainter) -> None:
        if not isinstance(self, QWidget):
            return
        try:
            from ui.runtime_settings import current_settings
            from ui.styles.l3_features import show_focus_ring

            settings = current_settings()
            if not show_focus_ring(settings):
                return
        except Exception as exc:
            logger.debug("L3 focus-ring lookup failed: %s", exc, exc_info=True)
        if not self.hasFocus():
            return
        rect = self.rect()
        snapped = snap_rect(rect, inset=self.focus_ring_inset)
        pen = make_cosmetic_pen(self._focus_ring_color(), 1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(
            snapped,
            float(self.focus_ring_radius),
            float(self.focus_ring_radius),
        )
        painter.restore()


class PixelSnapMixin:
    """Mixin that forces :class:`QPainter` antialiasing on every paint.

    Combine with :class:`FocusRingMixin` to get the same crisp output
    that ``ui/utils/pixel_snap`` documents.
    """

    def _enable_aa(self, painter: QPainter) -> None:
        if not isinstance(self, QWidget):
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)


class ThemedButton(QPushButton):
    """Standard themed push button.

    Uses :class:`SurfaceScale` and :class:`TextScale` tokens instead of
    inline ``QColor`` literals. New buttons should inherit from this
    class to ensure consistent look-and-feel.
    """

    def __init__(self, text_value: str = "", parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(text_value, parent)
        self.theme = theme
        self.setAttribute(QtCompat.WA_StyledBackground, False)

    def accent_color(self) -> QColor:
        return surface(self.theme, "bg_elevated")

    def foreground_color(self) -> QColor:
        return text(self.theme, "primary")


class ThemedLabel(QLabel):
    """Standard themed label.

    Inherits from the i18n-aware ``QLabel`` exported by :mod:`qt_compat`.
    """

    def __init__(self, text_value: str = "", parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(text_value, parent)
        self.theme = theme


class ThemedLineEdit(QLineEdit):
    """Standard themed line edit with a 1-px cosmetic border."""

    def __init__(self, parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(QtCompat.WA_StyledBackground, False)

    def border_color(self) -> QColor:
        return surface(self.theme, "bg_elevated")


class ThemedDialog(QDialog):
    """Standard themed dialog.

    Subclasses can override :meth:`_accent_color` / :meth:`_background_color`
    to tweak the paint event without duplicating token plumbing.
    """

    def __init__(self, parent: QWidget | None = None, theme: str = "dark"):
        super().__init__(parent)
        self.theme = theme
        self._animation_names: tuple[str, ...] = ()

    def hideEvent(self, event: QHideEvent | None) -> None:  # noqa: N802 - Qt API
        stop_named_animations(self, *self._animation_names)
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 - Qt API
        stop_named_animations(self, *self._animation_names)
        super().closeEvent(event)
