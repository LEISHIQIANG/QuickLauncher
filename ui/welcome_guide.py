"""
新手引导窗口 - 首次启动交互式教程
"""

import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    Qt, QtCompat, PYQT_VERSION, QPainter, QColor, QPainterPath, QPen, QPixmap, QPoint, QTimer, QCheckBox
)
from ui.utils.window_effect import is_win11, get_window_effect, enable_acrylic_for_config_window, is_win10
from ui.styles.style import Glassmorphism
from ui.utils.dialog_helper import center_dialog_on_main_window

logger = logging.getLogger(__name__)


class WelcomeGuide(QDialog):
    """新手引导对话框"""

    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 QuickLauncher")
        self.setModal(True)
        self._theme = theme
        self.corner_radius = 8 if is_win11() else 12
        self.current_step = 0
        self._shadow_applied = False

        self.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Window)
        self.setAttribute(QtCompat.WA_TranslucentBackground, True)
        self.setWindowOpacity(0)

        self.resize(500, 350)

        self.steps = [
            {
                "title": "欢迎使用 QuickLauncher！",
                "content": "QuickLauncher v2.6.7.7\n轻量级快捷启动工具\n\n• 鼠标中键快速唤出启动面板\n• 支持文件、文件夹、打开网址、快捷键、运行命令\n• 自定义主题和透明度\n\n让我们开始 30 秒快速上手教程",
                "icon": "🚀"
            },
            {
                "title": "第一步：添加快捷方式",
                "content": "在设置窗口中，有三种方式添加快捷方式：\n\n1. 直接拖拽文件/文件夹到中间区域\n2. 点击底部按钮添加（快捷方式/打开网址/快捷键/运行命令）\n3. 双击图标可以编辑\n\n提示：支持拖入 .lnk 快捷方式文件",
                "icon": "📁"
            },
            {
                "title": "第二步：使用启动器",
                "content": "配置完成后，随时可以唤出启动器：\n\n• 默认：鼠标中键\n• 特殊软件：Ctrl + 中键（避免冲突）\n• 锁定：右键空白处锁定窗口\n• 强制新开：Alt + 左键点击图标",
                "icon": "🖱️"
            },
            {
                "title": "第三步：个性化设置",
                "content": "在右侧设置面板可以自定义：\n\n• 主题：深色/浅色\n• 透明度：背景、Dock、图标\n• 尺寸：图标大小、列数、圆角\n• 背景：纯色/图片/主题色\n\n滚轮可快速调节透明度（Ctrl/Shift+滚轮）",
                "icon": "🎨"
            },
            {
                "title": "开始使用！",
                "content": "现在你已经掌握了基本用法\n\n更多功能：\n• Dock 栏：顶部/底部常驻图标\n• 拖放联动：拖文件到图标上打开\n• 分类管理：左侧创建多个分类\n\n祝你使用愉快！",
                "icon": "✨"
            }
        ]

        self._setup_ui()
        self._apply_theme(theme)
        self._update_content()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 图标和标题
        header_layout = QHBoxLayout()
        self.icon_label = QLabel("🚀")
        self.icon_label.setStyleSheet("font-size: 48px;")
        header_layout.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 500;")
        self.title_label.setWordWrap(True)
        header_layout.addWidget(self.title_label, 1)
        layout.addLayout(header_layout)

        # 内容
        self.content_label = QLabel()
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        self.content_label.setMinimumHeight(150)
        layout.addWidget(self.content_label, 1)

        # 进度指示
        self.progress_label = QLabel("1 / 5")
        self.progress_label.setAlignment(QtCompat.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.progress_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        # 左下角：不再显示复选框
        self.dont_show_cb = QCheckBox("不再显示")
        self.dont_show_cb.setStyleSheet("font-size: 12px;")
        btn_layout.addWidget(self.dont_show_cb)

        btn_layout.addStretch()

        self.skip_btn = QPushButton("跳过")
        self.skip_btn.setFixedSize(80, 32)
        self.skip_btn.clicked.connect(lambda: logger.info("skip_btn clicked") or self.reject())
        btn_layout.addWidget(self.skip_btn)

        self.prev_btn = QPushButton("上一步")
        self.prev_btn.setFixedSize(80, 32)
        self.prev_btn.clicked.connect(lambda: logger.info("prev_btn clicked") or self._prev_step())
        self.prev_btn.setEnabled(False)
        btn_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("下一步")
        self.next_btn.setFixedSize(90, 32)
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(lambda: logger.info("next_btn clicked") or self._next_step())
        btn_layout.addWidget(self.next_btn)

        layout.addLayout(btn_layout)

    def _apply_theme(self, theme: str):
        self.theme = theme
        if theme == "dark":
            self.bg_color = QColor(28, 28, 30, 180)
            self.border_color = QColor(190, 190, 197, 60)
        else:
            self.bg_color = QColor(242, 242, 247, 160)
            self.border_color = QColor(229, 229, 234, 150)

        # 使用 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        btn_style = Glassmorphism.get_flat_action_button_style(theme)

        self.setStyleSheet(base_style + """
            QDialog { background: transparent; }
        """)

        for btn in [self.skip_btn, self.prev_btn, self.next_btn]:
            btn.setStyleSheet(btn_style)

    def _update_content(self):
        step = self.steps[self.current_step]
        logger.info(f"_update_content: step={self.current_step}, title={step['title']}")

        self.icon_label.setText(step["icon"])
        self.title_label.setText(step["title"])
        self.content_label.setText(step["content"])
        self.progress_label.setText(f"{self.current_step + 1} / {len(self.steps)}")

        self.prev_btn.setEnabled(self.current_step > 0)

        if self.current_step == len(self.steps) - 1:
            self.next_btn.setText("开始使用")
        else:
            self.next_btn.setText("下一步")

    def _next_step(self):
        logger.info(f"_next_step called, current_step={self.current_step}")
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self._update_content()
        else:
            self.accept()

    def _prev_step(self):
        logger.info(f"_prev_step called, current_step={self.current_step}")
        if self.current_step > 0:
            self.current_step -= 1
            self._update_content()

    def should_show_again(self):
        """返回是否应该再次显示欢迎页面"""
        return not self.dont_show_cb.isChecked()

    def mousePressEvent(self, event):
        """鼠标按下事件 - 添加调试"""
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        logger.info(f"WelcomeGuide mousePressEvent at ({pos.x()}, {pos.y()})")
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """背景绘制 - 与主配置窗口一致的 alpha 处理"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)

        from ui.utils.window_effect import is_win10
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

        # 磨砂玻璃模式 - 与主配置窗口一致的 alpha 处理
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

    def showEvent(self, event):
        """显示时启动动画"""
        super().showEvent(event)
        center_dialog_on_main_window(self)

        if not self._shadow_applied:
            self._shadow_applied = True
            QTimer.singleShot(100, self._apply_effects)
            QTimer.singleShot(50, self._start_show_animation)

    def _apply_effects(self):
        """应用窗口特效 - 圆角 + 磨砂玻璃"""
        try:
            hwnd = int(self.winId())
            effect = get_window_effect()
            if is_win11():
                effect.set_round_corners(hwnd, enable=True)
                effect.enable_window_shadow(hwnd, self.corner_radius)
            else:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, self.corner_radius)
            enable_acrylic_for_config_window(self, self.theme, blur_amount=10)
            logger.info("Window effects applied successfully")
        except Exception as e:
            logger.error(f"Failed to apply window effects: {e}")

    def _start_show_animation(self):
        """窗口出现动画 (0.2s)"""
        logger.info("Starting show animation")
        pos = self.pos()
        anim = QtCompat.QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
        anim.setEndValue(pos)
        anim.setEasingCurve(QtCompat.OutCubic)
        anim.finished.connect(lambda: logger.info("Animation finished"))
        anim.finished.connect(lambda: anim.deleteLater())
        anim.start()
        logger.info(f"Animation started, moving from {pos.y() + 20} to {pos.y()}")
