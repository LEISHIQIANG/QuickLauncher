"""
日志查看窗口 - 与主配置窗口风格统一
"""

import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.i18n import tr
from qt_compat import (
    QColor,
    QDialog,
    QFont,
    QHBoxLayout,
    QIcon,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPlainTextEdit,
    QPoint,
    QPushButton,
    Qt,
    QtCompat,
    QVBoxLayout,
)
from ui.styles.style import Glassmorphism, PopupMenu, StyleSheet
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_qfont, tune_font_rendering
from ui.utils.window_effect import (
    enable_acrylic_for_config_window,
    get_window_effect,
    is_win11,
    paint_win10_rounded_surface,
)

logger = logging.getLogger(__name__)


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
        self._full_log_content = ""  # 完整日志内容缓存

        self.setWindowTitle(tr("运行日志"))
        self.resize(700, 500)

        # 无边框 + 透明背景
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
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
                os.path.join(sys._MEIPASS, "assets", "app.ico") if hasattr(sys, "_MEIPASS") else None,
            ]
            for icon_path in possible_paths:
                if icon_path and os.path.exists(icon_path):
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        break
        except Exception as exc:
            logger.debug("加载窗口图标失败: %s", exc, exc_info=True)

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
        self.title_label.setFont(get_qfont(14, 400))
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 400;")
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

        # 底部按钮栏：左侧操作按钮 + 右侧过滤按钮
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

        self.info_filter_btn = QPushButton("INFO (0)")
        self.info_filter_btn.setFixedHeight(30)
        self.info_filter_btn.setMinimumWidth(105)
        self.info_filter_btn.setCursor(QtCompat.PointingHandCursor)
        self.info_filter_btn.setCheckable(True)
        self.info_filter_btn.setChecked(True)
        self.info_filter_btn.clicked.connect(self._apply_filter)
        btn_layout.addWidget(self.info_filter_btn)

        self.debug_filter_btn = QPushButton("DEBUG (0)")
        self.debug_filter_btn.setFixedHeight(30)
        self.debug_filter_btn.setMinimumWidth(105)
        self.debug_filter_btn.setCursor(QtCompat.PointingHandCursor)
        self.debug_filter_btn.setCheckable(True)
        self.debug_filter_btn.setChecked(True)
        self.debug_filter_btn.clicked.connect(self._apply_filter)
        btn_layout.addWidget(self.debug_filter_btn)

        self.error_filter_btn = QPushButton("ERROR (0)")
        self.error_filter_btn.setFixedHeight(30)
        self.error_filter_btn.setMinimumWidth(105)
        self.error_filter_btn.setCursor(QtCompat.PointingHandCursor)
        self.error_filter_btn.setCheckable(True)
        self.error_filter_btn.setChecked(True)
        self.error_filter_btn.clicked.connect(self._apply_filter)
        btn_layout.addWidget(self.error_filter_btn)

        layout.addLayout(btn_layout)

    def _load_title_icon(self):
        """加载标题栏app图标"""
        try:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            possible_paths = [
                os.path.join(root_dir, "assets", "app.ico"),
                os.path.join(root_dir, "app.ico"),
                os.path.join(sys._MEIPASS, "assets", "app.ico") if hasattr(sys, "_MEIPASS") else None,
            ]
            for icon_path in possible_paths:
                if icon_path and os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        from qt_compat import QSize

                        self.icon_label.setPixmap(
                            pixmap.scaled(QSize(20, 20), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                        )
                        break
        except Exception as exc:
            logger.debug("加载标题栏图标失败: %s", exc, exc_info=True)

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

        Glassmorphism.get_neumorphism_input_style(theme)
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
            font-size: 14px; font-weight: 400;
            color: {text_primary};
            background: transparent;
        """)
        self.title_label.setFont(get_qfont(14, 400))
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
        tune_font_rendering(self, recursive=True)
        self.title_label.setFont(get_qfont(14, 400))

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

        # 过滤按钮样式
        self._apply_filter_button_styles(theme)

    def _apply_blur_effect(self):
        """应用磨砂玻璃模糊效果 - 与主配置窗口相同"""
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return

            effect = get_window_effect()
            radius = 8 if is_win11() else 8

            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, radius)
                enable_acrylic_for_config_window(self, self._theme, blur_amount=10)
            else:
                enable_acrylic_for_config_window(self, self._theme, blur_amount=8, radius=radius)

            self._blur_applied = True
        except Exception as exc:
            logger.debug("应用模糊效果失败: %s", exc, exc_info=True)

    def paintEvent(self, event):
        """绘制圆角半透明背景 - 与主配置窗口一致"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10

        if is_win10():
            painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        radius = 8 if is_win11() else 8
        inset = 1.0 if is_win10() else 0.5

        if self._theme == "dark":
            bg = QColor(28, 28, 30, 180)
            border = QColor(190, 190, 197, 60)
        else:
            bg = QColor(242, 242, 247, 160)
            border = QColor(229, 229, 234, 150)

        if is_win10():
            paint_win10_rounded_surface(painter, self, bg, border, radius)
            return

        path = QPainterPath()
        path.addRoundedRect(inset, inset, self.width() - inset * 2, self.height() - inset * 2, radius, radius)

        tint_color = QColor(bg)
        if is_win10():
            tint_color.setAlpha(min(tint_color.alpha(), 220))
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
                        effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
        except Exception as exc:
            logger.debug("更新窗口区域失败: %s", exc, exc_info=True)

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
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            # 只允许在标题栏区域（顶部36px）拖动
            if pos.y() <= 36:
                self._drag_pos = (
                    event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                )
            else:
                self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.move(self.pos() + new_pos - self._drag_pos)
            self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # --- 过滤按钮逻辑 ---
    def _apply_filter_button_styles(self, theme: str):
        """应用过滤按钮的主题样式"""
        is_dark = theme == "dark"

        # INFO 按钮 - 默认主题色
        if is_dark:
            info_bg = "rgba(255, 255, 255, 0.10)"
            info_border = "rgba(255, 255, 255, 0.18)"
            info_text = "rgba(255, 255, 255, 0.85)"
            info_active_bg = "rgba(10, 132, 255, 0.35)"
            info_active_border = "rgba(10, 132, 255, 0.6)"
        else:
            info_bg = "rgba(0, 0, 0, 0.04)"
            info_border = "rgba(0, 0, 0, 0.08)"
            info_text = "rgba(28, 28, 30, 0.85)"
            info_active_bg = "rgba(0, 122, 255, 0.15)"
            info_active_border = "rgba(0, 122, 255, 0.4)"

        self.info_filter_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px; padding: 4px 8px;
                background: {info_bg}; border: 1px solid {info_border};
                border-radius: 5px; color: {info_text};
            }}
            QPushButton:hover {{ background: {info_active_bg}; border: 1px solid {info_active_border}; }}
            QPushButton:checked {{ background: {info_active_bg}; border: 1px solid {info_active_border}; font-weight: 400; }}
        """)

        # DEBUG 按钮 - 淡黄色（柔和）
        if is_dark:
            debug_bg = "rgba(255, 214, 10, 0.05)"
            debug_border = "rgba(255, 214, 10, 0.12)"
            debug_text = "rgba(255, 224, 130, 0.7)"
            debug_active_bg = "rgba(255, 214, 10, 0.15)"
            debug_active_border = "rgba(255, 214, 10, 0.30)"
        else:
            debug_bg = "rgba(180, 150, 0, 0.03)"
            debug_border = "rgba(180, 150, 0, 0.08)"
            debug_text = "rgba(140, 120, 20, 0.75)"
            debug_active_bg = "rgba(255, 214, 10, 0.10)"
            debug_active_border = "rgba(200, 170, 0, 0.22)"

        self.debug_filter_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px; padding: 4px 8px;
                background: {debug_bg}; border: 1px solid {debug_border};
                border-radius: 5px; color: {debug_text};
            }}
            QPushButton:hover {{ background: {debug_active_bg}; border: 1px solid {debug_active_border}; }}
            QPushButton:checked {{ background: {debug_active_bg}; border: 1px solid {debug_active_border}; font-weight: 400; }}
        """)

        # ERROR 按钮 - 淡红色（柔和）
        if is_dark:
            error_bg = "rgba(255, 69, 58, 0.06)"
            error_border = "rgba(255, 69, 58, 0.14)"
            error_text = "rgba(255, 120, 110, 0.7)"
            error_active_bg = "rgba(255, 69, 58, 0.18)"
            error_active_border = "rgba(255, 69, 58, 0.35)"
        else:
            error_bg = "rgba(200, 40, 30, 0.03)"
            error_border = "rgba(200, 40, 30, 0.08)"
            error_text = "rgba(190, 50, 40, 0.75)"
            error_active_bg = "rgba(255, 69, 58, 0.10)"
            error_active_border = "rgba(220, 50, 40, 0.22)"

        self.error_filter_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px; padding: 4px 8px;
                background: {error_bg}; border: 1px solid {error_border};
                border-radius: 5px; color: {error_text};
            }}
            QPushButton:hover {{ background: {error_active_bg}; border: 1px solid {error_active_border}; }}
            QPushButton:checked {{ background: {error_active_bg}; border: 1px solid {error_active_border}; font-weight: 400; }}
        """)

    def _count_log_levels(self, content: str):
        """统计日志中各级别的条数"""
        # 匹配常见日志格式中的级别关键字
        info_count = len(re.findall(r"\bINFO\b", content))
        debug_count = len(re.findall(r"\bDEBUG\b", content))
        error_count = len(re.findall(r"\bERROR\b", content))
        return info_count, debug_count, error_count

    def _update_filter_button_labels(self, content: str):
        """更新过滤按钮上的计数"""
        info_c, debug_c, error_c = self._count_log_levels(content)
        self.info_filter_btn.setText(f"INFO ({info_c})")
        self.debug_filter_btn.setText(f"DEBUG ({debug_c})")
        self.error_filter_btn.setText(f"ERROR ({error_c})")

    def _apply_filter(self):
        """根据按钮选中状态过滤日志内容，未选中的级别会被隐藏"""
        content = self._full_log_content
        if not content:
            return

        show_info = self.info_filter_btn.isChecked()
        show_debug = self.debug_filter_btn.isChecked()
        show_error = self.error_filter_btn.isChecked()

        if show_info and show_debug and show_error:
            # 全部选中，显示完整内容
            self.log_edit.setPlainText(content)
        else:
            # 排除未选中的级别
            hidden_levels = []
            if not show_info:
                hidden_levels.append("INFO")
            if not show_debug:
                hidden_levels.append("DEBUG")
            if not show_error:
                hidden_levels.append("ERROR")

            lines = content.splitlines()
            filtered = [line for line in lines if not any(lv in line for lv in hidden_levels)]
            if filtered:
                self.log_edit.setPlainText("\n".join(filtered))
            else:
                self.log_edit.setPlainText("所有日志条目均已被过滤")

        from qt_compat import QTextCursor

        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    # --- 日志操作 ---
    def load_log(self):
        """加载日志内容（只读取最后100KB）"""
        if not os.path.exists(self.log_path):
            self._full_log_content = ""
            self.log_edit.setPlainText("日志文件不存在")
            self._update_filter_button_labels("")
            return

        try:
            max_size = 100 * 1024
            file_size = os.path.getsize(self.log_path)

            with open(self.log_path, encoding="utf-8", errors="ignore") as f:
                if file_size > max_size:
                    f.seek(max(0, file_size - max_size))
                    f.readline()
                    content = f.read()
                    content = f"... (显示最后 {max_size // 1024}KB)\n\n" + content
                else:
                    content = f.read()

                self._full_log_content = content
                self._update_filter_button_labels(content)
                self._apply_filter()
        except Exception as e:
            self._full_log_content = ""
            self.log_edit.setPlainText(f"无法读取日志文件: {e}")
            self._update_filter_button_labels("")

    def clear_log(self):
        """清空日志"""
        confirmed = ThemedMessageBox.question(self, tr("确认清空"), tr("确定要清空所有日志内容吗？"))
        if confirmed == ThemedMessageBox.Yes:
            try:
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.write("")
                self.info_filter_btn.setChecked(True)
                self.debug_filter_btn.setChecked(True)
                self.error_filter_btn.setChecked(True)
                self.load_log()
            except Exception as e:
                ThemedMessageBox.warning(self, tr("错误"), tr("无法清空日志: {error}", error=e))
