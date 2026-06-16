"""Diagnostics center dialog."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from core.diagnostics import collect_diagnostics, export_diagnostics_zip
from core.i18n import tr
from core.shortcut_health import apply_health_fixes, check_shortcuts, preview_health_fixes, save_health_state
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
from ui.utils.qt_thread_cleanup import stop_qthread_nonblocking
from ui.utils.safe_file_dialog import get_save_file_name
from ui.utils.ui_scale import font_px, sp

logger = logging.getLogger(__name__)


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


class DiagnosticsFixThread(QThread):
    finished_signal = pyqtSignal(dict, str)

    def __init__(self, data_manager, fix_ids):
        super().__init__()
        self.data_manager = data_manager
        self.fix_ids = list(fix_ids or [])

    def run(self):
        try:
            self.finished_signal.emit(apply_health_fixes(self.data_manager, self.fix_ids), "")
        except Exception as exc:
            self.finished_signal.emit({}, str(exc))


class DiagnosticsWindow(ThemedToolWindow):
    """Simple diagnostics center for runtime health and export."""

    def __init__(self, data_manager, tray_app=None, parent=None):
        self.data_manager = data_manager
        self.tray_app = tray_app
        self._collect_thread = None
        self._fix_thread = None
        self.items = []
        self.shortcut_issues = []
        self._last_repair_result = None
        self._last_scan_at = ""
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__(tr("诊断中心"), theme=theme, parent=parent)
        self.resize(sp(760), sp(560))
        self._setup_ui()
        self._apply_content_theme()
        self.text.setHtml(tr("正在收集诊断信息..."))
        QTimer.singleShot(80, self.refresh)

    def _setup_ui(self):
        self.set_subtitle(tr("运行环境、配置、钩子、热键、缓存和最近错误"))

        self.text = _DiagnosticsTextEdit()
        self.text.setReadOnly(True)
        font = QFont("Consolas", font_px(9))
        if not font.exactMatch():
            font = QFont("Courier New", font_px(9))
        self.text.setFont(font)
        self.content_layout.addWidget(self.text)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton(tr("复制摘要"))
        self.copy_btn.clicked.connect(self.copy_summary)
        buttons.addWidget(self.copy_btn)

        self.fix_btn = QPushButton(tr("一键修复"))
        self.fix_btn.clicked.connect(self.apply_all_fixes)
        self.fix_btn.setEnabled(False)
        buttons.addWidget(self.fix_btn)

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
            getattr(self, "fix_btn", None),
            getattr(self, "export_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        if self._collect_thread and self._collect_thread.isRunning():
            return
        self.text.setHtml(tr("正在收集诊断信息..."))
        self.refresh_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._collect_thread = DiagnosticsCollectThread(self.data_manager, self.tray_app)
        self._collect_thread.finished_signal.connect(self._on_collect_finished)
        self._collect_thread.finished.connect(
            lambda thread=self._collect_thread: (
                setattr(self, "_collect_thread", None) if getattr(self, "_collect_thread", None) is thread else None
            )
        )
        self._collect_thread.finished.connect(self._collect_thread.deleteLater)
        self._collect_thread.start()

    def _on_collect_finished(self, items, error: str):
        self.refresh_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        if error:
            self.items = []
            self.shortcut_issues = []
            self.fix_btn.setEnabled(False)
            self.text.setHtml(tr("诊断收集失败: {error}", error=error))
            return
        self.items = list(items or [])
        self.shortcut_issues = self._scan_shortcut_issues()
        self.fix_btn.setEnabled(any(issue.fix_action for issue in self.shortcut_issues))
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

    def apply_all_fixes(self):
        if self._fix_thread and self._fix_thread.isRunning():
            return
        fix_ids = [issue.id for issue in self.shortcut_issues if issue.fix_action]
        if not fix_ids:
            ThemedMessageBox.information(self, tr("一键修复"), tr("未发现可自动修复的问题。"))
            return

        previews = preview_health_fixes(self.data_manager, fix_ids)
        if not previews:
            ThemedMessageBox.information(self, tr("一键修复"), tr("未发现可自动修复的问题。"))
            return

        destructive = [p for p in previews if not p.safe]
        safe_items = [p for p in previews if p.safe]
        preview_text = self._format_fix_preview(destructive, safe_items)
        confirm_msg = preview_text + "\n\n" + tr("确定要执行以上修复吗？")
        result = ThemedMessageBox.question(
            self,
            tr("确认修复"),
            confirm_msg,
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )
        if result != ThemedMessageBox.Yes:
            return

        self._set_fix_running(True)
        self._fix_thread = DiagnosticsFixThread(self.data_manager, fix_ids)
        self._fix_thread.finished_signal.connect(self._on_fix_finished)
        self._fix_thread.finished.connect(
            lambda thread=self._fix_thread: (
                setattr(self, "_fix_thread", None) if getattr(self, "_fix_thread", None) is thread else None
            )
        )
        self._fix_thread.finished.connect(self._fix_thread.deleteLater)
        self._fix_thread.start()

    def _set_fix_running(self, running: bool):
        self.fix_btn.setEnabled(not running)
        self.refresh_btn.setEnabled(not running)
        self.export_btn.setEnabled(not running)
        self.fix_btn.setText(tr("修复中...") if running else tr("一键修复"))
        if running:
            self.text.setPlainText(tr("正在后台修复，网站图标会并发重新自动获取，请稍候..."))

    def _on_fix_finished(self, repair_result: dict, error: str):
        self._set_fix_running(False)
        if error:
            self.refresh()
            ThemedMessageBox.warning(self, tr("修复失败"), tr("修复过程中发生错误:\n{error}", error=error))
            return
        self._last_repair_result = repair_result
        self.refresh()
        skipped = repair_result.get("skipped", 0)
        failed = repair_result.get("failed", 0)
        detail = tr("已应用 {count} 项修复。", count=repair_result.get("applied", 0))
        if skipped:
            detail += tr("\n已跳过 {skipped} 项被删除图标覆盖的重复修复。", skipped=skipped)
        if failed:
            detail += tr("\n有 {failed} 项修复失败，请重新扫描后查看报告。", failed=failed)
        ThemedMessageBox.information(self, tr("修复完成"), detail)

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
        repair_summary = self._shortcut_repair_summary()

        lines = [f'<pre style="font-family: Consolas, Courier New, monospace; font-size: {font_px(12)}px;">']

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
        lines.append(
            "  "
            + self._html_escape(
                tr(
                    "可修复: {fixable} 项，其中删除快捷方式: {destructive} 项",
                    fixable=repair_summary["fixable"],
                    destructive=repair_summary["destructive"],
                )
            )
        )
        if repair_summary["last_scan"]:
            lines.append("  " + self._html_escape(tr("扫描时间: {time}", time=repair_summary["last_scan"])))
        if self._last_repair_result:
            lines.append(
                "  "
                + self._html_escape(
                    tr(
                        "上次修复: 应用 {applied} / 跳过 {skipped} / 失败 {failed}",
                        applied=self._last_repair_result.get("applied", 0),
                        skipped=self._last_repair_result.get("skipped", 0),
                        failed=self._last_repair_result.get("failed", 0),
                    )
                )
            )
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

    def _scan_shortcut_issues(self):
        try:
            issues = check_shortcuts(self.data_manager.data)
            self._last_scan_at = datetime.now().isoformat(timespec="seconds")
            state_dir = getattr(self.data_manager, "config_dir", None)
            if state_dir:
                save_health_state(state_dir, issues)
            return list(issues or [])
        except Exception:
            return []

    def _shortcut_repair_summary(self) -> dict:
        fixable = 0
        destructive = 0
        last_scan = self._last_scan_at
        for item in self.items:
            if item.title not in ("图标检查", tr("图标检查")):
                continue
            metadata = getattr(item, "metadata", {}) or {}
            fixable = int(metadata.get("fixable", 0) or 0)
            destructive = int(metadata.get("destructive_fix_count", 0) or 0)
        for item in self.items:
            if item.title not in ("健康检查缓存", tr("健康检查缓存")):
                continue
            try:
                import json

                cached = json.loads(item.details or "{}")
                last_scan = last_scan or str(cached.get("last_scan_at") or "")
            except Exception:
                logger.debug("解析健康检查缓存摘要失败", exc_info=True)
        return {"fixable": fixable, "destructive": destructive, "last_scan": last_scan}

    def _format_fix_preview(self, destructive, safe_items) -> str:
        lines = []
        if destructive:
            lines.append(tr("⚠️ 以下操作不可逆：\n"))
            for preview in destructive[:20]:
                lines.append(f"  • {preview.description}")
            if len(destructive) > 20:
                lines.append(tr("  ... 另有 {count} 项删除操作", count=len(destructive) - 20))
            lines.append("")
        if safe_items:
            lines.append(tr("安全修复：\n"))
            action_counts = {}  # type: ignore[var-annotated]
            for preview in safe_items:
                action_counts[preview.action] = action_counts.get(preview.action, 0) + 1
            for action, count in sorted(action_counts.items()):
                lines.append(f"  • {self._format_fix_action(action)}: {count}")
        return "\n".join(lines)

    def _format_fix_action(self, action: str) -> str:
        labels = {
            "clear_icon": tr("清除失效图标路径"),
            "refresh_favicon": tr("重新自动获取网站图标"),
            "delete_shortcut": tr("删除该图标"),
            "clear_working_dir": tr("清空失效工作目录"),
            "disable_folder_sync": tr("关闭该分类自动同步"),
        }
        return labels.get(action, action)

    def closeEvent(self, event):
        for attr in ("_collect_thread", "_fix_thread"):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            stopped = stop_qthread_nonblocking(
                thread,
                owner=f"DiagnosticsWindow.{attr}",
                wait_ms=0,
                disconnect_thread_signals=("finished", "finished_signal"),
            )
            if stopped:
                setattr(self, attr, None)
        super().closeEvent(event)
