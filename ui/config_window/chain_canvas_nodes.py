"""Node-canvas editor primitives for action chains."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.chain_contracts import (
    binding_key,
    input_port_specs_for_node,
    output_port_specs_for_node,
)
from core.chain_processors import (
    DEFAULT_PYTHON_CELL_SOURCE,
    processor_title,
    python_cell_metadata,
)
from core.data_models import ShortcutItem, normalize_chain_step_delay_ms
from qt_compat import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QPainter,
    QPointF,
    QRectF,
    Qt,
    QtCompat,
    QTextOption,
)
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import font_px, sp, spf

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
        step: dict[str, Any] = {
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
                param_bindings = step["param_bindings"]
                args = step["args"]
                assert isinstance(param_bindings, dict)
                assert isinstance(args, dict)
                existing = param_bindings.get(target_port)
                param_bindings[target_port] = _append_binding(existing, binding)
                args.pop(target_port, None)
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


def _ensure_helpers() -> None:
    return


def _port_label(port: str) -> str:
    return str(port or "").replace("_", " ")


def _node_preview_text(node: dict) -> str:
    text = str(node.get("last_output") or "")
    if not text:
        args = dict(node.get("args") or {})
        text = str(args.get("text") or args.get("input") or "")
    return text or "（空）"


def _node_port_tooltip(node: dict, direction: str, port: str) -> str:
    direction_label = "输入" if direction == "input" else "输出"
    return f"{direction_label}端口: {_port_label(port)} ({port})"


class PortItem(QGraphicsEllipseItem):
    def __init__(self, node_id: str, port_id: str, direction: str, x: float, y: float, parent=None):
        super().__init__(-sp(6), -sp(6), sp(12), sp(12), parent)
        self.node_id = node_id
        self.port_id = port_id
        self.direction = direction
        self.setPos(x, y)
        self.color = QColor("#4DB6AC") if direction == "input" else QColor("#64B5F6")
        self.setBrush(QBrush(self.color))
        pen_color = QColor(Qt.white)
        pen_color.setAlpha(150)
        self.setPen(make_cosmetic_pen(pen_color, 1.2, 1))
        self.setCursor(Qt.PointingHandCursor)  # type: ignore[unused-ignore, attr-defined]
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(self.color.lighter(115)))
        pen_color = QColor(Qt.white)
        pen_color.setAlpha(230)
        self.setPen(make_cosmetic_pen(pen_color, 1.8, 1))
        self.setRect(-spf(7.5), -spf(7.5), spf(15), spf(15))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(self.color))
        pen_color = QColor(Qt.white)
        pen_color.setAlpha(150)
        self.setPen(make_cosmetic_pen(pen_color, 1.2, 1))
        self.setRect(-sp(6), -sp(6), sp(12), sp(12))
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

        self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)  # type: ignore[unused-ignore, attr-defined]
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.NoButton)  # type: ignore[unused-ignore, attr-defined]

        self.text_item = QGraphicsTextItem(self)
        self.text_item.setFont(QFont("Microsoft YaHei UI", font_px(8)))
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)  # type: ignore[unused-ignore, attr-defined]

        option = self.text_item.document().defaultTextOption()  # type: ignore[unused-ignore, union-attr]
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text_item.document().setDefaultTextOption(option)  # type: ignore[unused-ignore, union-attr]

        self.scrollbar_track = QGraphicsRectItem(self)
        self.scrollbar_track.setAcceptedMouseButtons(Qt.NoButton)  # type: ignore[unused-ignore, attr-defined]
        self.scrollbar_track.setPen(make_cosmetic_pen(Qt.NoPen, 1))  # type: ignore[unused-ignore, attr-defined]
        self.scrollbar_track.setZValue(2)

        self.scrollbar_thumb = QGraphicsRectItem(self)
        self.scrollbar_thumb.setAcceptedMouseButtons(Qt.NoButton)  # type: ignore[unused-ignore, attr-defined]
        self.scrollbar_thumb.setPen(make_cosmetic_pen(Qt.NoPen, 1))  # type: ignore[unused-ignore, attr-defined]
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
        self.setPen(make_cosmetic_pen(border, 1.0, 1))
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
        self.node_width = sp(self.PANEL_WIDTH) if self.is_panel else sp(self.WIDTH)
        rows = max(len(input_ports), len(output_ports), 2)
        height = sp(self.HEADER) + rows * sp(self.ROW) + sp(12)
        if self.is_panel:
            height = max(height, sp(self.PANEL_MIN_HEIGHT))
        super().__init__(0, 0, self.node_width, height, parent)
        self.node = node
        self.node_id = str(node.get("id") or "")
        self.input_ports = list(input_ports)
        self.output_ports = list(output_ports)
        self.input_labels = dict(input_labels or {})
        self.output_labels = dict(output_labels or {})
        self.port_items: dict[tuple[str, str], PortItem] = {}
        self.connected_lines = []  # type: ignore[var-annotated]  # 缓存关联的连线，用于 O(1) 的高效拖拽重绘

        self.setPos(float(node.get("x", 0) or 0), float(node.get("y", 0) or 0))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore[unused-ignore, attr-defined]
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)  # type: ignore[unused-ignore, attr-defined]
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)  # type: ignore[unused-ignore, attr-defined]
        _ensure_helpers()

        self._build_labels()
        self.update_appearance()

    def _build_labels(self):
        title = str(self.node.get("title") or self.node.get("processor_id") or self.node.get("shortcut_id") or "节点")
        self.header_item = QGraphicsSimpleTextItem(title, self)  # 取消左上角的自动编号，使界面更精简

        font = QFont("Microsoft YaHei UI", font_px(9))
        font.setBold(True)
        self.header_item.setFont(font)
        self.header_item.setPos(sp(8), sp(7))
        self.header_item.setAcceptedMouseButtons(Qt.NoButton)

        self.input_label_items = []
        for i, port in enumerate(self.input_ports):
            y = sp(self.HEADER) + i * sp(self.ROW) + sp(12)
            self.port_items[("input", port)] = PortItem(self.node_id, port, "input", 0, y, self)
            self.port_items[("input", port)].setToolTip(_node_port_tooltip(self.node, "input", port))
            label = QGraphicsSimpleTextItem(self.input_labels.get(port) or _port_label(port), self)
            label.setFont(QFont("Microsoft YaHei UI", font_px(8)))
            label.setPos(sp(8), y - sp(8))
            label.setAcceptedMouseButtons(Qt.NoButton)
            self.input_label_items.append(label)

        self.output_label_items = []
        for i, port in enumerate(self.output_ports):
            y = sp(self.HEADER) + i * sp(self.ROW) + sp(12)
            self.port_items[("output", port)] = PortItem(self.node_id, port, "output", self.node_width, y, self)
            self.port_items[("output", port)].setToolTip(_node_port_tooltip(self.node, "output", port))
            label = QGraphicsSimpleTextItem(self.output_labels.get(port) or _port_label(port), self)
            label.setFont(QFont("Microsoft YaHei UI", font_px(8)))
            label_rect = label.boundingRect()
            label.setPos(self.node_width - label_rect.width() - sp(8), y - sp(8))
            label.setAcceptedMouseButtons(Qt.NoButton)
            self.output_label_items.append(label)

        self.preview_item = None
        if self.is_panel:
            preview = _node_preview_text(self.node)
            rows = max(len(self.input_ports), len(self.output_ports), 2)
            top = sp(self.HEADER) + rows * sp(self.ROW) + sp(8)
            rect = QRectF(sp(12), top, self.node_width - sp(24), max(spf(56.0), self.rect().height() - top - sp(12)))
            self.preview_item = PanelTextViewportItem(rect, preview, self)

    def update_appearance(self):
        is_selected = self.isSelected()
        status = self.node.get("status", "")

        # 完美的 Grasshopper 电池配色方案
        if status == "failed":
            # 运行出错为红色
            bg_color = QColor("#FFCDD2")  # 淡粉红
            border_color = QColor("#D32F2F")  # 深红
            text_color = QColor("#311B92")  # 深紫/黑
            port_text_color = QColor("#5C3A21")
        elif status == "skipped":
            # 运行警告为淡黄色
            bg_color = QColor("#FFF59D")  # 淡黄色
            border_color = QColor("#FBC02D")  # 金黄
            text_color = QColor("#3E2723")  # 暗棕色
            port_text_color = QColor("#5D4037")
        elif is_selected:
            # 点击选中为更加清爽亮洁的亮白色，杜绝深灰色调带来的暗沉感
            bg_color = QColor("#FFFFFF")  # 亮白背景，轻盈明快
            border_color = QColor("#007AFF")  # 高级品牌焦点蓝，极其醒目专业
            text_color = QColor("#1C1C1E")  # 黑色文字
            port_text_color = QColor("#3A3A3C")
        else:
            # 默认灰白色
            bg_color = QColor("#ECEFF1")  # 灰白色
            border_color = QColor("#90A4AE")  # 浅灰蓝边
            text_color = QColor("#212121")  # 深灰字
            port_text_color = QColor("#607D8B")

        self.setBrush(QBrush(bg_color))
        self.setPen(make_cosmetic_pen(border_color, 2.0 if is_selected else 1.1, 1))

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

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[unused-ignore, override]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        # 绘制 Grasshopper 经典的精美圆角矩形电池外观
        rect = self.rect()
        painter.setBrush(self.brush())
        painter.setPen(self.pen())

        # 5.0px 优雅圆角
        painter.drawRoundedRect(rect, spf(5.0), spf(5.0))
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
