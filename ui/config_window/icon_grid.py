"""
图标网格 - 设置窗口版本（四按钮横向排列）
"""

import copy
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import AppData, DataManager, ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QApplication,
    QColor,
    QDrag,
    QEasingCurve,
    QFont,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QImage,
    QLabel,
    QMenu,
    QMimeData,
    QObject,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPropertyAnimation,
    QPushButton,
    QRect,
    QRegion,
    QSize,
    Qt,
    QtCompat,
    QThread,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

# 使用统一的风格组件
from ui.styles.style import Glassmorphism, PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.smooth_scroll import SmoothScrollArea

from .action_button_icons import create_action_button_icon
from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class MoveFolderDialog(BaseDialog):
    """移动到文件夹对话框"""

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = folders
        self.selected_folder = None
        self.setWindowTitle(tr("移动到文件夹"))
        self.setFixedSize(240, 135)
        self._setup_ui()
        self._apply_theme_colors()

    def _setup_ui(self):
        from qt_compat import QComboBox

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        label = QLabel(tr("目标文件夹:"))
        label.setStyleSheet("font-size: 11px;")
        main_layout.addWidget(label)

        self.combo = QComboBox()
        self.combo.setFixedHeight(30)
        for folder in self.folders:
            self.combo.addItem(folder.name, folder)
        self.combo.showPopup = lambda: self._show_folder_popup()
        main_layout.addWidget(self.combo)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.setFixedHeight(28)
        self.cancel_btn.setMinimumWidth(60)
        self.cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton(tr("确定"))
        self.ok_btn.setFixedHeight(28)
        self.ok_btn.setMinimumWidth(60)
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._on_ok)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

    def _show_folder_popup(self):
        menu = PopupMenu(theme=self.theme, radius=12, parent=self)
        for i in range(self.combo.count()):
            folder_name = self.combo.itemText(i)
            menu.add_action(folder_name, lambda idx=i: self.combo.setCurrentIndex(idx))
        pos = self.combo.mapToGlobal(self.combo.rect().bottomLeft())
        menu.setMinimumWidth(self.combo.width())
        menu.popup(pos)

    def _on_ok(self):
        self.selected_folder = self.combo.currentData()
        self.accept()

    def _apply_theme_colors(self):
        super()._apply_theme_colors()
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(self.theme)
        self.setStyleSheet(base_style + "QDialog { background: transparent; border: none; }")


class IconContainer(QWidget):
    """图标容器 - 支持空白区域右键菜单"""

    context_menu_requested = pyqtSignal(QPoint)
    blank_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        # 检查点击位置是否在子控件上
        child = self.childAt(event.pos())
        if child is None or child == self:
            if event.button() == QtCompat.LeftButton:
                self.blank_clicked.emit()
                event.accept()
                return
            if event.button() == QtCompat.RightButton:
                # 空白区域，显示菜单
                global_pos = self.mapToGlobal(event.pos())
                self.context_menu_requested.emit(global_pos)
                event.accept()
                return
        super().mousePressEvent(event)


class _IconLoadWorker(QObject):
    """后台图标加载 worker（使用 QImage 保证线程安全）"""

    finished = pyqtSignal(str, QImage)  # (shortcut_id, image)
    completed = pyqtSignal()

    def __init__(self, tasks):
        super().__init__()
        self._tasks = tasks
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        from core.icon_extractor import IconExtractor

        try:
            import ctypes

            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass

        try:
            for sid, icon_path, target_path, size, stype in self._tasks:
                if self._cancel_requested:
                    break
                image = QImage()

                import os
                import sys

                is_folder_type = stype == ShortcutType.FOLDER
                if stype == ShortcutType.FILE and target_path and os.path.isdir(target_path):
                    is_folder_type = True

                if not icon_path and is_folder_type:
                    possible_paths = [
                        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "Folder.ico"),
                        os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "assets",
                            "Folder.ico",
                        ),
                    ]
                    if hasattr(sys, "_MEIPASS"):
                        possible_paths.insert(0, os.path.join(sys._MEIPASS, "assets", "Folder.ico"))
                    for p in possible_paths:
                        if os.path.exists(p):
                            icon_path = p
                            target_path = None
                            break

                try:
                    image = self._load_one(IconExtractor, icon_path, target_path, size)
                except Exception as e:
                    logger.debug(
                        "[IconDiag] grid worker exception sid=%s icon_path=%r target_path=%r size=%s error=%s",
                        sid,
                        icon_path,
                        target_path,
                        size,
                        e,
                    )
                if self._cancel_requested:
                    break
                self.finished.emit(sid, image if image else QImage())
        finally:
            try:
                import ctypes

                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass
            self.completed.emit()

    @staticmethod
    def _load_one(IE, icon_path, target_path, size):
        """线程安全的单个图标加载（只用 QImage，不用 QPixmap/QIcon）"""
        if icon_path:
            if IE._is_pixmap_preferred_resource(icon_path):
                IE._diag("grid worker defer resource icon_path=%s size=%s", icon_path, size)
                return None
            r = IE.from_file(icon_path, size, return_image=True)
            if r and not r.isNull():
                IE._diag("grid worker source=from_file icon_path=%s size=%s", icon_path, size)
                return r

        if target_path:
            if IE._is_pixmap_preferred_resource(target_path):
                IE._diag("grid worker defer resource target_path=%s size=%s", target_path, size)
                return None
            r = IE.extract(
                target_path,
                target_path,
                size,
                return_image=True,
                fallback_to_default=False,
            )
            if r and not r.isNull():
                IE._diag("grid worker source=extract target_path=%s size=%s", target_path, size)
                return r

        IE._warn_once(
            f"grid-worker:{icon_path}|{target_path}|{size}",
            "grid worker failed icon_path=%r target_path=%r size=%s",
            icon_path,
            target_path,
            size,
        )
        return None


class IconWidget(QFrame):
    """单个图标控件"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    context_menu_requested = pyqtSignal(QPoint)
    drag_started = pyqtSignal(str)

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

        self._setup_ui()
        self.setAcceptDrops(True)
        self._set_normal_style()

    def _setup_ui(self):
        self.setFixedSize(self.cell_size, self.cell_size)
        self.setCursor(QtCompat.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(QtCompat.AlignCenter)

        # 图标底框：图标四周各大7px
        icon_frame_h = self.icon_size + 14
        icon_frame_w = self.icon_size + 14
        self.icon_frame = QFrame()
        self.icon_frame.setFixedSize(icon_frame_w, icon_frame_h)
        self.icon_frame.setStyleSheet(self._icon_frame_style())
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
        self.name_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self.name_label.setWordWrap(True)
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.name_label)

        self._load_icon()

    def _icon_frame_style(self, hover=False, drop=False):
        if self._is_selected:
            return "QFrame { background-color: rgba(100,181,246,26); border-radius: 9px; border: 1px solid rgba(100,181,246,170); }"
        if drop:
            if self.theme == "dark":
                return "QFrame { background-color: rgba(168, 230, 207, 45); border-radius: 9px; border: 2px dashed rgba(168, 230, 207, 180); }"
            else:
                return "QFrame { background-color: rgba(168, 230, 207, 75); border-radius: 9px; border: 2px dashed rgba(70, 180, 140, 200); }"
        bg = self._hover_bg if hover else self._normal_bg
        return f"QFrame {{ background-color: {bg}; border-radius: 9px; border: {self._border}; }}"

    def _load_icon(self):
        """设置占位图标（实际图标由 IconGrid 异步加载）"""
        if self.shortcut.type == ShortcutType.HOTKEY:
            pixmap = self._create_hotkey_icon()
        elif self.shortcut.type == ShortcutType.URL:
            pixmap = self._create_url_icon()
        elif self.shortcut.type == ShortcutType.COMMAND:
            pixmap = self._create_command_icon()
        elif self.shortcut.type == ShortcutType.CHAIN:
            pixmap = self._create_chain_icon()
        else:
            pixmap = None

        if not pixmap:
            pixmap = self._create_default_icon()

        self.icon_label.setPixmap(pixmap)

    def _create_default_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setBrush(QColor(135, 206, 250))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        radius = size // 6
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, radius, radius)

        first_char = self.shortcut.name[0] if self.shortcut.name else "?"
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", int(size * 0.4))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, first_char)
        painter.end()

        return pixmap

    def _create_hotkey_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        painter.setBrush(QColor(70, 130, 180))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⌨")

        painter.end()
        return pixmap

    def _create_url_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        painter.setBrush(QColor(60, 160, 120))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "🌐")

        painter.end()
        return pixmap

    def _create_command_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        painter.setBrush(QColor(50, 50, 50))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)

        painter.setPen(QColor(0, 255, 0))
        font = QFont("Consolas", size // 3)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, ">_")

        painter.end()
        return pixmap

    def _create_chain_icon(self) -> QPixmap:
        size = self.icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        painter.setBrush(QColor(180, 100, 50))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin * 2, size - margin * 2, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⛓")

        painter.end()
        return pixmap

    def _set_normal_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, "icon_frame"):
            self.icon_frame.setStyleSheet(self._icon_frame_style(hover=False))

    def _set_hover_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, "icon_frame"):
            self.icon_frame.setStyleSheet(self._icon_frame_style(hover=True))

    def _set_drop_target_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, "icon_frame"):
            self.icon_frame.setStyleSheet(self._icon_frame_style(drop=True))

    def set_selected(self, selected: bool):
        self._is_selected = bool(selected)
        if hasattr(self, "icon_frame"):
            self.icon_frame.setStyleSheet(self._icon_frame_style())

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
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        # 浅雅清新的粉绿配色系统
        if self.theme == "dark":
            bg_color = QColor(48, 79, 74, 190)
            border_color = QColor(168, 230, 207, 120)
        else:
            bg_color = QColor(225, 248, 243, 215)
            border_color = QColor(168, 230, 207, 220)

        # 模拟精致的悬浮阴影
        shadow_color = QColor(0, 0, 0, 15 if self.theme == "dark" else 10)
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(shadow_color)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 9, 9)

        # 绘制卡片背景与浅绿边框 (圆角完美契合底框的 9px)
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(1, 1, size - 3, size - 3, 9, 9)

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

            # 使用 QGraphicsOpacityEffect 在拖动过程中淡化源图标
            if grid_parent and hasattr(grid_parent, "begin_drag_visuals"):
                grid_parent.begin_drag_visuals(drag_ids)
            else:
                self._drag_opacity = QGraphicsOpacityEffect(self)
                self._drag_opacity.setOpacity(0.4)
                self.setGraphicsEffect(self._drag_opacity)

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
                pass

            # Notify parent grid that drag has ended
            parent = self.parent()
            while parent:
                if hasattr(parent, "handle_drag_ended"):
                    parent.handle_drag_ended()
                    break
                parent = parent.parent()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-shortcut-id"):
            event.acceptProposedAction()
            self._is_drop_target = True
            self._set_drop_target_style()

            # Trigger real-time swap
            source_id = event.mimeData().data("application/x-shortcut-id").data().decode()
            target_id = self.shortcut.id
            pointer_pos = None
            try:
                local_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                pointer_pos = self.mapToGlobal(local_pos)
            except Exception:
                pass

            parent = self.parent()
            while parent:
                if hasattr(parent, "handle_realtime_swap"):
                    parent.handle_realtime_swap(source_id, target_id, pointer_pos=pointer_pos)
                    break
                parent = parent.parent()

    def dragLeaveEvent(self, event):
        self._is_drop_target = False
        self._set_normal_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        try:
            self._is_drop_target = False
            self._set_normal_style()

            if event.mimeData().hasFormat("application/x-shortcut-id"):
                parent = self.parent()
                while parent:
                    if hasattr(parent, "handle_final_reorder"):
                        parent.handle_final_reorder()
                        break
                    parent = parent.parent()

                event.acceptProposedAction()
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"放置失败: {e}")


class IconGrid(QWidget):
    """图标网格"""

    shortcut_edit_requested = pyqtSignal(ShortcutItem)
    shortcut_delete_requested = pyqtSignal(ShortcutItem)
    shortcut_added = pyqtSignal()  # 新增：拖放添加图标后发送
    add_file_requested = pyqtSignal()
    add_hotkey_requested = pyqtSignal()
    add_url_requested = pyqtSignal()
    add_command_requested = pyqtSignal()
    add_chain_requested = pyqtSignal()

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data_manager = data_manager
        self.current_folder_id = None
        self.icon_widgets = []
        self.selected_shortcut_ids = set()
        self._last_selected_index = -1
        self._batch_undo_snapshot = None
        self._icon_size = 24
        self._cell_size = self._icon_size + 8 + 8  # icon_frame = icon+8, widget padding
        self._icon_load_generation = 0

        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 使用堆叠容器来叠加显示提示和图标网格
        from qt_compat import QStackedLayout, Qt  # noqa: F811

        # 滚动区域容器
        scroll_container = QWidget()
        scroll_container_layout = QVBoxLayout(scroll_container)
        scroll_container_layout.setContentsMargins(0, 0, 0, 8)
        scroll_container_layout.setSpacing(0)

        # 滚动区域
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        # 隐藏垂直滚动条，但仍可通过鼠标滚轮滚动
        scroll.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        scroll.setViewportMargins(0, 0, 0, 12)

        # 图标容器 - 使用手动定位
        self.container = IconContainer()
        self.container.setStyleSheet("background: transparent;")
        self.container.context_menu_requested.connect(self._show_grid_context_menu)
        self.container.blank_clicked.connect(self._clear_selection)
        scroll.setWidget(self.container)

        scroll_container_layout.addWidget(scroll, 1)

        # 提示标签 - 独立的居中容器
        self.hint_container = QWidget()
        self.hint_container.setStyleSheet("background: transparent;")
        if hasattr(Qt, "WidgetAttribute"):
            self.hint_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.hint_container.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hint_layout = QVBoxLayout(self.hint_container)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(0)

        # 添加弹性空间使标签垂直居中
        hint_layout.addStretch(1)

        self.hint_label = QLabel(tr("拖拽文件到此处添加\n或点击下方按钮新建\n\n拖拽图标可调整顺序"))
        self.hint_label.setAlignment(QtCompat.AlignCenter)
        self.hint_label.setStyleSheet("color: #8e8e93; font-size: 13px; line-height: 1.6;")
        from qt_compat import Qt

        if hasattr(Qt, "WidgetAttribute"):
            self.hint_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.hint_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hint_layout.addWidget(self.hint_label, 0, QtCompat.AlignCenter)

        hint_layout.addStretch(1)

        # 将提示容器和滚动区域用堆叠布局叠加
        stacked_widget = QWidget()
        stacked_widget.setObjectName("iconGridArea")
        stacked_layout = QStackedLayout(stacked_widget)
        stacked_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        # 先添加提示容器（在下层）
        stacked_layout.addWidget(self.hint_container)
        # 再添加滚动区域容器（在上层）
        stacked_layout.addWidget(scroll_container)

        self.grid_area = stacked_widget
        main_layout.addWidget(stacked_widget, 1)

        # 下方按钮区域 - 1U=16px，胶囊圆角
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 5, 0, 0)
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(QtCompat.AlignHCenter)

        self.add_file_btn = QPushButton(tr("快捷方式"))
        self.add_file_btn.setFixedHeight(36)
        self.add_file_btn.clicked.connect(self.add_file_requested.emit)
        btn_layout.addWidget(self.add_file_btn, 1)

        self.add_hotkey_btn = QPushButton(tr("快捷键"))
        self.add_hotkey_btn.setFixedHeight(36)
        self.add_hotkey_btn.clicked.connect(self.add_hotkey_requested.emit)
        btn_layout.addWidget(self.add_hotkey_btn, 1)

        self.add_url_btn = QPushButton(tr("打开网址"))
        self.add_url_btn.setFixedHeight(36)
        self.add_url_btn.clicked.connect(self.add_url_requested.emit)
        btn_layout.addWidget(self.add_url_btn, 1)

        self.add_command_btn = QPushButton(tr("运行命令"))
        self.add_command_btn.setFixedHeight(36)
        self.add_command_btn.clicked.connect(self.add_command_requested.emit)
        btn_layout.addWidget(self.add_command_btn, 1)

        main_layout.addWidget(btn_container)

        # 初始应用主题
        try:
            theme = self.data_manager.get_settings().theme
            self.apply_theme(theme)
        except Exception:
            pass

    def apply_theme(self, theme: str):
        """应用主题样式"""
        self.retranslate_ui()
        if theme == "dark":
            btn_bg = "rgba(255, 255, 255, 0.18)"
            btn_border = "rgba(255, 255, 255, 0.22)"
            btn_hover = "rgba(255, 255, 255, 0.28)"
            grid_bg = "rgba(255, 255, 255, 0.06)"
            grid_border = "rgba(255, 255, 255, 0.10)"
        else:
            btn_bg = "rgba(255, 255, 255, 0.75)"
            btn_border = "rgba(255, 255, 255, 0.35)"
            btn_hover = "rgba(255, 255, 255, 0.95)"
            grid_bg = "rgba(255, 255, 255, 0.20)"
            grid_border = "rgba(0, 0, 0, 0.06)"

        self.grid_area.setStyleSheet(f"""
            QWidget#iconGridArea {{
                background-color: {grid_bg};
                border: 1px solid {grid_border};
                border-radius: 10px;
            }}
        """)

        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_hover = "rgba(255,255,255,0.28)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_text = "rgba(255,255,255,0.85)"
            shadow_color = QColor(0, 0, 0, 35)
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_hover = "rgba(255,255,255,0.95)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_text = "#1D1D1F"
            shadow_color = QColor(0, 0, 0, 20)

        btn_style = f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 10px;
                padding: 4px 13px;
                color: {btn_text};
                font-size: 11px;
                font-weight: 400;
            }}
            QPushButton:hover {{ background-color: {btn_hover}; }}
            QPushButton:pressed {{ background-color: {btn_bg}; opacity: 0.8; }}
            QPushButton:disabled {{ background-color: rgba(255,255,255,0.3); color: #C7C7CC; }}
        """

        self.add_file_btn.setStyleSheet(btn_style)
        self.add_hotkey_btn.setStyleSheet(btn_style)
        self.add_url_btn.setStyleSheet(btn_style)
        self.add_command_btn.setStyleSheet(btn_style)

        action_buttons = (
            (self.add_file_btn, "file"),
            (self.add_hotkey_btn, "hotkey"),
            (self.add_url_btn, "url"),
            (self.add_command_btn, "command"),
        )
        for btn, kind in action_buttons:
            btn.setIcon(create_action_button_icon(kind, theme, 18))
            btn.setIconSize(QSize(18, 18))
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setOffset(0, 2)
            shadow.setColor(shadow_color)
            btn.setGraphicsEffect(shadow)

        self.hint_label.setStyleSheet(
            f"color: {theme == 'dark' and '#8e8e93' or '#8e8e93'}; font-size: 13px; line-height: 1.6;"
        )

    def retranslate_ui(self):
        if hasattr(self, "hint_label"):
            self.hint_label.setText(tr("拖拽文件到此处添加\n或点击下方按钮新建\n\n拖拽图标可调整顺序"))
        labels = (
            ("add_file_btn", "快捷方式"),
            ("add_hotkey_btn", "快捷键"),
            ("add_url_btn", "打开网址"),
            ("add_command_btn", "运行命令"),
        )
        for attr, text in labels:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setText(tr(text))

    def _get_menu_stylesheet(self) -> str:
        """获取右键菜单样式 — 半透明背景配合模糊效果"""
        # 向上查找 ConfigWindow 获取主题
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, "data_manager"):
                theme = parent.data_manager.get_settings().theme
                break
            parent = parent.parent()

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
                    color: rgba(255, 255, 255, 0.85);
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

    def _get_cell_size(self):
        # 分栏框宽度减去左右各10px边距，除以6列
        w = self.grid_area.width()
        if w <= 0:
            w = 400
        return (w - 20) // 6

    def _place_icons(self, animate=False):
        """手动定位所有图标 widget，支持平滑动画过渡"""
        if not self.icon_widgets:
            return
        live_widgets = self._live_icon_widgets(self.icon_widgets)
        if len(live_widgets) != len(self.icon_widgets):
            self.icon_widgets = live_widgets
        cell = self._get_cell_size()
        pad_x = 10
        pad_top = 14
        for i, widget in enumerate(self.icon_widgets):
            col = i % 6
            row = i // 6
            x = pad_x + col * cell
            y = pad_top + row * cell
            target_rect = QRect(x, y, cell, cell)

            # 为了防止多次触发动画产生抖动，我们需要检查 widget 现有的动画
            if animate and widget.geometry() != target_rect:
                # 检查该 widget 是否已经在向目标位置运动
                if hasattr(widget, "_pos_anim") and widget._pos_anim is not None:
                    # 如果目标未改变，则继续执行
                    if widget._pos_anim.endValue() == target_rect:
                        continue
                    # 否则，停止旧动画，开启新动画
                    widget._pos_anim.stop()

                anim = QPropertyAnimation(widget, b"geometry")
                anim.setDuration(180)  # 180ms 快速且灵动的过渡
                anim.setStartValue(widget.geometry())
                anim.setEndValue(target_rect)
                anim.setEasingCurve(QEasingCurve.OutCubic)  # 优雅的减速贝塞尔曲线
                widget._pos_anim = anim
                anim.start()
            else:
                # 停止并清除任何正在运行的动画
                if hasattr(widget, "_pos_anim") and widget._pos_anim is not None:
                    widget._pos_anim.stop()
                    widget._pos_anim = None
                widget.setGeometry(target_rect)

        rows = (len(self.icon_widgets) + 5) // 6
        self.container.setMinimumHeight(pad_top + rows * cell + pad_x)

    def load_folder(self, folder_id: str):
        """加载文件夹内容"""
        self.current_folder_id = folder_id
        self.selected_shortcut_ids.clear()
        self._last_selected_index = -1
        self._clear_icons()

        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder:
            return

        sort_mode = getattr(self.data_manager.get_settings(), "sort_mode", "custom")
        if getattr(folder, "is_icon_repo", False):
            items = list(folder.items)
        elif sort_mode == "smart":
            items = sorted(
                folder.items,
                key=lambda x: (
                    getattr(x, "smart_order", None) is None,
                    int(
                        getattr(x, "smart_order", 0)
                        if getattr(x, "smart_order", None) is not None
                        else getattr(x, "order", 0) or 0
                    ),
                    int(getattr(x, "order", 0) or 0),
                ),
            )
        else:
            items = sorted(folder.items, key=lambda x: x.order)

        if not items:
            self.hint_container.show()
            return

        self.hint_container.hide()

        cell_size = self._get_cell_size()
        icon_size = 26  # 固定图标大小
        theme = "dark"
        try:
            theme = self.data_manager.get_settings().theme
        except Exception:
            pass
        icon_tasks = []
        for i, shortcut in enumerate(items):
            widget = IconWidget(shortcut, icon_size=icon_size, cell_size=cell_size, theme=theme)
            widget.setParent(self.container)
            widget.clicked.connect(lambda s=shortcut: self._on_item_clicked(s))
            widget.double_clicked.connect(lambda s=shortcut: self._emit_edit_if_allowed(s))
            widget.context_menu_requested.connect(lambda pos, s=shortcut: self._show_context_menu(pos, s))
            widget.drag_started.connect(self._on_drag_started)
            widget.show()

            self.icon_widgets.append(widget)

            if shortcut.type not in (ShortcutType.HOTKEY, ShortcutType.URL, ShortcutType.COMMAND):
                icon_tasks.append((shortcut.id, shortcut.icon_path, shortcut.target_path, icon_size, shortcut.type))
            elif shortcut.icon_path:
                icon_tasks.append((shortcut.id, shortcut.icon_path, None, icon_size, shortcut.type))

        self._place_icons()

        # 建立 id -> shortcut 映射，用于反转判断
        self._shortcut_map = {s.id: s for s in items}

        # 启动异步图标加载
        if icon_tasks:
            self._start_async_icon_load(icon_tasks)

    def _clear_icons(self):
        self._icon_load_generation = getattr(self, "_icon_load_generation", 0) + 1
        self._stop_icon_thread()

        widgets_to_clear = []
        seen = set()
        for source in (
            self.icon_widgets,
            vars(self).get("_initial_widgets", []) or [],
            vars(self).get("_drag_visual_widgets", []) or [],
        ):
            for widget in source:
                if id(widget) in seen:
                    continue
                seen.add(id(widget))
                widgets_to_clear.append(widget)

        for widget in widgets_to_clear:
            try:
                pos_anim = getattr(widget, "_pos_anim", None)
                if pos_anim is not None:
                    pos_anim.stop()
                    widget._pos_anim = None
                widget.deleteLater()
            except RuntimeError:
                pass
        self.icon_widgets.clear()
        self._initial_widgets = []
        self._drag_visual_widgets = []
        self._active_drag_ids = []
        self.hint_container.show()
        self._shortcut_map = {}

    @staticmethod
    def _is_system_icon_repo_item(shortcut: ShortcutItem | None) -> bool:
        return getattr(shortcut, "_icon_repo_source", "") == "system"

    def _filter_mutable_shortcut_ids(self, ids) -> list[str]:
        shortcut_map = vars(self).get("_shortcut_map", {}) or {}
        result = []
        for sid in ids or []:
            if self._is_system_icon_repo_item(shortcut_map.get(sid)):
                continue
            result.append(sid)
        return result

    def _emit_edit_if_allowed(self, shortcut: ShortcutItem):
        if self._is_system_icon_repo_item(shortcut):
            return
        self.shortcut_edit_requested.emit(shortcut)

    def _stop_icon_thread(self):
        worker = getattr(self, "_icon_worker", None)
        if worker is not None:
            try:
                worker.cancel()
            except RuntimeError:
                pass
            except Exception:
                pass

        thread = getattr(self, "_icon_thread", None)
        if thread is not None:
            try:
                thread.quit()
                thread.wait(2000)
            except RuntimeError:
                pass
            self._icon_thread = None
            self._icon_worker = None

    def _start_async_icon_load(self, tasks):
        """启动后台线程加载图标"""
        self._stop_icon_thread()
        self._icon_load_generation = getattr(self, "_icon_load_generation", 0) + 1
        generation = self._icon_load_generation
        self._icon_worker = _IconLoadWorker(tasks)
        self._icon_thread = QThread()
        self._icon_worker.moveToThread(self._icon_thread)
        self._icon_worker.finished.connect(lambda sid, image, gen=generation: self._on_icon_loaded(gen, sid, image))
        self._icon_thread.started.connect(self._icon_worker.run)
        self._icon_thread.start()

    def _on_icon_loaded(self, *args):
        if len(args) == 3:
            generation, shortcut_id, image = args
            if generation != getattr(self, "_icon_load_generation", generation):
                return
        elif len(args) == 2:
            shortcut_id, image = args
        else:
            return

        shortcut_map = getattr(self, "_shortcut_map", {})
        item = shortcut_map.get(shortcut_id)
        if image.isNull() and item:
            logger.debug(
                "[IconDiag] grid worker returned null, retrying on main thread sid=%s name=%r icon_path=%r target_path=%r",
                shortcut_id,
                getattr(item, "name", ""),
                getattr(item, "icon_path", ""),
                getattr(item, "target_path", ""),
            )
            image = self._load_icon_on_main_thread(item)
        if image.isNull():
            if item:
                logger.debug(
                    "[IconDiag] grid icon still null sid=%s name=%r icon_path=%r target_path=%r",
                    shortcut_id,
                    getattr(item, "name", ""),
                    getattr(item, "icon_path", ""),
                    getattr(item, "target_path", ""),
                )
            return

        # 检查是否需要反转
        shortcut_map = getattr(self, "_shortcut_map", {})
        item = shortcut_map.get(shortcut_id)
        if item:
            try:
                from core.icon_extractor import IconExtractor, should_invert_icon

                theme = "dark"
                try:
                    theme = self.data_manager.get_settings().theme
                except Exception:
                    pass
                if should_invert_icon(item, theme):
                    image = IconExtractor.invert_image(image)
            except Exception:
                pass

        pixmap = QPixmap.fromImage(image)
        for w in list(self.icon_widgets):
            try:
                if w.shortcut.id == shortcut_id:
                    w.icon_label.setPixmap(pixmap)
                    break
            except RuntimeError:
                continue

    def _load_icon_on_main_thread(self, item: ShortcutItem):
        try:
            from core.icon_extractor import IconExtractor

            size = 26
            for widget in self.icon_widgets:
                if widget.shortcut.id == item.id:
                    size = widget.icon_size
                    break

            pixmap = None
            if item.icon_path:
                pixmap = IconExtractor.from_file(item.icon_path, size, return_image=False)
            elif item.target_path:
                pixmap = IconExtractor.extract(
                    item.target_path,
                    item.target_path,
                    size,
                    return_image=False,
                    fallback_to_default=False,
                )

            if pixmap and not pixmap.isNull():
                return pixmap.toImage()
        except Exception:
            logger.debug(
                "[IconDiag] grid main-thread retry exception name=%r icon_path=%r target_path=%r",
                getattr(item, "name", ""),
                getattr(item, "icon_path", ""),
                getattr(item, "target_path", ""),
                exc_info=True,
            )
        return QImage()

    def _on_item_clicked(self, shortcut: ShortcutItem):
        modifiers = QApplication.keyboardModifiers()
        ids = [widget.shortcut.id for widget in self.icon_widgets]
        current_index = ids.index(shortcut.id) if shortcut.id in ids else -1
        if modifiers & QtCompat.ShiftModifier and self._last_selected_index >= 0 and current_index >= 0:
            start = min(self._last_selected_index, current_index)
            end = max(self._last_selected_index, current_index)
            self.selected_shortcut_ids.update(ids[start : end + 1])
        elif modifiers & QtCompat.ControlModifier:
            if shortcut.id in self.selected_shortcut_ids:
                self.selected_shortcut_ids.remove(shortcut.id)
            else:
                self.selected_shortcut_ids.add(shortcut.id)
            self._last_selected_index = current_index
        else:
            self.selected_shortcut_ids = {shortcut.id}
            self._last_selected_index = current_index
        self._refresh_selection_styles()

    def _refresh_selection_styles(self):
        for widget in self.icon_widgets:
            widget.set_selected(widget.shortcut.id in self.selected_shortcut_ids)

    def _clear_selection(self):
        if not self.selected_shortcut_ids:
            return
        self.selected_shortcut_ids.clear()
        self._last_selected_index = -1
        self._refresh_selection_styles()

    def _selected_ids_for(self, shortcut: ShortcutItem | None = None):
        if shortcut and shortcut.id not in self.selected_shortcut_ids:
            return [shortcut.id]
        return list(self.selected_shortcut_ids)

    def _take_batch_snapshot(self):
        try:
            self._batch_undo_snapshot = copy.deepcopy(self.data_manager.data.to_dict())
        except Exception:
            self._batch_undo_snapshot = None

    def _restore_batch_snapshot(self):
        if not self._batch_undo_snapshot:
            return
        try:
            self.data_manager.data = AppData.from_dict(copy.deepcopy(self._batch_undo_snapshot))
            self.data_manager.save(immediate=True)
            self.load_folder(self.current_folder_id)
            self.shortcut_added.emit()
        except Exception as e:
            logger.error("撤销批量操作失败: %s", e, exc_info=True)

    def _confirm_batch(self, title: str, count: int) -> bool:
        return (
            ThemedMessageBox.question(
                self,
                tr(title),
                tr("确定要对 {count} 个快捷方式执行此操作吗？", count=count),
            )
            == ThemedMessageBox.Yes
        )

    def _batch_delete(self, ids):
        ids = self._filter_mutable_shortcut_ids(ids)
        if not ids or not self._confirm_batch("批量删除", len(ids)):
            return
        self._take_batch_snapshot()
        self.data_manager.delete_shortcuts_batch(ids)
        self.load_folder(self.current_folder_id)
        self.shortcut_added.emit()

    def _batch_set_enabled(self, ids, enabled: bool):
        ids = self._filter_mutable_shortcut_ids(ids)
        if not ids:
            return
        self._take_batch_snapshot()
        self.data_manager.set_shortcuts_enabled_batch(ids, enabled)
        self.load_folder(self.current_folder_id)
        self.shortcut_added.emit()

    def _batch_move(self, ids):
        if not ids:
            return
        folders = [f for f in self.data_manager.data.folders if not f.is_dock and f.id != self.current_folder_id]
        if not folders:
            return
        dialog = MoveFolderDialog(folders, self)
        if dialog.exec_() != dialog.Accepted or not dialog.selected_folder:
            return
        target = dialog.selected_folder
        self._take_batch_snapshot()
        current_folder = self.data_manager.data.get_folder_by_id(self.current_folder_id)
        if getattr(current_folder, "is_icon_repo", False) or getattr(target, "is_icon_repo", False):
            self.data_manager.copy_shortcuts_batch(ids, target.id)
        else:
            self.data_manager.move_shortcuts_batch(ids, target.id)
        self.load_folder(self.current_folder_id)
        self.shortcut_added.emit()

    def _show_context_menu(self, pos: QPoint, shortcut: ShortcutItem):
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, "data_manager"):
                theme = parent.data_manager.get_settings().theme
                break
            parent = parent.parent()

        ids = self._selected_ids_for(shortcut)
        multi = len(ids) > 1
        mutable_ids = self._filter_mutable_shortcut_ids(ids)
        system_item = self._is_system_icon_repo_item(shortcut)
        menu = PopupMenu(theme=theme, radius=12, parent=None)
        menu.add_action("编辑", lambda: self._emit_edit_if_allowed(shortcut), enabled=not multi and not system_item)
        menu.add_separator()
        menu.add_action(
            "启用所选", lambda ids=mutable_ids: self._batch_set_enabled(ids, True), enabled=bool(mutable_ids)
        )
        menu.add_action(
            "禁用所选", lambda ids=mutable_ids: self._batch_set_enabled(ids, False), enabled=bool(mutable_ids)
        )
        menu.add_action("移动所选到...", lambda ids=ids: self._batch_move(ids), enabled=bool(ids))
        menu.add_separator()
        if multi:
            menu.add_action(tr("删除所选"), lambda ids=mutable_ids: self._batch_delete(ids), enabled=bool(mutable_ids))
        else:
            menu.add_action(tr("删除"), lambda: self.shortcut_delete_requested.emit(shortcut), enabled=not system_item)
        if self._batch_undo_snapshot:
            menu.add_separator()
            menu.add_action(tr("撤销上次批量操作"), self._restore_batch_snapshot, enabled=True)
        menu.popup(pos)

    def _show_grid_context_menu(self, pos: QPoint):
        """显示空白区域右键菜单"""
        if not self.current_folder_id:
            return

        theme = "dark"
        try:
            theme = self.data_manager.get_settings().theme
        except Exception:
            pass

        menu = PopupMenu(theme=theme, radius=12, parent=None)
        menu.add_action(tr("快捷方式"), lambda: self.add_file_requested.emit(), enabled=True)
        menu.add_action(tr("快捷键"), lambda: self.add_hotkey_requested.emit(), enabled=True)
        menu.add_action(tr("打开网址"), lambda: self.add_url_requested.emit(), enabled=True)
        menu.add_action(tr("运行命令"), lambda: self.add_command_requested.emit(), enabled=True)
        menu.add_action(tr("新建动作链"), lambda: self.add_chain_requested.emit(), enabled=True)
        if self._batch_undo_snapshot:
            menu.add_separator()
            menu.add_action(tr("撤销上次批量操作"), self._restore_batch_snapshot, enabled=True)
        menu.popup(pos)

    def _apply_menu_mask(self, menu: QMenu):
        try:
            radius = 10
            try:
                menu.adjustSize()
            except Exception:
                pass
            path = QPainterPath()
            rect = menu.rect()
            path.addRoundedRect(rect, radius, radius)
            menu.setMask(QRegion(path.toFillPolygon().toPolygon()))
        except Exception:
            pass

    @staticmethod
    def _widget_shortcut_id(widget) -> str | None:
        try:
            shortcut = getattr(widget, "shortcut", None)
            return getattr(shortcut, "id", None)
        except RuntimeError:
            return None

    def _live_icon_widgets(self, widgets=None):
        return [widget for widget in (widgets or []) if self._widget_shortcut_id(widget)]

    def get_drag_shortcut_ids(self, source_id: str) -> list[str]:
        """Return the shortcut ids that should move with this drag."""
        if source_id in self.selected_shortcut_ids:
            selected = set(self.selected_shortcut_ids)
            ids = []
            for widget in self.icon_widgets:
                sid = self._widget_shortcut_id(widget)
                if sid in selected:
                    ids.append(sid)
            return ids or [source_id]
        return [source_id]

    def create_drag_preview_pixmap(self, shortcut_ids: list[str], source_widget: IconWidget) -> QPixmap:
        shortcut_id_set = set(shortcut_ids or [])
        widgets = [w for w in self.icon_widgets if self._widget_shortcut_id(w) in shortcut_id_set]
        if len(widgets) <= 1:
            return source_widget.create_drag_preview_pixmap()

        base = source_widget.create_drag_preview_pixmap()
        if not base or base.isNull():
            return base

        visible_count = min(len(widgets), 4)
        offset = 7
        badge_size = 18
        width = base.width() + offset * (visible_count - 1) + badge_size // 2
        height = base.height() + offset * (visible_count - 1) + badge_size // 2
        pixmap = QPixmap(width, height)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        for i in range(visible_count - 1, -1, -1):
            painter.setOpacity(0.72 if i else 0.95)
            painter.drawPixmap(i * offset, i * offset, base)

        painter.setOpacity(1.0)
        badge_x = width - badge_size - 1
        badge_y = 1
        painter.setPen(QtCompat.NoPen)
        painter.setBrush(QColor(0, 122, 255, 230))
        painter.drawEllipse(badge_x, badge_y, badge_size, badge_size)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(badge_x, badge_y, badge_size, badge_size), QtCompat.AlignCenter, str(len(widgets)))
        painter.end()
        return pixmap

    def begin_drag_visuals(self, shortcut_ids: list[str]):
        self._active_drag_ids = list(shortcut_ids or [])
        self._drag_visual_widgets = []
        active_ids = set(self._active_drag_ids)
        for widget in self.icon_widgets:
            try:
                if self._widget_shortcut_id(widget) not in active_ids:
                    continue
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(0.4)
                widget.setGraphicsEffect(effect)
                self._drag_visual_widgets.append(widget)
            except RuntimeError:
                pass

    def end_drag_visuals(self):
        for widget in vars(self).get("_drag_visual_widgets", []) or []:
            try:
                widget.setVisible(True)
                widget.setGraphicsEffect(None)
                widget._set_normal_style()
            except RuntimeError:
                pass
        self._drag_visual_widgets = []
        self._active_drag_ids = []

    def _on_drag_started(self, source_id):
        self._initial_widgets = self._live_icon_widgets(self.icon_widgets)
        self._drag_completed = False
        self._last_realtime_swap_target_id = None
        self._last_realtime_swap_global_pos = None
        self._last_realtime_swap_at = 0.0

    def handle_realtime_swap(
        self,
        source_id: str,
        target_id: str,
        drag_ids: list[str] | None = None,
        pointer_pos: QPoint | None = None,
    ):
        if source_id == target_id:
            return
        if getattr(self.data_manager.get_settings(), "sort_mode", "custom") == "smart":
            return

        moving_ids = drag_ids or vars(self).get("_active_drag_ids") or [source_id]
        shortcut_map = vars(self).get("_shortcut_map", {}) or {}
        if vars(self).get("current_folder_id") == "icon_repo":
            if any(self._is_system_icon_repo_item(shortcut_map.get(sid)) for sid in moving_ids):
                return
            if self._is_system_icon_repo_item(shortcut_map.get(target_id)):
                return
            # 用户图标不能拖到系统图标前面
            is_user_icon_moving = any(not self._is_system_icon_repo_item(shortcut_map.get(sid)) for sid in moving_ids)
            if is_user_icon_moving:
                target_idx = next(
                    (i for i, w in enumerate(self.icon_widgets) if self._widget_shortcut_id(w) == target_id), -1
                )
                if target_idx >= 0:
                    for i in range(target_idx + 1, len(self.icon_widgets)):
                        if self._is_system_icon_repo_item(
                            shortcut_map.get(self._widget_shortcut_id(self.icon_widgets[i]))
                        ):
                            return
        try:
            current_ids = {self._widget_shortcut_id(w) for w in self.icon_widgets}
            current_ids.discard(None)
        except RuntimeError:
            current_ids = set()
        if any(sid not in current_ids for sid in moving_ids):
            self._restore_drag_preview_order(animate=False)

        if self._should_suppress_realtime_swap(target_id, pointer_pos):
            return

        if self._move_drag_group(source_id, target_id, moving_ids):
            self._record_realtime_swap(target_id, pointer_pos)
            self._place_icons(animate=True)

    def _should_suppress_realtime_swap(self, target_id: str, pointer_pos: QPoint | None) -> bool:
        state = vars(self)
        last_target_id = state.get("_last_realtime_swap_target_id")
        last_pos = state.get("_last_realtime_swap_global_pos")
        last_at = float(state.get("_last_realtime_swap_at", 0.0) or 0.0)

        if not last_target_id or pointer_pos is None or last_pos is None:
            return False

        elapsed_ms = (time.monotonic() - last_at) * 1000.0
        if elapsed_ms > 260:
            return False

        try:
            moved_px = (pointer_pos - last_pos).manhattanLength()
        except Exception:
            return False

        return moved_px < max(16, int(self._get_cell_size() * 0.45))

    def _record_realtime_swap(self, target_id: str, pointer_pos: QPoint | None):
        self._last_realtime_swap_target_id = target_id
        self._last_realtime_swap_global_pos = QPoint(pointer_pos) if pointer_pos is not None else None
        self._last_realtime_swap_at = time.monotonic()

    def _move_drag_group(self, source_id: str, target_id: str, drag_ids: list[str]) -> bool:
        self.icon_widgets = self._live_icon_widgets(self.icon_widgets)
        id_to_index = {}
        for i, widget in enumerate(self.icon_widgets):
            sid = self._widget_shortcut_id(widget)
            if sid:
                id_to_index[sid] = i
        if target_id not in id_to_index:
            return False

        ordered_ids = []
        seen = set()
        for widget in self.icon_widgets:
            sid = self._widget_shortcut_id(widget)
            if sid in drag_ids and sid not in seen:
                ordered_ids.append(sid)
                seen.add(sid)
        if not ordered_ids or target_id in seen:
            return False

        source_idx = id_to_index.get(source_id, id_to_index[ordered_ids[0]])
        target_idx = id_to_index[target_id]
        moving_set = set(ordered_ids)
        moving_widgets = [w for w in self.icon_widgets if self._widget_shortcut_id(w) in moving_set]
        remaining_widgets = [w for w in self.icon_widgets if self._widget_shortcut_id(w) not in moving_set]
        target_pos = next((i for i, w in enumerate(remaining_widgets) if self._widget_shortcut_id(w) == target_id), -1)
        if target_pos < 0:
            return False

        insert_at = target_pos + 1 if source_idx < target_idx else target_pos
        new_widgets = remaining_widgets[:insert_at] + moving_widgets + remaining_widgets[insert_at:]
        new_ids = [self._widget_shortcut_id(w) for w in new_widgets]
        current_ids = [self._widget_shortcut_id(w) for w in self.icon_widgets]
        if new_ids == current_ids:
            return False
        self.icon_widgets = new_widgets
        return True

    def handle_final_reorder(self):
        self._drag_completed = True
        if not self.current_folder_id:
            return
        shortcut_ids = [w.shortcut.id for w in self.icon_widgets]
        self.data_manager.reorder_shortcuts(self.current_folder_id, shortcut_ids)

        # 直接发送信号通知外部弹窗刷新，而无需销毁重建当前所有卡片及重新加载图标（彻底消除闪烁！）
        self.shortcut_added.emit()

    def handle_drag_ended(self):
        # 如果拖放未完成即松手（取消拖拽），将所有卡片恢复到初始的排序 and 位置
        if not vars(self).get("_drag_completed", False):
            self._restore_drag_preview_order(animate=True)
        self._drag_completed = False

    def _active_drag_id_set(self) -> set[str]:
        return set(vars(self).get("_active_drag_ids", []) or [])

    def _set_active_drag_widgets_visible(self, visible: bool):
        active_ids = self._active_drag_id_set()
        if not active_ids:
            return
        for widget in vars(self).get("_initial_widgets", []) or []:
            try:
                if self._widget_shortcut_id(widget) in active_ids:
                    widget.setVisible(visible)
            except RuntimeError:
                continue

    def _restore_drag_preview_order(self, animate: bool = True):
        initial_widgets = self._live_icon_widgets(vars(self).get("_initial_widgets") or [])
        if not initial_widgets:
            return

        self._set_active_drag_widgets_visible(True)
        try:
            current_ids = [self._widget_shortcut_id(w) for w in self.icon_widgets]
            initial_ids = [self._widget_shortcut_id(w) for w in initial_widgets]
        except RuntimeError:
            return

        if current_ids == initial_ids:
            return

        self.icon_widgets = list(initial_widgets)
        self._place_icons(animate=animate)

    def _remove_active_drag_placeholders(self, animate: bool = True):
        initial_widgets = self._live_icon_widgets(vars(self).get("_initial_widgets") or [])
        active_ids = self._active_drag_id_set()
        if not initial_widgets or not active_ids:
            return

        try:
            remaining_widgets = [w for w in initial_widgets if self._widget_shortcut_id(w) not in active_ids]
            current_ids = [self._widget_shortcut_id(w) for w in self.icon_widgets]
            remaining_ids = [self._widget_shortcut_id(w) for w in remaining_widgets]
        except RuntimeError:
            return

        self._set_active_drag_widgets_visible(False)
        if current_ids == remaining_ids:
            return

        self.icon_widgets = remaining_widgets
        self._place_icons(animate=animate)

    def handle_reorder(self, source_id: str, target_id: str):
        self.handle_final_reorder()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.icon_widgets:
            self._place_icons()

    def dragEnterEvent(self, event):
        # 只有在有有效文件夹时才接受拖放
        if not self.current_folder_id:
            event.ignore()
            return

        # 检查是否包含支持的文件（自动过滤不支持的文件）
        has_valid_file = False
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile():
                    has_valid_file = True
                    break
        elif event.mimeData().hasFormat("application/x-shortcut-id"):
            has_valid_file = True

        if has_valid_file:
            if event.mimeData().hasFormat("application/x-shortcut-id"):
                self._restore_drag_preview_order(animate=True)
            event.acceptProposedAction()
            theme = "dark"
            try:
                theme = self.data_manager.get_settings().theme
            except Exception:
                pass

            if theme == "dark":
                bg = "rgba(168, 230, 207, 25)"
                border = "2px dashed rgba(168, 230, 207, 160)"
            else:
                bg = "rgba(224, 250, 240, 200)"
                border = "2px dashed rgba(70, 180, 140, 180)"

            self.grid_area.setStyleSheet(f"""
                QWidget#iconGridArea {{
                    background-color: {bg};
                    border: {border};
                    border-radius: 10px;
                }}
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._remove_active_drag_placeholders(animate=True)
        theme = "dark"
        try:
            theme = self.data_manager.get_settings().theme
        except Exception:
            pass
        self.apply_theme(theme)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        theme = "dark"
        try:
            theme = self.data_manager.get_settings().theme
        except Exception:
            pass
        self.apply_theme(theme)

        if not self.current_folder_id:
            event.acceptProposedAction()
            return

        # NEW: Handle internal drag drop on empty space
        if event.mimeData().hasFormat("application/x-shortcut-id"):
            self.handle_final_reorder()
            event.acceptProposedAction()
            return

        shortcuts_to_add = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    # 预先创建 shortcut 对象，但不添加
                    shortcut = self._create_shortcut_from_file(file_path)
                    if shortcut:
                        shortcuts_to_add.append(shortcut)

        if shortcuts_to_add:
            # 批量添加并保存
            self.data_manager.add_shortcuts(self.current_folder_id, shortcuts_to_add)
            # 刷新 UI
            self.load_folder(self.current_folder_id)
            # 发送信号
            self.shortcut_added.emit()

        event.acceptProposedAction()

    def _create_shortcut_from_file(self, file_path: str) -> ShortcutItem:
        """从文件路径创建快捷方式对象"""
        shortcut = ShortcutItem()
        shortcut.name = os.path.splitext(os.path.basename(file_path))[0][:6]

        if os.path.isdir(file_path):
            shortcut.type = ShortcutType.FOLDER
        else:
            shortcut.type = ShortcutType.FILE

        shortcut.target_path = file_path

        if file_path.lower().endswith(".lnk"):
            try:
                from core.shortcut_parser import ShortcutParser

                info = ShortcutParser.parse(file_path)
                shortcut.target_path = info.get("target", file_path)
                shortcut.target_args = info.get("args", "")
                shortcut.working_dir = info.get("working_dir", "")
            except Exception:
                pass
        return shortcut

    def _add_from_file(self, file_path: str):
        # 保持兼容性，用于单个文件添加
        if not self.current_folder_id:
            return

        shortcut = self._create_shortcut_from_file(file_path)
        self.data_manager.add_shortcut(self.current_folder_id, shortcut)
        self.load_folder(self.current_folder_id)
        self.shortcut_added.emit()
