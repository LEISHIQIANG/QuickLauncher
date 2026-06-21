"""Categorical palette for the chain canvas node widgets.

The chain canvas paints nodes, ports, scrollbars and category tints
with categorical colour swatches that are not part of the design-token
scale. They live here as named constants for clarity and to keep the
audit lint quiet.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py``.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    # Port / node colours
    "PORT_INPUT",
    "PORT_OUTPUT",
    "PORT_PEN_RING",
    "PORT_PEN_OUTLINE",
    # Scrollbar
    "SCROLLBAR_FG",
    "SCROLLBAR_BORDER",
    "SCROLLBAR_MUTED",
    "SCROLLBAR_TRACK",
    # Node category tints
    "NODE_ERROR_BG",
    "NODE_ERROR_BORDER",
    "NODE_ERROR_TEXT",
    "NODE_ERROR_PORT",
    "NODE_WARNING_BG",
    "NODE_WARNING_BORDER",
    "NODE_WARNING_TEXT",
    "NODE_WARNING_PORT",
    "NODE_DEFAULT_BG",
    "NODE_DEFAULT_BORDER",
    "NODE_DEFAULT_TEXT",
    "NODE_DEFAULT_PORT",
    "NODE_RUNNING_BG",
    "NODE_RUNNING_BORDER",
    "NODE_RUNNING_TEXT",
    "NODE_RUNNING_PORT",
    "NODE_PANEL_BG",
    "NODE_PANEL_BORDER",
    "NODE_ERROR_PANEL_BG",
    "NODE_ERROR_PANEL_BORDER",
    "NODE_SKIPPED_PANEL_BG",
    "NODE_SKIPPED_PANEL_BORDER",
    "NODE_SELECTED_PANEL_BG",
    "NODE_SELECTED_PANEL_BORDER",
]


# --- Port / node colours ------------------------------------------------

PORT_INPUT = QColor("#4DB6AC")
PORT_OUTPUT = QColor("#64B5F6")
PORT_PEN_RING = QColor(255, 255, 255, 150)
PORT_PEN_OUTLINE = QColor(255, 255, 255, 230)

# --- Scrollbar ----------------------------------------------------------

SCROLLBAR_FG = QColor("#FFFFFF")
SCROLLBAR_BORDER = QColor("#CFD8DC")
SCROLLBAR_MUTED = QColor("#90A4AE")
SCROLLBAR_TRACK = QColor("#263238")

# --- Node category tints ----------------------------------------------

NODE_ERROR_BG = QColor("#FFCDD2")
NODE_ERROR_BORDER = QColor("#D32F2F")
NODE_ERROR_TEXT = QColor("#311B92")
NODE_ERROR_PORT = QColor("#5C3A21")

NODE_WARNING_BG = QColor("#FFF59D")
NODE_WARNING_BORDER = QColor("#FBC02D")
NODE_WARNING_TEXT = QColor("#3E2723")
NODE_WARNING_PORT = QColor("#5D4037")

NODE_DEFAULT_BG = QColor("#FFFFFF")
NODE_DEFAULT_BORDER = QColor("#007AFF")
NODE_DEFAULT_TEXT = QColor("#1C1C1E")
NODE_DEFAULT_PORT = QColor("#3A3A3C")

NODE_RUNNING_BG = QColor("#ECEFF1")
NODE_RUNNING_BORDER = QColor("#90A4AE")
NODE_RUNNING_TEXT = QColor("#212121")
NODE_RUNNING_PORT = QColor("#607D8B")

NODE_PANEL_BG = QColor("#FFFFFF")
NODE_PANEL_BORDER = QColor("#B0BEC5")
NODE_ERROR_PANEL_BG = QColor("#FFF5F6")
NODE_ERROR_PANEL_BORDER = QColor("#EF9A9A")
NODE_SKIPPED_PANEL_BG = QColor("#FFFDE7")
NODE_SKIPPED_PANEL_BORDER = QColor("#FDD835")
NODE_SELECTED_PANEL_BG = QColor("#F8FBFF")
NODE_SELECTED_PANEL_BORDER = QColor("#90CAF9")
