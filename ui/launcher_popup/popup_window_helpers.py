"""
弹窗辅助类：FolderSyncWorker 和 IconFlashOverlay。
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
import logging

from qt_compat import (
    QColor,
    QFontMetrics,
    QPainter,
    QPixmap,
    QRect,
    Qt,
    QtCompat,
    QThread,
    QWidget,
    pyqtProperty,
)
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)

try:
    from core.icon_extractor import should_invert_icon as _should_invert_icon
except ImportError:
    _should_invert_icon = None  # type: ignore[assignment]


def sync_all_folders_for_data_manager(data_manager) -> tuple[int, int]:
    """Synchronize linked folders without touching any GUI object."""
    try:
        from core.folder_sync import sync_folder

        folders = list(getattr(getattr(data_manager, "data", None), "folders", []) or [])
        total_added = 0
        total_removed = 0

        for folder in folders:
            if not getattr(folder, "linked_path", ""):
                continue
            try:
                added, removed = sync_folder(data_manager, folder.id)
                total_added += added
                total_removed += removed
                logger.info("同步文件夹 '%s': 新增 %s 项, 删除 %s 项", folder.name, added, removed)
            except Exception as e:
                logger.error("同步文件夹 '%s' 失败: %s", getattr(folder, "name", ""), e)

        if total_added > 0 or total_removed > 0:
            logger.info("所有文件夹同步完成: 总计新增 %s 项, 删除 %s 项", total_added, total_removed)
        else:
            logger.info("所有文件夹已是最新状态")

        return total_added, total_removed
    except Exception as e:
        logger.error("同步文件夹失败: %s", e)
        return 0, 0


class FolderSyncWorker(QThread):
    """后台文件夹同步工作线程，避免 GUI 线程卡顿"""

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager

    def run(self):
        try:
            sync_all_folders_for_data_manager(self.data_manager)
        except Exception as e:
            logger.error(f"后台文件夹同步失败: {e}")


class IconFlashOverlay(QWidget):
    """Lightweight icon flash layer that does not repaint the launcher content."""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher
        self._opacity = 0.0
        self._duration_ms = 96
        self._peak_opacity = 0.38
        self._items = []
        self._dirty_rect = QRect()
        self._animation = None
        self._flash_generation = 0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()

    def _next_flash_generation(self) -> int:
        self._flash_generation = int(getattr(self, "_flash_generation", 0) or 0) + 1
        return int(self._flash_generation)

    def _is_flash_current(self, generation: int) -> bool:
        return generation == int(getattr(self, "_flash_generation", -1) or -1)

    def _get_flash_opacity(self):
        return self._opacity

    def _set_flash_opacity(self, value):
        self._opacity = max(0.0, min(float(value), self._peak_opacity))
        if self.isVisible() and not self._dirty_rect.isNull():
            self.update(self._dirty_rect)

    flashOpacity = pyqtProperty(float, _get_flash_opacity, _set_flash_opacity)

    def start(self):
        if self.isVisible():
            self.stop()

        self.setGeometry(self.launcher.rect())
        self._items = list(self._snapshot_icons())
        if not self._items:
            return
        self._dirty_rect = self._calculate_dirty_rect()
        self.raise_()
        self._opacity = self._peak_opacity
        self.show()
        self.update(self._dirty_rect)
        generation = self._next_flash_generation()
        self._animation = QtCompat.QPropertyAnimation(self, b"flashOpacity", self)
        self._animation.setStartValue(self._peak_opacity)
        self._animation.setEndValue(0.0)
        self._animation.setDuration(self._duration_ms)
        self._animation.setEasingCurve(QtCompat.OutCubic)
        self._animation.finished.connect(lambda generation=generation: self._finish(generation))
        self._animation.start()

    def stop(self):
        generation = self._next_flash_generation()
        try:
            if self._animation is not None:
                self._animation.stop()
        except Exception as exc:
            logger.debug("停止图标闪烁动画失败: %s", exc, exc_info=True)
        self._finish(generation)

    def _finish(self, generation: int | None = None):
        if generation is not None and not self._is_flash_current(generation):
            return
        self._opacity = 0.0
        self._items = []
        dirty_rect = QRect(self._dirty_rect)
        self._dirty_rect = QRect()
        self.hide()
        if not dirty_rect.isNull():
            try:
                self.launcher.update(dirty_rect)
            except Exception as exc:
                logger.debug("更新启动器区域失败: %s", exc, exc_info=True)

    def _calculate_dirty_rect(self):
        dirty = QRect()
        for x, y, pixmap, _cover in self._items:
            rect = QRect(int(x), int(y), pixmap.width(), pixmap.height()).adjusted(-sp(4), -sp(4), sp(4), sp(4))
            dirty = rect if dirty.isNull() else dirty.united(rect)
        return dirty.intersected(self.rect())

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
        text_spacing = sp(1)
        use_card = True

        if 0 <= current_page < len(pages):
            items = getattr(pages[current_page], "items", []) or []
            bottom_margin = sp(6)
            indicator_height = sp(16) if len(pages) > 1 else 0
            indicator_spacing = sp(4) if len(pages) > 1 else 0
            dock_height = int(getattr(launcher, "dock_height", 0) or 0)
            if not (getattr(launcher, "dock_items", None) and dock_height > 0):
                dock_height = 0
            shadow_margin = int(launcher.__dict__.get("shadow_margin", 0) or 0)
            icons_bottom = (
                launcher.height() - shadow_margin - bottom_margin - dock_height - indicator_height - indicator_spacing
            )
            for i, item in enumerate(items[: cols * fixed_rows]):
                row = i // cols
                col = i % cols
                x = padding + col * cell_size
                y = icons_bottom - (fixed_rows - row) * cell_h
                if use_card:
                    card_pad = sp(4)
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
            try:
                display_rows = launcher._dock_display_rows(visible_count, cols)
                dock_row_stride = launcher._get_dock_row_stride(display_rows)
                first_icon_y = launcher._dock_first_icon_y(display_rows)
            except Exception:
                dock_row_stride = icon_size + sp(6)
                first_icon_y = dock_y + sp(12)
            for i in range(visible_count):
                row = i // cols
                if row >= dock_height_mode:
                    break
                col = i % cols
                x = start_x + col * cell_size
                y = first_icon_y + row * dock_row_stride
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
        _tint_dark = QColor()
        _tint_dark.setRgb(200, 200, 200)
        _tint_light = QColor(Qt.white)
        color = _tint_dark if theme == "dark" else _tint_light
        painter.fillRect(cover.rect(), color)
        painter.end()
        return cover

    def paintEvent(self, event):  # noqa: paint_perf
        if self._opacity <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setOpacity(self._opacity)
        dirty = event.rect()
        for x, y, _pixmap, cover in self._items:
            if not QRect(int(x), int(y), cover.width(), cover.height()).intersects(dirty):
                continue
            painter.drawPixmap(x, y, cover)
        painter.end()
