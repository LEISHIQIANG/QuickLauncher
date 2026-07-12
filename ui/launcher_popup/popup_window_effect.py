"""Window effects (Win10/Win11 round corners, acrylic) and layout helpers for LauncherPopup."""

import logging

from qt_compat import (
    QApplication,
    QFont,
    QFontMetrics,
    QPainterPath,
    QRectF,
    QRegion,
    Qt,
    QtCompat,
    QTimer,
)
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.font_manager import get_font_family
from ui.utils.ui_scale import font_px, sp
from ui.utils.window_effect import install_win10_window_shadow, is_win10, is_win11, remove_win10_window_shadow

logger = logging.getLogger(__name__)


class PopupWindowEffectMixin:
    """Win10/Win11 window effects: corner radius, acrylic, blur."""

    def _get_win11_corner_preference(self, desired_radius: int):
        r = max(0, int(desired_radius))
        if r <= 0:
            return self.window_effect.DWMWCP_DONOTROUND  # type: ignore[attr-defined]
        if r <= 6:
            return self.window_effect.DWMWCP_ROUNDSMALL  # type: ignore[attr-defined]
        return self.window_effect.DWMWCP_ROUND  # type: ignore[attr-defined]

    def _get_win11_effective_radius(self, desired_radius: int) -> int:
        r = max(0, int(desired_radius))
        if r <= 0:
            return 0
        if r <= 6:
            return 4
        return 8

    def _get_paint_corner_radius(self, bg_mode=None, blur_radius=None) -> int:
        desired = getattr(self.settings, "corner_radius", 8)  # type: ignore[attr-defined]
        desired = max(0, int(desired))
        # Scale the corner radius for current UI scale
        desired = sp(desired)

        if bg_mode is None:
            bg_mode = getattr(self.settings, "bg_mode", "theme")  # type: ignore[attr-defined]
        if blur_radius is None:
            blur_radius = getattr(self.settings, "bg_blur_radius", 0)  # type: ignore[attr-defined]

        # 亚克力模式：使用 paintEvent 绘制完美圆角，直接返回用户设置值
        if bg_mode == "acrylic":
            return desired

        effect_enabled = bg_mode == "theme" and blur_radius > 0

        # Win11 特殊逻辑
        if is_win11() and effect_enabled:
            return self._get_win11_effective_radius(desired)

        return desired

    def _apply_rounded_mask(self, margin: int, clip_w: int, clip_h: int, radius: int):
        """Apply a rounded-rect window mask for hit-test / clipping.

        On Win10, Qt's :func:`paint_win10_rounded_surface` handles
        anti-aliased corners via per-pixel alpha, so we clear any GDI
        mask to avoid 1-bit jagged edges. On Win11, DWM native rounding
        is preferred, but a QRegion mask is still used as a fallback.
        """
        if is_win10():
            self.clearMask()  # type: ignore[attr-defined]
            self.update()  # type: ignore[attr-defined]
            return
        r = max(0, int(radius))
        if r <= 0:
            self.clearMask()  # type: ignore[attr-defined]
            return
        rect = QRectF(int(margin), int(margin), int(clip_w), int(clip_h))
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))  # type: ignore[attr-defined]

    def _snapshot_effect_state(self):
        """收集当前效果相关参数快照，用于跳过无变化的 DWM 重建。"""
        s = getattr(self, "settings", None)
        if s is None:
            return None
        try:
            hwnd = int(self.winId())
        except Exception:
            hwnd = 0
        screen_state = None
        try:
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.screenAt(self.pos())
            if screen is not None:
                geometry = screen.geometry()
                available = screen.availableGeometry()
                screen_state = (
                    screen.name(),
                    round(float(screen.devicePixelRatio()), 3),
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                    available.x(),
                    available.y(),
                    available.width(),
                    available.height(),
                )
        except Exception as exc:
            logger.debug("采集窗口特效屏幕状态失败: %s", exc, exc_info=True)
        theme = getattr(s, "theme", "dark")
        bg_mode = getattr(s, "bg_mode", "theme")
        # 颜色滤镜参数（当前主题）
        return (
            hwnd,
            bool(is_win10()),
            bool(is_win11()),
            screen_state,
            bg_mode,
            getattr(s, "corner_radius", 8),
            getattr(s, "bg_alpha", 90),
            getattr(s, "bg_blur_radius", 0),
            getattr(s, "shadow_size", 0),
            getattr(s, "shadow_distance", 0),
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

    def _schedule_window_effect_update(self, delay_ms: int = 0):
        delay_ms = max(0, int(delay_ms))
        timer = getattr(self, "_window_effect_update_timer", None)
        if timer is None:
            timer = QTimer(self)  # type: ignore[unused-ignore, arg-type]
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_scheduled_window_effect_update)
            self._window_effect_update_timer = timer

        if timer.isActive():
            current_delay = int(getattr(self, "_window_effect_update_delay_ms", delay_ms) or 0)
            if delay_ms >= current_delay:
                return
            timer.stop()

        self._window_effect_update_delay_ms = delay_ms
        timer.start(delay_ms)

    def _run_scheduled_window_effect_update(self):
        self._window_effect_update_delay_ms = None
        self._update_window_effect()

    def _install_win10_popup_shadow(self, radius: int):
        if self._uses_win10_internal_popup_shadow():
            remove_win10_window_shadow(self)
            return True
        settings = getattr(self, "settings", None)
        shadow_size = getattr(settings, "shadow_size", 0)
        shadow_distance = getattr(settings, "shadow_distance", 0)
        return install_win10_window_shadow(
            self,
            radius,
            shadow_size=shadow_size,
            shadow_distance=shadow_distance,
        )

    def _uses_win10_internal_popup_shadow(self) -> bool:
        return bool(is_win10())

    def _update_window_effect(self):
        """更新窗口特效 (Acrylic / Blur)"""
        try:
            bg_mode = getattr(self.settings, "bg_mode", "theme")
            desired_radius = getattr(self.settings, "corner_radius", 8)
            blur_radius = getattr(self.settings, "bg_blur_radius", 0)
            paint_radius = self._get_paint_corner_radius(bg_mode, blur_radius)

            # 参数快照缓存：如果效果参数未变化则跳过 DWM 重建，
            # 避免 showEvent 等场景重复调用导致的视觉闪烁
            current_state = self._snapshot_effect_state()
            if current_state is not None and current_state == getattr(self, "_last_effect_state", None):
                if is_win10():
                    self._install_win10_popup_shadow(paint_radius)
                logger.debug("[EFFECT] 参数未变化，跳过 DWM 重建")
                return

            hwnd = int(self.winId())
            if not hwnd:
                return

            logger.debug(f"[EFFECT] 更新窗口效果: mode={bg_mode}, size={self.width()}x{self.height()}")
            if is_win10():
                self._install_win10_popup_shadow(paint_radius)
            else:
                self.window_effect.enable_window_shadow(hwnd, paint_radius)

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
                if is_win11():
                    self.window_effect.set_round_corners(
                        hwnd, preference=self._get_win11_corner_preference(desired_radius)
                    )
                else:
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

    def _update_grid_text_metrics(self) -> None:
        """Keep the smaller single-line label font and row height in sync."""
        label_font = self.__dict__.get("_label_font")
        if label_font is not None:
            raw_size = max(9, int(self.settings.icon_size * 0.28))  # type: ignore[attr-defined]
            label_font.setFamily(get_font_family())
            label_font.setPixelSize(font_px(raw_size))
            label_font.setWeight(QFont.Weight.Medium)
            label_font.setStyleHint(QFont.StyleHint.SansSerif)
            label_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            label_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            label_font.setKerning(True)
        self.cell_h = int(self.cell_size * 1.15)  # type: ignore[attr-defined]

    def _dock_display_rows(self, visible_count: int | None = None, cols: int | None = None) -> int:
        if not self.dock_items:  # type: ignore[attr-defined]
            return 0

        max_rows = max(1, int(getattr(self.settings, "dock_height_mode", 1) or 1))  # type: ignore[attr-defined]
        cols = max(1, int(cols if cols is not None else getattr(self, "cols", 1) or 1))
        if visible_count is None:
            visible_count = len(self.dock_items)  # type: ignore[attr-defined]
            if max_rows == 1:
                visible_count = min(visible_count, cols)
        visible_count = max(0, int(visible_count or 0))
        if visible_count <= 0:
            return 0

        actual_rows = (visible_count + cols - 1) // cols
        return min(max(1, actual_rows), max_rows)

    def _dock_background_top_gap(self) -> int:
        return max(1, sp(6))

    def _dock_outer_bottom_gap(self) -> int:
        return sp(6)

    def _dock_background_height(self) -> int:
        total_h = int(getattr(self, "dock_height", 0) or 0) + self._dock_outer_bottom_gap()
        return max(0, total_h - self._dock_background_top_gap() * 2)

    def _dock_shows_text(self, display_rows: int) -> bool:
        return display_rows >= 2

    def _get_dock_row_stride(self, display_rows: int) -> int:
        card_pad = sp(4)
        card_size = self.icon_size + card_pad * 2  # type: ignore[attr-defined]
        if self._dock_shows_text(display_rows):
            if hasattr(self, "_label_font") and self._label_font:
                fm = QFontMetrics(self._label_font)
            else:
                fm = QFontMetrics(QFont())
            text_h = fm.height()
            text_spacing = sp(1)
            row_height = card_size + text_spacing + text_h
            return row_height + sp(6)  # type: ignore[no-any-return]
        else:
            return self.icon_size + sp(6)  # type: ignore[attr-defined, no-any-return]

    def _dock_card_block_height(self, display_rows: int) -> int:
        rows = max(1, int(display_rows or 1))
        card_pad = sp(4)
        card_size = self.icon_size + card_pad * 2  # type: ignore[attr-defined]

        if self._dock_shows_text(rows):
            if hasattr(self, "_label_font") and self._label_font:
                fm = QFontMetrics(self._label_font)
            else:
                fm = QFontMetrics(QFont())
            text_h = fm.height()
            text_spacing = sp(1)
            row_height = card_size + text_spacing + text_h
        else:
            row_height = card_size

        dock_row_stride = self._get_dock_row_stride(rows)
        return row_height + (rows - 1) * dock_row_stride  # type: ignore[no-any-return]

    def _dock_first_icon_y(self, display_rows: int | None = None) -> int:
        rows = self._dock_display_rows() if display_rows is None else max(1, int(display_rows or 1))
        card_pad = sp(4)
        bg_y = int(getattr(self, "dock_y", 0) or 0) + self._dock_background_top_gap()
        block_h = self._dock_card_block_height(rows)
        bg_h = self._dock_background_height()
        inner_top = max(card_pad, (bg_h - block_h) // 2)
        return bg_y + inner_top + card_pad

    def _calculate_dock_height(self) -> int:
        """Return Dock height with enough room for the shared icon card frame."""
        dock_enabled = getattr(self.settings, "dock_enabled", True)  # type: ignore[attr-defined]
        if not (dock_enabled and self.dock_items):  # type: ignore[attr-defined]
            return 0

        display_rows = self._dock_display_rows()
        if display_rows <= 0:
            return 0
        return self._dock_card_block_height(display_rows) + sp(12)

    def _shadow_dpi_scale(self) -> float:
        """Return the per-monitor DPI scale for shadow metrics.

        Mirrors :meth:`_Win10ShadowWindow._shadow_metrics` so the
        internal content padding matches the actual companion shadow
        window, avoiding double-scaling when the global UI scale
        (:func:`sp`) differs from the monitor's logical DPI.
        """
        try:
            handle = self.windowHandle()  # type: ignore[attr-defined]
            if handle is not None:
                screen = handle.screen()
                if screen is not None:
                    return max(1.0, float(screen.logicalDotsPerInchX()) / 96.0)
        except Exception:
            logger.debug("windowHandle/screen DPI query failed", exc_info=True)
        try:
            from qt_compat import QApplication

            screens = QApplication.screens() or []
            if screens:
                return max(1.0, float(screens[0].logicalDotsPerInchX()) / 96.0)
        except Exception:
            logger.debug("QApplication.screens DPI query failed", exc_info=True)
        return 1.0

    def _win10_internal_shadow_metrics(self) -> tuple[int, int, int]:
        """Shadow metrics for internal layout, matching the companion shadow window.

        Uses the same per-monitor DPI scaling as
        :class:`_Win10ShadowWindow` instead of the global ``sp()`` scale.
        This prevents the left/right content margins from growing
        disproportionately at higher UI zoom levels (the companion
        shadow already handles DPI scaling independently).
        """
        if not self._uses_win10_internal_popup_shadow():  # type: ignore[attr-defined]
            return 0, 0, 0
        settings = getattr(self, "settings", None)
        raw_size = getattr(settings, "shadow_size", 0)
        raw_distance = getattr(settings, "shadow_distance", 0)
        try:
            shadow_size = int(raw_size)
        except (TypeError, ValueError):
            shadow_size = 0
        try:
            shadow_distance = int(raw_distance)
        except (TypeError, ValueError):
            shadow_distance = 0

        dpi_scale = self._shadow_dpi_scale()

        shadow_size_px = max(0, int(round((shadow_size if shadow_size > 0 else 14) * dpi_scale)))
        shadow_distance_px = max(0, int(round((shadow_distance if shadow_distance > 0 else 2) * dpi_scale)))
        margin = max(0, shadow_size_px + max(1, int(round(2 * dpi_scale))))
        return shadow_size_px, shadow_distance_px, margin

    def _setup_window(self):
        """设置窗口属性"""
        apply_custom_window_chrome(
            self,
            kind="tool",
            topmost=True,
            translucent=True,
            no_shadow=self._uses_win10_internal_popup_shadow(),
        )
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
        self.fixed_rows = getattr(self.settings, "popup_max_rows", 8)
        self.shadow_size_px, self.shadow_distance_px, self.shadow_margin = self._win10_internal_shadow_metrics()
        base_padding = int(self.__dict__.get("_base_padding", sp(8)) or sp(8))
        self.padding = base_padding + int(self.shadow_margin)
        self._update_grid_text_metrics()

        width = self.padding * 2 + self.cols * self.cell_size
        # 顶部标题/搜索栏始终占用固定高度。
        if y_offset_override is None:
            y_offset = self._body_y_offset() if hasattr(self, "_body_y_offset") else 0
        else:
            y_offset = int(y_offset_override)

        logger.debug(
            f"[SIZE] 计算窗口尺寸: y_offset={y_offset}, "
            f"search_reveal_progress={self.__dict__.get('_search_reveal_progress', 'N/A')}"
        )

        # theme/image 模式：mask 裁掉顶部34px，所有坐标需整体下移补偿
        self.content_height = self.padding + y_offset + self.fixed_rows * self.cell_h

        indicator_height = sp(16) if len(self.pages) > 1 else 0
        indicator_spacing = sp(4) if len(self.pages) > 1 else 0
        self.indicator_y = self.content_height + indicator_spacing

        dock_height = self.dock_height if (self.dock_items and self.dock_height > 0) else 0
        self.dock_y = self.indicator_y + indicator_height

        height = (
            self.content_height + indicator_spacing + indicator_height + dock_height + self._dock_outer_bottom_gap()
        )

        total_width = width
        total_height = height + self.shadow_margin

        self.setFixedSize(total_width, total_height)
        return total_width, total_height

    def _center_to(self, x: int, y: int, window_width: int = None, window_height: int = None):  # type: ignore[assignment]
        """定位窗口并返回计算出的 ``(left, top)``。

        ``x, y`` 是"项目坐标"——在本项目 ``QT_AUTO_SCREEN_SCALE_FACTOR=0`` +
        ``PerMonitorV2`` 配置下，``QScreen.geometry()`` 返回物理像素，
        ``devicePixelRatio()`` 恒为 1.0；所以这里直接使用 ``x, y`` 即可，
        不再做任何二次缩放（历史上曾经有 ``if dpr != 1.0: x/dpr`` 的死代码分支，
        已删除以避免误导）。

        **多屏边界处理**（修复跨屏显示 bug）：
        使用 :func:`ui.utils.coordinate_utils.pick_best_screen_for_popup` 选
        锚定屏幕——当鼠标在多屏交界处时，``QApplication.screenAt`` 可能因边界
        歧义返回"错"的屏幕；该函数会按"screenAt → geometry contains → 重叠
        面积最大"三级降级重选，确保弹窗能完整落在某一块屏幕的 ``availableGeometry``
        内。

        **最小边距**：边界裁剪使用 ``sp(4)``（仅 2px）作为最小安全距离，
        不再使用过大的 ``sp(20)``——DWM 阴影溢出由 Windows 自身控制，
        用户期望弹窗紧贴屏幕边缘而非保持大间距。

        Returns:
            ``(left, top)`` 计算出的窗口左上角坐标；调用方在 ``SetWindowPos``
            时应使用此返回值，**不要**使用原始 ``(x, y)`` 鼠标位置——
            否则 HWND 会先被定位到鼠标点（top-left 在鼠标处），
            再被 ``_center_to`` 纠正，造成多屏边界处短暂的"弹窗跨屏"闪烁。
        """
        if window_width is None:
            window_width = self.width()
        if window_height is None:
            window_height = self.height()

        from ui.utils.coordinate_utils import pick_best_screen_for_popup

        # 最小边界安全距离：sp(4) ≈ 2px（@ 100% scale）
        # 用户偏好弹窗紧贴屏幕边缘，不再使用 sp(20) 那种大间距
        edge_inset = sp(2)
        screen = pick_best_screen_for_popup(
            int(x),
            int(y),
            int(window_width),
            int(window_height),
            margin=edge_inset,
        )
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
            return None  # 没有可用屏幕时直接放弃（防御性兜底）

        work_area = screen.availableGeometry()  # type: ignore[unused-ignore, union-attr]

        lx, ly = x, y

        align_mode = getattr(self.settings, "popup_align_mode", "mouse_center")  # type: ignore[attr-defined]

        if align_mode == "screen_center":
            left = work_area.center().x() - window_width // 2
            top = work_area.center().y() - window_height // 2
        elif align_mode == "bottom_right":
            # bottom_right 模式保留稍大的 10px corner inset。
            left = work_area.right() - window_width - sp(12)
            top = work_area.bottom() - window_height - sp(12)
        elif align_mode == "mouse_top_left":
            left = lx
            top = ly
        else:  # mouse_center
            left = lx - window_width // 2
            top = ly - window_height // 2

        # 严格约束到单块屏幕：使用统一工具函数防止窗口溢出
        from ui.utils.coordinate_utils import clamp_window_to_screen

        left, top = clamp_window_to_screen(
            left,
            top,
            window_width,
            window_height,
            work_area,
            margin=edge_inset,
        )

        self.move(left, top)  # type: ignore[attr-defined]
        return (int(left), int(top))

    def resizeEvent(self, event):
        self._bg_cache = None
        self._cached_bg_path = None
        overlay = getattr(self, "_icon_flash_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
        if not getattr(self, "_geometry_adjusting", False):
            self._schedule_window_effect_update(0)
        glass_renderer = getattr(self, "_glass_renderer", None)
        if glass_renderer is not None and glass_renderer.active:
            glass_renderer.configure()
            glass_renderer.sync_geometry()
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
                self._schedule_window_effect_update(50)
            else:
                self._schedule_window_effect_update(0)
            glass_renderer = getattr(self, "_glass_renderer", None)
            if glass_renderer is not None and glass_renderer.active:
                glass_renderer.sync_geometry()
        except Exception as exc:
            logger.debug("处理窗口移动事件失败: %s", exc, exc_info=True)
        super().moveEvent(event)
