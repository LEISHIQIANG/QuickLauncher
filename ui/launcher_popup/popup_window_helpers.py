"""
弹窗辅助类：FolderSyncWorker 和 IconFlashOverlay。
"""

import logging
import time

from qt_compat import (
    QColor,
    QFontMetrics,
    QPainter,
    QPixmap,
    Qt,
    QtCompat,
    QThread,
    QTimer,
    QWidget,
)

logger = logging.getLogger(__name__)

try:
    from core.icon_extractor import should_invert_icon as _should_invert_icon
except ImportError:
    _should_invert_icon = None


class FolderSyncWorker(QThread):
    """后台文件夹同步工作线程，避免 GUI 线程卡顿"""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def run(self):
        try:
            self.launcher._sync_all_folders()
        except Exception as e:
            logger.error(f"后台文件夹同步失败: {e}")


class IconFlashOverlay(QWidget):
    """Lightweight icon flash layer that does not repaint the launcher content."""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher
        self._opacity = 0.0
        self._started_at = 0.0
        self._last_started_at = 0.0
        self._duration_ms = 140
        self._items = []
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()

    def start(self):
        now = time.perf_counter()
        if now - self._last_started_at < 0.45:
            return
        self.setGeometry(self.launcher.rect())
        self._items = list(self._snapshot_icons())
        if not self._items:
            return
        self._last_started_at = now
        self.raise_()
        self._started_at = time.perf_counter()
        self._opacity = 0.32
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self._opacity = 0.0
        self._items = []
        self.hide()

    def _tick(self):
        elapsed_ms = (time.perf_counter() - self._started_at) * 1000.0
        t = max(0.0, min(1.0, elapsed_ms / self._duration_ms))
        if t >= 1.0:
            self.stop()
            return

        eased = 1.0 - (1.0 - t) * (1.0 - t)
        self._opacity = 0.32 * (1.0 - eased)
        self.update()

    def _snapshot_icons(self):
        launcher = self.launcher
        icon_size = int(getattr(launcher, "icon_size", 0) or 0)
        if icon_size <= 0:
            return

        pages = getattr(launcher, "pages", []) or []
        current_page = int(getattr(launcher, "current_page", 0) or 0)
        cols = max(1, int(getattr(launcher, "cols", 1) or 1))
        fixed_rows = max(1, int(getattr(launcher, "fixed_rows", 1) or 1))
        cell_size = int(getattr(launcher, "cell_size", icon_size) or icon_size)
        cell_h = int(getattr(launcher, "cell_h", cell_size) or cell_size)
        padding = int(getattr(launcher, "padding", 0) or 0)
        text_h = QFontMetrics(getattr(launcher, "_label_font", launcher.font())).height()
        text_spacing = 1
        use_card = getattr(getattr(launcher, "settings", None), "bg_mode", "theme") == "acrylic"

        if 0 <= current_page < len(pages):
            items = getattr(pages[current_page], "items", []) or []
            bottom_margin = 6
            indicator_height = 16 if len(pages) > 1 else 0
            indicator_spacing = 4 if len(pages) > 1 else 0
            dock_height = int(getattr(launcher, "dock_height", 0) or 0)
            if not (getattr(launcher, "dock_items", None) and dock_height > 0):
                dock_height = 0
            icons_bottom = launcher.height() - bottom_margin - dock_height - indicator_height - indicator_spacing
            for i, item in enumerate(items[: cols * fixed_rows]):
                row = i // cols
                col = i % cols
                x = padding + col * cell_size
                y = icons_bottom - (fixed_rows - row) * cell_h
                if use_card:
                    card_pad = 2
                    card_size = icon_size + card_pad * 2
                    total_h = card_size + text_spacing + text_h
                    card_y = y + (cell_h - total_h) // 2
                    card_x = x + (cell_size - card_size) // 2
                    icon_x = card_x + card_pad
                    icon_y = card_y + card_pad
                else:
                    total_h = icon_size + text_spacing + text_h
                    icon_x = x + (cell_size - icon_size) // 2
                    icon_y = y + (cell_h - total_h) // 2
                pixmap = self._icon_pixmap(item)
                if pixmap is not None:
                    yield icon_x, icon_y, pixmap, self._cover_pixmap(pixmap)

        dock_items = getattr(launcher, "dock_items", []) or []
        dock_height = int(getattr(launcher, "dock_height", 0) or 0)
        if dock_items and dock_height > 0:
            dock_height_mode = max(1, int(getattr(launcher.settings, "dock_height_mode", 1) or 1))
            visible_count = len(dock_items)
            if dock_height_mode == 1:
                visible_count = min(visible_count, cols)
            line_width = (
                cols * cell_size
                if dock_height_mode > 1 and visible_count > cols
                else min(visible_count, cols) * cell_size
            )
            start_x = (launcher.width() - line_width) // 2
            dock_y = int(getattr(launcher, "dock_y", 0) or 0)
            dock_row_stride = icon_size + 6
            for i in range(visible_count):
                row = i // cols
                if row >= dock_height_mode:
                    break
                col = i % cols
                x = start_x + col * cell_size
                y = dock_y + 8 + row * dock_row_stride
                icon_x = x + (cell_size - icon_size) // 2
                pixmap = self._icon_pixmap(dock_items[i])
                if pixmap is not None:
                    yield icon_x, y, pixmap, self._cover_pixmap(pixmap)

    def _icon_pixmap(self, item):
        try:
            need_invert = False
            try:
                if _should_invert_icon is not None:
                    current_theme = getattr(self.launcher.settings, "theme", "dark")
                    need_invert = _should_invert_icon(item, current_theme)
            except Exception:
                need_invert = False

            pixmap = self.launcher._get_cached_icon_for_animation(item, need_invert)
            if pixmap is None:
                default_key = self.launcher._default_icon_cache_key(item)
                pixmap = self.launcher._default_icon_cache.get(default_key)
        except Exception:
            return None
        if pixmap is None or pixmap.isNull():
            return None
        return pixmap

    def _cover_pixmap(self, pixmap):
        cover = QPixmap(pixmap.size())
        cover.fill(QtCompat.transparent)
        painter = QPainter(cover)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        theme = getattr(getattr(self.launcher, "settings", None), "theme", "dark")
        color = QColor(200, 200, 200) if theme == "dark" else QColor(255, 255, 255)
        painter.fillRect(cover.rect(), color)
        painter.end()
        return cover

    def paintEvent(self, event):
        if self._opacity <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        for x, y, _pixmap, cover in self._items:
            painter.drawPixmap(x, y, cover)
        painter.end()
