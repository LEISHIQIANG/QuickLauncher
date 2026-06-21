"""StyleManager — unified setStyleSheet entry point.

Replace ``self.setStyleSheet(...)`` calls with::

    StyleManager.apply_theme(self, theme)
"""

from __future__ import annotations

import logging
import weakref

from ui.utils.ui_scale import scale_qss

logger = logging.getLogger(__name__)


class StyleManager:
    _installed_windows: dict[int, weakref.ref] = {}

    @classmethod
    def apply_theme(cls, window, theme: str) -> None:
        from ui.styles.qss import compose_full_stylesheet

        qss = scale_qss(compose_full_stylesheet(theme))
        window.setStyleSheet(qss)
        cls._register(window)

    @classmethod
    def retheme(cls, window, new_theme: str) -> None:
        current = getattr(window, "_ql_theme", None)
        if current == new_theme:
            return
        window._ql_theme = new_theme
        cls.apply_theme(window, new_theme)
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

    @classmethod
    def apply_component_style(cls, widget, style_key: str, theme: str) -> None:
        from ui.styles.qss import get_component_style

        qss = get_component_style(style_key, theme)
        widget.setStyleSheet(scale_qss(qss))

    @classmethod
    def _register(cls, window) -> None:
        cls._installed_windows[id(window)] = weakref.ref(window)

    @classmethod
    def unregister(cls, window) -> None:
        cls._installed_windows.pop(id(window), None)
