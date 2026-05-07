"""Painting helpers for LauncherPopup."""

import logging
import os
import time

from qt_compat import (
    QColor, QBrush, QFont, QPainter, QPainterPath, QPen, QPixmap,
    QRect, QRectF, Qt, QtCompat
)
from ui.utils.window_effect import is_win10

logger = logging.getLogger(__name__)


class PopupRendererMixin:
    def paintEvent(self, event):
        """绘制"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.TextAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)
        
        # 获取颜色配置
        if self.settings.theme == "dark":
            theme_bg = QColor(28, 28, 30)
            text_color = QColor(255, 255, 255, 230)
            hover_color = QColor(255, 255, 255, 50)
            border_color = QColor(255, 255, 255, 40)
            accent_color = QColor(10, 132, 255)
            dock_bg = QColor(255, 255, 255, 18)
            drop_highlight_color = QColor(10, 132, 255)
        else:
            theme_bg = QColor(242, 242, 247)
            text_color = QColor(28, 28, 30, 230)
            hover_color = QColor(255, 255, 255, 160)
            border_color = QColor(0, 0, 0, 20)
            accent_color = QColor(0, 122, 255)
            dock_bg = QColor(255, 255, 255, 12)
            drop_highlight_color = QColor(0, 122, 255)
        
        # 确定背景颜色和模式
        bg_mode = getattr(self.settings, 'bg_mode', 'theme')
        blur_radius = getattr(self.settings, 'bg_blur_radius', 0)
        
        # 统一计算绘制区域 (用于背景路径和后续高光计算)
        margin = getattr(self, 'shadow_margin', 0)
        rect = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        radius = self._get_paint_corner_radius(bg_mode, blur_radius)

        # 使用缓存的路径，避免重复计算
        if self._cached_bg_path is None or self._cached_bg_path.isEmpty():
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            self._cached_bg_path = path
        else:
            path = self._cached_bg_path

        def make_border_path(pen_width_f: float) -> QPainterPath:
            inset = max(0.5, float(pen_width_f) / 2.0)
            r = max(0.0, float(radius) - inset)
            pr = rect.adjusted(inset, inset, -inset, -inset)
            p = QPainterPath()
            p.addRoundedRect(pr, r, r)
            return p

        def composition_mode(name: str):
            mode = getattr(QPainter, f"CompositionMode_{name}", None)
            if mode is not None:
                return mode
            enum = getattr(QPainter, "CompositionMode", None)
            if enum is None:
                return None
            return getattr(enum, name, None) or getattr(enum, f"CompositionMode_{name}", None)

        if radius > 0:
            painter.save()
            full = QPainterPath()
            full.addRect(QRectF(self.rect()))
            outside = full.subtracted(path)
            clear_mode = composition_mode("Clear")
            if clear_mode is not None:
                painter.setCompositionMode(clear_mode)
            painter.fillPath(outside, QtCompat.transparent)
            painter.restore()
            
        # 绘制背景
        if bg_mode == 'image' and self.settings.custom_bg_path and os.path.exists(self.settings.custom_bg_path):
            # 图片模式
            bg_pixmap = self._get_cached_bg_pixmap()
            if bg_pixmap:
                painter.save()
                # 图片模式下的透明度 (0=透明, 100=不透明)
                paint_alpha = self.settings.bg_alpha / 100.0
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
                
        elif bg_mode == 'acrylic':
            # ===== 亚克力模式：与配置窗口 RoundedWindow 相同的绘制方式 =====
            # bg_alpha 0-100: 0=最透明/最强磨砂, 100=最不透明/实色
            user_alpha = getattr(self.settings, 'bg_alpha', 90)

            tint_color = QColor(theme_bg)
            if is_win10():
                # Win10: paintEvent tint alpha 范围 0~220 (bg_alpha 0~100 线性映射)
                paint_alpha = max(0, min(220, int(user_alpha * 2.2)))
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
            painter.setPen(QPen(border_c, 1))
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(path)
            
            # Win10 多层抗锯齿柔化（与 RoundedWindow 一致）
            if is_win10():
                soften_color = QColor(theme_bg)
                soften_color.setAlpha(int(soften_color.alpha() * 0.6))
                painter.setPen(QPen(soften_color, 0.5))
                inner_path = QPainterPath()
                inner_path.addRoundedRect(
                    rect.adjusted(0.75, 0.75, -0.75, -0.75),
                    radius, radius
                )
                painter.drawPath(inner_path)
                
                soften_color2 = QColor(theme_bg)
                soften_color2.setAlpha(int(soften_color2.alpha() * 0.3))
                painter.setPen(QPen(soften_color2, 0.5))
                outer_path = QPainterPath()
                outer_path.addRoundedRect(
                    rect.adjusted(0.25, 0.25, -0.25, -0.25),
                    radius + 0.5, radius + 0.5
                )
                painter.drawPath(outer_path)
                
        else: # theme mode
            c = QColor(theme_bg)
            # 计算透明度 (0=透明/0, 100=不透明/255)
            alpha_val = int(255 * (self.settings.bg_alpha / 100.0))
            c.setAlpha(max(0, min(255, alpha_val)))
            painter.fillPath(path, QBrush(c))

        # 绘制边缘高光 / 边框（亚克力模式已在上方绘制完毕，这里只处理 theme 和 image 模式）
        if bg_mode != 'acrylic':
            edge_opacity = getattr(self.settings, 'edge_highlight_opacity', 0.0)
            
            if edge_opacity > 0:
                # 用户自定义高光 (模拟玻璃质感)
                edge_color_str = getattr(self.settings, 'edge_highlight_color', '#ffffff')
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
        
        # 偏移 painter 坐标系，以便后续内容绘制逻辑不用修改坐标
        # margin = getattr(self, 'shadow_margin', 0)
        # if margin > 0:
        #     painter.translate(margin, margin)
        
        # 绘制内容
        self._draw_icons(painter, text_color, hover_color, drop_highlight_color, bg_mode)
        
        if len(self.pages) > 1:
            self._draw_indicator(painter, text_color, accent_color)
        
        if self.dock_items:
            self._draw_dock(painter, text_color, hover_color, dock_bg, drop_highlight_color, bg_mode, border_color)
        
        if self.is_pinned:
            painter.setBrush(QBrush(accent_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawEllipse(self.width() - 14, 6, 8, 8)
    def _draw_icons(self, painter: QPainter, text_color: QColor, hover_color: QColor,
                    drop_highlight_color: QColor, bg_mode: str = 'theme'):
        """绘制图标网格"""
        if not self.pages or self.current_page >= len(self.pages):
            return

        painter.setFont(self._label_font)

        # 翻页滑动动画
        if self._page_slide_progress < 1.0:
            # easing: ease-out cubic
            t = self._page_slide_progress
            ease = 1.0 - (1.0 - t) ** 3
            w = self.width()
            offset_new = int(w * (1.0 - ease) * self._page_slide_dir)
            offset_old = int(-w * ease * self._page_slide_dir)

            # 绘制旧页（滑出）
            if 0 <= self._prev_page < len(self.pages):
                painter.save()
                painter.translate(offset_old, 0)
                self._draw_page_items(painter, self._prev_page, text_color, hover_color,
                                      drop_highlight_color, bg_mode, is_prev=True)
                painter.restore()

            # 绘制新页（滑入）
            painter.save()
            painter.translate(offset_new, 0)
            self._draw_page_items(painter, self.current_page, text_color, hover_color,
                                  drop_highlight_color, bg_mode, is_prev=False)
            painter.restore()
            return

        self._draw_page_items(painter, self.current_page, text_color, hover_color,
                              drop_highlight_color, bg_mode, is_prev=False)
    def _draw_page_items(self, painter: QPainter, page_index: int, text_color: QColor,
                         hover_color: QColor, drop_highlight_color: QColor,
                         bg_mode: str, is_prev: bool):
        """绘制指定页的图标"""
        items = self.pages[page_index].items

        # 获取窗口中心点（鼠标位置）
        center_x = self.width() / 2
        center_y = self.height() / 2
        max_distance = ((self.width() / 2) ** 2 + (self.height() / 2) ** 2) ** 0.5

        # 如果动画未完成，预先计算一些值
        if self._reveal_progress < 1.0:
            progress_factor = self._reveal_progress * 2.5

        for i, item in enumerate(items):
            col = i % self.cols
            row = i // self.cols

            if row >= self.fixed_rows:
                break

            x = self.padding + col * self.cell_size
            y = self.padding + row * self.cell_h

            # 动画优化：如果已完成，跳过动画计算
            if self._reveal_progress >= 1.0:
                item_progress = 1.0
                scale = 1.0
                opacity = 1.0
            else:
                # 计算图标中心到窗口中心的距离
                icon_center_x = x + self.cell_size / 2
                icon_center_y = y + self.cell_size / 2
                distance = ((icon_center_x - center_x) ** 2 + (icon_center_y - center_y) ** 2) ** 0.5

                # 根据动画进度和距离计算显示进度
                normalized_distance = distance / max_distance
                item_progress = max(0.0, min(1.0, progress_factor - normalized_distance))

                # 如果还未显示到这个图标，跳过
                if item_progress <= 0:
                    continue

                # 应用缩放和透明度
                scale = 0.85 + 0.15 * item_progress
                opacity = item_progress

            # 保存当前painter状态
            painter.save()
            painter.setOpacity(opacity)

            # 应用缩放变换（仅在动画进行时）
            if scale < 1.0:
                icon_center_x = x + self.cell_size / 2
                icon_center_y = y + self.cell_size / 2
                painter.translate(icon_center_x, icon_center_y)
                painter.scale(scale, scale)
                painter.translate(-icon_center_x, -icon_center_y)

            fm = painter.fontMetrics()
            name_str = item.name[:6] if item.name else ""
            text_h = fm.height()
            text_spacing = 1
            is_dark = self.settings.theme == "dark"
            use_card = (bg_mode == 'acrylic')

            if use_card:
                card_pad = 2
                card_size = self.icon_size + card_pad * 2
                card_x = x + (self.cell_size - card_size) // 2
                total_h = card_size + text_spacing + text_h
                card_y = y + (self.cell_h - total_h) // 2
                card_r = 6

                if not is_prev and i == self._drag_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 1.5))
                elif not is_prev and i == self.hover_index:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 80 if is_dark else 200)))
                    painter.setPen(QPen(QColor(255, 255, 255, 80 if is_dark else 160), 1))
                else:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 22 if is_dark else 90)))
                    painter.setPen(QPen(QColor(255, 255, 255, 40 if is_dark else 120), 1))

                painter.drawRoundedRect(card_x, card_y, card_size, card_size, card_r, card_r)
                icon_x = card_x + card_pad
                icon_y = card_y + card_pad
            else:
                # 非亚克力模式：保持原有悬停逻辑
                if not is_prev and i == self._drag_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 2))
                    painter.drawRoundedRect(x, y, self.cell_size, self.cell_h, 6, 6)
                elif not is_prev and i == self.hover_index:
                    painter.setBrush(QBrush(hover_color))
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(x, y, self.cell_size, self.cell_h, 6, 6)
                total_h = self.icon_size + text_spacing + text_h
                icon_x = x + (self.cell_size - self.icon_size) // 2
                icon_y = y + (self.cell_h - total_h) // 2
                card_y = icon_y
                card_size = self.icon_size

            pixmap = self._get_icon(item)
            if pixmap:
                painter.setOpacity(self.settings.icon_alpha * opacity)
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawPixmap(icon_x, icon_y, pixmap)

            painter.restore()
            painter.save()
            painter.setOpacity(opacity)
            painter.setPen(QPen(text_color))
            text_y = card_y + card_size + text_spacing
            painter.drawText(x, text_y, self.cell_size, text_h,
                             QtCompat.AlignHCenter | QtCompat.AlignTop, name_str)

            painter.restore()
    def _tick_indicator(self):
        target = float(self.current_page)
        diff = target - self._indicator_pos
        if abs(diff) < 0.01:
            self._indicator_pos = target
        else:
            self._indicator_pos += diff * 0.25

        # 推进翻页滑动动画（spring easing）
        if self._page_slide_progress < 1.0:
            remaining = 1.0 - self._page_slide_progress
            self._page_slide_progress += remaining * 0.28
            if self._page_slide_progress > 0.995:
                self._page_slide_progress = 1.0

        if self._page_slide_progress >= 1.0 and abs(diff) < 0.01:
            self._indicator_timer.stop()

        self.update()
    def _draw_indicator(self, painter: QPainter, text_color: QColor, accent_color: QColor):
        """绘制页面指示器"""
        dot_size = 5
        active_w = 14
        spacing = 10
        n = len(self.pages)
        pos = self._indicator_pos  # 浮点插值位置

        # 计算每个点的实际宽度（插值）
        def dot_w(i):
            dist = abs(i - pos)
            return dot_size + (active_w - dot_size) * max(0.0, 1.0 - dist)

        total_width = sum(dot_w(i) for i in range(n)) + spacing * (n - 1)
        cx = (self.width() - total_width) / 2
        y = self.indicator_y + 1

        dim_color = QColor(text_color)
        dim_color.setAlpha(70)

        for i in range(n):
            w = dot_w(i)
            # 颜色插值：离 pos 越近越接近 accent_color
            t = max(0.0, 1.0 - abs(i - pos))
            r = int(dim_color.red()   + (accent_color.red()   - dim_color.red())   * t)
            g = int(dim_color.green() + (accent_color.green() - dim_color.green()) * t)
            b = int(dim_color.blue()  + (accent_color.blue()  - dim_color.blue())  * t)
            a = int(dim_color.alpha() + (accent_color.alpha() - dim_color.alpha()) * t)
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(QColor(r, g, b, a)))
            painter.drawRoundedRect(int(cx), y, max(1, int(w)), dot_size, dot_size // 2, dot_size // 2)
            cx += w + spacing
    def _draw_dock(self, painter: QPainter, text_color: QColor, hover_color: QColor,
                   dock_bg: QColor, drop_highlight_color: QColor, bg_mode: str = 'theme', border_color: QColor = None):
        """绘制 Dock 栏"""
        if self.dock_height <= 0:
            return
            
        dock_y = self.dock_y
        
        # Dock 背景
        dock_bg.setAlpha(self.settings.dock_bg_alpha_255)
        painter.setBrush(QBrush(dock_bg))
        painter.setPen(QtCompat.NoPen)
        radius = getattr(self.settings, 'dock_corner_radius', 10)
        painter.drawRoundedRect(6, dock_y, self.width() - 12, self.dock_height, radius, radius)

        # 顶部分隔线 — 极细纯黑（关闭抗锯齿保证清晰）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.drawLine(0, dock_y, self.width(), dock_y)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Dock 行数模式
        dock_height_mode = getattr(self.settings, 'dock_height_mode', 1)
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
            dock_row_stride = self.icon_size + 6
            y = dock_y + 8 + row * dock_row_stride
            
            hover_x = x + (self.cell_size - self.icon_size) // 2 - 4
            hover_y = y - 4
            hover_size = self.icon_size + 9

            # ===== 绘制背景 =====
            is_dark = self.settings.theme == "dark"
            use_card = (bg_mode == 'acrylic')

            if use_card:
                card_pad = 2
                card_size = self.icon_size + card_pad * 2
                card_x = x + (self.cell_size - card_size) // 2
                card_y = y - card_pad
                card_r = 6
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
                painter.drawRoundedRect(card_x, card_y, card_size, card_size, card_r, card_r)
                icon_x = card_x + card_pad
                icon_y = card_y + card_pad
            else:
                if i == self._drag_dock_hover_index:
                    highlight = QColor(drop_highlight_color)
                    highlight.setAlpha(80)
                    painter.setBrush(QBrush(highlight))
                    painter.setPen(QPen(drop_highlight_color, 2))
                    painter.drawRoundedRect(hover_x, hover_y, hover_size, hover_size, 6, 6)
                elif i == self.dock_hover_index:
                    hover_color.setAlpha(180)
                    painter.setBrush(QBrush(hover_color))
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(hover_x, hover_y, hover_size, hover_size, 6, 6)
                icon_x = x + (self.cell_size - self.icon_size) // 2
                icon_y = y
            # ===== 背景绘制结束 =====
            
            pixmap = self._get_icon(item)
            if pixmap:
                painter.setOpacity(self.settings.icon_alpha)
                painter.drawPixmap(icon_x, icon_y, pixmap)
                painter.setOpacity(1.0)
