"""完美圆角的自定义 Tooltip"""

from qt_compat import (
    QApplication,
    QColor,
    QCursor,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.window_chrome import apply_custom_window_chrome


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

    def paintEvent(self, event):
        from ui.utils.window_effect import is_win10, paint_win10_rounded_surface

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if self._theme == "dark":
                bg = QColor(44, 44, 48, 240)
                border = QColor(255, 255, 255, 38)
            else:
                bg = QColor(255, 255, 255, 240)
                border = QColor(0, 0, 0, 25)

            if is_win10():
                paint_win10_rounded_surface(painter, self, bg, border, 6, inset=0.5, max_border_alpha=80)
                return

            rect = self.rect()
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 6, 6)

            painter.fillPath(path, bg)
            pen = QPen(border)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)

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

        self.label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 11px;
                padding: 4px 8px;
                background: transparent;
                border: none;
            }}
        """)
        self.label.setText(text)

        # 强制更新布局
        self.label.adjustSize()
        self.setFixedSize(self.label.sizeHint())
        self.update()

        x = pos.x() + 15
        y = pos.y() + 20

        screen = QApplication.screenAt(pos)
        if screen:
            geo = screen.availableGeometry()
            if x + self.width() > geo.right():
                x = pos.x() - self.width() - 5
            if y + self.height() > geo.bottom():
                y = pos.y() - self.height() - 5

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
