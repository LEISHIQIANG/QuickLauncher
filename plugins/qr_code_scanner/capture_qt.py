"""Minimal PyQt screen region capture overlay."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QWidget


class CaptureOverlay(QWidget):
    def __init__(self, screen, done_callback):
        super().__init__(None)
        self.screen = screen
        self.done_callback = done_callback
        self.screen_geometry = screen.geometry()
        self.screenshot = screen.grabWindow(0)
        self.start_pos: QPoint | None = None
        self.end_pos: QPoint | None = None
        self.selection = QRect()
        self.dragging = False
        self.confirm_rect = QRect()
        self.cancel_rect = QRect()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(self.screen_geometry)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 130))

        rect = self._normalized_selection()
        if rect.isValid() and rect.width() > 2 and rect.height() > 2:
            painter.drawPixmap(rect, self.screenshot, rect)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(38, 132, 255), 1))
            painter.drawRect(rect.adjusted(2, 2, -2, -2))
            self._draw_size_label(painter, rect)
            self._draw_buttons(painter, rect)
        else:
            self.confirm_rect = QRect()
            self.cancel_rect = QRect()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.done_callback("")
            return
        if event.button() != Qt.LeftButton:
            return
        if self.confirm_rect.contains(event.pos()):
            self._confirm()
            return
        if self.cancel_rect.contains(event.pos()):
            self.done_callback("")
            return
        self.start_pos = event.pos()
        self.end_pos = event.pos()
        self.dragging = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.end_pos = event.pos()
            self.dragging = False
            self.selection = self._normalized_selection()
            self.update()

    def mouseDoubleClickEvent(self, event):
        if self._normalized_selection().isValid():
            self._confirm()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.done_callback("")
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()

    def _normalized_selection(self) -> QRect:
        if self.start_pos is None or self.end_pos is None:
            return QRect()
        return QRect(self.start_pos, self.end_pos).normalized()

    def _draw_size_label(self, painter: QPainter, rect: QRect) -> None:
        text = f"{rect.width()} x {rect.height()}"
        painter.setFont(QFont("Segoe UI", 9))
        metrics = painter.fontMetrics()
        label = QRect(rect.left(), max(0, rect.top() - 26), metrics.horizontalAdvance(text) + 14, 22)
        painter.fillRect(label, QColor(20, 20, 20, 210))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(label, Qt.AlignCenter, text)

    def _draw_buttons(self, painter: QPainter, rect: QRect) -> None:
        button_w = 58
        button_h = 30
        gap = 8
        y = rect.bottom() + 10
        if y + button_h > self.height():
            y = rect.top() - button_h - 10
        x = min(max(rect.right() - button_w * 2 - gap, 8), max(8, self.width() - button_w * 2 - gap - 8))
        self.confirm_rect = QRect(x, y, button_w, button_h)
        self.cancel_rect = QRect(x + button_w + gap, y, button_w, button_h)
        self._draw_button(painter, self.confirm_rect, "识别", QColor(38, 132, 255))
        self._draw_button(painter, self.cancel_rect, "取消", QColor(70, 70, 70))

    def _draw_button(self, painter: QPainter, rect: QRect, text: str, color: QColor) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _confirm(self) -> None:
        rect = self._normalized_selection()
        if not rect.isValid() or rect.width() < 8 or rect.height() < 8:
            return
        dpr = self.screenshot.devicePixelRatio() or 1.0
        source = QRect(
            int(rect.x() * dpr),
            int(rect.y() * dpr),
            int(rect.width() * dpr),
            int(rect.height() * dpr),
        )
        cropped = self.screenshot.copy(source)
        cropped.setDevicePixelRatio(1.0)
        out = Path(tempfile.gettempdir()) / f"ql_qr_capture_{int(time.time() * 1000)}.png"
        if cropped.save(str(out), "PNG"):
            self.done_callback(str(out))
        else:
            self.done_callback("")


class CaptureSession:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.result = ""
        self.overlays: list[CaptureOverlay] = []

    def run(self) -> str:
        screens = self.app.screens()
        if not screens:
            return ""
        for screen in screens:
            overlay = CaptureOverlay(screen, self._finish)
            self.overlays.append(overlay)
            overlay.showFullScreen()
            overlay.activateWindow()
            overlay.raise_()
        self.app.exec_()
        return self.result

    def _finish(self, path: str) -> None:
        self.result = path
        for overlay in list(self.overlays):
            overlay.hide()
            overlay.close()
        self.overlays.clear()
        self.app.quit()


def capture_region() -> str:
    return CaptureSession().run()
