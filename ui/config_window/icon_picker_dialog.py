"""
图标选择对话框
"""
import os
import logging
import threading
from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QSize, QIcon, QPixmap,
    Qt, QtCompat, pyqtSignal, QPoint
)
from core.icon_extractor import IconExtractor
from ui.utils.window_effect import enable_window_shadow_and_round_corners
from ui.utils.dialog_helper import center_dialog_on_main_window
from ui.styles.style import Glassmorphism
from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)

class IconPickerDialog(BaseDialog):
    """图标选择对话框"""

    # 信号：加载进度 (current, total)
    load_progress = pyqtSignal(int, int)
    # 信号：加载完成一个图标 (index, pixmap)
    from qt_compat import QImage
    icon_loaded = pyqtSignal(int, QImage)

    def __init__(self, parent=None, file_path: str = ""):
        super().__init__(parent)
        self.file_path = file_path
        self.selected_index = -1
        self._is_loading = False
        self._stop_loading = False

        self.setWindowTitle(f"选择图标 - {os.path.basename(file_path)}")
        self.resize(600, 400)
        self.setModal(True)

        self._setup_ui()
        self._apply_theme_colors()
        self._start_loading()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 顶部信息
        info_layout = QHBoxLayout()
        self.info_label = QLabel("正在读取图标...")
        info_layout.addWidget(self.info_label)
        layout.addLayout(info_layout)
        
        # 图标列表
        self.list_widget = QListWidget()
        try:
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setMovement(QListWidget.Movement.Static)
        except:
            self.list_widget.setViewMode(QListWidget.IconMode)
            self.list_widget.setResizeMode(QListWidget.Adjust)
            self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSpacing(10)
        self.list_widget.setIconSize(QSize(48, 48))
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        self._ok_btn = ok_btn
        
        layout.addLayout(btn_layout)
        
        # 连接信号
        self.load_progress.connect(self._update_progress)
        self.icon_loaded.connect(self._add_icon_item)

        # 应用按钮样式
        self._apply_button_theme()
        
    def _apply_button_theme(self):
        """应用按钮主题样式"""
        theme = self._get_theme_from_parent()
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        self._cancel_btn.setStyleSheet(flat_btn_style)
        self._ok_btn.setStyleSheet(flat_btn_style)

    def _start_loading(self):
        """开始加载图标"""
        self._is_loading = True
        self._stop_loading = False
        
        # 预先获取图标数量
        count = IconExtractor.get_icon_count(self.file_path)
        if count == 0:
            self.info_label.setText("未找到图标")
            return
            
        self.info_label.setText(f"发现 {count} 个图标，正在加载...")
        
        # 启动加载线程
        threading.Thread(target=self._load_task, args=(count,), daemon=True).start()
        
    def _load_task(self, count):
        """加载任务"""
        try:
            for i in range(count):
                if self._stop_loading:
                    break
                    
                # 提取图标 (返回 QImage 以便在线程中使用)
                image = IconExtractor.from_file(f"{self.file_path},{i}", 48, return_image=True)
                if image and not image.isNull():
                    self.icon_loaded.emit(i, image)
                
                if i % 10 == 0:
                    self.load_progress.emit(i + 1, count)
                    
            self.load_progress.emit(count, count)
            
        except Exception as e:
            logger.error(f"加载图标失败: {e}")
            
    def _update_progress(self, current, total):
        """更新进度"""
        self.info_label.setText(f"已加载 {current}/{total} 个图标")
        
    def _add_icon_item(self, index, image):
        """添加图标项"""
        pixmap = QPixmap.fromImage(image)
        item = QListWidgetItem(QIcon(pixmap), str(index))
        item.setData(QtCompat.UserRole, index)
        self.list_widget.addItem(item)

    def _on_item_double_clicked(self, item):
        """双击选择"""
        self.selected_index = item.data(QtCompat.UserRole)
        self.accept()
        
    def _on_ok(self):
        """点击确定"""
        items = self.list_widget.selectedItems()
        if items:
            self.selected_index = items[0].data(Qt.UserRole)
            self.accept()
        else:
            # 如果没有选择，提示用户
            pass
            
    def closeEvent(self, event):
        """关闭事件"""
        self._stop_loading = True
        super().closeEvent(event)
    
    def showEvent(self, event):
        """显示时应用阴影效果并居中"""
        super().showEvent(event)
        center_dialog_on_main_window(self)
        if not getattr(self, '_shadow_applied', False):
            self._shadow_applied = True
            enable_window_shadow_and_round_corners(self, radius=12)
        self._start_show_animation()

    def _start_show_animation(self):
        """窗口出现动画 (0.2s)"""
        self.opacity_anim = QtCompat.QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QtCompat.OutCubic)

        pos = self.pos()
        self.pos_anim = QtCompat.QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(200)
        self.pos_anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
        self.pos_anim.setEndValue(pos)
        self.pos_anim.setEasingCurve(QtCompat.OutCubic)

        self.anim_group = QtCompat.QParallelAnimationGroup()
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.start()
