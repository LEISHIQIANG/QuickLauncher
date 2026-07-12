"""Folder panel drag-drop mixin — extracted from folder_panel."""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging
import os

from qt_compat import (
    QApplication,
    QColor,
    QDrag,
    QEasingCurve,
    QMimeData,
    QPainter,
    QPixmap,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QtCompat,
)
from ui.config_window.folder_panel_helpers import (
    decode_mime_text,
    is_auto_sync_folder_locked,
    shortcut_ids_from_mime,
    should_copy_shortcut_drop,
)
from ui.styles.design_tokens import StatusScale
from ui.utils.pixel_snap import make_cosmetic_pen

logger = logging.getLogger(__name__)


class FolderPanelDragMixin:
    """Drag-and-drop logic for FolderPanel."""

    def _list_start_drag(self, supported_actions):
        """自定义文件夹拖动开始事件 - 苹果风格高质感动态预览与局部减淡"""
        item = self.folder_list.currentItem()
        if not item:
            return

        widget = self.folder_list.itemWidget(item)
        if not widget:
            return

        # Record the initial row at the start of the drag
        self._initial_drag_row = self.folder_list.row(item)

        drag = QDrag(self.folder_list)
        mime_data = QMimeData()

        # 设置特殊标识：这是文件夹排序拖动
        folder_id = item.data(QtCompat.UserRole)
        mime_data.setData("application/x-folder-reorder", folder_id.encode())
        drag.setMimeData(mime_data)

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
        theme = self._get_current_theme()
        if theme == "dark":
            border_color = QColor(StatusScale.drop_highlight_pen)
        else:
            border_color = QColor(StatusScale.drop_highlight_pressed)

        painter.setPen(make_cosmetic_pen(border_color, 1.5, 1))
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)
        painter.end()

        drag.setPixmap(transparent_pixmap)
        drag.setHotSpot(QPoint(w // 2, h // 2))

        # Dim the source widget in the list during drag for dynamic feedback.
        # Previously used ``QGraphicsOpacityEffect`` which triggers an
        # off-screen render of the whole subtree on every paint; replaced
        # with the cheap ``opacity`` style override.
        try:
            widget.setStyleSheet("QWidget { opacity: 0.35; }")
        except Exception as exc:
            logger.debug("Failed to apply folder drag opacity stylesheet: %s", exc)

        try:
            drag.exec_(supported_actions)
        finally:
            # If the drag was cancelled or finished, restore full opacity
            try:
                widget.setGraphicsEffect(None)
            except Exception as exc:
                logger.debug("清除图形效果失败: %s", exc, exc_info=True)

    def _list_drag_enter_event(self, event):
        """处理拖入事件"""
        # 文件夹排序拖动
        if event.mimeData().hasFormat("application/x-folder-reorder"):
            event.acceptProposedAction()
        # 外部文件/文件夹URL
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        # 图标拖动
        elif event.mimeData().hasFormat("application/x-shortcut-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _list_drag_move_event(self, event):
        """处理拖动移动事件 - 实时苹果风格平滑滑动交换"""
        if not event.mimeData().hasFormat("application/x-folder-reorder"):
            # 外部文件/图标拖动时，仍使用原始指示器逻辑
            for i in range(self.folder_list.count()):
                list_item = self.folder_list.item(i)
                list_item.setData(QtCompat.UserRole + 1, False)

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        item = self.folder_list.itemAt(pos)

        # 文件夹排序拖动：实时苹果风格滑动交换
        if event.mimeData().hasFormat("application/x-folder-reorder"):
            event.acceptProposedAction()

            if not item:
                return

            dest_row = self.folder_list.row(item)
            source_item = self.folder_list.currentItem()
            if not source_item:
                return

            source_row = self.folder_list.row(source_item)

            # Dynamic real-time Apple-style swapping reorder
            if source_row != dest_row:
                # Record old positions of all visible widgets in the list
                old_positions = {}
                for r in range(self.folder_list.count()):
                    it = self.folder_list.item(r)
                    try:
                        w = self.folder_list.itemWidget(it)
                        if w:
                            old_positions[id(it)] = w.pos()
                    except RuntimeError:
                        logger.debug("拖拽时获取文件夹列表项控件位置失败", exc_info=True)

                try:
                    widget = self.folder_list.itemWidget(source_item)
                except RuntimeError:
                    widget = None

                self.folder_list.blockSignals(True)
                try:
                    # Unparent widget to protect it from C++ deletion during takeItem
                    if widget:
                        self.folder_list.removeItemWidget(source_item)

                    self.folder_list.takeItem(source_row)
                    self.folder_list.insertItem(dest_row, source_item)

                    if widget:
                        self.folder_list.setItemWidget(source_item, widget)
                        source_item.setSizeHint(widget.sizeHint())
                        widget.show()
                    self.folder_list.setCurrentItem(source_item)
                except RuntimeError:
                    logger.debug("拖拽重排序文件夹列表项失败", exc_info=True)
                finally:
                    self.folder_list.blockSignals(False)

                # Force layout recalculation
                self.folder_list.doItemsLayout()

                # Trigger QPropertyAnimation for all shifted items
                for r in range(self.folder_list.count()):
                    it = self.folder_list.item(r)
                    try:
                        w = self.folder_list.itemWidget(it)
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
                                anim.setDuration(180)  # 180ms responsive slide
                                anim.setStartValue(old_pos)
                                anim.setEndValue(new_pos)
                                anim.setEasingCurve(QEasingCurve.OutCubic)
                                w._pos_anim = anim
                                anim.start()
                        except RuntimeError:
                            logger.debug("拖拽移动时启动位置动画失败", exc_info=True)
        # 外部拖入
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        # 图标拖动：检查同步文件夹限制
        elif event.mimeData().hasFormat("application/x-shortcut-id"):
            if event.mimeData().hasFormat("application/x-source-folder-id"):
                source_folder_id = event.mimeData().data("application/x-source-folder-id").data().decode()
                source_folder = self.data_manager.data.get_folder_by_id(source_folder_id)

                if is_auto_sync_folder_locked(source_folder):
                    while QApplication.overrideCursor():
                        QApplication.restoreOverrideCursor()
                    QApplication.setOverrideCursor(Qt.ForbiddenCursor)
                    event.ignore()
                    return

            if item:
                folder_id = item.data(QtCompat.UserRole)
                folder = self.data_manager.data.get_folder_by_id(folder_id)

                if is_auto_sync_folder_locked(folder):
                    while QApplication.overrideCursor():
                        QApplication.restoreOverrideCursor()
                    QApplication.setOverrideCursor(Qt.ForbiddenCursor)
                    event.ignore()
                    return
                else:
                    while QApplication.overrideCursor():
                        QApplication.restoreOverrideCursor()
                    item.setData(QtCompat.UserRole + 1, True)
                    self.folder_list.viewport().update()
            else:
                while QApplication.overrideCursor():
                    QApplication.restoreOverrideCursor()

            event.acceptProposedAction()
        else:
            event.ignore()

    def _list_drag_leave_event(self, event):
        """处理拖动离开事件 - 拖离时弹性还原位置"""
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()

        source_item = self.folder_list.currentItem()
        if source_item and hasattr(self, "_initial_drag_row") and self._initial_drag_row >= 0:
            current_row = self.folder_list.row(source_item)
            if current_row != self._initial_drag_row:
                old_positions = {}
                for r in range(self.folder_list.count()):
                    it = self.folder_list.item(r)
                    try:
                        w = self.folder_list.itemWidget(it)
                        if w:
                            old_positions[id(it)] = w.pos()
                    except RuntimeError:
                        logger.debug("拖拽离开时获取文件夹列表项控件位置失败", exc_info=True)

                try:
                    widget = self.folder_list.itemWidget(source_item)
                except RuntimeError:
                    widget = None

                self.folder_list.blockSignals(True)
                try:
                    if widget:
                        self.folder_list.removeItemWidget(source_item)

                    self.folder_list.takeItem(current_row)
                    self.folder_list.insertItem(self._initial_drag_row, source_item)
                    if widget:
                        self.folder_list.setItemWidget(source_item, widget)
                        source_item.setSizeHint(widget.sizeHint())
                        widget.show()
                    self.folder_list.setCurrentItem(source_item)
                except RuntimeError:
                    logger.debug("拖拽离开时恢复文件夹列表项位置失败", exc_info=True)
                finally:
                    self.folder_list.blockSignals(False)

                self.folder_list.doItemsLayout()

                for r in range(self.folder_list.count()):
                    it = self.folder_list.item(r)
                    try:
                        w = self.folder_list.itemWidget(it)
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

        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            list_item.setData(QtCompat.UserRole + 1, False)
        self.folder_list.viewport().update()

    @staticmethod
    def _decode_mime_text(mime_data, fmt: str) -> str:
        return decode_mime_text(mime_data, fmt)

    @classmethod
    def _shortcut_ids_from_mime(cls, mime_data) -> list[str]:
        return shortcut_ids_from_mime(mime_data)

    def _list_drop_event(self, event):
        """处理放下事件"""
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()

        # 文件夹排序拖动
        if event.mimeData().hasFormat("application/x-folder-reorder"):
            event.ignore()  # 阻止 Qt 默认删除/重建行为

            source_item = self.folder_list.currentItem()
            if not source_item:
                return

            widget = self.folder_list.itemWidget(source_item)
            if widget:
                try:
                    widget.setGraphicsEffect(None)
                except Exception as exc:
                    logger.debug("清除图形效果失败: %s", exc, exc_info=True)

            if hasattr(self, "_initial_drag_row") and self._initial_drag_row >= 0:
                # 重新保存序列并刷新
                folder_ids = []
                for i in range(self.folder_list.count()):
                    item = self.folder_list.item(i)
                    folder_ids.append(item.data(QtCompat.UserRole))
                self.data_manager.reorder_folders(folder_ids)

                # 获取拖动项的ID
                folder_id = source_item.data(QtCompat.UserRole)

                # 重新加载文件夹列表，干净地重建所有 Item 及其自定义 Widget
                self._load_folders()

                # 恢复选中状态
                for i in range(self.folder_list.count()):
                    if self.folder_list.item(i).data(QtCompat.UserRole) == folder_id:
                        self.folder_list.setCurrentRow(i)
                        self.folder_selected.emit(folder_id)
                        break
            return

        target_item = None
        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            if list_item.data(QtCompat.UserRole + 1):
                target_item = list_item
            list_item.setData(QtCompat.UserRole + 1, False)
        self.folder_list.viewport().update()

        # 外部文件/文件夹拖入
        if target_item is None:
            try:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                target_item = self.folder_list.itemAt(pos)
            except Exception:
                target_item = None

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                local_path = url.toLocalFile()
                if not local_path:
                    continue

                if os.path.isdir(local_path):
                    self._import_folder(local_path)
                    event.acceptProposedAction()
                    return

            event.ignore()
        # 图标拖动到文件夹
        elif event.mimeData().hasFormat("application/x-shortcut-id"):
            if not target_item:
                event.ignore()
                return

            target_folder_id = target_item.data(QtCompat.UserRole)
            folder = self.data_manager.data.get_folder_by_id(target_folder_id)

            if is_auto_sync_folder_locked(folder):
                event.ignore()
                return

            if event.mimeData().hasFormat("application/x-source-folder-id"):
                source_folder_id = self._decode_mime_text(event.mimeData(), "application/x-source-folder-id").strip()
                source_folder = self.data_manager.data.get_folder_by_id(source_folder_id)
                if is_auto_sync_folder_locked(source_folder):
                    event.ignore()
                    return
            else:
                source_folder = None

            shortcut_ids = self._shortcut_ids_from_mime(event.mimeData())
            if not shortcut_ids:
                event.ignore()
                return

            if event.mimeData().hasFormat("application/x-source-folder-id"):
                source_folder_id = self._decode_mime_text(event.mimeData(), "application/x-source-folder-id").strip()
                source_folder = self.data_manager.data.get_folder_by_id(source_folder_id)
            copy_drag = should_copy_shortcut_drop(folder, source_folder)

            if copy_drag:
                result = self.data_manager.copy_shortcuts_batch(shortcut_ids, target_folder_id)
            else:
                result = self.data_manager.move_shortcuts_batch(shortcut_ids, target_folder_id)
            if result.get("success", 0) > 0:
                current_item = self.folder_list.currentItem()
                if current_item:
                    current_folder_id = current_item.data(QtCompat.UserRole)
                    self.folder_selected.emit(current_folder_id)
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()
