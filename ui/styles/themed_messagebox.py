"""
主题化消息框
提供跟随主题的 QMessageBox 替代品
"""

import logging
import os
import sys

from core.i18n import tr
from hooks.hook_pause import mouse_hook_paused
from qt_compat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPoint,
    QPushButton,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.utils.dialog_helper import center_dialog_on_main_window
from ui.utils.font_manager import get_qfont, tune_font_rendering
from ui.utils.window_effect import get_window_effect, is_win10, is_win11, paint_win10_rounded_surface

from .style import get_dialog_stylesheet
from .window_chrome import apply_custom_window_chrome

logger = logging.getLogger(__name__)


def _execute_native_message_box(parent, title, text, icon_type, buttons) -> int:
    """
    同步安全地在主线程呼起 QuickLauncher 自定义消息框。
    在调用前原子同步暂停鼠标钩子，绝对防止瞬间误触与死锁，且完全集成于 Qt 事件循环。
    提供极其详尽的步骤追踪，便于环境审计。
    """
    # logger.debug("[消息框追踪] ================= 开始执行安全消息框流程 ================= ")

    try:
        from ui.utils.safe_file_dialog import _global_mouse_hook
    except ImportError:
        _global_mouse_hook = None

    res = 1024  # Default/None
    with mouse_hook_paused(_global_mouse_hook, log_label="消息框鼠标钩子"):
        try:
            # 映射图标
            if icon_type == "info":
                icon = ThemedMessageBox.Information
            elif icon_type == "question":
                icon = ThemedMessageBox.Question
            elif icon_type == "warning":
                icon = ThemedMessageBox.Warning
            elif icon_type == "critical":
                icon = ThemedMessageBox.Critical
            else:
                icon = ThemedMessageBox.Information

            dialog = ThemedMessageBox(parent, icon, title or "提示", text, buttons)
            dialog.exec_()
            res = dialog.result()
        except Exception as e:
            logger.error(f"[消息框追踪] 步骤 2 异常: {e}", exc_info=True)

    # logger.debug("[消息框追踪] ================= 安全消息框流程执行完毕 ================= ")
    return res


class ThemedMessageBox(QDialog):
    """主题化消息框"""

    # 消息框类型
    Information = 0
    Question = 1
    Warning = 2
    Critical = 3
    Download = 4

    _ICON_FILE_NAMES = {
        Information: "information.png",
        Question: "question.png",
        Warning: "warning.png",
        Critical: "critical.png",
        Download: "download.png",
    }

    # 按钮类型
    Ok = 0x00000400
    Cancel = 0x00400000
    Yes = 0x00004000
    No = 0x00010000

    def __init__(self, parent=None, icon_type=Information, title="", text="", buttons=Ok):
        parent = self._coerce_parent(parent)
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(180)
        self.setMaximumWidth(300)
        apply_custom_window_chrome(self, kind="dialog", translucent=True)
        self.setFont(get_qfont(12))
        self.setWindowOpacity(0)  # 初始透明度为 0

        self.corner_radius = 8
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)
        self.result_value = 0
        self.title_text = title
        self._theme = "dark"
        self._acrylic_applied = False
        self._dialog_finished = False
        self._title_label = None

        # 主布局 - 紧凑间距
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题栏（图标 + 标题）
        if title:
            title_layout = QHBoxLayout()
            title_layout.setSpacing(8)
            title_layout.setContentsMargins(0, 0, 0, 0)

            icon_label = QLabel()
            self.configure_icon_label(icon_label, icon_type)
            icon_label.raise_()
            title_layout.addWidget(icon_label)

            # 标题
            title_label = QLabel(title)
            title_label.setObjectName("TitleLabel")
            title_label.setFont(get_qfont(13, 400))
            title_label.setStyleSheet("font-size: 13px; font-weight: 400; margin-bottom: 4px;")
            title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._title_label = title_label
            title_layout.addWidget(title_label, 1)

            layout.addLayout(title_layout)

        # 文本内容
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setFont(get_qfont(12))
        text_label.setStyleSheet("font-size: 12px; line-height: 1.4;")
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(text_label)

        # 按钮 - 紧凑样式
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        self.button_results = {}

        if buttons & self.Yes:
            yes_btn = QPushButton(tr("是"))
            yes_btn.setFixedHeight(22)
            yes_btn.setMinimumWidth(52)
            yes_btn.clicked.connect(lambda: self._set_result(self.Yes))
            btn_layout.addWidget(yes_btn)
            self.button_results[self.Yes] = yes_btn

        if buttons & self.No:
            no_btn = QPushButton(tr("否"))
            no_btn.setFixedHeight(22)
            no_btn.setMinimumWidth(52)
            no_btn.clicked.connect(lambda: self._set_result(self.No))
            btn_layout.addWidget(no_btn)
            self.button_results[self.No] = no_btn

        if buttons & self.Ok:
            ok_btn = QPushButton(tr("确定"))
            ok_btn.setDefault(True)
            ok_btn.setFixedHeight(22)
            ok_btn.setMinimumWidth(52)
            ok_btn.clicked.connect(lambda: self._set_result(self.Ok))
            btn_layout.addWidget(ok_btn)
            self.button_results[self.Ok] = ok_btn

        if buttons & self.Cancel:
            cancel_btn = QPushButton(tr("取消"))
            cancel_btn.setFixedHeight(22)
            cancel_btn.setMinimumWidth(52)
            cancel_btn.clicked.connect(lambda: self._set_result(self.Cancel))
            btn_layout.addWidget(cancel_btn)
            self.button_results[self.Cancel] = cancel_btn

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()
        tune_font_rendering(self, recursive=True)
        self._apply_explicit_fonts()

    @staticmethod
    def _coerce_parent(parent):
        return parent if parent is None or isinstance(parent, QWidget) else None

    @classmethod
    def configure_icon_label(cls, icon_label, icon_type, size=24):
        """Apply the themed PNG icon while preserving the original label size."""
        icon_label.setFixedSize(size, size)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")

        pixmap = cls._get_icon_pixmap(icon_type, size)
        if pixmap and not pixmap.isNull():
            icon_label.setPixmap(pixmap)
            return

        icon_label.setText(cls._get_icon_text(icon_type))
        icon_label.setStyleSheet("font-size: 20px; margin-top: -3px;")

    @classmethod
    def _get_icon_pixmap(cls, icon_type, size=24):
        path = cls._get_icon_path(icon_type)
        if not path:
            return QPixmap()
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return pixmap
        return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    @classmethod
    def _get_icon_path(cls, icon_type):
        file_name = cls._ICON_FILE_NAMES.get(icon_type, cls._ICON_FILE_NAMES[cls.Information])
        relative_parts = ("dialog_icons", file_name)
        for root in cls._asset_roots():
            path = os.path.join(root, *relative_parts)
            if os.path.exists(path):
                return path
        return ""

    @staticmethod
    def _asset_roots():
        roots = []
        if hasattr(sys, "_MEIPASS"):
            roots.append(os.path.join(sys._MEIPASS, "assets"))
        roots.extend(
            [
                os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets"),
                os.path.join(os.getcwd(), "assets"),
            ]
        )

        seen = set()
        for root in roots:
            normalized = os.path.normpath(root)
            if normalized not in seen:
                seen.add(normalized)
                yield normalized

    @classmethod
    def _get_icon_text(cls, icon_type):
        """获取图标文本"""
        if icon_type == cls.Information:
            return "ℹ️"
        elif icon_type == cls.Question:
            return "❓"
        elif icon_type == cls.Warning:
            return "⚠️"
        elif icon_type == cls.Critical:
            return "❌"
        elif icon_type == cls.Download:
            return "⬇"
        return "ℹ️"

    def _detect_theme(self):
        """检测当前主题"""
        theme = "dark"
        if self.parent():
            try:
                parent = self.parent()
                # 优先从 _theme 属性获取（如 LogWindow 等自定义窗口）
                while parent:
                    if hasattr(parent, "_theme"):
                        theme = parent._theme
                        break
                    if hasattr(parent, "data_manager"):
                        theme = parent.data_manager.get_settings().theme
                        break
                    parent = parent.parent() if hasattr(parent, "parent") else None
            except Exception as exc:
                logger.debug("从父窗口获取主题失败: %s", exc, exc_info=True)
        if theme == "dark" and not self.parent():
            try:
                from core import DataManager

                dm = DataManager()
                theme = dm.get_settings().theme
            except Exception as exc:
                logger.debug("从DataManager获取主题失败: %s", exc, exc_info=True)
        return theme

    def _apply_theme(self):
        """应用主题 - 与主配置窗口一致的 alpha 处理"""
        theme = self._detect_theme()
        self._theme = theme

        self.setStyleSheet(get_dialog_stylesheet(theme))

        # 使用与主配置窗口一致的颜色和 alpha 值
        if theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

    def _apply_explicit_fonts(self):
        if self._title_label is not None:
            self._title_label.setFont(get_qfont(13, 400))

    def paintEvent(self, event):
        """背景绘制 - 完全按照RoundedWindow的逻辑"""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if is_win10():
                paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                return

            inset = 1.0 if is_win10() else 0.5

            path = QPainterPath()
            path.addRoundedRect(
                inset, inset, self.width() - inset * 2, self.height() - inset * 2, self.corner_radius, self.corner_radius
            )

            # 磨砂玻璃模式：与RoundedWindow完全一致
            tint_color = QColor(self.bg_color)
            if is_win10():
                tint_color.setAlpha(min(tint_color.alpha(), 220))
            else:
                tint_color.setAlpha(min(tint_color.alpha(), 100))
            painter.fillPath(path, tint_color)

            # 边框
            pen_color = QColor(self.border_color)
            pen_color.setAlpha(min(pen_color.alpha(), 120))
            pen = QPen(pen_color, 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)
        finally:
            painter.end()

    def _set_result(self, value):
        """设置结果并关闭"""
        self.result_value = value
        self.accept()

    def result(self):
        """返回结果"""
        return self.result_value

    def showEvent(self, event):
        """显示时居中并应用模糊效果"""
        super().showEvent(event)
        self._dialog_finished = False
        self.adjustSize()
        center_dialog_on_main_window(self)
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)
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

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            if self._dialog_finished or not self.isVisible():
                return
            from ui.utils.window_effect import enable_acrylic_for_config_window

            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)

            enable_acrylic_for_config_window(self, self._theme, blur_amount=30, radius=self.corner_radius)
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def done(self, result):
        self._dialog_finished = True
        for attr in ("anim_group", "opacity_anim", "pos_anim"):
            anim = getattr(self, attr, None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception as exc:
                    logger.debug("停止动画失败: %s", exc, exc_info=True)
        super().done(result)

    @staticmethod
    def _exec_with_hook_pause(dialog):
        """在鼠标钩子暂停状态下执行对话框，防止误触"""
        _global_mouse_hook = None
        try:
            from ui.utils.safe_file_dialog import _global_mouse_hook as _gmh

            _global_mouse_hook = _gmh
        except ImportError:
            logger.debug("safe_file_dialog 鼠标钩子未初始化", exc_info=True)
        with mouse_hook_paused(_global_mouse_hook, log_label="消息框鼠标钩子"):
            dialog.exec_()
        return dialog.result()

    @staticmethod
    def information(parent, title, text, max_width=None):
        """显示信息消息框 - 主题化样式"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Information, title or "信息", text, ThemedMessageBox.Ok)
        if max_width:
            dialog.setMaximumWidth(max_width)
        ThemedMessageBox._exec_with_hook_pause(dialog)
        return ThemedMessageBox.Ok

    @staticmethod
    def question(parent, title, text, buttons=None, icon_type=None):
        """显示询问消息框 - 主题化样式"""
        is_legacy = isinstance(buttons, str)
        if is_legacy:
            buttons = None
        if buttons is None:
            buttons = ThemedMessageBox.Yes | ThemedMessageBox.No
        icon = ThemedMessageBox.Question if icon_type is None else icon_type
        dialog = ThemedMessageBox(parent, icon, title or "询问", text, buttons)
        result = ThemedMessageBox._exec_with_hook_pause(dialog)
        if is_legacy:
            return result == ThemedMessageBox.Yes
        return result

    @staticmethod
    def warning(parent, title, text):
        """显示警告消息框 - 主题化样式"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Warning, title or "警告", text, ThemedMessageBox.Ok)
        ThemedMessageBox._exec_with_hook_pause(dialog)
        return ThemedMessageBox.Ok

    @staticmethod
    def critical(parent, title, text):
        """显示错误消息框 - 主题化样式"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Critical, title or "错误", text, ThemedMessageBox.Ok)
        ThemedMessageBox._exec_with_hook_pause(dialog)
        return ThemedMessageBox.Ok


class ThemedInputDialog(QDialog):
    """主题化输入对话框"""

    def __init__(self, parent=None, title="", label="", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(380)
        apply_custom_window_chrome(self, kind="dialog", translucent=True)
        self.setFont(get_qfont(12))
        self.setWindowOpacity(0)

        self.corner_radius = 8
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)
        self.input_text = text
        self.ok_clicked = False
        self._theme = "dark"
        self._acrylic_applied = False
        self._dialog_finished = False

        # 主布局 - 紧凑间距
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("TitleLabel")
            title_label.setFont(get_qfont(13, 400))
            title_label.setStyleSheet("font-size: 13px; font-weight: 400; margin-bottom: 4px;")
            title_label.setAlignment(Qt.AlignLeft)
            self._title_label = title_label
            layout.addWidget(title_label)

        # 标签
        if label:
            label_widget = QLabel(label)
            label_widget.setFont(get_qfont(12))
            label_widget.setStyleSheet("font-size: 12px; margin-bottom: 2px;")
            label_widget.setAlignment(Qt.AlignLeft)
            layout.addWidget(label_widget)

        # 输入框
        from qt_compat import QLineEdit

        self.line_edit = QLineEdit()
        self.line_edit.setText(text)
        self.line_edit.setFixedHeight(28)

        # 设置字体 - 垂直hinting平衡清晰度和重影
        self.line_edit.setFont(get_qfont(12))

        self.line_edit.selectAll()
        layout.addWidget(self.line_edit)

        # 按钮 - 紧凑样式
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        cancel_btn = QPushButton(tr("取消"))
        cancel_btn.setFixedHeight(22)
        cancel_btn.setMinimumWidth(52)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("确定"))
        ok_btn.setDefault(True)
        ok_btn.setFixedHeight(22)
        ok_btn.setMinimumWidth(52)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()
        tune_font_rendering(self, recursive=True)
        self._apply_explicit_fonts()

    def _apply_theme(self):
        """应用主题 - 与主配置窗口一致的 alpha 处理"""
        theme = ThemedMessageBox._detect_theme(self)
        self._theme = theme

        from .style import get_dialog_stylesheet

        self.setStyleSheet(get_dialog_stylesheet(theme))

        if theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

    def _apply_explicit_fonts(self):
        if self._title_label is not None:
            self._title_label.setFont(get_qfont(13, 400))

    def paintEvent(self, event):
        """背景绘制 - 完全按照RoundedWindow的逻辑"""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if is_win10():
                paint_win10_rounded_surface(painter, self, self.bg_color, self.border_color, self.corner_radius)
                return

            inset = 1.0 if is_win10() else 0.5

            path = QPainterPath()
            path.addRoundedRect(
                inset, inset, self.width() - inset * 2, self.height() - inset * 2, self.corner_radius, self.corner_radius
            )

            # 磨砂玻璃模式：与RoundedWindow完全一致
            tint_color = QColor(self.bg_color)
            if is_win10():
                tint_color.setAlpha(min(tint_color.alpha(), 220))
            else:
                tint_color.setAlpha(min(tint_color.alpha(), 100))
            painter.fillPath(path, tint_color)

            # 边框
            pen_color = QColor(self.border_color)
            pen_color.setAlpha(min(pen_color.alpha(), 120))
            pen = QPen(pen_color, 1.0)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)
        finally:
            painter.end()

    def _on_ok(self):
        """确定按钮点击"""
        self.input_text = self.line_edit.text()
        self.ok_clicked = True
        self.accept()

    def showEvent(self, event):
        """显示时居中并应用模糊效果"""
        super().showEvent(event)
        self._dialog_finished = False
        self.adjustSize()
        center_dialog_on_main_window(self)
        self.line_edit.setFocus()
        if not self._acrylic_applied:
            self._acrylic_applied = True
            QTimer.singleShot(10, self._apply_acrylic)
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

    def _apply_acrylic(self):
        """应用模糊效果 - 与主配置窗口一致"""
        try:
            if self._dialog_finished or not self.isVisible():
                return
            from ui.utils.window_effect import enable_acrylic_for_config_window

            hwnd = int(self.winId())
            if not hwnd:
                return
            effect = get_window_effect()

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)

            enable_acrylic_for_config_window(self, self._theme, blur_amount=30, radius=self.corner_radius)
        except Exception as exc:
            logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

    def done(self, result):
        self._dialog_finished = True
        for attr in ("anim_group", "opacity_anim", "pos_anim"):
            anim = getattr(self, attr, None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception as exc:
                    logger.debug("停止动画失败: %s", exc, exc_info=True)
        super().done(result)

    @staticmethod
    def getText(parent, title, label, text=""):
        """获取文本输入"""
        dialog = ThemedInputDialog(parent, title, label, text)
        result = dialog.exec_()
        if result and dialog.ok_clicked:
            return dialog.input_text, True
        return "", False
