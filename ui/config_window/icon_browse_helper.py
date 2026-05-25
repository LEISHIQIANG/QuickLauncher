"""Shared helpers for choosing custom icon files in config dialogs."""

import os

from qt_compat import QDialog, QFileDialog

from .icon_picker_dialog import IconPickerDialog

ICON_FILE_FILTER = "Icon Files (*.ico *.png *.jpg *.jpeg *.bmp *.exe *.dll);;All Files (*.*)"


def choose_custom_icon(parent, title: str = "Choose Icon") -> str:
    # Nuitka 打包后主线程 COM 公寓可能未初始化，QFileDialog 内部用 IFileOpenDialog
    # 需要确保 STA 已初始化，否则抛 RPC_E_WRONG_THREAD (0x8001010e)
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass

    from .base_dialog import _trace_to_crash_log
    _trace_to_crash_log(f"QFileDialog: choose_custom_icon title={title}")
    file_path, _ = QFileDialog.getOpenFileName(parent, title, "", ICON_FILE_FILTER)
    if not file_path:
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".exe", ".dll"):
        dialog = IconPickerDialog(parent, file_path)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_index >= 0:
            return f"{file_path},{dialog.selected_index}"

    return file_path
