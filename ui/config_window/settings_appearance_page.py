"""Appearance settings page builder and event handlers."""

import logging

from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QtCompat,
    QWidget,
)
from ui.utils.safe_file_dialog import get_open_file_name
from ui.utils.ui_scale import sp

logger = logging.getLogger(__name__)


class SettingsAppearancePageMixin:
    def _setup_appearance_page(self, page):
        # 弹窗背景 (置顶)
        layout, group = page.add_group("弹窗背景")

        # 模式选择
        mode_layout = QHBoxLayout()
        self.bg_mode_group = QButtonGroup(self)
        self.bg_theme_radio = QRadioButton(tr("跟随主题"))
        self.bg_image_radio = QRadioButton(tr("图片背景"))
        self.bg_acrylic_radio = QRadioButton(tr("亚克力背景"))

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
        self.bg_path_edit.setPlaceholderText(tr("选择背景图片..."))
        self.bg_browse_btn = QPushButton(tr("浏览..."))
        self.bg_browse_btn.clicked.connect(self._browse_bg_image)
        img_layout.addWidget(self.bg_path_edit)
        img_layout.addWidget(self.bg_browse_btn)
        layout.addWidget(self.bg_image_widget)

        # 尺寸布局
        layout, group = page.add_group("尺寸布局")

        grid = QGridLayout()
        grid.setVerticalSpacing(sp(8))  # 减小行间距

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
        self.dock_height_spin.setSpecialValueText(tr("隐藏"))
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
        grid_alpha.setVerticalSpacing(sp(8))

        # 背景透明度
        grid_alpha.addWidget(self._create_label("背景不透明度"), 0, 0)
        self.bg_alpha_slider = QSlider(QtCompat.Horizontal)
        self.bg_alpha_slider.setRange(1, 100)
        self.bg_alpha_slider.valueChanged.connect(self._on_bg_alpha_changed)
        grid_alpha.addWidget(self.bg_alpha_slider, 0, 1)
        self.bg_alpha_label = QLabel("90%")
        self.bg_alpha_label.setMinimumWidth(sp(40))
        grid_alpha.addWidget(self.bg_alpha_label, 0, 2)

        # 图标透明度
        grid_alpha.addWidget(self._create_label("图标不透明度"), 1, 0)
        self.icon_alpha_slider = QSlider(QtCompat.Horizontal)
        self.icon_alpha_slider.setRange(1, 100)
        self.icon_alpha_slider.valueChanged.connect(self._on_icon_alpha_changed)
        grid_alpha.addWidget(self.icon_alpha_slider, 1, 1)
        self.icon_alpha_label = QLabel("100%")
        self.icon_alpha_label.setMinimumWidth(sp(40))
        grid_alpha.addWidget(self.icon_alpha_label, 1, 2)

        # Dock透明度
        grid_alpha.addWidget(self._create_label("Dock不透明度"), 2, 0)
        self.dock_bg_alpha_slider = QSlider(QtCompat.Horizontal)
        self.dock_bg_alpha_slider.setRange(1, 100)
        self.dock_bg_alpha_slider.valueChanged.connect(self._on_dock_bg_alpha_changed)
        grid_alpha.addWidget(self.dock_bg_alpha_slider, 2, 1)
        self.dock_bg_alpha_label = QLabel("90%")
        self.dock_bg_alpha_label.setMinimumWidth(sp(40))
        grid_alpha.addWidget(self.dock_bg_alpha_label, 2, 2)

        layout.addLayout(grid_alpha)

        # 视觉特效 (模糊/阴影/高光)
        layout, self.visual_effect_group = page.add_group("视觉特效")

        grid_effect = QGridLayout()
        grid_effect.setVerticalSpacing(sp(8))

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
        self.edge_opacity_label.setMinimumWidth(sp(40))
        grid_effect.addWidget(self.edge_opacity_label, 1, 2)

        layout.addLayout(grid_effect)

    # === Settings Load ===

    def _load_appearance_settings(self, settings):
        self.icon_size_spin.setValue(settings.icon_size)
        self.cell_size_spin.setValue(settings.cell_size)
        self.cols_spin.setValue(settings.cols)
        self.corner_spin.setValue(settings.corner_radius)

        if not settings.dock_enabled:
            self.dock_height_spin.setValue(0)
        else:
            self.dock_height_spin.setValue(settings.dock_height_mode)

        self.popup_max_rows_spin.setValue(getattr(settings, "popup_max_rows", 3))

        self.bg_alpha_slider.setValue(settings.bg_alpha)
        self.bg_alpha_label.setText(f"{settings.bg_alpha}%")
        self.dock_bg_alpha_slider.setValue(settings.dock_bg_alpha)
        self.dock_bg_alpha_label.setText(f"{settings.dock_bg_alpha}%")
        self.icon_alpha_slider.setValue(int(settings.icon_alpha * 100))
        self.icon_alpha_label.setText(f"{int(settings.icon_alpha * 100)}%")

        self.bg_path_edit.setText(settings.custom_bg_path)

        self.blur_radius_slider.setValue(settings.bg_blur_radius)
        self.blur_radius_label.setText(str(settings.bg_blur_radius))

        self.edge_opacity_slider.setValue(int(settings.edge_highlight_opacity * 100))
        self.edge_opacity_label.setText(f"{int(settings.edge_highlight_opacity * 100)}%")

        current_alpha = settings.bg_alpha
        current_blur = settings.bg_blur_radius
        current_edge = settings.edge_highlight_opacity

        if settings.bg_mode == "theme":
            self.bg_theme_radio.setChecked(True)
            self.bg_image_widget.setVisible(False)
            current_alpha = getattr(settings, "theme_bg_alpha", 90)
            current_blur = getattr(settings, "theme_blur_radius", 0)
            current_edge = getattr(settings, "theme_edge_opacity", 0.0)
        elif settings.bg_mode == "image":
            self.bg_image_radio.setChecked(True)
            self.bg_image_widget.setVisible(True)
            current_alpha = getattr(settings, "image_bg_alpha", 90)
            current_blur = getattr(settings, "image_blur_radius", 0)
            current_edge = getattr(settings, "image_edge_opacity", 0.0)
        elif settings.bg_mode == "acrylic":
            self.bg_acrylic_radio.setChecked(True)
            self.bg_image_widget.setVisible(False)
            current_alpha = getattr(settings, "acrylic_bg_alpha", 90)
            current_blur = getattr(settings, "acrylic_blur_radius", 0)
            current_edge = getattr(settings, "acrylic_edge_opacity", 0.0)

        self.bg_alpha_slider.blockSignals(True)
        self.bg_alpha_slider.setValue(current_alpha)
        self.bg_alpha_slider.blockSignals(False)
        self.bg_alpha_label.setText(f"{current_alpha}%")

        self.blur_radius_slider.blockSignals(True)
        self.blur_radius_slider.setValue(current_blur)
        self.blur_radius_slider.blockSignals(False)
        self.blur_radius_label.setText(str(current_blur))

        self.edge_opacity_slider.blockSignals(True)
        self.edge_opacity_slider.setValue(int(current_edge * 100))
        self.edge_opacity_slider.blockSignals(False)
        self.edge_opacity_label.setText(f"{int(current_edge * 100)}%")

        self._update_ui_state_for_mode(settings.bg_mode)

        self.bg_path_edit.setText(settings.custom_bg_path)

    # === UI State ===

    def _update_ui_state_for_mode(self, mode):
        if mode == "theme" or mode == "acrylic":
            self.visual_effect_group.setVisible(False)
        else:
            self.visual_effect_group.setVisible(True)

        if not self.corner_spin.isEnabled() or self.corner_spin.value() == 0:
            settings = self.data_manager.get_settings()
            self.corner_spin.blockSignals(True)
            self.corner_spin.setValue(settings.corner_radius)
            self.corner_spin.blockSignals(False)
        self.corner_spin.setEnabled(True)

    # === Event Handlers ===

    def _on_size_changed(self):
        if self._updating:
            return

        updates = {
            "icon_size": self.icon_size_spin.value(),
            "cell_size": self.cell_size_spin.value(),
            "cols": self.cols_spin.value(),
            "popup_max_rows": self.popup_max_rows_spin.value(),
        }

        if self.corner_spin.isEnabled():
            updates["corner_radius"] = self.corner_spin.value()

        self.data_manager.update_settings(**updates)

    def _on_dock_size_changed(self):
        if self._updating:
            return

        height_val = self.dock_height_spin.value()
        enabled = height_val > 0
        mode = height_val if height_val > 0 else 1

        self.data_manager.update_settings(dock_enabled=enabled, dock_height_mode=mode)

    def _on_bg_alpha_changed(self, value):
        self.bg_alpha_label.setText(f"{value}%")
        if self._updating:
            return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            self.data_manager.update_settings(bg_alpha=value)

            if mode == "theme":
                self.data_manager.update_settings(theme_bg_alpha=value)
            elif mode == "image":
                self.data_manager.update_settings(image_bg_alpha=value)
            elif mode == "acrylic":
                self.data_manager.update_settings(acrylic_bg_alpha=value)

    def _on_dock_bg_alpha_changed(self, value):
        self.dock_bg_alpha_label.setText(f"{value}%")
        if self._updating:
            return
        self.data_manager.update_settings(dock_bg_alpha=value)

    def _on_icon_alpha_changed(self, value):
        self.icon_alpha_label.setText(f"{value}%")
        if self._updating:
            return
        self.data_manager.update_settings(icon_alpha=value / 100.0)

    def _on_bg_mode_changed(self, button):
        mode = "theme"
        if button == self.bg_image_radio:
            mode = "image"
        elif button == self.bg_acrylic_radio:
            mode = "acrylic"

        self.bg_image_widget.setVisible(mode == "image")
        self._update_ui_state_for_mode(mode)

        settings = self.data_manager.get_settings()
        if mode == "theme":
            target_alpha = getattr(settings, "theme_bg_alpha", 90)
            target_blur = getattr(settings, "theme_blur_radius", 0)
            target_edge = getattr(settings, "theme_edge_opacity", 0.0)
        elif mode == "image":
            target_alpha = getattr(settings, "image_bg_alpha", 90)
            target_blur = getattr(settings, "image_blur_radius", 0)
            target_edge = getattr(settings, "image_edge_opacity", 0.0)
        else:  # acrylic
            target_alpha = getattr(settings, "acrylic_bg_alpha", 90)
            target_blur = getattr(settings, "acrylic_blur_radius", 0)
            target_edge = getattr(settings, "acrylic_edge_opacity", 0.0)

        self.bg_alpha_slider.blockSignals(True)
        self.bg_alpha_slider.setValue(target_alpha)
        self.bg_alpha_slider.blockSignals(False)
        self.bg_alpha_label.setText(f"{target_alpha}%")

        self.blur_radius_slider.blockSignals(True)
        self.blur_radius_slider.setValue(target_blur)
        self.blur_radius_slider.blockSignals(False)
        self.blur_radius_label.setText(str(target_blur))

        self.edge_opacity_slider.blockSignals(True)
        self.edge_opacity_slider.setValue(int(target_edge * 100))
        self.edge_opacity_slider.blockSignals(False)
        self.edge_opacity_label.setText(f"{int(target_edge * 100)}%")

        if self._updating:
            return
        with self.data_manager.batch_update():
            self.data_manager.update_settings(bg_mode=mode)
            self.data_manager.update_settings(bg_alpha=target_alpha)
            self.data_manager.update_settings(bg_blur_radius=target_blur)
            self.data_manager.update_settings(edge_highlight_opacity=target_edge)
        self.settings_changed.emit()

    def _browse_bg_image(self):
        file_path, _ = get_open_file_name(self, "选择背景图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.bg_path_edit.setText(file_path)
            self.data_manager.update_settings(custom_bg_path=file_path)
            self.settings_changed.emit()

    def _on_blur_radius_changed(self, value):
        self.blur_radius_label.setText(str(value))
        if self._updating:
            return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            self.data_manager.update_settings(bg_blur_radius=value)

            if mode == "theme":
                self.data_manager.update_settings(theme_blur_radius=value)
            elif mode == "image":
                self.data_manager.update_settings(image_blur_radius=value)
            elif mode == "acrylic":
                self.data_manager.update_settings(acrylic_blur_radius=value)

        self._schedule_slider_settings_changed()

    def _on_edge_opacity_changed(self, value):
        self.edge_opacity_label.setText(f"{value}%")
        if self._updating:
            return

        mode = self.data_manager.get_settings().bg_mode
        with self.data_manager.batch_update():
            self.data_manager.update_settings(edge_highlight_opacity=value / 100.0)

            if mode == "theme":
                self.data_manager.update_settings(theme_edge_opacity=value / 100.0)
            elif mode == "image":
                self.data_manager.update_settings(image_edge_opacity=value / 100.0)
            elif mode == "acrylic":
                self.data_manager.update_settings(acrylic_edge_opacity=value / 100.0)
