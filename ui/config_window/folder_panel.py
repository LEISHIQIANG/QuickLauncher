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
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, pyqtProperty,
    QPropertyAnimation, QEasingCurve, QBrush, QPixmap
)

from ui.utils.window_effect import enable_window_shadow_and_round_corners, enable_acrylic_for_config_window, is_win11, get_window_effect
from core import DataManager
from ui.styles.style import PopupMenu, get_dialog_stylesheet
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.dialog_helper import center_dialog_on_main_window
from .base_dialog import BaseDialog


class FolderItemDelegate(QStyledItemDelegate):
    """文件夹列表项委托 - 绘制拖放目标提示"""

    def __init__(self, owner=None):
        super().__init__()
        self._owner = owner

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        # 检查是否为拖放目标
        is_drop_target = index.data(QtCompat.UserRole + 1)
        if is_drop_target:
            theme = "dark"
            if self._owner:
                theme = self._owner._get_current_theme()

            painter.setRenderHint(QtCompat.Antialiasing)

            if theme == "dark":
                # Dark theme: fresh mint green (minty pastel)
                pen_color = QColor(168, 230, 207, 180)
                brush_color = QColor(168, 230, 207, 45)
            else:
                # Light theme: gorgeous pastel mint green
                pen_color = QColor(70, 180, 140, 200)
                brush_color = QColor(168, 230, 207, 75)

            painter.setPen(QPen(pen_color, 1.5))
            painter.setBrush(brush_color)
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


class FolderItemWidget(QWidget):
    """Custom folder item widget supporting Apple-style press scale feedback and theme-aware styling."""
    
    def __init__(self, text, icon, theme="dark", parent=None):
        super().__init__(parent)
        self.text = text
        self.icon = icon
        self.theme = theme
        self._scale_factor = 1.0
        self.item = None  # Reference to QListWidgetItem
        self._scale_anim = None
        self.setMouseTracking(True)
    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        h = max(18, fm.height()) + 18  # 18px padding total (9px top/bottom)
        return QSize(100, h)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor
        
    @scale_factor.setter
    def scale_factor(self, value: float):
        self._scale_factor = value
        self.update()
        
    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Determine selection and hover states
        is_selected = False
        if self.item is not None:
            is_selected = self.item.isSelected()
        is_hovered = self.underMouse()
        
        # Draw hover background
        if is_hovered and not is_selected:
            if self.theme == "dark":
                hover_bg = QColor(255, 255, 255, 15)  # rgba(255, 255, 255, 0.06)
            else:
                hover_bg = QColor(0, 0, 0, 10)  # rgba(0, 0, 0, 0.04)
            painter.setBrush(hover_bg)
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 1, 0, -1), 8, 8)
            
        # Draw icon
        if self.icon:
            pixmap = self.icon.pixmap(18, 18)
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(8, y, pixmap)
            
        # Draw text
        if self.theme == "dark":
            text_color = QColor(255, 255, 255, 242) if is_selected else (QColor(255, 255, 255, 217) if is_hovered else QColor(255, 255, 255, 180))
        else:
            text_color = QColor(28, 28, 30, 242) if is_selected else (QColor(28, 28, 30, 217) if is_hovered else QColor(28, 28, 30, 165))
            
        painter.setPen(text_color)
        from ui.utils.font_manager import get_qfont
        painter.setFont(get_qfont(12))
        
        text_rect = QRectF(32, 0, self.width() - 42, self.height())
        painter.drawText(text_rect, QtCompat.AlignLeft | QtCompat.AlignVCenter, self.text)
        
        painter.end()


class FolderListWidget(QListWidget):
    """Folder list with stable Qt drag/drop virtual method dispatch and sliding selection anim."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self._pill_rect = QRectF()
        self._pill_opacity = 0.0
        self._pill_rect_anim = None
        self._pill_opacity_anim = None
        
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
    @pyqtProperty(QRectF)
    def pill_rect(self) -> QRectF:
        return self._pill_rect
        
    @pill_rect.setter
    def pill_rect(self, rect: QRectF):
        self._pill_rect = rect
        self.viewport().update()
        
    @pyqtProperty(float)
    def pill_opacity(self) -> float:
        return self._pill_opacity
        
    @pill_opacity.setter
    def pill_opacity(self, opacity: float):
        self._pill_opacity = opacity
        self.viewport().update()
        
    def _on_selection_changed(self, selected, deselected):
        curr_indexes = self.selectedIndexes()
        if curr_indexes:
            index = curr_indexes[0]
            visual_rect = self.visualRect(index)
            target_rect = QRectF(visual_rect).adjusted(0, 1, 0, -1)
            
            if self._pill_rect_anim is not None:
                self._pill_rect_anim.stop()
                
            if self._pill_rect.isEmpty() or self._pill_opacity < 0.1:
                self._pill_rect = target_rect
            else:
                self._pill_rect_anim = QPropertyAnimation(self, b"pill_rect")
                self._pill_rect_anim.setDuration(220)
                self._pill_rect_anim.setStartValue(self._pill_rect)
                self._pill_rect_anim.setEndValue(target_rect)
                self._pill_rect_anim.setEasingCurve(QEasingCurve.OutCubic)
                self._pill_rect_anim.start()
                
            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(1.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()
        else:
            if self._pill_opacity_anim is not None:
                self._pill_opacity_anim.stop()
            self._pill_opacity_anim = QPropertyAnimation(self, b"pill_opacity")
            self._pill_opacity_anim.setDuration(180)
            self._pill_opacity_anim.setStartValue(self._pill_opacity)
            self._pill_opacity_anim.setEndValue(0.0)
            self._pill_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pill_opacity_anim.start()

    def startDrag(self, supported_actions):
        self._owner._list_start_drag(supported_actions)

    def dragEnterEvent(self, event):
        self._owner._list_drag_enter_event(event)

    def dragMoveEvent(self, event):
        self._owner._list_drag_move_event(event)

    def dragLeaveEvent(self, event):
        self._owner._list_drag_leave_event(event)

    def dropEvent(self, event):
        self._owner._list_drop_event(event)

    def paintEvent(self, event):
        if self._pill_opacity > 0 and not self._pill_rect.isEmpty():
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            
            theme = self._owner._get_current_theme()
            if theme == "dark":
                pill_color = QColor(255, 255, 255, int(self._pill_opacity * 35))  # rgba(255, 255, 255, 0.14)
            else:
                pill_color = QColor(0, 0, 0, int(self._pill_opacity * 20))  # rgba(0, 0, 0, 0.08)
                
            painter.setBrush(QBrush(pill_color))
            painter.setPen(QtCompat.NoPen)
            painter.drawRoundedRect(self._pill_rect, 8, 8)
            painter.end()
            
        super().paintEvent(event)


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

        self.folder_list = FolderListWidget(self)
        self.folder_list.setObjectName("folderList")
        self.folder_list.setIconSize(QSize(18, 18))
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

        self.list_frame.setStyleSheet(f"""
            QFrame#folderListFrame {{
                background-color: {frame_bg};
                border: 1px solid {frame_border};
                border-radius: 10px;
            }}
        """)

        # Items are drawn by FolderItemWidget, stylesheet just resets default background
        self.folder_list.setStyleSheet("""
            QListWidget#folderList {
                outline: none;
                background: transparent;
                border: none;
            }
            QListWidget#folderList::item {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 1px 0px;
            }
            QListWidget#folderList::item:selected {
                background: transparent;
                border: none;
            }
            QListWidget#folderList::item:hover {
                background: transparent;
                border: none;
            }
        """)

        # Propagate theme change to any existing FolderItemWidgets
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            widget = self.folder_list.itemWidget(item)
            if isinstance(widget, FolderItemWidget):
                widget.theme = theme
                widget.update()

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
            widget = FolderItemWidget(display_text, folder_icon, self._get_current_theme(), self.folder_list)
            widget.item = item
            
            item.setSizeHint(widget.sizeHint())

            self.folder_list.addItem(item)
            self.folder_list.setItemWidget(item, widget)

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
        painter.setOpacity(0.75)  # Floating glass translucent card
        painter.drawPixmap(0, 0, pixmap)

        # Soft fresh mint overlay border around the preview
        painter.setOpacity(0.9)
        theme = self._get_current_theme()
        if theme == "dark":
            border_color = QColor(168, 230, 207, 150)
        else:
            border_color = QColor(70, 180, 140, 220)

        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QtCompat.NoBrush)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)
        painter.end()

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
            except Exception:
                pass

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

        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
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
                        pass
                        
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
                    pass
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
                            pass
        # 外部拖入
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
        """处理拖动离开事件 - 拖离时弹性还原位置"""
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()

        source_item = self.folder_list.currentItem()
        if source_item and hasattr(self, '_initial_drag_row') and self._initial_drag_row >= 0:
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
                        pass

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
                    pass
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
                            pass

        for i in range(self.folder_list.count()):
            list_item = self.folder_list.item(i)
            list_item.setData(QtCompat.UserRole + 1, False)
        self.folder_list.viewport().update()

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
                
            final_row = self.folder_list.row(source_item)
            
            widget = self.folder_list.itemWidget(source_item)
            if widget:
                try:
                    widget.setGraphicsEffect(None)
                except Exception:
                    pass
                    
            if hasattr(self, '_initial_drag_row') and self._initial_drag_row >= 0:
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
