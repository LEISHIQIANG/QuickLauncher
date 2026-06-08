"""Data management settings page builder."""

import logging
from pathlib import Path

from core.i18n import tr
from qt_compat import QHBoxLayout, QLabel, QPushButton
from ui.tooltip_helper import install_tooltip
from ui.utils.font_manager import get_font_css_with_size
from ui.utils.ui_scale import scale_qss, sp

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "ok": ("正常", "#4caf50"),
    "recovered": ("已自动恢复", "#ff9800"),
    "recovered_memory_only": ("仅内存恢复", "#ff9800"),
    "fallback_default": ("使用默认配置", "#ff9800"),
    "failed": ("恢复失败", "#f44336"),
}


class SettingsDataPageMixin:
    def _setup_recovery_section(self, page):
        """添加配置恢复状态区域"""
        layout, _group = page.add_group("配置恢复状态")

        # 获取恢复报告
        try:
            report = self.data_manager.get_recovery_report()
        except Exception:
            report = {}

        status = report.get("status", "ok") if report else "ok"
        status_text, status_color = _STATUS_LABELS.get(status, ("未知", "#999"))

        # 状态行
        status_row = QHBoxLayout()
        status_label = QLabel(tr("配置状态"))
        status_label.setStyleSheet(get_font_css_with_size(12, 600))
        status_row.addWidget(status_label)

        status_value = QLabel(status_text)
        status_value.setStyleSheet(f"{get_font_css_with_size(12, 600)} color: {status_color};")
        status_row.addWidget(status_value)
        status_row.addStretch()
        layout.addLayout(status_row)

        # 恢复详情（仅非 ok 状态显示）
        if report and status != "ok":
            recovered_from = report.get("recovered_from", "")
            created_at = report.get("created_at", "")
            reason = report.get("reason", "")
            quarantined_path = report.get("quarantined_path", "")

            details = []
            if reason:
                details.append(f"{tr('原因')}: {reason}")
            if recovered_from:
                details.append(f"{tr('恢复来源')}: {Path(recovered_from).name}")
            if created_at:
                details.append(f"{tr('恢复时间')}: {created_at}")
            if quarantined_path:
                details.append(f"{tr('隔离文件')}: {Path(quarantined_path).name}")

            issues = report.get("issues", [])
            if issues:
                details.append(f"{tr('问题')}: {', '.join(issues[:3])}")

            if details:
                detail_label = QLabel("\n".join(details))
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(scale_qss(f"""
                    {get_font_css_with_size(11, 400)}
                    color: {self._get_desc_color()};
                    padding: 2px 0px;
                """))
                layout.addWidget(detail_label)

        # 统计隔离文件数量
        try:
            recovery_dir = getattr(self.data_manager, "recovery_dir", None)
            if recovery_dir:
                recovery_path = Path(str(recovery_dir))
                if recovery_path.is_dir():
                    quarantined_count = len(list(recovery_path.glob("bad_data_*.json")))
                    if quarantined_count > 0:
                        count_label = QLabel(tr("已隔离损坏配置文件") + f": {quarantined_count}")
                        count_label.setStyleSheet(scale_qss(f"""
                            {get_font_css_with_size(11, 400)}
                            color: {self._get_desc_color()};
                            padding: 2px 0px;
                        """))
                        layout.addWidget(count_label)
        except Exception:
            logger.debug("加载配置恢复状态失败", exc_info=True)

        # 查看详细历史按钮
        history_btn = QPushButton(tr("查看配置历史"))
        history_btn.setFixedHeight(sp(36))
        history_btn.clicked.connect(self._on_config_history_clicked)
        layout.addWidget(history_btn)

    def _setup_data_page(self, page):
        """设置数据管理页面"""
        # 配置恢复状态
        self._setup_recovery_section(page)

        # 配置管理
        layout, group = page.add_group("配置管理")

        # 导出配置按钮
        export_btn = QPushButton(tr("导出配置"))
        export_btn.setFixedHeight(sp(36))
        export_btn.clicked.connect(self._on_export_clicked)
        layout.addWidget(export_btn)

        # 导入配置按钮
        import_btn = QPushButton(tr("导入配置"))
        import_btn.setFixedHeight(sp(36))
        import_btn.clicked.connect(self._on_import_clicked)
        layout.addWidget(import_btn)

        # 分享配置按钮
        share_row = QHBoxLayout()
        share_row.setSpacing(sp(8))

        export_share_btn = QPushButton(tr("导出分享配置"))
        export_share_btn.setFixedHeight(sp(36))
        install_tooltip(export_share_btn, tr("仅导出快捷键、打开网址、运行命令三种类型"))
        export_share_btn.clicked.connect(self._on_export_shareable_clicked)
        share_row.addWidget(export_share_btn, 1)

        import_share_btn = QPushButton(tr("导入分享配置"))
        import_share_btn.setFixedHeight(sp(36))
        install_tooltip(import_share_btn, tr("导入后会自动创建「导入图标」分类"))
        import_share_btn.clicked.connect(self._on_import_shareable_clicked)
        share_row.addWidget(import_share_btn, 1)

        layout.addLayout(share_row)

        # 危险操作区域
        danger_layout, danger_group = page.add_group("危险操作")
        danger_layout.setSpacing(sp(10))

        # 警告说明
        warning_label = QLabel(tr("以下操作不可逆，请谨慎使用"))
        warning_label.setStyleSheet(scale_qss(f"""
            {get_font_css_with_size(12, 600)}
            color: #ff6b6b;
            padding: 0px;
            margin: 0px 0px 8px 0px;
        """))
        danger_layout.addWidget(warning_label)

        # 清除所有配置按钮
        self.factory_reset_btn = QPushButton(tr("清除所有配置"))
        self.factory_reset_btn.setFixedHeight(sp(36))
        self.factory_reset_btn.setStyleSheet(scale_qss(f"""
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
        """))
        self.factory_reset_btn.clicked.connect(self._on_factory_reset_clicked)
        danger_layout.addWidget(self.factory_reset_btn)

        # 说明文本
        reset_desc = QLabel(tr("清除所有配置、图标缓存、快速搜索列表、右键扩展注册表项，并重启应用"))
        reset_desc.setObjectName("data_desc_3")
        reset_desc.setStyleSheet(scale_qss(f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            padding: 0px;
            margin: 4px 0px 0px 0px;
        """))
        reset_desc.setWordWrap(True)
        danger_layout.addWidget(reset_desc)
