"""Custom title-bar widget for the configuration window.

Extracted from :mod:`ui.config_window.main_window` as part of the
P1-06 file-split pass.  Hosts two small widgets used at the top of
the rounded configuration window:

* :class:`DotWidget` — small coloured dot used for status indicators.
* :class:`TitleBar` — frameless title bar with back / settings /
  update buttons and drag-to-move support.
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging
import os

from core import APP_VERSION
from core.i18n import tr
from qt_compat import (
    QColor,
    QHBoxLayout,
    QIcon,
    QLabel,
    QPainter,
    QPushButton,
    QSize,
    QtCompat,
    QWidget,
    pyqtSignal,
)
from runtime_paths import app_root
from ui.utils.ui_scale import scale_qss, sp

logger = logging.getLogger(__name__)


class DotWidget(QWidget):
    def __init__(self, color: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(sp(16))
        self._color = QColor(color)
        self.setToolTip(tooltip)

    def paintEvent(self, event):  # noqa: paint_perf
        p = QPainter(self)
        p.setRenderHint(QtCompat.Antialiasing)
        p.setRenderHint(QtCompat.HighQualityAntialiasing)
        p.setPen(QtCompat.NoPen)
        p.setBrush(self._color)
        cy = self.height() // 2 + 1
        p.drawEllipse(sp(3), cy - sp(4), sp(8), sp(8))
        p.end()


class TitleBar(QWidget):
    """自定义标题栏"""

    back_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._drag_pos = None
        self._in_settings_mode = False
        self._app_icon_path = None

        self.setFixedHeight(sp(36))
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp(8), 0, sp(1), 0)
        layout.setSpacing(sp(4))

        # 返回按钮 (默认隐藏)
        self.back_btn = QPushButton("‹")
        self.back_btn.setFixedSize(sp(32), sp(32))
        self.back_btn.setCursor(QtCompat.PointingHandCursor)
        self.back_btn.clicked.connect(self._on_back)
        self.back_btn.setVisible(False)
        self.back_btn.setStyleSheet(
            scale_qss(
                """
            QPushButton {
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 6px;
                font-size: 24px;
                font-weight: normal;
                color: #8e8e93;
                padding-bottom: 8px;
                margin-top: 2px;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.1);
                color: #007aff;
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.18);
                color: #006fd6;
            }
        """
            )
        )
        layout.addWidget(self.back_btn)

        # 图标 (默认显示)
        icon_size = sp(24)
        base_dir = str(app_root())
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setCursor(QtCompat.PointingHandCursor)
        self.icon_label.mousePressEvent = self._on_update_click
        self.icon_label.setStyleSheet("background: transparent;")

        try:
            # 优先查找 assets 目录
            icon_path = os.path.join(base_dir, "assets", "app.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_dir, "app.ico")

            if os.path.exists(icon_path):
                self._app_icon_path = icon_path
                if self.parent_window:
                    self.parent_window.setWindowIcon(QIcon(icon_path))

                pixmap = QIcon(icon_path).pixmap(icon_size, icon_size)
                if pixmap and not pixmap.isNull():
                    self.icon_label.setPixmap(
                        pixmap.scaled(icon_size, icon_size, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                    )
        except Exception as exc:
            logger.debug("加载窗口图标失败: %s", exc, exc_info=True)
        layout.addWidget(self.icon_label, alignment=QtCompat.AlignVCenter)
        layout.addSpacing(sp(6))

        # 标题
        self.title_label = QLabel(f"QuickLauncher {APP_VERSION}")
        self.title_label.setCursor(QtCompat.PointingHandCursor)
        self.title_label.mousePressEvent = self._on_update_click
        self.title_label.setStyleSheet(scale_qss("font-size: 13px; font-weight: 400; background: transparent;"))
        self.title_label.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # 设置按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(sp(32), sp(32))
        self._settings_icon_path = None

        # 尝试加载设置图标
        try:
            setting_icon_path = os.path.join(base_dir, "assets", "setting.ico")
            if not os.path.exists(setting_icon_path):
                setting_icon_path = os.path.join(base_dir, "setting.ico")

            if os.path.exists(setting_icon_path):
                self._settings_icon_path = setting_icon_path
                self.settings_btn.setIcon(QIcon(setting_icon_path))
                self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
            else:
                self.settings_btn.setText("⚙")
        except Exception as exc:
            logger.debug("加载设置图标失败: %s", exc, exc_info=True)
            self.settings_btn.setText("⚙")

        self.settings_btn.setCursor(QtCompat.PointingHandCursor)
        self.settings_btn.clicked.connect(self._on_settings)

        self.settings_btn.setStyleSheet(
            scale_qss(
                """
            QPushButton {
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 4px;
                font-size: 16px;
                color: #aaaaaa;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.1);
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.18);
                color: #ffffff;
            }
        """
            )
        )
        layout.addWidget(self.settings_btn)

        # 关闭按钮
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(sp(32), sp(32))
        self.close_btn.setCursor(QtCompat.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_close)
        self.close_btn.setStyleSheet(
            scale_qss(
                """
            QPushButton {
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 6px;
                font-size: 18px;
                color: #aaaaaa;
            }
            QPushButton:hover {
                background-color: #e81123;
                color: white;
            }
            QPushButton:pressed {
                background-color: #c50f1f;
                color: white;
            }
        """
            )
        )
        layout.addWidget(self.close_btn)

    def set_theme(self, theme: str):
        """根据主题设置文字和按钮颜色"""
        self._theme = theme
        if theme == "dark":
            text_color = "#ffffff"
            subtext_color = "#aaaaaa"
            btn_hover_bg = "rgba(255, 255, 255, 0.1)"
        else:
            text_color = "#1c1c1e"
            subtext_color = "#555555"
            btn_hover_bg = "rgba(0, 0, 0, 0.05)"

        self.title_label.setStyleSheet(
            scale_qss(f"font-size: 13px; font-weight: 400; background: transparent; color: {text_color};")
        )

        # 更新按钮样式
        btn_base_style = scale_qss(
            f"""
            QPushButton {{
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 6px;
                color: {subtext_color};
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
                color: {text_color};
            }}
            QPushButton:pressed {{
                background-color: rgba(128, 128, 128, 0.18);
                color: {text_color};
            }}
        """
        )

        self.back_btn.setStyleSheet(btn_base_style + scale_qss("QPushButton { font-size: 24px; padding-bottom: 8px; }"))
        self.settings_btn.setStyleSheet(btn_base_style + scale_qss("QPushButton { font-size: 18px; }"))

        # 关闭按钮特殊处理 hover 颜色
        self.close_btn.setStyleSheet(
            scale_qss(
                f"""
            QPushButton {{
                background: transparent;
                border: none; border-radius: 0;
                border-radius: 6px;
                font-size: 18px;
                color: {subtext_color};
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: #e81123;
                color: white;
            }}
            QPushButton:pressed {{
                background-color: #c50f1f;
                color: white;
            }}
        """
            )
        )

        if not self._settings_icon_path:
            return

        try:
            from qt_compat import QPixmap

            # 如果是暗主题，反色图标
            if theme == "dark":
                # 加载原始图标
                pixmap = QPixmap(self._settings_icon_path)
                if pixmap.isNull():
                    return

                # 缩放到需要的大小
                pixmap = pixmap.scaled(sp(20), sp(20), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

                # 转换为 QImage 进行像素操作
                image = pixmap.toImage()

                # 反色处理 - 保持透明度，只反转RGB
                for y in range(image.height()):
                    for x in range(image.width()):
                        pixel = image.pixelColor(x, y)
                        # 保持 alpha，反转 RGB
                        inverted = QColor(255 - pixel.red(), 255 - pixel.green(), 255 - pixel.blue(), pixel.alpha())
                        image.setPixelColor(x, y, inverted)

                # 转回 QPixmap
                inverted_pixmap = QPixmap.fromImage(image)
                self.settings_btn.setIcon(QIcon(inverted_pixmap))
            else:
                # 亮主题使用原始图标
                self.settings_btn.setIcon(QIcon(self._settings_icon_path))

            self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
        except Exception as exc:
            logger.debug("应用主题到设置图标失败: %s", exc, exc_info=True)

    def set_mode(self, is_settings):
        if self._in_settings_mode == is_settings:
            return
        self._in_settings_mode = is_settings
        self.back_btn.setVisible(is_settings)
        self.icon_label.setVisible(not is_settings)
        self.settings_btn.setVisible(not is_settings)
        self.retranslate_ui()

    def rescale_ui(self):
        self.setFixedHeight(sp(36))
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(sp(8), 0, sp(1), 0)
            layout.setSpacing(sp(4))

        self.back_btn.setFixedSize(sp(32), sp(32))
        self.icon_label.setFixedSize(sp(24), sp(24))
        if self._app_icon_path and os.path.exists(self._app_icon_path):
            pixmap = QIcon(self._app_icon_path).pixmap(sp(24), sp(24))
            if pixmap and not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(sp(24), sp(24), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                )

        self.settings_btn.setFixedSize(sp(32), sp(32))
        self.settings_btn.setIconSize(QSize(sp(20), sp(20)))
        self.close_btn.setFixedSize(sp(32), sp(32))
        self.set_theme(getattr(self, "_theme", "dark"))
        self.retranslate_ui()

    def retranslate_ui(self):
        if not self._in_settings_mode:
            self.title_label.setText(f"QuickLauncher {APP_VERSION}")
            self.title_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
            self.title_label.setContentsMargins(0, 0, 0, 0)
            return

        self.title_label.setText(tr("设置"))
        self.title_label.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
        self.title_label.setContentsMargins(0, 0, 0, 0)

    def _on_back(self):
        self.back_requested.emit()

    def _on_settings(self):
        self.settings_requested.emit()

    def _on_update_click(self, event):
        if self._in_settings_mode:
            return
        if event.button() == QtCompat.LeftButton:
            self.update_requested.emit()

    def _on_close(self):
        if self.parent_window:
            self.parent_window.close()

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            if hasattr(event, "globalPosition"):
                self._drag_pos = event.globalPosition().toPoint()
            else:
                self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & QtCompat.LeftButton:
            if hasattr(event, "globalPosition"):
                new_pos = event.globalPosition().toPoint()
            else:
                new_pos = event.globalPos()

            if self.parent_window:
                diff = new_pos - self._drag_pos
                target_pos = self.parent_window.pos() + diff
                # 约束窗口在屏幕可见区域内（标题栏至少保留 40px 可见）
                target_pos = self._clamp_to_screen(target_pos)
                self.parent_window.move(target_pos)
            self._drag_pos = new_pos

    def _clamp_to_screen(self, pos):
        """将窗口位置约束到所有屏幕的合并可用区域内"""
        from PyQt5.QtCore import QRect
        from PyQt5.QtWidgets import QApplication

        screens = QApplication.screens()
        if not screens:
            return pos

        # 合并所有屏幕的可用几何区域
        combined = screens[0].availableGeometry()
        for screen in screens[1:]:
            combined = combined.united(screen.availableGeometry())

        win = self.parent_window
        win_rect = QRect(pos, win.size())

        min_visible = 40  # 标题栏至少可见的像素数
        # 水平约束
        if win_rect.right() < combined.left() + min_visible:
            pos.setX(combined.left() + min_visible - win.width())
        elif win_rect.left() > combined.right() - min_visible:
            pos.setX(combined.right() - min_visible)
        # 垂直约束
        if win_rect.bottom() < combined.top() + min_visible:
            pos.setY(combined.top() + min_visible - win.height())
        elif win_rect.top() > combined.bottom() - min_visible:
            pos.setY(combined.bottom() - min_visible)

        return pos

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
