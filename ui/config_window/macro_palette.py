"""Categorical palette for the macro recorder widget.

The macro recorder draws key-press, key-release and wheel-scroll events
with three categorical tints that are theme-aware. The values mirror
the legacy inline literals in
``ui/config_window/macro_record_dialog.py`` so the audit lint stays
quiet and the visual output is byte-for-byte identical.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py`` because the values are
decorative palette tints not in the design-token scale.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    "PRESS_DARK",
    "PRESS_LIGHT",
    "RELEASE_DARK",
    "RELEASE_LIGHT",
    "WHEEL_DARK",
    "WHEEL_LIGHT",
    "MACRO_ACCENT",
]


PRESS_DARK = QColor(120, 220, 150)
PRESS_LIGHT = QColor(20, 130, 60)

RELEASE_DARK = QColor(255, 145, 120)
RELEASE_LIGHT = QColor(170, 40, 40)

WHEEL_DARK = QColor(120, 180, 240)
WHEEL_LIGHT = QColor(40, 90, 200)

MACRO_ACCENT = QColor(192, 132, 252)


def press_color(theme: str) -> QColor:
    return QColor(PRESS_DARK) if theme == "dark" else QColor(PRESS_LIGHT)


def release_color(theme: str) -> QColor:
    return QColor(RELEASE_DARK) if theme == "dark" else QColor(RELEASE_LIGHT)


def wheel_color(theme: str) -> QColor:
    return QColor(WHEEL_DARK) if theme == "dark" else QColor(WHEEL_LIGHT)
