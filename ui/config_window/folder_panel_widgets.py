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
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtProperty,
)
from ui.styles.design_tokens import StatusScale, surface, text
from ui.styles.managers import StyleManager
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
                pen_color = QColor(StatusScale.drop_highlight_pen)
                brush_color = QColor(StatusScale.drop_highlight_brush_soft)
            else:
                # Light theme: gorgeous pastel mint green
                pen_color = QColor(StatusScale.drop_highlight_pressed)
                brush_color = QColor(StatusScale.drop_highlight_brush_strong)

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
        layout.setSpacing(sp(8))
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
        StyleManager.apply_dialog_style(self, self.theme)

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
        layout.setSpacing(sp(8))
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
        StyleManager.apply_dialog_style(self, self.theme)

    def is_auto_sync_checked(self):
        """返回自动同步复选框的状态"""
        return self.sync_check.isChecked()


class FolderItemWidget(QWidget):
    """Custom folder item widget supporting Apple-style press scale feedback and theme-aware styling."""

    # Sidebar rows and top tabs deliberately use independent geometry.
    SIDEBAR_ITEM_WIDTH = 128
    SIDEBAR_ICON_SIZE = 18
    SIDEBAR_ICON_X = 8
    SIDEBAR_TEXT_X = 32
    SIDEBAR_TEXT_RIGHT_PADDING = 8
    SIDEBAR_FONT_SIZE = 12
    TOP_TAB_MIN_WIDTH = 96
    TOP_TAB_MAX_WIDTH = 182
    TOP_TAB_TEXT_EXTRA_WIDTH = 54
    TOP_TAB_HEIGHT = 44
    TOP_TAB_ICON_SIZE = 18
    TOP_TAB_ICON_X = 8
    TOP_TAB_TEXT_X = 35
    TOP_TAB_TEXT_RIGHT_PADDING = 11
    TOP_TAB_FONT_SIZE = 13
    # A single capsule geometry is shared by hover and selection in top-tab mode.
    # The 40px item widget therefore gets one 32px centered visual surface.
    TOP_TAB_CAPSULE_INSETS = (4, 4, 4, 4)

    def __init__(self, text, icon, theme="dark", parent=None):
        super().__init__(parent)
        self.text = text
        self.icon = icon
        self.theme = theme
        self._scale_factor = 1.0
        self._compact_tab_mode = False
        self.item = None  # Reference to QListWidgetItem
        self._scale_anim = None
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        if self._compact_tab_mode:
            text_width = self.fontMetrics().horizontalAdvance(self.text)
            return QSize(
                max(sp(self.TOP_TAB_MIN_WIDTH), min(sp(self.TOP_TAB_MAX_WIDTH), text_width + sp(self.TOP_TAB_TEXT_EXTRA_WIDTH))),
                sp(self.TOP_TAB_HEIGHT),
            )
        fm = self.fontMetrics()
        h = max(sp(18), fm.height()) + sp(18)  # 18px padding total (9px top/bottom)
        return QSize(sp(self.SIDEBAR_ITEM_WIDTH), h)

    def set_compact_tab_mode(self, enabled: bool):
        enabled = bool(enabled)
        if self._compact_tab_mode == enabled:
            return
        self._compact_tab_mode = enabled
        self.updateGeometry()
        self.update()

    def _top_tab_capsule_rect(self) -> QRectF:
        left, top, right, bottom = self.TOP_TAB_CAPSULE_INSETS
        return QRectF(self.rect()).adjusted(sp(left), sp(top), -sp(right), -sp(bottom))

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

    def paintEvent(self, event):  # noqa: paint_perf
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Determine selection and hover states
        is_selected = False
        if self.item is not None:
            is_selected = self.item.isSelected()
        is_hovered = self.underMouse()

        # Top-tab selection is painted inside the item itself.  Unlike a viewport
        # overlay, it can never be partially covered or clipped by the list view.
        if is_selected and self._compact_tab_mode:
            if self.theme == "dark":
                selected_bg = QColor(255, 255, 255, 35)
            else:
                selected_bg = QColor(0, 0, 0, 20)
            painter.setBrush(selected_bg)
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(self._top_tab_capsule_rect(), sp(8), sp(8))
        elif is_hovered:
            hover_bg = surface(self.theme, "bg_hover_subtle")
            painter.setBrush(hover_bg)
            painter.setPen(QtCompat.NoPen)
            hover_rect = self._top_tab_capsule_rect() if self._compact_tab_mode else QRectF(self.rect()).adjusted(
                sp(4), sp(1), sp(-2), sp(-1)
            )
            painter.drawRoundedRect(hover_rect, sp(8), sp(8))

        # Draw icon
        if self._compact_tab_mode:
            icon_size = sp(self.TOP_TAB_ICON_SIZE)
            icon_x = sp(self.TOP_TAB_ICON_X)
            text_x = sp(self.TOP_TAB_TEXT_X)
            text_right_padding = sp(self.TOP_TAB_TEXT_RIGHT_PADDING)
            font_size = self.TOP_TAB_FONT_SIZE
        else:
            icon_size = sp(self.SIDEBAR_ICON_SIZE)
            icon_x = sp(self.SIDEBAR_ICON_X)
            text_x = sp(self.SIDEBAR_TEXT_X)
            text_right_padding = sp(self.SIDEBAR_TEXT_RIGHT_PADDING)
            font_size = self.SIDEBAR_FONT_SIZE
        if self.icon:
            pixmap = self.icon.pixmap(icon_size, icon_size)
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(icon_x, y, pixmap)

        # Draw text
        if self.theme == "dark":
            text_color = (
                text(self.theme, "primary")
                if is_selected
                else (text(self.theme, "secondary") if is_hovered else text(self.theme, "tertiary"))
            )
        else:
            text_color = (
                text(self.theme, "primary")
                if is_selected
                else (text(self.theme, "secondary") if is_hovered else text(self.theme, "tertiary"))
            )

        painter.setPen(text_color)
        from ui.utils.font_manager import get_qfont

        painter.setFont(get_qfont(font_size))

        text_rect = QRectF(text_x, 0, self.width() - text_x - text_right_padding, self.height())
        painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, self.text)

        painter.end()


class FolderListWidget(QListWidget):
    """Folder list with stable Qt drag/drop virtual method dispatch and sliding selection anim."""

    SIDEBAR_SELECTION_INSETS = (4, 1, 2, 1)
    # Match the item-painted 32px top-tab capsule: widget y=1 plus 4px local
    # inset equals 5px against the 42px logical item slot.
    TOP_TAB_SELECTION_INSETS = (4, 5, 4, 5)

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self._pill_rect = QRectF()
        self._pill_opacity = 0.0
        self._pill_rect_anim = None
        self._pill_opacity_anim = None
        self._selection_overlay = QFrame(self.viewport())
        self._selection_overlay.setObjectName("folderSelectionOverlay")
        self._selection_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._selection_overlay.hide()

        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        # Selection decoration is painted in viewport coordinates, so it must be
        # recomputed whenever either axis scrolls.
        self._pill_scroll_sync_scheduled = False
        self.verticalScrollBar().valueChanged.connect(self._schedule_pill_scroll_sync)
        self.horizontalScrollBar().valueChanged.connect(self._schedule_pill_scroll_sync)
        self.verticalScrollBar().valueChanged.connect(self._lock_tab_strip_vertical_scroll)

    def _is_top_tab_strip(self) -> bool:
        return getattr(self._owner, "layout_mode", "sidebar") == "top_tabs"

    def lock_tab_strip_vertical_scroll(self):
        """Top tabs are a single horizontal strip; vertical offsets are never valid there."""
        if self._is_top_tab_strip() and self.verticalScrollBar().value() != 0:
            self.verticalScrollBar().setValue(0)

    def _lock_tab_strip_vertical_scroll(self, _value=0):
        self.lock_tab_strip_vertical_scroll()

    @pyqtProperty(QRectF)
    def pill_rect(self) -> QRectF:
        return self._pill_rect

    @pill_rect.setter  # type: ignore[no-redef]
    def pill_rect(self, rect: QRectF):
        self._pill_rect = rect
        self._sync_selection_overlay()

    @pyqtProperty(float)
    def pill_opacity(self) -> float:
        return self._pill_opacity

    @pill_opacity.setter  # type: ignore[no-redef]
    def pill_opacity(self, opacity: float):
        self._pill_opacity = opacity
        self._sync_selection_overlay()

    def _sync_selection_overlay(self):
        """Keep the selection surface behind item widgets and clipped by the actual viewport."""
        if getattr(self._owner, "layout_mode", "sidebar") == "top_tabs":
            self._selection_overlay.hide()
            return
        if self._pill_rect.isEmpty() or self._pill_opacity <= 0:
            self._selection_overlay.hide()
            return
        theme = self._owner._get_current_theme()
        if theme == "dark":
            color = f"rgba(255, 255, 255, {int(self._pill_opacity * 35)})"
        else:
            color = f"rgba(0, 0, 0, {int(self._pill_opacity * 20)})"
        self._selection_overlay.setStyleSheet(
            scale_qss(
                f"QFrame#folderSelectionOverlay {{ background: {color}; border: none; border-radius: 8px; }}"
            )
        )
        self._selection_overlay.setGeometry(self._pill_rect.toAlignedRect())
        self._selection_overlay.show()
        self._selection_overlay.lower()

    def _on_selection_changed(self, selected, deselected):
        curr_indexes = self.selectedIndexes()
        if curr_indexes:
            index = curr_indexes[0]
            target_rect = self._selection_target_rect(index)

            if self._pill_rect_anim is not None:
                self._pill_rect_anim.stop()

            if self._pill_rect.isEmpty() or self._pill_opacity < 0.1:
                self.pill_rect = target_rect
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

    def _schedule_pill_scroll_sync(self, _value=0):
        if self._pill_scroll_sync_scheduled:
            return
        self._pill_scroll_sync_scheduled = True
        QTimer.singleShot(0, self._sync_pill_to_scroll)

    def _sync_pill_to_scroll(self):
        """Keep the custom selection pill attached to its item during list scrolling."""
        self._pill_scroll_sync_scheduled = False
        curr_indexes = self.selectedIndexes()
        if not curr_indexes:
            return
        if self._pill_rect_anim is not None:
            self._pill_rect_anim.stop()
        self.pill_rect = self._selection_target_rect(curr_indexes[0])

    def _selection_target_rect(self, index):
        visual_rect = self.visualRect(index)
        if getattr(self._owner, "layout_mode", "sidebar") == "top_tabs":
            # Browser-style tabs: a compact selection surface that hugs the tag.
            left, top, right, bottom = self.TOP_TAB_SELECTION_INSETS
            return QRectF(visual_rect).adjusted(sp(left), sp(top), -sp(right), -sp(bottom))
        # Left list: retain the existing taller row treatment.
        left, top, right, bottom = self.SIDEBAR_SELECTION_INSETS
        return QRectF(visual_rect).adjusted(sp(left), sp(top), -sp(right), -sp(bottom))

    def scrollContentsBy(self, dx, dy):
        """Run after Qt moves the viewport so visualRect uses the final scroll offset."""
        if self._is_top_tab_strip():
            dy = 0
        super().scrollContentsBy(dx, dy)
        self._schedule_pill_scroll_sync()

    def wheelEvent(self, event):
        """Use the wheel to traverse top tabs horizontally instead of allowing vertical drift."""
        if not self._is_top_tab_strip():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta:
            steps = delta / 120.0
            distance = max(sp(72), self.horizontalScrollBar().singleStep() * 3)
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - steps * distance))
        self.lock_tab_strip_vertical_scroll()
        event.accept()

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
            self.pill_rect = self._selection_target_rect(index)

    def paintEvent(self, event):  # noqa: paint_perf
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
