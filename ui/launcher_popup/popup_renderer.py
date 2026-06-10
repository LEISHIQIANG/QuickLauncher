"""Painting helpers for LauncherPopup."""

import logging
import math
import os
import time

from qt_compat import (
    QApplication,
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRect,
    QRectF,
    QtCompat,
)
from ui.utils.ui_scale import font_px, sp
from ui.utils.window_effect import is_win10

logger = logging.getLogger(__name__)


class PopupRendererMixin:
    def _get_theme_colors(self):
        theme = self.settings.theme
        cache = getattr(self, "_theme_colors_cache", None)
        if cache is not None and cache[0] == theme:
            return cache[1]
        if theme == "dark":
            colors = (
                QColor(28, 28, 30),  # theme_bg
                QColor(255, 255, 255, 230),  # text_color
                QColor(255, 255, 255, 50),  # hover_color
                QColor(255, 255, 255, 40),  # border_color
                QColor(10, 132, 255),  # accent_color
                QColor(255, 255, 255, 18),  # dock_bg
                QColor(10, 132, 255),  # drop_highlight_color
            )
        else:
            colors = (
                QColor(242, 242, 247),
                QColor(28, 28, 30, 230),
                QColor(255, 255, 255, 160),
                QColor(0, 0, 0, 20),
                QColor(0, 122, 255),
                QColor(255, 255, 255, 12),
                QColor(0, 122, 255),
            )
        self._theme_colors_cache = (theme, colors)
        return colors

    def paintEvent(self, event):
        """绘制"""
        painter = QPainter(self)
        try:
            painter.setClipRegion(event.region())
        except Exception as exc:
            logger.debug("设置绘制裁剪区域失败: %s", exc, exc_info=True)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QtCompat.TextAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        dirty_rect = event.rect()

        theme_bg, text_color, hover_color, border_color, accent_color, dock_bg, drop_highlight_color = (
            self._get_theme_colors()
        )

        # 确定背景颜色和模式
        bg_mode = getattr(self.settings, "bg_mode", "theme")
        blur_radius = getattr(self.settings, "bg_blur_radius", 0)

        # 统一计算绘制区域 (用于背景路径和后续高光计算)
        margin = getattr(self, "shadow_margin", 0)
        top_inset = self._background_top_inset() if hasattr(self, "_background_top_inset") else 0
        rect = QRectF(self.rect()).adjusted(margin, margin + top_inset, -margin, -margin)
        radius = self._get_paint_corner_radius(bg_mode, blur_radius)

        # 使用缓存的路径，避免重复计算
        path_cache_key = (self.width(), self.height(), int(top_inset), float(radius))
        if (
            self._cached_bg_path is None
            or self._cached_bg_path.isEmpty()
            or getattr(self, "_cached_bg_path_key", None) != path_cache_key
        ):
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            self._cached_bg_path = path
            self._cached_bg_path_key = path_cache_key
            # Invalidate derived path caches
            self._cached_outside_path = None
            self._cached_border_path = None
        else:
            path = self._cached_bg_path

        # Cache border path (1px inset)
        if getattr(self, "_cached_border_path", None) is None:
            inset = 0.5
            r = max(0.0, float(radius) - inset)
            self._cached_border_path = QPainterPath()
            self._cached_border_path.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset), r, r)

        def make_border_path(pen_width_f: float) -> QPainterPath:
            if pen_width_f == 1.0:
                return self._cached_border_path
            inset = max(0.5, float(pen_width_f) / 2.0)
            r = max(0.0, float(radius) - inset)
            p = QPainterPath()
            p.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset), r, r)
            return p

        # Cache CompositionMode_Clear lookup (constant per process)
        if not hasattr(PopupRendererMixin, "_clear_composition_mode"):
            mode = getattr(QPainter, "CompositionMode_Clear", None)
            if mode is None:
                enum = getattr(QPainter, "CompositionMode", None)
                mode = getattr(enum, "Clear", None) or getattr(enum, "CompositionMode_Clear", None) if enum else None
            PopupRendererMixin._clear_composition_mode = mode

        if is_win10() and radius > 0:
            painter.save()
            source_mode = getattr(QPainter, "CompositionMode_Source", None)
            source_over_mode = getattr(QPainter, "CompositionMode_SourceOver", None)
            enum = getattr(QPainter, "CompositionMode", None)
            if enum is not None:
                source_mode = getattr(enum, "Source", source_mode)
                source_over_mode = getattr(enum, "SourceOver", source_over_mode)
            if source_mode is not None:
                painter.setCompositionMode(source_mode)
            painter.fillRect(self.rect(), QtCompat.transparent)
            if source_over_mode is not None:
                painter.setCompositionMode(source_over_mode)
            painter.restore()
        elif radius > 0:
            # Cache outside path (full rect minus rounded rect)
            if getattr(self, "_cached_outside_path", None) is None:
                full = QPainterPath()
                full.addRect(QRectF(self.rect()))
                self._cached_outside_path = full.subtracted(path)
            painter.save()
            clear_mode = PopupRendererMixin._clear_composition_mode
            if clear_mode is not None:
                painter.setCompositionMode(clear_mode)
            painter.fillPath(self._cached_outside_path, QtCompat.transparent)
            painter.restore()
        # 绘制背景
        if bg_mode == "image" and self.settings.custom_bg_path and os.path.exists(self.settings.custom_bg_path):
            # 图片模式
            bg_pixmap = self._get_cached_bg_pixmap()
            if bg_pixmap:
                painter.save()
                # 图片模式下的透明度 (0=透明, 100=不透明)
                paint_alpha = self.settings.bg_alpha / 100.0
                # Win10 图片模式允许完整的透明度控制
                painter.setOpacity(max(0.0, min(1.0, paint_alpha)))
                # 绘制到 path 区域
                # 需要设置 Clip Path，因为图片本身可能比内容区域大 (或者我们调整绘制位置)
                painter.setClipPath(path)

                # 计算图片绘制位置 (居中于 path)
                target_rect = path.boundingRect()
                pix_x = target_rect.x() + (target_rect.width() - bg_pixmap.width()) / 2
                pix_y = target_rect.y() + (target_rect.height() - bg_pixmap.height()) / 2

                painter.drawPixmap(int(pix_x), int(pix_y), bg_pixmap)
                painter.restore()
            else:
                # 回退
                c = QColor(theme_bg)
                c.setAlpha(int(255 * (self.settings.bg_alpha / 100.0)))
                painter.fillPath(path, QBrush(c))

        elif bg_mode == "acrylic":
            # ===== 亚克力模式：与配置窗口 RoundedWindow 相同的绘制方式 =====
            # bg_alpha 0-100: 0=最透明/最强磨砂, 100=最不透明/实色
            user_alpha = getattr(self.settings, "bg_alpha", 90)

            tint_color = QColor(theme_bg)
            if is_win10():
                # Win10 不启用原生毛玻璃；用近似不透明底色保证圆角边缘干净。
                paint_alpha = max(248, min(255, int(user_alpha * 2.55)))
            else:
                # Win11: paintEvent tint alpha 范围 0~200 (DWM 已提供主要磨砂效果，Qt层做补充)
                paint_alpha = max(0, min(200, int(user_alpha * 2.0)))
            tint_color.setAlpha(paint_alpha)
            painter.fillPath(path, tint_color)

            # 绘制 1px 半透明边框
            if self.settings.theme == "dark":
                border_c = QColor(85, 85, 85, 120)
            else:
                border_c = QColor(200, 200, 200, 120)
            pen = QPen(border_c, 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(path)

        else:  # theme mode
            c = QColor(theme_bg)
            # 计算透明度 (0=透明/0, 100=不透明/255)
            alpha_val = int(255 * (self.settings.bg_alpha / 100.0))
            if is_win10():
                alpha_val = max(248, alpha_val)
            c.setAlpha(max(0, min(255, alpha_val)))
            painter.fillPath(path, QBrush(c))

        # 绘制边缘高光 / 边框（亚克力模式已在上方绘制完毕，这里只处理 theme 和 image 模式）
        if bg_mode != "acrylic":
            edge_opacity = getattr(self.settings, "edge_highlight_opacity", 0.0)

            if edge_opacity > 0:
                # 用户自定义高光 (模拟玻璃质感)
                edge_color_str = getattr(self.settings, "edge_highlight_color", "#ffffff")
                try:
                    edge_c = QColor(edge_color_str)
                except Exception as e:
                    logger.debug("Invalid edge highlight color %r: %s", edge_color_str, e)
                    edge_c = QColor(255, 255, 255)

                edge_c.setAlphaF(edge_opacity)
                pen = QPen(edge_c, 1.0)
                pen.setJoinStyle(QtCompat.RoundJoin)
                pen.setCapStyle(QtCompat.RoundCap)
                painter.setPen(pen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPath(make_border_path(1.0))
            else:
                # 默认普通边框
                pen = QPen(border_color, 1)
                pen.setJoinStyle(QtCompat.RoundJoin)
                pen.setCapStyle(QtCompat.RoundCap)
                painter.setPen(pen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPath(make_border_path(1.0))

        # 绘制内容。滚轮翻页动画只刷新主体和指示器区域，避免每帧重画 Dock 图标。
        search_visible = bool(
            getattr(self, "search_query", "")
            or getattr(self, "_search_forced_active", False)
            or getattr(self, "_search_reveal_progress", 0.0) > 0.001
            or getattr(self, "_search_target_progress", 0.0) > 0.001
        )

        body_bottom = max(
            int(getattr(self, "content_height", self.height()) or self.height()),
            int(getattr(self, "indicator_y", 0) or 0) + sp(16),
        )
        body_rect = QRect(0, 0, self.width(), min(self.height(), max(1, body_bottom)))
        content_dirty = dirty_rect.intersects(body_rect)

        if content_dirty:
            if search_visible:
                self._draw_search_bar(painter, text_color, accent_color)
            if getattr(self, "search_query", ""):
                self._draw_search_results(painter, text_color, hover_color, drop_highlight_color, bg_mode)
            elif not search_visible or getattr(self, "_search_reveal_progress", 0.0) >= 0.999:
                self._draw_icons(painter, text_color, hover_color, drop_highlight_color, bg_mode)
            else:
                # During search reveal animation, still draw icons underneath
                self._draw_icons(painter, text_color, hover_color, drop_highlight_color, bg_mode)

        indicator_rect = QRect(0, max(0, int(getattr(self, "indicator_y", 0) or 0) - sp(6)), self.width(), sp(24))
        if len(self.pages) > 1 and dirty_rect.intersects(indicator_rect):
            self._draw_indicator(painter, text_color, self._indicator_accent_color(accent_color))

        dock_rect = QRect(
            0,
            max(0, int(getattr(self, "dock_y", self.height()) or self.height()) - sp(8)),
            self.width(),
            max(0, int(getattr(self, "dock_height", 0) or 0) + sp(16)),
        )
        if self.dock_items and dirty_rect.intersects(dock_rect):
            self._draw_dock(painter, text_color, hover_color, dock_bg, drop_highlight_color, bg_mode, border_color)

        pin_y_offset = self._body_y_offset() if hasattr(self, "_body_y_offset") else 0
        pinned_rect = QRect(max(0, self.width() - sp(18)), pin_y_offset, sp(18), sp(18))
        if self.is_pinned and dirty_rect.intersects(pinned_rect):
            painter.setBrush(QBrush(accent_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawEllipse(self.width() - sp(14), pin_y_offset + sp(6), sp(8), sp(8))

    def _draw_icons(
        self,
        painter: QPainter,
        text_color: QColor,
        hover_color: QColor,
        drop_highlight_color: QColor,
        bg_mode: str = "theme",
    ):
        """绘制图标网格"""
        if not self.pages or self.current_page >= len(self.pages):
            return

        painter.setFont(self._label_font)

        page_pos = float(getattr(self, "_page_position", getattr(self, "_page_offset", float(self.current_page))))
        self._page_offset = page_pos
        y_offset = self._body_y_offset() if hasattr(self, "_body_y_offset") else 0
        page_base = math.floor(page_pos)
        page_fraction = page_pos - page_base
        w = self.width()

        if page_fraction > 0.001 and len(self.pages) > 1:
            first_index = page_base % len(self.pages)
            second_index = (page_base + 1) % len(self.pages)
            first_pixmap = self._get_page_animation_pixmap(
                first_index, text_color, hover_color, drop_highlight_color, bg_mode
            )
            second_pixmap = self._get_page_animation_pixmap(
                second_index, text_color, hover_color, drop_highlight_color, bg_mode
            )
            if first_pixmap is not None and second_pixmap is not None:
                offset1 = int(w * page_fraction)
                visible1 = w - offset1
                if visible1 > 0:
                    painter.save()
                    painter.setClipRect(0, y_offset, visible1, self.content_height)
                    painter.drawPixmap(-offset1, y_offset, first_pixmap)
                    painter.restore()
                offset2 = int(w * (1.0 - page_fraction))
                visible2 = w - offset2
                if visible2 > 0:
                    painter.save()
                    painter.setClipRect(offset2, y_offset, visible2, self.content_height)
                    painter.drawPixmap(offset2, y_offset, second_pixmap)
                    painter.restore()
            else:
                painter.save()
                painter.translate(int(-w * page_fraction), 0)
                self._draw_page_items(
                    painter,
                    first_index,
                    text_color,
                    hover_color,
                    drop_highlight_color,
                    bg_mode,
                    is_prev=True,
                    y_offset=y_offset,
                )
                painter.restore()

                painter.save()
                painter.translate(int(w * (1.0 - page_fraction)), 0)
                self._draw_page_items(
                    painter,
                    second_index,
                    text_color,
                    hover_color,
                    drop_highlight_color,
                    bg_mode,
                    is_prev=False,
                    y_offset=y_offset,
                )
                painter.restore()
            return

        display_page = round(page_pos) % len(self.pages)
        self._draw_page_items(
            painter,
            display_page,
            text_color,
            hover_color,
            drop_highlight_color,
            bg_mode,
            is_prev=False,
            y_offset=y_offset,
        )

    def _get_page_animation_pixmap(
        self, page_index: int, text_color: QColor, hover_color: QColor, drop_highlight_color: QColor, bg_mode: str
    ):
        if not self.pages:
            return None
        page_index = page_index % len(self.pages)
        items = self._get_page_animation_items(page_index)
        if not self._page_animation_icons_ready(items):
            return None
        key = (
            page_index,
            getattr(self, "_model_revision", 0),
            self.width(),
            self.content_height,
            self.icon_size,
            self.cell_size,
            self._page_animation_screen_key(),
            getattr(self.settings, "theme", "dark"),
            bg_mode,
            getattr(self.settings, "sort_mode", "custom"),
        )
        cache = getattr(self, "_page_pixmap_cache", None)
        if cache is None:
            cache = {}
            self._page_pixmap_cache = cache
        cached = cache.get(key)
        if cached is not None and not cached.isNull():
            return cached

        image = self._create_page_animation_image()
        page_painter = QPainter(image)
        page_painter.setRenderHint(QtCompat.Antialiasing)
        page_painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        page_painter.setRenderHint(QtCompat.TextAntialiasing)
        page_painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        old_suspend = getattr(self, "_suspend_icon_extraction", False)
        old_reveal = getattr(self, "_reveal_progress", 1.0)
        self._suspend_icon_extraction = True
        self._reveal_progress = 1.0
        try:
            self._draw_page_items(
                page_painter,
                page_index,
                text_color,
                hover_color,
                drop_highlight_color,
                bg_mode,
                is_prev=True,
                y_offset=0,
            )
        finally:
            self._suspend_icon_extraction = old_suspend
            self._reveal_progress = old_reveal
            page_painter.end()

        pixmap = QPixmap.fromImage(image)
        cache[key] = pixmap
        while len(cache) > 24:
            try:
                cache.pop(next(iter(cache)))
            except Exception:
                break
        return pixmap

    def _page_animation_screen_info(self):
        screen = None
        try:
            handle = self.windowHandle()
            if handle is not None:
                screen = handle.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = self.screen()
            except Exception:
                screen = None
        if screen is None:
            try:
                screen = QApplication.screenAt(self.geometry().center())
            except Exception:
                screen = None
        if screen is None:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None

        dpr = 1.0
        dpi_x = 96.0
        dpi_y = 96.0
        name = ""
        if screen is not None:
            try:
                dpr = float(screen.devicePixelRatio() or 1.0)
            except Exception:
                dpr = 1.0
            try:
                dpi_x = float(screen.logicalDotsPerInchX() or 96.0)
            except Exception:
                dpi_x = 96.0
            try:
                dpi_y = float(screen.logicalDotsPerInchY() or dpi_x)
            except Exception:
                dpi_y = dpi_x
            try:
                name = screen.name() or ""
            except Exception:
                name = ""
        else:
            try:
                dpr = float(self.devicePixelRatioF() or 1.0)
            except Exception:
                dpr = 1.0

        try:
            widget_dpr = float(self.devicePixelRatioF() or 0.0)
            if widget_dpr > 0:
                dpr = widget_dpr
        except Exception as exc:
            logger.debug("获取设备像素比失败: %s", exc, exc_info=True)
        try:
            widget_dpi_x = float(self.logicalDpiX() or 0.0)
            if widget_dpi_x > 0:
                dpi_x = widget_dpi_x
        except Exception as exc:
            logger.debug("获取逻辑DPI X失败: %s", exc, exc_info=True)
        try:
            widget_dpi_y = float(self.logicalDpiY() or 0.0)
            if widget_dpi_y > 0:
                dpi_y = widget_dpi_y
        except Exception as exc:
            logger.debug("获取逻辑DPI Y失败: %s", exc, exc_info=True)

        dpr = max(1.0, dpr)
        dpi_x = dpi_x if dpi_x > 0 else 96.0
        dpi_y = dpi_y if dpi_y > 0 else dpi_x
        return name, dpr, dpi_x, dpi_y

    def _page_animation_screen_key(self):
        name, dpr, dpi_x, dpi_y = self._page_animation_screen_info()
        return (name, round(dpr, 3), round(dpi_x, 2), round(dpi_y, 2))

    def _create_page_animation_image(self) -> QImage:
        _, dpr, dpi_x, dpi_y = self._page_animation_screen_info()
        logical_w = max(1, int(self.width()))
        logical_h = max(1, int(self.content_height))
        image = QImage(
            max(1, int(math.ceil(logical_w * dpr))),
            max(1, int(math.ceil(logical_h * dpr))),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(dpr)
        image.setDotsPerMeterX(max(1, int(dpi_x / 0.0254)))
        image.setDotsPerMeterY(max(1, int(dpi_y / 0.0254)))
        image.fill(0)
        return image

    def _get_page_animation_items(self, page_index: int):
        try:
            get_page_render_items = getattr(self, "_get_page_render_items", None)
        except RuntimeError:
            get_page_render_items = None
        if get_page_render_items is not None:
            return get_page_render_items(page_index)
        return self.pages[page_index].items

    def _page_animation_icons_ready(self, items) -> bool:
        if not hasattr(self, "_animation_icon_ready"):
            return True
        for entry in items:
            item = entry.get("item") if isinstance(entry, dict) else entry
            if item is None:
                continue
            if not self._animation_icon_ready(item):
                return False
        return True

    def _draw_search_bar(self, painter: QPainter, text_color: QColor, accent_color: QColor):
        query = getattr(self, "search_query", "")
        full_h = self._search_bar_full_height() if hasattr(self, "_search_bar_full_height") else 34
        clip_top = self._search_visible_top_inset() if hasattr(self, "_search_visible_top_inset") else 0
        clip_h = max(0, full_h - int(clip_top))
        if clip_h <= 0:
            return
        # Compute opacity from reveal progress for smooth fade
        progress = max(0.0, min(1.0, float(getattr(self, "_search_reveal_progress", 1.0))))
        x = self.padding
        w = self.width() - self.padding * 2
        rect_h = max(sp(6), full_h - sp(8))
        rect_y = sp(4)
        rect = QRectF(x, rect_y, w, rect_h)
        bg = QColor(255, 255, 255, 34 if self.settings.theme == "dark" else 150)
        painter.save()
        painter.setClipRect(0, clip_top, self.width(), clip_h)
        painter.setOpacity(progress)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(accent_color, 1))
        painter.drawRoundedRect(rect, sp(8), sp(8))
        painter.setPen(text_color)
        font = self._search_font() if hasattr(self, "_search_font") else QFont(self._label_font)
        if font.pixelSize() <= 0:
            font.setPixelSize(font_px(10))
        painter.setFont(font)
        preedit = getattr(self, "_search_preedit_text", "") or ""
        prefix = self._search_text_prefix() if hasattr(self, "_search_text_prefix") else ("搜索: " if query else "搜索")
        cursor = self._get_search_cursor_pos() if hasattr(self, "_get_search_cursor_pos") else len(query)
        label = f"{prefix}{query[:cursor]}{preedit}{query[cursor:]}"
        text_rect = rect.adjusted(sp(9), 0, -sp(9), 0)
        scroll_x = int(getattr(self, "__dict__", {}).get("_search_scroll_x", 0) or 0)
        draw_text_rect = QRectF(text_rect)
        draw_text_rect.moveLeft(text_rect.left() - scroll_x)
        metrics = painter.fontMetrics()

        def text_width(value: str) -> int:
            if hasattr(metrics, "horizontalAdvance"):
                return metrics.horizontalAdvance(value)
            return metrics.width(value)

        selection = self._search_selection_bounds() if hasattr(self, "_search_selection_bounds") else None
        if selection:
            sel_start, sel_end = selection
            sel_x = int(text_rect.left() + text_width(prefix + query[:sel_start]) - scroll_x)
            sel_w = max(1, int(text_width(query[sel_start:sel_end])))
            sel_rect = QRectF(sel_x, text_rect.top() + sp(5), sel_w, max(sp(12), text_rect.height() - sp(10)))
            sel_rect = sel_rect.intersected(text_rect)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 95)))
            if sel_rect.width() > 0:
                painter.drawRoundedRect(sel_rect, sp(3), sp(3))
            painter.setPen(text_color)

        painter.save()
        painter.setClipRect(text_rect)
        painter.drawText(draw_text_rect, QtCompat.AlignVCenter | QtCompat.AlignLeft, label)
        painter.restore()

        if preedit:
            underline_x = int(text_rect.left() + text_width(prefix + query[:cursor]) - scroll_x)
            underline_w = max(1, int(text_width(preedit)))
            underline_y = int(text_rect.center().y() + metrics.ascent() / 2 + sp(2))
            painter.setPen(QPen(accent_color, 1))
            painter.save()
            painter.setClipRect(text_rect)
            painter.drawLine(underline_x, underline_y, underline_x + underline_w, underline_y)
            painter.restore()
            painter.setPen(text_color)

        if (
            self._is_search_active()
            and getattr(self, "_search_cursor_visible", True)
            and hasattr(self, "_search_cursor_rect")
        ):
            cursor_rect = self._search_cursor_rect()
            if text_rect.intersects(QRectF(cursor_rect)):
                painter.fillRect(cursor_rect, accent_color)
        painter.restore()

    def _draw_search_results(
        self, painter: QPainter, text_color: QColor, hover_color: QColor, drop_highlight_color: QColor, bg_mode: str
    ):
        all_results = getattr(self, "search_results", []) or []
        results = all_results
        if not all_results:
            painter.setPen(text_color)
            painter.setFont(self._label_font)
            query = getattr(self, "search_query", "")
            if query.startswith("/"):
                action_hint = "输入命令名称"
            elif " " in query:
                action_hint = "按 Enter 进行网页搜索"
            else:
                action_hint = "无匹配结果"
            y_offset = (
                self._body_y_offset() if hasattr(self, "_body_y_offset") else getattr(self, "search_bar_height", sp(30))
            )
            painter.drawText(
                QRect(0, self.padding + y_offset, self.width(), self.content_height), QtCompat.AlignCenter, action_hint
            )
            return

        max_visible = max(0, int(getattr(self, "cols", 0) or 0) * int(getattr(self, "fixed_rows", 0) or 0))
        visible_results = results[:max_visible] if max_visible else []
        cache_key = tuple(
            (id(result.shortcut), getattr(result.shortcut, "name", "") or "") for result in visible_results
        )
        cached_items = getattr(self, "_search_draw_items_cache", None)
        if cached_items is not None and cached_items[0] == cache_key:
            items = cached_items[1]
        else:
            items = [
                {"item": result.shortcut, "text": (getattr(result.shortcut, "name", "") or "")[:6]}
                for result in visible_results
            ]
            self._search_draw_items_cache = (cache_key, items)

        selected_index = getattr(self, "search_selected_index", -1)
        selected = selected_index if 0 <= selected_index < len(visible_results) else -1
        self._draw_items_grid(
            painter,
            items,
            text_color,
            hover_color,
            drop_highlight_color,
            bg_mode,
            y_offset=(
                self._body_y_offset() if hasattr(self, "_body_y_offset") else getattr(self, "search_bar_height", sp(30))
            ),
            selected_index=selected,
        )

    def _draw_page_items(
        self,
        painter: QPainter,
        page_index: int,
        text_color: QColor,
        hover_color: QColor,
        drop_highlight_color: QColor,
        bg_mode: str,
        is_prev: bool,
        y_offset: int = 0,
    ):
        """绘制指定页的图标"""
        if hasattr(self, "_get_page_render_items"):
            items = self._get_page_render_items(page_index)
        else:
            items = self.pages[page_index].items
        self._draw_items_grid(
            painter, items, text_color, hover_color, drop_highlight_color, bg_mode, is_prev=is_prev, y_offset=y_offset
        )

    def _draw_items_grid(
        self,
        painter: QPainter,
        items,
        text_color: QColor,
        hover_color: QColor,
        drop_highlight_color: QColor,
        bg_mode: str,
        is_prev: bool = False,
        y_offset: int = 0,
        selected_index: int | None = None,
    ):
        """绘制图标网格项目"""
        painter.setFont(self._label_font)

        reveal_done = self._reveal_progress >= 1.0
        if reveal_done:
            reveal_opacity = 1.0
        else:
            reveal_opacity = max(0.0, min(1.0, float(getattr(self, "_reveal_progress", 0.0))))

        fm = painter.fontMetrics()
        text_h = fm.height()
        text_spacing = sp(1)
        is_dark = self.settings.theme == "dark"
        use_card = bg_mode == "acrylic"
        icon_alpha = self.settings.icon_alpha
        cols = self.cols
        cell_size = self.cell_size
        cell_h = self.cell_h
        icon_size = self.icon_size
        fixed_rows = self.fixed_rows
        padding = self.padding
        bottom_margin = sp(6)
        has_indicator = len(self.pages) > 1
        indicator_height = sp(16) if has_indicator else 0
        indicator_spacing = sp(4) if has_indicator else 0
        dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
        icons_bottom = self.height() - bottom_margin - dock_height - indicator_height - indicator_spacing

        for i, entry in enumerate(items):
            if isinstance(entry, dict):
                item = entry.get("item")
                name_str = entry.get("text", "")
            else:
                item = entry
                name_str = (getattr(item, "name", "") or "")[:6]
            if item is None:
                continue

            col = i % cols
            row = i // cols

            if row >= fixed_rows:
                break

            x = padding + col * cell_size
            y = icons_bottom - (fixed_rows - row) * cell_h

            # 只记录第一个图标的位置
            if i == 0:
                pass  # Position info available for debugging if needed

            opacity = 1.0 if reveal_done else reveal_opacity
            if opacity <= 0:
                continue

            painter.save()
            painter.setOpacity(opacity)

            if use_card:
                card_pad = sp(2)
                card_size = icon_size + card_pad * 2
                card_x = x + (cell_size - card_size) // 2
                total_h = card_size + text_spacing + text_h
                card_y = y + (cell_h - total_h) // 2
                card_r = sp(6)

                if not is_prev and i == self._drag_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 1.5))
                elif not is_prev and (i == self.hover_index or i == selected_index):
                    painter.setBrush(QBrush(QColor(255, 255, 255, 80 if is_dark else 200)))
                    painter.setPen(QPen(QColor(255, 255, 255, 80 if is_dark else 160), 1))
                else:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 22 if is_dark else 90)))
                    painter.setPen(QPen(QColor(255, 255, 255, 40 if is_dark else 120), 1))

                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
                icon_x = card_x + card_pad
                icon_y = card_y + card_pad
            else:
                if not is_prev and i == self._drag_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 2))
                    painter.drawRoundedRect(QRectF(x, y, cell_size, cell_h), sp(6), sp(6))
                elif not is_prev and (i == self.hover_index or i == selected_index):
                    painter.setBrush(QBrush(hover_color))
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(QRectF(x, y, cell_size, cell_h), sp(6), sp(6))
                total_h = icon_size + text_spacing + text_h
                icon_x = x + (cell_size - icon_size) // 2
                icon_y = y + (cell_h - total_h) // 2
                card_y = icon_y
                card_size = icon_size

            pixmap = self._get_icon_for_paint(item) if hasattr(self, "_get_icon_for_paint") else self._get_icon(item)
            if pixmap:
                painter.setOpacity(icon_alpha * opacity)
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPixmap(icon_x, icon_y, pixmap)

            painter.restore()
            painter.save()
            painter.setOpacity(opacity)
            painter.setPen(QPen(text_color))
            text_y = card_y + card_size + text_spacing
            painter.drawText(x, text_y, cell_size, text_h, QtCompat.AlignHCenter | QtCompat.AlignTop, name_str)

            painter.restore()

    def _tick_indicator(self):
        """动画tick - 平滑过渡到目标页面"""
        frame_start = time.perf_counter()
        last = getattr(self, "_page_anim_last_ts", 0.0) or frame_start
        dt = max(0.001, min(0.05, frame_start - last))
        self._page_anim_last_ts = frame_start

        target = float(getattr(self, "_target_page", self.current_page))
        current = float(getattr(self, "_page_position", float(self.current_page)))
        diff = target - current

        if abs(diff) < 0.002:
            self._page_position = target
            self._page_offset = target
            self._indicator_pos = target
            self._indicator_timer.stop()
            if hasattr(self, "_finish_page_animation"):
                self._finish_page_animation()
        else:
            tau = 0.055
            alpha = 1.0 - math.exp(-dt / tau)
            self._page_position = current + diff * alpha
            self._page_offset = self._page_position
            self._indicator_pos = self._page_position

        tick_ms = (time.perf_counter() - frame_start) * 1000.0
        self._page_anim_frames = int(getattr(self, "_page_anim_frames", 0) or 0) + 1
        self._page_anim_total_ms = float(getattr(self, "_page_anim_total_ms", 0.0)) + tick_ms
        self._page_anim_max_ms = max(float(getattr(self, "_page_anim_max_ms", 0.0)), tick_ms)
        if tick_ms > 16.7:
            self._page_anim_dropped = int(getattr(self, "_page_anim_dropped", 0) or 0) + 1
        if hasattr(self, "_request_page_animation_update"):
            self._request_page_animation_update()
        else:
            self.update()

    def _draw_indicator(self, painter: QPainter, text_color: QColor, accent_color: QColor):
        """绘制页面指示器"""
        dot_size = sp(5)
        active_w = sp(14)
        spacing = sp(10)
        n = len(self.pages)
        pos = float(getattr(self, "_indicator_pos", self.current_page)) % max(1, n)

        # 计算每个点的实际宽度（插值）
        def dot_w(i):
            raw_dist = abs(i - pos)
            dist = min(raw_dist, n - raw_dist)
            return dot_size + (active_w - dot_size) * max(0.0, 1.0 - dist)

        total_width = sum(dot_w(i) for i in range(n)) + spacing * (n - 1)
        cx = (self.width() - total_width) / 2
        y = self.indicator_y + sp(1)

        dim_color = QColor(text_color)
        dim_color.setAlpha(70)

        for i in range(n):
            w = dot_w(i)
            # 颜色插值：离 pos 越近越接近 accent_color
            raw_dist = abs(i - pos)
            dist = min(raw_dist, n - raw_dist)
            t = max(0.0, 1.0 - dist)
            r = int(dim_color.red() + (accent_color.red() - dim_color.red()) * t)
            g = int(dim_color.green() + (accent_color.green() - dim_color.green()) * t)
            b = int(dim_color.blue() + (accent_color.blue() - dim_color.blue()) * t)
            a = int(dim_color.alpha() + (accent_color.alpha() - dim_color.alpha()) * t)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(QColor(r, g, b, a)))
            painter.drawRoundedRect(QRectF(int(cx), y, max(1, int(w)), dot_size), dot_size // 2, dot_size // 2)
            cx += w + spacing

    def _indicator_accent_color(self, accent_color: QColor) -> QColor:
        """Use orange page dots while a valid Explorer/Desktop selection is ready."""
        if getattr(self, "_selected_files_status", "") != "ready" or not getattr(self, "_selected_files", None):
            return accent_color

        started_at = float(getattr(self, "_selected_files_request_started_at", 0.0) or 0.0)
        ttl = float(getattr(self, "SELECTED_FILES_CACHE_TTL_SECONDS", 8.0) or 8.0)
        if started_at <= 0.0 or (time.monotonic() - started_at) > ttl:
            return accent_color

        # 根据窗口类型返回不同颜色：explorer=橙色，desktop=绿色
        context = getattr(self, "_selected_files_context", None)
        target_kind = getattr(context, "target_kind", "explorer")
        is_dark = getattr(self.settings, "theme", "dark") == "dark"

        if target_kind == "desktop":
            # 桌面文件选中：绿色
            return QColor(46, 204, 113) if is_dark else QColor(39, 174, 96)
        else:
            # 资源管理器窗口文件选中：橙色（保持不变）
            return QColor(255, 159, 10) if is_dark else QColor(201, 92, 0)

    def _draw_dock(
        self,
        painter: QPainter,
        text_color: QColor,
        hover_color: QColor,
        dock_bg: QColor,
        drop_highlight_color: QColor,
        bg_mode: str = "theme",
        border_color: QColor = None,
    ):
        """绘制 Dock 栏"""
        if self.dock_height <= 0:
            return

        dock_y = self.dock_y

        # Dock 背景
        dock_bg.setAlpha(self.settings.dock_bg_alpha_255)
        painter.setBrush(QBrush(dock_bg))
        painter.setPen(QtCompat.NoPen)
        radius = sp(getattr(self.settings, "dock_corner_radius", 10))
        painter.drawRoundedRect(QRectF(sp(6), dock_y, self.width() - sp(12), self.dock_height), radius, radius)

        # 顶部分隔线 — 极细纯黑（关闭抗锯齿保证清晰）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.drawLine(0, dock_y, self.width(), dock_y)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Dock 行数模式
        dock_height_mode = getattr(self.settings, "dock_height_mode", 1)
        visible_count = len(self.dock_items)

        # 如果只有一行，按列数限制
        if dock_height_mode == 1:
            visible_count = min(visible_count, self.cols)

        # 计算每行最大图标数 (与主网格一致)
        max_cols = self.cols

        # 计算起始X坐标 (居中)
        # 如果是多行，按满行计算居中；如果是单行且不足满行，按实际数量计算居中
        if dock_height_mode > 1 and visible_count > max_cols:
            line_width = max_cols * self.cell_size
        else:
            line_width = min(visible_count, max_cols) * self.cell_size

        start_x = (self.width() - line_width) // 2
        cell_size = self.cell_size
        icon_size = self.icon_size
        dock_row_stride = icon_size + sp(6)
        is_dark = self.settings.theme == "dark"
        use_card = bg_mode == "acrylic"
        card_pad = sp(2)
        card_r = sp(6)
        hover_pad = sp(4)
        hover_size_extra = sp(9)
        dock_top_padding = sp(8)

        for i in range(visible_count):
            item = self.dock_items[i]

            # 计算行和列
            col = i % max_cols
            row = i // max_cols

            # 如果超出设定行数，停止绘制
            if row >= dock_height_mode:
                break

            x = start_x + col * self.cell_size
            # Dock图标Y坐标：
            # - 单行(row=0)：y = dock_y + 8（与原来完全一致）
            # - 多行(row>0)：y = dock_y + 8 + row * dock_row_stride
            #   dock_row_stride = icon_size + 6（行间距6px，上下边距保持 8px 不变）
            y = dock_y + dock_top_padding + row * dock_row_stride

            hover_x = x + (cell_size - icon_size) // 2 - hover_pad
            hover_y = y - hover_pad
            hover_size = icon_size + hover_size_extra

            # ===== 绘制背景 =====
            if use_card:
                card_size = icon_size + card_pad * 2
                card_x = x + (cell_size - card_size) // 2
                card_y = y - card_pad
                if i == self._drag_dock_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 1.5))
                elif i == self.dock_hover_index:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 80 if is_dark else 200)))
                    painter.setPen(QPen(QColor(255, 255, 255, 80 if is_dark else 160), 1))
                else:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 22 if is_dark else 90)))
                    painter.setPen(QPen(QColor(255, 255, 255, 40 if is_dark else 120), 1))
                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
                icon_x = card_x + card_pad
                icon_y = card_y + card_pad
            else:
                if i == self._drag_dock_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 2))
                    painter.drawRoundedRect(QRectF(hover_x, hover_y, hover_size, hover_size), sp(6), sp(6))
                elif i == self.dock_hover_index:
                    hover = QColor(hover_color)
                    hover.setAlpha(180)
                    painter.setBrush(QBrush(hover))
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(QRectF(hover_x, hover_y, hover_size, hover_size), sp(6), sp(6))
                icon_x = x + (cell_size - icon_size) // 2
                icon_y = y
            # ===== 背景绘制结束 =====

            pixmap = self._get_icon_for_paint(item) if hasattr(self, "_get_icon_for_paint") else self._get_icon(item)
            if pixmap:
                painter.setOpacity(self.settings.icon_alpha)
                painter.drawPixmap(icon_x, icon_y, pixmap)
                painter.setOpacity(1.0)

    def preload_page_animation_pixmaps(self):
        """Pre-render and cache page animation pixmaps to prevent frame drops on first slide."""
        if not hasattr(self, "pages") or not self.pages:
            return
        try:
            theme_bg, text_color, hover_color, border_color, accent_color, dock_bg, drop_highlight_color = (
                self._get_theme_colors()
            )
            bg_mode = getattr(self.settings, "bg_mode", "theme")

            # Pre-render animation pixmaps for all pages
            for page_idx in range(len(self.pages)):
                # Pre-extract icons for this page to populate self._icon_pixmap_cache
                items = self._get_page_animation_items(page_idx)
                for entry in items:
                    item = entry.get("item") if isinstance(entry, dict) else entry
                    if item is not None:
                        try:
                            self._get_icon(item)
                        except Exception as exc:
                            logger.debug("预加载图标失败: %s", exc, exc_info=True)

                # Pre-render the page animation pixmap
                self._get_page_animation_pixmap(page_idx, text_color, hover_color, drop_highlight_color, bg_mode)
            logger.debug(f"Preloaded page animation pixmaps for {len(self.pages)} pages successfully.")
        except Exception as e:
            logger.debug(f"preload page animation pixmaps failed: {e}")
