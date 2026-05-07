"""PyQt5 environment diagnostic for QuickLauncher."""

import os
import platform
import struct
import subprocess
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def main() -> int:
    print("=" * 50)
    print("QuickLauncher PyQt5 environment check")
    print("=" * 50)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"Architecture: {struct.calcsize('P') * 8}-bit {platform.python_implementation()}")

    print("\nInstalled Qt packages:")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    for line in result.stdout.splitlines():
        if "qt" in line.lower() or "pyside" in line.lower():
            print(f"  {line}")

    print("\nImport check:")
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets
        import PyQt5
    except Exception as exc:
        print(f"  PyQt5 import failed: {exc}")
        try:
            import PyQt5  # type: ignore[no-redef]
            print(f"  PyQt5 path: {os.path.dirname(PyQt5.__file__)}")
        except Exception:
            pass
        return 1

    print(f"  PyQt version: {QtCore.PYQT_VERSION_STR}")
    print(f"  Qt version: {QtCore.QT_VERSION_STR}")
    print(f"  QtCore: {QtCore.__name__}")
    print(f"  QtGui: {QtGui.__name__}")
    print(f"  QtWidgets: {QtWidgets.__name__}")

    try:
        import qt_compat
    except Exception as exc:
        print(f"  qt_compat import failed: {exc}")
        return 1

    if qt_compat.QT_LIB != "PyQt5" or qt_compat.PYQT_VERSION != 5:
        print(f"  qt_compat selected unexpected binding: {qt_compat.QT_LIB} {qt_compat.PYQT_VERSION}")
        return 1

    print(f"  qt_compat: {qt_compat.QT_LIB} {qt_compat.PYQT_VERSION}")
    print("\nOK: PyQt5 environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
