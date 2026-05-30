"""
快捷方式编辑对话框
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import ShortcutItem, ShortcutType
from core.i18n import tr
from qt_compat import (
    QCheckBox,
    QColor,
    QFont,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPushButton,
    QtCompat,
    QThread,
    QVBoxLayout,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.utils.safe_file_dialog import get_existing_directory, get_open_file_name

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)


class _IconLoadThread(QThread):
    """后台线程：提取图标，避免阻塞主线程。"""

    finished = pyqtSignal(object)  # QPixmap or None

    def __init__(self, custom_icon_path: str, target_path: str, parent=None):
        super().__init__(parent)
        self._custom_icon_path = custom_icon_path
        self._target_path = target_path

    def run(self):
        from core.icon_extractor import IconExtractor

        pixmap = None

        # 1. 尝试自定义图标
        icon_path = self._custom_icon_path
        if icon_path:
            # 去掉 index 后缀判断文件是否存在
            check_path = icon_path
            if "," in icon_path:
                check_path = icon_path.rsplit(",", 1)[0]
            if os.path.exists(check_path) or "," in icon_path:
                try:
                    pixmap = IconExtractor.from_file(icon_path, 48)
                except Exception:
                    pass

        # 2. 尝试目标文件图标
        if not pixmap and self._target_path:
            try:
                pixmap = IconExtractor.extract(self._target_path, self._target_path, 48, fallback_to_default=False)
            except Exception:
                pass

        self.finished.emit(pixmap)


class ShortcutDialog(BaseDialog):
    """快捷方式编辑对话框"""

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.FILE)
        self._custom_icon_path = self.shortcut.icon_path or ""

        self.setWindowTitle(tr("编辑快捷方式") if shortcut else tr("添加快捷方式"))
        self.setMinimumWidth(380)

        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        """设置窗口图标"""
        try:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                font = QFont("Segoe UI Emoji", 40)
                font.setStyleHint(QFont.StyleHint.SansSerif)
                painter.setFont(font)
                painter.setPen(QColor(70, 130, 180))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "📁")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception:
            pass

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"

        custom_style = (
            base_style
            + f"""
            QDialog {{ background: transparent; border: none; }}
            QGroupBox {{
                border: 1px solid {border_color};
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 8px;
                font-weight: 400;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: -9px;
                top: -3px;
                color: {title_color};
                font-size: 13px;
            }}
        """
        )
        self.setStyleSheet(custom_style)

        # 按钮使用扁平操作按钮样式（与主配置窗口底部四按钮一致）
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [
            self._browse_target_btn,
            self._browse_workdir_btn,
            self._browse_icon_btn,
            self._clear_icon_btn,
            self._cancel_btn,
            self._ok_btn,
        ]:
            btn.setStyleSheet(flat_btn_style)

        # 应用复选框样式
        cb_style = get_small_checkbox_stylesheet(theme)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)
        self.run_as_admin_cb.setStyleSheet(cb_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑快捷方式" if self.shortcut.name else "添加快捷方式")
        title_label.setStyleSheet("font-size: 12px; font-weight: 400; color: gray;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)
        basic_layout.setContentsMargins(8, 0, 8, 8)

        # 名称
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)

        # 目标路径
        target_layout = QHBoxLayout()
        target_layout.setSpacing(8)
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("程序或文件路径")
        target_layout.addWidget(self.target_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_target)
        target_layout.addWidget(browse_btn)
        self._browse_target_btn = browse_btn
        basic_layout.addRow(tr("目标:"), target_layout)

        layout.addWidget(basic_group)

        launch_group = QGroupBox("启动参数")
        launch_layout = QFormLayout(launch_group)
        launch_layout.setSpacing(6)
        launch_layout.setContentsMargins(8, 0, 8, 8)

        # 参数
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("可选，启动参数")
        launch_layout.addRow(tr("参数:"), self.args_edit)

        # 工作目录
        workdir_layout = QHBoxLayout()
        workdir_layout.setSpacing(8)
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText("可选，工作目录")
        workdir_layout.addWidget(self.workdir_edit)

        workdir_btn = QPushButton("浏览...")
        workdir_btn.clicked.connect(self._browse_workdir)
        workdir_layout.addWidget(workdir_btn)
        self._browse_workdir_btn = workdir_btn
        launch_layout.addRow(tr("工作目录:"), workdir_layout)

        # 以管理员身份运行
        self.run_as_admin_cb = QCheckBox("以管理员身份运行")
        launch_layout.addRow("", self.run_as_admin_cb)

        layout.addWidget(launch_group)

        # 图标设置
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 0, 6, 6)

        # 图标预览
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            """
            QLabel {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
        """
        )
        icon_layout.addWidget(self.icon_preview)

        # 图标路径和按钮
        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(6)

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("留空则使用默认图标")
        self.icon_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(8)

        browse_icon_btn = QPushButton("选择图标...")
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton("清除")
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(clear_icon_btn)
        self._clear_icon_btn = clear_icon_btn

        icon_btn_layout.addStretch()
        icon_right_layout.addLayout(icon_btn_layout)

        # 图标反转选项（紧凑垂直排列，在清除按钮右侧）
        invert_v_layout = QVBoxLayout()
        invert_v_layout.setSpacing(2)
        invert_v_layout.setContentsMargins(0, 0, 0, 0)
        self.invert_theme_cb = QCheckBox("随主题反转")
        self.invert_theme_cb.setStyleSheet(
            """
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """
        )
        self.invert_current_cb = QCheckBox("当前反转")
        self.invert_current_cb.setStyleSheet(
            """
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """
        )
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        invert_v_layout.addWidget(self.invert_theme_cb)
        invert_v_layout.addWidget(self.invert_current_cb)
        icon_btn_layout.addLayout(invert_v_layout)

        icon_layout.addLayout(icon_right_layout, 1)

        layout.addWidget(icon_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 32)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        self._ok_btn = ok_btn

        layout.addLayout(btn_layout)

    def _load_data(self):
        """加载数据"""
        self.name_edit.setText(self.shortcut.name or "")
        self.target_edit.setText(self.shortcut.target_path or "")
        self.args_edit.setText(self.shortcut.target_args or "")
        self.workdir_edit.setText(self.shortcut.working_dir or "")
        if self._custom_icon_path:
            self.icon_edit.setText(self._custom_icon_path)

        # 加载反转设置
        self.invert_theme_cb.setChecked(self.shortcut.icon_invert_with_theme)
        self.invert_current_cb.setChecked(self.shortcut.icon_invert_current)

        # 加载管理员运行设置
        self.run_as_admin_cb.setChecked(self.shortcut.run_as_admin)

        self._update_icon_preview()

    def _update_icon_preview(self):
        """更新图标预览（异步加载，避免阻塞主线程）"""
        # 取消上一次未完成的加载
        thread = getattr(self, "_icon_thread", None)
        if thread is not None and thread.isRunning():
            thread.finished.disconnect()
            thread.terminate()
            thread.wait(200)
            thread.deleteLater()
            self._icon_thread = None

        custom = self._custom_icon_path or ""
        target = self.target_edit.text().strip() if hasattr(self, "target_edit") else ""

        if not custom and not target:
            # 无路径，直接显示默认图标
            pixmap = self._create_file_icon(48)
            self._apply_icon_to_preview(pixmap)
            return

        # 先显示默认图标，后台加载真实图标
        self._apply_icon_to_preview(self._create_file_icon(48))

        thread = _IconLoadThread(custom, target, parent=None)
        thread.finished.connect(self._on_icon_loaded)
        self._icon_thread = thread
        thread.start()

    def _on_icon_loaded(self, pixmap):
        """后台图标加载完成"""
        self._icon_thread = None
        if not pixmap or pixmap.isNull():
            pixmap = self._create_file_icon(48)
        self._apply_icon_to_preview(pixmap)

    def _apply_icon_to_preview(self, pixmap):
        """将图标应用到预览控件（仅在主线程调用）"""
        # 应用反转
        if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor

            pixmap = IconExtractor.invert_pixmap(pixmap)

        # 缩放到预览尺寸
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

        self.icon_preview.setPixmap(pixmap)

    def _create_file_icon(self, size: int) -> QPixmap:
        """创建文件默认图标"""
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
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "📄")

        painter.end()
        return pixmap

    def _browse_target(self):
        """浏览目标文件"""
        file_path, _ = get_open_file_name(
            self,
            tr("选择目标"),
            "",
            tr("可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)"),
        )

        if file_path:
            self.target_edit.setText(file_path)

            # 自动填充名称
            if not self.name_edit.text():
                name = os.path.splitext(os.path.basename(file_path))[0][:6]
                self.name_edit.setText(name)

            # 解析 .lnk
            if file_path.lower().endswith(".lnk"):
                try:
                    from core.shortcut_parser import ShortcutParser

                    info = ShortcutParser.parse(file_path)
                    self.target_edit.setText(info.get("target", file_path))
                    self.args_edit.setText(info.get("args", ""))
                    self.workdir_edit.setText(info.get("working_dir", ""))
                except Exception:
                    pass

            # 更新预览
            self._update_icon_preview()

    def _browse_workdir(self):
        """浏览工作目录"""
        folder = get_existing_directory(self, tr("选择工作目录"))
        if folder:
            self.workdir_edit.setText(folder)

    def _browse_icon(self):
        """浏览图标"""
        file_path = choose_custom_icon(self, "选择图标")
        if file_path:
            self._custom_icon_path = file_path
            self.icon_edit.setText(file_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()

    def _clear_icon(self):
        """清除图标"""
        self._custom_icon_path = ""
        self.icon_edit.clear()
        self.invert_theme_cb.setChecked(False)
        self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_invert_theme_changed(self, state):
        """随主题反转勾选变化"""
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_ok(self):
        """确定"""
        name = self.name_edit.text().strip()
        target = self.target_edit.text().strip()

        if not name:
            self.name_edit.setFocus()
            return

        if not target:
            self.target_edit.setFocus()
            return

        self.accept()

    def done(self, result):
        thread = getattr(self, "_icon_thread", None)
        if thread is not None:
            try:
                thread.finished.disconnect(self._on_icon_loaded)
            except Exception:
                pass
            if thread.isRunning():
                thread.terminate()
                thread.wait(200)
            thread.deleteLater()
            self._icon_thread = None
        super().done(result)

    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.target_path = self.target_edit.text().strip()
        self.shortcut.target_args = self.args_edit.text().strip()
        self.shortcut.working_dir = self.workdir_edit.text().strip()
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        self.shortcut.run_as_admin = self.run_as_admin_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, "theme", "dark")
        return self.shortcut
