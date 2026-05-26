"""Rebuild popup_window.py and all extracted mixin files from the original 3519-line source."""

import os
import re

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "launcher_popup")

with open(os.path.join(BASE, "popup_window.py"), "r", encoding="utf-8") as f:
    lines = f.readlines()

# ============================================================
# STEP 1: Identify method boundaries
# ============================================================

# Find all class-level method definitions
methods = []
for i, line in enumerate(lines):
    if re.match(r"^    def \w+\(", line):
        name = re.search(r"def (\w+)\(", line).group(1)
        methods.append((i, name))  # 0-indexed

# Build ranges: (start_0, end_0_exclusive, method_name)
ranges = []
for idx, (line_0, name) in enumerate(methods):
    if idx + 1 < len(methods):
        end_0 = methods[idx + 1][0]
    else:
        end_0 = len(lines)
    ranges.append((line_0, end_0, name))


def get_method_body(name):
    """Get the lines (as joined string) for a method."""
    for s, e, n in ranges:
        if n == name:
            return "\n".join(lines[s:e])
    return None


# ============================================================
# STEP 2: Define which methods go where
# ============================================================

popup_window_effect_methods = [
    "_get_win11_corner_preference",
    "_get_win11_effective_radius",
    "_get_paint_corner_radius",
    "_apply_win10_rounded_mask",
    "_update_window_effect",
]
popup_layout_methods = [
    "_setup_window",
    "_calculate_fixed_size",
    "_center_to",
    "resizeEvent",
    "moveEvent",
]
popup_data_refresh_methods = [
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
popup_events_methods = [
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
popup_item_execution_methods = [
    "_execute_item",
    "_on_execution_error",
]
popup_search_methods = [
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

all_extracted = set()
for group in [
    popup_window_effect_methods,
    popup_layout_methods,
    popup_data_refresh_methods,
    popup_events_methods,
    popup_item_execution_methods,
    popup_search_methods,
]:
    all_extracted.update(group)

# Verify all extracted methods exist
missing = [m for m in all_extracted if get_method_body(m) is None]
if missing:
    print(f"WARNING: methods not found: {missing}")

# ============================================================
# STEP 3: Find helper classes and LauncherPopup class boundary
# ============================================================

# Find FolderSyncWorker and IconFlashOverlay classes (before LauncherPopup)
class_launcher_line = None
helper_start = None
helper_end = None
for i, line in enumerate(lines):
    if line.startswith("class LauncherPopup("):
        class_launcher_line = i
        break
    if line.startswith("class ") and helper_start is None:
        helper_start = i

if helper_start is not None and class_launcher_line is not None:
    # Helper classes end at the blank line(s) before LauncherPopup
    helper_end = class_launcher_line
    # Trim trailing blank lines
    while helper_end > helper_start and lines[helper_end - 1].strip() == "":
        helper_end -= 1
    helper_end += 1  # include the last non-blank line

print(f"Helper classes: lines {helper_start + 1}-{helper_end}")
print(f"LauncherPopup class starts at line {class_launcher_line + 1}")

# ============================================================
# STEP 4: Build line set to remove
# ============================================================

remove_lines = set()

# Remove helper classes (already in popup_window_helpers.py)
if helper_start is not None:
    for i in range(helper_start, helper_end):
        remove_lines.add(i)

# Remove extracted methods
for m in all_extracted:
    for s, e, n in ranges:
        if n == m:
            for i in range(s, e):
                remove_lines.add(i)
            break

print(f"Total lines to remove: {len(remove_lines)}")
print(f"Original file: {len(lines)} lines")
print(f"Expected result: {len(lines) - len(remove_lines)} lines")

# ============================================================
# STEP 5: Rebuild popup_window.py
# ============================================================

new_lines = []
for i, line in enumerate(lines):
    if i not in remove_lines:
        new_lines.append(line)

content = "\n".join(new_lines)

# Add new mixin imports after the existing popup imports
insert_after = "from ui.launcher_popup.popup_background import PopupBackgroundMixin\n"
new_imports = (
    "from ui.launcher_popup.popup_data_refresh import PopupDataRefreshMixin\n"
    "from ui.launcher_popup.popup_events import PopupEventsMixin\n"
)
content = content.replace(insert_after, insert_after + new_imports)

# Update class definition to include all mixins
old_class = """class LauncherPopup(
    PopupCommandResultMixin,
    PopupBackgroundMixin,
    PopupRendererMixin,
    PopupDragDropMixin,
    PopupIconMixin,
    QWidget,
):"""
new_class = """class LauncherPopup(
    PopupCommandResultMixin,
    PopupBackgroundMixin,
    PopupRendererMixin,
    PopupDragDropMixin,
    PopupIconMixin,
    PopupSearchMixin,
    PopupWindowEffectMixin,
    PopupLayoutMixin,
    PopupItemExecutionMixin,
    PopupEventsMixin,
    PopupDataRefreshMixin,
    QWidget,
):"""
content = content.replace(old_class, new_class)

with open(os.path.join(BASE, "popup_window.py"), "w", encoding="utf-8") as f:
    f.write(content)

final_lines = content.count("\n") + 1
print(f"\nRebuilt popup_window.py: {final_lines} lines")

# Verify remaining methods
remaining = []
for i, line in enumerate(content.split("\n")):
    if re.match(r"^    def \w+\(self", line):
        name = re.search(r"def (\w+)\(", line).group(1)
        remaining.append(name)
print(f"Remaining methods ({len(remaining)}): {remaining}")
