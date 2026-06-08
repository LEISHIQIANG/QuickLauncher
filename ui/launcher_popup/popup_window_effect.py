"""Window effects (Win10/Win11 round corners, acrylic) and layout helpers for LauncherPopup."""

import logging

from qt_compat import (
    QApplication,
    QPainterPath,
    QPoint,
    QRectF,
    QRegion,
    Qt,
    QtCompat,
    QTimer,
)
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.window_effect import is_win10, is_win11
from ui.utils.ui_scale import sp, spf, font_px

logger = logging.getLogger(__name__)


class PopupWindowEffectMixin:
    """Win10/Win11 window effects: corner radius, acrylic, blur."""

    # 效果参数缓存，用于避免重复的 DWM 重建（showEvent 等场景）
    _last_effect_state = None

    def _get_win11_corner_preference(self, desired_radius: int):
        r = max(0, int(desired_radius))
        if r <= 0:
            return self.window_effect.DWMWCP_DONOTROUND
        if r <= 6:
            return self.window_effect.DWMWCP_ROUNDSMALL
        return self.window_effect.DWMWCP_ROUND

    def _get_win11_effective_radius(self, desired_radius: int) -> int:
        r = max(0, int(desired_radius))
        if r <= 0:
            return 0
        if r <= 6:
            return 4
        return 8

    def _get_paint_corner_radius(self, bg_mode=None, blur_radius=None) -> int:
        desired = getattr(self.settings, "corner_radius", 8)
        desired = max(0, int(desired))
        # Scale the corner radius for current UI scale
        desired = sp(desired)

        if bg_mode is None:
            bg_mode = getattr(self.settings, "bg_mode", "theme")
        if blur_radius is None:
            blur_radius = getattr(self.settings, "bg_blur_radius", 0)

        # 亚克力模式：使用 paintEvent 绘制完美圆角，直接返回用户设置值
        if bg_mode == "acrylic":
            return desired

        effect_enabled = bg_mode == "theme" and blur_radius > 0

        # Win11 特殊逻辑
        if is_win11() and effect_enabled:
            return self._get_win11_effective_radius(desired)

        return desired

    def _apply_win10_rounded_mask(self, margin: int, clip_w: int, clip_h: int, radius: int):
        logger.info(
            f"[MASK] 设置Win10遮罩: clip={clip_w}x{clip_h}, window={self.width()}x{self.height()}, margin={margin}, radius={radius}"
        )
        if is_win10():
            self.clearMask()
            self.update()
            return
        r = max(0, int(radius))
        if r <= 0:
            self.clearMask()
            return
        rect = QRectF(int(margin), int(margin), int(clip_w), int(clip_h))
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        logger.info("[MASK] 遮罩已应用")

    def _snapshot_effect_state(self):
        """收集当前效果相关参数快照，用于跳过无变化的 DWM 重建。"""
        s = getattr(self, "settings", None)
        if s is None:
            return None
        theme = getattr(s, "theme", "dark")
        bg_mode = getattr(s, "bg_mode", "theme")
        # 颜色滤镜参数（当前主题）
        return (
            bg_mode,
            getattr(s, "corner_radius", 8),
            getattr(s, "bg_alpha", 90),
            getattr(s, "bg_blur_radius", 0),
            theme,
            getattr(s, f"{theme}_black_point", 50),
            getattr(s, f"{theme}_white_point", 50),
            getattr(s, f"{theme}_mid_gamma", 50),
            getattr(s, f"{theme}_temperature", 50),
            getattr(s, f"{theme}_acrylic", 30),
            getattr(s, f"{theme}_bg_alpha_filter", 100),
            self.width(),
            self.height(),
        )

    def _update_window_effect(self):
        """更新窗口特效 (Acrylic / Blur)"""
        try:
            # 参数快照缓存：如果效果参数未变化则跳过 DWM 重建，
            # 避免 showEvent 等场景重复调用导致的视觉闪烁
            current_state = self._snapshot_effect_state()
            if current_state is not None and current_state == self._last_effect_state:
                logger.debug("[EFFECT] 参数未变化，跳过 DWM 重建")
                return

            bg_mode = getattr(self.settings, "bg_mode", "theme")
            desired_radius = getattr(self.settings, "corner_radius", 8)

            hwnd = int(self.winId())
            if not hwnd:
                return

            logger.debug(f"[EFFECT] 更新窗口效果: mode={bg_mode}, size={self.width()}x{self.height()}")

            if bg_mode == "acrylic":
                # ===== 亚克力模式：使用与配置窗口完全相同的磨砂玻璃效果 =====
                # 禁用旧的 DWM Blur
                if getattr(self, "_win10_dwm_blur_active", False):
                    self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                    self._win10_dwm_blur_active = False

                theme = getattr(self.settings, "theme", "dark")
                radius = max(0, int(desired_radius))
                # bg_alpha: 0-100 (0=全透明/最强磨砂, 100=不透明)
                bg_alpha = getattr(self.settings, "bg_alpha", 90)

                # 颜色分级后的底色
                from ui.styles.color_filter_overlay import compute_graded_tint

                bp = getattr(self.settings, f"{theme}_black_point", 50)
                wp = getattr(self.settings, f"{theme}_white_point", 50)
                mg = getattr(self.settings, f"{theme}_mid_gamma", 50)
                tp = getattr(self.settings, f"{theme}_temperature", 50)
                r_c, g_c, b_c = compute_graded_tint(theme, bp, wp, mg, tp)

                # 颜色滤镜的 Acrylic 和底色α 滑块
                cf_acrylic = getattr(self.settings, f"{theme}_acrylic", 30)
                cf_bg_alpha = getattr(self.settings, f"{theme}_bg_alpha_filter", 100)

                if is_win11():
                    # Win11: 结合 popup bg_alpha 和颜色滤镜滑块
                    base_from_bg = max(0, min(180, int(bg_alpha * 1.75)))
                    cf_alpha = max(5, min(int(cf_acrylic), 250))
                    cf_scale = max(0.05, min(int(cf_bg_alpha) / 100.0, 2.55))
                    dwm_alpha = max(5, min(int((base_from_bg + cf_alpha) / 2 * cf_scale), 250))
                    gradient_color = f"{dwm_alpha:02x}{r_c:02x}{g_c:02x}{b_c:02x}"
                    self.window_effect.set_acrylic(hwnd, gradient_color=gradient_color, enable=True, blur=True)
                    self.window_effect.set_round_corners(
                        hwnd, preference=self._get_win11_corner_preference(desired_radius)
                    )
                    self.window_effect.clear_window_region(hwnd)
                    self.clearMask()
                else:
                    # Win10: 只使用窗口区域裁剪，背景由 Qt 自绘。
                    w = self.width()
                    h = self.height()
                    logger.info(f"[REGION] Win10亚克力模式: window={w}x{h}, radius={radius}")
                    if w > 0 and h > 0:
                        self.window_effect.set_window_region(hwnd, w, h, radius)
                        logger.info("[REGION] 窗口区域已设置")
                    if is_win10():
                        self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                    else:
                        dwm_alpha = max(20, min(240, int(bg_alpha * 2.2)))
                        gradient_color = f"{dwm_alpha:02x}{r_c:02x}{g_c:02x}{b_c:02x}"
                        self.window_effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)
                        self.window_effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)

            else:
                # 其他模式禁用特效 (Theme / Image 模式)
                self.window_effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
                self._win10_dwm_blur_active = False
                self.window_effect.set_acrylic(hwnd, enable=False)
                self.window_effect.set_round_corners(hwnd, enable=False)
                self.window_effect.clear_window_region(hwnd)
                if hasattr(self, "_apply_search_mask"):
                    self._apply_search_mask()

            # 更新成功后保存参数快照
            self._last_effect_state = current_state

        except Exception as e:
            logger.error(f"更新窗口特效失败: {e}")


class PopupLayoutMixin:
    """Window setup, sizing, positioning, and resize/move events."""

    def _setup_window(self):
        """设置窗口属性"""
        apply_custom_window_chrome(self, kind="tool", topmost=True, translucent=True)
        self.setWindowOpacity(0)  # 初始透明度为 0
        try:
            self.setAttribute(QtCompat.WA_NoSystemBackground, True)
        except Exception as exc:
            logger.debug("设置WA_NoSystemBackground失败: %s", exc, exc_info=True)

        # 启用DPI感知，确保在不同缩放屏幕上正确显示
        try:
            self.setAttribute(QtCompat.WA_NativeWindow, True)
        except Exception as exc:
            logger.debug("设置WA_NativeWindow失败: %s", exc, exc_info=True)
        try:
            self.setFocusPolicy(QtCompat.StrongFocus)
            self.setAttribute(Qt.WA_InputMethodEnabled, True)
        except Exception as exc:
            logger.debug("设置焦点策略和输入法失败: %s", exc, exc_info=True)

    def _calculate_fixed_size(self, y_offset_override=None):
        """基于"常用"页面计算固定窗口大小"""
        # 使用配置的每列行数
        self.fixed_rows = getattr(self.settings, "popup_max_rows", 3)
        self.shadow_margin = 0
        self.cell_h = int(self.cell_size * 1.15)

        width = self.padding * 2 + self.cols * self.cell_size
        # 增加搜索框导致的Y偏移
        if y_offset_override is None:
            y_offset = self._body_y_offset() if hasattr(self, "_body_y_offset") else 0
        else:
            y_offset = int(y_offset_override)

        logger.debug(
            f"[SIZE] 计算窗口尺寸: y_offset={y_offset}, "
            f"search_reveal_progress={getattr(self, '_search_reveal_progress', 'N/A')}"
        )

        # theme/image 模式：mask 裁掉顶部34px，所有坐标需整体下移补偿
        self.content_height = self.padding + y_offset + self.fixed_rows * self.cell_h

        indicator_height = sp(16) if len(self.pages) > 1 else 0
        indicator_spacing = sp(4) if len(self.pages) > 1 else 0
        self.indicator_y = self.content_height + indicator_spacing

        dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
        self.dock_y = self.indicator_y + indicator_height

        height = self.content_height + indicator_spacing + indicator_height + dock_height + sp(6)

        total_width = width + self.shadow_margin * 2
        total_height = height + self.shadow_margin * 2

        self.setFixedSize(total_width, total_height)
        return total_width, total_height

    def _center_to(self, x: int, y: int, window_width: int = None, window_height: int = None):
        """定位窗口"""
        if window_width is None:
            window_width = self.width()
        if window_height is None:
            window_height = self.height()

        screen = QApplication.screenAt(QPoint(x, y))
        if not screen:
            screen = QApplication.primaryScreen()

        work_area = screen.availableGeometry()

        dpr = screen.devicePixelRatio()
        if dpr and dpr != 1.0:
            lx = int(x / dpr)
            ly = int(y / dpr)
        else:
            lx, ly = x, y

        align_mode = getattr(self.settings, "popup_align_mode", "mouse_center")

        if align_mode == "screen_center":
            left = work_area.center().x() - window_width // 2
            top = work_area.center().y() - window_height // 2
        elif align_mode == "bottom_right":
            left = work_area.right() - window_width - sp(10)
            top = work_area.bottom() - window_height - sp(10)
        elif align_mode == "mouse_top_left":
            left = lx
            top = ly
        else:  # mouse_center
            left = lx - window_width // 2
            top = ly - window_height // 2

        left = max(work_area.left() + sp(5), min(left, work_area.right() - window_width - sp(5)))
        top = max(work_area.top() + sp(5), min(top, work_area.bottom() - window_height - sp(5)))

        self.move(left, top)

    def resizeEvent(self, event):
        self._bg_cache = None
        self._cached_bg_path = None
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
        if not getattr(self, "_geometry_adjusting", False):
            QTimer.singleShot(0, self._update_window_effect)
        super().resizeEvent(event)

    def moveEvent(self, event):
        """窗口移动时更新特效，确保在新屏幕上正确显示"""
        try:
            if getattr(self, "_geometry_adjusting", False):
                super().moveEvent(event)
                return
            old_screen = QApplication.screenAt(event.oldPos()) if hasattr(event, "oldPos") else None
            new_screen = QApplication.screenAt(self.pos())

            if old_screen and new_screen and old_screen != new_screen:
                self._bg_cache = None
                self._last_bg_params = None
                logger.debug(f"屏幕切换，清空背景缓存: {old_screen.name()} -> {new_screen.name()}")
                QTimer.singleShot(50, self._update_window_effect)
            else:
                self._update_window_effect()
        except Exception as exc:
            logger.debug("处理窗口移动事件失败: %s", exc, exc_info=True)
        super().moveEvent(event)
