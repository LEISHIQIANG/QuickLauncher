"""StyleManager — unified setStyleSheet entry point.

Replace ``self.setStyleSheet(...)`` calls with::

    StyleManager.apply_dialog_style(self, theme)   # dialog stylesheet
    StyleManager.apply_glass_style(self, theme)     # glassmorphism stylesheet
    StyleManager.apply_component_style(widget, "button.plain", theme)  # single widget
    StyleManager.apply_raw(widget, qss)             # inline QSS (lowest level)

All methods register the window for bulk retheme::

    StyleManager.retheme_all("dark")   # switch every registered window
"""

from __future__ import annotations

import logging
import weakref

from ui.utils.ui_scale import scale_qss

logger = logging.getLogger(__name__)


class StyleManager:
    _installed_windows: dict[int, weakref.ref] = {}

    # ── High-level API ──────────────────────────────────────────────

    @classmethod
    def apply_dialog_style(cls, window, theme: str) -> None:
        """Apply ``get_dialog_stylesheet(theme)`` to *window*."""
        from ui.styles._public_functions import get_dialog_stylesheet
        qss = get_dialog_stylesheet(theme)
        window.setStyleSheet(qss)
        cls._register(window)

    @classmethod
    def apply_glass_style(cls, window, theme: str) -> None:
        """Apply ``get_full_glassmorphism_stylesheet(theme)`` to *window*."""
        from ui.styles.glassmorphism import Glassmorphism
        qss = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        window.setStyleSheet(qss)
        cls._register(window)

    @classmethod
    def apply_theme(cls, window, theme: str) -> None:
        """Apply ``compose_full_stylesheet(theme)`` to *window*."""
        from ui.styles.qss import compose_full_stylesheet
        qss = scale_qss(compose_full_stylesheet(theme))
        window.setStyleSheet(qss)
        cls._register(window)

    @classmethod
    def apply_component_style(cls, widget, style_key: str, theme: str) -> None:
        """Apply a single component QSS by ``"component.variant"`` key."""
        from ui.styles.qss import get_component_style
        qss = get_component_style(style_key, theme)
        widget.setStyleSheet(scale_qss(qss))

    @classmethod
    def apply_raw(cls, widget, qss: str) -> None:
        """Apply raw QSS without any transformation (for inline overrides).

        Use this for ``setStyleSheet("color:red; background:transparent")``
        style calls that don't need theme processing.
        """
        widget.setStyleSheet(qss)

    # ── Theme switch ───────────────────────────────────────────────

    @classmethod
    def retheme(cls, window, new_theme: str) -> None:
        current = getattr(window, "_ql_theme", None)
        if current == new_theme:
            return
        window._ql_theme = new_theme
        cls.apply_dialog_style(window, new_theme)
        try:
            window.update()
        except RuntimeError:
            logger.debug("window already deleted during retheme")

    @classmethod
    def retheme_all(cls, new_theme: str) -> None:
        for wid, ref in list(cls._installed_windows.items()):
            win = ref()
            if win is None:
                cls._installed_windows.pop(wid, None)
                continue
            try:
                cls.retheme(win, new_theme)
            except RuntimeError:
                cls._installed_windows.pop(wid, None)

    # ── Lifecycle ──────────────────────────────────────────────────

    @classmethod
    def _register(cls, window) -> None:
        cls._installed_windows[id(window)] = weakref.ref(window)

    @classmethod
    def unregister(cls, window) -> None:
        cls._installed_windows.pop(id(window), None)
