"""Command settings page — favorites and builtin command management."""

from __future__ import annotations

import logging

from core.i18n import tr
from qt_compat import (
    QColor,
    QDrag,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPen,
    QPixmap,
    QPoint,
    QPushButton,
    QRectF,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_font_css_with_size
from ui.utils.ui_scale import scale_qss, sp

logger = logging.getLogger(__name__)


class DragDropListWidget(QListWidget):
    def __init__(self, parent=None, theme="dark", on_reordered_callback=None, on_drag_finished_callback=None):
        super().__init__(parent)
        self.theme = theme
        self.on_reordered_callback = on_reordered_callback
        self.on_drag_finished_callback = on_drag_finished_callback
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # Completely disable default drop indicator to remove the thin black/blue line!
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QListWidget.InternalMove)

        self._initial_drag_row = -1

        # Transparent background and zero focus outlines
        self.setStyleSheet(
            scale_qss(
                """
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
                padding: 0px;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 0px;
                margin-bottom: 6px;
            }
            QListWidget::item:hover {
                background: transparent;
            }
            QListWidget::item:selected {
                background: transparent;
            }
        """
            )
        )

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if not item:
            return

        widget = self.itemWidget(item)
        if not widget:
            return

        # Record the initial row at the start of the drag
        self._initial_drag_row = self.row(item)

        drag = QDrag(self)

        # Grab high-fidelity snapshot of the item card widget
        pixmap = widget.grab()
        w = pixmap.width()
        h = pixmap.height()

        transparent_pixmap = QPixmap(w, h)
        transparent_pixmap.fill(QtCompat.transparent)

        painter = QPainter(transparent_pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setOpacity(0.75)  # Floating glass translucent card
        painter.drawPixmap(0, 0, pixmap)

        # Soft fresh mint overlay border around the preview
        painter.setOpacity(0.9)
        if self.theme == "dark":
            border_color = QColor(168, 230, 207, 150)
        else:
            border_color = QColor(70, 180, 140, 220)

        pen = QPen(border_color, 1.5)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        painter.end()

        mime_data = self.model().mimeData(self.selectedIndexes())

        drag.setMimeData(mime_data)
        drag.setPixmap(transparent_pixmap)
        drag.setHotSpot(QPoint(w // 2, h // 2))

        # Dim the source widget in the list during drag for dynamic feedback
        try:
            opacity_effect = QGraphicsOpacityEffect(widget)
            opacity_effect.setOpacity(0.35)
            widget.setGraphicsEffect(opacity_effect)
        except Exception:
            opacity_effect = None

        try:
            drag.exec_(supported_actions)
        finally:
            # If the drag was cancelled or finished, restore full opacity
            try:
                widget.setGraphicsEffect(None)
            except Exception as exc:
                logger.debug("清除图形效果失败: %s", exc, exc_info=True)

            # ALWAYS trigger the drag-finished callback to cleanly refresh the entire UI list and prevent disappearing widgets!
            if self.on_drag_finished_callback:
                self.on_drag_finished_callback()

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() != self:
            event.ignore()
            return

        event.acceptProposedAction()

        # Find target item under the cursor
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(pos)

        if not index.isValid():
            return

        dest_row = index.row()
        source_item = self.currentItem()
        if not source_item:
            return

        source_row = self.row(source_item)

        # Dynamic real-time Apple-style card swapping reorder
        if source_row != dest_row:
            # Record old positions of all visible widgets in the list (use id(it) as key because QListWidgetItem is unhashable)
            old_positions = {}
            for r in range(self.count()):
                it = self.item(r)
                try:
                    w = self.itemWidget(it)
                    if w:
                        old_positions[id(it)] = w.pos()
                except RuntimeError:
                    logger.debug("拖拽时获取列表项控件位置失败", exc_info=True)

            try:
                widget = self.itemWidget(source_item)
            except RuntimeError:
                widget = None

            self.blockSignals(True)
            try:
                # Unparent the widget to protect it from C++ deletion during takeItem!
                if widget:
                    self.removeItemWidget(source_item)

                self.takeItem(source_row)
                self.insertItem(dest_row, source_item)

                if widget:
                    self.setItemWidget(source_item, widget)
                    # Force set size hint of the item to invalidate layout cache on the first swap!
                    widget_size = widget.sizeHint()
                    widget_size.setHeight(widget_size.height() + 4)
                    source_item.setSizeHint(widget_size)
                    widget.show()  # Ensure visible inside viewport!
                self.setCurrentItem(source_item)
            except RuntimeError:
                logger.debug("拖拽重排序列表项失败", exc_info=True)
            finally:
                self.blockSignals(False)

            # Force layout recalculation
            self.doItemsLayout()

            # Trigger QPropertyAnimation for all shifted items
            from qt_compat import QEasingCurve, QPropertyAnimation

            for r in range(self.count()):
                it = self.item(r)
                try:
                    w = self.itemWidget(it)
                except RuntimeError:
                    w = None

                if w and id(it) in old_positions:
                    old_pos = old_positions[id(it)]
                    try:
                        new_pos = w.pos()
                        if old_pos != new_pos:
                            # Stop active animation to prevent conflicts
                            if hasattr(w, "_pos_anim") and w._pos_anim is not None:
                                w._pos_anim.stop()

                            anim = QPropertyAnimation(w, b"pos")
                            anim.setDuration(180)  # 180ms responsive slide
                            anim.setStartValue(old_pos)
                            anim.setEndValue(new_pos)
                            anim.setEasingCurve(QEasingCurve.OutCubic)
                            w._pos_anim = anim
                            anim.start()
                    except RuntimeError:
                        logger.debug("拖拽移动时启动位置动画失败", exc_info=True)

    def dragLeaveEvent(self, event):
        # If drag left, restore position to initial row
        source_item = self.currentItem()
        if source_item and self._initial_drag_row >= 0:
            current_row = self.row(source_item)
            if current_row != self._initial_drag_row:
                old_positions = {}
                for r in range(self.count()):
                    it = self.item(r)
                    try:
                        w = self.itemWidget(it)
                        if w:
                            old_positions[id(it)] = w.pos()
                    except RuntimeError:
                        logger.debug("拖拽离开时获取列表项控件位置失败", exc_info=True)

                try:
                    widget = self.itemWidget(source_item)
                except RuntimeError:
                    widget = None

                self.blockSignals(True)
                try:
                    if widget:
                        self.removeItemWidget(source_item)

                    self.takeItem(current_row)
                    self.insertItem(self._initial_drag_row, source_item)
                    if widget:
                        self.setItemWidget(source_item, widget)
                        # Force set size hint of the item to invalidate layout cache on the first swap!
                        widget_size = widget.sizeHint()
                        widget_size.setHeight(widget_size.height() + 4)
                        source_item.setSizeHint(widget_size)
                        widget.show()  # Ensure visible inside viewport!
                    self.setCurrentItem(source_item)
                except RuntimeError:
                    logger.debug("拖拽离开时恢复列表项位置失败", exc_info=True)

                try:
                    widget = self.itemWidget(source_item)
                except RuntimeError:
                    widget = None

                self.blockSignals(True)
                try:
                    if widget:
                        self.removeItemWidget(source_item)

                    self.takeItem(current_row)
                    self.insertItem(self._initial_drag_row, source_item)
                    if widget:
                        self.setItemWidget(source_item, widget)
                        # Force set size hint of the item to invalidate list layout cache on the first swap!
                        widget_size = widget.sizeHint()
                        widget_size.setHeight(widget_size.height() + 4)
                        source_item.setSizeHint(widget_size)
                        widget.show()  # Ensure visible inside viewport!
                    self.setCurrentItem(source_item)
                except RuntimeError:
                    logger.debug("拖拽时设置当前项失败", exc_info=True)
                finally:
                    self.blockSignals(False)

                self.doItemsLayout()

                from qt_compat import QEasingCurve, QPropertyAnimation

                for r in range(self.count()):
                    it = self.item(r)
                    try:
                        w = self.itemWidget(it)
                    except RuntimeError:
                        w = None

                    if w and id(it) in old_positions:
                        old_pos = old_positions[id(it)]
                        try:
                            new_pos = w.pos()
                            if old_pos != new_pos:
                                if hasattr(w, "_pos_anim") and w._pos_anim is not None:
                                    w._pos_anim.stop()
                                anim = QPropertyAnimation(w, b"pos")
                                anim.setDuration(180)
                                anim.setStartValue(old_pos)
                                anim.setEndValue(new_pos)
                                anim.setEasingCurve(QEasingCurve.OutCubic)
                                w._pos_anim = anim
                                anim.start()
                        except RuntimeError:
                            logger.debug("拖拽离开时启动位置动画失败", exc_info=True)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.source() != self:
            event.ignore()
            return

        source_item = self.currentItem()
        if not source_item:
            event.ignore()
            return

        final_row = self.row(source_item)

        # Restore full opacity
        widget = self.itemWidget(source_item)
        if widget:
            try:
                widget.setGraphicsEffect(None)
            except Exception as exc:
                logger.debug("清除图形效果失败: %s", exc, exc_info=True)

        event.ignore()  # Prevent default Qt drop widget destruction behavior

        # Trigger reorder callback if the position actually changed
        if self._initial_drag_row != final_row and self._initial_drag_row >= 0 and final_row >= 0:
            if self.on_reordered_callback:
                self.on_reordered_callback(self._initial_drag_row, final_row)


class SettingsCommandsPageMixin:
    def _setup_commands_page(self, page):
        # ── Favorites ──
        layout2, group2 = page.add_group("收藏命令")

        fav_desc = QLabel(
            tr(
                "收藏的命令会显示在 / 默认页顶部，方便快速访问。\n可以使用下方“内置命令管理”中的“收藏”按钮或从结果卡片的星标按钮添加。"
            )
        )
        fav_desc.setObjectName("fav_desc")
        fav_desc.setWordWrap(True)
        fav_desc.setMinimumWidth(0)
        fav_desc.setStyleSheet(
            scale_qss(
                f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            padding: 0px;
            margin: 0px 0px 8px 0px;
        """
            )
        )
        layout2.addWidget(fav_desc)

        # Drag & Drop list widget for favorite commands
        self.fav_list_widget = DragDropListWidget(
            page,
            theme=self.current_theme,
            on_reordered_callback=self._on_favorites_reordered,
            on_drag_finished_callback=self._schedule_refresh,
        )
        self.fav_list_widget.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.fav_list_widget.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        layout2.addWidget(self.fav_list_widget)

        # Placeholder label when no favorites are present
        self.fav_placeholder_lbl = QLabel(tr("暂未收藏任何命令"))
        self.fav_placeholder_lbl.setStyleSheet(
            scale_qss(
                f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            font-style: italic;
            padding: 4px;
        """
            )
        )
        layout2.addWidget(self.fav_placeholder_lbl)

        # ── Disabled builtin commands ──
        layout3, group3 = page.add_group("内置命令管理")

        disable_desc = QLabel(tr("可在下方直接启用或禁用特定的系统内置命令，以优化匹配列表。"))
        disable_desc.setObjectName("disable_desc")
        disable_desc.setWordWrap(True)
        disable_desc.setMinimumWidth(0)
        disable_desc.setStyleSheet(
            scale_qss(
                f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            padding: 0px;
            margin: 0px 0px 8px 0px;
        """
            )
        )
        layout3.addWidget(disable_desc)

        # Search filter for built-in commands
        self.builtin_filter_edit = QLineEdit()
        self.builtin_filter_edit.setPlaceholderText(tr("搜索内置命令 (支持名称、快捷键、描述)..."))
        self.builtin_filter_edit.setClearButtonEnabled(True)
        self.builtin_filter_edit.setFixedHeight(sp(26))
        # Debounce search: don't rebuild 28+ widgets on every keystroke
        self._builtin_filter_timer = QTimer(self)
        self._builtin_filter_timer.setSingleShot(True)
        self._builtin_filter_timer.setInterval(200)
        self._builtin_filter_timer.timeout.connect(self._refresh_command_settings)
        self.builtin_filter_edit.textChanged.connect(lambda: self._builtin_filter_timer.start())
        layout3.addWidget(self.builtin_filter_edit)

        # Container for list of all built-in commands
        self.builtin_container = QWidget()
        self.builtin_layout = QVBoxLayout(self.builtin_container)
        self.builtin_layout.setContentsMargins(0, sp(4), 0, sp(4))
        self.builtin_layout.setSpacing(sp(6))
        layout3.addWidget(self.builtin_container)

        # ── Reload current state ──
        self._refresh_command_settings()

    def _refresh_command_settings(self):
        """Refresh displayed values from current settings."""
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()

            # Suppress all intermediate repaints during bulk widget refresh
            if hasattr(self, "builtin_container"):
                self.builtin_container.setUpdatesEnabled(False)
            if hasattr(self, "fav_list_widget"):
                self.fav_list_widget.setUpdatesEnabled(False)

            # Dynamic Colors
            if self.current_theme == "dark":
                bg = "rgba(255, 255, 255, 0.04)"
                border = "rgba(255, 255, 255, 0.08)"
                text_color = "rgba(255, 255, 255, 0.9)"
                sub_text_color = "rgba(255, 255, 255, 0.6)"
            else:
                bg = "rgba(0, 0, 0, 0.02)"
                border = "rgba(0, 0, 0, 0.05)"
                text_color = "rgba(28, 28, 30, 0.9)"
                sub_text_color = "rgba(28, 28, 30, 0.6)"

            # Clear layout helper
            def clear_layout(layout):
                while layout.count():
                    item = layout.takeAt(0)
                    w = item.widget()
                    if w:
                        w.deleteLater()

            # Stop and clear all running animations in favorite command item widgets before clear()
            if hasattr(self, "fav_list_widget") and self.fav_list_widget:
                for r in range(self.fav_list_widget.count()):
                    try:
                        it = self.fav_list_widget.item(r)
                        w = self.fav_list_widget.itemWidget(it)
                        if w and hasattr(w, "_pos_anim") and w._pos_anim is not None:
                            w._pos_anim.stop()
                            w._pos_anim = None
                    except RuntimeError:
                        logger.debug("刷新时停止收藏项位置动画失败", exc_info=True)

            # 1. Favorites List Rebuild (Recreated because it's small and dynamic in size/order)
            self.fav_list_widget.clear()
            favs = settings.favorite_commands
            if favs:
                from core import registry

                for fid in favs:
                    cmd = registry.get(fid) if registry else None
                    name = cmd.title if cmd else fid

                    item_widget = QWidget()
                    item_widget.setObjectName("FavItem")
                    item_widget.setStyleSheet(
                        scale_qss(
                            f"QWidget#FavItem {{ background-color: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
                        )
                    )

                    item_layout = QGridLayout(item_widget)
                    item_layout.setContentsMargins(sp(10), sp(6), sp(10), sp(6))
                    item_layout.setHorizontalSpacing(sp(8))
                    item_layout.setVerticalSpacing(sp(2))

                    star_lbl = QLabel("⭐")
                    item_layout.addWidget(star_lbl, 0, 0, 1, 1, QtCompat.AlignTop)

                    fid_display = fid.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")
                    name_display = name.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")

                    name_lbl = QLabel(name_display)
                    name_lbl.setStyleSheet(scale_qss(f"font-weight: 400; color: {text_color}; font-size: 12px;"))
                    name_lbl.setWordWrap(True)
                    name_lbl.setMinimumWidth(0)
                    item_layout.addWidget(name_lbl, 0, 1, 1, 1)

                    key_lbl = QLabel(f"/{fid_display}")
                    key_lbl.setStyleSheet(scale_qss("color: rgba(10,132,255,0.85); font-size: 11px;"))
                    key_lbl.setWordWrap(True)
                    key_lbl.setMinimumWidth(0)
                    item_layout.addWidget(key_lbl, 1, 1, 1, 1)

                    unfav_btn = QPushButton(tr("取消收藏"))
                    unfav_btn.setFixedWidth(sp(72))
                    unfav_btn.setMinimumHeight(sp(20))
                    unfav_btn.setProperty("is_compact_btn", True)
                    unfav_btn.setStyleSheet(scale_qss("QPushButton { font-size: 10px; padding: 2px 4px; }"))
                    unfav_btn.clicked.connect(lambda checked, cmd_id=fid: self._on_unfavorite_command(cmd_id))
                    item_layout.addWidget(unfav_btn, 0, 2, 2, 1, QtCompat.AlignVCenter)

                    item_layout.setColumnStretch(0, 0)
                    item_layout.setColumnStretch(1, 1)
                    item_layout.setColumnStretch(2, 0)

                    item = QListWidgetItem()
                    item.setFlags(
                        item.flags() | QtCompat.ItemIsDragEnabled | QtCompat.ItemIsSelectable | QtCompat.ItemIsEnabled
                    )

                    widget_size = item_widget.sizeHint()
                    widget_size.setHeight(widget_size.height() + 4)
                    item.setSizeHint(widget_size)

                    self.fav_list_widget.addItem(item)
                    self.fav_list_widget.setItemWidget(item, item_widget)

                total_height = 0
                for i in range(self.fav_list_widget.count()):
                    total_height += self.fav_list_widget.sizeHintForRow(i)
                self.fav_list_widget.setFixedHeight(total_height + 4)

                self.fav_list_widget.show()
                self.fav_placeholder_lbl.hide()
            else:
                self.fav_list_widget.setFixedHeight(0)
                self.fav_list_widget.hide()
                self.fav_placeholder_lbl.show()

            # 2. Built-in Commands List Rebuild (Optimized: Cache and update in-place to eliminate 99% of UI freeze/lag)
            from core import registry

            if registry:
                all_cmds = registry.list()
                builtin_cmds = [cmd for cmd in all_cmds if cmd.source == "builtin"]
                builtin_cmds.sort(key=lambda c: c.id)

                query = self.builtin_filter_edit.text().strip().lower() if hasattr(self, "builtin_filter_edit") else ""

                # Lazy initial creation of widgets
                if not hasattr(self, "_builtin_widgets") or not self._builtin_widgets:
                    self._builtin_widgets = {}
                    clear_layout(self.builtin_layout)

                    for cmd in builtin_cmds:
                        item_widget = QWidget()
                        item_widget.setObjectName("BuiltinItem")

                        item_layout = QGridLayout(item_widget)
                        item_layout.setContentsMargins(sp(10), sp(8), sp(10), sp(8))
                        item_layout.setHorizontalSpacing(sp(8))
                        item_layout.setVerticalSpacing(sp(2))

                        dot_lbl = QLabel("●")
                        item_layout.addWidget(dot_lbl, 0, 0, 1, 1, QtCompat.AlignTop)

                        cmd_title_display = (
                            cmd.title.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")
                        )
                        cmd_id_display = cmd.id.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")

                        title_lbl = QLabel(cmd_title_display)
                        title_lbl.setWordWrap(True)
                        title_lbl.setMinimumWidth(0)
                        item_layout.addWidget(title_lbl, 0, 1, 1, 1)

                        key_lbl = QLabel(f"/{cmd_id_display}")
                        key_lbl.setWordWrap(True)
                        key_lbl.setMinimumWidth(0)
                        item_layout.addWidget(key_lbl, 1, 1, 1, 1)

                        actions_layout = QHBoxLayout()
                        actions_layout.setContentsMargins(0, 0, 0, 0)
                        actions_layout.setSpacing(sp(6))

                        fav_btn = QPushButton()
                        fav_btn.setFixedWidth(sp(60))
                        fav_btn.setMinimumHeight(sp(20))
                        fav_btn.setProperty("is_compact_btn", True)
                        fav_btn.setStyleSheet(scale_qss("QPushButton { font-size: 10px; padding: 2px 4px; }"))
                        actions_layout.addWidget(fav_btn)

                        toggle_btn = QPushButton()
                        toggle_btn.setFixedWidth(sp(60))
                        toggle_btn.setMinimumHeight(sp(20))
                        toggle_btn.setProperty("is_compact_btn", True)
                        toggle_btn.setStyleSheet(scale_qss("QPushButton { font-size: 10px; padding: 2px 4px; }"))
                        actions_layout.addWidget(toggle_btn)

                        item_layout.addLayout(actions_layout, 0, 2, 2, 1, QtCompat.AlignVCenter)

                        desc_lbl = None
                        if cmd.description:
                            desc_display = (
                                cmd.description.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")
                            )
                            desc_lbl = QLabel(desc_display)
                            desc_lbl.setWordWrap(True)
                            desc_lbl.setMinimumWidth(0)
                            item_layout.addWidget(desc_lbl, 2, 1, 1, 1)

                        item_layout.setColumnStretch(0, 0)
                        item_layout.setColumnStretch(1, 1)
                        item_layout.setColumnStretch(2, 0)

                        self.builtin_layout.addWidget(item_widget)

                        self._builtin_widgets[cmd.id] = {
                            "widget": item_widget,
                            "dot_lbl": dot_lbl,
                            "fav_btn": fav_btn,
                            "toggle_btn": toggle_btn,
                            "title_lbl": title_lbl,
                            "desc_lbl": desc_lbl,
                            "key_lbl": key_lbl,
                        }

                self._update_builtin_command_rows(
                    builtin_cmds, settings, colors=(bg, border, text_color, sub_text_color), query=query
                )
            else:
                clear_layout(self.builtin_layout)
                lbl = QLabel(tr("无法读取注册表命令"))
                lbl.setStyleSheet("color: #f44336;")
                self.builtin_layout.addWidget(lbl)

            if (
                getattr(self, "_command_refresh_apply_theme", True)
                and hasattr(self, "page_commands")
                and self.page_commands
            ):
                self.page_commands.apply_theme(self.current_theme)

        except Exception as e:
            logger.warning("刷新命令设置失败: %s", e)
        finally:
            # Resume painting — single
            # repaint for all accumulated changes
            if hasattr(self, "builtin_container"):
                self.builtin_container.setUpdatesEnabled(True)
            if hasattr(self, "fav_list_widget"):
                self.fav_list_widget.setUpdatesEnabled(True)

    def _iter_builtin_commands(self):
        try:
            from core import registry

            if not registry:
                return []
            return sorted(
                [cmd for cmd in registry.list() if cmd.source == "builtin"],
                key=lambda c: c.id,
            )
        except Exception:
            return []

    def _current_command_row_colors(self):
        if self.current_theme == "dark":
            return (
                "rgba(255, 255, 255, 0.04)",
                "rgba(255, 255, 255, 0.08)",
                "rgba(255, 255, 255, 0.9)",
                "rgba(255, 255, 255, 0.6)",
            )
        return (
            "rgba(0, 0, 0, 0.02)",
            "rgba(0, 0, 0, 0.05)",
            "rgba(28, 28, 30, 0.9)",
            "rgba(28, 28, 30, 0.6)",
        )

    def _update_builtin_command_rows(self, builtin_cmds=None, settings=None, colors=None, query=None):
        if not hasattr(self, "_builtin_widgets") or not self._builtin_widgets:
            return
        try:
            from core import data_manager

            if settings is None:
                settings = data_manager.get_settings() if data_manager else None
            if settings is None:
                return
            builtin_cmds = builtin_cmds or self._iter_builtin_commands()
            favs = settings.favorite_commands
            disabled_list = settings.disabled_builtin_commands
            bg, border, text_color, sub_text_color = colors or self._current_command_row_colors()
            if query is None:
                query = self.builtin_filter_edit.text().strip().lower() if hasattr(self, "builtin_filter_edit") else ""

            for cmd in builtin_cmds:
                entry = self._builtin_widgets.get(cmd.id)
                if not entry:
                    continue
                is_disabled = cmd.id in disabled_list
                is_fav = cmd.id in favs

                entry["widget"].setStyleSheet(
                    scale_qss(
                        f"QWidget#BuiltinItem {{ background-color: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
                    )
                )
                entry["title_lbl"].setStyleSheet(scale_qss(f"font-weight: 400; color: {text_color}; font-size: 12px;"))
                entry["key_lbl"].setStyleSheet(scale_qss("color: rgba(10,132,255,0.85); font-size: 11px;"))
                if entry["desc_lbl"]:
                    entry["desc_lbl"].setStyleSheet(
                        scale_qss(f"color: {sub_text_color}; font-size: 11px; margin-left: 14px;")
                    )

                dot_color = "#f44336" if is_disabled else "#4caf50"
                entry["dot_lbl"].setStyleSheet(scale_qss(f"color: {dot_color}; font-size: 11px; margin-right: 2px;"))

                fav_btn = entry["fav_btn"]
                fav_btn.setText(tr("取消收藏") if is_fav else tr("收藏"))
                try:
                    fav_btn.clicked.disconnect()
                except Exception as exc:
                    logger.debug("断开收藏按钮信号失败: %s", exc, exc_info=True)
                if is_fav:
                    fav_btn.clicked.connect(lambda checked, cid=cmd.id: self._on_unfavorite_command(cid))
                else:
                    fav_btn.clicked.connect(lambda checked, cid=cmd.id: self._on_favorite_command(cid))

                toggle_btn = entry["toggle_btn"]
                toggle_btn.setText(tr("启用") if is_disabled else tr("禁用"))
                try:
                    toggle_btn.clicked.disconnect()
                except Exception as exc:
                    logger.debug("断开启用按钮信号失败: %s", exc, exc_info=True)
                if is_disabled:
                    toggle_btn.clicked.connect(lambda checked, cid=cmd.id: self._on_toggle_builtin_command(cid, True))
                else:
                    toggle_btn.clicked.connect(lambda checked, cid=cmd.id: self._on_toggle_builtin_command(cid, False))

                visible = True
                if query:
                    visible = (
                        query in cmd.title.lower()
                        or query in cmd.id.lower()
                        or (cmd.description and query in cmd.description.lower())
                    )
                entry["widget"].setVisible(visible)
        except Exception as e:
            logger.debug("更新内置命令行状态失败: %s", e)

    def _refresh_builtin_command_rows_only(self):
        if hasattr(self, "builtin_container"):
            self.builtin_container.setUpdatesEnabled(False)
        try:
            self._update_builtin_command_rows()
        finally:
            if hasattr(self, "builtin_container"):
                self.builtin_container.setUpdatesEnabled(True)

    def _schedule_refresh(self):
        """Debounced refresh — coalesces rapid clicks into one rebuild."""
        if not hasattr(self, "_refresh_timer"):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.setInterval(50)
            self._refresh_timer.timeout.connect(self._refresh_command_settings)
        self._refresh_timer.start()

    def _stop_command_page_timers(self):
        for timer_name in ("_builtin_filter_timer", "_refresh_timer"):
            timer = getattr(self, timer_name, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception as exc:
                logger.debug("停止定时器失败: %s", exc, exc_info=True)

    def _on_unfavorite_command(self, cmd_id):
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()
            if cmd_id in settings.favorite_commands:
                settings.favorite_commands.remove(cmd_id)
            data_manager.save()
            if hasattr(self, "command_settings_changed"):
                self.command_settings_changed.emit()
            self._refresh_builtin_command_rows_only()
        except Exception as e:
            logger.error("取消收藏失败: %s", e)
            ThemedMessageBox.critical(self, tr("操作失败"), tr("取消收藏失败:\n{error}", error=e))

    def _on_toggle_builtin_command(self, cmd_id, enable):
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()

            if enable:
                if cmd_id in settings.disabled_builtin_commands:
                    settings.disabled_builtin_commands.remove(cmd_id)
            else:
                if cmd_id not in settings.disabled_builtin_commands:
                    settings.disabled_builtin_commands.append(cmd_id)

            data_manager.save()
            if hasattr(self, "command_settings_changed"):
                self.command_settings_changed.emit()
            self._refresh_builtin_command_rows_only()
        except Exception as e:
            logger.error("切换内置命令状态失败: %s", e)
            ThemedMessageBox.critical(self, tr("操作失败"), tr("保存命令状态失败:\n{error}", error=e))

    def _on_favorite_command(self, cmd_id):
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()
            if cmd_id not in settings.favorite_commands:
                settings.favorite_commands.append(cmd_id)
            data_manager.save()
            if hasattr(self, "command_settings_changed"):
                self.command_settings_changed.emit()
            self._refresh_builtin_command_rows_only()
        except Exception as e:
            logger.error("收藏失败: %s", e)
            ThemedMessageBox.critical(self, tr("操作失败"), tr("收藏失败:\n{error}", error=e))

    def _on_favorites_reordered(self, source_row, dest_row):
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()
            favs = settings.favorite_commands
            if 0 <= source_row < len(favs) and 0 <= dest_row < len(favs):
                item = favs.pop(source_row)
                favs.insert(dest_row, item)
                data_manager.save()
                if hasattr(self, "command_settings_changed"):
                    self.command_settings_changed.emit()
                self._schedule_refresh()
        except Exception as e:
            logger.error("重新排序收藏命令失败: %s", e)
            ThemedMessageBox.critical(self, tr("操作失败"), tr("重新排序失败:\n{error}", error=e))
