"""Individual icon widget and rounded frame — extracted from icon_grid (per §4.7)."""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import ClassVar

from core.data_models import ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QColor,
    QDrag,
    QFont,
    QFrame,
    QLabel,
    QMimeData,
    QPainter,
    QPainterPath,
    QPixmap,
    QPoint,
    QRectF,
    Qt,
    QtCompat,
    QVBoxLayout,
    pyqtSignal,
)
from ui.utils.pixel_snap import create_pixmap, make_cosmetic_pen
from ui.utils.ui_scale import scale_qss, sp

from .icon_grid_palette import (
    BATCH_LAUNCH_BG,
    CELL_BG_DARK,
    CELL_BG_LIGHT,
    CELL_BORDER_DARK,
    CELL_HOVER_DARK,
    CELL_HOVER_LIGHT,
    CELL_SELECTION_DARK,
    CELL_SELECTION_LIGHT,
    COMMAND_BG,
    COMMAND_TEXT,
    DEFAULT_FALLBACK_BG,
    DEFAULT_FALLBACK_TEXT,
    DROP_HIGHLIGHT_BG_DARK,
    DROP_HIGHLIGHT_BG_LIGHT,
    DROP_HIGHLIGHT_BORDER_DARK,
    DROP_HIGHLIGHT_BORDER_LIGHT,
    DROP_TARGET_BG_DARK,
    DROP_TARGET_BG_LIGHT,
    DROP_TARGET_BORDER_DARK,
    DROP_TARGET_BORDER_LIGHT,
    HOTKEY_BG,
    ICON_TEXT,
    MUTED_LABEL_DARK,
    SELECTION_BG,
    SELECTION_BORDER,
    SHADOW_DARK,
    SHADOW_LIGHT,
    URL_BG,
)

logger = logging.getLogger(__name__)


class IconWidget(QFrame):
    """单个图标控件"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    context_menu_requested = pyqtSignal(QPoint)
    drag_started = pyqtSignal(str)
    _placeholder_icon_cache: ClassVar[OrderedDict] = OrderedDict()
    _MAX_PLACEHOLDER_ICON_CACHE = 80

    LIGHT_NORMAL_BG = "rgba(255, 255, 255, 100)"
    LIGHT_HOVER_BG = "rgba(255, 255, 255, 160)"
    DARK_NORMAL_BG = "rgba(255, 255, 255, 22)"
    DARK_HOVER_BG = "rgba(255, 255, 255, 45)"
    DROP_TARGET_BG = "rgba(0, 122, 255, 80)"

    def __init__(self, shortcut: ShortcutItem, icon_size: int = 24, cell_size: int = 65, theme: str = "dark"):
        super().__init__()
        self.shortcut = shortcut
        self.icon_size = icon_size
        self.cell_size = cell_size
        self.theme = theme
        self._drag_start_pos = None
        self._is_dragging = False
        self._is_drop_target = False
        self._is_selected = False
        self._normal_bg = self.DARK_NORMAL_BG if theme == "dark" else self.LIGHT_NORMAL_BG
        self._hover_bg = self.DARK_HOVER_BG if theme == "dark" else self.LIGHT_HOVER_BG
        self._border = "1px solid rgba(255, 255, 255, 35)" if theme == "dark" else "1px solid rgba(0, 0, 0, 12)"
        # QColor values for RoundedFrame (high-quality antialiased painting)
        self._border_qcolor = QColor(CELL_BORDER_DARK) if theme == "dark" else QColor(MUTED_LABEL_DARK)
        self._bg_qcolor = QColor(CELL_BG_DARK) if theme == "dark" else QColor(CELL_BG_LIGHT)
        self._hover_qcolor = QColor(CELL_HOVER_DARK) if theme == "dark" else QColor(CELL_HOVER_LIGHT)
        self._selection_qcolor = QColor(CELL_SELECTION_DARK) if theme == "dark" else QColor(CELL_SELECTION_LIGHT)

        self._setup_ui()
        self.setAcceptDrops(False)
        self._set_normal_style()

    def _setup_ui(self):
        self.setFixedSize(self.cell_size, self.cell_size)
        self.setCursor(QtCompat.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(4), sp(4), sp(4), sp(4))
        layout.setSpacing(sp(2))
        layout.setAlignment(QtCompat.AlignCenter)

        # 图标底框：图标四周各大7px — 使用 RoundedFrame 替代 QSS border-radius
        # 以消除深色模式下圆角边缘的锯齿和泛白
        icon_frame_h = self.icon_size + sp(12)
        icon_frame_w = self.icon_size + sp(12)
        self.icon_frame = RoundedFrame()
        self.icon_frame.setFixedSize(icon_frame_w, icon_frame_h)
        self._apply_icon_frame_style()
        self.icon_frame.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        frame_layout = QVBoxLayout(self.icon_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setAlignment(QtCompat.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(self.icon_size, self.icon_size)
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        frame_layout.addWidget(self.icon_label)

        layout.addWidget(self.icon_frame, alignment=QtCompat.AlignCenter)

        self.name_label = QLabel(self.shortcut.name[:6] if self.shortcut.name else tr("未命名"))
        self.name_label.setAlignment(QtCompat.AlignCenter)
        self.name_label.setStyleSheet(
            scale_qss("font-size: 11px; background: transparent; border-radius: 0; border: none;")
        )
        self.name_label.setWordWrap(True)
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.name_label)

        self._load_icon()

    def _apply_icon_frame_style(self, hover=False, drop=False):
        """Apply antialiased QPainter-based style to RoundedFrame."""
        if not isinstance(self.icon_frame, RoundedFrame):
            return
        if self._is_selected:
            self.icon_frame.set_colors(
                QColor(SELECTION_BG),
                QColor(SELECTION_BORDER),
                border_width=1.0,
                radius=9.0,
            )
        elif drop:
            if self.theme == "dark":
                self.icon_frame.set_colors(
                    QColor(DROP_HIGHLIGHT_BG_DARK),
                    QColor(DROP_HIGHLIGHT_BORDER_DARK),
                    border_width=2.0,
                    radius=9.0,
                    dashed=True,
                )
            else:
                self.icon_frame.set_colors(
                    QColor(DROP_HIGHLIGHT_BG_LIGHT),
                    QColor(DROP_HIGHLIGHT_BORDER_LIGHT),
                    border_width=2.0,
                    radius=9.0,
                    dashed=True,
                )
        else:
            bg = self._hover_qcolor if hover else self._bg_qcolor
            self.icon_frame.set_colors(
                bg,
                self._border_qcolor,
                border_width=1.0,
                radius=9.0,
            )

    def _icon_frame_style(self, hover=False, drop=False):
        if self._is_selected:
            return scale_qss(
                "QFrame { background-color: rgba(100,181,246,26); border-radius: 9px; border: 1px solid rgba(100,181,246,170); }"
            )
        if drop:
            if self.theme == "dark":
                return scale_qss(
                    "QFrame { background-color: rgba(168, 230, 207, 45); border-radius: 9px; border: 2px dashed rgba(168, 230, 207, 180); }"
                )
            else:
                return scale_qss(
                    "QFrame { background-color: rgba(168, 230, 207, 75); border-radius: 9px; border: 2px dashed rgba(70, 180, 140, 200); }"
                )
        bg = self._hover_bg if hover else self._normal_bg
        return scale_qss(f"QFrame {{ background-color: {bg}; border-radius: 9px; border: {self._border}; }}")

    def _load_icon(self):
        """设置占位图标（实际图标由 IconGrid 异步加载）"""
        cache_key = self._placeholder_icon_cache_key()
        cached = self._placeholder_icon_cache.get(cache_key)
        if cached is not None and not cached.isNull():
            self._placeholder_icon_cache.move_to_end(cache_key)
            self.icon_label.setPixmap(cached)
            return

        if self.shortcut.type == ShortcutType.HOTKEY:
            pixmap = self._create_hotkey_icon()
        elif self.shortcut.type == ShortcutType.URL:
            pixmap = self._create_url_icon()
        elif self.shortcut.type == ShortcutType.COMMAND:
            pixmap = self._create_command_icon()
        elif self.shortcut.type == ShortcutType.BATCH_LAUNCH:
            pixmap = self._create_batch_launch_icon()
        else:
            pixmap = None

        if not pixmap:
            pixmap = self._create_default_icon()

        self._placeholder_icon_cache[cache_key] = pixmap
        self._placeholder_icon_cache.move_to_end(cache_key)
        while len(self._placeholder_icon_cache) > self._MAX_PLACEHOLDER_ICON_CACHE:
            self._placeholder_icon_cache.popitem(last=False)
        self.icon_label.setPixmap(pixmap)

    def _placeholder_icon_cache_key(self):
        item_type = getattr(self.shortcut, "type", None)
        first_char = self.shortcut.name[0] if getattr(self.shortcut, "name", "") else "?"
        if item_type in {
            ShortcutType.HOTKEY,
            ShortcutType.URL,
            ShortcutType.COMMAND,
            ShortcutType.BATCH_LAUNCH,
        }:
            first_char = ""
        return (item_type, int(self.icon_size), first_char)

    def _create_default_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setBrush(QColor(DEFAULT_FALLBACK_BG))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        radius = size // 6
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), radius, radius)

        first_char = self.shortcut.name[0] if self.shortcut.name else "?"
        painter.setPen(QColor(DEFAULT_FALLBACK_TEXT))
        font = QFont("Segoe UI")
        font.setPixelSize(max(1, int(size * 0.4)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, first_char)
        painter.end()

        return pixmap

    def _create_hotkey_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        painter.setBrush(QColor(HOTKEY_BG))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

        painter.setPen(QColor(ICON_TEXT))
        font = QFont("Segoe UI Symbol")
        font.setPixelSize(max(1, size // 3))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌨")

        painter.end()
        return pixmap

    def _create_url_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        painter.setBrush(QColor(URL_BG))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

        painter.setPen(QColor(ICON_TEXT))
        font = QFont("Segoe UI Symbol")
        font.setPixelSize(max(1, size // 3))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "🌐")

        painter.end()
        return pixmap

    def _create_command_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        painter.setBrush(QColor(COMMAND_BG))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

        painter.setPen(QColor(COMMAND_TEXT))
        font = QFont("Consolas")
        font.setPixelSize(max(1, size // 3))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, ">_")

        painter.end()
        return pixmap

    def _create_batch_launch_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        painter.setBrush(QColor(BATCH_LAUNCH_BG))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

        painter.setPen(QColor(ICON_TEXT))
        font = QFont("Segoe UI Symbol")
        font.setPixelSize(max(1, size // 3))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "▶")

        painter.end()
        return pixmap

    def _set_normal_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border-radius: 0; border: none; }")
        if hasattr(self, "icon_frame"):
            self._apply_icon_frame_style(hover=False)

    def _set_hover_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border-radius: 0; border: none; }")
        if hasattr(self, "icon_frame"):
            self._apply_icon_frame_style(hover=True)

    def _set_drop_target_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border-radius: 0; border: none; }")
        if hasattr(self, "icon_frame"):
            self._apply_icon_frame_style(drop=True)

    def set_selected(self, selected: bool):
        self._is_selected = bool(selected)
        if hasattr(self, "icon_frame"):
            self._apply_icon_frame_style()

    def enterEvent(self, event):
        if not self._is_drop_target and not self._is_dragging:
            self._set_hover_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_drop_target:
            self._set_normal_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self._drag_start_pos = event.pos()
            self._is_dragging = False

    def mouseMoveEvent(self, event):
        if not self._drag_start_pos:
            return

        if event.buttons() & QtCompat.LeftButton:
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance > 10 and not self._is_dragging:
                self._is_dragging = True
                self._start_drag()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            if not self._is_dragging:
                self.clicked.emit()
        elif event.button() == QtCompat.RightButton:
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.context_menu_requested.emit(pos)

        self._drag_start_pos = None
        self._is_dragging = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.double_clicked.emit()

    def create_drag_preview_pixmap(self) -> QPixmap:
        # 尺寸与图标底框完全一致：icon_size + 14 像素
        size = self.icon_size + 14
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)

        # 浅雅清新的粉绿配色系统
        if self.theme == "dark":
            bg_color = QColor(DROP_TARGET_BG_DARK)
            border_color = QColor(DROP_TARGET_BORDER_DARK)
        else:
            bg_color = QColor(DROP_TARGET_BG_LIGHT)
            border_color = QColor(DROP_TARGET_BORDER_LIGHT)

        # 模拟精致的悬浮阴影 — 使用 QRectF 半像素对齐
        shadow_color = QColor(SHADOW_DARK) if self.theme == "dark" else QColor(SHADOW_LIGHT)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(shadow_color)
        painter.drawRoundedRect(QRectF(2.5, 2.5, size - 5, size - 5), 9, 9)

        # 绘制卡片背景与浅绿边框 (圆角完美契合底框的 9px)
        painter.setBrush(bg_color)
        pen = make_cosmetic_pen(border_color, 1.5)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(1.5, 1.5, size - 3, size - 3), 9, 9)

        # 居中绘制图标本身，去掉文本标签
        icon_pixmap = self.icon_label.pixmap()
        if icon_pixmap and not icon_pixmap.isNull():
            icon_x = (size - self.icon_size) // 2
            icon_y = (size - self.icon_size) // 2
            painter.drawPixmap(icon_x, icon_y, icon_pixmap)

        painter.end()
        return pixmap

    def _start_drag(self):
        # 系统图标不允许拖动
        if getattr(self.shortcut, "_icon_repo_source", "") == "system":
            return

        grid_parent = None
        try:
            parent = self.parent()
            while parent:
                if hasattr(parent, "data_manager"):
                    if getattr(parent.data_manager.get_settings(), "sort_mode", "custom") == "smart":
                        return
                    if hasattr(parent, "current_folder_id"):
                        grid_parent = parent
                    break
                parent = parent.parent()

            self._set_normal_style()

            drag = QDrag(self)
            mime_data = QMimeData()
            drag_ids = [self.shortcut.id]
            if grid_parent and hasattr(grid_parent, "get_drag_shortcut_ids"):
                drag_ids = grid_parent.get_drag_shortcut_ids(self.shortcut.id)
            mime_data.setData("application/x-shortcut-id", self.shortcut.id.encode())
            mime_data.setData("application/x-shortcut-ids", "\n".join(drag_ids).encode())

            # 添加源文件夹信息
            if grid_parent and grid_parent.current_folder_id:
                mime_data.setData("application/x-source-folder-id", grid_parent.current_folder_id.encode())

            drag.setMimeData(mime_data)

            # 使用高拟真自定义淡雅卡片作为拖动预览
            preview_pixmap = None
            if grid_parent and hasattr(grid_parent, "create_drag_preview_pixmap"):
                preview_pixmap = grid_parent.create_drag_preview_pixmap(drag_ids, self)
            if preview_pixmap is None:
                preview_pixmap = self.create_drag_preview_pixmap()
            if preview_pixmap and not preview_pixmap.isNull():
                drag.setPixmap(preview_pixmap)
                # 热点居中，确保拖拽时卡片完美处于鼠标指针正下方！
                drag.setHotSpot(QPoint(preview_pixmap.width() // 2, preview_pixmap.height() // 2))
            elif self.icon_label.pixmap() and not self.icon_label.pixmap().isNull():
                drag.setPixmap(self.icon_label.pixmap())
                drag.setHotSpot(QPoint(self.icon_size // 2, self.icon_size // 2))

            # Dim the source icon during drag for dynamic feedback.
            # ``QGraphicsOpacityEffect`` triggers an off-screen render of
            # the whole subtree on every paint; replaced with the cheap
            # ``opacity`` style override.
            if grid_parent and hasattr(grid_parent, "begin_drag_visuals"):
                grid_parent.begin_drag_visuals(drag_ids)
            else:
                self._drag_opacity = True
                self.setStyleSheet("QWidget { opacity: 0.4; }")

            self.drag_started.emit(self.shortcut.id)
            result = drag.exec_(QtCompat.MoveAction)
            if grid_parent and result == QtCompat.MoveAction:
                grid_parent._drag_completed = True
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"拖动失败: {e}")
        finally:
            self._is_dragging = False
            try:
                if grid_parent and hasattr(grid_parent, "end_drag_visuals"):
                    grid_parent.end_drag_visuals()
                else:
                    self.setGraphicsEffect(None)
                self._set_normal_style()
            except RuntimeError:
                logger.debug("拖动结束后恢复图标视觉效果失败", exc_info=True)

            # Notify parent grid that drag has ended
            parent = self.parent()
            while parent:
                if hasattr(parent, "handle_drag_ended"):
                    parent.handle_drag_ended()
                    break
                parent = parent.parent()

    def dragEnterEvent(self, event):
        event.ignore()

    def dragMoveEvent(self, event):
        event.ignore()

    def dragLeaveEvent(self, event):
        event.ignore()

    def dropEvent(self, event):
        event.ignore()


class RoundedFrame(QFrame):
    """High-quality antialiased rounded frame using QPainter.

    Replaces QSS ``border-radius`` which produces jagged / whitish edges
    on small widgets, especially noticeable in dark mode.  QPainter with
    *HighQualityAntialiasing* + ``QRectF`` half-pixel alignment yields
    clean sub-pixel rendering.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(CELL_BG_DARK)
        self._border_color = QColor(CELL_BORDER_DARK)
        self._border_width = 1.0
        self._radius = 9.0
        self._is_dashed = False
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def set_colors(self, bg_color, border_color, border_width=1.0, radius=9.0, dashed=False):
        """Update visual properties and trigger repaint."""
        self._bg_color = QColor(bg_color) if not isinstance(bg_color, QColor) else QColor(bg_color)
        self._border_color = QColor(border_color) if not isinstance(border_color, QColor) else QColor(border_color)
        self._border_width = float(border_width)
        self._radius = float(radius)
        self._is_dashed = bool(dashed)
        self.update()

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        # Half-pixel inset so the 1 px pen sits exactly on the pixel grid,
        # eliminating the fuzzy / whitish halo that QSS border-radius produces.
        inset = self._border_width / 2.0
        rect = QRectF(inset, inset, w - inset * 2, h - inset * 2)

        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        # -- fill --
        painter.fillPath(path, self._bg_color)

        # -- border --
        if self._border_color.alpha() > 0 and self._border_width > 0:
            pen = make_cosmetic_pen(self._border_color, self._border_width)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            if self._is_dashed:
                pen.setStyle(QtCompat.DashLine)
            painter.setPen(pen)
            painter.setBrush(QtCompat.NoBrush)
            painter.drawPath(path)

        painter.end()
