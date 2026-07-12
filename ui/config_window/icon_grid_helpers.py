"""Icon grid helper classes — extracted from icon_grid."""

from __future__ import annotations

import logging

from core.i18n import tr
from core.qt_worker import BaseLoggedWorker
from qt_compat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPoint,
    QPushButton,
    QRectF,
    QtCompat,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism, PopupMenu
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.pixel_snap import make_cosmetic_pen, snap_rect
from ui.utils.ui_scale import scale_qss, sp

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class SimpleStatusDialog(QDialog):
    """Simple semi-transparent status/notification dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.styles.design_tokens import border as _border
        from ui.styles.design_tokens import surface as _surface

        self.bg_color = _surface("dark", "bg_dialog")
        self.border_color = _border("dark", "subtle")

        apply_custom_window_chrome(self, kind="window", translucent=True)
        self.setWindowOpacity(0)
        self.corner_radius = sp(8)
        self.setModal(True)

    def _apply_theme(self, theme=None):
        if theme is None:
            theme = "dark"
        self.theme = theme
        from ui.styles.design_tokens import border as _border
        from ui.styles.design_tokens import surface as _surface

        self.bg_color = _surface(theme, "bg_dialog")
        self.border_color = _border(theme, "subtle")
        self.update()

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        from qt_compat import QPainterPath as _QPainterPath
        from ui.utils.window_effect import is_win10, paint_win10_rounded_surface

        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)
            if is_win10():
                paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                return
            rect = snap_rect(QRectF(0, 0, self.width(), self.height()))
            path = _QPainterPath()
            path.addRoundedRect(rect, self.corner_radius, self.corner_radius)
            painter.fillPath(path, self.bg_color)
            painter.setPen(make_cosmetic_pen(self.border_color))
            painter.drawPath(path)
        finally:
            painter.end()

    def showEvent(self, event):
        from ui.utils.dialog_helper import center_dialog_on_main_window
        from ui.utils.window_effect import enable_acrylic_for_config_window, get_window_effect

        super().showEvent(event)
        try:
            enable_acrylic_for_config_window(self, "dark", radius=self.corner_radius)
        except Exception:
            get_window_effect().set_blur_behind(self.winId())
        center_dialog_on_main_window(self)


class MoveFolderDialog(BaseDialog):
    """Dialog for selecting a target folder when moving shortcuts."""

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = folders
        self.selected_folder = None
        self.setWindowTitle(tr("移动所选到"))
        self.setFixedSize(sp(300), sp(136))
        self._setup_ui()
        self._apply_move_folder_styles()

    def _folder_display_name(self, folder):
        name = folder.name
        if getattr(folder, "is_dock", False):
            return f"\U0001f4cc {name}  [DOCK]"
        if getattr(folder, "is_icon_repo", False):
            return f"\U0001f4e6 {name}  [图标仓库]"
        return f"\U0001f4c1 {name}"

    def _setup_ui(self):
        from qt_compat import QComboBox

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(sp(16), sp(16), sp(16), sp(16))
        main_layout.setSpacing(sp(8))
        label = QLabel(tr("目标位置:"))
        label.setStyleSheet(scale_qss("font-size: 11px;"))
        main_layout.addWidget(label)
        self.combo = QComboBox()
        self.combo.setFixedHeight(sp(28))
        for folder in self.folders:
            self.combo.addItem(self._folder_display_name(folder), folder)
        self.combo.showPopup = lambda: self._show_folder_popup()
        main_layout.addWidget(self.combo)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(sp(8))
        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.setFixedHeight(sp(28))
        self.cancel_btn.setMinimumWidth(sp(60))
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton(tr("确定"))
        self.ok_btn.setFixedHeight(sp(28))
        self.ok_btn.setMinimumWidth(sp(60))
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(btn_layout)
        container = QWidget()
        container.setLayout(main_layout)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

    def _show_folder_popup(self):
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        for i in range(self.combo.count()):
            folder_name = self.combo.itemText(i)
            menu.add_action(folder_name, lambda idx=i: self.combo.setCurrentIndex(idx))
        pos = self.combo.mapToGlobal(self.combo.rect().bottomLeft())
        menu.setMinimumWidth(self.combo.width())
        menu.popup(pos)

    def _on_ok(self):
        self.selected_folder = self.combo.currentData()
        self.accept()

    def _apply_move_folder_styles(self):
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(self.theme)
        self.setStyleSheet(base_style + "QDialog { background: transparent; border-radius: 0; border: none; }")
        if not hasattr(self, "cancel_btn") or not hasattr(self, "ok_btn"):
            return
        if self.theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_hover = "rgba(255,255,255,0.28)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_text = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_hover = "rgba(255,255,255,0.95)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_text = "#1D1D1F"
        btn_style = scale_qss(
            f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 8px;
                padding: 4px 13px;
                color: {btn_text};
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {btn_hover}; }}
            QPushButton:pressed {{ background-color: {btn_bg}; opacity: 0.8; }}
        """
        )
        self.cancel_btn.setStyleSheet(btn_style)
        self.ok_btn.setStyleSheet(btn_style)


class IconContainer(QWidget):
    """Icon container widget."""

    context_menu_requested = pyqtSignal(QPoint)
    blank_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border-radius: 0; border: none;")

    def mousePressEvent(self, event):
        child = self.childAt(event.pos())
        if child is None or child == self:
            if event.button() == QtCompat.LeftButton:
                self.blank_clicked.emit()
                event.accept()
                return
            if event.button() == QtCompat.RightButton:
                global_pos = self.mapToGlobal(event.pos())
                self.context_menu_requested.emit(global_pos)
                event.accept()
                return
        super().mousePressEvent(event)


class _IconLoadWorker(BaseLoggedWorker):
    """Background worker for loading icons in icon_grid."""

    finished = pyqtSignal(str, object)  # (shortcut_id, QImage | None)

    def __init__(self, tasks):
        super().__init__(name="_IconLoadWorker")
        self._tasks = tasks

    def run(self):
        try:
            from core.icon_extractor import IconExtractor
        except Exception:
            self.completed.emit()
            return

        com_ok = self.com_initialize()
        try:
            for shortcut_id, icon_path, target_path, size, _shortcut_type in self._tasks:
                if self._cancel_requested:
                    break
                image = None
                if icon_path:
                    if not IconExtractor._is_pixmap_preferred_resource(icon_path):
                        image = IconExtractor.from_file(icon_path, size, return_image=True)
                if image is None and target_path:
                    image = IconExtractor.extract(
                        target_path, target_path, size, return_image=True, fallback_to_default=False
                    )
                if self._cancel_requested:
                    break
                self.finished.emit(shortcut_id, image)
        except Exception as exc:
            logger.exception("[_IconLoadWorker] fatal error: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            if com_ok:
                self.com_uninitialize()
            self.completed.emit()


class _BatchFaviconFetchWorker(BaseLoggedWorker):
    """Background worker for batch favicon fetching."""

    completed = pyqtSignal(int, int)  # (success, total) — shadows BaseLoggedWorker.completed
    result = pyqtSignal(str, str, str)  # (shortcut_id, icon_path, error)
    progress = pyqtSignal(int, int)  # (completed, total)

    def __init__(self, tasks):
        super().__init__(name="_BatchFaviconFetchWorker")
        self._tasks = tasks

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from core.favicon_cache import fetch_favicon

        total = len(self._tasks)
        completed_count = 0
        success_count = 0

        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}
                for sid, name, url in self._tasks:
                    if self._cancel_requested:
                        break
                    futures[executor.submit(fetch_favicon, url)] = (sid, name, url)

                for future in as_completed(futures):
                    if self._cancel_requested:
                        break
                    sid, name, url = futures[future]
                    try:
                        result = future.result()
                        if result:
                            self.result.emit(sid, result, "")
                            success_count += 1
                        else:
                            self.result.emit(sid, "", "未获取到图标")
                    except Exception as e:
                        self.result.emit(sid, "", str(e))
                    completed_count += 1
                    self.progress.emit(completed_count, total)
        except Exception as exc:
            logger.exception("[_BatchFaviconFetchWorker] fatal error: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.completed.emit(success_count, total)


__all__ = [
    "SimpleStatusDialog",
    "MoveFolderDialog",
    "IconContainer",
    "_IconLoadWorker",
    "_BatchFaviconFetchWorker",
]
