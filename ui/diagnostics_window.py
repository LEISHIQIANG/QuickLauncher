"""Diagnostics center dialog."""

from __future__ import annotations

import os
from datetime import datetime

from core.diagnostics import collect_diagnostics, export_diagnostics_zip
from core.i18n import tr
from qt_compat import (
    QApplication,
    QFont,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QThread,
    QTimer,
    pyqtSignal,
)
from ui.styles.style import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.themed_tool_window import ThemedToolWindow
from ui.utils.safe_file_dialog import get_save_file_name


class _DiagnosticsTextEdit(QTextEdit):
    """带主题右键菜单的诊断文本编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "light"

    def set_theme(self, theme: str):
        self._theme = theme

    def contextMenuEvent(self, event):
        menu = PopupMenu(theme=self._theme, radius=12, parent=None)
        menu.add_action(tr("复制"), lambda: self.copy(), enabled=self.textCursor().hasSelection())
        menu.add_action(tr("全选"), lambda: self.selectAll(), enabled=len(self.toPlainText()) > 0)
        menu.popup(event.globalPos())


class DiagnosticsCollectThread(QThread):
    finished_signal = pyqtSignal(list, str)

    def __init__(self, data_manager, tray_app=None):
        super().__init__()
        self.data_manager = data_manager
        self.tray_app = tray_app

    def run(self):
        try:
            self.finished_signal.emit(collect_diagnostics(self.data_manager, self.tray_app), "")
        except Exception as exc:
            self.finished_signal.emit([], str(exc))


class DiagnosticsWindow(ThemedToolWindow):
    """Simple diagnostics center for runtime health and export."""

    def __init__(self, data_manager, tray_app=None, parent=None):
        self.data_manager = data_manager
        self.tray_app = tray_app
        self._collect_thread = None
        self.items = []
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__(tr("诊断中心"), theme=theme, parent=parent)
        self.resize(760, 560)
        self._setup_ui()
        self._apply_content_theme()
        self.text.setHtml(tr("正在收集诊断信息..."))
        QTimer.singleShot(80, self.refresh)

    def _setup_ui(self):
        self.set_subtitle(tr("运行环境、配置、钩子、热键、缓存和最近错误"))

        self.text = _DiagnosticsTextEdit()
        self.text.setReadOnly(True)
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.text.setFont(font)
        self.content_layout.addWidget(self.text)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton(tr("复制摘要"))
        self.copy_btn.clicked.connect(self.copy_summary)
        buttons.addWidget(self.copy_btn)

        self.export_btn = QPushButton(tr("导出诊断包"))
        self.export_btn.clicked.connect(self.export_package)
        buttons.addWidget(self.export_btn)

        buttons.addStretch()
        self.button_layout.addLayout(buttons)

    def _apply_content_theme(self):
        if hasattr(self, "text"):
            self.style_plain_text(self.text)
            self.text.set_theme(self._theme)
        buttons = [
            getattr(self, "refresh_btn", None),
            getattr(self, "copy_btn", None),
            getattr(self, "export_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        if self._collect_thread and self._collect_thread.isRunning():
            return
        self.text.setHtml(tr("正在收集诊断信息..."))
        self.refresh_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._collect_thread = DiagnosticsCollectThread(self.data_manager, self.tray_app)
        self._collect_thread.finished_signal.connect(self._on_collect_finished)
        self._collect_thread.finished.connect(lambda: setattr(self, "_collect_thread", None))
        self._collect_thread.finished.connect(self._collect_thread.deleteLater)
        self._collect_thread.start()

    def _on_collect_finished(self, items, error: str):
        self.refresh_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        if error:
            self.items = []
            self.text.setHtml(tr("诊断收集失败: {error}", error=error))
            return
        self.items = list(items or [])
        self.text.setHtml(self._format_items())

    def copy_summary(self):
        QApplication.clipboard().setText(self.text.toPlainText())

    def export_package(self):
        default_name = f"QuickLauncher_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        default_path = os.path.join(str(self.data_manager.app_dir), default_name)
        path, _ = get_save_file_name(self, tr("导出诊断包"), default_path, "Zip Files (*.zip)")
        if not path:
            return
        if export_diagnostics_zip(self.data_manager, path, self.tray_app):
            ThemedMessageBox.information(self, tr("导出完成"), tr("诊断包已导出:\n{path}", path=path))
        else:
            ThemedMessageBox.warning(self, tr("导出失败"), tr("无法导出诊断包，请查看运行日志。"))

    def _format_items(self) -> str:
        """格式化诊断项为HTML，带颜色支持"""
        status_colors = {
            "error": "#ff4444",
            "warn": "#ffaa00",
            "ok": "#00cc66",
            "unknown": "#888888",
        }

        counts = {"error": 0, "warn": 0, "ok": 0, "unknown": 0}
        for item in self.items:
            key = str(item.status).lower()
            counts[key] = counts.get(key, 0) + 1

        lines = ['<pre style="font-family: Consolas, Courier New, monospace; font-size: 9pt;">']

        # 显示恢复状态横幅（如果有恢复事件）
        recovery_items = [it for it in self.items if it.title == tr("配置恢复")]
        if recovery_items:
            r = recovery_items[0]
            banner_color = status_colors.get(str(r.status).lower(), "#888888")
            lines.append(
                f'<span style="color: {banner_color};"><b>{tr("[配置恢复]")} {self._html_escape(r.summary)}</b></span>'
            )
            if r.details:
                lines.append(f"  {self._html_escape(r.details)}")
            lines.append("")

        lines.append(tr("<b>摘要</b>"))
        lines.append(f'  <span style="color: {status_colors["error"]};">ERROR  : {counts.get("error", 0)}</span>')
        lines.append(f'  <span style="color: {status_colors["warn"]};">WARN   : {counts.get("warn", 0)}</span>')
        lines.append(f'  <span style="color: {status_colors["ok"]};">OK     : {counts.get("ok", 0)}</span>')
        lines.append(f'  <span style="color: {status_colors["unknown"]};">UNKNOWN: {counts.get("unknown", 0)}</span>')
        lines.append("")
        lines.append(tr("<b>明细</b>"))

        for item in sorted(self.items, key=self._diagnostic_sort_key):
            status_upper = item.status.upper()
            color = status_colors.get(str(item.status).lower(), "#888888")
            lines.append(f'<span style="color: {color};">[{status_upper}] {self._html_escape(item.title)}</span>')
            lines.append(f"{tr('  摘要:')} {self._html_escape(item.summary)}")
            if item.details:
                lines.append(f"{tr('  详情:')} {self._html_escape(item.details)}")
            if item.action:
                lines.append(f"{tr('  建议:')} {self._html_escape(item.action)}")
            lines.append("")

        lines.append("</pre>")
        return "\n".join(lines)

    def _html_escape(self, text: str) -> str:
        """转义HTML特殊字符"""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _diagnostic_sort_key(self, item):
        status_rank = {"error": 0, "warn": 1, "unknown": 2, "ok": 3}
        return (status_rank.get(str(item.status).lower(), 9), item.title)

    def closeEvent(self, event):
        if self._collect_thread and self._collect_thread.isRunning():
            self._collect_thread.quit()
            self._collect_thread.wait(2000)
        super().closeEvent(event)
