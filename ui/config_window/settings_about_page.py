"""About settings page builder."""

import os
import sys
import shutil
import time
import winreg

from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QFormLayout, QSlider, QSpinBox, QRadioButton, QButtonGroup,
    QLabel, QFrame, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QScrollArea, QMessageBox,
    QPainter, QPixmap, QColor, QPen, QBrush, QRect, QRectF, QDialog,
    QTimer, QIcon, QStackedWidget, Qt, QtCompat, pyqtSignal, PYQT_VERSION,
    QThread, QStyledItemDelegate, QSize, QKeySequence, QMenu, QAction,
    QComboBox, QPainterPath, exec_dialog, QPoint, QApplication
)
from core import APP_VERSION, DEFAULT_SPECIAL_APPS, ShortcutItem, ShortcutType
from core.app_scanner import AppScanner
from ui.config_window.settings_helpers import NumberedListDelegate, ProgressDialog, ExportThread, ImportThread
from ui.config_window.folder_panel import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_font_css_with_size

class SettingsAboutPageMixin:
    def _setup_about_page(self, page):
        # 软件信息
        layout, group = page.add_group("关于 QuickLauncher")

        # 图标和标题
        header_layout = QHBoxLayout()
        
        # 尝试加载图标
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            # 优先查找 assets 目录
            icon_path = os.path.join(base_dir, "assets", "app.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_dir, "app.ico")
                
            if os.path.exists(icon_path):
                icon_label = QLabel()
                icon_label.setFixedSize(64, 64)
                pixmap = QIcon(icon_path).pixmap(64, 64)
                if pixmap and not pixmap.isNull():
                    icon_label.setPixmap(pixmap.scaled(64, 64, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation))
                    header_layout.addWidget(icon_label)
        except:
            pass
            
        title_layout = QVBoxLayout()
        title = QLabel("QuickLauncher")
        title.setStyleSheet(f"{get_font_css_with_size(24, 600)}")
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet(f"{get_font_css_with_size(14, 400)} color: #b0b0b5;")
        title_layout.addWidget(title)
        title_layout.addWidget(version)
        title_layout.addStretch()
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 软件简介
        layout, group = page.add_group("软件简介")
        intro_text = QLabel(
            "QuickLauncher 是一款轻量级的鼠标中键快速启动工具。\n"
            "在任意位置按下鼠标中键，即可呼出应用弹窗，快速启动常用程序、打开文件夹、访问网址等。"
        )
        intro_text.setWordWrap(True)
        intro_text.setStyleSheet("QLabel { line-height: 1.5; }")
        layout.addWidget(intro_text)

        # 基本操作
        layout, group = page.add_group("一、基本操作")
        feature1_text = QLabel(
            "1. 呼出弹窗\n"
            "   • 在任意位置按下鼠标中键（滚轮按下），弹窗会在鼠标位置附近显示\n"
            "   • 可在任何软件界面使用，包括桌面、浏览器、办公软件等\n\n"

            "2. 隐藏弹窗\n"
            "   • 再次按下鼠标中键\n"
            "   • 点击弹窗外部的任意区域\n"
            "   • 按下 Esc 键\n"
            "   • 启动应用后自动隐藏（可在设置中关闭）\n\n"

            "3. 临时禁用/启用中键弹窗\n"
            "   • 双击 Alt 键可临时禁用或启用中键弹窗功能\n"
            "   • 禁用后鼠标中键不会触发弹窗，方便在特定场景下使用\n"
            "   • 再次双击 Alt 键即可恢复\n\n"

            "4. 锁定弹窗\n"
            "   • 右键点击弹窗任意空白区域\n"
            "   • 或点击弹窗右上角的图钉图标\n"
            "   • 锁定后弹窗不会因失去焦点而自动隐藏，方便连续操作\n\n"

            "5. 翻页切换\n"
            "   • 鼠标滚轮上下滚动\n"
            "   • 键盘方向键 ← 和 →\n"
            "   • 弹窗底部会显示当前页码和总页数"
        )
        feature1_text.setWordWrap(True)
        feature1_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature1_text)

        # 添加应用
        layout, group = page.add_group("二、添加应用")
        feature2_text = QLabel(
            "1. 拖拽添加（推荐）\n"
            "   • 将 exe 程序、文件夹、快捷方式直接拖入弹窗的空白格子\n"
            "   • 支持从桌面、文件资源管理器、开始菜单拖拽\n"
            "   • 可同时拖拽多个文件，会依次添加到空白格子中\n\n"

            "2. 点击添加\n"
            "   • 点击弹窗中的空白格子\n"
            "   • 在弹出的文件选择对话框中选择要添加的文件\n"
            "   • 支持选择 exe 程序、文件夹、任意文件类型\n\n"

            "3. 支持的类型\n"
            "   • 应用程序：exe 可执行文件\n"
            "   • 文件夹：快速打开常用目录\n"
            "   • 文件：文档、图片、视频等任意文件\n"
            "   • 打开网址：在编辑对话框中输入 http:// 或 https:// 开头的网址\n"
            "   • 运行命令：在编辑对话框中输入系统命令或脚本路径"
        )
        feature2_text.setWordWrap(True)
        feature2_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature2_text)

        # 图标管理
        layout, group = page.add_group("三、图标管理")
        feature3_text = QLabel(
            "1. 编辑图标\n"
            "   • 右键点击图标 → 选择「编辑」\n"
            "   • 可修改显示名称、图标图片、目标路径、启动参数\n"
            "   • 可设置管理员权限运行、最小化启动等选项\n\n"

            "2. 删除图标\n"
            "   • 右键点击图标 → 选择「删除」\n"
            "   • 确认后即可移除该图标\n\n"

            "3. 调整顺序\n"
            "   • 长按鼠标左键拖动图标到目标位置\n"
            "   • 可在同一页内调整，也可拖到其他页面\n"
            "   • 松开鼠标即可完成位置调整\n\n"

            "4. 其他操作\n"
            "   • 打开所在位置：右键图标 → 选择「打开所在位置」\n"
            "   • 复制路径：右键图标 → 选择「复制路径」"
        )
        feature3_text.setWordWrap(True)
        feature3_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature3_text)

        # 高级功能
        layout, group = page.add_group("四、高级功能")
        feature4_text = QLabel(
            "1. 强制启动新进程\n"
            "   • 按住 Alt 键 + 左键点击图标\n"
            "   • 即使程序已经运行，也会强制启动一个新的进程窗口\n\n"

            "2. 拖放文件到图标\n"
            "   • 将文件拖到程序图标上松开鼠标\n"
            "   • 会用该程序打开拖入的文件\n"
            "   • 例如：将图片拖到 Photoshop 图标上，用 PS 打开图片\n\n"

            "3. 透明度调节\n"
            "   • Ctrl + 鼠标滚轮：调节弹窗背景透明度\n"
            "   • Shift + 鼠标滚轮：调节图标透明度\n"
            "   • 可在「弹窗外观」设置中精确调整数值\n\n"

            "4. 特殊触发（Ctrl + 中键）\n"
            "   • 按住 Ctrl 键 + 鼠标中键：触发特殊应用列表\n"
            "   • 可在「弹窗交互」设置中配置特殊触发的应用\n"
            "   • 适合设置常用但不想占用主弹窗空间的应用"
        )
        feature4_text.setWordWrap(True)
        feature4_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature4_text)

        # 配置管理
        layout, group = page.add_group("五、配置管理")
        feature5_text = QLabel(
            "1. 导出配置\n"
            "   • 在「配置管理」页面点击「导出配置」\n"
            "   • 会导出所有图标、设置、分类信息到 JSON 文件\n"
            "   • 可用于备份或迁移到其他电脑\n\n"

            "2. 导入配置\n"
            "   • 在「配置管理」页面点击「导入配置」\n"
            "   • 选择之前导出的 JSON 配置文件\n"
            "   • 会覆盖当前所有配置，请谨慎操作\n\n"

            "3. 分享配置\n"
            "   • 导出分享配置：仅导出快捷键、打开网址、运行命令类型的图标\n"
            "   • 导入分享配置：导入后会自动创建「导入图标」分类\n"
            "   • 适合与他人分享配置，不包含本地程序路径"
        )
        feature5_text.setWordWrap(True)
        feature5_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature5_text)

        # 使用技巧
        layout, group = page.add_group("六、使用技巧")
        feature6_text = QLabel(
            "1. 游戏防误触\n"
            "   • 在「弹窗交互」设置中添加游戏进程名（如 game.exe）\n"
            "   • 当游戏运行时，中键不会触发弹窗，避免游戏中误操作\n\n"

            "2. 自定义弹窗外观\n"
            "   • 在「弹窗外观」中调整图标大小、每行列数、圆角等\n"
            "   • 在「系统设置」中切换明暗主题\n"
            "   • 可根据个人喜好打造专属界面\n\n"

            "3. 开机自启动\n"
            "   • 在「系统设置」中勾选「开机自启动」\n"
            "   • 软件会在系统启动后自动运行，无需手动打开\n\n"

            "4. 弹窗位置设置\n"
            "   • 在「弹窗交互」中选择弹窗显示位置\n"
            "   • 鼠标-弹窗中心：弹窗中心对齐鼠标位置\n"
            "   • 鼠标-弹窗左上角：弹窗左上角对齐鼠标位置"
        )
        feature6_text.setWordWrap(True)
        feature6_text.setStyleSheet("QLabel { line-height: 1.6; }")
        layout.addWidget(feature6_text)
        
        # 作者信息
        layout, group = page.add_group("作者信息")
        author_label = QLabel("开发者: NAYTON")
        layout.addWidget(author_label)
