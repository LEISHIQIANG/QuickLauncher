"""Icon check dialog."""

from __future__ import annotations

from core.shortcut_health import apply_health_fixes, check_shortcuts, save_health_state
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
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.themed_tool_window import ThemedToolWindow


class ShortcutHealthScanThread(QThread):
    finished_signal = pyqtSignal(list, str)

    def __init__(self, data, state_dir=None):
        super().__init__()
        self.data = data
        self.state_dir = state_dir

    def run(self):
        try:
            issues = check_shortcuts(self.data)
            if self.state_dir:
                save_health_state(self.state_dir, issues)
            self.finished_signal.emit(issues, "")
        except Exception as exc:
            self.finished_signal.emit([], str(exc))


class FaviconCacheCleanThread(QThread):
    finished_signal = pyqtSignal(dict, str)

    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager

    def run(self):
        try:
            from core.favicon_cache import clean_unused_favicon_cache

            self.finished_signal.emit(clean_unused_favicon_cache(self.data_manager.data, dry_run=False), "")
        except Exception as exc:
            self.finished_signal.emit({}, str(exc))


class ShortcutHealthWindow(ThemedToolWindow):
    """Read-only icon and shortcut consistency report with safe batch fixes."""

    def __init__(self, data_manager, parent=None):
        self.data_manager = data_manager
        self._scan_thread = None
        self._cache_clean_thread = None
        self.issues = []
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__("图标检查", theme=theme, parent=parent)
        self.resize(380, 560)
        self._setup_ui()
        self._apply_content_theme()
        self.text.setHtml("正在扫描图标、路径和命令风险...")
        QTimer.singleShot(80, self.refresh)

    def _setup_ui(self):
        self.set_subtitle("扫描缺失图标、失效路径、重复项、URL 和命令风险")

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.text.setFont(font)
        self.content_layout.addWidget(self.text)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton("重新扫描")
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton("复制报告")
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        buttons.addWidget(self.copy_btn)

        self.fix_btn = QPushButton("应用修复")
        self.fix_btn.clicked.connect(self.apply_safe_fixes)
        buttons.addWidget(self.fix_btn)

        self.clean_cache_btn = QPushButton("清理缓存")
        self.clean_cache_btn.clicked.connect(self.clean_unused_favicon_cache)
        buttons.addWidget(self.clean_cache_btn)

        buttons.addStretch()
        self.button_layout.addLayout(buttons)

    def _apply_content_theme(self):
        if hasattr(self, "text"):
            self.style_plain_text(self.text)
        buttons = [
            getattr(self, "refresh_btn", None),
            getattr(self, "copy_btn", None),
            getattr(self, "fix_btn", None),
            getattr(self, "clean_cache_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self.text.setHtml("正在扫描图标、路径和命令风险...")
        self.refresh_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.clean_cache_btn.setEnabled(False)
        self._scan_thread = ShortcutHealthScanThread(self.data_manager.data, state_dir=self.data_manager.config_dir)
        self._scan_thread.finished_signal.connect(self._on_scan_finished)
        self._scan_thread.finished.connect(lambda: setattr(self, "_scan_thread", None))
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _on_scan_finished(self, issues, error: str):
        self.refresh_btn.setEnabled(True)
        if error:
            self.issues = []
            self.fix_btn.setEnabled(False)
            self.clean_cache_btn.setEnabled(True)
            self.text.setHtml(f"扫描失败: {error}")
            return
        self.issues = self._sorted_issues(list(issues or []))
        self.fix_btn.setEnabled(any(issue.fix_action for issue in self.issues))
        self.clean_cache_btn.setEnabled(True)
        self.text.setHtml(self._format_issues())

    def apply_safe_fixes(self):
        fix_ids = [issue.id for issue in self.issues if issue.fix_action]
        if not fix_ids:
            return
        result = apply_health_fixes(self.data_manager, fix_ids)
        self.refresh()
        skipped = result.get("skipped", 0)
        failed = result.get("failed", 0)
        detail = f"已应用 {result.get('applied', 0)} 项修复。"
        if skipped:
            detail += f"\n已跳过 {skipped} 项被删除图标覆盖的重复修复。"
        if failed:
            detail += f"\n有 {failed} 项修复失败，请重新扫描后查看报告。"
        ThemedMessageBox.information(
            self,
            "修复完成",
            detail,
        )

    def clean_unused_favicon_cache(self):
        if self._cache_clean_thread and self._cache_clean_thread.isRunning():
            return
        self.clean_cache_btn.setEnabled(False)
        self.clean_cache_btn.setText("清理中...")
        self._cache_clean_thread = FaviconCacheCleanThread(self.data_manager)
        self._cache_clean_thread.finished_signal.connect(self._on_cache_clean_finished)
        self._cache_clean_thread.finished.connect(lambda: setattr(self, "_cache_clean_thread", None))
        self._cache_clean_thread.finished.connect(self._cache_clean_thread.deleteLater)
        self._cache_clean_thread.start()

    def _on_cache_clean_finished(self, stats: dict, error: str):
        self.clean_cache_btn.setText("清理缓存")
        self.clean_cache_btn.setEnabled(True)
        if error:
            ThemedMessageBox.warning(self, "清理失败", f"无法清理未使用图标缓存:\n{error}")
            return

        removed = int(stats.get("files_removed", stats.get("total_removed", 0)) or 0)
        freed = float(stats.get("size_freed_mb", stats.get("total_size_freed_mb", 0)) or 0)
        self.refresh()
        ThemedMessageBox.information(
            self,
            "清理完成",
            f"已清理 {removed} 个未使用的网页图标缓存，释放 {freed:.1f} MB。",
        )

    def _format_issues(self) -> str:
        """格式化问题列表为HTML，带颜色支持"""
        severity_colors = {
            "error": "#ff4444",
            "warn": "#ffaa00",
            "debug": "#888888",
            "info": "#888888",
        }

        cache_summary = self._format_favicon_cache_summary()
        if not self.issues:
            return f'<pre style="font-family: Consolas, Courier New, monospace; font-size: 9pt;">未发现问题。\n\n{cache_summary}</pre>'

        counts = self._count_by_severity(self.issues)
        fixable_count = sum(1 for issue in self.issues if issue.fix_action)

        lines = ['<pre style="font-family: Consolas, Courier New, monospace; font-size: 9pt;">']
        lines.append("<b>摘要</b>")
        lines.append(f'  <span style="color: {severity_colors["error"]};">ERROR: {counts.get("error", 0)}</span>')
        lines.append(f'  <span style="color: {severity_colors["warn"]};">WARN : {counts.get("warn", 0)}</span>')
        lines.append(f'  <span style="color: {severity_colors["debug"]};">DEBUG: {counts.get("debug", 0)}</span>')
        lines.append(f"  可修复: {fixable_count}")
        lines.append(cache_summary)
        lines.append("")
        lines.append("<b>明细</b>")

        for issue in self.issues:
            target = issue.shortcut_name or issue.folder_name or issue.shortcut_id or issue.folder_id
            color = severity_colors.get(issue.severity.lower(), "#888888")
            lines.append(
                f'<span style="color: {color};">[{issue.severity.upper()}] {self._html_escape(issue.title)} - {self._html_escape(target)}</span>'
            )
            lines.append(f"  分类: {self._html_escape(issue.folder_name or issue.folder_id)}")
            lines.append(f"  类型: {self._html_escape(issue.issue_type)}")
            lines.append(f"  说明: {self._html_escape(issue.message)}")
            if issue.fix_action:
                lines.append(f"  修复动作: {self._html_escape(self._format_fix_action(issue.fix_action))}")
            lines.append("")

        lines.append("</pre>")
        return "\n".join(lines)

    def _html_escape(self, text: str) -> str:
        """转义HTML特殊字符"""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _format_favicon_cache_summary(self) -> str:
        try:
            from core.favicon_cache import get_favicon_cache_stats

            stats = get_favicon_cache_stats(self.data_manager.data)
            return (
                "缓存\n"
                f"  网页图标: {stats.get('total_files', 0)} 个，{stats.get('total_size_mb', 0)} MB\n"
                f"  未使用: {stats.get('unused_files', 0)} 个，{stats.get('unused_size_mb', 0)} MB"
            )
        except Exception as exc:
            return f"缓存\n  网页图标: 无法读取 ({exc})"

    def _sorted_issues(self, issues):
        severity_rank = {"error": 0, "warn": 1, "unknown": 2, "debug": 3, "ok": 4}
        return sorted(
            issues,
            key=lambda issue: (
                severity_rank.get(str(issue.severity).lower(), 9),
                0 if issue.fix_action else 1,
                issue.folder_name or issue.folder_id,
                issue.shortcut_name or issue.shortcut_id,
                issue.issue_type,
            ),
        )

    def _count_by_severity(self, issues):
        counts = {"error": 0, "warn": 0, "debug": 0}
        for issue in issues:
            key = str(issue.severity).lower()
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _format_fix_action(self, action: str) -> str:
        labels = {
            "clear_icon": "清除失效图标路径",
            "delete_shortcut": "删除该图标",
            "clear_working_dir": "清空失效工作目录",
            "disable_folder_sync": "关闭该分类自动同步",
            "disable_shortcut": "禁用该快捷方式",
        }
        return labels.get(action, action)

    def closeEvent(self, event):
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
        if self._cache_clean_thread and self._cache_clean_thread.isRunning():
            self._cache_clean_thread.quit()
            self._cache_clean_thread.wait(2000)
        super().closeEvent(event)
