"""Unified style facade.

This module re-exports the four classes and three helpers that used
to live in this single 1,993-line file (W6.3 split):

* :class:`Colors`            -> :mod:`ui.styles._colors`
* :class:`PopupMenu`         -> :mod:`ui.styles.popup_menu`
* :class:`StyleSheet`        -> :mod:`ui.styles.style_sheet`
* :class:`Glassmorphism`     -> :mod:`ui.styles.glassmorphism`
* :func:`get_menu_stylesheet`, :func:`get_dialog_stylesheet`,
  :func:`get_button_stylesheet` -> :mod:`ui.styles._public_functions`

Existing imports ``from ui.styles.style import X`` continue to work
because every public name is re-exported here.

The :mod:`qt_compat` symbols (:class:`QApplication`, :class:`QCursor`,
...) are also re-exported because the legacy
``monkeypatch.setattr(style_mod, "QApplication", ...)`` test pattern
relies on the symbol being visible on the facade.
"""

from __future__ import annotations

from ._colors import Colors
from ._public_functions import (
    get_button_stylesheet,
    get_dialog_stylesheet,
    get_menu_stylesheet,
)
from .glassmorphism import Glassmorphism
from .popup_menu import PopupMenu, QApplication, QCursor
from .style_sheet import StyleSheet

__all__ = [
    "Colors",
    "Glassmorphism",
    "PopupMenu",
    "QApplication",
    "QCursor",
    "StyleSheet",
    "get_button_stylesheet",
    "get_dialog_stylesheet",
    "get_menu_stylesheet",
]
