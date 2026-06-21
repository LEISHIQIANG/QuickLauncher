"""ConnectionItem — extracted from chain_canvas (per §4.7)."""

from __future__ import annotations

from qt_compat import (
    QBrush,
    QColor,
    QGraphicsPathItem,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    Qt,
    QtCompat,
)

from .chain_canvas_nodes import NodeItem  # noqa: F811 - type-only re-export


class ConnectionItem(QGraphicsPathItem):
    def __init__(self, connection: dict, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.source_node_item: NodeItem | None = None
        self.target_node_item: NodeItem | None = None
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)

    def update_path(self, start: QPointF, end: QPointF):
        path = QPainterPath(start)
        dist_x = end.x() - start.x()
        dist_y = end.y() - start.y()

        if dist_x > 0:
            # Forward connection: smooth transition scaling with distance
            dx = max(40.0, dist_x * 0.5)
        else:
            # Backward connection: create a beautiful wide loop
            base_loop = 80.0
            dx = base_loop + abs(dist_x) * 0.5 + min(120.0, abs(dist_y) * 0.3)

        path.cubicTo(start.x() + dx, start.y(), end.x() - dx, end.y(), end.x(), end.y())
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        path = self.path()
        if path.isEmpty():
            return QRectF()
        rect = path.boundingRect()
        padding = 6.0
        return rect.adjusted(-padding, -padding, padding, padding + 2.0)

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[unused-ignore, override]
        path = self.path()
        if path.isEmpty():
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # Check selection status of connected nodes
        source_selected = self.source_node_item.isSelected() if self.source_node_item else False
        target_selected = self.target_node_item.isSelected() if self.target_node_item else False
        is_highlighted = source_selected or target_selected

        # Check if preview path
        is_preview = self.connection.get("id") == "__preview__"

        start_pt = path.pointAtPercent(0.0)
        end_pt = path.pointAtPercent(1.0)

        # Define colors (Grasshopper aesthetic)
        if is_preview:
            color_start = QColor("#FFB74D")  # Cozy orange
            color_end = QColor("#FF8A65")  # Soft coral
        elif is_highlighted:
            color_start = QColor("#AEEA00")  # Electric neon green
            color_end = QColor("#00E676")  # Bright flow green
        else:
            color_start = QColor("#64B5F6")  # Premium output blue
            color_end = QColor("#4DB6AC")  # Premium input teal

        # Pass 1: Drop Shadow (Soft, floating 3D depth, without harsh outlines)
        shadow_path = path.translated(0, 1.2)
        shadow_pen = QPen(QColor(0, 0, 0, 40), 4.5)
        shadow_pen.setCapStyle(Qt.RoundCap)  # type: ignore[unused-ignore, attr-defined]
        shadow_pen.setJoinStyle(Qt.RoundJoin)  # type: ignore[unused-ignore, attr-defined]
        painter.setPen(shadow_pen)
        painter.drawPath(shadow_path)

        # Pass 2: Flowing Core Line (Linear Gradient)
        # Slightly wider (2.0px) to compensate for outline removal and ensure crispness
        grad = QLinearGradient(start_pt, end_pt)
        grad.setColorAt(0.0, color_start)
        grad.setColorAt(1.0, color_end)

        core_pen = QPen(QBrush(grad), 2.0)
        core_pen.setCapStyle(Qt.RoundCap)  # type: ignore[unused-ignore, attr-defined]
        core_pen.setJoinStyle(Qt.RoundJoin)  # type: ignore[unused-ignore, attr-defined]
        painter.setPen(core_pen)
        painter.drawPath(path)

        painter.restore()
