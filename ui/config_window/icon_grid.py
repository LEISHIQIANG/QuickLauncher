"""
图标网格 - 设置窗口版本（四按钮横向排列）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QGridLayout, QLabel, QPushButton, QFrame, QMenu,
    QSizePolicy, Qt, QtCompat, pyqtSignal, QPoint,
    QPixmap, QDrag, QPainter, QColor, QFont, QMimeData, PYQT_VERSION,
    QPainterPath, QRegion, QPen, QRectF, QApplication,
    QThread, QObject, QImage, QTimer, QGraphicsDropShadowEffect
)

from core import DataManager, ShortcutItem, ShortcutType

# 使用统一的风格组件
from ui.styles.style import PopupMenu


class IconContainer(QWidget):
    """图标容器 - 支持空白区域右键菜单"""
    context_menu_requested = pyqtSignal(QPoint)

    def mousePressEvent(self, event):
        if event.button() == QtCompat.RightButton:
            # 检查点击位置是否在子控件上
            child = self.childAt(event.pos())
            if child is None or child == self:
                # 空白区域，显示菜单
                global_pos = self.mapToGlobal(event.pos())
                self.context_menu_requested.emit(global_pos)
                return
        super().mousePressEvent(event)


class _IconLoadWorker(QObject):
    """后台图标加载 worker（使用 QImage 保证线程安全）"""
    finished = pyqtSignal(str, QImage)  # (shortcut_id, image)

    def __init__(self, tasks):
        super().__init__()
        self._tasks = tasks

    def run(self):
        from core.icon_extractor import IconExtractor
        try:
            import ctypes
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
            
        try:
            for sid, icon_path, target_path, size, stype in self._tasks:
                
                import sys, os
                is_folder_type = stype == ShortcutType.FOLDER
                if stype == ShortcutType.FILE and target_path and os.path.isdir(target_path):
                    is_folder_type = True
                    
                if not icon_path and is_folder_type:
                    possible_paths = [
                        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'assets', 'Folder.ico'),
                        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'assets', 'Folder.ico')
                    ]
                    if hasattr(sys, '_MEIPASS'):
                        possible_paths.insert(0, os.path.join(sys._MEIPASS, 'assets', 'Folder.ico'))
                    for p in possible_paths:
                        if os.path.exists(p):
                            icon_path = p
                            target_path = None
                            break
                            
                try:
                    image = self._load_one(IconExtractor, icon_path, target_path, size)
                except Exception:
                    pass
                if image and not image.isNull():
                    self.finished.emit(sid, image)
        finally:
            try:
                import ctypes
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    @staticmethod
    def _load_one(IE, icon_path, target_path, size):
        """线程安全的单个图标加载（只用 QImage，不用 QPixmap/QIcon）"""
        # 1. icon_path 为 "path,index" 格式 → 从资源提取
        if icon_path and ',' in icon_path:
            parts = icon_path.split(',')
            if len(parts) >= 2:
                path_part = ",".join(parts[:-1]).strip()
                idx_part = parts[-1].strip()
                if idx_part.lstrip('-').isdigit():
                    r = IE._extract_from_resource(path_part, int(idx_part), size, return_image=True)
                    if r and not r.isNull():
                        return r

        # 2. icon_path 为图片文件 → QImage 直接加载
        if icon_path and os.path.exists(icon_path):
            ext = os.path.splitext(icon_path)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.ico'):
                img = QImage(icon_path)
                if not img.isNull():
                    return img.scaled(size, size, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

        # 3. shell 路径使用 PIDL 提取
        for p in (icon_path, target_path):
            if p and str(p).lower().startswith("shell:"):
                r = IE._extract_shell_pidl(p, size, return_image=True)
                if r and (not hasattr(r, 'isNull') or not r.isNull()):
                    return r

        # 4. Win32 API 提取
        for p in (icon_path, target_path):
            # 不再强求 os.path.exists 因为有的路径可能提取也能工作，但是如果是目录，ExtractIconExW 可能失败。 
            # Win32 API 包含了 SHGetFileInfoW 回退，所以对于目录、特殊路径都可能工作。
            if p and (os.path.exists(p) or os.path.isdir(p)):
                r = IE._extract_win32(p, size, return_image=True)
                if r and (not hasattr(r, 'isNull') or not r.isNull()):
                    return r
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
        self._normal_bg = self.DARK_NORMAL_BG if theme == "dark" else self.LIGHT_NORMAL_BG
        self._hover_bg = self.DARK_HOVER_BG if theme == "dark" else self.LIGHT_HOVER_BG
        self._border = (
            "1px solid rgba(255, 255, 255, 35)"
            if theme == "dark"
            else "1px solid rgba(0, 0, 0, 12)"
        )
        
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

        frame_layout = QVBoxLayout(self.icon_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setAlignment(QtCompat.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(self.icon_size, self.icon_size)
        self.icon_label.setAlignment(QtCompat.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        frame_layout.addWidget(self.icon_label)

        layout.addWidget(self.icon_frame, alignment=QtCompat.AlignCenter)

        self.name_label = QLabel(self.shortcut.name[:6] if self.shortcut.name else "未命名")
        self.name_label.setAlignment(QtCompat.AlignCenter)
        self.name_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self._load_icon()

    def _icon_frame_style(self, hover=False, drop=False):
        if drop:
            return "QFrame { background-color: rgba(0,122,255,40); border-radius: 9px; border: 1.5px solid rgba(0,122,255,180); }"
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
        painter.setBrush(QColor(100, 130, 180))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawEllipse(margin, margin, size - margin*2, size - margin*2)
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
        painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 6, 6)
        
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
        painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 6, 6)
        
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
        painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 6, 6)
        
        painter.setPen(QColor(0, 255, 0))
        font = QFont("Consolas", size // 3)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, ">_")
        
        painter.end()
        return pixmap
    
    def _set_normal_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, 'icon_frame'):
            self.icon_frame.setStyleSheet(self._icon_frame_style(hover=False))

    def _set_hover_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, 'icon_frame'):
            self.icon_frame.setStyleSheet(self._icon_frame_style(hover=True))

    def _set_drop_target_style(self):
        self.setStyleSheet("IconWidget { background: transparent; border: none; }")
        if hasattr(self, 'icon_frame'):
            self.icon_frame.setStyleSheet(self._icon_frame_style(drop=True))
    
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
            pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.context_menu_requested.emit(pos)
        
        self._drag_start_pos = None
        self._is_dragging = False
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            self.double_clicked.emit()
    
    def _start_drag(self):
        try:
            self._set_normal_style()

            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setData("application/x-shortcut-id", self.shortcut.id.encode())

            # 添加源文件夹信息
            parent = self.parent()
            while parent:
                if hasattr(parent, 'current_folder_id'):
                    mime_data.setData("application/x-source-folder-id", parent.current_folder_id.encode())
                    break
                parent = parent.parent()

            drag.setMimeData(mime_data)

            # 使用图标作为拖动预览
            if self.icon_label.pixmap() and not self.icon_label.pixmap().isNull():
                drag.setPixmap(self.icon_label.pixmap())
                drag.setHotSpot(QPoint(self.icon_size//2, self.icon_size//2))

            self.drag_started.emit(self.shortcut.id)
            drag.exec_(QtCompat.MoveAction)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"拖动失败: {e}")
        finally:
            self._is_dragging = False
            self._set_normal_style()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-shortcut-id"):
            event.acceptProposedAction()
            self._is_drop_target = True
            self._set_drop_target_style()
    
    def dragLeaveEvent(self, event):
        self._is_drop_target = False
        self._set_normal_style()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        try:
            self._is_drop_target = False
            self._set_normal_style()

            if event.mimeData().hasFormat("application/x-shortcut-id"):
                source_id = event.mimeData().data("application/x-shortcut-id").data().decode()
                target_id = self.shortcut.id

                if source_id != target_id:
                    parent = self.parent()
                    while parent:
                        if hasattr(parent, 'handle_reorder'):
                            parent.handle_reorder(source_id, target_id)
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
    builtin_icon_requested = pyqtSignal()  # 新增：内置图标请求信号

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data_manager = data_manager
        self.current_folder_id = None
        self.icon_widgets = []
        self._icon_size = 24
        self._cell_size = self._icon_size + 8 + 8  # icon_frame = icon+8, widget padding

        self._setup_ui()
        self.setAcceptDrops(True)
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # 使用堆叠容器来叠加显示提示和图标网格
        from qt_compat import QStackedLayout
        
        # 滚动区域容器
        scroll_container = QWidget()
        scroll_container_layout = QVBoxLayout(scroll_container)
        scroll_container_layout.setContentsMargins(0, 0, 0, 8)
        scroll_container_layout.setSpacing(0)
        
        # 滚动区域
        scroll = QScrollArea()
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
        scroll.setWidget(self.container)
        
        scroll_container_layout.addWidget(scroll, 1)
        
        # 提示标签 - 独立的居中容器
        self.hint_container = QWidget()
        self.hint_container.setStyleSheet("background: transparent;")
        from qt_compat import Qt
        if hasattr(Qt, 'WidgetAttribute'):
            self.hint_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.hint_container.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hint_layout = QVBoxLayout(self.hint_container)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(0)
        
        # 添加弹性空间使标签垂直居中
        hint_layout.addStretch(1)
        
        self.hint_label = QLabel("拖拽文件到此处添加\n或点击下方按钮新建\n\n拖拽图标可调整顺序")
        self.hint_label.setAlignment(QtCompat.AlignCenter)
        self.hint_label.setStyleSheet("color: #8e8e93; font-size: 13px; line-height: 1.6;")
        from qt_compat import Qt
        if hasattr(Qt, 'WidgetAttribute'):
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

        self.add_file_btn = QPushButton("📄 快捷方式")
        self.add_file_btn.setFixedHeight(36)
        self.add_file_btn.clicked.connect(self.add_file_requested.emit)
        btn_layout.addWidget(self.add_file_btn, 1)

        self.add_hotkey_btn = QPushButton("⌨ 快捷键")
        self.add_hotkey_btn.setFixedHeight(36)
        self.add_hotkey_btn.clicked.connect(self.add_hotkey_requested.emit)
        btn_layout.addWidget(self.add_hotkey_btn, 1)

        self.add_url_btn = QPushButton("🌐 打开网址")
        self.add_url_btn.setFixedHeight(36)
        self.add_url_btn.clicked.connect(self.add_url_requested.emit)
        btn_layout.addWidget(self.add_url_btn, 1)

        self.add_command_btn = QPushButton("⚡ 运行命令")
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
        if theme == "dark":
            btn_bg = "rgba(255, 255, 255, 0.18)"
            btn_border = "rgba(255, 255, 255, 0.22)"
            btn_hover = "rgba(255, 255, 255, 0.28)"
            btn_hover_text = "rgba(255, 255, 255, 0.95)"
            text_color = "rgba(255, 255, 255, 0.80)"
            grid_bg = "rgba(255, 255, 255, 0.06)"
            grid_border = "rgba(255, 255, 255, 0.10)"
        else:
            btn_bg = "rgba(255, 255, 255, 0.75)"
            btn_border = "rgba(255, 255, 255, 0.35)"
            btn_hover = "rgba(255, 255, 255, 0.95)"
            btn_hover_text = "rgba(28, 28, 30, 0.9)"
            text_color = "rgba(28, 28, 30, 0.65)"
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

        for btn in (self.add_file_btn, self.add_hotkey_btn, self.add_url_btn, self.add_command_btn):
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setOffset(0, 2)
            shadow.setColor(shadow_color)
            btn.setGraphicsEffect(shadow)
        
        self.hint_label.setStyleSheet(f"color: {theme == 'dark' and '#8e8e93' or '#8e8e93'}; font-size: 13px; line-height: 1.6;")
    
    def _get_menu_stylesheet(self) -> str:
        """获取右键菜单样式 — 半透明背景配合模糊效果"""
        # 向上查找 ConfigWindow 获取主题
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_manager'):
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

    def _place_icons(self):
        """手动定位所有图标 widget"""
        if not self.icon_widgets:
            return
        cell = self._get_cell_size()
        pad_x = 10
        pad_top = 14
        for i, widget in enumerate(self.icon_widgets):
            col = i % 6
            row = i // 6
            x = pad_x + col * cell
            y = pad_top + row * cell
            widget.setGeometry(x, y, cell, cell)

        rows = (len(self.icon_widgets) + 5) // 6
        self.container.setMinimumHeight(pad_top + rows * cell + pad_x)

    def load_folder(self, folder_id: str):
        """加载文件夹内容"""
        self.current_folder_id = folder_id
        self._clear_icons()

        folder = self.data_manager.data.get_folder_by_id(folder_id)
        if not folder:
            return

        items = sorted(folder.items, key=lambda x: x.order)

        if not items:
            self.hint_container.show()
            return

        self.hint_container.hide()

        cols = 6
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
            widget.double_clicked.connect(lambda s=shortcut: self.shortcut_edit_requested.emit(s))
            widget.context_menu_requested.connect(lambda pos, s=shortcut: self._show_context_menu(pos, s))
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
        self._stop_icon_thread()
        for widget in self.icon_widgets:
            widget.deleteLater()
        self.icon_widgets.clear()
        self.hint_container.show()

    def _stop_icon_thread(self):
        if hasattr(self, '_icon_thread') and self._icon_thread is not None:
            self._icon_thread.quit()
            self._icon_thread.wait(2000)
            self._icon_thread = None
            self._icon_worker = None

    def _start_async_icon_load(self, tasks):
        """启动后台线程加载图标"""
        self._stop_icon_thread()
        self._icon_worker = _IconLoadWorker(tasks)
        self._icon_thread = QThread()
        self._icon_worker.moveToThread(self._icon_thread)
        self._icon_worker.finished.connect(self._on_icon_loaded)
        self._icon_thread.started.connect(self._icon_worker.run)
        self._icon_thread.start()

    def _on_icon_loaded(self, shortcut_id, image):
        """异步图标加载完成回调（主线程中将 QImage 转 QPixmap）"""
        if image.isNull():
            return

        # 检查是否需要反转
        shortcut_map = getattr(self, '_shortcut_map', {})
        item = shortcut_map.get(shortcut_id)
        if item:
            try:
                from core.icon_extractor import should_invert_icon, IconExtractor
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
        for w in self.icon_widgets:
            if w.shortcut.id == shortcut_id:
                w.icon_label.setPixmap(pixmap)
                break

    def _on_item_clicked(self, shortcut: ShortcutItem):
        pass
    
    def _show_context_menu(self, pos: QPoint, shortcut: ShortcutItem):
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, 'data_manager'):
                theme = parent.data_manager.get_settings().theme
                break
            parent = parent.parent()

        menu = PopupMenu(theme=theme, radius=12, parent=None)
        menu.add_action("编辑", lambda: self.shortcut_edit_requested.emit(shortcut), enabled=True)
        menu.add_separator()
        menu.add_action("删除", lambda: self.shortcut_delete_requested.emit(shortcut), enabled=True)
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
        menu.add_action("快捷方式", lambda: self.add_file_requested.emit(), enabled=True)
        menu.add_action("快捷键", lambda: self.add_hotkey_requested.emit(), enabled=True)
        menu.add_action("打开网址", lambda: self.add_url_requested.emit(), enabled=True)
        menu.add_action("运行命令", lambda: self.add_command_requested.emit(), enabled=True)
        menu.add_separator()
        menu.add_action("内置图标", lambda: self.builtin_icon_requested.emit(), enabled=True)
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
    
    def handle_reorder(self, source_id: str, target_id: str):
        try:
            if not self.current_folder_id:
                return

            folder = self.data_manager.data.get_folder_by_id(self.current_folder_id)
            if not folder:
                return

            source_index = -1
            target_index = -1

            items = sorted(folder.items, key=lambda x: x.order)

            for i, item in enumerate(items):
                if item.id == source_id:
                    source_index = i
                if item.id == target_id:
                    target_index = i

            if source_index < 0 or target_index < 0:
                return

            item = items.pop(source_index)
            items.insert(target_index, item)

            shortcut_ids = [item.id for item in items]
            self.data_manager.reorder_shortcuts(self.current_folder_id, shortcut_ids)

            # 延迟刷新UI，避免在拖动操作未完成时删除控件导致崩溃
            folder_id = self.current_folder_id
            QTimer.singleShot(50, lambda fid=folder_id: self.load_folder(fid))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"重新排序失败: {e}")

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
            event.acceptProposedAction()
            # 圆角蓝色背景提示
            self.setStyleSheet("""
                IconGrid {
                    background-color: rgba(70, 130, 180, 30);
                    border: 2px dashed rgba(70, 130, 180, 100);
                    border-radius: 12px;
                }
            """)
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet("IconGrid { background: transparent; border: none; }")
    
    def dropEvent(self, event):
        self.setStyleSheet("IconGrid { background: transparent; border: none; }")
        
        if not self.current_folder_id:
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
        
        if file_path.lower().endswith('.lnk'):
            try:
                from core.shortcut_parser import ShortcutParser
                info = ShortcutParser.parse(file_path)
                shortcut.target_path = info.get('target', file_path)
                shortcut.target_args = info.get('args', '')
                shortcut.working_dir = info.get('working_dir', '')
            except:
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
