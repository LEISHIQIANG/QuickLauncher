"""
设置面板 - 精确布局版本
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QFormLayout, QSlider, QSpinBox, QRadioButton,
    QButtonGroup, QLabel, QFrame, QCheckBox,
    QLineEdit, QPushButton, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog, QScrollArea, QMessageBox,
    QPainter, QPixmap, QColor, QPen, QBrush, QRectF, QDialog, QTimer, QIcon,
    Qt, QtCompat, pyqtSignal, PYQT_VERSION, QThread, QStyledItemDelegate, QStyleOptionViewItem, QModelIndex, QStyle,
    QPainterPath
)

from core import APP_VERSION, DataManager, DEFAULT_SPECIAL_APPS
from .theme_helper import apply_theme_to_dialog, get_radio_stylesheet, get_switch_stylesheet
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.window_effect import get_window_effect


class ExportThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, data_manager, path):
        super().__init__()
        self.data_manager = data_manager
        self.path = path

    def run(self):
        try:
            from core.config_importer import ConfigImporter
            success = ConfigImporter.export_config(self.data_manager, self.path)
            self.finished_signal.emit(success, "导出成功" if success else "导出失败")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class ImportThread(QThread):
    finished_signal = pyqtSignal(bool, int, str)

    def __init__(self, data_manager, path):
        super().__init__()
        self.data_manager = data_manager
        self.path = path

    def run(self):
        try:
            from core.config_importer import ConfigImporter
            count = ConfigImporter.import_config(self.data_manager, self.path)
            self.finished_signal.emit(count >= 0, max(0, count), "导入成功" if count >= 0 else "导入失败")
        except Exception as e:
            self.finished_signal.emit(False, 0, str(e))


class NumberedListDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editing_row = -1

    def paint(self, painter, option, index):
        try:
            painter.save()
            painter.setRenderHint(QtCompat.Antialiasing)

            # Get theme
            theme = "dark"
            try:
                p = (getattr(option, "widget", None) or index.model()).parent()
                while p:
                    if hasattr(p, "data_manager"):
                        theme = p.data_manager.get_settings().theme
                        break
                    p = p.parent()
            except: pass

            is_selected = bool(option.state & QtCompat.State_Selected)
            is_hover = bool(option.state & QtCompat.State_MouseOver)

            # Draw background
            r = QRectF(option.rect).adjusted(1, 1, -1, -1)

            if is_selected:
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QColor(0, 120, 215, 70))
                painter.drawRoundedRect(r, 6, 6)
            else:
                # Normal/Hover background
                if theme == "dark":
                    bg_color = QColor(255, 255, 255, 30) if is_hover else QColor(255, 255, 255, 18)
                    border_color = QColor(255, 255, 255, 22)
                else:
                    bg_color = QColor(120, 120, 128, 44) if is_hover else QColor(120, 120, 128, 26)
                    border_color = QColor(60, 60, 67, 18)

                painter.setBrush(bg_color)
                painter.setPen(QPen(border_color, 1))
                # Ensure border
                painter.drawRoundedRect(r, 6, 6)

            row = index.row() + 1
            num_str = f"{row:02d}"
            font = option.font
            font.setPointSize(9)
            painter.setFont(font)
            num_color = QColor(255, 255, 255, 100) if theme == "dark" else QColor(0, 0, 0, 80)
            if is_selected: num_color = QColor(255, 255, 255, 200)
            painter.setPen(num_color)
            num_rect = QRectF(option.rect.left() + 10, option.rect.top(), 24, option.rect.height())
            painter.drawText(num_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, num_str)

            text_color = QColor(255, 255, 255, 230) if theme == "dark" else QColor(28, 28, 30, 230)
            if is_selected: text_color = QColor(255, 255, 255)
            painter.setPen(text_color)
            font.setBold(False)
            font.setPointSize(10)
            painter.setFont(font)
            text_rect = QRectF(option.rect.left() + 38, option.rect.top(), option.rect.width() - 44, option.rect.height())
            text = index.data(QtCompat.DisplayRole)
            if text and index.row() != self.editing_row:
                elided_text = painter.fontMetrics().elidedText(text, QtCompat.ElideRight, int(text_rect.width()))
                painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, elided_text)
            painter.restore()
        except Exception as e:
            if painter.isActive(): painter.restore()
            super(NumberedListDelegate, self).paint(painter, option, index)

    def createEditor(self, parent, option, index):
        self.editing_row = index.row()
        from qt_compat import QLineEdit
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        return editor

    def destroyEditor(self, editor, index):
        self.editing_row = -1
        super().destroyEditor(editor, index)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        editor.setGeometry(int(rect.left() + 38), int(rect.top()), int(rect.width() - 44), int(rect.height()))

    def setEditorData(self, editor, index):
        text = index.data(QtCompat.DisplayRole)
        if text is None:
            text = ""
        editor.setText(str(text))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), 0) # EditRole/DisplayRole

class ProgressDialog(QDialog):
    """带进度/状态的对话框 - 模糊半透明背景"""
    def __init__(self, parent, title, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMaximumWidth(260)
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Dialog)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)

        from ui.utils.window_effect import is_win11
        self.corner_radius = 8 if is_win11() else 12
        self._acrylic_applied = False
        self._detect_theme()
        self._setup_ui()

    def _detect_theme(self):
        if self.theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
            self.text_color = "#dddddd"
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)
            self.text_color = "#333333"

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(8)

        self.msg_label = QLabel("正在处理...")
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.msg_label.setStyleSheet(
            f"font-size: 13px; border: none; "
            f"background: transparent; color: {self.text_color};"
        )
        main_layout.addWidget(self.msg_label, 1)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.addStretch()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setFixedSize(60, 22)
        self.ok_btn.setStyleSheet("font-size: 13px; border-radius: 4px;")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setVisible(False)
        self.btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(self.btn_layout)

        from ui.styles.style import get_dialog_stylesheet
        self.setStyleSheet(get_dialog_stylesheet(self.theme))

    def paintEvent(self, event):
        """背景绘制 - 完全按照ThemedMessageBox的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10
        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset,
            self.width() - inset * 2, self.height() - inset * 2,
            self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与ThemedMessageBox完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        # 边框
        pen_color = QColor(self.border_color)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1))
        painter.drawPath(path)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()
        from ui.utils.dialog_helper import center_dialog_on_main_window
        center_dialog_on_main_window(self)
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            from ui.utils.window_effect import enable_acrylic_for_config_window, is_win11
            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)

            enable_acrylic_for_config_window(self, self.theme, blur_amount=30, radius=self.corner_radius)
        except Exception:
            pass

    def show_success(self, msg):
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()

    def show_failure(self, msg):
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()
