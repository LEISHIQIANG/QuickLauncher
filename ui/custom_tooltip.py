"""完美圆角的自定义 Tooltip"""

from qt_compat import (
    QApplication,
    QColor,
    QCursor,
    QLabel,
    QPainter,
    QPainterPath,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.design_tokens import border as token_border
from ui.styles.design_tokens import surface as token_surface
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import scale_qss, sp, spf


class CustomToolTip(QWidget):
    """完美圆角 Tooltip"""

    _instance = None
    _timer = None

    def __init__(self):
        super().__init__(None)
        apply_custom_window_chrome(self, kind="tooltip", topmost=True, translucent=True, no_shadow=True)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.label = QLabel(self)
        self.label.setWordWrap(False)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMargin(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.label)

        self._theme = "dark"
        self._text = ""

    def paintEvent(self, event):  # noqa: paint_perf
        from ui.utils.window_effect import is_win10, paint_win10_rounded_surface

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if self._theme == "dark":
                # 自定义 tooltip 偏冷的深灰色 bg_chrome，与 bg_glass 有视觉差异
                bg = QColor(token_surface(self._theme, "bg_chrome"))
                bg.setAlpha(240)
                # 与基线一致：dark 边框 38 alpha white overlay
                border = QColor(token_border(self._theme, "subtle"))
            else:
                # 与基线一致：light 背景纯白 240 alpha，黑色 25 alpha 边框
                bg = QColor(token_surface(self._theme, "bg_chrome"))
                border = QColor(token_border(self._theme, "subtle"))

            if is_win10():
                paint_win10_rounded_surface(painter, self, bg, border, sp(6), inset=spf(4.0), max_border_alpha=80)
                return

            rect = self.rect()
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), spf(6), spf(6))

            painter.fillPath(path, bg)
            # 使用 make_cosmetic_pen 保证 1px 边框在 125%+ DPI 下不发胖
            painter.setPen(make_cosmetic_pen(border, 1))

            painter.drawPath(path)
        finally:
            painter.end()

    def showText(self, text: str, pos, theme: str = "dark"):
        self._theme = theme
        self._text = text

        if theme == "dark":
            color = "#ffffff"
        else:
            color = "#1c1c1e"

        self.label.setStyleSheet(
            scale_qss(
                f"""
            QLabel {{
                color: {color};
                font-size: 11px;
                padding: 4px 8px;
                background: transparent;
                border: none; border-radius: 0;
            }}
        """
            )
        )
        self.label.setText(text)

        # 强制更新布局
        self.label.adjustSize()
        self.setFixedSize(self.label.sizeHint())
        self.update()

        x = pos.x() + sp(16)
        y = pos.y() + sp(20)

        screen = QApplication.screenAt(pos)
        if screen:
            geo = screen.availableGeometry()
            if x + self.width() > geo.right():
                x = pos.x() - self.width() - sp(5)
            if y + self.height() > geo.bottom():
                y = pos.y() - self.height() - sp(5)

        self.move(x, y)
        self.show()
        self.raise_()

    @classmethod
    def showToolTip(cls, text: str, theme: str = "dark", pos=None):
        if not text:
            return

        if cls._instance is None:
            cls._instance = CustomToolTip()

        if cls._timer:
            cls._timer.stop()

        if pos is None:
            pos = QCursor.pos()

        cls._instance.showText(text, pos, theme)

        cls._timer = QTimer(cls._instance)
        cls._timer.setSingleShot(True)
        cls._timer.timeout.connect(cls._instance.hide)
        cls._timer.start(3000)

    @classmethod
    def hideToolTip(cls):
        if cls._instance:
            cls._instance.hide()
        if cls._timer:
            cls._timer.stop()
