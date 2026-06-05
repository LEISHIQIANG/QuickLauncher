"""
设置面板 - 精确布局版本
"""

import logging

from qt_compat import (
    QBrush,
    QCheckBox,
    QColor,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    QSize,
    QStyledItemDelegate,
    QtCompat,
    QThread,
    QTimer,
    QVBoxLayout,
    pyqtProperty,
    pyqtSignal,
)
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.window_effect import get_window_effect, paint_win10_rounded_surface

logger = logging.getLogger(__name__)


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
            except Exception as exc:
                logger.debug("获取父窗口主题失败: %s", exc, exc_info=True)

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
            if is_selected:
                num_color = QColor(255, 255, 255, 200)
            painter.setPen(num_color)
            num_rect = QRectF(option.rect.left() + 10, option.rect.top(), 24, option.rect.height())
            painter.drawText(num_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, num_str)

            text_color = QColor(255, 255, 255, 230) if theme == "dark" else QColor(28, 28, 30, 230)
            if is_selected:
                text_color = QColor(255, 255, 255)
            painter.setPen(text_color)
            font.setBold(False)
            font.setPointSize(10)
            painter.setFont(font)
            text_rect = QRectF(
                option.rect.left() + 38, option.rect.top(), option.rect.width() - 44, option.rect.height()
            )
            text = index.data(QtCompat.DisplayRole)
            if text and index.row() != self.editing_row:
                elided_text = painter.fontMetrics().elidedText(text, QtCompat.ElideRight, int(text_rect.width()))
                painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, elided_text)
            painter.restore()
        except Exception:
            if painter.isActive():
                painter.restore()
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        self.editing_row = index.row()
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
        model.setData(index, editor.text(), 0)  # EditRole/DisplayRole


class ProgressDialog(QDialog):
    """带进度/状态的对话框 - 模糊半透明背景"""

    def __init__(self, parent, title, theme="dark"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMaximumWidth(260)
        apply_custom_window_chrome(self, kind="dialog", translucent=True)

        self.corner_radius = 8
        self._acrylic_applied = False
        self._dialog_finished = False
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
            f"font-size: 13px; border: none; background: transparent; color: {self.text_color};"
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
            paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
            return

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset, self.width() - inset * 2, self.height() - inset * 2, self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与ThemedMessageBox完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 220))
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
        self._dialog_finished = False
        self.adjustSize()
        from ui.utils.dialog_helper import center_dialog_on_main_window

        center_dialog_on_main_window(self)
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            if self._dialog_finished or not self.isVisible():
                return
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
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def done(self, result):
        self._dialog_finished = True
        super().done(result)

    def show_success(self, msg):
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()

    def show_failure(self, msg):
        self.msg_label.setText(msg)
        self.ok_btn.setVisible(True)
        self.adjustSize()


class SwitchButton(QCheckBox):
    """Custom Apple/iOS-style animated toggle switch button."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(QtCompat.PointingHandCursor)

        # Set a highly specific local stylesheet to disable standard QCheckBox indicator
        self.setStyleSheet(
            "QCheckBox::indicator, SwitchButton::indicator { width: 0px; height: 0px; border: none; background: transparent; image: none; }"
        )

        # Anim progress: 0.0 (off) to 1.0 (on)
        self._progress = 1.0 if self.isChecked() else 0.0

        self._anim = QPropertyAnimation(self, b"progress")
        self._anim.setDuration(220)  # Smooth animation duration
        self._anim.setEasingCurve(QtCompat.OutCubic)

        self.stateChanged.connect(self._on_state_changed)
        self._theme = "dark"

    @pyqtProperty(float)
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, val: float):
        self._progress = val
        self.update()

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        # Bypass animation when loaded offscreen (e.g. settings load)
        if not self.isVisible():
            self._anim.stop()
            self._progress = 1.0 if checked else 0.0
            self.update()

    def set_theme(self, theme: str):
        self._theme = theme
        self.update()

    def _on_state_changed(self, state):
        checked = self.isChecked()
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self):
        font_metrics = self.fontMetrics()
        text_width = (
            font_metrics.horizontalAdvance(self.text())
            if hasattr(font_metrics, "horizontalAdvance")
            else font_metrics.width(self.text())
        )
        text_height = font_metrics.height()

        w = 29 + 8 + text_width + 4
        h = max(18, text_height) + 4
        return QSize(int(w), int(h))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        # Switch dimensions
        sw_width = 29
        sw_height = 18
        spacing = 8

        rect = self.rect()
        sw_y = (rect.height() - sw_height) / 2.0
        sw_x = 0.0

        # Colors based on theme and progress
        if self._theme == "dark":
            bg_off = QColor("#48484A")
            bg_border_off = QColor("#8E8E93")
            text_color = QColor("#FFFFFF")
        else:
            bg_off = QColor("#E9E9EA")
            bg_border_off = QColor("#D1D1D6")
            text_color = QColor("#333333")

        bg_on = QColor("#007AFF")  # Apple system blue

        # Interpolate background color
        r = int(bg_off.red() + (bg_on.red() - bg_off.red()) * self._progress)
        g = int(bg_off.green() + (bg_on.green() - bg_off.green()) * self._progress)
        b = int(bg_off.blue() + (bg_on.blue() - bg_off.blue()) * self._progress)
        current_bg = QColor(r, g, b)

        # Draw background track
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QBrush(current_bg))
        track_rect = QRectF(sw_x, sw_y, sw_width, sw_height)
        painter.drawRoundedRect(track_rect, sw_height / 2.0, sw_height / 2.0)

        # Draw unchecked border for contrast when not fully checked
        if self._progress < 1.0:
            opacity = 1.0 - self._progress
            border_color = QColor(bg_border_off)
            border_color.setAlphaF(opacity)
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QtCompat.NoBrush)
            painter.drawRoundedRect(track_rect.adjusted(0.5, 0.5, -0.5, -0.5), sw_height / 2.0, sw_height / 2.0)

        # Draw white knob
        knob_size = sw_height - 4
        knob_min_x = sw_x + 2.0
        knob_max_x = sw_x + sw_width - sw_height + 2.0
        knob_current_x = knob_min_x + (knob_max_x - knob_min_x) * self._progress

        # Draw knob shadow
        painter.setPen(QPen(QColor(0, 0, 0, 30), 0.5))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        shadow_rect = QRectF(knob_current_x, sw_y + 2.5, knob_size, knob_size)
        painter.drawEllipse(shadow_rect)

        # Draw knob
        knob_rect = QRectF(knob_current_x, sw_y + 2.0, knob_size, knob_size)
        painter.drawEllipse(knob_rect)

        # Draw text
        text = self.text()
        if text:
            font = self.font()
            painter.setFont(font)
            painter.setPen(QPen(text_color))

            text_x = sw_x + sw_width + spacing
            text_rect = QRectF(text_x, 0, rect.width() - text_x, rect.height())
            painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, text)
