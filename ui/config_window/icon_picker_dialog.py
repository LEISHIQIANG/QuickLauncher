"""Icon resource picker for executable and DLL files."""

import logging
import os

from core.background_tasks import start_background_thread
from core.i18n import tr
from core.icon_extractor import IconExtractor
from qt_compat import (
    QHBoxLayout,
    QIcon,
    QImage,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPixmap,
    QPushButton,
    QtCompat,
    QVBoxLayout,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.utils.ui_scale import sp, sqsize

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class IconPickerDialog(BaseDialog):
    """Let users choose a specific icon resource from an .exe or .dll."""

    load_progress = pyqtSignal(int, int)
    icon_loaded = pyqtSignal(int, QImage)

    def __init__(self, parent=None, file_path: str = ""):
        super().__init__(parent)
        self.file_path = file_path
        self.selected_index = -1
        self._stop_loading = False
        self._load_thread = None
        self._closing = False
        self._selection_finishing = False

        self.setWindowTitle(f"选择图标 - {os.path.basename(file_path)}")
        self.resize(sp(600), sp(400))
        self.setModal(True)

        self._setup_ui()
        self._apply_theme_colors()
        self._apply_button_theme()
        self._start_loading()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(18), sp(18), sp(18), sp(16))
        layout.setSpacing(sp(8))

        self.info_label = QLabel("正在读取图标...")
        layout.addWidget(self.info_label)

        self.list_widget = QListWidget()
        try:
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setMovement(QListWidget.Movement.Static)
        except AttributeError:
            self.list_widget.setViewMode(QListWidget.IconMode)
            self.list_widget.setResizeMode(QListWidget.Adjust)
            self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSpacing(sp(8))
        self.list_widget.setIconSize(sqsize(48, 48))
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton("确定")
        self._ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self._ok_btn)
        layout.addLayout(btn_layout)

        self.load_progress.connect(self._update_progress)
        self.icon_loaded.connect(self._add_icon_item)

    def _apply_button_theme(self):
        theme = self._get_theme_from_parent()
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        self._cancel_btn.setStyleSheet(flat_btn_style)
        self._ok_btn.setStyleSheet(flat_btn_style)

    def _start_loading(self):
        count = IconExtractor.get_icon_count(self.file_path)
        if count <= 0:
            self.info_label.setText(tr("未找到可选图标"))
            return

        self.info_label.setText(f"发现 {count} 个图标，正在加载...")
        self._stop_loading = False
        self._load_thread = start_background_thread(
            name="IconResourcePicker",
            target=self._load_task,
            args=(count,),
            owner=self,
        )

    def _load_task(self, count: int):
        try:
            for index in range(count):
                if self._stop_loading:
                    break
                image = IconExtractor.from_file(f"{self.file_path},{index}", 48, return_image=True)
                if self._stop_loading:
                    break
                if image and not image.isNull():
                    self.icon_loaded.emit(index, image)
                if index % 10 == 0:
                    if self._stop_loading:
                        break
                    self.load_progress.emit(index + 1, count)
            if not self._stop_loading:
                self.load_progress.emit(count, count)
        except Exception:
            logger.debug("加载资源图标失败: %s", self.file_path, exc_info=True)

    def _update_progress(self, current: int, total: int):
        if not self._stop_loading and not self._closing:
            self.info_label.setText(f"已加载 {current}/{total} 个图标")

    def _add_icon_item(self, index: int, image: QImage):
        if self._stop_loading or self._closing:
            return
        pixmap = QPixmap.fromImage(image)
        item = QListWidgetItem(QIcon(pixmap), str(index))
        item.setData(QtCompat.UserRole, index)
        self.list_widget.addItem(item)

    def _on_item_double_clicked(self, item):
        if self._selection_finishing:
            return
        self.selected_index = item.data(QtCompat.UserRole)
        self._finish_selection()

    def _on_ok(self):
        if self._selection_finishing:
            return
        items = self.list_widget.selectedItems()
        if not items:
            return
        self.selected_index = items[0].data(QtCompat.UserRole)
        self._finish_selection()

    def _finish_selection(self):
        self._selection_finishing = True
        self._stop_loading = True
        self.list_widget.setEnabled(False)
        self._ok_btn.setEnabled(False)
        self.accept()

    def done(self, result):
        self._stop_loading = True
        self._closing = True
        try:
            self.load_progress.disconnect(self._update_progress)
        except Exception as exc:
            logger.debug("断开进度信号失败: %s", exc, exc_info=True)
        try:
            self.icon_loaded.disconnect(self._add_icon_item)
        except Exception as exc:
            logger.debug("断开图标加载信号失败: %s", exc, exc_info=True)
            pass
        super().done(result)
