"""
批量启动对话框
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
import copy
import logging
import os

from core import DataManager, ShortcutItem, ShortcutType
from core.data_models import BATCH_LAUNCH_MODULE_ID, BATCH_LAUNCH_MODULE_VERSION
from core.i18n import tr
from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon
from qt_compat import (
    QApplication,
    QCheckBox,
    QColor,
    QEasingCurve,
    QFont,
    QFrame,
    QHBoxLayout,
    QImage,
    QLabel,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    Qt,
    QtCompat,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.design_tokens import surface
from ui.styles.style import Glassmorphism
from ui.utils.interruptible_animation import stop_animation
from ui.utils.pixel_snap import create_pixmap
from ui.utils.qt_thread_cleanup import stop_qthread_nonblocking
from ui.utils.smooth_scroll import SmoothScrollArea
from ui.utils.ui_scale import scale_qss, sp

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_compact_checkbox_stylesheet, get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)


LAUNCHABLE_TYPES = (
    ShortcutType.FILE,
    ShortcutType.FOLDER,
    ShortcutType.COMMAND,
    ShortcutType.URL,
    ShortcutType.HOTKEY,
)


def _shortcut_search_text(shortcut: ShortcutItem) -> str:
    parts = [
        getattr(shortcut, "name", ""),
        getattr(shortcut, "alias", ""),
        getattr(shortcut, "target_path", ""),
        getattr(shortcut, "url", ""),
        getattr(shortcut, "command", ""),
        getattr(shortcut, "hotkey", ""),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _create_type_icon(shortcut: ShortcutItem, size: int) -> QPixmap:
    from .icon_grid_palette import (
        BATCH_LAUNCH_BG,
        COMMAND_BG,
        DEFAULT_FALLBACK_BG,
        DEFAULT_FALLBACK_TEXT,
        FOLDER_BG,
        HOTKEY_BG,
        URL_BG,
    )

    pixmap = create_pixmap(size, size)
    pixmap.fill(QtCompat.transparent)

    palette = {
        ShortcutType.FOLDER: (QColor(FOLDER_BG), "F"),
        ShortcutType.URL: (QColor(URL_BG), "W"),
        ShortcutType.HOTKEY: (QColor(HOTKEY_BG), "K"),
        ShortcutType.COMMAND: (QColor(COMMAND_BG), ">"),
        ShortcutType.BATCH_LAUNCH: (QColor(BATCH_LAUNCH_BG), "B"),
    }
    bg, text = palette.get(shortcut.type, (QColor(DEFAULT_FALLBACK_BG), (shortcut.name or "?")[:1]))

    painter = QPainter(pixmap)
    painter.setRenderHint(QtCompat.Antialiasing)
    painter.setRenderHint(QtCompat.HighQualityAntialiasing)
    painter.setBrush(bg)
    painter.setPen(QtCompat.NoPen)
    margin = max(2, size // 8)
    radius = max(4, size // 5)
    painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), radius, radius)

    painter.setPen(QColor(DEFAULT_FALLBACK_TEXT))
    font = QFont("Segoe UI", max(8, int(size * 0.42)))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCompat.AlignCenter, text)
    painter.end()
    return pixmap


def _load_shortcut_icon(shortcut: ShortcutItem, size: int) -> QPixmap:
    """Load a shortcut icon with type-specific fallbacks used by batch launch UI."""
    try:
        from core.icon_extractor import IconExtractor

        pixmap = None
        icon_path = getattr(shortcut, "icon_path", "") or ""
        target_path = getattr(shortcut, "target_path", "") or ""

        if not icon_path and shortcut_uses_folder_icon(getattr(shortcut, "type", None), target_path):
            icon_path = default_folder_icon_path() or ""
            target_path = ""

        if icon_path:
            pixmap = IconExtractor.from_file(icon_path, size, return_image=False)
        if (not pixmap or pixmap.isNull()) and target_path:
            pixmap = IconExtractor.extract(
                target_path,
                target_path,
                size,
                return_image=False,
                fallback_to_default=False,
            )
        if pixmap and not pixmap.isNull():
            return pixmap  # type: ignore[unused-ignore, no-any-return]
    except Exception:
        logger.debug(
            "批量启动图标加载失败: id=%s name=%r icon_path=%r target_path=%r",
            getattr(shortcut, "id", ""),
            getattr(shortcut, "name", ""),
            getattr(shortcut, "icon_path", ""),
            getattr(shortcut, "target_path", ""),
            exc_info=True,
        )

    return _create_type_icon(shortcut, size)


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
        self.icon_label.setStyleSheet("background: transparent; border: none; border-radius: 0;")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_label)

        # 名称
        self.name_label = QLabel(self.shortcut.name or tr("未命名"))
        self.name_label.setStyleSheet(
            scale_qss("font-size: 13px; background: transparent; border: none; border-radius: 0;")
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
            scale_qss("font-size: 12px; background: transparent; border: none; border-radius: 0;")
        )
        delay_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        delay_layout.addWidget(delay_label)

        self.delay_input = QLineEdit()
        self.delay_input.setText("0")
        self.delay_input.setFixedWidth(sp(48))
        self.delay_input.setPlaceholderText("0")
        delay_layout.addWidget(self.delay_input)

        delay_unit = QLabel("s")
        delay_unit.setStyleSheet(scale_qss("font-size: 12px; background: transparent; border: none; border-radius: 0;"))
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
        self.setFixedSize(sp(72), sp(72))
        self.setCursor(QtCompat.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(4), sp(4), sp(4), sp(4))
        layout.setSpacing(sp(4))

        # 复选框在左上角
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(sp(16), sp(16))
        self.checkbox.setStyleSheet(get_small_checkbox_stylesheet(self.theme))
        self.checkbox.stateChanged.connect(self._on_check_changed)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(sp(24), sp(24))
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none; border-radius: 0;")

        # 名称
        self.name_label = QLabel(self.shortcut.name[:8] if self.shortcut.name else tr("未命名"))
        self.name_label.setAlignment(QtCompat.AlignCenter)
        self.name_label.setStyleSheet(
            scale_qss("font-size: 11px; background: transparent; border: none; border-radius: 0;")
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
        self._bg_color = QColor(surface(self.theme, "bg_hover_subtle"))
        self._bg_color.setAlpha(8 if self.theme == "dark" else 5)
        self._border_color = QColor(surface(self.theme, "bg_hover_subtle"))
        self._border_color.setAlpha(15 if self.theme == "dark" else 10)
        self._radius = 6.0
        # Remove QSS border-radius — painting is handled by paintEvent now
        self.setStyleSheet("QFrame { background: transparent; border: none; border-radius: 0; }")
        self.update()

    def paintEvent(self, event):  # noqa: paint_perf
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

        pen = QPen(self._border_color, 1.0)
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


class BatchLaunchDialog(BaseDialog):
    """批量启动对话框"""

    def __init__(self, data_manager: DataManager, folder_id: str, parent=None, shortcut: ShortcutItem | None = None):
        self.data_manager = data_manager
        self.folder_id = folder_id
        self.shortcut = (
            copy.deepcopy(shortcut) if shortcut is not None else ShortcutItem(type=ShortcutType.BATCH_LAUNCH)
        )
        self._editing_existing = shortcut is not None
        self.launch_cards = []  # type: ignore[var-annotated]
        self._launch_card_by_id = {}  # type: ignore[var-annotated]
        self._shortcut_by_id = {}  # type: ignore[var-annotated]
        self._icon_pixmap_cache = {}  # type: ignore[var-annotated]
        self._shortcut_load_queue = []  # type: ignore[var-annotated]
        self._shortcut_load_started = False
        self._icon_worker = None
        self._icon_thread = None
        self._icon_load_generation = 0
        self._dragging_card_id = None
        self._card_animations = []  # type: ignore[var-annotated]
        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        self._initial_batch_steps = list(getattr(self.shortcut, "batch_launch_steps", None) or [])
        self._selection_restored = False
        self._dialog_finished = False
        self.saved_shortcut = None
        self.selected_order = []  # type: ignore[var-annotated]
        super().__init__(parent)
        self._apply_theme_colors()  # 先应用主题颜色
        self.setWindowTitle(tr("批量启动"))
        self.setFixedSize(sp(700), sp(500))
        self._setup_ui()
        self._apply_theme()
        self._prime_icon_cache_from_parent()

    def _prime_icon_cache_from_parent(self):
        """复用配置窗口已经显示的图标，避免批量启动弹窗重复抽取 exe/ico。"""
        parent = self.parent()
        widgets = list(getattr(parent, "icon_widgets", []) or [])
        if not widgets:
            icon_grid = getattr(parent, "icon_grid", None)
            widgets = list(getattr(icon_grid, "icon_widgets", []) or [])
        for widget in widgets:
            try:
                shortcut_id = getattr(getattr(widget, "shortcut", None), "id", "")
                pixmap = widget.icon_label.pixmap() if hasattr(widget, "icon_label") else None
                if shortcut_id and pixmap and not pixmap.isNull():
                    self._icon_pixmap_cache[shortcut_id] = QPixmap(pixmap)
            except RuntimeError:
                continue

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sp(16), sp(16), sp(16), sp(16))
        main_layout.setSpacing(sp(12))

        # 标题
        title = QLabel(tr("批量启动配置"))
        title.setStyleSheet(
            scale_qss("font-size: 13px; font-weight: 400; background: transparent; border: none; border-radius: 0;")
        )
        main_layout.addWidget(title)

        # 左右分栏
        content_layout = QHBoxLayout()
        content_layout.setSpacing(sp(12))

        # 左侧：已选图标列表
        left_panel = self._create_left_panel()
        content_layout.addWidget(left_panel, 1)

        # 右侧：候选图标
        right_panel = self._create_right_panel()
        content_layout.addWidget(right_panel, 1)

        main_layout.addLayout(content_layout, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("取消"))
        cancel_btn.setFixedSize(sp(80), sp(32))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("确定"))
        ok_btn.setFixedSize(sp(80), sp(32))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._save_batch_launch)
        btn_layout.addWidget(ok_btn)

        main_layout.addLayout(btn_layout)

    def _create_batch_info_panel(self):
        """创建左上角名称与图标设置栏。"""
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: transparent; border: none; border-radius: 0; }")
        layout = QHBoxLayout(panel)
        layout.setSpacing(sp(8))
        layout.setContentsMargins(0, 0, 0, 0)

        self.batch_icon_preview = QLabel()
        self.batch_icon_preview.setFixedSize(sp(32), sp(32))
        self.batch_icon_preview.setAlignment(QtCompat.AlignCenter)
        self.batch_icon_preview.setStyleSheet(
            scale_qss(
                """
            QLabel {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
        """
            )
        )
        layout.addWidget(self.batch_icon_preview)

        right = QVBoxLayout()
        right.setSpacing(sp(6))

        name_row = QHBoxLayout()
        name_row.setSpacing(sp(6))
        name_label = QLabel(tr("名称:"))
        name_label.setStyleSheet(scale_qss("font-size: 12px; background: transparent; border: none; border-radius: 0;"))
        self.batch_name_edit = QLineEdit()
        self.batch_name_edit.setMaxLength(6)
        self.batch_name_edit.setText((getattr(self.shortcut, "name", "") or tr("批量启动"))[:6])
        self.batch_name_edit.setPlaceholderText(tr("最多6个字符"))
        self.batch_name_edit.textChanged.connect(lambda: self._update_batch_icon_preview())
        name_row.addWidget(name_label)
        name_row.addWidget(self.batch_name_edit, 1)
        right.addLayout(name_row)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(sp(6))
        self.batch_icon_edit = QLineEdit()
        self.batch_icon_edit.setPlaceholderText(tr("留空则使用默认图标"))
        self.batch_icon_edit.setReadOnly(True)
        if self._custom_icon_path:
            self.batch_icon_edit.setText(self._custom_icon_path)
        icon_row.addWidget(self.batch_icon_edit, 1)

        browse_btn = QPushButton(tr("选择图标..."))
        browse_btn.clicked.connect(self._browse_batch_icon)
        icon_row.addWidget(browse_btn)
        self._browse_batch_icon_btn = browse_btn

        clear_btn = QPushButton(tr("清除"))
        clear_btn.clicked.connect(self._clear_batch_icon)
        icon_row.addWidget(clear_btn)
        self._clear_batch_icon_btn = clear_btn

        self.batch_invert_light_cb = QCheckBox(tr("浅色反转"))
        self.batch_invert_dark_cb = QCheckBox(tr("深色反转"))
        self.batch_invert_light_cb.setChecked(bool(getattr(self.shortcut, "icon_invert_light", False)))
        self.batch_invert_dark_cb.setChecked(bool(getattr(self.shortcut, "icon_invert_dark", False)))
        self.batch_invert_dark_cb.stateChanged.connect(lambda: self._update_batch_icon_preview())
        self.batch_invert_light_cb.stateChanged.connect(lambda: self._update_batch_icon_preview())
        icon_row.addWidget(self.batch_invert_light_cb)
        icon_row.addWidget(self.batch_invert_dark_cb)

        right.addLayout(icon_row)
        layout.addLayout(right, 1)

        self._update_batch_icon_preview()
        return panel

    def _create_left_panel(self):
        """创建左侧面板 - 已选图标卡片列表"""
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: transparent; border: none; border-radius: 0; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(8))

        layout.addWidget(self._create_batch_info_panel())

        label = QLabel(tr("启动列表（从上到下执行）"))
        label.setStyleSheet(scale_qss("font-size: 12px; background: transparent; border: none; border-radius: 0;"))
        layout.addWidget(label)

        self.cards_scroll = SmoothScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.NoFrame)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(sp(4))
        self.cards_layout.addStretch()

        self.cards_scroll.setWidget(self.cards_container)
        layout.addWidget(self.cards_scroll, 1)

        return panel

    def _create_right_panel(self):
        """创建右侧面板 - 图标候选栏"""
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: transparent; border: none; border-radius: 0; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sp(8))

        label = QLabel(tr("可选图标"))
        label.setStyleSheet(scale_qss("font-size: 12px; background: transparent; border: none; border-radius: 0;"))
        layout.addWidget(label)

        self.icon_selector = IconSelectorWidget(self.theme)
        self.icon_selector.icon_checked.connect(self._on_icon_checked)
        layout.addWidget(self.icon_selector, 1)

        return panel

    def showEvent(self, event):
        super().showEvent(event)
        if not self._shortcut_load_started:
            self._shortcut_load_started = True
            QTimer.singleShot(280, self._load_shortcuts)

    def _load_shortcuts(self):
        """加载所有普通分类下的快捷方式。"""
        if getattr(self, "_dialog_finished", False):
            return
        try:
            all_shortcuts = []
            folders = sorted(
                (folder for folder in self.data_manager.data.folders if not getattr(folder, "is_icon_repo", False)),
                key=lambda folder: int(getattr(folder, "order", 0) or 0),
            )
            for folder in folders:
                if folder.items:
                    all_shortcuts.extend(
                        sorted(
                            (item for item in folder.items if getattr(item, "enabled", True)),
                            key=lambda item: int(getattr(item, "order", 0) or 0),
                        )
                    )

            shortcuts = [s for s in all_shortcuts if s.type in LAUNCHABLE_TYPES]
            self._shortcut_by_id = {shortcut.id: shortcut for shortcut in shortcuts}
            self.icon_selector.begin_shortcuts()
            self._shortcut_load_queue = list(shortcuts)
            self._load_next_shortcut_batch()
        except Exception as exc:
            logger.error("加载快捷方式失败: %s", exc, exc_info=True)

    def _load_next_shortcut_batch(self):
        if getattr(self, "_dialog_finished", False):
            self._shortcut_load_queue = []
            return

        batch_size = 24
        batch = self._shortcut_load_queue[:batch_size]
        self._shortcut_load_queue = self._shortcut_load_queue[batch_size:]
        self.icon_selector.append_shortcuts(batch)
        self._apply_cached_icons(batch)

        if self._shortcut_load_queue:
            QTimer.singleShot(1, self._load_next_shortcut_batch)
        else:
            self._restore_existing_selection()
            self._start_async_icon_load()

    def _restore_existing_selection(self):
        if self._selection_restored:
            return
        self._selection_restored = True
        for step in ShortcutItem._normalize_chain_steps(self._initial_batch_steps):
            shortcut_id = str(step.get("shortcut_id") or "")
            if not shortcut_id or shortcut_id not in self._shortcut_by_id:
                continue
            self.icon_selector.set_checked(shortcut_id, True)
            if shortcut_id not in self.selected_order:
                self._add_launch_card(shortcut_id)
            card = self._launch_card_by_id.get(shortcut_id)
            if not card:
                continue
            delay_seconds = float(step.get("delay_ms", 0) or 0) / 1000.0
            delay_text = str(int(delay_seconds)) if delay_seconds.is_integer() else f"{delay_seconds:g}"
            card.delay_input.setText(delay_text)
            card.pause_checkbox.setChecked(bool(step.get("stop_on_error", True)))

    def _apply_cached_icons(self, shortcuts):
        for shortcut in shortcuts:
            pixmap = self._icon_pixmap_cache.get(shortcut.id)
            if pixmap and not pixmap.isNull():
                self.icon_selector.set_icon_pixmap(shortcut.id, pixmap)

    def _start_async_icon_load(self):
        """后台加载其它分类图标，避免主线程同步抽取导致小窗口闪烁。"""
        tasks = []
        for shortcut in self._shortcut_by_id.values():
            if shortcut.id in self._icon_pixmap_cache:
                continue
            if (
                shortcut.type in (ShortcutType.HOTKEY, ShortcutType.URL, ShortcutType.COMMAND)
                and not shortcut.icon_path
            ):
                continue
            tasks.append((shortcut.id, shortcut.icon_path, shortcut.target_path, 24, shortcut.type))

        if not tasks:
            return

        self._stop_icon_thread()
        self._icon_load_generation += 1
        generation = self._icon_load_generation
        try:
            from ui.config_window.icon_grid import _IconLoadWorker

            self._icon_worker = _IconLoadWorker(tasks)
            self._icon_thread = QThread()
            self._icon_worker.moveToThread(self._icon_thread)
            self._icon_worker.finished.connect(
                lambda sid, image, gen=generation: self._on_async_icon_loaded(gen, sid, image)
            )
            self._icon_worker.completed.connect(self._icon_thread.quit)
            self._icon_thread.finished.connect(self._icon_worker.deleteLater)
            self._icon_thread.finished.connect(self._icon_thread.deleteLater)
            self._icon_thread.finished.connect(
                lambda gen=generation, thread=self._icon_thread, worker=self._icon_worker: self._on_async_icon_thread_finished(
                    gen, thread, worker
                )
            )
            self._icon_thread.started.connect(self._icon_worker.run)
            self._icon_thread.start()
        except Exception as exc:
            logger.debug("启动批量启动图标后台加载失败: %s", exc, exc_info=True)

    def _on_async_icon_loaded(self, generation: int, shortcut_id: str, image: QImage):
        if generation != self._icon_load_generation or getattr(self, "_dialog_finished", False):
            return
        if not image or image.isNull():
            shortcut = self._shortcut_by_id.get(shortcut_id)
            pixmap = self._load_icon_on_main_thread(shortcut) if shortcut else None
        else:
            pixmap = QPixmap.fromImage(image)
        if not pixmap or pixmap.isNull():
            return
        self._icon_pixmap_cache[shortcut_id] = pixmap
        self.icon_selector.set_icon_pixmap(shortcut_id, pixmap)
        card = self._launch_card_by_id.get(shortcut_id)
        if card:
            card.set_icon(pixmap)

    def _load_icon_on_main_thread(self, shortcut: ShortcutItem | None) -> QPixmap | None:
        if shortcut is None:
            return None
        try:
            return _load_shortcut_icon(shortcut, 24)
        except Exception:
            logger.debug(
                "批量启动主线程兜底加载图标失败: id=%s name=%r",
                getattr(shortcut, "id", ""),
                getattr(shortcut, "name", ""),
                exc_info=True,
            )
            return None

    def _on_async_icon_load_completed(self):
        thread = self._icon_thread
        if thread is not None:
            try:
                thread.quit()
            except RuntimeError:
                logger.debug("退出批量启动图标线程失败", exc_info=True)

    def _on_async_icon_thread_finished(self, generation: int, thread, worker):
        if generation != getattr(self, "_icon_load_generation", generation):
            return
        if getattr(self, "_icon_thread", None) is thread:
            self._icon_thread = None
        if getattr(self, "_icon_worker", None) is worker:
            self._icon_worker = None

    def _stop_icon_thread(self):
        self._icon_load_generation += 1
        worker = self._icon_worker
        thread = self._icon_thread
        if thread is None:
            self._icon_worker = None
            return
        stopped = stop_qthread_nonblocking(
            thread,
            worker=worker,
            owner="BatchLaunchDialog.icon_loader",
            wait_ms=0,
            disconnect_thread_signals=("finished",),
            disconnect_worker_signals=("finished",),
        )
        if stopped:
            self._icon_worker = None
            self._icon_thread = None

    def _on_icon_checked(self, shortcut_id: str, checked: bool):
        """图标勾选状态改变"""
        if checked:
            self._add_launch_card(shortcut_id)
        else:
            self._remove_launch_card(shortcut_id)

    def _add_launch_card(self, shortcut_id: str):
        """添加启动卡片到左侧列表"""
        if shortcut_id in self.selected_order:
            return

        try:
            shortcut = self._shortcut_by_id.get(shortcut_id) or self.data_manager.get_shortcut_by_id(shortcut_id)
            if not shortcut:
                logger.warning("无法找到快捷方式: %s", shortcut_id)
                self.icon_selector.set_checked(shortcut_id, False)
                return

            card = BatchLaunchCard(shortcut, self.theme)
            card.remove_requested.connect(self._on_card_remove_requested)
            card.drag_started.connect(self._on_card_drag_started)
            card.drag_moved.connect(self._on_card_drag_moved)
            card.drag_finished.connect(self._on_card_drag_finished)
            self.launch_cards.append(card)
            self._launch_card_by_id[shortcut_id] = card
            self.selected_order.append(shortcut_id)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

            pixmap = self._icon_pixmap_cache.get(shortcut_id)
            if not pixmap or pixmap.isNull():
                pixmap = _create_type_icon(shortcut, BatchLaunchCard.ICON_PIXMAP_SIZE)
            card.set_icon(pixmap)
        except Exception as exc:
            logger.error("添加启动卡片失败: %s", exc, exc_info=True)

    def _remove_launch_card(self, shortcut_id: str):
        """移除启动卡片"""
        if shortcut_id not in self.selected_order:
            return

        idx = self.selected_order.index(shortcut_id)
        self.selected_order.pop(idx)
        card = self.launch_cards.pop(idx)
        self._launch_card_by_id.pop(shortcut_id, None)
        self.cards_layout.removeWidget(card)
        card.deleteLater()
        self.icon_selector.set_checked(shortcut_id, False)

    def _on_card_remove_requested(self, shortcut_id: str):
        """卡片请求移除"""
        self._remove_launch_card(shortcut_id)

    def _on_card_drag_started(self, shortcut_id: str):
        self._dragging_card_id = shortcut_id  # type: ignore[assignment]
        card = self._launch_card_by_id.get(shortcut_id)
        if card:
            card.raise_()

    def _on_card_drag_moved(self, shortcut_id: str, global_pos: QPoint):
        if shortcut_id != self._dragging_card_id or shortcut_id not in self.selected_order:
            return

        target_index = self._card_insert_index_for_pos(shortcut_id, global_pos)
        current_index = self.selected_order.index(shortcut_id)
        if target_index == current_index:
            return
        self._move_launch_card(shortcut_id, target_index)

    def _on_card_drag_finished(self, shortcut_id: str):
        if shortcut_id == self._dragging_card_id:
            self._dragging_card_id = None
        self._animate_card_reflow()

    def _card_insert_index_for_pos(self, dragged_id: str, global_pos: QPoint) -> int:
        local_y = self.cards_container.mapFromGlobal(global_pos).y()
        other_cards = [card for card in self.launch_cards if card.shortcut.id != dragged_id]
        for index, card in enumerate(other_cards):
            midpoint = card.y() + card.height() / 2
            if local_y < midpoint:
                return index
        return len(other_cards)

    def _move_launch_card(self, shortcut_id: str, target_index: int):
        if shortcut_id not in self.selected_order:
            return False

        target_index = max(0, min(target_index, len(self.launch_cards) - 1))
        current_index = self.selected_order.index(shortcut_id)
        if current_index == target_index:
            return False

        card = self.launch_cards.pop(current_index)
        self.selected_order.pop(current_index)
        self.launch_cards.insert(target_index, card)
        self.selected_order.insert(target_index, shortcut_id)
        self._rebuild_cards_layout(animate=True)
        card.raise_()
        return True

    def _rebuild_cards_layout(self, animate: bool = False):
        old_positions = {card: QPoint(card.pos()) for card in self.launch_cards}
        for card in self.launch_cards:
            self.cards_layout.removeWidget(card)
        for index, card in enumerate(self.launch_cards):
            self.cards_layout.insertWidget(index, card)
        self.cards_layout.activate()
        self.cards_container.updateGeometry()
        if animate:
            self._animate_card_reflow(old_positions)

    def _animate_card_reflow(self, old_positions: dict | None = None):
        old_positions = old_positions or {}
        self.cards_layout.activate()
        for card in self.launch_cards:
            start_pos = old_positions.get(card)
            end_pos = QPoint(card.pos())
            if start_pos is None or start_pos == end_pos:
                continue
            stop_animation(getattr(card, "_pos_anim", None), owner="BatchLaunchDialog.card_reflow")
            card.move(start_pos)
            anim = QPropertyAnimation(card, b"pos", card)
            anim.setDuration(130)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            card._pos_anim = anim
            anim.finished.connect(lambda animation=anim, card=card: self._forget_card_animation(animation, card))
            self._card_animations.append(anim)
            anim.start()

    def _forget_card_animation(self, animation, card=None):
        try:
            self._card_animations.remove(animation)
        except ValueError as exc:
            logger.debug("批量启动卡片动画已被移除: %s", exc, exc_info=True)
        if card is not None and getattr(card, "_pos_anim", None) is animation:
            card._pos_anim = None

    def _browse_batch_icon(self):
        file_path = choose_custom_icon(self, tr("选择图标"))
        if file_path:
            self._custom_icon_path = file_path
            self.batch_icon_edit.setText(file_path)
            self._update_batch_icon_preview()

    def _clear_batch_icon(self):
        self._custom_icon_path = ""
        self.batch_icon_edit.clear()
        self._update_batch_icon_preview()

    def _update_batch_icon_preview(self):
        pixmap = None
        if self._custom_icon_path:
            try:
                from core.icon_extractor import IconExtractor

                if "," in self._custom_icon_path or os.path.exists(self._custom_icon_path):
                    pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
            except Exception as exc:
                logger.debug("加载批量启动图标失败: %s", exc, exc_info=True)

        if not pixmap or pixmap.isNull():
            name = self.batch_name_edit.text() if hasattr(self, "batch_name_edit") else tr("批量启动")
            pixmap = _create_type_icon(ShortcutItem(type=ShortcutType.BATCH_LAUNCH, name=name), 48)
        _current_theme = getattr(self, "theme", "dark")
        _need_invert = (
            self.batch_invert_light_cb.isChecked()
            if _current_theme == "light"
            else self.batch_invert_dark_cb.isChecked()
        )
        if _need_invert and pixmap and not pixmap.isNull():
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.invert_pixmap(pixmap)
            except Exception as exc:
                logger.debug("反转批量启动图标失败: %s", exc, exc_info=True)
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.batch_icon_preview.setPixmap(pixmap)

    def _build_batch_launch_steps(self):
        steps = []
        for card in self.launch_cards:
            config = card.get_config()
            delay_ms = max(0, int(float(config.get("delay", 0) or 0) * 1000))
            steps.append(
                {
                    "shortcut_id": config["shortcut_id"],
                    "enabled": True,
                    "stop_on_error": bool(config["pause_on_failure"]),
                    "delay_ms": delay_ms,
                }
            )
        return ShortcutItem._normalize_chain_steps(steps)

    def get_shortcut(self) -> ShortcutItem:
        shortcut = copy.deepcopy(self.shortcut)
        shortcut.type = ShortcutType.BATCH_LAUNCH
        shortcut.name = (self.batch_name_edit.text().strip() or tr("批量启动"))[:6]
        shortcut.batch_launch_steps = self._build_batch_launch_steps()
        shortcut.module_id = BATCH_LAUNCH_MODULE_ID
        shortcut.module_version = BATCH_LAUNCH_MODULE_VERSION
        shortcut.icon_path = self._custom_icon_path
        shortcut.icon_invert_light = self.batch_invert_light_cb.isChecked()
        shortcut.icon_invert_dark = self.batch_invert_dark_cb.isChecked()
        return shortcut

    def _save_batch_launch(self):
        """保存批量启动配置。"""
        name = self.batch_name_edit.text().strip()
        if not name:
            logger.warning("批量启动保存失败: 名称为空")
            self.batch_name_edit.setFocus()
            return

        if not self.launch_cards:
            from ui.styles.themed_messagebox import ThemedMessageBox

            logger.warning("批量启动保存失败: 未选择任何启动项目")
            ThemedMessageBox.information(self, tr("提示"), tr("请至少选择一个图标"))
            return

        shortcut = self.get_shortcut()
        if self._editing_existing:
            logger.info(
                "批量启动编辑确认: id=%s name=%r steps=%s",
                getattr(shortcut, "id", ""),
                getattr(shortcut, "name", ""),
                len(getattr(shortcut, "batch_launch_steps", []) or []),
            )
            self.saved_shortcut = shortcut
            self.accept()
            return

        if not self.data_manager.add_shortcut(self.folder_id, shortcut):
            from ui.styles.themed_messagebox import ThemedMessageBox

            logger.error(
                "批量启动保存失败: folder_id=%s name=%r steps=%s",
                self.folder_id,
                getattr(shortcut, "name", ""),
                len(getattr(shortcut, "batch_launch_steps", []) or []),
            )
            ThemedMessageBox.warning(self, tr("提示"), tr("保存批量启动失败"))
            return

        logger.info(
            "批量启动保存成功: folder_id=%s id=%s name=%r steps=%s",
            self.folder_id,
            getattr(shortcut, "id", ""),
            getattr(shortcut, "name", ""),
            len(getattr(shortcut, "batch_launch_steps", []) or []),
        )
        self.saved_shortcut = shortcut
        self.accept()

    def done(self, result):
        self._dialog_finished = True
        self._stop_icon_thread()
        super().done(result)

    def deleteLater(self):
        self._dialog_finished = True
        self._stop_icon_thread()
        super().deleteLater()

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme
        style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        self.setStyleSheet(style)

        btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in self.findChildren(QPushButton):
            btn.setStyleSheet(btn_style)

        checkbox_style = get_small_checkbox_stylesheet(theme)
        for cb in self.findChildren(QCheckBox):
            cb.setStyleSheet(checkbox_style)

        invert_cb_style = get_compact_checkbox_stylesheet(theme)
        self.batch_invert_light_cb.setStyleSheet(invert_cb_style)
        self.batch_invert_dark_cb.setStyleSheet(invert_cb_style)
