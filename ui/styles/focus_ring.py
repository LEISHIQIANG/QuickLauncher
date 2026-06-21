"""Focus ring QSS rules.

Returns QSS snippets that can be merged into a stylesheet via
``style += focus_ring_qss("dark")``. The rules paint a 1-px cosmetic
focus ring around any focusable widget using the
``QWidget:focus`` / ``QAbstractButton:focus`` pseudo-classes.

The :class:`FeatureFlag` toggle ``Settings.advanced.show_focus_ring`` is
checked at apply time – the caller is expected to gate the merge based
on the flag. This module is content-only: it has no Qt runtime
dependency other than the CSS string itself, so it can be loaded during
splash without paying a Qt import cost.
"""

from __future__ import annotations

__all__ = [
    "focus_ring_qss",
    "pressed_transition_qss",
    "micro_animation_qss",
]


_FOCUS_RING_BASE = """
/* Focus ring – 1-px cosmetic accent border for keyboard navigation. */
QWidget:focus,
QAbstractButton:focus,
QLineEdit:focus,
QPlainTextEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QAbstractSpinBox:focus,
QSlider:focus,
QCheckBox:focus,
QRadioButton:focus,
QListView:focus,
QTreeView:focus,
QTableView:focus,
QTabBar::tab:focus {{
    border: 1px solid {focus_color};
    border-radius: 6px;
}}
/* Suppress the default focus rect on focusable buttons that opt-in. */
QPushButton:focus {{ outline: none; }}
"""


def focus_ring_qss(theme: str = "dark") -> str:
    """Return a QSS fragment that draws a 1-px focus ring.

    Parameters
    ----------
    theme:
        ``"dark"`` or ``"light"`` – chooses the focus colour from
        :mod:`ui.styles.design_tokens`.
    """

    color = "#0A84FF" if theme == "dark" else "#007AFF"
    return _FOCUS_RING_BASE.format(focus_color=color)


_PRESSED_TRANSITION_BASE = """
/* Subtle 80 ms colour transition on :pressed for high-frequency buttons. */
QPushButton {{
    transition: background-color {duration}ms {easing},
                color {duration}ms {easing};
}}
"""


def pressed_transition_qss(duration_ms: int = 80, easing: str = "cubic-bezier(0.4, 0.0, 0.2, 1.0)") -> str:
    """Return a QSS fragment that adds an 80 ms :pressed colour transition."""

    return _PRESSED_TRANSITION_BASE.format(duration=duration_ms, easing=easing)


def micro_animation_qss(theme: str = "dark", duration_ms: int = 120) -> str:
    """Return a QSS fragment bundling focus ring + pressed transition.

    Used by ``style.py`` to opt-in to the L3 micro-animation features
    behind the ``Settings.advanced.micro_animations`` flag.
    """

    return focus_ring_qss(theme) + "\n" + pressed_transition_qss(duration_ms)
