"""Shared log-style themed utility window chrome."""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging
import os
import sys
from typing import cast

from qt_compat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QIcon,
    QLabel,
    QListWidget,
    QPainter,
    QPainterPath,
    QPixmap,
    QPlainTextEdit,
    QPoint,
    QPushButton,
    QSize,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from runtime_paths import app_root
from ui.styles.design_tokens import border as token_border
from ui.styles.design_tokens import selection_bg_qss, selection_text_qss
from ui.styles.design_tokens import surface as token_surface
from ui.styles.l3_features import show_focus_ring as l3_show_focus_ring
from ui.styles.style import StyleSheet
from ui.styles.theme_controller import normalize_theme
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.font_manager import get_qfont, tune_font_rendering
from ui.utils.interruptible_animation import stop_named_animations
from ui.utils.pixel_snap import build_rounded_mask, make_cosmetic_pen
from ui.utils.ui_scale import scale_qss, sp, spf
from ui.utils.window_effect import (
    enable_acrylic_for_config_window,
    get_window_effect,
    is_win10,
    is_win11,
    paint_win10_rounded_surface,
)

logger = logging.getLogger(__name__)


class _ThemedToolWindowBase:
    """Reusable frameless shell shared by dialog and top-level widget windows."""

    def __init__(self, title: str, theme: str = "light", parent=None):
        super().__init__(parent)  # type: ignore[call-arg]
        self._theme = normalize_theme(theme, default="light")
        self._blur_applied = False
        self._drag_pos = None
        self.setWindowTitle(title)  # type: ignore[attr-defined]
        # Apply the frameless flags before opacity or any other property that
        # can force Qt to create the native HWND.  On Windows, creating the
        # handle first produces a short-lived default QDialog with a system
        # title bar before setWindowFlags() recreates it as frameless.
        apply_custom_window_chrome(self, kind="window", translucent=True)
        self.setWindowOpacity(0)  # type: ignore[attr-defined]
        self._load_window_icon()
        self._setup_shell(title)
        self._apply_theme()

    def _setup_shell(self, title: str):
        self.root_layout = QVBoxLayout(cast(QWidget, self))
        self.root_layout.setContentsMargins(sp(12), 0, 0, sp(12))
        self.root_layout.setSpacing(sp(6))

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(sp(6), 0, 0, 0)
        title_bar.setSpacing(sp(8))

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(sp(20), sp(20))
        self.icon_label.setStyleSheet("background: transparent;")
        self._load_title_icon()
        title_bar.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        self.title_label.setFont(get_qfont(14, 400))
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        self.close_btn_top = QPushButton("✕")
        self.close_btn_top.setFixedSize(sp(48), sp(32))
        self.close_btn_top.setCursor(QtCompat.PointingHandCursor)
        self.close_btn_top.clicked.connect(self.close)  # type: ignore[attr-defined]
        title_bar.addWidget(self.close_btn_top)
        self.root_layout.addLayout(title_bar)

        self.subtitle_label = QLabel("")
        self.subtitle_label.setVisible(False)
        self.root_layout.addWidget(self.subtitle_label)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, sp(4), 0)
        self.content_layout.setSpacing(sp(6))
        self.root_layout.addLayout(self.content_layout, 1)

        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 0, sp(4), 0)
        self.button_layout.setSpacing(sp(8))
        self.root_layout.addLayout(self.button_layout)

    def set_subtitle(self, text: str):
        self.subtitle_label.setText(text or "")
        self.subtitle_label.setVisible(bool(text))

    def set_theme(self, theme: str):
        self._theme = normalize_theme(theme, default="light")
        self._apply_theme()
        self._apply_content_theme()
        if self.isVisible():  # type: ignore[attr-defined]
            self._apply_blur_effect()

    def _apply_theme(self):
        theme = self._theme
        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
            text_secondary = "rgba(255, 255, 255, 0.5)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
            text_secondary = "rgba(60, 60, 67, 0.6)"

        self.setStyleSheet(scale_qss("QDialog { background: transparent; }"))
        self.title_label.setStyleSheet(
            scale_qss(
                f"""
            font-size: 14px; font-weight: 400;
            color: {text_primary};
            background: transparent;
        """
            )
        )
        self.title_label.setFont(get_qfont(14, 400))
        self.subtitle_label.setStyleSheet(
            scale_qss(
                f"""
            font-size: 11px;
            color: {text_secondary};
            background: transparent;
            padding-left: 6px;
        """
            )
        )
        self.close_btn_top.setStyleSheet(
            scale_qss(
                f"""
            QPushButton {{
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 4px;
                color: {text_primary};
                font-size: 13px;
                font-weight: 400;
                font-family: 'Segoe MDL2 Assets', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background: #E81123;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background: #C50F1F;
                color: #ffffff;
            }}
        """
            )
        )
        tune_font_rendering(self, recursive=True)
        self.title_label.setFont(get_qfont(14, 400))

    def _apply_content_theme(self):
        """Subclass hook for styling child widgets."""
        return

    def style_plain_text(self, widget: QPlainTextEdit):
        theme = self._theme
        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
        selection_bg = selection_bg_qss(theme)
        selection_text = selection_text_qss(theme)
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)
        widget.setStyleSheet(
            scale_qss(
                f"""
            QPlainTextEdit {{
                background: transparent;
                border: none; border-radius: 0;
                color: {text_primary};
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
        """
                + scrollbar_style
            )
        )
        self.style_scrollbars(widget)

    def style_list_widget(self, widget: QListWidget):
        self._style_list_widget(widget, compact=False)

    def style_compact_list_widget(self, widget: QListWidget):
        self._style_list_widget(widget, compact=True)

    def _style_list_widget(self, widget: QListWidget, compact: bool = False):
        theme = self._theme
        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
            item_hover = "rgba(255, 255, 255, 0.08)"
            border = "rgba(255, 255, 255, 0.12)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
            item_hover = "rgba(0, 0, 0, 0.04)"
            border = "rgba(0, 0, 0, 0.06)"
        item_selected = selection_bg_qss(theme)
        selected_text = selection_text_qss(theme)
        selected_border = "rgba(10, 132, 255, 0.42)" if theme == "dark" else "rgba(0, 122, 255, 0.22)"
        padding = "4px 7px" if compact else "8px 10px"
        radius = "4px" if compact else "6px"
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)
        widget.setStyleSheet(
            scale_qss(
                f"""
            QListWidget {{
                background: transparent;
                border: 1px solid {border};
                border-radius: 8px;
                color: {text_primary};
                padding: 6px;
                outline: none;
            }}
            QListWidget::item {{
                padding: {padding};
                border-radius: {radius};
                border: 1px solid transparent;
            }}
            QListWidget::item:hover {{
                background: {item_hover};
            }}
            QListWidget::item:selected {{
                background: {item_selected};
                color: {selected_text};
                border: 1px solid {selected_border};
            }}
        """
                + scrollbar_style
            )
        )
        self.style_scrollbars(widget)

    def style_scrollbars(self, widget):
        """Apply the same scrollbar style used by the log window."""
        scrollbar_style = StyleSheet.get_scrollbar_style(self._theme)
        for accessor in ("verticalScrollBar", "horizontalScrollBar"):
            try:
                scrollbar = getattr(widget, accessor)()
                scrollbar.setStyleSheet(scrollbar_style)
            except Exception as exc:
                logger.debug("设置滚动条样式失败: %s", exc, exc_info=True)

    def style_buttons(self, *buttons: QPushButton):
        theme = self._theme
        if theme == "dark":
            btn_bg = "rgba(255, 255, 255, 0.12)"
            btn_border = "rgba(255, 255, 255, 0.2)"
            btn_hover = "rgba(10, 132, 255, 0.8)"
            btn_text = "#ffffff"
            disabled = "rgba(255, 255, 255, 0.28)"
        else:
            btn_bg = "rgba(0, 0, 0, 0.03)"
            btn_border = "rgba(0, 0, 0, 0.05)"
            btn_hover = "rgba(0, 122, 255, 0.8)"
            btn_text = "#1c1c1e"
            disabled = "rgba(60, 60, 67, 0.35)"
        style = scale_qss(
            f"""
            QPushButton {{
                font-size: 11px;
                padding: 6px 10px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 6px;
                color: {btn_text};
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                color: white;
                border: 1px solid {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 90, 200, 0.9);
                color: white;
            }}
            QPushButton:disabled {{
                color: {disabled};
                background: transparent;
                border: 1px solid {btn_border};
            }}
        """
        )
        for button in buttons:
            button.setFixedHeight(sp(32))
            button.setCursor(QtCompat.PointingHandCursor)
            button.setStyleSheet(style)

    def _load_window_icon(self):
        try:
            for icon_path in self._possible_icon_paths():
                if icon_path and os.path.exists(icon_path):
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        return
        except Exception as exc:
            logger.debug("加载窗口图标失败: %s", exc, exc_info=True)

    def _load_title_icon(self):
        try:
            for icon_path in self._possible_icon_paths():
                if icon_path and os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        self.icon_label.setPixmap(
                            pixmap.scaled(
                                QSize(sp(20), sp(20)), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation
                            )
                        )
                        return
        except Exception as exc:
            logger.debug("加载标题图标失败: %s", exc, exc_info=True)

    @staticmethod
    def _possible_icon_paths():
        root_dir = str(app_root())
        return [
            os.path.join(root_dir, "assets", "app.ico"),
            os.path.join(root_dir, "app.ico"),
            os.path.join(sys._MEIPASS, "assets", "app.ico") if hasattr(sys, "_MEIPASS") else None,
        ]

    def _apply_blur_effect(self):
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()
            radius = 8
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                enable_acrylic_for_config_window(self, self._theme, blur_amount=10)
            else:
                enable_acrylic_for_config_window(self, self._theme, blur_amount=8, radius=radius)
            self._blur_applied = True
        except Exception as exc:
            logger.debug("应用模糊效果失败: %s", exc, exc_info=True)

    def paintEvent(self, event):  # noqa: paint_perf
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            radius = sp(8)
            if self._theme == "dark":
                bg = token_surface(self._theme, "bg_glass_dark_win10")
                border = token_border(self._theme, "subtle_dark")
            else:
                bg = token_surface(self._theme, "bg_glass_light_win10")
                border = token_border(self._theme, "subtle_light")

            if is_win10():
                paint_win10_rounded_surface(painter, self, bg, border, radius)
                return

            inset = spf(4.0)
            path = QPainterPath()
            path.addRoundedRect(
                inset,
                inset,
                self.width() - inset * 2,
                self.height() - inset * 2,
                radius,
                radius,
            )
            tint_color = QColor(bg)
            tint_color.setAlpha(min(tint_color.alpha(), 100))
            painter.fillPath(path, tint_color)

            pen_color = QColor(border)
            pen_color.setAlpha(min(pen_color.alpha(), 120))
            # 使用 make_cosmetic_pen 保证 1px 边框在 125%+ DPI 下不发胖
            painter.setPen(make_cosmetic_pen(pen_color, 1))
            painter.drawPath(path)

            # L3 §5.2 — Focus Ring: 键盘焦点时在 rounded 路径上画 1px 圆角高亮环
            try:
                from ui.styles.design_tokens import BorderScale

                if l3_show_focus_ring(getattr(self, "_settings", None)) and self.hasFocus():
                    ring_color = QColor(BorderScale.focus_dark) if self._theme == "dark" else QColor(BorderScale.focus)
                    ring_pen = make_cosmetic_pen(ring_color, 1)
                    painter.setPen(ring_pen)
                    painter.setBrush(QtCompat.NoBrush)
                    ring_path = QPainterPath()
                    ring_path.addRoundedRect(
                        spf(1.0),
                        spf(1.0),
                        self.width() - spf(2.0),
                        self.height() - spf(2.0),
                        sp(8),
                        sp(8),
                    )
                    painter.drawPath(ring_path)
            except Exception as exc:  # pragma: no cover
                logger.debug("L3 焦点环绘制失败: %s", exc, exc_info=True)
        finally:
            painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_window_mask()
        try:
            if not is_win11() and self._blur_applied:
                hwnd = int(self.winId())
                if hwnd:
                    effect = get_window_effect()
                    effect.set_window_region(hwnd, self.width(), self.height(), sp(12))
                    effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
        except Exception as exc:
            logger.debug("调整窗口区域失败: %s", exc, exc_info=True)

    def _apply_window_mask(self):
        """Set a rounded-rect window mask matching the painted surface.

        ``WA_TranslucentBackground`` makes Windows perform per-pixel hit testing
        on the backing store. The Win11 branch of :meth:`paintEvent` only fills
        the rounded body with ~40% alpha, and the ``setWindowOpacity`` fade-in
        can drop the effective alpha below the hit-test threshold, causing mouse
        events to fall through to whatever sits beneath the window. Pinning an
        explicit rounded-rect mask to the painted area makes the body opaque for
        hit testing regardless of per-pixel alpha or opacity animation, while
        still leaving the four corners click-through (which is the intended
        behaviour for a rounded window).
        """
        try:
            width = self.width()
            height = self.height()
            if width <= 0 or height <= 0:
                return
            radius = sp(8)
            self.setMask(build_rounded_mask(width, height, radius))
        except Exception as exc:
            logger.debug("应用窗口遮罩失败: %s", exc, exc_info=True)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_window_mask()
        from qt_compat import QTimer

        QTimer.singleShot(10, self._apply_blur_effect)
        self._start_show_animation()

    def _start_show_animation(self):
        stop_named_animations(self, "anim_group", "opacity_anim", "pos_anim")
        start_opacity = max(0.0, min(1.0, float(self.windowOpacity())))
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(start_opacity)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)
        self.opacity_anim.finished.connect(self.opacity_anim.deleteLater)

        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        start_pos = self.pos() if start_opacity > 0.001 else QPoint(pos.x(), pos.y() + sp(20))
        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(pos)
        self.pos_anim.setEasingCurve(QtCompat.OutCubic)
        self.pos_anim.finished.connect(self.pos_anim.deleteLater)

        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.finished.connect(self.anim_group.deleteLater)
        self.anim_group.start()

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._drag_pos = (
                (event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos())
                if pos.y() <= sp(36)
                else None
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.move(self.pos() + new_pos - self._drag_pos)
            self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class ThemedToolWindow(_ThemedToolWindowBase, QDialog):
    """Frameless themed shell for utility windows."""
