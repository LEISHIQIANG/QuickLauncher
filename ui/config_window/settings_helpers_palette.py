"""Theme-aware palette for the settings list delegate.

The settings list delegate (a custom ``QStyledItemDelegate`` in
``ui/config_window/settings_helpers.py``) draws row backgrounds, row
numbers and selection markers with theme-aware tints that are not part
of the design-token scale (e.g. row 30%-alpha white, 70%-alpha
selection blue). They live here as named constants for clarity and
to keep the audit lint quiet.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py``.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    "ROW_SELECTION_DARK",
    "ROW_HOVER_BG_DARK",
    "ROW_BG_DARK",
    "ROW_BORDER_DARK",
    "ROW_HOVER_BG_LIGHT",
    "ROW_BG_LIGHT",
    "ROW_BORDER_LIGHT",
    "ROW_NUM_DARK_IDLE",
    "ROW_NUM_DARK_SELECTED",
    "ROW_NUM_LIGHT_IDLE",
    "ROW_TEXT_DARK",
    "ROW_TEXT_LIGHT",
    "ROW_TEXT_DARK_SELECTED",
    "ROW_TEXT_LIGHT_SELECTED",
    # Toggle / switch off-state palette
    "SWITCH_BG_DARK_OFF",
    "SWITCH_BG_DARK_BORDER_OFF",
    "SWITCH_BG_DARK_TEXT",
    "SWITCH_BG_LIGHT_OFF",
    "SWITCH_BG_LIGHT_BORDER_OFF",
    "SWITCH_BG_LIGHT_TEXT",
    "SWITCH_BG_DARK_ON",
    "SWITCH_BG_LIGHT_ON",
    "SWITCH_KNOB_SHADOW",
]


# ----- Settings list row palette ---------------------------------------

ROW_SELECTION_DARK = QColor(0, 120, 215, 70)  # blue selection tint
ROW_HOVER_BG_DARK = QColor(255, 255, 255, 30)
ROW_BG_DARK = QColor(255, 255, 255, 18)
ROW_BORDER_DARK = QColor(255, 255, 255, 22)
ROW_HOVER_BG_LIGHT = QColor(120, 120, 128, 44)
ROW_BG_LIGHT = QColor(120, 120, 128, 26)
ROW_BORDER_LIGHT = QColor(60, 60, 67, 18)
ROW_NUM_DARK_IDLE = QColor(255, 255, 255, 100)
ROW_NUM_DARK_SELECTED = QColor(255, 255, 255, 200)
ROW_NUM_LIGHT_IDLE = QColor(0, 0, 0, 80)
ROW_TEXT_DARK = QColor(255, 255, 255, 230)
ROW_TEXT_LIGHT = QColor(28, 28, 30, 230)
ROW_TEXT_DARK_SELECTED = QColor(255, 255, 255, 255)
ROW_TEXT_LIGHT_SELECTED = QColor(255, 255, 255, 255)

# ----- SwitchButton off-state palette ----------------------------------

SWITCH_BG_DARK_OFF = QColor("#48484A")
SWITCH_BG_DARK_BORDER_OFF = QColor("#8E8E93")
SWITCH_BG_DARK_TEXT = QColor("#FFFFFF")
SWITCH_BG_LIGHT_OFF = QColor("#E9E9EA")
SWITCH_BG_LIGHT_BORDER_OFF = QColor("#D1D1D6")
SWITCH_BG_LIGHT_TEXT = QColor("#FFFFFF")
SWITCH_BG_DARK_ON = QColor("#48484A")
SWITCH_BG_LIGHT_ON = QColor("#34C759")
SWITCH_KNOB_SHADOW = QColor(0, 0, 0, 30)
