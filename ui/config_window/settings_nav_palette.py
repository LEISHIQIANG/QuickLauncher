"""Theme-aware palette for the settings side navigation row.

The settings panel's left-hand navigation list draws per-row hover,
selection and primary/secondary text colours that are theme-aware. The
previous code embedded ``QColor(...)`` literals inside the widget; this
module collects the values into named tokens and the widget now reads
them from here.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py`` because the values are
decorative palette tints not in the design-token scale.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    # Hover background tints
    "NAV_HOVER_BG_DARK",
    "NAV_HOVER_BG_LIGHT",
    # Primary text (titles)
    "NAV_PRIMARY_TEXT_DARK",
    "NAV_PRIMARY_TEXT_LIGHT",
    # Secondary text (descriptions, idle/hover/selected)
    "NAV_SECONDARY_TEXT_DARK",
    "NAV_SECONDARY_TEXT_LIGHT",
    # Light-theme primary text per state
    "NAV_PRIMARY_TEXT_LIGHT_SELECTED",
    "NAV_PRIMARY_TEXT_LIGHT_HOVER",
    "NAV_PRIMARY_TEXT_LIGHT_IDLE",
    # Dark-theme primary text per state
    "NAV_PRIMARY_TEXT_DARK_SELECTED",
    "NAV_PRIMARY_TEXT_DARK_HOVER",
    "NAV_PRIMARY_TEXT_DARK_IDLE",
    # Light-theme secondary text per state
    "NAV_SECONDARY_TEXT_LIGHT_HOVER",
    "NAV_SECONDARY_TEXT_LIGHT_IDLE",
    # Inks for the navigation label painting
    "NAV_INK_LIGHT",
    "NAV_INK_DARK",
]


# --- Hover backgrounds --------------------------------------------------

NAV_HOVER_BG_DARK = QColor(255, 255, 255, 24)  # rgba(255,255,255,0.09)
NAV_HOVER_BG_LIGHT = QColor(0, 0, 0, 18)  # rgba(0,0,0,0.07)

# --- Primary text (titles) ---------------------------------------------

NAV_PRIMARY_TEXT_DARK = QColor(255, 255, 255, 242)  # selected
NAV_PRIMARY_TEXT_LIGHT = QColor(0, 0, 0, 242)  # selected

# --- Secondary text (descriptions) -------------------------------------

NAV_SECONDARY_TEXT_DARK = QColor(255, 255, 255, 217)  # hover
NAV_SECONDARY_TEXT_LIGHT = QColor(0, 0, 0, 200)  # hover
NAV_PRIMARY_TEXT_LIGHT_IDLE = QColor(0, 0, 0, 155)
NAV_PRIMARY_TEXT_LIGHT_HOVER = QColor(0, 0, 0, 210)
NAV_PRIMARY_TEXT_LIGHT_SELECTED = QColor(0, 0, 0, 242)
NAV_PRIMARY_TEXT_DARK_IDLE = QColor(255, 255, 255, 175)
NAV_PRIMARY_TEXT_DARK_HOVER = QColor(255, 255, 255, 230)
NAV_PRIMARY_TEXT_DARK_SELECTED = QColor(255, 255, 255, 242)
NAV_SECONDARY_TEXT_LIGHT_HOVER = QColor(0, 0, 0, 210)
NAV_SECONDARY_TEXT_LIGHT_IDLE = QColor(0, 0, 0, 155)

# --- Paint-event ink for the nav label ---------------------------------

NAV_INK_LIGHT = QColor(38, 49, 64, 150)
NAV_INK_DARK = QColor(235, 241, 250, 165)
