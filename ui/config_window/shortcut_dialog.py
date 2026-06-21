"""
快捷方式编辑对话框
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
import logging
import os

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from core.shortcut_icon_helpers import (
    default_folder_icon_path,
    shortcut_type_for_target,
    shortcut_uses_folder_icon,
)
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
    QRectF,
    QtCompat,
    QThread,
    QVBoxLayout,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism
from ui.utils.pixel_snap import create_pixmap
from ui.utils.qt_thread_cleanup import stop_qthread_nonblocking
from ui.utils.safe_file_dialog import get_existing_directory, get_open_file_name
from ui.utils.ui_scale import font_px, scale_qss, sp

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_compact_checkbox_stylesheet, get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)


class _IconLoadThread(QThread):
    """后台线程：提取图标，避免阻塞主线程。"""

    icon_loaded = pyqtSignal(object)  # QPixmap or None

    def __init__(self, custom_icon_path: str, target_path: str, shortcut_type: ShortcutType, parent=None):
        super().__init__(parent)
        self._custom_icon_path = custom_icon_path
        self._target_path = target_path
        self._shortcut_type = shortcut_type
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        from core.icon_extractor import IconExtractor

        pixmap = None

        # 1. 尝试自定义图标
        icon_path = self._custom_icon_path
        if icon_path and not self._stop_requested:
            # 去掉 index 后缀判断文件是否存在
            check_path = icon_path
            if "," in icon_path:
                check_path = icon_path.rsplit(",", 1)[0]
            if os.path.exists(check_path) or "," in icon_path:
                try:
                    pixmap = IconExtractor.from_file(icon_path, 48)
                except Exception as exc:
                    logger.debug("从文件加载图标失败: %s", exc, exc_info=True)

        if (
            not pixmap
            and not icon_path
            and not self._stop_requested
            and shortcut_uses_folder_icon(self._shortcut_type, self._target_path)
        ):
            folder_icon = default_folder_icon_path()
            if folder_icon:
                try:
                    pixmap = IconExtractor.from_file(folder_icon, 48)
                except Exception as exc:
                    logger.debug("加载默认文件夹图标失败: %s", exc, exc_info=True)

        # 2. 尝试目标文件图标
        if not pixmap and self._target_path and not self._stop_requested:
            try:
                pixmap = IconExtractor.extract(self._target_path, self._target_path, 48, fallback_to_default=False)
            except Exception as exc:
                logger.debug("提取目标文件图标失败: %s", exc, exc_info=True)

        if not self._stop_requested:
            self.icon_loaded.emit(pixmap)


class ShortcutDialog(BaseDialog):
    """快捷方式编辑对话框"""

    def __init__(self, parent=None, shortcut: ShortcutItem = None):  # type: ignore[assignment]
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.FILE)
        self._custom_icon_path = self.shortcut.icon_path or ""

        self.setWindowTitle(tr("编辑快捷方式") if shortcut else tr("添加快捷方式"))
        self.setMinimumWidth(sp(380))

        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        """设置窗口图标"""
        try:
            pixmap = QPixmap(sp(64), sp(64))
            pixmap.setDevicePixelRatio(1.0)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                painter.setRenderHint(QtCompat.HighQualityAntialiasing)
                font = QFont("Segoe UI Emoji", font_px(40))
                font.setStyleHint(QFont.StyleHint.SansSerif)
                painter.setFont(font)
                painter.setPen(QColor(70, 130, 180))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "📁")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception as exc:
            logger.debug("设置窗口图标失败: %s", exc, exc_info=True)

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"

        custom_style = base_style + scale_qss(
            f"""
            QDialog {{ background: transparent; border: none; border-radius: 0; }}
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
        invert_cb_style = get_compact_checkbox_stylesheet(theme)
        self.invert_light_cb.setStyleSheet(invert_cb_style)
        self.invert_dark_cb.setStyleSheet(invert_cb_style)
        self.run_as_admin_cb.setStyleSheet(cb_style)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(sp(6))
        layout.setContentsMargins(sp(8), sp(8), sp(8), sp(8))  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑快捷方式" if self.shortcut.name else "添加快捷方式")
        title_label.setStyleSheet(scale_qss("font-size: 12px; font-weight: 400; color: gray;"))
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(sp(6))
        basic_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))

        # 名称
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow(tr("名称:"), self.name_edit)

        # 目标路径
        target_layout = QHBoxLayout()
        target_layout.setSpacing(sp(8))
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
        launch_layout.setSpacing(sp(6))
        launch_layout.setContentsMargins(sp(8), 0, sp(8), sp(8))

        # 参数
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("可选，启动参数")
        launch_layout.addRow(tr("参数:"), self.args_edit)

        # 工作目录
        workdir_layout = QHBoxLayout()
        workdir_layout.setSpacing(sp(8))
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
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), 0, sp(6), sp(6))

        # 图标预览
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            scale_qss(
                """
            QLabel {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
        """
            )
        )
        icon_layout.addWidget(self.icon_preview)

        # 图标路径和按钮
        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(sp(6))

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("留空则使用默认图标")
        self.icon_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(sp(8))

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

        # 图标反转选项（并排排列）
        self.invert_light_cb = QCheckBox("浅色反转")
        self.invert_dark_cb = QCheckBox("深色反转")
        icon_btn_layout.addWidget(self.invert_light_cb)
        icon_btn_layout.addWidget(self.invert_dark_cb)

        icon_layout.addLayout(icon_right_layout, 1)

        layout.addWidget(icon_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(sp(8))
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(sp(80), sp(32))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(sp(80), sp(32))
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
        self.invert_light_cb.setChecked(self.shortcut.icon_invert_light)
        self.invert_dark_cb.setChecked(self.shortcut.icon_invert_dark)

        # 加载管理员运行设置
        self.run_as_admin_cb.setChecked(self.shortcut.run_as_admin)

        self._update_icon_preview()

    def _update_icon_preview(self):
        """更新图标预览（异步加载，避免阻塞主线程）"""
        # 取消上一次未完成的加载
        thread = getattr(self, "_icon_thread", None)
        if thread is not None and thread.isRunning():
            stop_qthread_nonblocking(
                thread,
                owner="ShortcutDialog.icon_loader",
                wait_ms=0,
                disconnect_thread_signals=("icon_loaded",),
            )
            self._icon_thread = None

        custom = self._custom_icon_path or ""
        target = self.target_edit.text().strip() if hasattr(self, "target_edit") else ""

        if not custom and not target:
            # 无路径，直接显示默认图标
            pixmap = self._create_file_icon(48)
            self._apply_icon_to_preview(pixmap)
            return

        # 先显示默认图标，后台加载真实图标
        self._apply_icon_to_preview(self._create_fallback_icon(48))

        thread = _IconLoadThread(custom, target, self.shortcut.type, parent=None)
        thread.icon_loaded.connect(self._on_icon_loaded)
        self._icon_thread = thread
        thread.start()

    def _on_icon_loaded(self, pixmap):
        """后台图标加载完成"""
        self._icon_thread = None
        if not pixmap or pixmap.isNull():
            pixmap = self._create_fallback_icon(48)
        self._apply_icon_to_preview(pixmap)

    def _apply_icon_to_preview(self, pixmap):
        """将图标应用到预览控件（仅在主线程调用）"""
        # 应用反转（根据当前主题对应的反转标志）
        _current_theme = getattr(self, "theme", "dark")
        _need_invert = (
            self.invert_light_cb.isChecked() if _current_theme == "light" else self.invert_dark_cb.isChecked()
        )
        if _need_invert and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor

            pixmap = IconExtractor.invert_pixmap(pixmap)

        # 缩放到预览尺寸
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

        self.icon_preview.setPixmap(pixmap)

    def _create_file_icon(self, size: int) -> QPixmap:
        """创建文件默认图标"""
        pixmap = create_pixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)

        painter.setBrush(QColor(70, 130, 180))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "📄")

        painter.end()
        return pixmap

    def _create_fallback_icon(self, size: int) -> QPixmap:
        target = self.target_edit.text().strip() if hasattr(self, "target_edit") else ""
        if shortcut_uses_folder_icon(self.shortcut.type, target, resolve_lnk=False):
            folder_icon = default_folder_icon_path()
            if folder_icon:
                pixmap = QPixmap(folder_icon)
                if pixmap and not pixmap.isNull():
                    return pixmap.scaled(size, size, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        return self._create_file_icon(size)

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
                except Exception as exc:
                    logger.debug("解析快捷方式文件失败: %s", exc, exc_info=True)

            self.shortcut.type = shortcut_type_for_target(self.target_edit.text().strip())

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
            self._update_icon_preview()

    def _clear_icon(self):
        """清除图标"""
        self._custom_icon_path = ""
        self.icon_edit.clear()
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
            stopped = stop_qthread_nonblocking(
                thread,
                owner="ShortcutDialog.icon_loader",
                wait_ms=0,
                disconnect_thread_signals=("icon_loaded",),
            )
            if stopped:
                self._icon_thread = None
        super().done(result)

    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.target_path = self.target_edit.text().strip()
        self.shortcut.type = shortcut_type_for_target(self.shortcut.target_path)
        self.shortcut.target_args = self.args_edit.text().strip()
        self.shortcut.working_dir = self.workdir_edit.text().strip()
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.icon_invert_light = self.invert_light_cb.isChecked()
        self.shortcut.icon_invert_dark = self.invert_dark_cb.isChecked()
        self.shortcut.run_as_admin = self.run_as_admin_cb.isChecked()
        return self.shortcut
