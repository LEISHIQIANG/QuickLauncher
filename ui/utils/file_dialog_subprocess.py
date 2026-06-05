"""
独立进程文件对话框脚本
在独立进程中显示非原生 Qt 文件对话框，避免主进程鼠标钩子干扰
"""

import json
import sys


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing arguments"}))
        return

    args = json.loads(sys.argv[1])
    dialog_type = args.get("type")
    caption = args.get("caption", "")
    directory = args.get("directory", "")
    filter_str = args.get("filter", "")

    # 延迟导入PyQt5，只在需要时导入
    from qt_compat import QApplication, QDialog, QFileDialog
    from ui.styles.style import get_dialog_stylesheet
    from ui.styles.window_chrome import apply_custom_window_chrome

    QApplication(sys.argv)
    result = ""

    dialog = QFileDialog(None, caption, directory, filter_str)
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    apply_custom_window_chrome(dialog, kind="dialog", translucent=True)
    dialog.setStyleSheet(get_dialog_stylesheet("dark"))

    if dialog_type == "open":
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
    elif dialog_type == "save":
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
    elif dialog_type == "dir":
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)

    if dialog_type in {"open", "save", "dir"} and dialog.exec_() == QDialog.Accepted:
        selected = dialog.selectedFiles()
        result = selected[0] if selected else ""

    print(json.dumps({"result": result or ""}))


if __name__ == "__main__":
    main()
