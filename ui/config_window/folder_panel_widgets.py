"""Folder-panel helper widgets.

Extracted from :mod:`ui.config_window.folder_panel` as part of the
P1-06 file-split pass.  Hosts four small widget classes that the
:class:`FolderPanel` composes but does not own:

* :class:`FolderItemDelegate` — ``QStyledItemDelegate`` that draws
  the drop-target highlight on top of each list row.
* :class:`FolderInputDialog` — minimal ``BaseDialog`` for renaming
  a folder.
* :class:`FolderImportDialog` — confirmation ``BaseDialog`` shown
  when importing a folder.
* :class:`FolderItemWidget` — animated ``QWidget`` rendered inside
  each ``QListWidgetItem``.
* :class:`FolderListWidget` — ``QListWidget`` subclass with
  sliding-pill selection animation.
"""

from __future__ import annotations

from core.i18n import tr
from qt_compat import (
    QBrush,
    QCheckBox,
    QEasingCurve,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPainter,
    QPen,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    QSize,
    QStyledItemDelegate,
    QtCompat,
    QVBoxLayout,
    QWidget,
    pyqtProperty,
)
from ui.styles.style import get_dialog_stylesheet
from ui.utils.ui_scale import scale_qss, sp

from .base_dialog import BaseDialog


class FolderItemDelegate(QStyledItemDelegate):
    """文件夹列表项委托 - 绘制拖放目标提示"""

    def __init__(self, owner=None):
        super().__init__()
        self._owner = owner

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        # 检查是否为拖放目标
        is_drop_target = index.data(QtCompat.UserRole + 1)
        if is_drop_target:
            theme = "dark"
            if self._owner:
                theme = self._owner._get_current_theme()

            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if theme == "dark":
                # Dark theme: fresh mint green (minty pastel)
                pen_color = QColor(168, 230, 207, 180)
                brush_color = QColor(168, 230, 207, 45)
            else:
                # Light theme: gorgeous pastel mint green
                pen_color = QColor(70, 180, 140, 200)
                brush_color = QColor(168, 230, 207, 75)

            painter.setPen(QPen(pen_color, 1.5))
            painter.setBrush(QBrush(brush_color))
            rect = option.rect.adjusted(2, 2, -2, -2)
            painter.drawRoundedRect(QRectF(rect), 8, 8)


# ``QColor`` is used by ``FolderItemDelegate.paint``; re-export the
# name from qt_compat so callers can import it from this module.
from qt_compat import QColor  # noqa: E402


class FolderInputDialog(BaseDialog):
    """自定义文件夹输入对话框（支持主题）"""

    def __init__(self, parent=None, title="新建文件夹", label="请输入文件夹名称:", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(sp(200))

        layout = QVBoxLayout(self)
        layout.setSpacing(sp(10))
        layout.setContentsMargins(sp(12), sp(12), sp(12), sp(12))

        # 标签
        self.label = QLabel(label)
        layout.addWidget(self.label)

        # 输入框
        self.input_edit = QLineEdit()
        self.input_edit.setText(text)
        layout.addWidget(self.input_edit)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("取消"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("确定"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        self.setStyleSheet(get_dialog_stylesheet(self.theme))

    def _on_ok(self):
        if self.input_edit.text().strip():
            self.accept()

    def get_text(self) -> str:
        return self.input_edit.text().strip()  # type: ignore[no-any-return]


class FolderImportDialog(BaseDialog):
    """导入文件夹确认对话框（支持主题）"""

    def __init__(self, parent=None, folder_name=""):
        super().__init__(parent)
        self.setWindowTitle(tr("导入文件夹"))
        self.setModal(True)
        self.setMinimumWidth(sp(240))

        layout = QVBoxLayout(self)
        layout.setSpacing(sp(10))
        layout.setContentsMargins(sp(12), sp(12), sp(12), sp(12))

        # 标题
        title_label = QLabel(tr("将创建新分类: {folder_name}", folder_name=folder_name))
        title_label.setStyleSheet(scale_qss("font-weight: 400; font-size: 14px;"))
        layout.addWidget(title_label)

        # 说明文本
        info_label = QLabel(tr("是否启用文件夹自动同步?\n(启用后,文件夹内容变化时会自动更新)"))
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 复选框
        self.sync_check = QCheckBox(tr("启用自动同步"))
        self.sync_check.setChecked(True)  # 默认启用
        layout.addWidget(self.sync_check)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("取消"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("确定"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        self.setStyleSheet(get_dialog_stylesheet(self.theme))

    def is_auto_sync_checked(self):
        """返回自动同步复选框的状态"""
        return self.sync_check.isChecked()


class FolderItemWidget(QWidget):
    """Custom folder item widget supporting Apple-style press scale feedback and theme-aware styling."""

    def __init__(self, text, icon, theme="dark", parent=None):
        super().__init__(parent)
        self.text = text
        self.icon = icon
        self.theme = theme
        self._scale_factor = 1.0
        self.item = None  # Reference to QListWidgetItem
        self._scale_anim = None
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        h = max(sp(18), fm.height()) + sp(18)  # 18px padding total (9px top/bottom)
        return QSize(sp(100), h)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter  # type: ignore[no-redef]
    def scale_factor(self, value: float):
        self._scale_factor = value
        self.update()

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Determine selection and hover states
        is_selected = False
        if self.item is not None:
            is_selected = self.item.isSelected()
        is_hovered = self.underMouse()

        # Draw hover background
        if is_hovered and not is_selected:
            if self.theme == "dark":
                hover_bg = QColor(255, 255, 255, 15)  # rgba(255, 255, 255, 0.06)
            else:
                hover_bg = QColor(0, 0, 0, 10)  # rgba(0, 0, 0, 0.04)
            painter.setBrush(hover_bg)
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(sp(2), sp(1), sp(-2), sp(-1)), sp(8), sp(8))

        # Draw icon
        if self.icon:
            pixmap = self.icon.pixmap(sp(18), sp(18))
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(sp(8), y, pixmap)

        # Draw text
        if self.theme == "dark":
            text_color = (
                QColor(255, 255, 255, 242)
                if is_selected
                else (QColor(255, 255, 255, 217) if is_hovered else QColor(255, 255, 255, 180))
            )
        else:
            text_color = (
                QColor(28, 28, 30, 242)
                if is_selected
                else (QColor(28, 28, 30, 217) if is_hovered else QColor(28, 28, 30, 165))
            )

        painter.setPen(text_color)
        from ui.utils.font_manager import get_qfont

        painter.setFont(get_qfont(12))

        text_rect = QRectF(sp(32), 0, self.width() - sp(42), self.height())
        painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, self.text)

        painter.end()


class FolderListWidget(QListWidget):
    """Folder list with stable Qt drag/drop virtual method dispatch and sliding selection anim."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self._pill_rect = QRectF()
        self._pill_opacity = 0.0
        self._pill_rect_anim = None
        self._pill_opacity_anim = None

        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    @pyqtProperty(QRectF)
    def pill_rect(self) -> QRectF:
        return self._pill_rect

    @pill_rect.setter  # type: ignore[no-redef]
    def pill_rect(self, rect: QRectF):
        self._pill_rect = rect
        self.viewport().update()

    @pyqtProperty(float)
    def pill_opacity(self) -> float:
        return self._pill_opacity

    @pill_opacity.setter  # type: ignore[no-redef]
    def pill_opacity(self, opacity: float):
        self._pill_opacity = opacity
        self.viewport().update()

    def _on_selection_changed(self, selected, deselected):
        curr_indexes = self.selectedIndexes()
        if curr_indexes:
            index = curr_indexes[0]
            visual_rect = self.visualRect(index)
            # 左右各内缩 2px，防止圆角抗锯齿像素被 viewport 右边界裁剪
            target_rect = QRectF(visual_rect).adjusted(sp(2), sp(1), sp(-2), sp(-1))

            if self._pill_rect_anim is not None:
                self._pill_rect_anim.stop()

            if self._pill_rect.isEmpty() or self._pill_opacity < 0.1:
                self._pill_rect = target_rect
            else:
                self._pill_rect_anim = QPropertyAnimation(self, b"pill_rect")
                self._pill_rect_anim.setDuration(220)
                self._pill_rect_anim.setStartValue(self._pill_rect)
                self._pill_rect_anim.setEndValue(target_rect)
                self._pill_rect_anim.setEasingCurve(QEasingCurve.OutCubic)
                self._pill_rect_anim.start()

            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(1.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()
        else:
            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(0.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()

    def startDrag(self, supported_actions):
        self._owner._list_start_drag(supported_actions)

    def dragEnterEvent(self, event):
        self._owner._list_drag_enter_event(event)

    def dragMoveEvent(self, event):
        self._owner._list_drag_move_event(event)

    def dragLeaveEvent(self, event):
        self._owner._list_drag_leave_event(event)

    def dropEvent(self, event):
        self._owner._list_drop_event(event)

    def resizeEvent(self, event):
        """Recalculate pill position when viewport resizes to avoid clipping."""
        super().resizeEvent(event)
        curr_indexes = self.selectedIndexes()
        if curr_indexes and not self._pill_rect.isEmpty():
            index = curr_indexes[0]
            visual_rect = self.visualRect(index)
            self._pill_rect = QRectF(visual_rect).adjusted(sp(2), sp(1), sp(-2), sp(-1))
            self.viewport().update()

    def paintEvent(self, event):
        if self._pill_opacity > 0 and not self._pill_rect.isEmpty():
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            theme = self._owner._get_current_theme()
            if theme == "dark":
                pill_color = QColor(255, 255, 255, int(self._pill_opacity * 35))  # rgba(255, 255, 255, 0.14)
            else:
                pill_color = QColor(0, 0, 0, int(self._pill_opacity * 20))  # rgba(0, 0, 0, 0.08)

            painter.setBrush(QBrush(pill_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(self._pill_rect, sp(8), sp(8))
            painter.end()

        super().paintEvent(event)


__all__ = [
    "FolderImportDialog",
    "FolderInputDialog",
    "FolderItemDelegate",
    "FolderItemWidget",
    "FolderListWidget",
]


# ``QFrame`` is referenced in the type annotations of the parent
# module even after the move; import it locally to keep ruff
# satisfied when this module is imported standalone.
_ = QFrame  # noqa: F841 - imported for side-effect availability
