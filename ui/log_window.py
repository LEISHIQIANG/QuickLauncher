"""
日志查看窗口 - 与主配置窗口风格统一
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QtCompat, QFont, QColor,
    QPainter, QPixmap, QIcon, QWidget, QPainterPath,
    QPen, QRectF, PYQT_VERSION, Qt, QPoint
)
from ui.utils.window_effect import enable_window_shadow_and_round_corners, get_window_effect, is_win11, enable_acrylic_for_config_window
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.styles.style import PopupMenu, Glassmorphism, StyleSheet, Colors


class RoundedMenuPlainTextEdit(QPlainTextEdit):
    """带圆角右键菜单的文本编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "light"

    def set_theme(self, theme: str):
        self._theme = theme

    def contextMenuEvent(self, event):
        """重写右键菜单事件，使用项目统一的 PopupMenu"""
        menu = PopupMenu(theme=self._theme, radius=12, parent=None)
        menu.add_action("复制", lambda: self.copy(), enabled=self.textCursor().hasSelection())
        menu.add_action("全选", lambda: self.selectAll(), enabled=len(self.toPlainText()) > 0)
        menu.popup(event.globalPos())


class LogWindow(QDialog):
    """日志查看窗口 - 跟随主题切换亮暗"""

    def __init__(self, log_path: str, theme: str = "light", parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self._theme = theme
        self._blur_applied = False
        self.setWindowOpacity(0)  # 初始透明度为 0
        self._auto_refresh_timer = None

        self.setWindowTitle("运行日志")
        self.resize(700, 500)

        # 无边框 + 透明背景
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._load_window_icon()
        self._setup_ui()
        self._apply_theme()
        self.load_log()

        # 拖动支持
        self._drag_pos = None

    def _load_window_icon(self):
        """加载窗口图标"""
        try:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            possible_paths = [
                os.path.join(root_dir, "assets", "app.ico"),
                os.path.join(root_dir, "app.ico"),
                os.path.join(sys._MEIPASS, "assets", "app.ico") if hasattr(sys, '_MEIPASS') else None,
            ]
            for icon_path in possible_paths:
                if icon_path and os.path.exists(icon_path):
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        break
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 12)
        layout.setSpacing(6)

        # 标题栏
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(6, 0, 0, 0)
        title_bar.setSpacing(8)

        # 左侧：app图标 + 标题
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setStyleSheet("background: transparent;")
        self._load_title_icon()
        title_bar.addWidget(self.icon_label)

        self.title_label = QLabel("运行日志")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 500;")
        title_bar.addWidget(self.title_label)

        title_bar.addStretch()

        # 右侧：Win风格关闭按钮
        self.close_btn_top = QPushButton("✕")
        self.close_btn_top.setFixedSize(46, 32)
        self.close_btn_top.setCursor(QtCompat.PointingHandCursor)
        self.close_btn_top.clicked.connect(self.close)
        title_bar.addWidget(self.close_btn_top)

        layout.addLayout(title_bar)

        # 路径提示
        self.path_label = QLabel(f"{self.log_path}")
        self.path_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.path_label)

        # 日志内容
        self.log_edit = RoundedMenuPlainTextEdit()
        self.log_edit.setReadOnly(True)
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.log_edit.setFont(font)
        layout.addWidget(self.log_edit)

        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 4, 0)
        btn_layout.setSpacing(8)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.setMinimumWidth(70)
        self.refresh_btn.setCursor(QtCompat.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.load_log)
        btn_layout.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.setFixedHeight(30)
        self.clear_btn.setMinimumWidth(80)
        self.clear_btn.setCursor(QtCompat.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_log)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _load_title_icon(self):
        """加载标题栏app图标"""
        try:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            possible_paths = [
                os.path.join(root_dir, "assets", "app.ico"),
                os.path.join(root_dir, "app.ico"),
                os.path.join(sys._MEIPASS, "assets", "app.ico") if hasattr(sys, '_MEIPASS') else None,
            ]
            for icon_path in possible_paths:
                if icon_path and os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        from qt_compat import QSize
                        self.icon_label.setPixmap(pixmap.scaled(
                            QSize(20, 20), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation
                        ))
                        break
        except Exception:
            pass

    def set_theme(self, theme: str):
        """外部切换主题"""
        self._theme = theme
        self._apply_theme()
        # 重新应用模糊效果以更新底色
        if self.isVisible():
            self._apply_blur_effect()

    def _apply_theme(self):
        """应用主题样式 - 与主配置窗口风格统一"""
        theme = self._theme
        self.log_edit.set_theme(theme)

        input_style = Glassmorphism.get_neumorphism_input_style(theme)
        scrollbar_style = StyleSheet.get_scrollbar_style(theme)

        if theme == "dark":
            text_primary = "rgba(255, 255, 255, 0.9)"
            text_secondary = "rgba(255, 255, 255, 0.5)"
        else:
            text_primary = "rgba(28, 28, 30, 0.9)"
            text_secondary = "rgba(60, 60, 67, 0.6)"

        # Win风格关闭按钮样式
        close_top_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: {text_primary};
                font-size: 13px;
                font-weight: 400;
                font-family: 'Segoe MDL2 Assets', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background: #E81123;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background: #C50F1F;
                color: #ffffff;
            }}
        """
        self.close_btn_top.setStyleSheet(close_top_style)

        self.title_label.setStyleSheet(f"""
            font-size: 14px; font-weight: 500;
            color: {text_primary};
            background: transparent;
        """)
        self.path_label.setStyleSheet(f"""
            font-size: 11px;
            color: {text_secondary};
            background: transparent;
            padding-left: 6px;
        """)

        # 日志文本框完全透明
        log_edit_style = f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {text_primary};
            }}
        """
        self.log_edit.setStyleSheet(log_edit_style + scrollbar_style)

        # 窗口样式
        self.setStyleSheet("QDialog { background: transparent; }")

        # 底部按钮样式 - 与主配置窗口底部四按钮一致
        if theme == "dark":
            btn_bg = "rgba(255, 255, 255, 0.12)"
            btn_border = "rgba(255, 255, 255, 0.2)"
            btn_hover = "rgba(10, 132, 255, 0.8)"
            btn_text = "#ffffff"
        else:
            btn_bg = "rgba(0, 0, 0, 0.03)"
            btn_border = "rgba(0, 0, 0, 0.05)"
            btn_hover = "rgba(0, 122, 255, 0.8)"
            btn_text = "#1c1c1e"

        action_btn_style = f"""
            QPushButton {{
                font-size: 11px;
                padding: 6px 4px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 6px;
                color: {btn_text};
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                color: white;
                border: 1px solid {btn_hover};
            }}
        """
        self.refresh_btn.setStyleSheet(action_btn_style)
        self.clear_btn.setStyleSheet(action_btn_style)

    def _apply_blur_effect(self):
        """应用磨砂玻璃模糊效果 - 与主配置窗口相同"""
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return

            effect = get_window_effect()
            radius = 8 if is_win11() else 12

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                enable_acrylic_for_config_window(self, self._theme, blur_amount=10)
            else:
                enable_acrylic_for_config_window(self, self._theme, blur_amount=8, radius=radius)

            self._blur_applied = True
        except Exception:
            pass

    def paintEvent(self, event):
        """绘制圆角半透明背景 - 与主配置窗口一致"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10
        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        radius = 8 if is_win11() else 12
        inset = 1.0 if is_win10() else 0.5

        if self._theme == "dark":
            bg = QColor(28, 28, 30, 180)
            border = QColor(190, 190, 197, 60)
        else:
            bg = QColor(242, 242, 247, 160)
            border = QColor(229, 229, 234, 150)

        path = QPainterPath()
        path.addRoundedRect(
            inset, inset,
            self.width() - inset * 2, self.height() - inset * 2,
            radius, radius
        )

        tint_color = QColor(bg)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 150))
        else:
            tint_color.setAlpha(min(tint_color.alpha(), 100))
        painter.fillPath(path, tint_color)

        pen_color = QColor(border)
        pen_color.setAlpha(min(pen_color.alpha(), 120))
        painter.setPen(QPen(pen_color, 1.0))
        painter.drawPath(path)

    def resizeEvent(self, event):
        """窗口大小变化时更新圆角区域（仅 Win10 需要）"""
        super().resizeEvent(event)
        try:
            if not is_win11() and self._blur_applied:
                hwnd = int(self.winId())
                if hwnd:
                    effect = get_window_effect()
                    w = self.width()
                    h = self.height()
                    radius = 12
                    if w > 0 and h > 0:
                        effect.set_window_region(hwnd, w, h, radius)
                        effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)
        except Exception:
            pass

    def showEvent(self, event):
        """显示时应用模糊效果和启动动画"""
        super().showEvent(event)
        # 每次显示都重新应用模糊效果，确保重启后正常
        from qt_compat import QTimer
        QTimer.singleShot(10, self._apply_blur_effect)
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

    # --- 拖动支持 ---
    def mousePressEvent(self, event):
        if event.button() == QtCompat.LeftButton:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            # 只允许在标题栏区域（顶部36px）拖动
            if pos.y() <= 36:
                self._drag_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            else:
                self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            self.move(self.pos() + new_pos - self._drag_pos)
            self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # --- 日志操作 ---
    def load_log(self):
        """加载日志内容（只读取最后100KB）"""
        if not os.path.exists(self.log_path):
            self.log_edit.setPlainText("日志文件不存在")
            return

        try:
            max_size = 100 * 1024
            file_size = os.path.getsize(self.log_path)

            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                if file_size > max_size:
                    f.seek(max(0, file_size - max_size))
                    f.readline()
                    content = f.read()
                    content = f"... (显示最后 {max_size // 1024}KB)\n\n" + content
                else:
                    content = f.read()

                self.log_edit.setPlainText(content)
                from qt_compat import QTextCursor
                self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
        except Exception as e:
            self.log_edit.setPlainText(f"无法读取日志文件: {e}")

    def clear_log(self):
        """清空日志"""
        confirmed = ThemedMessageBox.question(
            self, "确认清空", "确定要清空所有日志内容吗？"
        )
        if confirmed == ThemedMessageBox.Yes:
            try:
                with open(self.log_path, 'w', encoding='utf-8') as f:
                    f.write("")
                self.load_log()
            except Exception as e:
                ThemedMessageBox.warning(self, "错误", f"无法清空日志: {e}")
