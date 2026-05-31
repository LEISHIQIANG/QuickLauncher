"""Configuration history restore dialog."""

from __future__ import annotations

import os
from datetime import datetime

from core.i18n import tr
from qt_compat import (
    QEvent,
    QFont,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QObject,
    QPushButton,
    QSize,
    Qt,
    QTimer,
)
from ui.custom_tooltip import CustomToolTip
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.themed_tool_window import ThemedToolWindow


class ConfigHistoryWindow(ThemedToolWindow):
    """List and restore persisted configuration snapshots."""

    def __init__(self, data_manager, parent=None):
        self.data_manager = data_manager
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__(tr("配置历史"), theme=theme, parent=parent)
        self.resize(700, 480)
        self._setup_ui()
        self._apply_content_theme()
        self.refresh()

    def _setup_ui(self):
        self.set_subtitle(tr("最近 20 次重要配置变更快照，可用于恢复"))

        self.recovery_label = QLabel("")
        self.recovery_label.setWordWrap(True)
        self.content_layout.addWidget(self.recovery_label)

        # Recovery action buttons
        recovery_btn_layout = QHBoxLayout()
        recovery_btn_layout.setSpacing(8)

        self.open_recovery_dir_btn = QPushButton(tr("打开恢复目录"))
        self.open_recovery_dir_btn.clicked.connect(self._open_recovery_dir)
        recovery_btn_layout.addWidget(self.open_recovery_dir_btn)

        self.open_backup_dir_btn = QPushButton(tr("打开备份目录"))
        self.open_backup_dir_btn.clicked.connect(self._open_backup_dir)
        recovery_btn_layout.addWidget(self.open_backup_dir_btn)

        self.copy_report_btn = QPushButton(tr("复制恢复报告"))
        self.copy_report_btn.clicked.connect(self._copy_recovery_report)
        recovery_btn_layout.addWidget(self.copy_report_btn)

        recovery_btn_layout.addStretch()
        self.content_layout.addLayout(recovery_btn_layout)

        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(False)
        self.list_widget.setSpacing(0)
        self.list_widget.setUniformItemSizes(True)
        font = QFont("Microsoft YaHei UI", 9)
        if not font.exactMatch():
            font = QFont("Segoe UI", 9)
        self.list_widget.setFont(font)
        self.content_layout.addWidget(self.list_widget)

        self._install_list_tooltips()

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.restore_btn = QPushButton(tr("恢复选中快照"))
        self.restore_btn.clicked.connect(self.restore_selected)
        buttons.addWidget(self.restore_btn)

        buttons.addStretch()
        self.button_layout.addLayout(buttons)

    def _install_list_tooltips(self):
        """安装主题感知的自定义工具提示，与其他配置窗口风格统一。"""
        viewport = self.list_widget.viewport()
        viewport.setMouseTracking(True)

        class _TooltipFilter(QObject):
            def __init__(self, list_widget, get_theme):
                super().__init__()
                self._list = list_widget
                self._get_theme = get_theme
                self._hovered = None
                self._timer = None

            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseMove:
                    item = self._list.itemAt(event.pos())
                    if item is not self._hovered:
                        self._hovered = item
                        if self._timer:
                            self._timer.stop()
                        CustomToolTip.hideToolTip()
                        if item is not None:
                            tip = item.data(Qt.UserRole)
                            if tip:
                                theme = self._get_theme()
                                self._timer = QTimer()
                                self._timer.setSingleShot(True)
                                self._timer.timeout.connect(lambda t=tip, th=theme: CustomToolTip.showToolTip(t, th))
                                self._timer.start(500)
                elif event.type() == QEvent.Leave:
                    if self._timer:
                        self._timer.stop()
                        self._timer = None
                    CustomToolTip.hideToolTip()
                return False

        viewport._tooltip_filter = _TooltipFilter(self.list_widget, lambda: getattr(self, "_theme", "dark"))
        viewport.installEventFilter(viewport._tooltip_filter)

    def _apply_content_theme(self):
        if hasattr(self, "list_widget"):
            self.style_compact_list_widget(self.list_widget)
        if hasattr(self, "recovery_label"):
            color = (
                "rgba(255, 255, 255, 0.62)" if getattr(self, "_theme", "light") == "dark" else "rgba(60, 60, 67, 0.72)"
            )
            self.recovery_label.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent;")
        buttons = [
            getattr(self, "refresh_btn", None),
            getattr(self, "restore_btn", None),
            getattr(self, "open_recovery_dir_btn", None),
            getattr(self, "open_backup_dir_btn", None),
            getattr(self, "copy_report_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        self._refresh_recovery_status()
        self.list_widget.clear()
        self.snapshots = self.data_manager.list_config_history()
        if not self.snapshots:
            item = QListWidgetItem(tr("暂无历史快照。重要配置变更后会自动保存最近 20 次快照"))
            item.setSizeHint(QSize(0, 32))
            self.list_widget.addItem(item)
            return
        for snapshot in self.snapshots:
            ts = datetime.fromtimestamp(snapshot.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            action = snapshot.action or tr("配置变更")
            summary = snapshot.summary or ""
            if summary and summary != action:
                text = f"{ts}  {action}  {summary}"
                tip = f"{ts}\n{action}\n{summary}"
            else:
                text = f"{ts}  {action}"
                tip = f"{ts}\n{action}"
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(0, 32))
            item.setData(Qt.UserRole, tip)
            item.setData(32, snapshot.id)
            self.list_widget.addItem(item)

    def _refresh_recovery_status(self):
        report = getattr(self.data_manager, "get_recovery_report", lambda: {})()
        if not report:
            self.recovery_label.setText(tr("配置恢复状态：暂无恢复记录。"))
            return
        status = report.get("status", "unknown")
        status_labels = {
            "ok": tr("正常"),
            "recovered": tr("已自动恢复"),
            "fallback_default": tr("使用默认配置"),
            "failed": tr("恢复失败"),
        }
        status_text = status_labels.get(status, status)
        source = report.get("recovered_from") or report.get("source_path") or "-"
        quarantined = report.get("quarantined_path") or "-"
        issues = report.get("issues", [])
        parts = [tr("状态: {status_text}", status_text=status_text), tr("来源: {source}", source=source)]
        if quarantined and quarantined != "-":
            parts.append(tr("隔离文件: {quarantined}", quarantined=quarantined))
        if issues:
            parts.append(tr("问题: {issues}", issues=", ".join(issues[:3])))
        self.recovery_label.setText(" | ".join(parts))

    def _open_recovery_dir(self):
        recovery_dir = getattr(self.data_manager, "recovery_dir", None)
        if recovery_dir and os.path.isdir(str(recovery_dir)):
            try:
                os.startfile(str(recovery_dir))
            except OSError as exc:
                ThemedMessageBox.warning(self, tr("打开失败"), tr("无法打开目录: {error}", error=str(exc)))
        else:
            ThemedMessageBox.information(self, tr("提示"), tr("恢复目录不存在。"))

    def _open_backup_dir(self):
        backup_dir = getattr(self.data_manager, "auto_backup_dir", None)
        if backup_dir and os.path.isdir(str(backup_dir)):
            try:
                os.startfile(str(backup_dir))
            except OSError as exc:
                ThemedMessageBox.warning(self, tr("打开失败"), tr("无法打开目录: {error}", error=str(exc)))
        else:
            ThemedMessageBox.information(self, tr("提示"), tr("备份目录不存在。"))

    def _copy_recovery_report(self):
        report = getattr(self.data_manager, "get_recovery_report", lambda: {})()
        if report:
            import json

            from qt_compat import QApplication

            text = json.dumps(report, ensure_ascii=False, indent=2)
            QApplication.clipboard().setText(text)
            ThemedMessageBox.information(self, tr("已复制"), tr("恢复报告已复制到剪贴板。"))
        else:
            ThemedMessageBox.information(self, tr("提示"), tr("暂无恢复报告。"))

    def restore_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        snapshot_id = item.data(32)
        if not snapshot_id:
            return
        result = ThemedMessageBox.question(
            self,
            tr("确认恢复"),
            tr("确认恢复选中的历史快照吗？当前配置会先被记录为新的历史快照。"),
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )
        if result != ThemedMessageBox.Yes:
            return
        if self.data_manager.restore_config_history(str(snapshot_id)):
            ThemedMessageBox.information(self, tr("恢复完成"), tr("历史快照已恢复，请重启或刷新窗口查看。"))
            self.refresh()
        else:
            ThemedMessageBox.warning(self, tr("恢复失败"), tr("无法恢复该历史快照。"))
