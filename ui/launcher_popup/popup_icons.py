"""Icon cache and fallback icon helpers for LauncherPopup."""

import logging
import os

from core import ShortcutItem, ShortcutType
from core.command_icon_catalog import builtin_command_id_from_icon_path
from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon
from qt_compat import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRectF, Qt, QtCompat
from ui.command_icon_renderer import render_builtin_command_icon_path
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
    _MIN_ICON_PIXMAP_CACHE_CAPACITY = 200

    def _icon_pixmap_cache_capacity(self) -> int:
        return max(
            self._MIN_ICON_PIXMAP_CACHE_CAPACITY,
            int(self.__dict__.get("_icon_pixmap_cache_capacity_value", 0) or 0),
        )

    def _reserve_icon_pixmap_cache(self, item_count: int) -> int:
        """Reserve enough LRU entries for file keys plus target-path aliases."""
        required = max(self._MIN_ICON_PIXMAP_CACHE_CAPACITY, max(0, int(item_count)) * 2 + 32)
        self._icon_pixmap_cache_capacity_value = required
        return required

    def _trim_icon_pixmap_cache(self, cache=None) -> None:
        cache = self._icon_pixmap_cache if cache is None else cache
        limit = self._icon_pixmap_cache_capacity()
        while len(cache) > limit:
            try:
                cache.popitem(last=False)
            except TypeError:
                cache.pop(next(iter(cache)))
            except Exception:
                break

    def _default_icon_cache_key(self, item: ShortcutItem):
        name = getattr(item, "name", "") or "?"
        initial = name[0] if name else "?"
        return (getattr(item, "type", None), self.icon_size, initial)

    def _mark_icon_cache_changed(self):
        if self.__dict__.get("_batch_icon_preload_active", False):
            self._icon_cache_batch_changed = True
            return
        self._icon_cache_revision = int(getattr(self, "_icon_cache_revision", 0) or 0) + 1
        # Clear page pixmap cache so it re-renders with updated icons
        cache = getattr(self, "_page_pixmap_cache", None)
        if cache is not None:
            cache.clear()
        try:
            self.update()
        except Exception as exc:
            logger.debug("刷新图标缓存绘制失败: %s", exc, exc_info=True)

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
        key = int(getattr(self, "icon_size", 0) or 0)
        cached = getattr(self, "_cached_icon_source_size", None)
        if cached is None or cached[0] != key:
            cached = (key, max(48, key * 2))
            self._cached_icon_source_size = cached
        return cached[1]

    def _folder_icon_path(self) -> str | None:
        cached = self.__dict__.get("_cached_folder_icon_path")
        if cached and os.path.exists(cached):
            return cached

        self._cached_folder_icon_path = default_folder_icon_path()
        return self._cached_folder_icon_path

    def _get_cached_icon_for_animation(self, item: ShortcutItem, need_invert: bool = False):
        source_size = self._get_icon_source_size()
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        command_id = builtin_command_id_from_icon_path(icon_path)
        if command_id:
            theme = getattr(self.settings, "theme", "dark")
            cache_key = ("builtin-command", command_id, self.icon_size, theme)
            cached = self._icon_pixmap_cache.get(cache_key)
            if cached is not None:
                self._icon_pixmap_cache.move_to_end(cache_key)
            return cached

        # Resolve folder icon path to match _get_icon behavior,
        # otherwise the cache key won't match and folder icons
        # fall back to colored rectangles during page animation.
        if not icon_path:
            item_type = getattr(item, "type", None)
            if shortcut_uses_folder_icon(item_type, target_path):
                folder_icon_path = self._folder_icon_path()
                if folder_icon_path:
                    icon_path = folder_icon_path
                    target_path = None

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
            need_invert = self._icon_should_invert(item)
        if self._get_cached_icon_for_animation(item, need_invert) is not None:
            return True

        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        item_type = getattr(item, "type", None)
        if builtin_command_id_from_icon_path(icon_path):
            return True
        if icon_path:
            return False
        if target_path:
            return False
        if item_type == ShortcutType.FOLDER:
            return False
        if item_type == ShortcutType.FILE and target_path:
            return False
        return True

    def _icon_should_invert(self, item: ShortcutItem) -> bool:
        try:
            if _should_invert_icon is not None:
                current_theme = getattr(self.settings, "theme", "dark") if hasattr(self, "settings") else "dark"
                return bool(_should_invert_icon(item, current_theme))
        except Exception as exc:
            logger.debug("检查图标反转失败: %s", exc, exc_info=True)
        return False

    def _get_default_icon_cached(self, item: ShortcutItem) -> QPixmap:
        default_cache = getattr(self, "_default_icon_cache", None)
        if default_cache is None:
            default_cache = {}
            self._default_icon_cache = default_cache
        default_key = self._default_icon_cache_key(item)
        cached_default = default_cache.get(default_key)
        if cached_default is not None:
            return cached_default
        pixmap = self._create_default_icon(item)
        default_cache[default_key] = pixmap
        return pixmap

    def _get_icon_for_paint(self, item: ShortcutItem) -> QPixmap:
        """Get an icon for paint paths without touching shell/file-system extraction."""
        need_invert = self._icon_should_invert(item)
        source_size = self._get_icon_source_size()
        icon_cache = getattr(self, "_icon_pixmap_cache", None)
        if icon_cache is None:
            icon_cache = {}
            self._icon_pixmap_cache = icon_cache
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        folder_icon_path = None
        command_id = builtin_command_id_from_icon_path(icon_path)
        if command_id:
            theme = getattr(self.settings, "theme", "dark")
            cache_key = ("builtin-command", command_id, self.icon_size, theme)
            cached = icon_cache.get(cache_key)
            if cached is None:
                cached = render_builtin_command_icon_path(icon_path, self.icon_size, theme)
                if cached is not None:
                    icon_cache[cache_key] = cached
                    self._trim_icon_pixmap_cache(icon_cache)
            return cached or self._get_default_icon_cached(item)

        if not icon_path and shortcut_uses_folder_icon(
            getattr(item, "type", None),
            target_path,
            resolve_lnk=False,
        ):
            folder_icon_path = self._folder_icon_path()
            icon_path = folder_icon_path
            if icon_path:
                target_path = None

        if icon_cache is not None and icon_path:
            cache_key = ("from_file", icon_path, self.icon_size, source_size, need_invert)
            cached = icon_cache.get(cache_key)
            if cached is not None:
                move_to_end = getattr(icon_cache, "move_to_end", None)
                if callable(move_to_end):
                    move_to_end(cache_key)
                return cached
            if folder_icon_path:
                pixmap = QPixmap(folder_icon_path)
                if pixmap and not pixmap.isNull():
                    if need_invert and HAS_ICON_EXTRACTOR and IconExtractor:
                        pixmap = IconExtractor.invert_pixmap(pixmap)
                    if pixmap.width() != self.icon_size or pixmap.height() != self.icon_size:
                        pixmap = pixmap.scaled(
                            self.icon_size,
                            self.icon_size,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    icon_cache[cache_key] = pixmap
                    move_to_end = getattr(icon_cache, "move_to_end", None)
                    if callable(move_to_end):
                        move_to_end(cache_key)
                    self._trim_icon_pixmap_cache(icon_cache)
                    return pixmap

        if icon_cache is not None and target_path:
            alias_key = ("target_path", str(target_path), self.icon_size, source_size, need_invert)
            cached = icon_cache.get(alias_key)
            if cached is not None:
                move_to_end = getattr(icon_cache, "move_to_end", None)
                if callable(move_to_end):
                    move_to_end(alias_key)
                return cached

        return self._get_default_icon_cached(item)

    def _get_icon(self, item: ShortcutItem) -> QPixmap:
        """Get icon pixmap for a shortcut item."""
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        item_type = getattr(item, "type", None)
        command_id = builtin_command_id_from_icon_path(icon_path)
        if command_id:
            return self._get_icon_for_paint(item)

        need_invert = self._icon_should_invert(item)

        if getattr(self, "_suspend_icon_extraction", False):
            return self._get_icon_for_paint(item)

        if not icon_path and shortcut_uses_folder_icon(item_type, target_path):
            folder_icon_path = self._folder_icon_path()
            if folder_icon_path:
                icon_path = folder_icon_path
                target_path = None

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
                            self._trim_icon_pixmap_cache()
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
                    alias_key = ("target_path", str(target_path), self.icon_size, source_size, need_invert)
                    if cached is not None:
                        self._icon_pixmap_cache[alias_key] = cached
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        self._icon_pixmap_cache.move_to_end(alias_key)
                        self._trim_icon_pixmap_cache()
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
                            self._icon_pixmap_cache[alias_key] = pixmap
                            self._mark_icon_cache_changed()
                            self._icon_pixmap_cache.move_to_end(cache_key)
                            self._icon_pixmap_cache.move_to_end(alias_key)
                            self._trim_icon_pixmap_cache()
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

        return self._get_default_icon_cached(item)

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
