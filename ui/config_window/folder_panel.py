"""
文件夹面板
"""

import logging
import os
import time

from core import DataManager
from core.i18n import tr
from infrastructure.process import runtime as process_runtime
from qt_compat import (
    QApplication,
    QColor,
    QDialog,
    QDrag,
    QEasingCurve,
    QFrame,
    QGraphicsDropShadowEffect,
    QIcon,
    QListWidgetItem,
    QMimeData,
    QPainter,
    QPen,
    QPoint,
    QPropertyAnimation,
    QPushButton,
    QRectF,
    QSize,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from runtime_paths import app_root
from ui.styles.design_tokens import StatusScale, elevation
from ui.styles.style import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.pixel_snap import create_pixmap
from ui.utils.ui_scale import scale_qss, sp
from ui.utils.window_effect import is_win10

from .folder_panel_helpers import (
    decode_mime_text,
    is_auto_sync_folder_locked,
    move_folder_id_to_target,
    shortcut_ids_from_mime,
    should_copy_shortcut_drop,
)
from .folder_panel_widgets import (
    FolderImportDialog,
    FolderInputDialog,
    FolderItemDelegate,
    FolderItemWidget,
    FolderListWidget,
)

logger = logging.getLogger(__name__)


class FolderPanel(QWidget):
    """左侧文件夹面板"""

    folder_selected = pyqtSignal(str)
    _folder_sync_requested = pyqtSignal(str)  # 用于从 watchdog 线程安全地通知主线程执行同步

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data_manager = data_manager
        self._setup_ui()
        self._load_folders()

        # 连接同步信号（确保 watchdog 线程可以安全通知主线程）
        self._folder_sync_requested.connect(self._auto_sync)

        # 延迟恢复文件夹监听，避免阻塞 UI 初始化
        QTimer.singleShot(0, self._restore_folder_watches_async)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(8), sp(8), sp(8), sp(1))
        layout.setSpacing(sp(8))

        self.list_frame = QFrame()
        self.list_frame.setObjectName("folderListFrame")
        list_frame_layout = QVBoxLayout(self.list_frame)
        list_frame_layout.setContentsMargins(sp(8), sp(4), sp(8), sp(8))
        list_frame_layout.setSpacing(sp(8))

        self.folder_list = FolderListWidget(self)
        self.folder_list.setObjectName("folderList")
        self.folder_list.setIconSize(QSize(sp(18), sp(18)))
        # 设置自定义委托以绘制拖放提示
        self.folder_list.setItemDelegate(FolderItemDelegate(self))
        # 启用拖放，不仅支持内部移动，也支持接收外部拖放
        self.folder_list.setDragDropMode(QtCompat.DragDrop)
        self.folder_list.setDefaultDropAction(QtCompat.MoveAction)
        self.folder_list.setAcceptDrops(True)
        # 禁用默认的拖放指示器（小箭头）
        self.folder_list.setDropIndicatorShown(False)

        self.folder_list.itemClicked.connect(self._on_item_clicked)
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._show_context_menu)
        self.folder_list.model().rowsMoved.connect(self._on_rows_moved)

        # 设置选择模式 - 使用 QtCompat
        self.folder_list.setSelectionMode(QtCompat.SingleSelection)
        # 禁用水平滚动条并启用文字省略号
        self.folder_list.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.folder_list.setTextElideMode(QtCompat.ElideRight)

        if hasattr(self.folder_list, "setFrameShape"):
            try:
                self.folder_list.setFrameShape(QFrame.NoFrame)
            except Exception as exc:
                logger.debug("设置框架形状失败: %s", exc, exc_info=True)

        list_frame_layout.addWidget(self.folder_list)

        # 新建按钮 - 放在 list_frame 内部，底框包含按钮
        self.add_btn = QPushButton(tr("＋ 新建分类"))
        self.add_btn.clicked.connect(self._add_folder)
        self.add_btn.setFixedHeight(sp(36))
        list_frame_layout.addWidget(self.add_btn)

        layout.addWidget(self.list_frame, 1)

        # 应用初始主题
        self.apply_theme(self._get_current_theme())

    def apply_theme(self, theme: str):
        self.retranslate_ui()
        if theme == "dark":
            frame_bg = "rgba(255, 255, 255, 0.06)"
            frame_border = "rgba(255, 255, 255, 0.10)"
            btn_bg = "rgba(255, 255, 255, 0.18)"
            btn_border_color = "rgba(255, 255, 255, 0.22)"
            btn_hover_bg = "rgba(255, 255, 255, 0.28)"
            btn_hover_text = "rgba(255, 255, 255, 0.95)"
            btn_color = "rgba(255, 255, 255, 0.80)"
        else:
            frame_bg = "rgba(255, 255, 255, 0.20)"
            frame_border = "rgba(0, 0, 0, 0.06)"
            btn_bg = "rgba(255, 255, 255, 0.75)"
            btn_border_color = "rgba(255, 255, 255, 0.35)"
            btn_hover_bg = "rgba(255, 255, 255, 0.95)"
            btn_hover_text = "rgba(28, 28, 30, 0.9)"
            btn_color = "rgba(28, 28, 30, 0.65)"

        self.list_frame.setStyleSheet(
            scale_qss(
                f"""
            QFrame#folderListFrame {{
                background-color: {frame_bg};
                border: 1px solid {frame_border};
                border-radius: 10px;
            }}
        """
            )
        )

        # Items are drawn by FolderItemWidget, stylesheet just resets default background
        self.folder_list.setStyleSheet(
            scale_qss(
                """
            QListWidget#folderList {
                outline: none;
                background: transparent;
                border: none; border-radius: 0;
            }
            QListWidget#folderList::item {
                background: transparent;
                border: none; border-radius: 0;
                padding: 0px;
                margin: 1px 0px;
            }
            QListWidget#folderList::item:selected {
                background: transparent;
                border: none; border-radius: 0;
            }
            QListWidget#folderList::item:hover {
                background: transparent;
                border: none; border-radius: 0;
            }
        """
            )
        )

        # Propagate theme change to any existing FolderItemWidgets
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            widget = self.folder_list.itemWidget(item)
            if isinstance(widget, FolderItemWidget):
                widget.theme = theme
                widget.update()

        self.add_btn.setStyleSheet(
            scale_qss(
                f"""
            QPushButton {{
                font-size: 11px;
                padding: 4px 13px;
                text-align: center;
                background: {btn_bg};
                border: 1px solid {btn_border_color};
                border-radius: 12px;
                color: {btn_color};
                font-weight: 400;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
                color: {btn_hover_text};
                border: 1px solid {btn_border_color};
            }}
            QPushButton:pressed {{
                opacity: 0.7;
            }}
        """
            )
        )

        shadow = QGraphicsDropShadowEffect()
        win10 = is_win10()
        offset_y, blur_r, shadow_color = elevation(1, is_win10=win10)
        shadow.setBlurRadius(blur_r)
        shadow.setOffset(0, offset_y)
        shadow.setColor(shadow_color)
        self.add_btn.setGraphicsEffect(shadow)

    def rescale_ui(self):
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(sp(8), sp(8), sp(8), sp(1))
            layout.setSpacing(sp(8))
        list_frame_layout = self.list_frame.layout()
        if list_frame_layout is not None:
            list_frame_layout.setContentsMargins(sp(8), sp(4), sp(8), sp(8))
            list_frame_layout.setSpacing(sp(8))
        self.folder_list.setIconSize(QSize(sp(18), sp(18)))
        self.add_btn.setFixedHeight(sp(36))
        for row in range(self.folder_list.count()):
            item = self.folder_list.item(row)
            widget = self.folder_list.itemWidget(item)
            if isinstance(widget, FolderItemWidget):
                item.setSizeHint(widget.sizeHint())
        self.apply_theme(self._get_current_theme())

    def retranslate_ui(self):
        if hasattr(self, "add_btn"):
            self.add_btn.setText(tr("＋ 新建分类"))

    def _get_current_theme(self) -> str:
        """获取当前主题"""
        try:
            return self.data_manager.get_settings().theme
        except Exception:
            return "dark"

    def _get_menu_stylesheet(self) -> str:
        """获取右键菜单样式 — 半透明背景配合模糊效果"""
        theme = self._get_current_theme()

        if theme == "dark":
            return scale_qss(
                """
                QMenu {
                    background-color: rgba(30, 30, 30, 120);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 12px;
                    padding: 6px;
                    font-size: 12px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: #ffffff;
                    padding: 7px 16px;
                    border-radius: 8px;
                    margin: 2px 4px;
                }
                QMenu::item:selected {
                    background-color: rgba(255, 255, 255, 0.10);
                    color: rgba(255, 255, 255, 0.95);
                }
                QMenu::item:disabled {
                    color: rgba(255, 255, 255, 110);
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(255, 255, 255, 16);
                    margin: 6px 10px;
                }
            """
            )
        else:
            return scale_qss(
                """
                QMenu {
                    background-color: rgba(255, 255, 255, 120);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 12px;
                    padding: 6px;
                    font-size: 12px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: rgba(28, 28, 30, 0.85);
                    padding: 7px 16px;
                    border-radius: 8px;
                    margin: 2px 4px;
                }
                QMenu::item:selected {
                    background-color: rgba(0, 0, 0, 0.06);
                    color: rgba(28, 28, 30, 0.95);
                }
                QMenu::item:disabled {
                    color: rgba(60, 60, 67, 120);
                }
                QMenu::separator {
                    height: 1px;
                    background-color: rgba(60, 60, 67, 18);
                    margin: 6px 10px;
                }
            """
            )

    def _load_folders(self):
        """加载文件夹列表"""
        self.folder_list.clear()

        # 加载文件夹图标 (从 assets/Folder.ico 读取蓝色图标)
        base_dir = str(app_root())

        icon_path = os.path.join(base_dir, "assets", "Folder.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, "Folder.ico")

        folder_icon = QIcon(icon_path) if os.path.exists(icon_path) else None
        theme = self._get_current_theme()

        icon_repo_folder = None

        for folder in self.data_manager.data.folders:
            # 图标仓库固定在最后加载
            if getattr(folder, "is_icon_repo", False):
                icon_repo_folder = folder
                continue

            item = QListWidgetItem()
            item.setData(QtCompat.UserRole, folder.id)

            # 根据类型设置文本 (移除黄色的文件夹 emoji，保留状态 emoji)
            if folder.is_dock:
                display_text = f"{folder.name}"
            elif folder.linked_path and folder.auto_sync:
                display_text = f"{folder.name}"
            else:
                display_text = folder.name

            # 系统文件夹不可拖拽
            if folder.is_system:
                flags = item.flags()
                flags &= ~QtCompat.ItemIsDragEnabled
                item.setFlags(flags)

            # Create Custom FolderItemWidget
            widget = FolderItemWidget(display_text, folder_icon, theme, self.folder_list)
            widget.item = item

            item.setSizeHint(widget.sizeHint())

            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, widget)

        # 图标仓库固定在底部（"新建分类"按钮上方）
        if icon_repo_folder:
            item = QListWidgetItem()
            item.setData(QtCompat.UserRole, icon_repo_folder.id)
            flags = item.flags()
            flags &= ~QtCompat.ItemIsDragEnabled
            item.setFlags(flags)
            widget = FolderItemWidget(icon_repo_folder.name, folder_icon, theme, self.folder_list)
            widget.item = item
            item.setSizeHint(widget.sizeHint())
            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, widget)

        # 选中第一个非Dock文件夹
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder_id = item.data(QtCompat.UserRole)
            folder = self.data_manager.data.get_folder_by_id(folder_id)
            if folder and not folder.is_dock and not folder.is_icon_repo:
                self.folder_list.setCurrentItem(item)
                self.folder_selected.emit(folder_id)
                break

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

        # 拖拽缩略图走 create_pixmap 自动适配 DPR
        transparent_pixmap = create_pixmap(w, h, widget)
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

        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)
        painter.end()

        drag.setPixmap(transparent_pixmap)
        drag.setHotSpot(QPoint(w // 2, h // 2))

        # Dim the source widget in the list during drag for dynamic feedback
        try:
            from ui.utils.widget_opacity import dim_for_drag

            dim_for_drag(widget, 0.35)
        except Exception:
            logger.debug("设置拖动透明度效果失败", exc_info=True)

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

    def _on_item_clicked(self, item: QListWidgetItem):
        """点击项目"""
        folder_id = item.data(QtCompat.UserRole)
        self.folder_list.setCurrentItem(item)
        self.folder_selected.emit(folder_id)

    def _on_rows_moved(self, *args):
        """行移动后重新排序"""
        folder_ids = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder_ids.append(item.data(QtCompat.UserRole))
        self.data_manager.reorder_folders(folder_ids)

    def _show_context_menu(self, pos):
        """显示右键菜单 - 修复重影问题"""
        item = self.folder_list.itemAt(pos)
        if not item:
            return

        folder_id = item.data(QtCompat.UserRole)
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder:
            return

        # 图标仓库不允许重命名、删除等操作
        if getattr(folder, "is_icon_repo", False):
            return

        theme = self._get_current_theme()
        menu = PopupMenu(theme=theme, radius=12, parent=None)
        menu.add_action(tr("重命名"), lambda: self._rename_folder(folder_id), enabled=True)

        # 新增: 绑定文件夹相关菜单
        if folder.linked_path:
            menu.add_separator()
            menu.add_action("更新文件", lambda: self._manual_sync(folder_id), enabled=True)
            menu.add_action("打开文件夹", lambda: self._open_linked_folder(folder_id), enabled=True)
            # 暂停/恢复自动更新选项
            if folder.auto_sync:
                menu.add_action("暂停自动更新", lambda: self._toggle_auto_sync(folder_id), enabled=True)
            else:
                menu.add_action("恢复自动更新", lambda: self._toggle_auto_sync(folder_id), enabled=True)
            menu.add_separator()
            menu.add_action("解除绑定", lambda: self._unlink_folder(folder_id), enabled=True)

        if not folder.is_system:
            menu.add_separator()
            menu.add_action(tr("删除"), lambda: self._delete_folder(folder_id), enabled=True)
        menu.popup(self.folder_list.mapToGlobal(pos))

    def _add_folder(self):
        """添加文件夹"""
        dialog = FolderInputDialog(self, tr("新建分类"), tr("请输入分类名称:"))
        if dialog.exec_():
            name = dialog.get_text()
            if name:
                folder = self.data_manager.add_folder(name)
                self._load_folders()

                # 选中新文件夹
                for i in range(self.folder_list.count()):
                    item = self.folder_list.item(i)
                    if item.data(QtCompat.UserRole) == folder.id:
                        self.folder_list.setCurrentItem(item)
                        self.folder_selected.emit(folder.id)
                        break

    def _rename_folder(self, folder_id: str):
        """重命名文件夹"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder:
            return

        dialog = FolderInputDialog(self, tr("重命名"), tr("请输入新名称:"), folder.name)
        if dialog.exec_():
            name = dialog.get_text()
            if name:
                QTimer.singleShot(
                    0, lambda fid=folder_id, new_name=name: self._rename_folder_after_dialog(fid, new_name)
                )

    def _rename_folder_after_dialog(self, folder_id: str, name: str):
        try:
            logger.info("确认重命名文件夹: folder_id=%s name=%s", folder_id, name)
            self.data_manager.rename_folder(folder_id, name)
            self._load_folders()
        except Exception as exc:
            logger.exception("重命名文件夹失败: folder_id=%s", folder_id)
            try:
                ThemedMessageBox.warning(
                    self,
                    tr("重命名失败"),
                    tr("重命名文件夹失败，请查看运行日志。\n{error}", error=str(exc)),
                )
            except Exception:
                logger.debug("显示重命名失败提示失败", exc_info=True)

    def _delete_folder(self, folder_id: str):
        """删除文件夹 - 使用主题化对话框"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if folder is None or folder.is_system:
            return

        # 使用 ThemedMessageBox 替代 QMessageBox
        from .main_window import ThemedMessageBox

        theme = self._get_current_theme()
        folder_name = str(folder.name)

        confirmed = ThemedMessageBox.question(
            self,
            tr("确认删除"),
            tr("确定要删除文件夹 '{name}' 吗?\n其中的快捷方式也会被删除。", name=folder_name),
            theme,
        )

        if confirmed:
            QTimer.singleShot(0, lambda fid=folder_id, name=folder_name: self._delete_folder_after_confirm(fid, name))

    def _delete_folder_after_confirm(self, folder_id: str, folder_name: str):
        try:
            logger.info("确认删除文件夹: folder_id=%s name=%s", folder_id, folder_name)
            deleted = self.data_manager.delete_folder(folder_id)
            logger.info("删除文件夹完成: folder_id=%s deleted=%s", folder_id, deleted)
            self._load_folders()
        except Exception as exc:
            logger.exception("删除文件夹失败: folder_id=%s", folder_id)
            try:
                ThemedMessageBox.warning(
                    self,
                    tr("删除失败"),
                    tr("删除文件夹失败，请查看运行日志。\n{error}", error=str(exc)),
                )
            except Exception:
                logger.debug("显示删除文件夹失败提示失败", exc_info=True)

    def _import_folder(self, folder_path: str):
        """导入文件夹并创建绑定分类

        Args:
            folder_path: 要导入的文件夹路径
        """
        # 1. 询问是否启用自动同步
        import_dialog = FolderImportDialog(self, os.path.basename(folder_path))
        result = import_dialog.exec_()
        accepted = QDialog.Accepted
        if result != accepted:
            return

        auto_sync = import_dialog.is_auto_sync_checked()

        # 2. 扫描文件夹
        from core.folder_scanner import FolderScanner

        shortcuts = FolderScanner.scan_folder(folder_path)

        if not shortcuts:
            ThemedMessageBox.warning(
                self, tr("文件夹为空"), tr("文件夹中没有找到支持的内容(子文件夹、.lnk 或 .exe 文件)")
            )
            return

        # 3. 创建新分类
        folder_name = os.path.basename(folder_path)
        folder = self.data_manager.add_folder(folder_name)

        # 4. 设置绑定属性
        folder.linked_path = folder_path
        folder.auto_sync = auto_sync
        folder.last_sync_time = time.time()

        # 5. 添加快捷方式
        self.data_manager.add_shortcuts(folder.id, shortcuts)

        # 6. 保存并刷新UI
        self.data_manager.save()
        self._load_folders()

        # 7. 选中新分类
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item.data(QtCompat.UserRole) == folder.id:
                self.folder_list.setCurrentItem(item)
                self.folder_selected.emit(folder.id)
                break

        # 8. 启动文件监听(如果启用自动同步)
        if auto_sync:
            self._start_folder_watch(folder.id)

        # 9. 显示成功消息
        ThemedMessageBox.information(
            self,
            tr("导入成功"),
            tr("已导入 {count} 个项目到分类 '{folder_name}'", count=len(shortcuts), folder_name=folder_name),
        )

    def _manual_sync(self, folder_id: str):
        """手动同步文件夹"""
        from core.folder_sync import sync_folder

        added, removed = sync_folder(self.data_manager, folder_id)

        ThemedMessageBox.information(
            self, tr("同步完成"), tr("新增 {added} 项,删除 {removed} 项", added=added, removed=removed)
        )

        # 如果当前选中的是这个文件夹,刷新显示
        current_item = self.folder_list.currentItem()
        if current_item and current_item.data(QtCompat.UserRole) == folder_id:
            self.folder_selected.emit(folder_id)

    def _toggle_auto_sync(self, folder_id: str):
        """切换自动同步状态"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder:
            return

        folder.auto_sync = not folder.auto_sync

        if folder.auto_sync:
            # 启动监听
            self._start_folder_watch(folder_id)
        else:
            # 停止监听
            from core.folder_watcher import get_watcher_manager

            get_watcher_manager().stop_watch(folder_id)

        self.data_manager.save()

        # 保存当前选中的文件夹
        current_selected_id = folder_id
        self._load_folders()

        # 恢复选中并刷新右侧图标栏
        for i in range(self.folder_list.count()):
            if self.folder_list.item(i).data(QtCompat.UserRole) == current_selected_id:
                self.folder_list.setCurrentRow(i)
                self.folder_selected.emit(current_selected_id)
                break

    def _open_linked_folder(self, folder_id: str):
        """打开绑定的文件夹"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if folder and folder.linked_path and os.path.exists(folder.linked_path):
            process_runtime.startfile(folder.linked_path)

    def _unlink_folder(self, folder_id: str):
        """解除文件夹绑定"""
        reply = ThemedMessageBox.question(
            self, "确认解除绑定", "解除绑定后将停止自动同步,但已导入的快捷方式会保留。\n确定继续吗?"
        )

        if reply == ThemedMessageBox.Yes:
            QTimer.singleShot(0, lambda fid=folder_id: self._unlink_folder_after_confirm(fid))

    def _unlink_folder_after_confirm(self, folder_id: str):
        try:
            folder = self.data_manager.data.get_folder_by_id(folder_id)
            if folder:
                folder.linked_path = ""
                folder.auto_sync = False

                # 停止监听
                from core.folder_watcher import get_watcher_manager

                get_watcher_manager().stop_watch(folder_id)

                self.data_manager.save()
                self._load_folders()
        except Exception as exc:
            logger.exception("解除文件夹绑定失败: folder_id=%s", folder_id)
            try:
                ThemedMessageBox.warning(
                    self,
                    tr("解除绑定失败"),
                    tr("解除文件夹绑定失败，请查看运行日志。\n{error}", error=str(exc)),
                )
            except Exception:
                logger.debug("显示解除绑定失败提示失败", exc_info=True)

    def _start_folder_watch(self, folder_id: str):
        """启动文件夹监听"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder or not folder.linked_path:
            return

        from core.folder_watcher import get_watcher_manager

        get_watcher_manager().start_watch(folder_id, folder.linked_path, self._on_folder_changed)

    def _on_folder_changed(self, folder_id: str):
        """文件夹内容变化回调（从 watchdog 线程调用）

        使用 pyqtSignal.emit() 而不是 QTimer.singleShot()，
        因为 pyqtSignal.emit() 是线程安全的，而 QTimer 从非 Qt 线程调用是不安全的。
        """
        self._folder_sync_requested.emit(folder_id)

    def _auto_sync(self, folder_id: str):
        """自动同步文件夹（静默执行，不弹对话框）"""
        import logging

        sync_logger = logging.getLogger(__name__)
        try:
            from core.folder_sync import sync_folder

            added, removed = sync_folder(self.data_manager, folder_id)
            if added > 0 or removed > 0:
                sync_logger.info(f"自动同步完成: 新增 {added} 项, 删除 {removed} 项")
                # 如果当前选中的是这个文件夹，刷新显示
                current_item = self.folder_list.currentItem()
                if current_item and current_item.data(QtCompat.UserRole) == folder_id:
                    self.folder_selected.emit(folder_id)
                # 通知上层刷新弹窗数据
                try:
                    parent = self.parent()
                    while parent:
                        if hasattr(parent, "settings_changed"):
                            parent.settings_changed.emit()
                            break
                        parent = parent.parent()
                except Exception as exc:
                    logger.debug("发送设置变更信号失败: %s", exc, exc_info=True)
        except Exception as e:
            sync_logger.error(f"自动同步失败: {e}")

    def _restore_folder_watches_async(self):
        """异步恢复所有启用自动同步的文件夹监听（在后台线程中执行 Observer 初始化）"""
        import logging

        from core.background_tasks import start_background_thread

        logger = logging.getLogger(__name__)

        # 收集需要监听的文件夹信息
        watch_tasks = []
        for folder in self.data_manager.data.folders:
            if folder.linked_path and folder.auto_sync:
                watch_tasks.append((folder.id, folder.linked_path, folder.name))

        if not watch_tasks:
            return

        def do_restore():
            """在后台线程中初始化 watchdog Observer 并注册监听"""
            try:
                from core.folder_watcher import get_watcher_manager

                watcher = get_watcher_manager()
                for folder_id, linked_path, folder_name in watch_tasks:
                    try:
                        watcher.start_watch(folder_id, linked_path, self._on_folder_changed)
                    except Exception as e:
                        logger.error(f"恢复文件夹监听失败 {folder_name}: {e}")
            except Exception as e:
                logger.error(f"初始化文件夹监听管理器失败: {e}")

        self._restore_watch_thread = start_background_thread(
            name="RestoreFolderWatches",
            target=do_restore,
            owner=self,
        )

    def _restore_folder_watches(self):
        """恢复所有启用自动同步的文件夹监听（同步版本，已弃用，保留兼容）"""
        self._restore_folder_watches_async()

    def _handle_folder_reorder(self, source_id: str, target_id: str):
        """处理文件夹重新排序（参考图标排列逻辑）"""
        all_folder_ids = [f.id for f in self.data_manager.data.folders]
        reordered_ids = move_folder_id_to_target(all_folder_ids, source_id, target_id)
        if not reordered_ids:
            return

        self.data_manager.reorder_folders(reordered_ids)

        # 保存当前选中的文件夹ID
        current_selected_id = source_id

        self._load_folders()

        # 恢复选中到被拖动的文件夹
        for i in range(self.folder_list.count()):
            if self.folder_list.item(i).data(QtCompat.UserRole) == current_selected_id:
                self.folder_list.setCurrentRow(i)
                # 发送信号刷新右侧图标栏
                self.folder_selected.emit(current_selected_id)
                break
