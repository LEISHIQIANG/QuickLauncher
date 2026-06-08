"""Icon cache and fallback icon helpers for LauncherPopup."""

import logging
import os
import sys

from core import ShortcutItem, ShortcutType
from qt_compat import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRectF, Qt, QtCompat
from ui.utils.ui_scale import font_px

try:
    from core import IconExtractor
    from core.icon_extractor import should_invert_icon as _should_invert_icon

    HAS_ICON_EXTRACTOR = True
except ImportError:
    IconExtractor = None
    HAS_ICON_EXTRACTOR = False
    _should_invert_icon = None

logger = logging.getLogger(__name__)


class PopupIconMixin:
    def _default_icon_cache_key(self, item: ShortcutItem):
        name = getattr(item, "name", "") or "?"
        initial = name[0] if name else "?"
        return (getattr(item, "type", None), self.icon_size, initial)

    def _mark_icon_cache_changed(self):
        self._icon_cache_revision = int(getattr(self, "_icon_cache_revision", 0) or 0) + 1
        # Clear page pixmap cache so it re-renders with updated icons
        cache = getattr(self, "_page_pixmap_cache", None)
        if cache is not None:
            cache.clear()

    def _get_icon_miss_cache(self):
        cache = getattr(self, "_icon_miss_cache", None)
        if cache is None:
            cache = set()
            self._icon_miss_cache = cache
        return cache

    def _remember_icon_miss(self, cache_key):
        cache = self._get_icon_miss_cache()
        cache.add(cache_key)
        while len(cache) > 200:
            cache.pop()

    def _get_icon_source_size(self) -> int:
        cached = getattr(self, "_cached_icon_source_size", None)
        if cached is None:
            self._cached_icon_source_size = max(48, self.icon_size * 2)
        return self._cached_icon_source_size

    def _get_cached_icon_for_animation(self, item: ShortcutItem, need_invert: bool = False):
        source_size = self._get_icon_source_size()
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)

        # Resolve folder icon path to match _get_icon behavior,
        # otherwise the cache key won't match and folder icons
        # fall back to colored rectangles during page animation.
        if not icon_path:
            item_type = getattr(item, "type", None)
            is_folder_type = item_type == ShortcutType.FOLDER
            if item_type == ShortcutType.FILE and target_path and os.path.isdir(target_path):
                is_folder_type = True
            if is_folder_type:
                possible_paths = [
                    os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico"),
                    os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "assets",
                        "Folder.ico",
                    ),
                ]
                if hasattr(sys, "_MEIPASS"):
                    possible_paths.insert(0, os.path.join(sys._MEIPASS, "assets", "Folder.ico"))
                for path in possible_paths:
                    if os.path.exists(path):
                        icon_path = path
                        target_path = None
                        break

        if icon_path:
            cache_key = ("from_file", icon_path, self.icon_size, source_size, need_invert)
            cached = self._icon_pixmap_cache.get(cache_key)
            if cached is not None:
                self._icon_pixmap_cache.move_to_end(cache_key)
                return cached

        if target_path and HAS_ICON_EXTRACTOR and IconExtractor:
            try:
                cache_id = IconExtractor.get_target_cache_id(target_path, target_path, source_size)
                cache_key = ("extract", cache_id, self.icon_size, source_size, need_invert)
                cached = self._icon_pixmap_cache.get(cache_key)
                if cached is not None:
                    self._icon_pixmap_cache.move_to_end(cache_key)
                    return cached
            except Exception as exc:
                logger.debug("从缓存获取图标失败: %s", exc, exc_info=True)

        return None

    def _animation_icon_ready(self, item: ShortcutItem, need_invert: bool | None = None) -> bool:
        """Return whether animation can render this item without a placeholder icon."""
        if need_invert is None:
            need_invert = False
            try:
                if _should_invert_icon is not None:
                    current_theme = getattr(self.settings, "theme", "dark") if hasattr(self, "settings") else "dark"
                    need_invert = _should_invert_icon(item, current_theme)
            except Exception:
                need_invert = False
        if self._get_cached_icon_for_animation(item, need_invert) is not None:
            return True

        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        item_type = getattr(item, "type", None)
        if icon_path:
            return False
        if target_path:
            return False
        if item_type == ShortcutType.FOLDER:
            return False
        if item_type == ShortcutType.FILE and target_path:
            return False
        return True

    def _get_icon(self, item: ShortcutItem) -> QPixmap:
        """Get icon pixmap for a shortcut item."""
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        item_type = getattr(item, "type", None)

        need_invert = False
        try:
            if _should_invert_icon is not None:
                current_theme = getattr(self.settings, "theme", "dark") if hasattr(self, "settings") else "dark"
                need_invert = _should_invert_icon(item, current_theme)
        except Exception as exc:
            logger.debug("检查图标反转失败: %s", exc, exc_info=True)

        if getattr(self, "_suspend_icon_extraction", False):
            cached = self._get_cached_icon_for_animation(item, need_invert)
            if cached is not None:
                return cached
            default_key = self._default_icon_cache_key(item)
            cached_default = self._default_icon_cache.get(default_key)
            if cached_default is not None:
                return cached_default
            pixmap = self._create_default_icon(item)
            self._default_icon_cache[default_key] = pixmap
            return pixmap

        is_folder_type = item_type == ShortcutType.FOLDER
        if item_type == ShortcutType.FILE and target_path and os.path.isdir(target_path):
            is_folder_type = True

        if not icon_path and is_folder_type:
            possible_paths = [
                os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico"),
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "assets",
                    "Folder.ico",
                ),
            ]
            if hasattr(sys, "_MEIPASS"):
                possible_paths.insert(0, os.path.join(sys._MEIPASS, "assets", "Folder.ico"))
            for path in possible_paths:
                if os.path.exists(path):
                    icon_path = path
                    target_path = None
                    break

        if HAS_ICON_EXTRACTOR and IconExtractor:
            try:
                source_size = self._get_icon_source_size()
                should_load = False
                if icon_path:
                    if "," in icon_path:
                        should_load = True
                    elif os.path.exists(icon_path):
                        should_load = True

                if should_load:
                    logger.debug(
                        "[IconDiag] popup custom probe name=%r icon_path=%r target_path=%r size=%s invert=%s",
                        getattr(item, "name", ""),
                        icon_path,
                        target_path,
                        self.icon_size,
                        source_size,
                        need_invert,
                    )
                    cache_key = ("from_file", icon_path, self.icon_size, source_size, need_invert)
                    cached = self._icon_pixmap_cache.get(cache_key)
                    if cached is not None:
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        return cached

                    if cache_key not in self._get_icon_miss_cache():
                        pixmap = IconExtractor.from_file(icon_path, source_size, return_image=False)
                        if pixmap and not pixmap.isNull():
                            if need_invert:
                                pixmap = IconExtractor.invert_pixmap(pixmap)
                            if pixmap.width() != self.icon_size or pixmap.height() != self.icon_size:
                                pixmap = pixmap.scaled(
                                    self.icon_size,
                                    self.icon_size,
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation,
                                )
                            self._icon_pixmap_cache[cache_key] = pixmap
                            self._mark_icon_cache_changed()
                            self._icon_pixmap_cache.move_to_end(cache_key)
                            while len(self._icon_pixmap_cache) > 200:
                                self._icon_pixmap_cache.popitem(last=False)
                            return pixmap

                        self._remember_icon_miss(cache_key)
                        logger.debug(
                            "[IconDiag] popup custom icon failed name=%r icon_path=%r target_path=%r size=%s",
                            getattr(item, "name", ""),
                            icon_path,
                            target_path,
                            self.icon_size,
                        )

                if target_path:
                    logger.debug(
                        "[IconDiag] popup target probe name=%r icon_path=%r target_path=%r size=%s invert=%s",
                        getattr(item, "name", ""),
                        icon_path,
                        target_path,
                        self.icon_size,
                        source_size,
                        need_invert,
                    )
                    cache_id = IconExtractor.get_target_cache_id(target_path, target_path, source_size)
                    cache_key = ("extract", cache_id, self.icon_size, source_size, need_invert)
                    cached = self._icon_pixmap_cache.get(cache_key)
                    if cached is not None:
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        return cached

                    if cache_key not in self._get_icon_miss_cache():
                        pixmap = IconExtractor.extract(
                            target_path,
                            target_path,
                            source_size,
                            return_image=False,
                            fallback_to_default=False,
                        )
                        if pixmap and not pixmap.isNull():
                            if need_invert:
                                pixmap = IconExtractor.invert_pixmap(pixmap)
                            if pixmap.width() != self.icon_size or pixmap.height() != self.icon_size:
                                pixmap = pixmap.scaled(
                                    self.icon_size,
                                    self.icon_size,
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation,
                                )
                            self._icon_pixmap_cache[cache_key] = pixmap
                            self._mark_icon_cache_changed()
                            self._icon_pixmap_cache.move_to_end(cache_key)
                            while len(self._icon_pixmap_cache) > 200:
                                self._icon_pixmap_cache.popitem(last=False)
                            return pixmap

                        self._remember_icon_miss(cache_key)
                        logger.debug(
                            "[IconDiag] popup target icon failed name=%r icon_path=%r target_path=%r size=%s cache_id=%s",
                            getattr(item, "name", ""),
                            icon_path,
                            target_path,
                            self.icon_size,
                            cache_id,
                        )
            except Exception as e:
                logger.debug(
                    "[IconDiag] popup icon exception name=%r icon_path=%r target_path=%r size=%s error=%s",
                    getattr(item, "name", ""),
                    icon_path,
                    target_path,
                    self.icon_size,
                    e,
                )

        default_key = self._default_icon_cache_key(item)
        cached_default = self._default_icon_cache.get(default_key)
        if cached_default is not None:
            return cached_default
        pixmap = self._create_default_icon(item)
        self._default_icon_cache[default_key] = pixmap
        return pixmap

    def _create_default_icon(self, item: ShortcutItem) -> QPixmap:
        """Create a simple fallback icon."""
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        color = QColor(135, 206, 250)
        painter.setBrush(QBrush(color))
        painter.setPen(QtCompat.NoPen)

        margin = size // 8
        radius = size // 6
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), radius, radius)

        first_char = item.name[0] if item.name else "?"
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont("Segoe UI")
        # Use unscaled settings value as input to font_px() to avoid double-scaling
        font.setPixelSize(font_px(max(10, int(self.settings.icon_size * 0.4))))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, first_char)

        painter.end()
        return pixmap
