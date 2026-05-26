"""Configuration history restore dialog."""

from __future__ import annotations

from datetime import datetime

from qt_compat import QEvent, QFont, QHBoxLayout, QListWidget, QListWidgetItem, QObject, QPushButton, QSize, Qt, QTimer
from ui.custom_tooltip import CustomToolTip
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.themed_tool_window import ThemedToolWindow


class ConfigHistoryWindow(ThemedToolWindow):
    """List and restore persisted configuration snapshots."""

    def __init__(self, data_manager, parent=None):
        self.data_manager = data_manager
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__("配置历史", theme=theme, parent=parent)
        self.resize(700, 480)
        self._setup_ui()
        self._apply_content_theme()
        self.refresh()

    def _setup_ui(self):
        self.set_subtitle("最近 20 次重要配置变更快照，可用于恢复")

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
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.restore_btn = QPushButton("恢复选中快照")
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
        buttons = [
            getattr(self, "refresh_btn", None),
            getattr(self, "restore_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        self.list_widget.clear()
        self.snapshots = self.data_manager.list_config_history()
        if not self.snapshots:
            item = QListWidgetItem("暂无历史快照。重要配置变更后会自动保存最近 20 次快照")
            item.setSizeHint(QSize(0, 32))
            self.list_widget.addItem(item)
            return
        for snapshot in self.snapshots:
            ts = datetime.fromtimestamp(snapshot.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            action = snapshot.action or "配置变更"
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

    def restore_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        snapshot_id = item.data(32)
        if not snapshot_id:
            return
        result = ThemedMessageBox.question(
            self,
            "确认恢复",
            "确认恢复选中的历史快照吗？当前配置会先被记录为新的历史快照。",
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )
        if result != ThemedMessageBox.Yes:
            return
        if self.data_manager.restore_config_history(str(snapshot_id)):
            ThemedMessageBox.information(self, "恢复完成", "历史快照已恢复，请重启或刷新窗口查看。")
            self.refresh()
        else:
            ThemedMessageBox.warning(self, "恢复失败", "无法恢复该历史快照。")
