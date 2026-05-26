"""Shared log-style themed utility window chrome."""

from __future__ import annotations

import os
import sys

from qt_compat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QIcon,
    QLabel,
    QListWidget,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPlainTextEdit,
    QPoint,
    QPushButton,
    QSize,
    Qt,
    QtCompat,
    QVBoxLayout,
)
from ui.styles.style import StyleSheet
from ui.utils.window_effect import enable_acrylic_for_config_window, get_window_effect, is_win10, is_win11


class ThemedToolWindow(QDialog):
    """Reusable frameless log-window style shell for utility dialogs."""

    def __init__(self, title: str, theme: str = "light", parent=None):
        super().__init__(parent)
        self._theme = theme or "light"
        self._blur_applied = False
        self._drag_pos = None
        self.setWindowTitle(title)
        self.setWindowOpacity(0)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._load_window_icon()
        self._setup_shell(title)
        self._apply_theme()

    def _setup_shell(self, title: str):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(12, 0, 0, 12)
        self.root_layout.setSpacing(6)

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(6, 0, 0, 0)
        title_bar.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setStyleSheet("background: transparent;")
        self._load_title_icon()
        title_bar.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        self.close_btn_top = QPushButton("✕")
        self.close_btn_top.setFixedSize(46, 32)
        self.close_btn_top.setCursor(QtCompat.PointingHandCursor)
        self.close_btn_top.clicked.connect(self.close)
        title_bar.addWidget(self.close_btn_top)
        self.root_layout.addLayout(title_bar)

        self.subtitle_label = QLabel("")
        self.subtitle_label.setVisible(False)
        self.root_layout.addWidget(self.subtitle_label)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(6)
        self.root_layout.addLayout(self.content_layout, 1)

        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 0, 4, 0)
        self.button_layout.setSpacing(8)
        self.root_layout.addLayout(self.button_layout)

    def set_subtitle(self, text: str):
        self.subtitle_label.setText(text or "")
        self.subtitle_label.setVisible(bool(text))

    def set_theme(self, theme: str):
        self._theme = theme or "light"
        self._apply_theme()
        self._apply_content_theme()
        if self.isVisible():
            self._apply_blur_effect()

    def _apply_theme(self):
        theme = self._theme
        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
            text_secondary = "rgba(255, 255, 255, 0.5)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
            text_secondary = "rgba(60, 60, 67, 0.6)"

        self.setStyleSheet("QDialog { background: transparent; }")
        self.title_label.setStyleSheet(f"""
            font-size: 14px; font-weight: 500;
            color: {text_primary};
            background: transparent;
        """)
        self.subtitle_label.setStyleSheet(f"""
            font-size: 11px;
            color: {text_secondary};
            background: transparent;
            padding-left: 6px;
        """)
        self.close_btn_top.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
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
        """)

    def _apply_content_theme(self):
        """Subclass hook for styling child widgets."""
        return

    def style_plain_text(self, widget: QPlainTextEdit):
        theme = self._theme
        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)
        widget.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {text_primary};
                selection-background-color: rgba(10, 132, 255, 0.45);
            }}
        """
            + scrollbar_style
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
            item_selected = "rgba(10, 132, 255, 0.62)"
            selected_text = "#ffffff"
            border = "rgba(255, 255, 255, 0.12)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
            item_hover = "rgba(0, 0, 0, 0.04)"
            item_selected = "rgba(0, 122, 255, 0.72)"
            selected_text = "#ffffff"
            border = "rgba(0, 0, 0, 0.06)"
        padding = "4px 7px" if compact else "8px 10px"
        radius = "4px" if compact else "6px"
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)
        widget.setStyleSheet(
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
            }}
            QListWidget::item:hover {{
                background: {item_hover};
            }}
            QListWidget::item:selected {{
                background: {item_selected};
                color: {selected_text};
            }}
        """
            + scrollbar_style
        )
        self.style_scrollbars(widget)

    def style_scrollbars(self, widget):
        """Apply the same scrollbar style used by the log window."""
        scrollbar_style = StyleSheet.get_scrollbar_style(self._theme)
        for accessor in ("verticalScrollBar", "horizontalScrollBar"):
            try:
                scrollbar = getattr(widget, accessor)()
                scrollbar.setStyleSheet(scrollbar_style)
            except Exception:
                pass

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
        style = f"""
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
        for button in buttons:
            button.setFixedHeight(30)
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
        except Exception:
            pass

    def _load_title_icon(self):
        try:
            for icon_path in self._possible_icon_paths():
                if icon_path and os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        self.icon_label.setPixmap(
                            pixmap.scaled(QSize(20, 20), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                        )
                        return
        except Exception:
            pass

    @staticmethod
    def _possible_icon_paths():
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
            radius = 8 if is_win11() else 12
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                enable_acrylic_for_config_window(self, self._theme, blur_amount=10)
            else:
                enable_acrylic_for_config_window(self, self._theme, blur_amount=8, radius=radius)
            self._blur_applied = True
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)
        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        radius = 8 if is_win11() else 12
        inset = 1.0 if is_win10() else 0.5
        if self._theme == "dark":
            bg = QColor(28, 28, 30, 180)
            border = QColor(190, 190, 197, 60)
        else:
            bg = QColor(242, 242, 247, 160)
            border = QColor(229, 229, 234, 150)

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
        tint_color.setAlpha(min(tint_color.alpha(), 150 if is_win10() else 100))
        painter.fillPath(path, tint_color)

        pen_color = QColor(border)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1.0))
        painter.drawPath(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            if not is_win11() and self._blur_applied:
                hwnd = int(self.winId())
                if hwnd:
                    effect = get_window_effect()
                    effect.set_window_region(hwnd, self.width(), self.height(), 12)
                    effect.set_dwm_blur_behind(hwnd, self.width(), self.height(), 12, enable=True)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        from qt_compat import QTimer

        QTimer.singleShot(10, self._apply_blur_effect)
        self._start_show_animation()

    def _start_show_animation(self):
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        self.pos_anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
        self.pos_anim.setEndValue(pos)
        self.pos_anim.setEasingCurve(QtCompat.OutCubic)

        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.start()

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._drag_pos = (
                (event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos())
                if pos.y() <= 36
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
