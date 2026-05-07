"""Appearance settings page builder."""

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

class SettingsAppearancePageMixin:
    def _setup_appearance_page(self, page):
        # 弹窗背景 (置顶)
        layout, group = page.add_group("弹窗背景")
        
        # 模式选择
        mode_layout = QHBoxLayout()
        self.bg_mode_group = QButtonGroup(self)
        self.bg_theme_radio = QRadioButton("跟随主题")
        self.bg_image_radio = QRadioButton("图片背景")
        self.bg_acrylic_radio = QRadioButton("亚克力背景")
        
        self.bg_mode_group.addButton(self.bg_theme_radio, 0)
        self.bg_mode_group.addButton(self.bg_image_radio, 1)
        self.bg_mode_group.addButton(self.bg_acrylic_radio, 2)
        self.bg_mode_group.buttonClicked.connect(self._on_bg_mode_changed)
        
        mode_layout.addWidget(self.bg_theme_radio)
        mode_layout.addWidget(self.bg_image_radio)
        mode_layout.addWidget(self.bg_acrylic_radio)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 图片选择器
        self.bg_image_widget = QWidget()
        img_layout = QHBoxLayout(self.bg_image_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)
        self.bg_path_edit = QLineEdit()
        self.bg_path_edit.setReadOnly(True)
        self.bg_path_edit.setPlaceholderText("选择背景图片...")
        self.bg_browse_btn = QPushButton("浏览...")
        self.bg_browse_btn.clicked.connect(self._browse_bg_image)
        img_layout.addWidget(self.bg_path_edit)
        img_layout.addWidget(self.bg_browse_btn)
        layout.addWidget(self.bg_image_widget)



        # 尺寸布局
        layout, group = page.add_group("尺寸布局")
        grid = QGridLayout()
        grid.setVerticalSpacing(8) # 减小行间距
        
        # Row 1
        grid.addWidget(self._create_label("图标大小"), 0, 0)
        self.icon_size_spin = self._create_spinbox(16, 64, "px")
        self.icon_size_spin.valueChanged.connect(self._on_size_changed)
        grid.addWidget(self.icon_size_spin, 0, 1)
        
        grid.addWidget(self._create_label("格子大小"), 0, 2)
        self.cell_size_spin = self._create_spinbox(32, 80, "px")
        self.cell_size_spin.valueChanged.connect(self._on_size_changed)
        grid.addWidget(self.cell_size_spin, 0, 3)
        
        grid.addWidget(self._create_label("每行列数"), 0, 4)
        self.cols_spin = self._create_spinbox(3, 12, "列")
        self.cols_spin.valueChanged.connect(self._on_size_changed)
        grid.addWidget(self.cols_spin, 0, 5)
        
        # Row 2
        grid.addWidget(self._create_label("窗口圆角"), 1, 0)
        self.corner_spin = self._create_spinbox(0, 20, "px")
        self.corner_spin.valueChanged.connect(self._on_size_changed)
        grid.addWidget(self.corner_spin, 1, 1)
        
        grid.addWidget(self._create_label("Dock高度"), 1, 2)
        self.dock_height_spin = self._create_spinbox(0, 3, "行")
        self.dock_height_spin.setSpecialValueText("隐藏")
        self.dock_height_spin.valueChanged.connect(self._on_dock_size_changed)
        grid.addWidget(self.dock_height_spin, 1, 3)

        grid.addWidget(self._create_label("每列行数"), 1, 4)
        self.popup_max_rows_spin = self._create_spinbox(1, 10, "行")
        self.popup_max_rows_spin.valueChanged.connect(self._on_size_changed)
        grid.addWidget(self.popup_max_rows_spin, 1, 5)
        
        layout.addLayout(grid)
        
        # 透明度
        layout, group = page.add_group("透明度")
        
        grid_alpha = QGridLayout()
        grid_alpha.setVerticalSpacing(8)
        
        # 背景透明度
        grid_alpha.addWidget(self._create_label("背景不透明度"), 0, 0)
        self.bg_alpha_slider = QSlider(QtCompat.Horizontal)
        self.bg_alpha_slider.setRange(1, 100)
        self.bg_alpha_slider.valueChanged.connect(self._on_bg_alpha_changed)
        grid_alpha.addWidget(self.bg_alpha_slider, 0, 1)
        self.bg_alpha_label = QLabel("90%")
        self.bg_alpha_label.setMinimumWidth(40)
        grid_alpha.addWidget(self.bg_alpha_label, 0, 2)
        
        # 图标透明度
        grid_alpha.addWidget(self._create_label("图标不透明度"), 1, 0)
        self.icon_alpha_slider = QSlider(QtCompat.Horizontal)
        self.icon_alpha_slider.setRange(1, 100)
        self.icon_alpha_slider.valueChanged.connect(self._on_icon_alpha_changed)
        grid_alpha.addWidget(self.icon_alpha_slider, 1, 1)
        self.icon_alpha_label = QLabel("100%")
        self.icon_alpha_label.setMinimumWidth(40)
        grid_alpha.addWidget(self.icon_alpha_label, 1, 2)
        
        # Dock透明度
        grid_alpha.addWidget(self._create_label("Dock不透明度"), 2, 0)
        self.dock_bg_alpha_slider = QSlider(QtCompat.Horizontal)
        self.dock_bg_alpha_slider.setRange(1, 100)
        self.dock_bg_alpha_slider.valueChanged.connect(self._on_dock_bg_alpha_changed)
        grid_alpha.addWidget(self.dock_bg_alpha_slider, 2, 1)
        self.dock_bg_alpha_label = QLabel("90%")
        self.dock_bg_alpha_label.setMinimumWidth(40)
        grid_alpha.addWidget(self.dock_bg_alpha_label, 2, 2)
        
        layout.addLayout(grid_alpha)
        
        # 视觉特效 (模糊/阴影/高光)
        layout, self.visual_effect_group = page.add_group("视觉特效")
        
        grid_effect = QGridLayout()
        grid_effect.setVerticalSpacing(8)
        
        # 模糊度 (原模糊半径)
        grid_effect.addWidget(self._create_label("模糊度"), 0, 0)
        
        self.blur_radius_slider = QSlider(QtCompat.Horizontal)
        self.blur_radius_slider.setRange(0, 100)
        self.blur_radius_slider.valueChanged.connect(self._on_blur_radius_changed)
        grid_effect.addWidget(self.blur_radius_slider, 0, 1)
        
        self.blur_radius_label = QLabel("0")
        grid_effect.addWidget(self.blur_radius_label, 0, 2)
        
        # 边缘高光
        grid_effect.addWidget(self._create_label("边缘高光"), 1, 0)
        
        self.edge_opacity_slider = QSlider(QtCompat.Horizontal)
        self.edge_opacity_slider.setRange(0, 100)
        self.edge_opacity_slider.valueChanged.connect(self._on_edge_opacity_changed)
        grid_effect.addWidget(self.edge_opacity_slider, 1, 1)
        
        self.edge_opacity_label = QLabel("0%")
        self.edge_opacity_label.setMinimumWidth(40)
        grid_effect.addWidget(self.edge_opacity_label, 1, 2)
        
        layout.addLayout(grid_effect)
