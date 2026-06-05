"""Node-canvas editor primitives for action chains."""

from __future__ import annotations

import copy
import logging
import uuid

from core.chain_contracts import (
    binding_key,
    input_port_specs_for_node,
    output_port_specs_for_node,
    validate_canvas_connection,
)
from core.chain_processors import (
    DEFAULT_PYTHON_CELL_SOURCE,
    processor_definition,
    processor_definitions,
    processor_title,
    python_cell_metadata,
)
from core.data_models import ShortcutItem, normalize_chain_step_delay_ms
from qt_compat import (
    QBrush,
    QCheckBox,
    QColor,
    QComboBox,
    QDialog,
    QFont,
    QFontMetrics,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLinearGradient,
    QLineEdit,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QPushButton,
    QRectF,
    QSpinBox,
    Qt,
    QtCompat,
    QTextEdit,
    QTextOption,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.utils.safe_file_dialog import get_existing_directory, get_open_file_name

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


def canvas_from_steps(steps: list[dict], shortcuts: dict[str, ShortcutItem]) -> dict:
    canvas = ShortcutItem._chain_canvas_from_steps(steps)
    real_ids = {node["id"] for node in canvas.get("nodes", [])}
    for node in canvas.get("nodes", []):
        if node.get("node_type") == "processor":
            if str(node.get("processor_id") or "") == "python_cell":
                node["title"] = python_cell_metadata(str(node.get("source") or DEFAULT_PYTHON_CELL_SOURCE))["title"]
            else:
                node["title"] = processor_title(str(node.get("processor_id") or ""))
        else:
            shortcut = shortcuts.get(str(node.get("shortcut_id") or ""))
            node["title"] = getattr(shortcut, "name", "") or str(node.get("shortcut_id") or "")
    canvas["connections"] = [
        connection
        for connection in canvas.get("connections", [])
        if connection.get("source_node") in real_ids and connection.get("target_node") in real_ids
    ]
    return canvas


def compile_canvas_to_steps(canvas: dict) -> list[dict]:
    nodes = sorted(canvas.get("nodes") or [], key=lambda n: (int(n.get("order", 0) or 0), float(n.get("x", 0) or 0)))
    index_by_node = {str(node.get("id")): index for index, node in enumerate(nodes, start=1)}
    incoming: dict[str, list[dict]] = {}
    for connection in list(canvas.get("connections") or []):
        incoming.setdefault(str(connection.get("target_node") or ""), []).append(connection)

    steps = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id") or uuid.uuid4())
        node_type = str(node.get("node_type") or "shortcut")
        step = {
            "id": node_id,
            "node_type": node_type,
            "enabled": bool(node.get("enabled", True)),
            "stop_on_error": bool(node.get("stop_on_error", True)),
            "delay_ms": normalize_chain_step_delay_ms(node.get("delay_ms", 0)),
            "input_binding": "",
            "param_bindings": {},
            "args": {str(k): str(v) for k, v in dict(node.get("args") or {}).items() if str(k).strip()},
        }
        if node_type == "processor":
            step["processor_id"] = str(node.get("processor_id") or "")
            step["shortcut_id"] = ""
            step["source"] = str(node.get("source") or "")
        else:
            step["shortcut_id"] = str(node.get("shortcut_id") or "")
            step["processor_id"] = ""
            step["source"] = ""
        for connection in incoming.get(node_id, []):
            source_index = index_by_node.get(str(connection.get("source_node") or ""))
            source_port = str(connection.get("source_port") or "").strip()
            target_port = str(connection.get("target_port") or "").strip()
            if not source_index or not source_port or not target_port:
                continue
            if source_index >= index:
                continue
            binding = binding_key(source_index, source_port)
            if target_port == "input":
                existing = step.get("input_binding")
                step["input_binding"] = _append_binding(existing, binding)
            else:
                existing = step["param_bindings"].get(target_port)
                step["param_bindings"][target_port] = _append_binding(existing, binding)
                step["args"].pop(target_port, None)
        step["order"] = index
        steps.append(step)
    return ShortcutItem._normalize_chain_steps(steps)

def _append_binding(existing, binding: str):
    if not existing:
        return binding
    if isinstance(existing, list):
        return existing + [binding]
    return [str(existing), binding]


def node_input_ports(node: dict, shortcuts: dict[str, ShortcutItem]) -> list[str]:
    return [spec.id for spec in input_port_specs_for_node(node, shortcuts)]


def node_output_ports(node: dict, shortcuts: dict[str, ShortcutItem] | None = None) -> list[str]:
    return [spec.id for spec in output_port_specs_for_node(node, shortcuts or {})]


def node_input_labels(node: dict, shortcuts: dict[str, ShortcutItem]) -> dict[str, str]:
    return {spec.id: spec.label for spec in input_port_specs_for_node(node, shortcuts) if spec.label}


def node_output_labels(node: dict, shortcuts: dict[str, ShortcutItem] | None = None) -> dict[str, str]:
    return {spec.id: spec.label for spec in output_port_specs_for_node(node, shortcuts or {}) if spec.label}


class PortItem(QGraphicsEllipseItem):
    def __init__(self, node_id: str, port_id: str, direction: str, x: float, y: float, parent=None):
        super().__init__(-6, -6, 12, 12, parent)
        self.node_id = node_id
        self.port_id = port_id
        self.direction = direction
        self.setPos(x, y)
        self.color = QColor("#4DB6AC") if direction == "input" else QColor("#64B5F6")
        self.setBrush(QBrush(self.color))
        self.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(self.color.lighter(115)))
        self.setPen(QPen(QColor(255, 255, 255, 230), 1.8))
        self.setRect(-7.5, -7.5, 15, 15)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(self.color))
        self.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
        self.setRect(-6, -6, 12, 12)
        super().hoverLeaveEvent(event)

    def boundingRect(self) -> QRectF:
        rect = self.rect()
        padding = 2.0
        return rect.adjusted(-padding, -padding, padding, padding)


class PanelTextViewportItem(QGraphicsRectItem):
    """Scrollable text viewport embedded in the panel node."""

    PADDING = 8.0
    SCROLLBAR_WIDTH = 5.0
    MIN_THUMB_HEIGHT = 18.0

    def __init__(self, rect: QRectF, text: str, parent=None):
        super().__init__(rect, parent)
        self._scroll_offset = 0.0
        self._max_scroll_offset = 0.0
        self._content_height = 0.0
        self._document_height = 0.0

        self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.NoButton)

        self.text_item = QGraphicsTextItem(self)
        self.text_item.setFont(QFont("Microsoft YaHei UI", 8))
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)

        option = self.text_item.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text_item.document().setDefaultTextOption(option)

        self.scrollbar_track = QGraphicsRectItem(self)
        self.scrollbar_track.setAcceptedMouseButtons(Qt.NoButton)
        self.scrollbar_track.setPen(QPen(Qt.NoPen))
        self.scrollbar_track.setZValue(2)

        self.scrollbar_thumb = QGraphicsRectItem(self)
        self.scrollbar_thumb.setAcceptedMouseButtons(Qt.NoButton)
        self.scrollbar_thumb.setPen(QPen(Qt.NoPen))
        self.scrollbar_thumb.setZValue(3)

        self.set_text(text)
        self.set_colors(QColor("#FFFFFF"), QColor("#CFD8DC"), QColor("#263238"), QColor("#90A4AE"))

    def toPlainText(self) -> str:  # Qt-style helper used by tests and callers.
        return self.text_item.toPlainText()

    @property
    def max_scroll_offset(self) -> float:
        return self._max_scroll_offset

    @property
    def scroll_offset(self) -> float:
        return self._scroll_offset

    def set_text(self, text: str):
        self.text_item.setPlainText(str(text or ""))
        self._refresh_layout()

    def set_colors(self, background: QColor, border: QColor, text: QColor, muted: QColor):
        self.setBrush(QBrush(background))
        self.setPen(QPen(border, 1.0))
        self.text_item.setDefaultTextColor(text)
        self.scrollbar_track.setBrush(QBrush(QColor(muted.red(), muted.green(), muted.blue(), 45)))
        self.scrollbar_thumb.setBrush(QBrush(QColor(muted.red(), muted.green(), muted.blue(), 170)))

    def set_scroll_offset(self, value: float):
        self._scroll_offset = max(0.0, min(float(value or 0.0), self._max_scroll_offset))
        rect = self.rect()
        self.text_item.setPos(rect.left() + self.PADDING, rect.top() + self.PADDING - self._scroll_offset)
        self._refresh_scrollbar()

    def scroll_by_wheel_delta(self, delta: float) -> bool:
        if self._max_scroll_offset <= 0:
            return False
        line_step = max(14.0, QFontMetrics(self.text_item.font()).height())
        self.set_scroll_offset(self._scroll_offset - (float(delta) / 120.0) * line_step * 3.0)
        return True

    def wheelEvent(self, event):
        if hasattr(event, "delta"):
            delta = event.delta()
        elif hasattr(event, "angleDelta"):
            delta = event.angleDelta().y()
        else:
            delta = 0
        if not self.scroll_by_wheel_delta(delta):
            super().wheelEvent(event)
            return
        event.accept()

    @staticmethod
    def wheel_delta_from_event(event) -> float:
        if hasattr(event, "delta"):
            return float(event.delta())
        if hasattr(event, "angleDelta"):
            return float(event.angleDelta().y())
        return 0.0

    def _refresh_layout(self):
        rect = self.rect()
        text_width = max(40.0, rect.width() - self.PADDING * 2 - self.SCROLLBAR_WIDTH - 6.0)
        self._content_height = max(1.0, rect.height() - self.PADDING * 2)
        self.text_item.setTextWidth(text_width)
        self._document_height = float(self.text_item.document().size().height())
        self._max_scroll_offset = max(0.0, self._document_height - self._content_height)
        self.set_scroll_offset(self._scroll_offset)

    def _refresh_scrollbar(self):
        rect = self.rect()
        track_x = rect.right() - self.SCROLLBAR_WIDTH - 4.0
        track_y = rect.top() + 6.0
        track_h = max(0.0, rect.height() - 12.0)
        self.scrollbar_track.setRect(track_x, track_y, self.SCROLLBAR_WIDTH, track_h)
        visible = self._max_scroll_offset > 0.5 and track_h > 0
        self.scrollbar_track.setVisible(visible)
        self.scrollbar_thumb.setVisible(visible)
        if not visible:
            return
        ratio = self._content_height / max(self._document_height, self._content_height)
        thumb_h = max(self.MIN_THUMB_HEIGHT, track_h * ratio)
        travel = max(0.0, track_h - thumb_h)
        thumb_y = track_y + travel * (self._scroll_offset / self._max_scroll_offset if self._max_scroll_offset else 0.0)
        self.scrollbar_thumb.setRect(track_x, thumb_y, self.SCROLLBAR_WIDTH, thumb_h)


class NodeItem(QGraphicsRectItem):
    WIDTH = 178
    PANEL_WIDTH = 300
    PANEL_MIN_HEIGHT = 220
    HEADER = 30
    ROW = 20

    def __init__(
        self,
        node: dict,
        input_ports: list[str],
        output_ports: list[str],
        input_labels: dict[str, str] | None = None,
        output_labels: dict[str, str] | None = None,
        parent=None,
    ):
        self.is_panel = str(node.get("processor_id") or "") == "panel_node"
        self.node_width = self.PANEL_WIDTH if self.is_panel else self.WIDTH
        rows = max(len(input_ports), len(output_ports), 2)
        height = self.HEADER + rows * self.ROW + 12
        if self.is_panel:
            height = max(height, self.PANEL_MIN_HEIGHT)
        super().__init__(0, 0, self.node_width, height, parent)
        self.node = node
        self.node_id = str(node.get("id") or "")
        self.input_ports = list(input_ports)
        self.output_ports = list(output_ports)
        self.input_labels = dict(input_labels or {})
        self.output_labels = dict(output_labels or {})
        self.port_items: dict[tuple[str, str], PortItem] = {}
        self.connected_lines = []  # 缓存关联的连线，用于 O(1) 的高效拖拽重绘

        self.setPos(float(node.get("x", 0) or 0), float(node.get("y", 0) or 0))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self._build_labels()
        self.update_appearance()

    def _build_labels(self):
        title = str(self.node.get("title") or self.node.get("processor_id") or self.node.get("shortcut_id") or "节点")
        self.header_item = QGraphicsSimpleTextItem(title, self)  # 取消左上角的自动编号，使界面更精简

        font = QFont("Microsoft YaHei UI", 9)
        font.setBold(True)
        self.header_item.setFont(font)
        self.header_item.setPos(10, 7)
        self.header_item.setAcceptedMouseButtons(Qt.NoButton)

        self.input_label_items = []
        for i, port in enumerate(self.input_ports):
            y = self.HEADER + i * self.ROW + 12
            self.port_items[("input", port)] = PortItem(self.node_id, port, "input", 0, y, self)
            self.port_items[("input", port)].setToolTip(_node_port_tooltip(self.node, "input", port))
            label = QGraphicsSimpleTextItem(self.input_labels.get(port) or _port_label(port), self)
            label.setFont(QFont("Microsoft YaHei UI", 8))
            label.setPos(10, y - 8)
            label.setAcceptedMouseButtons(Qt.NoButton)
            self.input_label_items.append(label)

        self.output_label_items = []
        for i, port in enumerate(self.output_ports):
            y = self.HEADER + i * self.ROW + 12
            self.port_items[("output", port)] = PortItem(self.node_id, port, "output", self.node_width, y, self)
            self.port_items[("output", port)].setToolTip(_node_port_tooltip(self.node, "output", port))
            label = QGraphicsSimpleTextItem(self.output_labels.get(port) or _port_label(port), self)
            label.setFont(QFont("Microsoft YaHei UI", 8))
            label_rect = label.boundingRect()
            label.setPos(self.node_width - label_rect.width() - 10, y - 8)
            label.setAcceptedMouseButtons(Qt.NoButton)
            self.output_label_items.append(label)

        self.preview_item = None
        if self.is_panel:
            preview = _node_preview_text(self.node)
            rows = max(len(self.input_ports), len(self.output_ports), 2)
            top = self.HEADER + rows * self.ROW + 8
            rect = QRectF(12, top, self.node_width - 24, max(56.0, self.rect().height() - top - 12))
            self.preview_item = PanelTextViewportItem(rect, preview, self)

    def update_appearance(self):
        is_selected = self.isSelected()
        status = self.node.get("status", "")

        # 完美的 Grasshopper 电池配色方案
        if status == "failed":
            # 运行出错为红色
            bg_color = QColor("#FFCDD2")      # 淡粉红
            border_color = QColor("#D32F2F")  # 深红
            text_color = QColor("#311B92")    # 深紫/黑
            port_text_color = QColor("#5C3A21")
        elif status == "skipped":
            # 运行警告为淡黄色
            bg_color = QColor("#FFF59D")      # 淡黄色
            border_color = QColor("#FBC02D")  # 金黄
            text_color = QColor("#3E2723")    # 暗棕色
            port_text_color = QColor("#5D4037")
        elif is_selected:
            # 点击选中为更加清爽亮洁的亮白色，杜绝深灰色调带来的暗沉感
            bg_color = QColor("#FFFFFF")      # 亮白背景，轻盈明快
            border_color = QColor("#007AFF")  # 高级品牌焦点蓝，极其醒目专业
            text_color = QColor("#1C1C1E")    # 黑色文字
            port_text_color = QColor("#3A3A3C")
        else:
            # 默认灰白色
            bg_color = QColor("#ECEFF1")      # 灰白色
            border_color = QColor("#90A4AE")  # 浅灰蓝边
            text_color = QColor("#212121")    # 深灰字
            port_text_color = QColor("#607D8B")

        self.setBrush(QBrush(bg_color))
        self.setPen(QPen(border_color, 2.0 if is_selected else 1.1))

        # 实时更新文字画刷，确保无论底色如何，文字绝对清晰可读
        if hasattr(self, "header_item"):
            self.header_item.setBrush(QBrush(text_color))
        for item in getattr(self, "input_label_items", []):
            item.setBrush(QBrush(port_text_color))
        for item in getattr(self, "output_label_items", []):
            item.setBrush(QBrush(port_text_color))
        if getattr(self, "preview_item", None) is not None:
            panel_bg = QColor("#FFFFFF")
            panel_border = QColor("#B0BEC5")
            if status == "failed":
                panel_bg = QColor("#FFF5F6")
                panel_border = QColor("#EF9A9A")
            elif status == "skipped":
                panel_bg = QColor("#FFFDE7")
                panel_border = QColor("#FDD835")
            elif is_selected:
                panel_bg = QColor("#F8FBFF")
                panel_border = QColor("#90CAF9")
            self.preview_item.set_colors(panel_bg, panel_border, text_color, port_text_color)

    def scene_port_pos(self, direction: str, port_id: str) -> QPointF:
        item = self.port_items.get((direction, port_id))
        if item is None:
            return self.scenePos()
        return item.scenePos()

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # 绘制 Grasshopper 经典的精美圆角矩形电池外观
        rect = self.rect()
        painter.setBrush(self.brush())
        painter.setPen(self.pen())

        # 5.0px 优雅圆角
        painter.drawRoundedRect(rect, 5.0, 5.0)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node["x"] = float(value.x())
            self.node["y"] = float(value.y())
            # 实时高效刷新与该节点连接的所有线条路径，实现极客级拖拽实时跟随
            for item in getattr(self, "connected_lines", []):
                source = item.source_node_item
                target = item.target_node_item
                if source is not None and target is not None:
                    item.update_path(
                        source.scene_port_pos("output", str(item.connection.get("source_port") or "")),
                        target.scene_port_pos("input", str(item.connection.get("target_port") or "")),
                    )
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self.update_appearance()
        return super().itemChange(change, value)


class ConnectionItem(QGraphicsPathItem):
    def __init__(self, connection: dict, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.source_node_item = None
        self.target_node_item = None
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

    def paint(self, painter: QPainter, option, widget=None):
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
            color_end = QColor("#FF8A65")    # Soft coral
        elif is_highlighted:
            color_start = QColor("#AEEA00")  # Electric neon green
            color_end = QColor("#00E676")    # Bright flow green
        else:
            color_start = QColor("#64B5F6")  # Premium output blue
            color_end = QColor("#4DB6AC")    # Premium input teal

        # Pass 1: Drop Shadow (Soft, floating 3D depth, without harsh outlines)
        shadow_path = path.translated(0, 1.2)
        shadow_pen = QPen(QColor(0, 0, 0, 40), 4.5)
        shadow_pen.setCapStyle(Qt.RoundCap)
        shadow_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(shadow_pen)
        painter.drawPath(shadow_path)

        # Pass 2: Flowing Core Line (Linear Gradient)
        # Slightly wider (2.0px) to compensate for outline removal and ensure crispness
        grad = QLinearGradient(start_pt, end_pt)
        grad.setColorAt(0.0, color_start)
        grad.setColorAt(1.0, color_end)

        core_pen = QPen(QBrush(grad), 2.0)
        core_pen.setCapStyle(Qt.RoundCap)
        core_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(core_pen)
        painter.drawPath(path)

        painter.restore()


class ChainCanvasScene(QGraphicsScene):
    port_clicked = pyqtSignal(object)
    port_connected = pyqtSignal(object, object, bool)
    node_clicked = pyqtSignal(str)
    node_double_clicked = pyqtSignal(str)
    scene_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_source_port = None
        self._drag_path = None
        self._hovered_snap_port = None

    def _find_snap_port(self, scene_pos: QPointF, max_distance: float = 32.0) -> PortItem | None:
        """在 max_distance 像素半径内寻找最近的有效相反方向端口"""
        if self._drag_source_port is None:
            return None

        # 目标端口方向必须与拖拽源端口相反
        target_direction = "input" if self._drag_source_port.direction == "output" else "output"

        closest_port = None
        min_dist = max_distance

        for item in self.items():
            if isinstance(item, PortItem) and item.direction == target_direction:
                # 排除自连接
                if item.node_id == self._drag_source_port.node_id:
                    continue

                port_pos = item.scenePos()
                dx = scene_pos.x() - port_pos.x()
                dy = scene_pos.y() - port_pos.y()
                dist = (dx * dx + dy * dy) ** 0.5

                if dist < min_dist and self._snap_port_is_connectable(item):
                    min_dist = dist
                    closest_port = item

        return closest_port

    def _snap_port_is_connectable(self, candidate: PortItem) -> bool:
        parent = self.parent()
        can_connect = getattr(parent, "can_connect_ports", None)
        if not callable(can_connect):
            return True
        try:
            if self._drag_source_port.direction == "output":
                return bool(can_connect(self._drag_source_port, candidate))
            return bool(can_connect(candidate, self._drag_source_port))
        except Exception:
            logger.debug("端口吸附校验失败", exc_info=True)
            return False

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
        if isinstance(item, PortItem):
            self._drag_source_port = item
            self._drag_path = ConnectionItem({"id": "__preview__"})
            self.addItem(self._drag_path)

            # 保证拖拽预览线在初始化时也按逻辑流向 Output -> Input
            if item.direction == "output":
                self._drag_path.update_path(item.scenePos(), event.scenePos())
            else:
                self._drag_path.update_path(event.scenePos(), item.scenePos())

            self._hovered_snap_port = None
            self._drag_start_pos = event.scenePos()  # 记录起始位置以用于区分点击与拖拽
            event.accept()
            return
        parent = item
        while parent is not None and not isinstance(parent, NodeItem):
            parent = parent.parentItem()
        if isinstance(parent, NodeItem):
            selected_nodes = [it for it in self.selectedItems() if isinstance(it, NodeItem)]
            preserving_multi = parent.isSelected() and len(selected_nodes) > 1
            extending_selection = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            if not preserving_multi and not extending_selection:
                self.node_clicked.emit(parent.node_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_source_port is not None and self._drag_path is not None:
            mouse_pos = event.scenePos()
            snap_port = self._find_snap_port(mouse_pos, 32.0)

            # 若吸附端口发生切换，恢复旧端口状态，高亮并扩张新吸附端口（磁力拉扯效果）
            if snap_port != self._hovered_snap_port:
                if self._hovered_snap_port is not None:
                    try:
                        self._hovered_snap_port.setBrush(QBrush(self._hovered_snap_port.color))
                        self._hovered_snap_port.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
                        self._hovered_snap_port.setRect(-6, -6, 12, 12)
                    except Exception as exc:
                        logger.debug("恢复吸附端口样式失败: %s", exc, exc_info=True)

                self._hovered_snap_port = snap_port

                if snap_port is not None:
                    try:
                        # 吸附时端口变为亮色并放大，产生强烈的连接捕捉提示
                        snap_port.setBrush(QBrush(snap_port.color.lighter(125)))
                        snap_port.setPen(QPen(QColor(255, 255, 255, 240), 2.0))
                        snap_port.setRect(-8.0, -8.0, 16, 16)
                    except Exception as exc:
                        logger.debug("设置吸附端口高亮失败: %s", exc, exc_info=True)

            if self._drag_source_port.direction == "output":
                start_pt = self._drag_source_port.scenePos()
                end_pt = snap_port.scenePos() if snap_port is not None else mouse_pos
            else:
                start_pt = snap_port.scenePos() if snap_port is not None else mouse_pos
                end_pt = self._drag_source_port.scenePos()

            self._drag_path.update_path(start_pt, end_pt)

            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_source_port is not None:
            mouse_pos = event.scenePos()
            # 在释放时同样使用磁力吸附最近的有效端口连接
            target = self._find_snap_port(mouse_pos, 32.0)

            # 恢复可能有残留的吸附高亮端口
            if self._hovered_snap_port is not None:
                try:
                    self._hovered_snap_port.setBrush(QBrush(self._hovered_snap_port.color))
                    self._hovered_snap_port.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
                    self._hovered_snap_port.setRect(-6, -6, 12, 12)
                except Exception as exc:
                    logger.debug("释放时恢复吸附端口样式失败: %s", exc, exc_info=True)
                self._hovered_snap_port = None

            # 先移除拖拽预览路径，避免 port_connected 触发 _render() 导致 drag_path 被 clear() 销毁后 removeItem 报错
            if self._drag_path is not None:
                try:
                    self.removeItem(self._drag_path)
                except (RuntimeError, Exception) as exc:
                    logger.debug("移除拖拽预览路径失败: %s", exc, exc_info=True)
                self._drag_path = None

            # 检测是否是微小的点击操作（拖拽位移小于 5 像素），如果是则触发纯点击连线流程
            is_click = False
            if hasattr(self, "_drag_start_pos") and self._drag_start_pos is not None:
                dx = mouse_pos.x() - self._drag_start_pos.x()
                dy = mouse_pos.y() - self._drag_start_pos.y()
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < 5.0:
                    is_click = True
                self._drag_start_pos = None

            if is_click and target is None:
                self.port_clicked.emit(self._drag_source_port)
            elif target is not None:
                multi = bool(event.modifiers() & Qt.ControlModifier)
                try:
                    # 如果起点是输入端，我们需要把 source_port 和 target_port 调换顺序，
                    # 确保传给 _on_port_connected/后端的数据流永远是 (output_port, input_port)
                    if self._drag_source_port.direction == "output":
                        self.port_connected.emit(self._drag_source_port, target, multi)
                    else:
                        self.port_connected.emit(target, self._drag_source_port, multi)
                except Exception as e:
                    logger.exception("连接端口时出错")
                    if self.views():
                        try:
                            from ui.toast_notification import ToastNotification
                            toast = ToastNotification(self.views()[0])
                            toast.show_toast(f"连接失败: {str(e)}", theme="error", duration_ms=3000, target_widget=self.views()[0])
                        except Exception as exc:
                            logger.debug("显示连线失败提示失败: %s", exc, exc_info=True)

            self._drag_source_port = None
            event.accept()
            self.scene_released.emit()
            return
        super().mouseReleaseEvent(event)
        self.scene_released.emit()

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
        parent = item
        while parent is not None and not isinstance(parent, NodeItem):
            parent = parent.parentItem()
        if isinstance(parent, NodeItem):
            self.node_double_clicked.emit(parent.node_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
        current = item
        panel_viewport = None
        while current is not None:
            if isinstance(current, PanelTextViewportItem):
                panel_viewport = current
                break
            current = current.parentItem()
        if panel_viewport is not None and panel_viewport.scroll_by_wheel_delta(PanelTextViewportItem.wheel_delta_from_event(event)):
            event.accept()
            return
        super().wheelEvent(event)


class ChainCanvasView(QGraphicsView):
    """自定义图形视图以捕获和派发键盘事件。"""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.HighQualityAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setFrameShape(QGraphicsView.NoFrame)

    def keyPressEvent(self, event):
        widget = self.parent()
        if hasattr(widget, "handle_key_press") and widget.handle_key_press(event):
            event.accept()
            return
        super().keyPressEvent(event)


class ChainCanvasWidget(QWidget):
    canvas_changed = pyqtSignal()
    selection_changed = pyqtSignal(str)

    def __init__(self, shortcuts: dict[str, ShortcutItem], parent=None):
        super().__init__(parent)
        self.shortcuts = shortcuts
        self.canvas = {"version": 1, "nodes": [], "connections": []}
        self.node_items: dict[str, NodeItem] = {}
        self.connection_items: list[ConnectionItem] = []
        self._pending_output: tuple[str, str] | None = None
        self._pending_port = None
        self._selected_node_id = ""
        self._clipboard: dict[str, list[dict]] = {"nodes": [], "connections": []}
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._history_limit = 80

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scene = ChainCanvasScene(self)
        self.scene.setSceneRect(-80, -80, 2200, 1200)
        self.scene.port_clicked.connect(self._on_port_clicked)
        self.scene.port_connected.connect(self._on_port_connected)
        self.scene.node_clicked.connect(self.select_node)
        self.scene.node_double_clicked.connect(self._on_node_double_clicked)
        self.scene.scene_released.connect(self._sync_order_from_positions)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.view = ChainCanvasView(self.scene, self)
        layout.addWidget(self.view)

    def set_canvas(self, canvas: dict):
        self.canvas = ShortcutItem._normalize_chain_canvas(canvas, [])
        self._prune_invalid_connections()
        self._undo_stack = []
        self._redo_stack = []
        self._render()

    def set_run_status(self, run_items: list[dict], node_snapshots: dict[str, dict] | None = None):
        node_snapshots = dict(node_snapshots or {})
        nodes = sorted(self.canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
        for index, node in enumerate(nodes):
            node_id = str(node.get("id") or "")
            snapshot = node_snapshots.get(node_id)
            if snapshot:
                node["status"] = snapshot.get("status", "")
                node["last_run_snapshot"] = dict(snapshot)
                node["last_output"] = _snapshot_preview_text(snapshot)
            elif index < len(run_items):
                item = run_items[index]
                node["status"] = item.get("status", "")
                node["last_output"] = str(item.get("detail", "") or "")
                node["last_run_snapshot"] = {
                    "node_id": node_id,
                    "status": item.get("status", ""),
                    "duration": item.get("duration", 0.0),
                    "message": item.get("detail", ""),
                    "error": item.get("error", ""),
                    "inputs": {},
                    "outputs": {"output": item.get("detail", "")},
                }
            else:
                node["status"] = ""
                node["last_output"] = ""
                node.pop("last_run_snapshot", None)
        self._render()

    def get_canvas(self) -> dict:
        self._sync_order_from_positions()
        self._prune_invalid_connections()
        return ShortcutItem._normalize_chain_canvas(self.canvas, [])

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._history_snapshot())
        snapshot = self._undo_stack.pop()
        self._restore_history_snapshot(snapshot)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._history_snapshot())
        snapshot = self._redo_stack.pop()
        self._restore_history_snapshot(snapshot)
        return True

    def _history_snapshot(self) -> dict:
        return {
            "canvas": copy.deepcopy(self.canvas),
            "selected_node_id": self._selected_node_id,
        }

    def _push_history(self):
        snapshot = self._history_snapshot()
        if self._undo_stack and self._undo_stack[-1].get("canvas") == snapshot.get("canvas"):
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack = self._undo_stack[-self._history_limit :]
        self._redo_stack = []

    def _restore_history_snapshot(self, snapshot: dict):
        self.canvas = copy.deepcopy(snapshot.get("canvas") or {"version": 1, "nodes": [], "connections": []})
        self._prune_invalid_connections()
        selected_id = str(snapshot.get("selected_node_id") or "")
        node_ids = {str(node.get("id") or "") for node in self.canvas.get("nodes", [])}
        self._selected_node_id = selected_id if selected_id in node_ids else ""
        self._render()
        if self._selected_node_id:
            self.select_node(self._selected_node_id)
        else:
            self.selection_changed.emit("")
        self.canvas_changed.emit()

    def add_shortcut_node(self, shortcut: ShortcutItem):
        self._add_node({"node_type": "shortcut", "shortcut_id": shortcut.id, "title": shortcut.name or shortcut.id})

    def add_processor_node(self, processor_id: str):
        values = {"node_type": "processor", "processor_id": processor_id, "title": processor_title(processor_id)}
        if processor_id == "python_cell":
            values["source"] = DEFAULT_PYTHON_CELL_SOURCE
            values["title"] = python_cell_metadata(DEFAULT_PYTHON_CELL_SOURCE)["title"]
        self._add_node(values)

    def selected_node(self) -> dict | None:
        return self._node_by_id(self._selected_node_id)

    def update_selected_args(self, args: dict[str, str]):
        node = self.selected_node()
        if node is None:
            return
        self._push_history()
        node["args"] = {str(k): str(v) for k, v in dict(args or {}).items() if str(k).strip()}
        if str(node.get("processor_id") or "") == "panel_node":
            node["last_output"] = ""
            self._render()
            self.select_node(str(node.get("id") or ""))

    def remove_selected_node(self):
        node = self.selected_node()
        if node is None:
            return
        self._push_history()
        node_id = str(node.get("id") or "")
        self.canvas["nodes"] = [n for n in self.canvas.get("nodes", []) if str(n.get("id") or "") != node_id]
        self.canvas["connections"] = [
            c
            for c in self.canvas.get("connections", [])
            if c.get("source_node") != node_id and c.get("target_node") != node_id
        ]
        self._selected_node_id = ""
        self._render()
        self.canvas_changed.emit()
        self.selection_changed.emit("")

    def edit_selected_source(self):
        node = self.selected_node()
        if node is not None:
            self._edit_node_source(str(node.get("id") or ""))

    def disconnect_input(self, node_id: str, port_id: str):
        connections = [
            c
            for c in self.canvas.get("connections", [])
            if not (c.get("target_node") == node_id and c.get("target_port") == port_id)
        ]
        if len(connections) == len(self.canvas.get("connections", [])):
            return
        self._push_history()
        self.canvas["connections"] = connections
        self._render()
        self.canvas_changed.emit()

    def compile_steps(self) -> list[dict]:
        return compile_canvas_to_steps(self.get_canvas())

    def select_node(self, node_id: str):
        self._selected_node_id = str(node_id or "")
        self._is_selecting = True
        try:
            self.scene.clearSelection()
            for item_id, item in self.node_items.items():
                if item_id == self._selected_node_id:
                    item.setSelected(True)
        finally:
            self._is_selecting = False
        self.selection_changed.emit(self._selected_node_id)

    def _on_scene_selection_changed(self):
        if getattr(self, "_is_selecting", False):
            return
        self.scene.update()
        selected_items = [item for item in self.scene.selectedItems() if item.__class__.__name__ == "NodeItem"]

        if len(selected_items) == 1:
            node_id = selected_items[0].node_id
            if self._selected_node_id != node_id:
                self._selected_node_id = node_id
                self.selection_changed.emit(self._selected_node_id)
        elif len(selected_items) > 1:
            # 框选/多选：取最后一个被选中的节点来显示在属性面板中
            if self._selected_node_id not in [item.node_id for item in selected_items]:
                self._selected_node_id = selected_items[-1].node_id
                self.selection_changed.emit(self._selected_node_id)
        else:
            if self._selected_node_id != "":
                self._selected_node_id = ""
                self.selection_changed.emit("")

    def handle_key_press(self, event) -> bool:
        modifiers = event.modifiers()
        key = event.key()

        # 0. Ctrl + Z / Ctrl + Y / Ctrl + C / Ctrl + V: 撤销重做、复制粘贴
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_Z:
            self.undo()
            return True
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_Y:
            self.redo()
            return True
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_C:
            self.copy_selected_nodes()
            return True
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_V:
            self.paste_copied_nodes()
            return True

        # 1. Ctrl + Shift + I: 反选
        if (modifiers & Qt.ControlModifier) and (modifiers & Qt.ShiftModifier) and key == Qt.Key_I:
            for item in self.scene.items():
                if item.__class__.__name__ == "NodeItem":
                    item.setSelected(not item.isSelected())
            return True

        # 2. Ctrl + A: 全选
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_A:
            for item in self.scene.items():
                if item.__class__.__name__ == "NodeItem":
                    item.setSelected(True)
            return True

        # 3. Ctrl + D: 取消全选
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_D:
            self.scene.clearSelection()
            return True

        # 4. Delete / Backspace: 删除选中的电池组
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_nodes()
            return True

        # 5. 方向键: 批量像素微调移动选中的电池
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            selected_items = [item for item in self.scene.selectedItems() if item.__class__.__name__ == "NodeItem"]
            if selected_items:
                # 默认移动 10px，按住 Shift 或 Alt 时执行 1px 的超清像素微调
                self._push_history()
                step = 1.0 if (modifiers & (Qt.ShiftModifier | Qt.AltModifier)) else 10.0
                dx, dy = 0.0, 0.0
                if key == Qt.Key_Left:
                    dx = -step
                elif key == Qt.Key_Right:
                    dx = step
                elif key == Qt.Key_Up:
                    dy = -step
                elif key == Qt.Key_Down:
                    dy = step

                # 批量平移
                for item in selected_items:
                    item.moveBy(dx, dy)

                # 同步坐标与连线并保存
                self._sync_order_from_positions()
                self.canvas_changed.emit()
                return True

        # 6. Ctrl + L: 左对齐选中的所有电池
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_L:
            selected_items = [item for item in self.scene.selectedItems() if item.__class__.__name__ == "NodeItem"]
            if len(selected_items) > 1:
                self._push_history()
                min_x = min(item.pos().x() for item in selected_items)
                for item in selected_items:
                    item.setPos(min_x, item.pos().y())
                self._sync_order_from_positions()
                self.canvas_changed.emit()
                return True

        # 7. Ctrl + T: 上对齐选中的所有电池
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_T:
            selected_items = [item for item in self.scene.selectedItems() if item.__class__.__name__ == "NodeItem"]
            if len(selected_items) > 1:
                self._push_history()
                min_y = min(item.pos().y() for item in selected_items)
                for item in selected_items:
                    item.setPos(item.pos().x(), min_y)
                self._sync_order_from_positions()
                self.canvas_changed.emit()
                return True

        # 8. Ctrl + R: 自动整理布局
        if (modifiers & Qt.ControlModifier) and key == Qt.Key_R:
            self.auto_arrange_nodes()
            return True

        return False

    def delete_selected_nodes(self):
        selected_nodes = []
        for item in self.scene.items():
            if item.__class__.__name__ == "NodeItem" and item.isSelected():
                selected_nodes.append(item.node_id)

        if not selected_nodes:
            return

        self._push_history()
        self.canvas["nodes"] = [
            n for n in self.canvas.get("nodes", [])
            if str(n.get("id") or "") not in selected_nodes
        ]
        self.canvas["connections"] = [
            c for c in self.canvas.get("connections", [])
            if str(c.get("source_node") or "") not in selected_nodes
            and str(c.get("target_node") or "") not in selected_nodes
        ]

        if self._selected_node_id in selected_nodes:
            self._selected_node_id = ""
            self.selection_changed.emit("")

        self._render()
        self.canvas_changed.emit()

    def copy_selected_nodes(self) -> bool:
        selected_ids = [
            item.node_id
            for item in self.scene.selectedItems()
            if item.__class__.__name__ == "NodeItem"
        ]
        if not selected_ids and self._selected_node_id:
            selected_ids = [self._selected_node_id]
        selected_set = set(selected_ids)
        if not selected_set:
            self._clipboard = {"nodes": [], "connections": []}
            return False
        nodes = [
            copy.deepcopy(node)
            for node in self.canvas.get("nodes", [])
            if str(node.get("id") or "") in selected_set
        ]
        connections = [
            copy.deepcopy(connection)
            for connection in self.canvas.get("connections", [])
            if str(connection.get("source_node") or "") in selected_set
            and str(connection.get("target_node") or "") in selected_set
        ]
        self._clipboard = {"nodes": nodes, "connections": connections}
        return bool(nodes)

    def paste_copied_nodes(self) -> bool:
        nodes = list(self._clipboard.get("nodes") or [])
        if not nodes:
            return False
        self._push_history()
        id_map: dict[str, str] = {}
        existing_orders = [int(node.get("order", 0) or 0) for node in self.canvas.get("nodes", [])]
        next_order = (max(existing_orders) if existing_orders else 0) + 1
        new_nodes = []
        for offset, raw in enumerate(nodes):
            node = copy.deepcopy(raw)
            old_id = str(node.get("id") or "")
            new_id = str(uuid.uuid4())
            id_map[old_id] = new_id
            node["id"] = new_id
            node["x"] = float(node.get("x", 0) or 0) + 36.0
            node["y"] = float(node.get("y", 0) or 0) + 36.0
            node["order"] = next_order + offset
            node.pop("status", None)
            node.pop("last_output", None)
            node.pop("last_run_snapshot", None)
            new_nodes.append(node)
        new_connections = []
        for raw in list(self._clipboard.get("connections") or []):
            source = id_map.get(str(raw.get("source_node") or ""))
            target = id_map.get(str(raw.get("target_node") or ""))
            if not source or not target:
                continue
            connection = copy.deepcopy(raw)
            connection["id"] = str(uuid.uuid4())
            connection["source_node"] = source
            connection["target_node"] = target
            new_connections.append(connection)
        self.canvas.setdefault("nodes", []).extend(new_nodes)
        self.canvas.setdefault("connections", []).extend(new_connections)
        self._render()
        for node in new_nodes:
            item = self.node_items.get(str(node.get("id") or ""))
            if item is not None:
                item.setSelected(True)
        self._selected_node_id = str(new_nodes[-1].get("id") or "")
        self.selection_changed.emit(self._selected_node_id)
        self.canvas_changed.emit()
        return True

    def auto_arrange_nodes(self) -> bool:
        nodes = sorted(self.canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
        if not nodes:
            return False
        self._push_history()
        columns = 8
        x_gap = 230.0
        y_gap = 150.0
        base_x = 40.0
        base_y = 60.0
        for index, node in enumerate(nodes):
            row = index // columns
            col = index % columns
            node["order"] = index + 1
            node["x"] = base_x + col * x_gap
            node["y"] = base_y + row * y_gap
        self.canvas["nodes"] = nodes
        self._render()
        if self._selected_node_id:
            selected = self.node_items.get(self._selected_node_id)
            if selected is not None:
                selected.setSelected(True)
        self.canvas_changed.emit()
        return True

    def incoming_connection(self, node_id: str, port_id: str) -> dict | None:
        for connection in self.canvas.get("connections", []):
            if connection.get("target_node") == node_id and connection.get("target_port") == port_id:
                return connection
        return None

    def can_connect_ports(self, source_port: PortItem, target_port: PortItem) -> bool:
        if source_port is None or target_port is None:
            return False
        if source_port.direction != "output" or target_port.direction != "input":
            return False
        if source_port.node_id == target_port.node_id:
            return False
        issue = validate_canvas_connection(
            self.canvas,
            self.shortcuts,
            source_port.node_id,
            source_port.port_id,
            target_port.node_id,
            target_port.port_id,
            multi=False,
        )
        return issue is None

    def incoming_connections(self, node_id: str, port_id: str) -> list[dict]:
        return [
            connection
            for connection in self.canvas.get("connections", [])
            if connection.get("target_node") == node_id and connection.get("target_port") == port_id
        ]

    def input_ports_for_node(self, node: dict) -> list[str]:
        return node_input_ports(node, self.shortcuts)

    def input_labels_for_node(self, node: dict) -> dict[str, str]:
        return node_input_labels(node, self.shortcuts)

    def connection_source_label(self, connection: dict) -> str:
        node = self._node_by_id(str(connection.get("source_node") or ""))
        if node is None:
            return "未知来源"
        return f"{int(node.get('order', 0) or 0)}.{_port_label(str(connection.get('source_port') or ''))}"

    def _add_node(self, values: dict):
        self._push_history()
        order = len(self.canvas.get("nodes", [])) + 1

        # 始终计算视口物理中心对应的场景坐标，以实现电池节点永远在屏幕正中间出现
        node_x = float((order - 1) * 220.0)
        node_y = 80.0
        try:
            view_rect = self.view.viewport().rect()
            if view_rect.width() > 0 and view_rect.height() > 0:
                scene_center = self.view.mapToScene(view_rect.center())
                node_x = float(scene_center.x() - 178 / 2.0)
                node_y = float(scene_center.y() - 50.0)
        except Exception as exc:
            logger.debug("计算新节点默认位置失败: %s", exc, exc_info=True)

        node = {
            "id": str(uuid.uuid4()),
            "node_type": values.get("node_type", "shortcut"),
            "shortcut_id": values.get("shortcut_id", ""),
            "processor_id": values.get("processor_id", ""),
            "source": values.get("source", ""),
            "title": values.get("title", ""),
            "x": node_x,
            "y": node_y,
            "order": order,
            "enabled": True,
            "stop_on_error": True,
            "delay_ms": 0,
            "args": {},
        }
        self.canvas.setdefault("nodes", []).append(node)
        self._render()
        self.select_node(node["id"])
        self.canvas_changed.emit()

    def _render(self):
        self._is_selecting = True
        try:
            self.scene.clear()
            self.node_items = {}
            self.connection_items = []
            for node in sorted(self.canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0)):
                item = NodeItem(
                    node,
                    self.input_ports_for_node(node),
                    node_output_ports(node, self.shortcuts),
                    self.input_labels_for_node(node),
                    node_output_labels(node, self.shortcuts),
                )
                self.scene.addItem(item)
                self.node_items[item.node_id] = item
            for connection in self.canvas.get("connections", []):
                item = ConnectionItem(connection)
                item.setToolTip(self._connection_tooltip(connection))
                self.scene.addItem(item)
                self.connection_items.append(item)
            self._refresh_connection_paths()
        finally:
            self._is_selecting = False

    def _connection_tooltip(self, connection: dict) -> str:
        source = self._node_by_id(str(connection.get("source_node") or ""))
        target = self._node_by_id(str(connection.get("target_node") or ""))
        source_port = str(connection.get("source_port") or "")
        target_port = str(connection.get("target_port") or "")
        source_title = str((source or {}).get("title") or (source or {}).get("processor_id") or (source or {}).get("shortcut_id") or "来源")
        target_title = str((target or {}).get("title") or (target or {}).get("processor_id") or (target or {}).get("shortcut_id") or "目标")
        lines = [f"{source_title}.{source_port} -> {target_title}.{target_port}"]
        snapshot = dict((source or {}).get("last_run_snapshot") or {})
        if not snapshot:
            lines.append("暂无运行数据。")
            return "\n".join(lines)
        value = _snapshot_port_value(snapshot, source_port)
        if value is None:
            lines.append("上次运行未产生该端口的值。")
        else:
            lines.append(_format_debug_value(value))
        error = str(snapshot.get("error") or "")
        if error:
            lines.append(f"错误: {_clip_debug_text(error, 240)}")
        return "\n".join(lines)

    def _node_by_id(self, node_id: str) -> dict | None:
        for node in self.canvas.get("nodes", []):
            if str(node.get("id") or "") == node_id:
                return node
        return None

    def _on_port_clicked(self, port: PortItem):
        if self._pending_port is None:
            self._pending_port = port
            # 保持对原有 _pending_output 的兼容与更新
            if port.direction == "output":
                self._pending_output = (port.node_id, port.port_id)
            return

        first_port = self._pending_port
        self._pending_port = None
        self._pending_output = None

        if first_port.node_id == port.node_id:
            # 如果点击的是同一个节点/电池，则将当前端口设为第一个挂起端口
            self._pending_port = port
            if port.direction == "output":
                self._pending_output = (port.node_id, port.port_id)
            return

        # 必须是相反方向的端口才能连接
        if first_port.direction != port.direction:
            if first_port.direction == "output":
                self._connect(first_port.node_id, first_port.port_id, port.node_id, port.port_id)
            else:
                self._connect(port.node_id, port.port_id, first_port.node_id, first_port.port_id)
        else:
            # 如果方向相同，视为重新设定第一个点击端口
            self._pending_port = port
            if port.direction == "output":
                self._pending_output = (port.node_id, port.port_id)

    def show_error_toast(self, message: str):
        try:
            from ui.toast_notification import ToastNotification
            toast = ToastNotification(self)
            toast.show_toast(message, theme="error", duration_ms=3000, target_widget=self)
        except Exception:
            logger.exception("显示错误通知 Toast 失败")

    def _on_port_connected(self, source_port: PortItem, target_port: PortItem, multi: bool):
        try:
            if source_port.node_id != target_port.node_id:
                self._connect(source_port.node_id, source_port.port_id, target_port.node_id, target_port.port_id, multi=multi)
            self._pending_output = None
            self._pending_port = None
        except Exception as e:
            logger.exception("连接端口异常")
            self.show_error_toast(f"连接失败: {str(e)}")

    def _connect(self, source_node: str, source_port: str, target_node: str, target_port: str, *, multi: bool = False):
        try:
            self._sync_order_from_positions()
            issue = validate_canvas_connection(
                self.canvas,
                self.shortcuts,
                source_node,
                source_port,
                target_node,
                target_port,
                multi=multi,
            )
            if issue is not None:
                self.show_error_toast(issue.message)
                return
            current_connections = list(self.canvas.get("connections", []))
            next_connections = current_connections
            if not multi:
                next_connections = [
                    c
                    for c in current_connections
                    if not (c.get("target_node") == target_node and c.get("target_port") == target_port)
                ]
            for c in next_connections:
                if (
                    c.get("source_node") == source_node
                    and c.get("source_port") == source_port
                    and c.get("target_node") == target_node
                    and c.get("target_port") == target_port
                ):
                    return
            self._push_history()
            self.canvas["connections"] = next_connections
            self.canvas.setdefault("connections", []).append(
                {
                    "id": str(uuid.uuid4()),
                    "source_node": source_node,
                    "source_port": source_port,
                    "target_node": target_node,
                    "target_port": target_port,
                }
            )
            self._render()
            self.select_node(target_node)
            self.canvas_changed.emit()
        except Exception as e:
            logger.exception("连接并渲染异常")
            self.show_error_toast(f"连接或渲染失败: {str(e)}")

    def _prune_invalid_connections(self):
        accepted = []
        for connection in list(self.canvas.get("connections") or []):
            if not isinstance(connection, dict):
                continue
            target_node = str(connection.get("target_node") or "")
            target_port = str(connection.get("target_port") or "")
            candidate_canvas = dict(self.canvas)
            candidate_canvas["connections"] = accepted + [connection]
            multi = any(
                str(existing.get("target_node") or "") == target_node
                and str(existing.get("target_port") or "") == target_port
                for existing in accepted
            )
            issue = validate_canvas_connection(
                candidate_canvas,
                self.shortcuts,
                str(connection.get("source_node") or ""),
                str(connection.get("source_port") or ""),
                target_node,
                target_port,
                multi=multi,
            )
            if issue is None:
                accepted.append(connection)
        self.canvas["connections"] = accepted

    def _on_node_double_clicked(self, node_id: str):
        self._edit_node_source(node_id)

    def _edit_node_source(self, node_id: str):
        node = self._node_by_id(node_id)
        if (
            node is None
            or str(node.get("node_type") or "") != "processor"
            or str(node.get("processor_id") or "") != "python_cell"
        ):
            return
        source = str(node.get("source") or DEFAULT_PYTHON_CELL_SOURCE)

        # 确保同一个电池不要打开多个重复的源码卡片
        if hasattr(self, "_active_dialog") and self._active_dialog:
            try:
                self._active_dialog.reject()
            except Exception as exc:
                logger.debug("关闭已有 Python 电池源码对话框失败: %s", exc, exc_info=True)

        dialog = PythonCellSourceDialog(source, self)
        # 设为 modeless 非模态！这样用户可以自由点击“动作链”父窗口的一切内容！
        dialog.setModal(False)
        self._active_dialog = dialog

        # 极客全息虚线引线初始化
        node_item = self.node_items.get(node_id)
        if node_item:
            self._leader_lines = QGraphicsPathItem()
            self._leader_lines.setZValue(10)

            # 提取主题
            theme = "dark"
            parent = self.parent()
            while parent:
                if hasattr(parent, "theme"):
                    theme = parent.theme
                    break
                if hasattr(parent, "data_manager"):
                    theme = parent.data_manager.get_settings().theme
                    break
                parent = parent.parent()

            line_color = QColor(255, 138, 101, 150) if theme == "dark" else QColor(255, 112, 67, 130)
            pen = QPen(line_color, 1.2)
            pen.setStyle(Qt.DashLine)
            pen.setDashPattern([5, 4])
            self._leader_lines.setPen(pen)

            self.scene.addItem(self._leader_lines)

            # 实时运动与滑入动画坐标同步绑定
            dialog.moved.connect(lambda: self._update_editor_leader_lines(dialog, node_item))
            self._update_editor_leader_lines(dialog, node_item)

        def on_finished(result):
            # 安全释放清除引线，防止任何悬空对象
            if hasattr(self, "_leader_lines") and self._leader_lines:
                try:
                    self.scene.removeItem(self._leader_lines)
                except Exception as exc:
                    logger.debug("移除 Python 电池引线失败: %s", exc, exc_info=True)
                self._leader_lines = None

            self._active_dialog = None

            if result == QDialog.Accepted:
                self._push_history()
                node["processor_id"] = "python_cell"
                node["source"] = dialog.source()
                metadata = python_cell_metadata(node["source"])
                node["title"] = metadata["title"]
                valid_inputs = set(metadata["inputs"])
                self.canvas["connections"] = [
                    c
                    for c in self.canvas.get("connections", [])
                    if c.get("target_node") != node_id or c.get("target_port") in valid_inputs
                ]
                self._render()
                self.select_node(node_id)
                self.canvas_changed.emit()

        dialog.finished.connect(on_finished)
        dialog.show()

    def _update_editor_leader_lines(self, dialog: PythonCellSourceDialog, node_item: NodeItem):
        if not hasattr(self, "_leader_lines") or not self._leader_lines:
            return

        try:
            # 电池节点左上角与右下角的场景坐标
            node_tl = node_item.scenePos()
            node_w = node_item.rect().width()
            node_h = node_item.rect().height()
            node_br = node_tl + QPointF(node_w, node_h)

            # 将卡片物理屏幕坐标投射映射为动作链画布的场景坐标
            dialog_tl = self.view.mapToScene(self.view.mapFromGlobal(dialog.geometry().topLeft()))
            dialog_br = self.view.mapToScene(self.view.mapFromGlobal(dialog.geometry().bottomRight()))

            # 构造高精度的虚线投影引线路径
            path = QPainterPath()
            path.moveTo(node_tl)
            path.lineTo(dialog_tl)
            path.moveTo(node_br)
            path.lineTo(dialog_br)

            self._leader_lines.setPath(path)
        except Exception:
            logger.exception("更新编辑器全息虚线引线坐标失败")

    def _sync_order_from_positions(self):
        nodes = list(self.canvas.get("nodes", []) or [])
        for node in nodes:
            item = self.node_items.get(str(node.get("id") or ""))
            if item is not None:
                pos = item.pos()
                node["x"] = float(pos.x())
                node["y"] = float(pos.y())
        for index, node in enumerate(sorted(nodes, key=lambda n: (float(n.get("y", 0) or 0), float(n.get("x", 0) or 0))), start=1):
            node["order"] = index
        self._refresh_connection_paths()

    def _refresh_connection_paths(self):
        # 清除每个节点关联的老连线引用
        for item in self.node_items.values():
            item.connected_lines = []

        for item in self.connection_items:
            connection = item.connection
            source = self.node_items.get(str(connection.get("source_node") or ""))
            target = self.node_items.get(str(connection.get("target_node") or ""))
            if source is None or target is None:
                continue
            item.source_node_item = source
            item.target_node_item = target

            # 将连线对象双向注册到对应的节点上，以实现 O(1) 的高效拖拽刷新
            source.connected_lines.append(item)
            target.connected_lines.append(item)

            item.update_path(
                source.scene_port_pos("output", str(connection.get("source_port") or "")),
                target.scene_port_pos("input", str(connection.get("target_port") or "")),
            )

    def _node_by_id(self, node_id: str) -> dict | None:
        for node in self.canvas.get("nodes", []):
            if str(node.get("id") or "") == str(node_id or ""):
                return node
        return None


class PythonCellSourceDialog(BaseDialog):
    moved = pyqtSignal()

    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("脚本电池源码")
        self.setModal(False)
        self._setup_ui(source)
        self._apply_theme()
        self._adjust_size_to_content(source)

        # 注册全局应用事件过滤器以捕获模态独占下的点击外部事件
        from qt_compat import QApplication
        QApplication.instance().installEventFilter(self)

    def done(self, result):
        # 关闭时注销过滤器以防内存泄漏
        try:
            from qt_compat import QApplication
            QApplication.instance().removeEventFilter(self)
        except Exception as exc:
            logger.debug("移除 Python 电池源码对话框事件过滤器失败: %s", exc, exc_info=True)
        super().done(result)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.moved.emit()

    def eventFilter(self, obj, event) -> bool:
        if self._dialog_finished or not self.isVisible():
            return super().eventFilter(obj, event)

        from qt_compat import QEvent
        if event.type() == QEvent.MouseButtonPress:
            # 向上遍历父链判定是否是对话框内的交互（如右键菜单、代码补全下拉等）
            p = obj
            is_child = False
            while p:
                if p == self:
                    is_child = True
                    break
                p = p.parent()

            if not is_child:
                # 获取物理坐标
                if hasattr(event, "globalPos"):
                    pos = event.globalPos()
                elif hasattr(event, "globalPosition"):
                    pos = event.globalPosition().toPoint()
                else:
                    pos = self.mapToGlobal(event.pos())

                # 如果点击在文本框卡片外面，触发自动保存关闭并拦截此点击，提供最流畅的防干扰体验
                if not self.geometry().contains(pos):
                    from qt_compat import QTimer
                    QTimer.singleShot(50, self.accept)
                    return True
        return super().eventFilter(obj, event)

    def _adjust_size_to_content(self, source: str):
        # Use Consolas font metrics to estimate line widths and height
        font = QFont("Consolas", 9)
        font_metrics = QFontMetrics(font)

        lines = source.splitlines()
        max_line_len = 0
        for line in lines:
            expanded_line = line.replace("\t", "    ")
            if hasattr(font_metrics, 'horizontalAdvance'):
                width = font_metrics.horizontalAdvance(expanded_line)
            else:
                width = font_metrics.width(expanded_line)
            if width > max_line_len:
                max_line_len = width

        # Target width: maximum line width + text padding + layout margins
        target_width = max_line_len + 60

        # Target height: line count * line height + margins
        line_height = font_metrics.height()
        total_line_height = max(1, len(lines)) * (line_height + 3)
        target_height = total_line_height + 40

        # Enforce minimum and maximum bounds
        min_w, max_w = 640, 1000
        min_h, max_h = 320, 800

        final_w = max(min_w, min(max_w, target_width))
        final_h = max(min_h, min(max_h, target_height))

        self.resize(int(final_w), int(final_h))

    def _setup_ui(self, source: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        # 留出 12 像素的精致玻璃边缘边框
        layout.setContentsMargins(12, 12, 12, 12)

        # 代码编辑器
        self.editor = QTextEdit()
        self.editor.setPlainText(str(source or DEFAULT_PYTHON_CELL_SOURCE))
        self.editor.setPlaceholderText("在此处编写脚本电池源码...")
        # 自动让文本框获取焦点
        self.editor.setFocus()
        layout.addWidget(self.editor, 1)

    def changeEvent(self, event):
        super().changeEvent(event)
        from qt_compat import QEvent, QTimer
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                # 稍微延迟检测，防止点击右键菜单等子窗口触发误关
                QTimer.singleShot(150, self._check_should_close)

    def _check_should_close(self):
        if self._dialog_finished:
            return
        from qt_compat import QApplication
        active_win = QApplication.activeWindow()
        if active_win is None:
            self.accept()
            return

        # 沿父链向上查找，如果活跃窗口是此对话框或其子孙，则不关闭
        p = active_win
        is_child = False
        while p:
            if p == self:
                is_child = True
                break
            p = p.parent()

        if not is_child:
            self.accept()

    def reject(self):
        # 即使按 Esc 键关闭，也执行自动保存
        self.accept()

    def _apply_theme(self):
        self._apply_theme_colors()
        theme = self.theme

        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)

        if theme == "dark":
            editor_text = "#E3E6EC"
        else:
            editor_text = "#1C1C1E"

        custom_style = base_style + f"""
            QDialog {{
                background: transparent;
                border: none;
            }}
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {editor_text};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 4px;
            }}
            QTextEdit::selection {{
                background-color: rgba(100, 181, 246, 0.3);
            }}
        """
        self.setStyleSheet(custom_style)

    def source(self) -> str:
        return self.editor.toPlainText()


class NodePropertyPanel(QWidget):
    args_changed = pyqtSignal(dict)
    disconnect_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal()
    edit_source_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node: dict | None = None
        self._input_ports: list[str] = []
        self._connections: dict[str, str] = {}
        self._edits: dict[str, QWidget] = {}
        self._loading = False
        self._setup_ui()

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)

        # 封装与 "动作链属性" 一致的 QGroupBox
        self.group_box = QGroupBox("参数设置")
        self.group_layout = QVBoxLayout(self.group_box)
        self.group_layout.setSpacing(6)
        self.group_layout.setContentsMargins(8, 4, 8, 6)

        # 表单布局放置在 GroupBox 内部
        self.form = QFormLayout()
        self.form.setVerticalSpacing(10)
        self.form.setHorizontalSpacing(10)
        self.form.setContentsMargins(0, 4, 0, 4)
        self.group_layout.addLayout(self.form)
        self.layout.addWidget(self.group_box)

        self.run_box = QGroupBox("上次运行")
        self.run_layout = QVBoxLayout(self.run_box)
        self.run_layout.setSpacing(6)
        self.run_layout.setContentsMargins(8, 6, 8, 6)
        self.run_text = QTextEdit()
        self.run_text.setReadOnly(True)
        self.run_text.setMinimumHeight(120)
        self.run_text.setMaximumHeight(220)
        self.run_layout.addWidget(self.run_text)
        self.layout.addWidget(self.run_box)

        # 底部操作按钮水平排列 (参考选择图标和清除按钮样式)
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(8)
        self.btn_layout.setContentsMargins(0, 4, 0, 4)

        self.source_btn = QPushButton("编辑源码")
        self.source_btn.clicked.connect(self.edit_source_requested.emit)
        self.btn_layout.addWidget(self.source_btn)

        self.delete_btn = QPushButton("删除节点")
        self.delete_btn.clicked.connect(self.delete_requested.emit)
        self.btn_layout.addWidget(self.delete_btn)

        self.layout.addLayout(self.btn_layout)
        self.layout.addStretch()

    def _get_theme(self) -> str:
        parent = self.parent()
        while parent:
            if hasattr(parent, "theme"):
                return parent.theme
            if hasattr(parent, "data_manager"):
                return parent.data_manager.get_settings().theme
            parent = parent.parent()
        return "dark"

    def _apply_theme(self):
        theme = self._get_theme()
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"
        input_bg = "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(255, 255, 255, 0.8)"

        self.group_box.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {border_color};
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 8px;
                font-weight: 400;
                font-size: 13px;
                color: {text_primary};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: -9px;
                top: -3px;
                color: {title_color};
                font-size: 13px;
            }}
        """)
        self.run_box.setStyleSheet(self.group_box.styleSheet())

        # 统一设置表单中的 QLineEdit 样式以和动作链属性的输入框一致
        self.setStyleSheet(f"""
            QLineEdit, QTextEdit, QSpinBox, QComboBox {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 10px;
                color: {text_primary};
                font-size: 13px;
                padding: 4px 8px;
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid #5E97F6;
            }}
            QCheckBox {{
                color: {text_primary};
                font-size: 12px;
            }}
        """)

        # 按钮复用扁平操作按钮样式，使其与 "动作链属性" 的按钮视觉完全一致
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme) + """
            QPushButton {
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 400;
                min-height: 22px;
            }
        """
        self.source_btn.setStyleSheet(flat_btn_style)
        self.delete_btn.setStyleSheet(flat_btn_style)

    def load_node(self, node: dict | None, input_ports: list[str], connections: dict[str, str]):
        self._clear_form()
        self._node = node
        self._input_ports = list(input_ports)
        self._connections = dict(connections)
        self._edits = {}

        # 实时同步最新主题配色
        self._apply_theme()

        if node is None:
            self.group_box.setTitle("未选择节点")
            self.run_box.setVisible(False)
            placeholder_color = "rgba(255, 255, 255, 0.45)" if self._get_theme() == "dark" else "rgba(0, 0, 0, 0.45)"
            placeholder = QLabel("请在左侧画布选择一个节点。")
            placeholder.setStyleSheet(f"color: {placeholder_color}; font-size: 12px; font-weight: 400;")
            self.form.addRow(placeholder)
            self.delete_btn.setEnabled(False)
            self.source_btn.setEnabled(False)
            return

        self.delete_btn.setEnabled(True)
        self.run_box.setVisible(True)
        self.source_btn.setEnabled(
            str(node.get("node_type") or "") == "processor" and str(node.get("processor_id") or "") == "python_cell"
        )

        # 动态将节点标题设为 GroupBox 的 Title
        title_text = str(node.get("title") or node.get("processor_id") or node.get("shortcut_id") or "参数设置")
        self.group_box.setTitle(title_text)

        args = dict(node.get("args") or {})
        param_defs = _processor_param_definitions(node)
        self._loading = True
        try:
            for port in self._input_ports:
                param_def = param_defs.get(port, {})
                # 表单左侧加冒号，完全参考 "动作链属性" 里的文字内容排列风格
                lbl_text = str(param_def.get("label") or _port_label(port)) + ":"

                label_widget = QLabel(lbl_text)
                label_widget.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        font-weight: 400;
                    }
                """)

                if port in self._connections:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(6)

                    label = QLabel(self._connections[port])
                    label.setWordWrap(True)
                    label.setStyleSheet("""
                        QLabel {
                            background-color: rgba(100, 181, 246, 0.12);
                            border: 1px solid rgba(100, 181, 246, 0.25);
                            border-radius: 4px;
                            padding: 4px 8px;
                            color: #64B5F6;
                            font-size: 11px;
                        }
                    """)

                    clear = QPushButton("断开")
                    clear.setFixedSize(48, 22)
                    clear.setCursor(Qt.PointingHandCursor)
                    clear.clicked.connect(lambda _=False, p=port: self.disconnect_requested.emit(str(node.get("id") or ""), p))
                    clear.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(220, 38, 38, 0.1);
                            border: 1px solid rgba(220, 38, 38, 0.25);
                            border-radius: 4px;
                            color: #F87171;
                            font-size: 11px;
                            padding: 0;
                            margin: 0;
                            text-align: center;
                        }
                        QPushButton:hover {
                            background-color: rgba(220, 38, 38, 0.22);
                            border: 1px solid rgba(220, 38, 38, 0.45);
                            color: #FF8787;
                        }
                    """)
                    clear.raise_()

                    row_layout.addWidget(label, 1)
                    row_layout.addWidget(clear)
                    self.form.addRow(label_widget, row)
                else:
                    value = str(args.get(port) if port in args else param_def.get("default", ""))
                    edit = self._create_param_editor(node, port, param_def, value)
                    self._edits[port] = edit
                    self.form.addRow(label_widget, edit)
            self._load_run_snapshot(node)
        finally:
            self._loading = False

    def _emit_args(self):
        if self._loading:
            return
        args = {}
        for port, edit in self._edits.items():
            value = self._editor_value(edit)
            if value:
                args[port] = value
        if self._node is not None:
            for key, value in dict(self._node.get("args") or {}).items():
                if key not in self._input_ports and value:
                    args[key] = value
        self.args_changed.emit(args)

    def _clear_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)

    def _create_param_editor(self, node: dict, port: str, param_def: dict, value: str) -> QWidget:
        kind = str(param_def.get("kind") or "").lower().strip()
        choices = [str(choice) for choice in list(param_def.get("choices") or [])]
        placeholder = str(param_def.get("placeholder") or "")
        description = str(param_def.get("description") or "")
        if choices or kind == "choice":
            edit = QComboBox()
            for choice in choices:
                edit.addItem(choice)
            if value and edit.findText(value) < 0:
                edit.addItem(value)
            if value:
                edit.setCurrentText(value)
            edit.currentTextChanged.connect(self._emit_args)
        elif kind == "bool":
            edit = QCheckBox()
            edit.setChecked(str(value or "").strip().lower() in {"1", "true", "yes", "on", "是", "真"})
            edit.stateChanged.connect(self._emit_args)
        elif kind == "number":
            edit = QSpinBox()
            edit.setButtonSymbols(QSpinBox.NoButtons)
            edit.setRange(-1_000_000, 1_000_000)
            try:
                edit.setValue(int(float(value or "0")))
            except Exception:
                edit.setValue(0)
            edit.valueChanged.connect(self._emit_args)
        elif kind in {"file", "folder"}:
            edit = self._create_path_editor(port, value, kind)
        elif kind in {"textarea", "json", "list"} or _is_multiline_port(node, port):
            edit = QTextEdit()
            edit.setPlainText(value)
            edit.setMinimumHeight(92 if kind in {"json", "list"} else 82)
            edit.textChanged.connect(self._emit_args)
        else:
            edit = QLineEdit()
            edit.setText(value)
            edit.setMinimumHeight(28)
            edit.textChanged.connect(self._emit_args)
        if hasattr(edit, "setPlaceholderText") and placeholder:
            edit.setPlaceholderText(placeholder)
        if description:
            edit.setToolTip(description)
        return edit

    def _create_path_editor(self, port: str, value: str, kind: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        edit = QLineEdit()
        edit.setText(value)
        edit.setMinimumHeight(28)
        edit.textChanged.connect(self._emit_args)
        browse = QPushButton("...")
        browse.setFixedSize(34, 26)
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(lambda _=False, p=port, k=kind, e=edit: self._browse_path(p, k, e))
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse)
        row._value_edit = edit
        return row

    def _browse_path(self, port: str, kind: str, edit: QLineEdit):
        if kind == "folder":
            path = get_existing_directory(self, "选择文件夹", edit.text().strip())
        else:
            path, _ = get_open_file_name(self, "选择文件", edit.text().strip())
        if path:
            edit.setText(path)

    def _editor_value(self, edit: QWidget) -> str:
        if isinstance(edit, QTextEdit):
            return edit.toPlainText()
        if isinstance(edit, QLineEdit):
            return edit.text()
        if isinstance(edit, QComboBox):
            return edit.currentText()
        if isinstance(edit, QCheckBox):
            return "true" if edit.isChecked() else "false"
        if isinstance(edit, QSpinBox):
            return str(edit.value())
        nested = getattr(edit, "_value_edit", None)
        if isinstance(nested, QLineEdit):
            return nested.text()
        if hasattr(edit, "toPlainText"):
            return edit.toPlainText()
        if hasattr(edit, "text"):
            return edit.text()
        return ""

    def _load_run_snapshot(self, node: dict):
        snapshot = dict(node.get("last_run_snapshot") or {})
        if not snapshot:
            self.run_text.setPlainText("暂无运行数据。")
            return
        lines = []
        status = str(snapshot.get("status") or "")
        duration = float(snapshot.get("duration") or 0.0)
        if status:
            lines.append(f"状态: {status}")
        if duration > 0:
            lines.append(f"耗时: {duration:.3f}s")
        message = str(snapshot.get("message") or "")
        error = str(snapshot.get("error") or "")
        if message:
            lines.append("")
            lines.append("消息:")
            lines.append(_clip_debug_text(message))
        if error:
            lines.append("")
            lines.append("错误:")
            lines.append(_clip_debug_text(error))
        inputs = dict(snapshot.get("typed_inputs") or snapshot.get("inputs") or {})
        outputs = dict(snapshot.get("typed_outputs") or snapshot.get("outputs") or {})
        if inputs:
            lines.append("")
            lines.append("输入:")
            lines.extend(_format_debug_mapping(inputs))
        if outputs:
            lines.append("")
            lines.append("输出:")
            lines.extend(_format_debug_mapping(outputs))
        self.run_text.setPlainText("\n".join(lines) if lines else "暂无运行数据。")


def processor_library_items() -> list[tuple[str, str]]:
    return [(definition.id, definition.title) for definition in processor_definitions()]


def _port_label(port: str) -> str:
    labels = {
        "input": "输入值",
        "open_file": "待打开文件",
        "success": "成功状态",
        "output": "主输出",
        "stdout": "标准输出",
        "stderr": "标准错误",
        "exit_code": "退出码",
        "error": "错误信息",
        "files.0": "结果文件[0]",
        "folders.0": "结果文件夹[0]",
        "urls.0": "结果 URL[0]",
        "template": "模板",
        "text": "字符串值",
        "find": "查找",
        "replace": "替换为",
        "start": "开始",
        "end": "结束",
        "json": "JSON 数据",
        "path": "路径",
        "folder": "文件夹",
        "filename": "文件名",
        "stem": "主文件名",
        "extension": "扩展名",
        "pattern": "正则",
        "group": "分组",
        "message": "提示",
        "value": "值",
        "type": "类型",
        "compare": "比较",
        "target": "目标",
        "level": "级别",
        "ms": "毫秒",
        "a": "甲",
        "b": "乙",
        "c": "丙",
        "d": "丁",
        "e": "戊",
        "operator": "判断方式",
        "condition": "条件",
        "true_value": "为真时",
        "false_value": "为假时",
        "count": "次数",
        "delimiter": "分隔符",
        "base": "底数",
        "exp": "指数",
        "ratio": "比例",
        "from_base": "原进制",
        "to_base": "目标进制",
        "number": "数字",
        "list": "列表",
        "index": "索引",
        "filepath": "文件路径",
        "width": "宽度",
        "height": "高度",
        "format": "格式",
        "position": "位置",
        "angle": "角度",
        "url": "URL",
        "headers": "请求头",
        "data": "数据",
        "json_str": "JSON 字符串",
        "mode": "模式",
        "save_dir": "保存目录",
        "fallback": "兜底值",
        "empty": "是否为空",
        "exists": "是否存在",
        "not": "取反",
        "length": "长度",
        "items_json": "列表数据",
        "first": "首项",
        "last": "末项",
        "contains": "包含",
        "exclude": "排除",
        "encoding": "编码",
        "true": "真",
        "false": "假",
    }
    return labels.get(str(port), str(port))


def _is_multiline_port(node: dict, port: str) -> bool:
    processor_id = str(node.get("processor_id") or "")
    return processor_id in {"panel_node", "text_input", "text_template", "file_write_text"} and port in {
        "text",
        "template",
        "input",
    }


def _processor_param_definitions(node: dict) -> dict[str, dict]:
    if str(node.get("node_type") or "") != "processor":
        return {}
    definition = processor_definition(str(node.get("processor_id") or ""))
    if definition is None:
        return {}
    return {param.id: param.to_dict() for param in definition.params}


def _node_preview_text(node: dict) -> str:
    text = str(node.get("last_output") or "")
    if not text:
        args = dict(node.get("args") or {})
        text = str(args.get("text") or args.get("input") or "")
    if not text:
        return "（空）"
    normalized = text.replace("\r\n", "\n")
    max_total_chars = 20000
    if len(normalized) > max_total_chars:
        return normalized[:max_total_chars] + f"\n（已截断，原 {len(normalized)} 字）"
    return normalized


def _snapshot_preview_text(snapshot: dict) -> str:
    outputs = dict(snapshot.get("outputs") or {})
    for key in ("output", "stdout", "text"):
        value = str(outputs.get(key) or "")
        if value:
            return value
    message = str(snapshot.get("message") or "")
    if message:
        return message
    error = str(snapshot.get("error") or "")
    return error


def _format_debug_mapping(values: dict) -> list[str]:
    lines = []
    for key, value in dict(values or {}).items():
        text = _clip_debug_text(_format_debug_value(value))
        if "\n" in text:
            lines.append(f"- {key}:")
            for line in text.splitlines():
                lines.append(f"  {line}")
        else:
            lines.append(f"- {key}: {text}")
    return lines


def _snapshot_port_value(snapshot: dict, port: str):
    return _snapshot_debug_port_value(snapshot, "output", port)


def _snapshot_debug_port_value(snapshot: dict, direction: str, port: str):
    typed_key = "typed_inputs" if str(direction or "") == "input" else "typed_outputs"
    plain_key = "inputs" if str(direction or "") == "input" else "outputs"
    typed_outputs = dict(snapshot.get(typed_key) or {})
    outputs = dict(snapshot.get(plain_key) or {})
    port = str(port or "")
    if port in typed_outputs:
        return typed_outputs[port]
    if port in outputs:
        return outputs[port]
    if "." in port:
        group, _, index_text = port.partition(".")
        try:
            index = int(index_text)
        except (TypeError, ValueError):
            return None
        typed_group = typed_outputs.get(group)
        if isinstance(typed_group, dict):
            values = typed_group.get("value")
            if isinstance(values, list) and 0 <= index < len(values):
                return values[index]
        raw_group = outputs.get(group)
        if isinstance(raw_group, list) and 0 <= index < len(raw_group):
            return raw_group[index]
    return None


def _node_port_tooltip(node: dict, direction: str, port: str) -> str:
    label = _port_label(port)
    direction_label = "输入" if str(direction or "") == "input" else "输出"
    kind = _port_kind_for_node(node, direction, port)
    lines = [f"{direction_label}端口: {label} ({port})"]
    if kind:
        lines.append(f"数据类型: {_debug_kind_label(kind)}")
    role = _port_role_for_node(node, direction, port)
    if role:
        lines.append(f"端口角色: {_debug_role_label(role)}")
    description = _port_description_for_node(node, direction, port)
    if description:
        lines.append(description)
    snapshot = dict(node.get("last_run_snapshot") or {})
    if not snapshot:
        lines.append("暂无运行数据。")
        return "\n".join(lines)
    value = _snapshot_debug_port_value(snapshot, direction, port)
    if value is None:
        lines.append("上次运行未记录该端口的值。")
    else:
        lines.append(_format_debug_value(value))
    error = str(snapshot.get("error") or "")
    if error:
        lines.append(f"错误: {_clip_debug_text(error, 240)}")
    return "\n".join(lines)


def _format_debug_value(value) -> str:
    if isinstance(value, dict) and "kind" in value:
        kind = str(value.get("kind") or "")
        preview = str(value.get("preview") or value.get("text") or value.get("value") or "")
        return f"[{_debug_kind_label(kind)}] {preview}" if kind else preview
    return "" if value is None else str(value)


def _debug_kind_label(kind: str) -> str:
    labels = {
        "any": "任意",
        "text": "字符串",
        "json": "JSON/结构化",
        "file": "文件",
        "folder": "文件夹",
        "url": "URL",
        "list": "列表",
        "number": "数字",
        "bool": "布尔(1/0)",
    }
    return labels.get(str(kind or ""), str(kind or ""))


def _port_kind_for_node(node: dict, direction: str, port: str) -> str:
    spec = _port_spec_for_node(node, direction, port)
    return str(getattr(spec, "kind", "") or "")


def _port_role_for_node(node: dict, direction: str, port: str) -> str:
    spec = _port_spec_for_node(node, direction, port)
    return str(getattr(spec, "role", "") or "")


def _port_description_for_node(node: dict, direction: str, port: str) -> str:
    spec = _port_spec_for_node(node, direction, port)
    description = str(getattr(spec, "description", "") or "")
    if description:
        return description
    fallback = {
        "success": "布尔状态。成功为 1/true，失败为 0/false。",
        "output": "主输出值；具体含义由电池或快捷方式决定。",
        "error": "失败时的错误说明；成功时通常为空。",
        "stdout": "命令进程写入 stdout 的字符串。",
        "stderr": "命令进程写入 stderr 的字符串。",
        "exit_code": "命令进程退出码，通常 0 表示成功。",
        "files.0": "结果文件集合的第 0 项。来自执行结果或从输出文本中识别出的文件路径。",
        "folders.0": "结果文件夹集合的第 0 项。来自执行结果或从输出文本中识别出的文件夹路径。",
        "urls.0": "结果 URL 集合的第 0 项。来自快捷方式目标或从输出文本中识别出的 URL。",
    }
    return fallback.get(str(port or ""), "")


def _port_spec_for_node(node: dict, direction: str, port: str):
    try:
        shortcuts = {}
        specs = (
            input_port_specs_for_node(node, shortcuts)
            if str(direction or "") == "input"
            else output_port_specs_for_node(node, shortcuts)
        )
        return next((spec for spec in specs if spec.id == port), None)
    except Exception:
        return None


def _debug_role_label(role: str) -> str:
    labels = {
        "primary": "主数据",
        "data": "数据",
        "status": "状态",
        "diagnostic": "诊断",
        "collection": "集合项",
        "metadata": "元数据",
        "stream": "流输出",
        "control": "控制参数",
        "parameter": "参数",
    }
    return labels.get(str(role or ""), str(role or ""))


def _clip_debug_text(value, limit: int = 800) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n")
    if len(text) > limit:
        return text[:limit] + f"...（已截断，原 {len(text)} 字）"
    return text
