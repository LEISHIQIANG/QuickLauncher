"""Icon cache and fallback icon helpers for LauncherPopup."""

import logging
import os
import sys

from qt_compat import QColor, QBrush, QFont, QPainter, QPainterPath, QPen, QPixmap, QRectF, Qt, QtCompat
from core import ShortcutItem, ShortcutType

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
    def _get_icon(self, item: ShortcutItem) -> QPixmap:
        """获取图标"""
        icon_path = getattr(item, "icon_path", None)
        target_path = getattr(item, "target_path", None)
        item_type = getattr(item, "type", None)

        # 判断是否需要反转
        need_invert = False
        try:
            if _should_invert_icon is not None:
                current_theme = getattr(self.settings, 'theme', 'dark') if hasattr(self, 'settings') else 'dark'
                need_invert = _should_invert_icon(item, current_theme)
        except Exception:
            pass

        is_folder_type = item_type == ShortcutType.FOLDER
        if item_type == ShortcutType.FILE and target_path and os.path.isdir(target_path):
            is_folder_type = True

        if not icon_path and is_folder_type:
            possible_paths = [
                os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'assets', 'Folder.ico'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'assets', 'Folder.ico')
            ]
            if hasattr(sys, '_MEIPASS'):
                possible_paths.insert(0, os.path.join(sys._MEIPASS, 'assets', 'Folder.ico'))
            for p in possible_paths:
                if os.path.exists(p):
                    icon_path = p
                    target_path = None
                    break

        if HAS_ICON_EXTRACTOR and IconExtractor:
            try:
                should_load = False
                if icon_path:
                    if ',' in icon_path:
                        should_load = True
                    elif os.path.exists(icon_path):
                        should_load = True

                if should_load:
                    cache_key = ("from_file", icon_path, self.icon_size, need_invert)
                    cached = self._icon_pixmap_cache.get(cache_key)
                    if cached is not None:
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        return cached

                    pixmap = IconExtractor.from_file(icon_path, self.icon_size)
                    if pixmap and not pixmap.isNull():
                        if need_invert:
                            pixmap = IconExtractor.invert_pixmap(pixmap)
                        self._icon_pixmap_cache[cache_key] = pixmap
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        while len(self._icon_pixmap_cache) > 200:
                            self._icon_pixmap_cache.popitem(last=False)
                        return pixmap

                if target_path:
                    cache_key = ("extract", target_path, self.icon_size, need_invert)
                    cached = self._icon_pixmap_cache.get(cache_key)
                    if cached is not None:
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        return cached

                    pixmap = IconExtractor.extract(target_path, target_path, self.icon_size)
                    if pixmap and not pixmap.isNull():
                        if need_invert:
                            pixmap = IconExtractor.invert_pixmap(pixmap)
                        self._icon_pixmap_cache[cache_key] = pixmap
                        self._icon_pixmap_cache.move_to_end(cache_key)
                        while len(self._icon_pixmap_cache) > 200:
                            self._icon_pixmap_cache.popitem(last=False)
                        return pixmap
            except Exception as e:
                logger.debug(f"提取图标失败: {e}")

        default_key = (item.type, self.icon_size)
        cached_default = self._default_icon_cache.get(default_key)
        if cached_default is not None:
            return cached_default
        pixmap = self._create_default_icon(item)
        self._default_icon_cache[default_key] = pixmap
        return pixmap
    def _create_default_icon(self, item: ShortcutItem) -> QPixmap:
        """创建默认图标"""
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        
        if item.type == ShortcutType.HOTKEY:
            color = QColor(70, 130, 180)
        else:
            color = QColor(100, 130, 180)
        
        painter.setBrush(QBrush(color))
        painter.setPen(QtCompat.NoPen)
        
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 4, 4)
        
        if item.type == ShortcutType.HOTKEY:
            painter.setPen(QPen(QColor(255, 255, 255)))
            font = QFont("Segoe UI", size // 4)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌨")
        
        painter.end()
        return pixmap
