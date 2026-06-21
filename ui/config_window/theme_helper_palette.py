"""Categorical palette for theme helper widgets.

The settings panel and various helper widgets use iOS-style categorical
colours (switch off-state, checkbox tick, knob border shadow, etc.).
These are decorative palette tints not in the design-token scale.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py``.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    # iOS-style switch colours
    "IOS_DARK_FILL",
    "IOS_DARK_BORDER",
    "IOS_DARK_TEXT",
    "IOS_DARK_KNOB",
    "IOS_LIGHT_FILL",
    "IOS_LIGHT_BORDER",
    "IOS_LIGHT_TEXT",
    "IOS_LIGHT_KNOB",
    "IOS_BLUE",
    # Knob border shadow
    "KNOB_BORDER_SHADOW",
    "KNOB_TEXT_WHITE",
]


# iOS-style categorical colours.
IOS_DARK_FILL = QColor("#48484A")
IOS_DARK_BORDER = QColor("#8E8E93")
IOS_DARK_TEXT = QColor("#FFFFFF")
IOS_DARK_KNOB = QColor("#48484A")
IOS_LIGHT_FILL = QColor("#E9E9EA")
IOS_LIGHT_BORDER = QColor("#D1D1D6")
IOS_LIGHT_TEXT = QColor("#FFFFFF")
IOS_LIGHT_KNOB = QColor("#34C759")
IOS_BLUE = QColor("#007AFF")
KNOB_BORDER_SHADOW = QColor(0, 0, 0, 50)
KNOB_TEXT_WHITE = QColor("#FFFFFF")
