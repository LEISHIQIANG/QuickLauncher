"""
独立进程文件对话框脚本。

在独立进程中显示原生系统文件对话框，避免主进程鼠标钩子干扰。
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
    from qt_compat import QApplication, QFileDialog

    QApplication(sys.argv)
    result = ""
    options = QFileDialog.Options()

    if dialog_type == "open":
        result, _ = QFileDialog.getOpenFileName(None, caption or "选择文件", directory, filter_str, "", options)
    elif dialog_type == "save":
        result, _ = QFileDialog.getSaveFileName(None, caption or "保存文件", directory, filter_str, "", options)
    elif dialog_type == "dir":
        result = QFileDialog.getExistingDirectory(
            None,
            caption or "选择文件夹",
            directory,
            options | QFileDialog.ShowDirsOnly,
        )

    print(json.dumps({"result": result or ""}))


if __name__ == "__main__":
    main()
