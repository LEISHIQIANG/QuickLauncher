"""支持一下弹窗 — 全屏悬浮半透明遮罩，打破窗口限制，玻璃拟态卡片，点击外部关闭。"""

import os
import sys

from core.i18n import tr
from qt_compat import (
    QColor,
    QDialog,
    QEasingCurve,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QtCompat,
    pyqtProperty,
)
from ui.styles.window_chrome import apply_custom_window_chrome


def _rounded_pixmap(source: QPixmap, radius: int = 20) -> QPixmap:
    """将 QPixmap 裁剪为圆角矩形。"""
    size = source.size()
    result = QPixmap(size)
    result.fill(Qt.transparent)

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)

    p = QPainter(result)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QtCompat.HighQualityAntialiasing)
    p.setClipPath(path)
    p.drawPixmap(0, 0, source)
    p.end()

    return result


def _support_image_path() -> str:
    """获取收款码图片的绝对路径。"""
    module_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    exe_root = os.path.dirname(os.path.abspath(sys.argv[0]))
    candidates = [
        os.path.join(module_root, "assets", "support.jpg"),
        os.path.join(exe_root, "assets", "support.jpg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


class SupportDialog(QDialog):
    """全屏悬浮遮罩弹窗，显示支持/收款图片。支持无边界设计，悬浮在屏幕中央。"""

    def __init__(self, drink_name=None, price=None, color_hex=None, parent=None):
        super().__init__(parent)
        self.drink_name = drink_name
        self.price = price
        self.color_hex = color_hex
        self.theme = "dark"

        # 尝试检测父窗口的主题 (兼容 current_theme 与 theme 属性)
        if parent:
            for attr in ("current_theme", "theme"):
                if hasattr(parent, attr):
                    self.theme = getattr(parent, attr)
                    break
                elif hasattr(parent, "window") and hasattr(parent.window(), attr):
                    self.theme = getattr(parent.window(), attr)
                    break

        apply_custom_window_chrome(
            self,
            kind="dialog",
            topmost=True,
            translucent=True,
            delete_on_close=True,
            no_shadow=True,
        )
        self.setModal(True)

        # 始终铺满全屏幕，以创造真正的无边界感觉
        self.showFullScreen()

        self._anim_progress = 0.0
        self._qr_pixmap = QPixmap()
        self._setup_ui()

        # 启动入场动画 (OutCubic: 指数级物理减速，苹果级丝滑自然动效)
        self._entry_anim = QPropertyAnimation(self, b"anim_progress")
        self._entry_anim.setDuration(300)
        self._entry_anim.setStartValue(0.0)
        self._entry_anim.setEndValue(1.0)
        self._entry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._entry_anim.start()

    @pyqtProperty(float)
    def anim_progress(self):
        return self._anim_progress

    @anim_progress.setter
    def anim_progress(self, val):
        self._anim_progress = val
        self.update()

    def _setup_ui(self):
        support_img_path = _support_image_path()
        pixmap = QPixmap(support_img_path)
        if pixmap.isNull():
            pixmap = QPixmap(280, 360)
            pixmap.fill(Qt.gray)
        else:
            # 动态计算收款图黄金比例，保持 100% 原图比例的同时，控制卡片精致小巧，不显得“傻大粗”
            # 限制 PC 端最大宽度 320px，最大高度 460px
            max_w = min(320, int(self.width() * 0.82))
            max_h = min(460, int(self.height() * 0.78))
            # 保持比例缩放
            pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap = _rounded_pixmap(pixmap, 20)
        self._qr_pixmap = pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 获取图片尺寸与绝对居中位置
            pw = self._qr_pixmap.width()
            ph = self._qr_pixmap.height()
            cx = (self.width() - pw) // 2
            cy = (self.height() - ph) // 2
            card_rect = QRect(cx, cy, pw, ph)
            # 只有点击海报外部空白处时，才平滑触发关闭
            if not card_rect.contains(event.pos()):
                self.close_with_anim()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.close_with_anim()
            return
        super().keyPressEvent(event)

    def close_with_anim(self):
        if hasattr(self, "_exit_anim") or self._anim_progress == 0.0:
            return
        self._entry_anim.stop()
        self._exit_anim = QPropertyAnimation(self, b"anim_progress")
        self._exit_anim.setDuration(200)
        self._exit_anim.setStartValue(self._anim_progress)
        self._exit_anim.setEndValue(0.0)
        self._exit_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._exit_anim.finished.connect(super().accept)
        self._exit_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)

        # 1. 绘制全屏背景半透明遮罩 (随着 anim_progress 渐变)
        overlay_alpha = int(140 * self._anim_progress)
        painter.fillRect(self.rect(), QColor(0, 0, 0, overlay_alpha))

        # 2. 绘制原图比例海报卡片
        pw = self._qr_pixmap.width()
        ph = self._qr_pixmap.height()
        cx = (self.width() - pw) // 2
        cy = (self.height() - ph) // 2

        # 应用缩放矩阵 (以海报绝对中心点为缩放原点)
        painter.save()
        card_center_x = cx + pw / 2.0
        card_center_y = cy + ph / 2.0
        painter.translate(card_center_x, card_center_y)
        scale_val = 0.93 + 0.07 * self._anim_progress  # 从 93% 缩放到 100%，过渡极其高档优雅
        painter.scale(scale_val, scale_val)
        painter.translate(-card_center_x, -card_center_y)

        # 3. 绘制极细腻的弥散阴影层
        for i in range(1, 7):
            shadow_color = QColor(0, 0, 0, int((22 - i * 3) * self._anim_progress))
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(QRectF(cx - i, cy - i, pw + i * 2, ph + i * 2), 20 + i, 20 + i)
            shadow_pen = QPen(shadow_color, 1.0)
            shadow_pen.setJoinStyle(QtCompat.RoundJoin)
            shadow_pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(shadow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(shadow_path)

        # 4. 绘制收款大图自身 (完美保留原图宽高比例)
        painter.setOpacity(self._anim_progress)
        painter.drawPixmap(cx, cy, self._qr_pixmap)

        # 5. 绘制卡片玻璃极细边框
        if self.theme == "dark":
            border_color = QColor(255, 255, 255, 38)
        else:
            border_color = QColor(0, 0, 0, 22)
        border_path = QPainterPath()
        border_path.addRoundedRect(QRectF(cx, cy, pw, ph), 20, 20)
        pen = QPen(border_color, 1.0)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(border_path)

        # 6. 绘制下方浮现的极简关闭提示文字
        close_font = QFont("Microsoft YaHei", 9)
        painter.setFont(close_font)
        if self.theme == "dark":
            text_color = QColor(255, 255, 255, 140)
        else:
            text_color = QColor(28, 28, 30, 140)
        painter.setPen(QPen(text_color))
        # 居中绘制在海报正下方 20px 处
        painter.drawText(QRect(0, cy + ph + 20, self.width(), 25), Qt.AlignCenter, tr("✕ 点击空白处关闭"))

        painter.restore()
        painter.end()
