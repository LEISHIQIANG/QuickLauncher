"""Data management settings page builder."""


import logging

from core.i18n import tr
from qt_compat import QHBoxLayout, QLabel, QPushButton
from ui.tooltip_helper import install_tooltip
from ui.utils.font_manager import get_font_css_with_size

logger = logging.getLogger(__name__)


class SettingsDataPageMixin:
    def _setup_data_page(self, page):
        """设置数据管理页面"""
        # 配置管理
        layout, group = page.add_group("配置管理")

        # 导出配置按钮
        export_btn = QPushButton(tr("导出配置"))
        export_btn.clicked.connect(self._on_export_clicked)
        layout.addWidget(export_btn)

        # 导入配置按钮
        import_btn = QPushButton(tr("导入配置"))
        import_btn.clicked.connect(self._on_import_clicked)
        layout.addWidget(import_btn)

        # 分享配置按钮
        share_row = QHBoxLayout()
        share_row.setSpacing(8)

        export_share_btn = QPushButton(tr("导出分享配置"))
        export_share_btn.setFixedHeight(36)
        install_tooltip(export_share_btn, tr("仅导出快捷键、打开网址、运行命令三种类型"))
        export_share_btn.clicked.connect(self._on_export_shareable_clicked)
        share_row.addWidget(export_share_btn, 1)

        import_share_btn = QPushButton(tr("导入分享配置"))
        import_share_btn.setFixedHeight(36)
        install_tooltip(import_share_btn, tr("导入后会自动创建「导入图标」分类"))
        import_share_btn.clicked.connect(self._on_import_shareable_clicked)
        share_row.addWidget(import_share_btn, 1)

        layout.addLayout(share_row)

        # 危险操作区域
        danger_layout, danger_group = page.add_group("危险操作")
        danger_layout.setSpacing(10)

        # 警告说明
        warning_label = QLabel(tr("以下操作不可逆，请谨慎使用"))
        warning_label.setStyleSheet(f"""
            {get_font_css_with_size(12, 600)}
            color: #ff6b6b;
            padding: 0px;
            margin: 0px 0px 8px 0px;
        """)
        danger_layout.addWidget(warning_label)

        # 清除所有配置按钮
        self.factory_reset_btn = QPushButton(tr("清除所有配置"))
        self.factory_reset_btn.setFixedHeight(36)
        self.factory_reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 0px 20px;
                border-radius: 6px;
                {get_font_css_with_size(13, 600)}
            }}
            QPushButton:hover {{
                background-color: #c82333;
            }}
            QPushButton:pressed {{
                background-color: #bd2130;
            }}
        """)
        self.factory_reset_btn.clicked.connect(self._on_factory_reset_clicked)
        danger_layout.addWidget(self.factory_reset_btn)

        # 说明文本
        reset_desc = QLabel(
            tr("清除所有配置、图标缓存、快速搜索列表、右键扩展注册表项，并重启应用")
        )
        reset_desc.setObjectName("data_desc_3")
        reset_desc.setStyleSheet(f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            padding: 0px;
            margin: 4px 0px 0px 0px;
        """)
        reset_desc.setWordWrap(True)
        danger_layout.addWidget(reset_desc)
