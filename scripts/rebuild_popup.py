"""Rebuild popup_window.py keeping only core methods, and create new mixin files."""

import os
import re

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "launcher_popup")
SRC = os.path.join(BASE, "popup_window.py")

with open(SRC, encoding="utf-8") as f:
    raw = f.read()
    lines = raw.split("\n")  # split on newlines, no trailing \n issues

# ============================================================
# STEP 1: Build method index (0-indexed line numbers)
# ============================================================

method_starts = []  # (line_index_0, method_name)
for i, line in enumerate(lines):
    if re.match(r"^    def \w+\(", line):
        name = re.search(r"def (\w+)\(", line).group(1)
        method_starts.append((i, name))

# Build ranges: (start_0, end_0_exclusive, name)
method_ranges = []
for idx, (s, name) in enumerate(method_starts):
    e = method_starts[idx + 1][0] if idx + 1 < len(method_starts) else len(lines)
    method_ranges.append((s, e, name))


def get_method(name):
    """Get method source text by name."""
    for s, e, n in method_ranges:
        if n == name:
            return "\n".join(lines[s:e])
    return None


def get_method_range(name, after_line=0):
    """Get (start, end) 0-indexed range for a method, optionally after a given line."""
    for s, e, n in method_ranges:
        if n == name and s >= after_line:
            return (s, e)
    return None


# ============================================================
# STEP 2: Find class LauncherPopup definition line
# ============================================================

class_line = None
for i, line in enumerate(lines):
    if line.startswith("class LauncherPopup("):
        class_line = i
        break

# Helper classes (FolderSyncWorker, IconFlashOverlay) are lines 74 to class_line-1
helper_start = 74  # 0-indexed, where class FolderSyncWorker starts (approximately)
# Find exact start
for i in range(60, class_line):
    if lines[i].startswith("class ") and "LauncherPopup" not in lines[i]:
        helper_start = i
        break

# Find end of helper classes (last line before blank lines before LauncherPopup)
helper_end = class_line
while helper_end > helper_start and lines[helper_end - 1].strip() == "":
    helper_end -= 1
helper_end += 1

print(f"Helper classes: {helper_start + 1}-{helper_end + 1}")
print(f"LauncherPopup class: {class_line + 1}")

# ============================================================
# STEP 3: Verify all expected methods exist
# ============================================================

all_extracted = [
    # Window effect
    "_get_win11_corner_preference",
    "_get_win11_effective_radius",
    "_get_paint_corner_radius",
    "_apply_rounded_mask",
    "_update_window_effect",
    # Layout
    "_setup_window",
    "_calculate_fixed_size",
    "_center_to",
    "resizeEvent",
    "moveEvent",
    # Data refresh
    "_on_settings_updated",
    "refresh_settings",
    "preload_background",
    "preload_visible_icons",
    "prepare_first_show",
    "_start_file_check",
    "_clear_selected_files_context",
    "_refresh_selected_files_indicator",
    "_schedule_selected_files_expiry_refresh",
    "_expire_selected_files_if_current",
    "_take_valid_selected_files_for_click",
    "_on_files_found",
    "_sync_all_folders",
    "_flash_icons",
    "_start_icon_flash_overlay",
    "_on_folder_sync_finished",
    "_refresh_after_folder_sync",
    "_run_blank_area_refresh",
    # Events
    "_get_event_pos",
    "_get_event_global_pos",
    "_get_clicked_item_at",
    "_is_click_on_result_panel",
    "_search_query_matches_result_command",
    "_search_shortcuts_have_priority_over_result",
    "mouseMoveEvent",
    "mousePressEvent",
    "mouseReleaseEvent",
    "mouseDoubleClickEvent",
    "wheelEvent",
    "keyPressEvent",
    "_switch_page",
    "enterEvent",
    "leaveEvent",
    "_check_close",
    "focusOutEvent",
    # Item execution
    "_execute_item",
    "_on_execution_error",
    # Search
    "inputMethodEvent",
    "inputMethodQuery",
    "_insert_or_replace_text",
    "_clamp_search_pos",
    "_search_selection_bounds",
    "_get_search_cursor_pos",
    "_search_bar_full_height",
    "_search_text_prefix",
    "_search_font",
    "_search_metrics",
    "_search_text_width",
    "_search_bar_rect",
    "_search_text_rect",
    "_search_bar_contains",
    "_ensure_search_cursor_visible",
    "_search_cursor_rect",
    "_search_pos_from_point",
    "_restart_search_cursor_blink",
    "_toggle_search_cursor",
    "_move_search_cursor",
    "_word_boundary_left",
    "_word_boundary_right",
    "_previous_search_boundary",
    "_next_search_boundary",
    "_search_word_bounds",
    "_delete_search_selection",
    "_delete_search_backward",
    "_delete_search_forward",
    "_select_all_search_text",
    "_selected_search_text",
    "_copy_search_selection",
    "_cut_search_selection",
    "_paste_search_clipboard",
    "_clear_search_text",
    "_show_search_context_menu",
    "_read_clipboard_text",
    "_set_search_query",
    "_refresh_search_results",
    "_current_search_bar_height",
    "_search_visible_height",
    "_body_y_offset",
    "_search_visible_top_inset",
    "_background_top_inset",
    "_is_search_layout_visible",
    "_is_search_active",
    "_search_animation_update_rect",
    "_remember_search_body_anchor",
    "_set_fixed_geometry_atomically",
    "_apply_search_geometry",
    "_apply_search_mask",
    "_start_search_reveal_animation",
    "_tick_search_reveal",
    "_finish_search_hide_geometry",
    "_reset_search_state",
    "_preload_animation_pages",
    "_preload_next_batch",
    "_warm_page_pixmap_cache",
    "_request_page_animation_update",
]

missing = [m for m in all_extracted if get_method(m) is None]
if missing:
    print(f"WARNING: methods not found: {missing}")

extracted_set = set(all_extracted)

# ============================================================
# STEP 4: Build new popup_window.py (keep only core code)
# ============================================================

# Lines to keep:
# - Everything before helper classes (imports, etc.) → lines 0 to helper_start
# - Class definition → lines[class_line]
# - __init__ → get_method_range('__init__')
# - Core lifecycle methods
# - refresh_data

keep_ranges = []

# 1. Header: from start to helper_classes_start (imports, module-level code)
keep_ranges.append((0, helper_start))

# 2. Class definition line and docstring (find LauncherPopup's __init__, after class_line)
init_start, init_end = get_method_range("__init__", after_line=class_line)
# Between class definition and __init__: class line, docstring, pyqtProperty, etc.
keep_ranges.append((class_line, init_start))

# 3. __init__
keep_ranges.append((init_start, init_end))

# 4. Core lifecycle methods
core_methods = [
    "getRevealProgress",
    "setRevealProgress",
    "prepare_show_animation_state",
    "show",
    "showEvent",
    "_start_show_animation",
    "_finish_show_animation",
    "hide",
    "_start_hide_animation",
    "_on_hide_finished",
    "hideEvent",
    "_restore_focus_safe",
    "_release_residual_modifiers",
]
for m in core_methods:
    rng = get_method_range(m)
    if rng:
        keep_ranges.append(rng)

# 5. refresh_data
rng = get_method_range("refresh_data")
if rng:
    keep_ranges.append(rng)

# Build kept lines
keep_lines_set = set()
for s, e in keep_ranges:
    for i in range(s, e):
        keep_lines_set.add(i)

new_lines = []
for i, line in enumerate(lines):
    if i in keep_lines_set:
        new_lines.append(line)

content = "\n".join(new_lines)

# ============================================================
# STEP 5: Fix imports and class definition
# ============================================================

# Remove imports only used by extracted methods
# These are imported in the original but not needed in the main file
unused_imports = [
    "from core import DataManager, ShortcutItem, ShortcutType",
    "from core.fuzzy_search import FuzzyMatchResult, search_shortcuts",
    "from core.search_engines import build_search_url, parse_search_action",
    "from core.slash_commands import find_matching_commands",
    "from qt_compat import (\n\n    QApplication,\n\n    QBitmap,\n\n    QColor,\n\n    QCursor,\n\n    QFont,\n\n    QFontMetrics,\n\n    QImage,",
]
# Hmm, this is complex with the double-newline issue. Let me just add the needed imports.

# Add new mixin imports
if "from ui.launcher_popup.popup_search import PopupSearchMixin" not in content:
    content = content.replace(
        "from ui.launcher_popup.popup_background import PopupBackgroundMixin\n",
        "from ui.launcher_popup.popup_background import PopupBackgroundMixin\n"
        "from ui.launcher_popup.popup_data_refresh import PopupDataRefreshMixin\n"
        "from ui.launcher_popup.popup_events import PopupEventsMixin\n"
        "from ui.launcher_popup.popup_item_execution import PopupItemExecutionMixin\n"
        "from ui.launcher_popup.popup_search import PopupSearchMixin\n"
        "from ui.launcher_popup.popup_window_effect import PopupLayoutMixin, PopupWindowEffectMixin\n",
    )

# Update class MRO
old_class_match = re.search(r"class LauncherPopup\([^)]*\):", content)
if old_class_match:
    old_class = old_class_match.group(0)
    new_class = """class LauncherPopup(
    PopupEventsMixin,
    PopupDataRefreshMixin,
    PopupCommandResultMixin,
    PopupBackgroundMixin,
    PopupRendererMixin,
    PopupDragDropMixin,
    PopupIconMixin,
    PopupSearchMixin,
    PopupWindowEffectMixin,
    PopupLayoutMixin,
    PopupItemExecutionMixin,
    QWidget,
):"""
    content = content.replace(old_class, new_class)

# Clean up unused imports that are no longer needed in the main file
# Remove threading import (only used by _execute_item)
content = re.sub(r"^import threading\n", "", content, flags=re.MULTILINE)

# Remove imports only used by extracted search/slash methods
for imp in [
    "from core.fuzzy_search import FuzzyMatchResult, search_shortcuts",
    "from core.search_engines import build_search_url, parse_search_action",
    "from core.slash_commands import find_matching_commands",
]:
    content = content.replace(imp + "\n", "")

# Replace combined core import with just DataManager (ShortcutItem/ShortcutType only in extracted code)
content = content.replace("from core import DataManager, ShortcutItem, ShortcutType", "from core import DataManager")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Rebuilt popup_window.py: {content.count(chr(10)) + 1} lines")

# Verify remaining methods
remaining = []
for _i, line in enumerate(content.split("\n")):
    if re.match(r"^    def \w+\(self", line):
        name = re.search(r"def (\w+)\(", line).group(1)
        remaining.append(name)
print(f"Remaining methods ({len(remaining)}): {remaining}")

# ============================================================
# STEP 6: Create popup_events.py (if not already correct)
# ============================================================

events_methods_list = [
    "_get_event_pos",
    "_get_event_global_pos",
    "_get_clicked_item_at",
    "_is_click_on_result_panel",
    "_search_query_matches_result_command",
    "_search_shortcuts_have_priority_over_result",
    "mouseMoveEvent",
    "mousePressEvent",
    "mouseReleaseEvent",
    "mouseDoubleClickEvent",
    "wheelEvent",
    "keyPressEvent",
    "_switch_page",
    "enterEvent",
    "leaveEvent",
    "_check_close",
    "focusOutEvent",
]

events_code = '''"""Mouse, keyboard, wheel events, page switching, and auto-close for LauncherPopup."""

import logging

from qt_compat import (
    QApplication,
    QCursor,
    QPoint,
    Qt,
    QtCompat,
    QTimer,
)
from core.window_detection import _is_desktop_window, _is_explorer_like_window

logger = logging.getLogger(__name__)


class PopupEventsMixin:
    """Mouse, keyboard, wheel events, page switching, and auto-close."""

'''
for m in events_methods_list:
    body = get_method(m)
    if body:
        events_code += body + "\n\n"

with open(os.path.join(BASE, "popup_events.py"), "w", encoding="utf-8") as f:
    f.write(events_code)
print(f"Created popup_events.py: {events_code.count(chr(10)) + 1} lines")

# ============================================================
# STEP 7: Create popup_data_refresh.py
# ============================================================

data_refresh_methods_list = [
    "_on_settings_updated",
    "refresh_settings",
    "preload_background",
    "preload_visible_icons",
    "prepare_first_show",
    "_start_file_check",
    "_clear_selected_files_context",
    "_refresh_selected_files_indicator",
    "_schedule_selected_files_expiry_refresh",
    "_expire_selected_files_if_current",
    "_take_valid_selected_files_for_click",
    "_on_files_found",
    "_sync_all_folders",
    "_flash_icons",
    "_start_icon_flash_overlay",
    "_on_folder_sync_finished",
    "_refresh_after_folder_sync",
    "_run_blank_area_refresh",
]

data_refresh_code = '''"""Data refresh, folder sync, icon flash, settings refresh, and file selection for LauncherPopup."""

import logging
import os
import time

try:
    import win32gui

    HAS_WIN32_SHELL = True
except ImportError:
    HAS_WIN32_SHELL = False

from qt_compat import (
    QApplication,
    QTimer,
)
from ui.launcher_popup.file_selection import FileSelectionThread, SelectionTriggerContext
from ui.launcher_popup.popup_window_helpers import FolderSyncWorker
from core.window_detection import _is_desktop_window, _is_explorer_like_window

logger = logging.getLogger(__name__)


class PopupDataRefreshMixin:
    """Data refresh, folder sync, icon flash, settings refresh, and file selection."""

'''
for m in data_refresh_methods_list:
    body = get_method(m)
    if body:
        data_refresh_code += body + "\n\n"

with open(os.path.join(BASE, "popup_data_refresh.py"), "w", encoding="utf-8") as f:
    f.write(data_refresh_code)
print(f"Created popup_data_refresh.py: {data_refresh_code.count(chr(10)) + 1} lines")
