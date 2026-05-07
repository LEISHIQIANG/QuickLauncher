"""System settings page builder."""

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

class SettingsSystemPageMixin:
    def _setup_system_page(self, page):
        # 启动
        layout, group = page.add_group("启动与运行")
        
        self.auto_start_cb = QCheckBox("开机自动启动")
        self.auto_start_cb.setTristate(False)
        self.auto_start_cb.stateChanged.connect(self._on_auto_start_changed)
        
        layout.addWidget(self.auto_start_cb)
        
        self.show_on_startup_cb = QCheckBox("启动时显示设置窗口")
        self.show_on_startup_cb.stateChanged.connect(self._on_startup_show_changed)
        layout.addWidget(self.show_on_startup_cb)
        
        self.hw_accel_cb = QCheckBox("启用硬件加速 (性能优先)")
        install_tooltip(self.hw_accel_cb, "开启后将提高进程优先级并优化资源调度，可能会增加系统资源占用")
        self.hw_accel_cb.stateChanged.connect(self._on_hw_accel_changed)
        layout.addWidget(self.hw_accel_cb)

        self.hide_tray_cb = QCheckBox("隐藏托盘图标")
        install_tooltip(self.hide_tray_cb, "隐藏后可通过内置命令'配置窗口'唤出设置面板")
        self.hide_tray_cb.stateChanged.connect(self._on_hide_tray_changed)
        layout.addWidget(self.hide_tray_cb)

        self.disable_logging_cb = QCheckBox("关闭日志")
        install_tooltip(self.disable_logging_cb, "停止记录日志到error.log，减少硬盘写入（配置信息仍会保存）")
        self.disable_logging_cb.stateChanged.connect(self._on_disable_logging_changed)
        layout.addWidget(self.disable_logging_cb)

        self.debug_log_cb = QCheckBox("开启DEBUG日志")
        install_tooltip(self.debug_log_cb, "开启后将记录详细的调试信息，用于问题排查")
        self.debug_log_cb.stateChanged.connect(self._on_debug_log_changed)
        layout.addWidget(self.debug_log_cb)

        # 主题
        layout, group = page.add_group("主题风格")
        theme_layout = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        self.follow_system_radio = QRadioButton("跟随系统")
        self.dark_radio = QRadioButton("深色模式")
        self.light_radio = QRadioButton("浅色模式")
        self.theme_group.addButton(self.follow_system_radio, 0)
        self.theme_group.addButton(self.dark_radio, 1)
        self.theme_group.addButton(self.light_radio, 2)
        self.theme_group.buttonClicked.connect(self._on_theme_changed)
        theme_layout.addWidget(self.follow_system_radio)
        theme_layout.addWidget(self.dark_radio)
        theme_layout.addWidget(self.light_radio)
        theme_layout.addStretch()
        layout.addLayout(theme_layout)
