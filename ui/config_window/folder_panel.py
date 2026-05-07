"""
文件夹面板
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QMenu, QInputDialog, QMessageBox, QFrame,
    QDialog, QLineEdit, QHBoxLayout, QLabel, QCheckBox,
    Qt, QtCompat, pyqtSignal, PYQT_VERSION, QPainterPath, QRegion,
    QPainter, QColor, QPen, QRectF, QApplication, QPoint, QTimer,
    QIcon, QSize, QStyledItemDelegate, QDrag, QMimeData,
    QGraphicsDropShadowEffect
)

from ui.utils.window_effect import enable_window_shadow_and_round_corners, enable_acrylic_for_config_window, is_win11, get_window_effect
from core import DataManager
from ui.styles.style import PopupMenu, get_dialog_stylesheet
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.dialog_helper import center_dialog_on_main_window
from .base_dialog import BaseDialog


class FolderItemDelegate(QStyledItemDelegate):
    """文件夹列表项委托 - 绘制拖放目标提示"""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        # 检查是否为拖放目标
        is_drop_target = index.data(QtCompat.UserRole + 1)
        if is_drop_target:
            painter.setRenderHint(QtCompat.Antialiasing)
            # 使用实线边框和半透明背景，参考图标排列栏样式
            painter.setPen(QPen(QColor(70, 130, 180, 200), 2))
            painter.setBrush(QColor(70, 130, 180, 100))
            rect = option.rect.adjusted(2, 2, -2, -2)
            painter.drawRoundedRect(rect, 8, 8)


class FolderInputDialog(BaseDialog):
    """自定义文件夹输入对话框（支持主题）"""

    def __init__(self, parent=None, title="新建文件夹", label="请输入文件夹名称:", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 标签
        self.label = QLabel(label)
        layout.addWidget(self.label)
        
        # 输入框
        self.input_edit = QLineEdit()
        self.input_edit.setText(text)
        layout.addWidget(self.input_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        self.setStyleSheet(get_dialog_stylesheet(self.theme))
    
    def _on_ok(self):
        if self.input_edit.text().strip():
            self.accept()
    
    def get_text(self) -> str:
        return self.input_edit.text().strip()


class FolderImportDialog(BaseDialog):
    """导入文件夹确认对话框（支持主题）"""

    def __init__(self, parent=None, folder_name=""):
        super().__init__(parent)
        self.setWindowTitle("导入文件夹")
        self.setModal(True)
        self.setMinimumWidth(240)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # 标题
        title_label = QLabel(f"将创建新分类: {folder_name}")
        title_label.setStyleSheet("font-weight: 400; font-size: 14px;")
        layout.addWidget(title_label)

        # 说明文本
        info_label = QLabel("是否启用文件夹自动同步?\n(启用后,文件夹内容变化时会自动更新)")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 复选框
        self.sync_check = QCheckBox("启用自动同步")
        self.sync_check.setChecked(True)  # 默认启用
        layout.addWidget(self.sync_check)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        self.setStyleSheet(get_dialog_stylesheet(self.theme))

    def is_auto_sync_checked(self):
        """返回自动同步复选框的状态"""
        return self.sync_check.isChecked()


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
        layout.setContentsMargins(8, 8, 8, 1)
        layout.setSpacing(8)

        self.list_frame = QFrame()
        self.list_frame.setObjectName("folderListFrame")
        list_frame_layout = QVBoxLayout(self.list_frame)
        list_frame_layout.setContentsMargins(7, 4, 7, 7)
        list_frame_layout.setSpacing(10)

        self.folder_list = QListWidget()
        self.folder_list.setObjectName("folderList")
        self.folder_list.setIconSize(QSize(18, 18))
        # 设置自定义委托以绘制拖放提示
        self.folder_list.setItemDelegate(FolderItemDelegate())
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
            except Exception:
                pass

        list_frame_layout.addWidget(self.folder_list)

        # 新建按钮 - 放在 list_frame 内部，底框包含按钮
        self.add_btn = QPushButton("＋ 新建分类")
        self.add_btn.clicked.connect(self._add_folder)
        self.add_btn.setFixedHeight(36)
        list_frame_layout.addWidget(self.add_btn)

        layout.addWidget(self.list_frame, 1)
        
        # 应用初始主题
        self.apply_theme(self._get_current_theme())

    def apply_theme(self, theme: str):
        if theme == "dark":
            frame_bg = "rgba(255, 255, 255, 0.06)"
            frame_border = "rgba(255, 255, 255, 0.10)"
            item_hover = "rgba(255, 255, 255, 0.08)"
            item_selected_bg = "rgba(255, 255, 255, 0.14)"
            item_selected_text = "rgba(255, 255, 255, 0.95)"
            item_text = "rgba(255, 255, 255, 0.85)"
            btn_bg = "rgba(255, 255, 255, 0.18)"
            btn_border_color = "rgba(255, 255, 255, 0.22)"
            btn_hover_bg = "rgba(255, 255, 255, 0.28)"
            btn_hover_text = "rgba(255, 255, 255, 0.95)"
            btn_color = "rgba(255, 255, 255, 0.80)"
        else:
            frame_bg = "rgba(255, 255, 255, 0.20)"
            frame_border = "rgba(0, 0, 0, 0.06)"
            item_hover = "rgba(0, 0, 0, 0.04)"
            item_selected_bg = "rgba(0, 0, 0, 0.08)"
            item_selected_text = "rgba(28, 28, 30, 0.95)"
            item_text = "rgba(28, 28, 30, 0.85)"
            btn_bg = "rgba(255, 255, 255, 0.75)"
            btn_border_color = "rgba(255, 255, 255, 0.35)"
            btn_hover_bg = "rgba(255, 255, 255, 0.95)"
            btn_hover_text = "rgba(28, 28, 30, 0.9)"
            btn_color = "rgba(28, 28, 30, 0.65)"

        self.list_frame.setStyleSheet(f"""
            QFrame#folderListFrame {{
                background-color: {frame_bg};
                border: 1px solid {frame_border};
                border-radius: 10px;
            }}
        """)

        self.folder_list.setStyleSheet(f"""
            QListWidget#folderList {{
                outline: none;
                background: transparent;
                border: none;
            }}
            QListWidget#folderList::item {{
                padding: 8px;
                border-radius: 8px;
                margin: 1px 0px;
                color: {item_text};
            }}
            QListWidget#folderList::item:selected {{
                background-color: {item_selected_bg};
                color: {item_selected_text};
            }}
            QListWidget#folderList::item:hover:!selected {{
                background-color: {item_hover};
            }}
        """)

        self.add_btn.setStyleSheet(f"""
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
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 35 if theme == "dark" else 20))
        self.add_btn.setGraphicsEffect(shadow)
    
    def _get_current_theme(self) -> str:
        """获取当前主题"""
        try:
            return self.data_manager.get_settings().theme
        except:
            return "dark"
    
    def _get_menu_stylesheet(self) -> str:
        """获取右键菜单样式 — 半透明背景配合模糊效果"""
        theme = self._get_current_theme()

        if theme == "dark":
            return """
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
        else:
            return """
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
    
    def _load_folders(self):
        """加载文件夹列表"""
        self.folder_list.clear()

        # 动态绑定拖放事件处理
        self.folder_list.startDrag = self._list_start_drag
        self.folder_list.dragEnterEvent = self._list_drag_enter_event
        self.folder_list.dragMoveEvent = self._list_drag_move_event
        self.folder_list.dragLeaveEvent = self._list_drag_leave_event
        self.folder_list.dropEvent = self._list_drop_event

        # 加载文件夹图标 (从 assets/Folder.ico 读取蓝色图标)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        icon_path = os.path.join(base_dir, "assets", "Folder.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, "Folder.ico")

        folder_icon = QIcon(icon_path) if os.path.exists(icon_path) else None

        for folder in self.data_manager.data.folders:
            item = QListWidgetItem()

            # 根据类型设置文本 (移除黄色的文件夹 emoji，保留状态 emoji)
            if folder.is_dock:
                display_text = f"{folder.name}"
            elif folder.linked_path and folder.auto_sync:
                display_text = f"{folder.name}"
            else:
                display_text = folder.name

            item.setText(display_text)
            item.setData(QtCompat.UserRole, folder.id)

            # 设置蓝色的 QIcon 图标
            if folder_icon:
                item.setIcon(folder_icon)

            # 系统文件夹不可拖拽
            if folder.is_system:
                flags = item.flags()
                flags &= ~QtCompat.ItemIsDragEnabled
                item.setFlags(flags)

            self.folder_list.addItem(item)

        # 选中第一个非Dock文件夹
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder_id = item.data(QtCompat.UserRole)
            folder = self.data_manager.data.get_folder_by_id(folder_id)
            if folder and not folder.is_dock:
                self.folder_list.setCurrentItem(item)
                self.folder_selected.emit(folder_id)
                break

    def _list_start_drag(self, supported_actions):
        """自定义文件夹拖动开始事件"""
        item = self.folder_list.currentItem()
        if not item:
            return

        drag = QDrag(self.folder_list)
        mime_data = QMimeData()

        # 设置特殊标识：这是文件夹排序拖动
        folder_id = item.data(QtCompat.UserRole)
        mime_data.setData("application/x-folder-reorder", folder_id.encode())

        drag.setMimeData(mime_data)
        drag.exec_(QtCompat.MoveAction)

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
        """处理拖动移动事件"""
        # 清除所有项的拖放标记
        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            list_item.setData(QtCompat.UserRole + 1, False)

        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        item = self.folder_list.itemAt(pos)

        # 文件夹排序拖动：允许所有文件夹作为目标
        if event.mimeData().hasFormat("application/x-folder-reorder"):
            if item:
                item.setData(QtCompat.UserRole + 1, True)
                self.folder_list.viewport().update()
            event.acceptProposedAction()
        # 外部文件拖入
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        # 图标拖动：检查同步文件夹限制
        elif event.mimeData().hasFormat("application/x-shortcut-id"):
            if event.mimeData().hasFormat("application/x-source-folder-id"):
                source_folder_id = event.mimeData().data("application/x-source-folder-id").data().decode()
                source_folder = self.data_manager.data.get_folder_by_id(source_folder_id)

                if source_folder and source_folder.linked_path and source_folder.auto_sync:
                    while QApplication.overrideCursor():
                        QApplication.restoreOverrideCursor()
                    QApplication.setOverrideCursor(Qt.ForbiddenCursor)
                    event.ignore()
                    return

            if item:
                folder_id = item.data(QtCompat.UserRole)
                folder = self.data_manager.data.get_folder_by_id(folder_id)

                if folder and folder.linked_path and folder.auto_sync:
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
        """处理拖动离开事件"""
        # 恢复光标
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()

        # 清除所有拖放提示
        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            list_item.setData(QtCompat.UserRole + 1, False)
        self.folder_list.viewport().update()

    def _list_drop_event(self, event):
        """处理放下事件"""
        # 恢复光标
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()

        # 找到标记为拖放目标的项
        target_item = None
        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            if list_item.data(QtCompat.UserRole + 1):
                target_item = list_item
            list_item.setData(QtCompat.UserRole + 1, False)
        self.folder_list.viewport().update()

        # 文件夹排序拖动
        if event.mimeData().hasFormat("application/x-folder-reorder"):
            if target_item:
                source_id = event.mimeData().data("application/x-folder-reorder").data().decode()
                target_id = target_item.data(QtCompat.UserRole)
                self._handle_folder_reorder(source_id, target_id)
            event.acceptProposedAction()
        # 外部文件/文件夹拖入
        elif event.mimeData().hasUrls():
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
            if target_item:
                target_folder_id = target_item.data(QtCompat.UserRole)
                folder = self.data_manager.data.get_folder_by_id(target_folder_id)

                if folder and folder.linked_path and folder.auto_sync:
                    event.ignore()
                    return

                shortcut_id = event.mimeData().data("application/x-shortcut-id").data().decode()

                if self.data_manager.move_shortcut_to_folder(shortcut_id, target_folder_id):
                    current_item = self.folder_list.currentItem()
                    if current_item:
                        current_folder_id = current_item.data(QtCompat.UserRole)
                        self.folder_selected.emit(current_folder_id)

                event.acceptProposedAction()
        else:
            event.ignore()
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """点击项目"""
        folder_id = item.data(QtCompat.UserRole)
        # 确保只有一个选中状态
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

        theme = self._get_current_theme()
        menu = PopupMenu(theme=theme, radius=12, parent=None)
        menu.add_action("重命名", lambda: self._rename_folder(folder_id), enabled=True)

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
            menu.add_action("删除", lambda: self._delete_folder(folder_id), enabled=True)
        menu.popup(self.folder_list.mapToGlobal(pos))

    def _add_folder(self):
        """添加文件夹"""
        dialog = FolderInputDialog(self, "新建分类", "请输入分类名称:")
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
        
        dialog = FolderInputDialog(self, "重命名", "请输入新名称:", folder.name)
        if dialog.exec_():
            name = dialog.get_text()
            if name:
                self.data_manager.rename_folder(folder_id, name)
                self._load_folders()
    
    def _delete_folder(self, folder_id: str):
        """删除文件夹 - 使用主题化对话框"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder or folder.is_system:
            return

        # 使用 ThemedMessageBox 替代 QMessageBox
        from .main_window import ThemedMessageBox
        theme = self._get_current_theme()

        confirmed = ThemedMessageBox.question(
            self,
            "确认删除",
            f"确定要删除文件夹 '{folder.name}' 吗?\n其中的快捷方式也会被删除。",
            theme
        )

        if confirmed:
            self.data_manager.delete_folder(folder_id)
            self._load_folders()

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
                self, "文件夹为空",
                f"文件夹中没有找到支持的内容(子文件夹、.lnk 或 .exe 文件)"
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
            self, "导入成功",
            f"已导入 {len(shortcuts)} 个项目到分类 '{folder_name}'"
        )

    def _manual_sync(self, folder_id: str):
        """手动同步文件夹"""
        from core.folder_sync import sync_folder
        added, removed = sync_folder(self.data_manager, folder_id)

        ThemedMessageBox.information(
            self, "同步完成",
            f"新增 {added} 项,删除 {removed} 项"
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
            os.startfile(folder.linked_path)

    def _unlink_folder(self, folder_id: str):
        """解除文件夹绑定"""
        reply = ThemedMessageBox.question(
            self, "确认解除绑定",
            "解除绑定后将停止自动同步,但已导入的快捷方式会保留。\n确定继续吗?"
        )

        if reply == ThemedMessageBox.Yes:
            folder = self.data_manager.data.get_folder_by_id(folder_id)
            if folder:
                folder.linked_path = ""
                folder.auto_sync = False

                # 停止监听
                from core.folder_watcher import get_watcher_manager
                get_watcher_manager().stop_watch(folder_id)

                self.data_manager.save()
                self._load_folders()

    def _start_folder_watch(self, folder_id: str):
        """启动文件夹监听"""
        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder or not folder.linked_path:
            return

        from core.folder_watcher import get_watcher_manager
        get_watcher_manager().start_watch(
            folder_id,
            folder.linked_path,
            self._on_folder_changed
        )

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
                        if hasattr(parent, 'settings_changed'):
                            parent.settings_changed.emit()
                            break
                        parent = parent.parent()
                except Exception:
                    pass
        except Exception as e:
            sync_logger.error(f"自动同步失败: {e}")

    def _restore_folder_watches_async(self):
        """异步恢复所有启用自动同步的文件夹监听（在后台线程中执行 Observer 初始化）"""
        import logging
        import threading
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
                        watcher.start_watch(
                            folder_id,
                            linked_path,
                            self._on_folder_changed
                        )
                    except Exception as e:
                        logger.error(f"恢复文件夹监听失败 {folder_name}: {e}")
            except Exception as e:
                logger.error(f"初始化文件夹监听管理器失败: {e}")

        threading.Thread(target=do_restore, name="RestoreFolderWatches", daemon=True).start()

    def _restore_folder_watches(self):
        """恢复所有启用自动同步的文件夹监听（同步版本，已弃用，保留兼容）"""
        self._restore_folder_watches_async()

    def _handle_folder_reorder(self, source_id: str, target_id: str):
        """处理文件夹重新排序（参考图标排列逻辑）"""
        # 获取所有文件夹ID（从数据管理器，不是UI列表）
        all_folder_ids = [f.id for f in self.data_manager.data.folders]

        source_index = -1
        target_index = -1

        for i, fid in enumerate(all_folder_ids):
            if fid == source_id:
                source_index = i
            if fid == target_id:
                target_index = i

        if source_index < 0 or target_index < 0 or source_index == target_index:
            return

        # 移除源位置，插入到目标位置
        all_folder_ids.pop(source_index)
        all_folder_ids.insert(target_index, source_id)

        self.data_manager.reorder_folders(all_folder_ids)

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
