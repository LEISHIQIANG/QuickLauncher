"""Painting helpers for LauncherPopup."""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
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
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import font_px, sp, spf
from ui.utils.window_effect import is_win10

logger = logging.getLogger(__name__)


class PopupRendererMixin:
    @staticmethod
    def _elided_label(text: str) -> str:
        """Show at most six characters, replacing the sixth with an ellipsis."""
        normalized = " ".join(str(text or "").split())
        return normalized if len(normalized) <= 6 else f"{normalized[:5]}…"

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

    def _draw_win10_internal_shadow(self, painter: QPainter, rect: QRectF, radius: int) -> None:
        margin = max(0, int(getattr(self, "shadow_margin", 0) or 0))
        if margin <= 0 or not is_win10():
            return
        shadow_size = max(1, int(getattr(self, "shadow_size_px", 0) or max(1, margin - sp(4))))
        shadow_distance = max(0, int(getattr(self, "shadow_distance_px", 0) or 0))
        cache_key = (
            self.width(),  # type: ignore[attr-defined]
            self.height(),  # type: ignore[attr-defined]
            round(rect.x(), 2),
            round(rect.y(), 2),
            round(rect.width(), 2),
            round(rect.height(), 2),
            int(radius),
            shadow_size,
            shadow_distance,
        )
        cached = getattr(self, "_win10_internal_shadow_cache", None)
        if cached is not None and getattr(self, "_win10_internal_shadow_cache_key", None) == cache_key:
            painter.drawPixmap(0, 0, cached)
            return

        alpha_scale = max(0.28, min(0.72, 12.0 / float(shadow_size)))

        shadow_pixmap = QPixmap(max(1, self.width()), max(1, self.height()))  # type: ignore[attr-defined]
        shadow_pixmap.fill(QtCompat.transparent)
        shadow_painter = QPainter(shadow_pixmap)
        shadow_painter.setRenderHint(QtCompat.Antialiasing)
        shadow_painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        shadow_painter.setPen(QtCompat.NoPen)
        for i in range(shadow_size, 0, -1):
            t = i / float(shadow_size)
            spread = float(i)
            strength = (1.0 - t) * (1.0 - t)
            alpha = max(1, int((2 + 12 * strength) * alpha_scale))
            shadow_rect = rect.adjusted(
                -spread,
                -spread * 0.88,
                spread,
                spread * 0.88,
            ).translated(0, shadow_distance)
            path = QPainterPath()
            path.addRoundedRect(shadow_rect, radius + spread, radius + spread)
            shadow_painter.fillPath(path, QColor(0, 0, 0, alpha))

        contact_margin = max(sp(4), int(round(shadow_size * 0.48)))
        contact_rect = rect.adjusted(
            contact_margin,
            rect.height() - max(sp(2), shadow_size * 0.28),
            -contact_margin,
            shadow_distance + max(sp(2), shadow_size * 0.28),
        )
        if contact_rect.width() > 0 and contact_rect.height() > 0:
            path = QPainterPath()
            path.addRoundedRect(contact_rect, radius, radius)
            shadow_painter.fillPath(path, QColor(0, 0, 0, max(1, int(9 * alpha_scale))))
        shadow_painter.end()

        self._win10_internal_shadow_cache = shadow_pixmap
        self._win10_internal_shadow_cache_key = cache_key
        painter.drawPixmap(0, 0, shadow_pixmap)

    def paintEvent(self, event):  # noqa: paint_perf
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
        path_cache_key = (self.width(), self.height(), int(margin), int(top_inset), float(radius))
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
            inset = spf(0.5)
            r = max(0.0, float(radius) - inset)
            self._cached_border_path = QPainterPath()
            self._cached_border_path.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset), r, r)

        def make_border_path(pen_width_f: float) -> QPainterPath:
            if pen_width_f == 1.0:
                return self._cached_border_path  # type: ignore[unused-ignore, no-any-return]
            inset = max(spf(0.5), float(pen_width_f) / 2.0)
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

        self._draw_win10_internal_shadow(painter, rect, radius)
        # 绘制背景
        if bg_mode == "glass":
            glass_renderer = getattr(self, "_glass_renderer", None)
            if glass_renderer is not None:
                glass_renderer.draw(painter)
        elif bg_mode == "image" and self.settings.custom_bg_path and os.path.exists(self.settings.custom_bg_path):
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

            # 绘制 1px 半透明边框（暗色: 85,85,85 alpha 120；亮色: 200,200,200 alpha 120）
            if self.settings.theme == "dark":
                border_c = QColor(85, 85, 85, 120)
            else:
                border_c = QColor(200, 200, 200, 120)
            # 使用 make_cosmetic_pen 保证 1px 边框在 125%+ DPI 下不发胖
            painter.setPen(make_cosmetic_pen(border_c, 1))
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
        if bg_mode not in {"acrylic", "glass"}:
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
                # 使用 make_cosmetic_pen 保证 1px 边框在 125%+ DPI 下不发胖
                painter.setPen(make_cosmetic_pen(edge_c, 1))
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPath(make_border_path(1.0))
            else:
                # 默认普通边框
                painter.setPen(make_cosmetic_pen(border_color, 1))
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPath(make_border_path(1.0))

        # 绘制内容。滚轮翻页动画只刷新主体和指示器区域，避免每帧重画 Dock 图标。
        search_visible = (
            bool(self._is_search_bar_visible())
            if hasattr(self, "_is_search_bar_visible")
            else (
                bool(self._is_search_active())
                if hasattr(self, "_is_search_active")
                else bool(getattr(self, "search_query", ""))
            )
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
            else:
                self._draw_page_header(painter, text_color, accent_color)
            if (
                self._is_search_active()
                if hasattr(self, "_is_search_active")
                else bool(getattr(self, "search_query", ""))
            ):
                self._draw_search_results(painter, text_color, hover_color, drop_highlight_color, bg_mode)
            else:
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

        shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
        pin_y_offset = (self._body_y_offset() if hasattr(self, "_body_y_offset") else 0) + shadow_margin
        pinned_rect = QRect(max(0, self.width() - shadow_margin - sp(18)), pin_y_offset, sp(18), sp(18))
        if self.is_pinned and dirty_rect.intersects(pinned_rect):
            painter.setBrush(QBrush(accent_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawEllipse(self.width() - shadow_margin - sp(16), pin_y_offset + sp(6), sp(8), sp(8))

    def _draw_icons(
        self,
        painter: QPainter,
        text_color: QColor,
        hover_color: QColor,
        drop_highlight_color: QColor,
        bg_mode: str = "theme",
    ):
        """绘制图标网格"""
        if not self.pages or self.current_page >= len(self.pages):  # type: ignore[attr-defined]
            return

        painter.setFont(self._label_font)  # type: ignore[attr-defined]

        page_pos = float(getattr(self, "_page_position", getattr(self, "_page_offset", float(self.current_page))))  # type: ignore[attr-defined]
        self._page_offset = page_pos
        y_offset = self._body_y_offset() if hasattr(self, "_body_y_offset") else 0
        page_base = math.floor(page_pos)
        page_fraction = page_pos - page_base
        w = self.width()  # type: ignore[attr-defined]

        shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
        visual_w = w - 2 * shadow_margin

        if page_fraction > 0.001 and len(self.pages) > 1:  # type: ignore[attr-defined]
            first_index = page_base % len(self.pages)  # type: ignore[attr-defined]
            second_index = (page_base + 1) % len(self.pages)  # type: ignore[attr-defined]
            first_pixmap = self._get_page_animation_pixmap(
                first_index, text_color, hover_color, drop_highlight_color, bg_mode
            )
            second_pixmap = self._get_page_animation_pixmap(
                second_index, text_color, hover_color, drop_highlight_color, bg_mode
            )
            if first_pixmap is not None and second_pixmap is not None:
                offset1 = int(visual_w * page_fraction)
                visible1 = visual_w - offset1
                if visible1 > 0:
                    painter.save()
                    painter.setClipRect(
                        shadow_margin,
                        y_offset + shadow_margin,
                        visible1,
                        max(0, self.content_height - y_offset - shadow_margin),  # type: ignore[attr-defined]
                    )
                    painter.drawPixmap(-offset1, 0, first_pixmap)
                    painter.restore()
                offset2 = int(visual_w * (1.0 - page_fraction))
                visible2 = visual_w - offset2
                if visible2 > 0:
                    painter.save()
                    painter.setClipRect(
                        shadow_margin + offset2,
                        y_offset + shadow_margin,
                        visible2,
                        max(0, self.content_height - y_offset - shadow_margin),  # type: ignore[attr-defined]
                    )
                    painter.drawPixmap(offset2, 0, second_pixmap)
                    painter.restore()
            else:
                offset1 = int(visual_w * page_fraction)
                visible1 = visual_w - offset1
                if visible1 > 0:
                    painter.save()
                    painter.setClipRect(
                        shadow_margin,
                        y_offset + shadow_margin,
                        visible1,
                        max(0, self.content_height - y_offset - shadow_margin),  # type: ignore[attr-defined]
                    )
                    painter.translate(-offset1, 0)
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

                offset2 = int(visual_w * (1.0 - page_fraction))
                visible2 = visual_w - offset2
                if visible2 > 0:
                    painter.save()
                    painter.setClipRect(
                        shadow_margin + offset2,
                        y_offset + shadow_margin,
                        visible2,
                        max(0, self.content_height - y_offset - shadow_margin),  # type: ignore[attr-defined]
                    )
                    painter.translate(offset2, 0)
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

        display_page = round(page_pos) % len(self.pages)  # type: ignore[attr-defined]
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
        if not self.pages:  # type: ignore[attr-defined]
            return None
        page_index = page_index % len(self.pages)  # type: ignore[attr-defined]
        items = self._get_page_animation_items(page_index)
        if not self._page_animation_icons_ready(items):
            return None
        key = (
            page_index,
            getattr(self, "_model_revision", 0),
            self.width(),  # type: ignore[attr-defined]
            self.content_height,  # type: ignore[attr-defined]
            self.icon_size,  # type: ignore[attr-defined]
            self.cell_size,  # type: ignore[attr-defined]
            self._page_animation_screen_key(),
            getattr(self.settings, "theme", "dark"),  # type: ignore[attr-defined]
            bg_mode,
            getattr(self.settings, "sort_mode", "custom"),  # type: ignore[attr-defined]
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
        logical_w = max(1, int(self.width()))  # type: ignore[attr-defined]
        logical_h = max(1, int(self.content_height))  # type: ignore[attr-defined]
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
        return self.pages[page_index].items  # type: ignore[attr-defined]

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
        preedit = getattr(self, "_search_preedit_text", "") or ""
        is_dark = getattr(self.settings, "theme", "dark") == "dark"  # type: ignore[attr-defined]

        if hasattr(self, "_search_bar_rect"):
            rect = self._search_bar_rect()
        else:
            shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
            rect = QRectF(
                self.padding + sp(0), shadow_margin + sp(8), self.width() - (self.padding + sp(0)) * 2, sp(28)  # type: ignore[attr-defined]
            )

        rect_h = rect.height()
        radius = sp(8)

        painter.save()

        # 1. 绘制阴影（仅在浅色模式下绘制精致投影）
        if not is_dark:
            for i in range(3, 0, -1):
                shadow_color = QColor(0, 0, 0, int(7 - i * 1.5))
                shadow_rect = rect.adjusted(
                    -i * spf(0.5), -i * spf(0.2) + spf(0.5), i * spf(0.5), i * spf(0.8) + spf(0.5)
                )
                shadow_radius = radius + i * spf(0.5)
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(shadow_color))
                painter.drawRoundedRect(shadow_rect, shadow_radius, shadow_radius)

        # 2. 绘制胶囊背景
        bg = QColor(255, 255, 255, 12 if is_dark else 160)
        border = QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 8)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, radius, radius)

        # 3. 字体设置
        font = self._search_font() if hasattr(self, "_search_font") else QFont(self._label_font)  # type: ignore[attr-defined]
        if font.pixelSize() <= 0:
            font.setPixelSize(font_px(10))
        painter.setFont(font)
        metrics = painter.fontMetrics()

        def text_width(value: str) -> int:
            if hasattr(metrics, "horizontalAdvance"):
                return int(metrics.horizontalAdvance(value))
            return int(metrics.width(value))

        # 4. 判断是否居中显示占位符
        show_centered = not bool(query) and not bool(preedit) and not getattr(self, "_search_forced_active", False)
        icon_size = sp(16)
        gap = sp(6)

        icon_color = QColor(text_color)
        icon_color.setAlpha(128 if is_dark else 100)

        if show_centered:
            text_w = text_width("搜索")
            total_w = icon_size + gap + text_w
            icon_x = rect.left() + (rect.width() - total_w) / 2
            text_x = icon_x + icon_size + gap
            draw_text_rect = QRectF(text_x, rect.top(), text_w + sp(4), rect_h)
        else:
            icon_x = rect.left() + sp(12)

        # 5. 绘制搜索图标
        painter.save()
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setBrush(QtCompat.NoBrush)
        painter.setPen(QPen(icon_color, max(1.5, sp(1.8)), QtCompat.SolidLine, QtCompat.RoundCap, QtCompat.RoundJoin))  # type: ignore[arg-type]

        icon_y = rect.center().y() - icon_size / 2
        circle_size = icon_size * 0.72
        painter.drawEllipse(QRectF(icon_x, icon_y, circle_size, circle_size))

        handle_start_x = icon_x + circle_size * 0.8
        handle_start_y = icon_y + circle_size * 0.8
        painter.drawLine(
            int(handle_start_x),
            int(handle_start_y),
            int(icon_x + icon_size),
            int(icon_y + icon_size),
        )
        painter.restore()

        # 6. 绘制文本
        text_rect = (
            self._search_text_rect() if hasattr(self, "_search_text_rect") else rect.adjusted(sp(32), 0, -sp(16), 0)
        )
        scroll_x = int(getattr(self, "__dict__", {}).get("_search_scroll_x", 0) or 0)
        draw_text_rect_typing = QRectF(text_rect)
        draw_text_rect_typing.moveLeft(text_rect.left() - scroll_x)

        # 绘制选中文本背景
        selection = self._search_selection_bounds() if hasattr(self, "_search_selection_bounds") else None
        if selection and not show_centered:
            sel_start, sel_end = selection
            prefix = self._search_text_prefix() if hasattr(self, "_search_text_prefix") else ""
            sel_x = int(text_rect.left() + text_width(prefix + query[:sel_start]) - scroll_x)
            sel_w = max(1, int(text_width(query[sel_start:sel_end])))
            sel_rect = QRectF(sel_x, text_rect.top() + sp(6), sel_w, max(sp(12), text_rect.height() - sp(12)))
            sel_rect = sel_rect.intersected(text_rect)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 95)))
            if sel_rect.width() > 0:
                painter.drawRoundedRect(sel_rect, sp(3), sp(3))

        painter.save()
        painter.setClipRect(text_rect)
        if show_centered:
            painter.setPen(icon_color)
            painter.drawText(draw_text_rect, QtCompat.AlignVCenter | QtCompat.AlignLeft, "搜索")
        else:
            if not query and not preedit:
                painter.setPen(icon_color)
                painter.drawText(draw_text_rect_typing, QtCompat.AlignVCenter | QtCompat.AlignLeft, "搜索")
            else:
                painter.setPen(text_color)
                prefix = self._search_text_prefix() if hasattr(self, "_search_text_prefix") else ""
                cursor = self._get_search_cursor_pos() if hasattr(self, "_get_search_cursor_pos") else len(query)
                label = f"{prefix}{query[:cursor]}{preedit}{query[cursor:]}"
                painter.drawText(draw_text_rect_typing, QtCompat.AlignVCenter | QtCompat.AlignLeft, label)
        painter.restore()

        # 绘制输入法拼音下划线
        if preedit and not show_centered:
            prefix = self._search_text_prefix() if hasattr(self, "_search_text_prefix") else ""
            cursor = self._get_search_cursor_pos() if hasattr(self, "_get_search_cursor_pos") else len(query)
            underline_x = int(text_rect.left() + text_width(prefix + query[:cursor]) - scroll_x)
            underline_w = max(1, int(text_width(preedit)))
            underline_y = int(text_rect.center().y() + metrics.ascent() / 2 + sp(4))
            painter.setPen(QPen(accent_color, 1))
            painter.save()
            painter.setClipRect(text_rect)
            painter.drawLine(underline_x, underline_y, underline_x + underline_w, underline_y)
            painter.restore()

        # 7. 绘制光标
        if (
            self._is_search_active()  # type: ignore[attr-defined]
            and getattr(self, "_search_cursor_visible", True)
            and hasattr(self, "_search_cursor_rect")
            and not show_centered
        ):
            cursor_rect = self._search_cursor_rect()
            if text_rect.intersects(QRectF(cursor_rect)):
                painter.fillRect(cursor_rect, accent_color)
        painter.restore()

    def _draw_page_header(self, painter: QPainter, text_color: QColor, accent_color: QColor):
        pages = list(getattr(self, "pages", None) or [])
        if not pages:
            return

        if hasattr(self, "_page_header_rect"):
            rect = self._page_header_rect()
        else:
            shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)
            rect = QRectF(
                self.padding + sp(0), shadow_margin + sp(8), self.width() - (self.padding + sp(0)) * 2, sp(28)  # type: ignore[attr-defined]
            )

        radius = sp(8)
        is_dark = getattr(self.settings, "theme", "dark") == "dark"  # type: ignore[attr-defined]

        painter.save()

        # 1. 绘制阴影（仅在浅色模式下绘制）
        if not is_dark:
            for i in range(3, 0, -1):
                shadow_color = QColor(0, 0, 0, int(7 - i * 1.5))
                shadow_rect = rect.adjusted(
                    -i * spf(0.5), -i * spf(0.2) + spf(0.5), i * spf(0.5), i * spf(0.8) + spf(0.5)
                )
                shadow_radius = radius + i * spf(0.5)
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(shadow_color))
                painter.drawRoundedRect(shadow_rect, shadow_radius, shadow_radius)

        # 2. 绘制胶囊背景
        bg = QColor(255, 255, 255, 12 if is_dark else 160)
        border = QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 8)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, radius, radius)

        # 3. 字体与标签设置
        font = self._search_font() if hasattr(self, "_search_font") else QFont(self._label_font)  # type: ignore[attr-defined]
        if font.pixelSize() <= 0:
            font.setPixelSize(font_px(10))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        active_index = max(0, min(int(getattr(self, "current_page", 0) or 0), len(pages) - 1))

        painter.save()
        painter.setClipRect(rect.adjusted(1, 0, -1, 0))

        tab_rects = self._page_header_tab_rects() if hasattr(self, "_page_header_tab_rects") else []
        for page_index, tab_rect in tab_rects:
            name = str(getattr(pages[page_index], "name", "") or "")
            label = metrics.elidedText(name, QtCompat.ElideRight, max(1, int(tab_rect.width() - sp(12))))
            color = QColor(accent_color) if page_index == active_index else QColor(text_color)
            color.setAlpha(255 if page_index == active_index else (128 if is_dark else 138))
            painter.setPen(color)

            # 文本垂直和水平居中
            painter.drawText(tab_rect, QtCompat.AlignCenter, label)

            if page_index == active_index:
                # 绘制选中指示器的微小胶囊线
                adv_width = (
                    metrics.horizontalAdvance(label) if hasattr(metrics, "horizontalAdvance") else metrics.width(label)
                )
                line_w = min(max(sp(18), adv_width // 2), max(sp(18), int(tab_rect.width() - sp(20))))
                line_h = sp(3)
                line_x = tab_rect.center().x() - line_w / 2
                line_y = rect.bottom() - sp(4)
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(accent_color))
                painter.drawRoundedRect(QRectF(line_x, line_y, line_w, line_h), line_h / 2, line_h / 2)
        painter.restore()
        painter.restore()

    def _draw_search_results(
        self, painter: QPainter, text_color: QColor, hover_color: QColor, drop_highlight_color: QColor, bg_mode: str
    ):
        all_results = getattr(self, "search_results", []) or []
        results = all_results
        if not all_results:
            painter.setPen(text_color)
            painter.setFont(self._label_font)  # type: ignore[attr-defined]
            query = getattr(self, "search_query", "")
            if query.startswith("/"):
                action_hint = "输入命令名称"
            elif " " in query:
                action_hint = "按 Enter 进行网页搜索"
            else:
                action_hint = "无匹配结果"
            y_offset = (
                self._body_y_offset() if hasattr(self, "_body_y_offset") else getattr(self, "search_bar_height", sp(32))
            )
            painter.drawText(
                QRect(0, self.padding + y_offset, self.width(), self.content_height), QtCompat.AlignCenter, action_hint  # type: ignore[attr-defined]
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
                {"item": result.shortcut, "text": getattr(result.shortcut, "name", "") or ""}
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
                self._body_y_offset() if hasattr(self, "_body_y_offset") else getattr(self, "search_bar_height", sp(32))
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
            items = self.pages[page_index].items  # type: ignore[attr-defined]
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
        painter.setFont(self._label_font)  # type: ignore[attr-defined]

        reveal_done = self._reveal_progress >= 1.0
        if reveal_done:
            reveal_opacity = 1.0
        else:
            reveal_opacity = max(0.0, min(1.0, float(getattr(self, "_reveal_progress", 0.0))))

        fm = painter.fontMetrics()
        text_h = fm.height()
        text_spacing = sp(1)
        is_dark = self.settings.theme == "dark"  # type: ignore[attr-defined]
        # Background modes should only change the panel background; icon affordances stay aligned.
        use_card = True
        icon_alpha = self.settings.icon_alpha  # type: ignore[attr-defined]
        cols = self.cols  # type: ignore[attr-defined]
        cell_size = self.cell_size  # type: ignore[attr-defined]
        cell_h = self.cell_h  # type: ignore[attr-defined]
        icon_size = self.icon_size  # type: ignore[attr-defined]
        fixed_rows = self.fixed_rows  # type: ignore[attr-defined]
        padding = self.padding  # type: ignore[attr-defined]
        bottom_margin = self._dock_outer_bottom_gap()  # type: ignore[attr-defined]
        has_indicator = len(self.pages) > 1  # type: ignore[attr-defined]
        indicator_height = sp(16) if has_indicator else 0
        indicator_spacing = sp(4) if has_indicator else 0
        dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0  # type: ignore[attr-defined]
        icons_bottom = (
            self.height()  # type: ignore[attr-defined]
            - int(getattr(self, "shadow_margin", 0) or 0)
            - bottom_margin
            - dock_height
            - indicator_height
            - indicator_spacing
        )

        for i, entry in enumerate(items):
            if isinstance(entry, dict):
                item = entry.get("item")
                name_str = entry.get("text", "")
            else:
                item = entry
                name_str = getattr(item, "name", "") or ""
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
                card_pad = sp(4)
                card_size = icon_size + card_pad * 2
                card_x = x + (cell_size - card_size) // 2
                total_h = card_size + text_spacing + text_h
                card_y = y + (cell_h - total_h) // 2
                card_r = sp(6)

                if not is_prev and i == self._drag_hover_index:  # type: ignore[attr-defined]
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 1.5))
                elif not is_prev and (i == self.hover_index or i == selected_index):  # type: ignore[attr-defined]
                    painter.setBrush(QBrush(QColor(255, 255, 255, 80 if is_dark else 200)))
                    painter.setPen(QPen(QColor(255, 255, 255, 80 if is_dark else 160), 1))
                else:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 22 if is_dark else 90)))
                    painter.setPen(QPen(QColor(255, 255, 255, 40 if is_dark else 120), 1))

                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
                icon_x = card_x + card_pad
                icon_y = card_y + card_pad
            else:
                if not is_prev and i == self._drag_hover_index:  # type: ignore[attr-defined]
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 2))
                    painter.drawRoundedRect(QRectF(x, y, cell_size, cell_h), sp(6), sp(6))
                elif not is_prev and (i == self.hover_index or i == selected_index):  # type: ignore[attr-defined]
                    painter.setBrush(QBrush(hover_color))
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(QRectF(x, y, cell_size, cell_h), sp(6), sp(6))
                total_h = icon_size + text_spacing + text_h
                icon_x = x + (cell_size - icon_size) // 2
                icon_y = y + (cell_h - total_h) // 2
                card_y = icon_y
                card_size = icon_size

            pixmap = self._get_icon_for_paint(item) if hasattr(self, "_get_icon_for_paint") else self._get_icon(item)  # type: ignore[attr-defined]
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
            label = self._elided_label(name_str)
            painter.drawText(x, text_y, cell_size, text_h, QtCompat.AlignHCenter | QtCompat.AlignTop, label)

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
        active_w = sp(16)
        spacing = sp(8)
        n = len(self.pages)  # type: ignore[attr-defined]
        pos = float(getattr(self, "_indicator_pos", self.current_page)) % max(1, n)  # type: ignore[arg-type, attr-defined]

        # 计算每个点的实际宽度（插值）
        def dot_w(i):
            raw_dist = abs(i - pos)
            dist = min(raw_dist, n - raw_dist)
            return dot_size + (active_w - dot_size) * max(0.0, 1.0 - dist)

        total_width = sum(dot_w(i) for i in range(n)) + spacing * (n - 1)
        cx = (self.width() - total_width) / 2  # type: ignore[attr-defined]
        y = self.indicator_y + sp(1)  # type: ignore[attr-defined]

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
        is_dark = getattr(self.settings, "theme", "dark") == "dark"  # type: ignore[attr-defined]

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
        border_color: QColor = None,  # type: ignore[unused-ignore, assignment]
    ):
        """绘制 Dock 栏"""
        if self.dock_height <= 0:  # type: ignore[attr-defined]
            return

        dock_y = self.dock_y  # type: ignore[attr-defined]
        shadow_margin = int(self.__dict__.get("shadow_margin", 0) or 0)

        # Dock 背景
        dock_bg.setAlpha(self.settings.dock_bg_alpha_255)  # type: ignore[attr-defined]
        painter.setBrush(QBrush(dock_bg))
        painter.setPen(QtCompat.NoPen)
        radius = sp(getattr(self.settings, "dock_corner_radius", 10))  # type: ignore[attr-defined]
        bg_y = dock_y + self._dock_background_top_gap()  # type: ignore[attr-defined]
        painter.drawRoundedRect(
            QRectF(
                shadow_margin + sp(6),
                bg_y,
                max(1, self.width() - shadow_margin * 2 - sp(12)),  # type: ignore[attr-defined]
                self._dock_background_height(),  # type: ignore[attr-defined]
            ),
            radius,
            radius,
        )

        # 顶部分隔线 — 极细纯黑（关闭抗锯齿保证清晰）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.drawLine(shadow_margin, dock_y, self.width() - shadow_margin, dock_y)  # type: ignore[attr-defined]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Dock 行数模式
        dock_height_mode = getattr(self.settings, "dock_height_mode", 1)  # type: ignore[attr-defined]
        visible_count = len(self.dock_items)  # type: ignore[attr-defined]

        # 如果只有一行，按列数限制
        if dock_height_mode == 1:
            visible_count = min(visible_count, self.cols)  # type: ignore[attr-defined]

        # 计算每行最大图标数 (与主网格一致)
        max_cols = self.cols  # type: ignore[attr-defined]

        # 计算起始X坐标 (居中)
        # 如果是多行，按满行计算居中；如果是单行且不足满行，按实际数量计算居中
        if dock_height_mode > 1 and visible_count > max_cols:
            line_width = max_cols * self.cell_size  # type: ignore[attr-defined]
        else:
            line_width = min(visible_count, max_cols) * self.cell_size  # type: ignore[attr-defined]

        start_x = (self.width() - line_width) // 2  # type: ignore[attr-defined]
        cell_size = self.cell_size  # type: ignore[attr-defined]
        icon_size = self.icon_size  # type: ignore[attr-defined]
        display_rows = self._dock_display_rows(visible_count, max_cols)  # type: ignore[attr-defined]
        dock_row_stride = self._get_dock_row_stride(display_rows)  # type: ignore[attr-defined]
        is_dark = self.settings.theme == "dark"  # type: ignore[attr-defined]
        card_pad = sp(4)
        card_r = sp(6)
        first_icon_y = self._dock_first_icon_y(display_rows)  # type: ignore[attr-defined]

        for i in range(visible_count):
            item = self.dock_items[i]  # type: ignore[attr-defined]

            # 计算行和列
            col = i % max_cols
            row = i // max_cols

            # 如果超出设定行数，停止绘制
            if row >= dock_height_mode:
                break

            x = start_x + col * self.cell_size  # type: ignore[attr-defined]
            y = first_icon_y + row * dock_row_stride

            card_size = icon_size + card_pad * 2
            card_x = x + (cell_size - card_size) // 2
            card_y = y - card_pad - sp(1)

            # ===== 绘制背景 =====
            if i == self._drag_dock_hover_index:  # type: ignore[attr-defined]
                highlight = QColor(drop_highlight_color)
                highlight.setAlpha(80)
                painter.setBrush(QBrush(highlight))
                painter.setPen(QPen(drop_highlight_color, 1.5))
                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
            elif i == self.dock_hover_index:  # type: ignore[attr-defined]
                painter.setBrush(QBrush(QColor(255, 255, 255, 80 if is_dark else 200)))
                painter.setPen(QPen(QColor(255, 255, 255, 80 if is_dark else 160), 1))
                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
            else:
                painter.setBrush(QBrush(QColor(255, 255, 255, 22 if is_dark else 90)))
                painter.setPen(QPen(QColor(255, 255, 255, 40 if is_dark else 120), 1))
                painter.drawRoundedRect(QRectF(card_x, card_y, card_size, card_size), card_r, card_r)
            icon_x = card_x + card_pad
            icon_y = card_y + card_pad
            # ===== 背景绘制结束 =====

            pixmap = self._get_icon_for_paint(item) if hasattr(self, "_get_icon_for_paint") else self._get_icon(item)  # type: ignore[attr-defined]
            if pixmap:
                painter.setOpacity(self.settings.icon_alpha)  # type: ignore[attr-defined]
                painter.drawPixmap(icon_x, icon_y, pixmap)
                painter.setOpacity(1.0)

            # ===== 绘制文本标签 =====
            if self._dock_shows_text(display_rows):  # type: ignore[attr-defined]
                name_str = getattr(item, "name", "") or ""
                label = self._elided_label(name_str)
                painter.setFont(self._label_font)  # type: ignore[attr-defined]
                painter.setPen(QPen(text_color))
                fm = painter.fontMetrics()
                text_h = fm.height()
                text_spacing = sp(1)
                text_y = card_y + card_size + text_spacing
                painter.drawText(x, text_y, cell_size, text_h, QtCompat.AlignHCenter | QtCompat.AlignTop, label)

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
