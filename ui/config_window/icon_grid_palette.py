"""Categorical icon palette for the settings icon grid.

These colours are *categorical* (one hue per ``ShortcutType``) and are
not theme-aware. Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` the audit
script :mod:`scripts.audit_hardcoded_colors` whitelists this file
because token derivation is not appropriate for palette tables.

Mirrors the legacy inline literals previously embedded in
``ui/config_window/icon_grid.py`` so behaviour is byte-for-byte
identical.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    "DEFAULT_FALLBACK_BG",
    "DEFAULT_FALLBACK_TEXT",
    "FOLDER_BG",
    "HOTKEY_BG",
    "HOTKEY_KEY_GREEN",
    "URL_BG",
    "URL_LINK_BLUE",
    "COMMAND_BG",
    "COMMAND_TEXT",
    "BATCH_LAUNCH_BG",
    "ICON_TEXT",
    "LIGHTNING_BOLT",
    "SELECTION_BG",
    "SELECTION_BORDER",
    "DROP_HIGHLIGHT_BG_DARK",
    "DROP_HIGHLIGHT_BORDER_DARK",
    "DROP_HIGHLIGHT_BG_LIGHT",
    "DROP_HIGHLIGHT_BORDER_LIGHT",
    "DROP_TARGET_BG_DARK",
    "DROP_TARGET_BORDER_DARK",
    "DROP_TARGET_BG_LIGHT",
    "DROP_TARGET_BORDER_LIGHT",
    "SHADOW_DARK",
    "SHADOW_LIGHT",
    "MUTED_LABEL_DARK",
    "CELL_BG_LIGHT",
    "CELL_BG_DARK",
    "CELL_HOVER_LIGHT",
    "CELL_HOVER_DARK",
    "CELL_BORDER_DARK",
    "CELL_SELECTION_DARK",
    "CELL_SELECTION_LIGHT",
    "BADGE_BG",
    "BADGE_TEXT",
]


# ----- Default / fallback icon (no shortcut) -----------------------------

DEFAULT_FALLBACK_BG = QColor(135, 206, 250)  # light-sky placeholder
DEFAULT_FALLBACK_TEXT = QColor(255, 255, 255)

# ----- Per ShortcutType backgrounds -------------------------------------

FOLDER_BG = QColor(235, 175, 70)  # folder amber
HOTKEY_BG = QColor(70, 130, 180)  # steel blue
HOTKEY_KEY_GREEN = QColor(144, 238, 144)  # key-glyph accent (light green)
URL_BG = QColor(60, 160, 120)  # sea green
URL_LINK_BLUE = QColor(100, 149, 237)  # URL link accent
COMMAND_BG = QColor(50, 50, 50)  # near-black
COMMAND_TEXT = QColor(0, 255, 0)  # terminal green
BATCH_LAUNCH_BG = QColor(130, 95, 200)  # purple

ICON_TEXT = QColor(255, 255, 255)  # glyph colour

# Special-purpose yellow (lightning bolt icon used by command dialog)
LIGHTNING_BOLT = QColor(255, 200, 0)

# ----- Selection / drop highlight ---------------------------------------

SELECTION_BG = QColor(100, 181, 246, 26)
SELECTION_BORDER = QColor(100, 181, 246, 170)

DROP_HIGHLIGHT_BG_DARK = QColor(168, 230, 207, 45)
DROP_HIGHLIGHT_BORDER_DARK = QColor(168, 230, 207, 180)
DROP_HIGHLIGHT_BG_LIGHT = QColor(168, 230, 207, 75)
DROP_HIGHLIGHT_BORDER_LIGHT = QColor(70, 180, 140, 200)

# ----- Drop target (legacy: slightly different shades) -----------------

DROP_TARGET_BG_DARK = QColor(48, 79, 74, 190)
DROP_TARGET_BORDER_DARK = QColor(168, 230, 207, 120)
DROP_TARGET_BG_LIGHT = QColor(225, 248, 243, 215)
DROP_TARGET_BORDER_LIGHT = QColor(168, 230, 207, 220)

# ----- Drop-shadow colours (paintEvent only) ----------------------------

SHADOW_DARK = QColor(0, 0, 0, 35)
SHADOW_LIGHT = QColor(0, 0, 0, 20)

# ----- Muted label / cell text (subtle on white) ------------------------

MUTED_LABEL_DARK = QColor(0, 0, 0, 12)
CELL_BG_LIGHT = QColor(255, 255, 255, 100)
CELL_BG_DARK = QColor(255, 255, 255, 22)
CELL_HOVER_LIGHT = QColor(255, 255, 255, 160)
CELL_HOVER_DARK = QColor(255, 255, 255, 45)
CELL_BORDER_DARK = QColor(255, 255, 255, 35)
CELL_BORDER_LIGHT = QColor(0, 0, 0, 12)
CELL_SELECTION_DARK = QColor(255, 255, 255, 35)
CELL_SELECTION_LIGHT = QColor(0, 0, 0, 20)

# ----- Folder badge (unread count) --------------------------------------

BADGE_BG = QColor(0, 122, 255, 230)
BADGE_TEXT = QColor(255, 255, 255)
