"""Shared settings page helpers."""

import os
import sys
import shutil
import time
import winreg

from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QFormLayout, QSlider, QSpinBox, QRadioButton, QButtonGroup,
    QLabel, QFrame, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QScrollArea, QMessageBox,
    QPainter, QPixmap, QColor, QPen, QBrush, QRect, QRectF, QDialog,
    QTimer, QIcon, QStackedWidget, Qt, QtCompat, pyqtSignal, PYQT_VERSION,
    QThread, QStyledItemDelegate, QSize, QKeySequence, QMenu, QAction,
    QComboBox, QPainterPath, exec_dialog, QPoint, QApplication
)
from core import APP_VERSION, DEFAULT_SPECIAL_APPS, ShortcutItem, ShortcutType
from core.app_scanner import AppScanner
from ui.config_window.settings_helpers import NumberedListDelegate, ProgressDialog, ExportThread, ImportThread
from ui.config_window.folder_panel import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_font_css_with_size

class SettingsPageHelpersMixin:
    def _create_label(self, text):
        """创建右对齐标签，自动处理2字/3字与4字对齐"""
        clean_text = text.replace(":", "")
        new_text = clean_text
        
        # 2字 -> 4字对齐 (中间加2个全角空格)
        if len(clean_text) == 2:
            new_text = f"{clean_text[0]}\u3000\u3000{clean_text[1]}"
        # 3字 -> 4字对齐 (中间加1个半角空格/En Space)
        elif len(clean_text) == 3:
            new_text = f"{clean_text[0]}\u2002{clean_text[1]}\u2002{clean_text[2]}"
            
        lbl = QLabel(new_text + ":")
        lbl.setAlignment(QtCompat.AlignRight | QtCompat.AlignVCenter)
        return lbl
    def _create_spinbox(self, min_val, max_val, suffix=""):
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setSuffix(suffix)
        spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spinbox.setFixedWidth(60)
        spinbox.setMinimumHeight(24)
        spinbox.setAlignment(QtCompat.AlignCenter)
        return spinbox
    def _is_win11(self) -> bool:
        try:
            return sys.getwindowsversion().build >= 22000
        except Exception:
            return False
    def _is_win10(self) -> bool:
        try:
            v = sys.getwindowsversion()
            return v.major == 10 and v.build < 22000
        except Exception:
            return False
