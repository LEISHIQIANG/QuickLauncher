"""Shared helpers for choosing custom icon files in config dialogs."""

import os

from qt_compat import QDialog
from ui.utils.safe_file_dialog import get_open_file_name

from .icon_picker_dialog import IconPickerDialog

ICON_FILE_FILTER = "Icon Files (*.ico *.png *.jpg *.jpeg *.bmp *.exe *.dll);;All Files (*.*)"


def choose_custom_icon(parent, title: str = "Choose Icon") -> str:
    from .base_dialog import _trace_to_crash_log

    _trace_to_crash_log(f"QFileDialog: choose_custom_icon title={title}")
    file_path, _ = get_open_file_name(parent, title, "", ICON_FILE_FILTER)
    if not file_path:
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".exe", ".dll"):
        dialog = IconPickerDialog(parent, file_path)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_index >= 0:
            return f"{file_path},{dialog.selected_index}"

    return file_path
