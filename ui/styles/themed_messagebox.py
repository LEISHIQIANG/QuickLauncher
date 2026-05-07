"""
主题化消息框
提供跟随主题的 QMessageBox 替代品
"""

from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    Qt, QtCompat, QPainter, QPainterPath, QColor, QPen, QTimer, QPoint
)
from .style import get_dialog_stylesheet
from ui.utils.dialog_helper import center_dialog_on_main_window
from ui.utils.window_effect import get_window_effect, is_win10, is_win11


class ThemedMessageBox(QDialog):
    """主题化消息框"""

    # 消息框类型
    Information = 0
    Question = 1
    Warning = 2
    Critical = 3

    # 按钮类型
    Ok = 0x00000400
    Cancel = 0x00400000
    Yes = 0x00004000
    No = 0x00010000

    def __init__(self, parent=None, icon_type=Information, title="", text="", buttons=Ok):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(480)
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Dialog)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)  # 初始透明度为 0

        self.corner_radius = 8 if is_win11() else 12
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)
        self.result_value = 0
        self.title_text = title
        self._theme = "dark"
        self._acrylic_applied = False

        # 主布局 - 紧凑间距
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题栏（图标 + 标题）
        if title:
            title_layout = QHBoxLayout()
            title_layout.setSpacing(8)
            title_layout.setContentsMargins(0, 0, 0, 0)

            # 图标
            icon_label = QLabel()
            icon_text = self._get_icon_text(icon_type)
            icon_label.setText(icon_text)
            icon_label.setStyleSheet("font-size: 20px; margin-top: -3px;")
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.raise_()  # 提升到最前面
            title_layout.addWidget(icon_label)

            # 标题
            title_label = QLabel(title)
            title_label.setObjectName("TitleLabel")
            title_label.setStyleSheet("font-size: 13px; font-weight: 500;")
            title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            title_layout.addWidget(title_label, 1)

            layout.addLayout(title_layout)

        # 文本内容
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif; font-size: 11px; line-height: 1.4; padding-left: 32px;")
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(text_label)

        # 按钮 - 紧凑样式
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        self.button_results = {}

        if buttons & self.Yes:
            yes_btn = QPushButton("是")
            yes_btn.setFixedHeight(22)
            yes_btn.setMinimumWidth(52)
            yes_btn.clicked.connect(lambda: self._set_result(self.Yes))
            btn_layout.addWidget(yes_btn)
            self.button_results[self.Yes] = yes_btn

        if buttons & self.No:
            no_btn = QPushButton("否")
            no_btn.setFixedHeight(22)
            no_btn.setMinimumWidth(52)
            no_btn.clicked.connect(lambda: self._set_result(self.No))
            btn_layout.addWidget(no_btn)
            self.button_results[self.No] = no_btn

        if buttons & self.Ok:
            ok_btn = QPushButton("确定")
            ok_btn.setDefault(True)
            ok_btn.setFixedHeight(22)
            ok_btn.setMinimumWidth(52)
            ok_btn.clicked.connect(lambda: self._set_result(self.Ok))
            btn_layout.addWidget(ok_btn)
            self.button_results[self.Ok] = ok_btn

        if buttons & self.Cancel:
            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedHeight(22)
            cancel_btn.setMinimumWidth(52)
            cancel_btn.clicked.connect(lambda: self._set_result(self.Cancel))
            btn_layout.addWidget(cancel_btn)
            self.button_results[self.Cancel] = cancel_btn

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

    def _get_icon_text(self, icon_type):
        """获取图标文本"""
        if icon_type == self.Information:
            return "ℹ️"
        elif icon_type == self.Question:
            return "❓"
        elif icon_type == self.Warning:
            return "⚠️"
        elif icon_type == self.Critical:
            return "❌"
        return "ℹ️"

    def _detect_theme(self):
        """检测当前主题"""
        theme = "dark"
        if self.parent():
            try:
                parent = self.parent()
                # 优先从 _theme 属性获取（如 LogWindow 等自定义窗口）
                while parent:
                    if hasattr(parent, '_theme'):
                        theme = parent._theme
                        break
                    if hasattr(parent, 'data_manager'):
                        theme = parent.data_manager.get_settings().theme
                        break
                    parent = parent.parent() if hasattr(parent, 'parent') else None
            except:
                pass
        if theme == "dark" and not self.parent():
            try:
                from core import DataManager
                dm = DataManager()
                theme = dm.get_settings().theme
            except:
                pass
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

    def paintEvent(self, event):
        """背景绘制 - 完全按照RoundedWindow的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset,
            self.width() - inset * 2, self.height() - inset * 2,
            self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与RoundedWindow完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        # 边框
        pen_color = QColor(self.border_color)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1))
        painter.drawPath(path)

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
        except Exception:
            pass

    @staticmethod
    def information(parent, title, text):
        """显示信息消息框"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Information, title, text, ThemedMessageBox.Ok)
        dialog.exec_()
        return dialog.result()

    @staticmethod
    def question(parent, title, text, buttons=None):
        """显示询问消息框"""
        if buttons is None:
            buttons = ThemedMessageBox.Yes | ThemedMessageBox.No
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Question, title, text, buttons)
        dialog.exec_()
        return dialog.result()

    @staticmethod
    def warning(parent, title, text):
        """显示警告消息框"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Warning, title, text, ThemedMessageBox.Ok)
        dialog.exec_()
        return dialog.result()

    @staticmethod
    def critical(parent, title, text):
        """显示错误消息框"""
        dialog = ThemedMessageBox(parent, ThemedMessageBox.Critical, title, text, ThemedMessageBox.Ok)
        dialog.exec_()
        return dialog.result()


class ThemedInputDialog(QDialog):
    """主题化输入对话框"""

    def __init__(self, parent=None, title="", label="", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(280)
        self.setMaximumWidth(480)
        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Dialog)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)

        self.corner_radius = 8 if is_win11() else 12
        self.bg_color = QColor(28, 28, 30, 180)
        self.border_color = QColor(190, 190, 197, 60)
        self.input_text = text
        self.ok_clicked = False
        self._theme = "dark"
        self._acrylic_applied = False

        # 主布局 - 紧凑间距
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("TitleLabel")
            title_label.setStyleSheet("font-size: 13px; font-weight: 400; margin-bottom: 4px;")
            title_label.setAlignment(Qt.AlignLeft)
            layout.addWidget(title_label)

        # 标签
        if label:
            label_widget = QLabel(label)
            label_widget.setStyleSheet("font-size: 11px; margin-bottom: 2px;")
            label_widget.setAlignment(Qt.AlignLeft)
            layout.addWidget(label_widget)

        # 输入框
        from qt_compat import QLineEdit, QFont
        self.line_edit = QLineEdit()
        self.line_edit.setText(text)
        self.line_edit.setFixedHeight(28)

        # 设置字体 - 垂直hinting平衡清晰度和重影
        font = QFont("Microsoft YaHei", 9)
        font.setWeight(QFont.Weight.Normal)
        font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.line_edit.setFont(font)

        self.line_edit.selectAll()
        layout.addWidget(self.line_edit)

        # 按钮 - 紧凑样式
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(22)
        cancel_btn.setMinimumWidth(52)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setDefault(True)
        ok_btn.setFixedHeight(22)
        ok_btn.setMinimumWidth(52)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 应用主题
        self._apply_theme()

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

    def paintEvent(self, event):
        """背景绘制 - 完全按照RoundedWindow的逻辑"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        inset = 1.0 if is_win10() else 0.5

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset,
            self.width() - inset * 2, self.height() - inset * 2,
            self.corner_radius, self.corner_radius
        )

        # 磨砂玻璃模式：与RoundedWindow完全一致
        tint_color = QColor(self.bg_color)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        # 边框
        pen_color = QColor(self.border_color)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1.0))
        painter.drawPath(path)

    def _on_ok(self):
        """确定按钮点击"""
        self.input_text = self.line_edit.text()
        self.ok_clicked = True
        self.accept()

    def showEvent(self, event):
        """显示时居中并应用模糊效果"""
        super().showEvent(event)
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
        except Exception:
            pass

    @staticmethod
    def getText(parent, title, label, text=""):
        """获取文本输入"""
        dialog = ThemedInputDialog(parent, title, label, text)
        result = dialog.exec_()
        if result and dialog.ok_clicked:
            return dialog.input_text, True
        return "", False
