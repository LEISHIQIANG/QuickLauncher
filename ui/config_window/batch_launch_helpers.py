"""Batch launch helper widgets — extracted from batch_launch_dialog."""

from __future__ import annotations

import logging

from core.data_models import ShortcutItem
from core.i18n import tr
from qt_compat import (
    QApplication,
    QCheckBox,
    QColor,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPixmap,
    QPoint,
    QPushButton,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.config_window.batch_launch_dialog import _create_type_icon, _shortcut_search_text
from ui.config_window.theme_helper import get_small_checkbox_stylesheet
from ui.styles.design_tokens import BorderScale, SurfaceScale
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.smooth_scroll import SmoothScrollArea
from ui.utils.ui_scale import scale_qss, sp

logger = logging.getLogger(__name__)


class BatchLaunchCard(QFrame):
    """批量启动卡片"""

    remove_requested = pyqtSignal(str)
    drag_started = pyqtSignal(str)
    drag_moved = pyqtSignal(str, QPoint)
    drag_finished = pyqtSignal(str)
    ICON_LABEL_SIZE = 32
    ICON_PIXMAP_SIZE = 26

    def __init__(self, shortcut: ShortcutItem, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.shortcut = shortcut
        self.theme = theme
        self._drag_press_pos = None
        self._dragging = False
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        self.setFixedHeight(sp(52))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp(8), sp(6), sp(8), sp(6))
        layout.setSpacing(sp(8))

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(sp(self.ICON_LABEL_SIZE), sp(self.ICON_LABEL_SIZE))
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border-radius: 0; border: none;")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_label)

        # 名称
        self.name_label = QLabel(self.shortcut.name or tr("未命名"))
        self.name_label.setStyleSheet(
            scale_qss("font-size: 13px; background: transparent; border-radius: 0; border: none;")
        )
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.name_label, 1)

        # 失败暂停复选框
        self.pause_checkbox = QCheckBox(tr("失败暂停"))
        self.pause_checkbox.setChecked(False)
        self.pause_checkbox.setStyleSheet(get_small_checkbox_stylesheet(self.theme))
        layout.addWidget(self.pause_checkbox)

        # 延迟输入框
        delay_layout = QHBoxLayout()
        delay_layout.setSpacing(sp(4))
        delay_label = QLabel(tr("延迟"))
        delay_label.setStyleSheet(
            scale_qss("font-size: 12px; background: transparent; border-radius: 0; border: none;")
        )
        delay_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        delay_layout.addWidget(delay_label)

        self.delay_input = QLineEdit()
        self.delay_input.setText("0")
        self.delay_input.setFixedWidth(sp(48))
        self.delay_input.setPlaceholderText("0")
        delay_layout.addWidget(self.delay_input)

        delay_unit = QLabel("s")
        delay_unit.setStyleSheet(scale_qss("font-size: 12px; background: transparent; border-radius: 0; border: none;"))
        delay_unit.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        delay_layout.addWidget(delay_unit)

        layout.addLayout(delay_layout)

        # 删除按钮
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(sp(24), sp(24))
        remove_btn.setCursor(QtCompat.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.shortcut.id))
        layout.addWidget(remove_btn)

    def _apply_theme(self):
        self._set_dragging_style(False)

    def _set_dragging_style(self, dragging: bool):
        if dragging:
            border = "1px solid rgba(100, 181, 246, 0.72)"
            bg = "rgba(100, 181, 246, 0.14)" if self.theme == "dark" else "rgba(0, 122, 255, 0.10)"
        else:
            border = "1px solid rgba(255, 255, 255, 0.08)" if self.theme == "dark" else "1px solid rgba(0, 0, 0, 0.06)"
            bg = "rgba(255, 255, 255, 0.04)" if self.theme == "dark" else "rgba(0, 0, 0, 0.02)"
        self.setStyleSheet(scale_qss(f"QFrame {{ background: {bg}; border: {border}; border-radius: 6px; }}"))

    def set_icon(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.icon_label.setPixmap(
                pixmap.scaled(
                    sp(self.ICON_PIXMAP_SIZE), sp(self.ICON_PIXMAP_SIZE), Qt.KeepAspectRatio, Qt.SmoothTransformation  # type: ignore[unused-ignore, attr-defined]
                )
            )

    def get_config(self):
        try:
            delay = float(self.delay_input.text() or "0")
        except ValueError:
            delay = 0
        return {
            "shortcut_id": self.shortcut.id,
            "pause_on_failure": self.pause_checkbox.isChecked(),
            "delay": delay,
        }

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self._drag_press_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_press_pos is None or not (event.buttons() & QtCompat.LeftButton):
            super().mouseMoveEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self._dragging and (pos - self._drag_press_pos).manhattanLength() < QApplication.startDragDistance():
            return

        global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        if not self._dragging:
            self._dragging = True
            self._set_dragging_style(True)
            self.raise_()
            self.drag_started.emit(self.shortcut.id)
        self.drag_moved.emit(self.shortcut.id, global_pos)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._drag_press_pos = None
            self._set_dragging_style(False)
            self.drag_finished.emit(self.shortcut.id)
            event.accept()
            return
        self._drag_press_pos = None
        super().mouseReleaseEvent(event)


class CompactIconWidget(QFrame):
    """紧凑图标控件 - 带左上角复选框"""

    check_changed = pyqtSignal(bool)

    def __init__(self, shortcut: ShortcutItem, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)  # type: ignore[unused-ignore, attr-defined]
        self.shortcut = shortcut
        self.theme = theme
        self._checked = False
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        self.setFixedSize(sp(68), sp(68))
        self.setCursor(QtCompat.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(4), sp(4), sp(4), sp(4))
        layout.setSpacing(sp(2))

        # 复选框在左上角
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(sp(16), sp(16))
        self.checkbox.setStyleSheet(get_small_checkbox_stylesheet(self.theme))
        self.checkbox.stateChanged.connect(self._on_check_changed)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(sp(24), sp(24))
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border-radius: 0; border: none;")

        # 名称
        self.name_label = QLabel(self.shortcut.name[:8] if self.shortcut.name else tr("未命名"))
        self.name_label.setAlignment(QtCompat.AlignCenter)
        self.name_label.setStyleSheet(
            scale_qss("font-size: 11px; background: transparent; border-radius: 0; border: none;")
        )
        self.name_label.setWordWrap(True)

        layout.addWidget(self.checkbox, 0, QtCompat.AlignLeft | QtCompat.AlignTop)
        layout.addWidget(self.icon_label, 0, QtCompat.AlignCenter)
        layout.addWidget(self.name_label)

        # 加载默认图标
        self._load_default_icon()

    def _load_default_icon(self):
        """加载默认占位图标"""
        self.icon_label.setPixmap(_create_type_icon(self.shortcut, 24))

    def _apply_theme(self):
        """Store theme colours for QPainter-based rendering (replaces QSS border-radius)."""
        if self.theme == "dark":
            self._bg_color = QColor(SurfaceScale.bg_hover_subtle_dark)
            self._border_color = QColor(BorderScale.strong_dark)
        else:
            self._bg_color = QColor(SurfaceScale.bg_hover_subtle_light)
            self._border_color = QColor(BorderScale.strong_light)
        self._radius = 6.0
        # Remove QSS border-radius — painting is handled by paintEvent now
        self.setStyleSheet("QFrame { background: transparent; border-radius: 0; border: none; }")
        self.update()

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        inset = 0.5
        rect = QRectF(inset, inset, w - inset * 2, h - inset * 2)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        painter.fillPath(path, self._bg_color)

        pen = make_cosmetic_pen(self._border_color, 1.0)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawPath(path)

        painter.end()

    def _on_check_changed(self, state):
        self._checked = state == Qt.Checked
        self.check_changed.emit(self._checked)

    def set_icon(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(sp(24), sp(24), Qt.KeepAspectRatio, Qt.SmoothTransformation))  # type: ignore[unused-ignore, attr-defined]

    def set_checked(self, checked: bool):
        self._checked = bool(checked)
        old = self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(old)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        event.accept()


class IconSelectorWidget(QFrame):
    """图标选择器 - 3列紧凑布局"""

    icon_checked = pyqtSignal(str, bool)  # shortcut_id, checked
    COLUMN_COUNT = 4

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.icon_widgets = {}  # type: ignore[var-annotated]
        self._ordered_shortcut_ids = []  # type: ignore[var-annotated]
        self._search_text_by_id = {}  # type: ignore[var-annotated]
        self._current_filter_text = ""
        self._search_timer = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(8))

        # 搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("搜索..."))
        self.search_box.textChanged.connect(self._on_search)
        layout.addWidget(self.search_box)

        # 滚动区域
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.scroll_area = scroll

        self.grid_container = QWidget()
        self.grid_container.setMinimumHeight(1)

        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll, 1)

    def _on_search(self, text):
        self._current_filter_text = (text or "").strip().lower()
        if self._search_timer is None:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._place_icons)
        self._search_timer.start(30)

    def _clear_grid(self):
        for widget in self.icon_widgets.values():
            widget.hide()

    def _reflow(self, filter_text: str = ""):
        self._current_filter_text = (filter_text or "").strip().lower()
        self._place_icons()

    def _place_icons(self):
        text = self._current_filter_text
        container_width = max(1, self.grid_container.width())
        cell_width = max(sp(76), container_width // self.COLUMN_COUNT)
        cell_height = sp(76)
        spacing_y = sp(4)
        visible_index = 0

        self.scroll_area.setUpdatesEnabled(False)
        self.grid_container.setUpdatesEnabled(False)
        for shortcut_id in self._ordered_shortcut_ids:
            widget = self.icon_widgets.get(shortcut_id)
            if widget is None:
                continue
            visible = not text or text in self._search_text_by_id.get(shortcut_id, "")
            if widget.isVisible() != visible:
                widget.setVisible(visible)
            if not visible:
                continue
            row = visible_index // self.COLUMN_COUNT
            col = visible_index % self.COLUMN_COUNT
            x = col * cell_width + max(0, (cell_width - widget.width()) // 2)
            y = row * (cell_height + spacing_y)
            widget.move(x, y)
            visible_index += 1
        rows = (visible_index + self.COLUMN_COUNT - 1) // self.COLUMN_COUNT
        self.grid_container.setMinimumHeight(max(1, rows * (cell_height + spacing_y)))
        self.grid_container.setUpdatesEnabled(True)
        self.scroll_area.setUpdatesEnabled(True)
        self.grid_container.update()

    def set_shortcuts(self, shortcuts):
        """设置可选图标列表"""
        self.begin_shortcuts()
        self.append_shortcuts(shortcuts)

    def begin_shortcuts(self):
        """清空候选图标列表，准备分批追加。"""
        self._clear_grid()
        for widget in self.icon_widgets.values():
            widget.deleteLater()
        self.icon_widgets.clear()
        self._ordered_shortcut_ids.clear()
        self._search_text_by_id.clear()
        self._current_filter_text = self.search_box.text().strip().lower()
        self.grid_container.setMinimumHeight(1)

    def append_shortcuts(self, shortcuts):
        """追加一批候选图标。"""
        self.scroll_area.setUpdatesEnabled(False)
        self.grid_container.setUpdatesEnabled(False)
        for shortcut in shortcuts:
            if shortcut.id in self.icon_widgets:
                continue
            icon_widget = CompactIconWidget(shortcut, self.theme, self.grid_container)
            icon_widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
            icon_widget.check_changed.connect(lambda c, sid=shortcut.id: self.icon_checked.emit(sid, c))
            self.icon_widgets[shortcut.id] = icon_widget
            self._ordered_shortcut_ids.append(shortcut.id)
            self._search_text_by_id[shortcut.id] = _shortcut_search_text(shortcut)
        self._place_icons()
        self.grid_container.setUpdatesEnabled(True)
        self.scroll_area.setUpdatesEnabled(True)
        self.grid_container.update()

    def set_icon_pixmap(self, shortcut_id: str, pixmap: QPixmap):
        if shortcut_id in self.icon_widgets:
            self.icon_widgets[shortcut_id].set_icon(pixmap)

    def set_checked(self, shortcut_id: str, checked: bool):
        if shortcut_id in self.icon_widgets:
            self.icon_widgets[shortcut_id].set_checked(checked)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.icon_widgets:
            self._place_icons()
