"""Icon check dialog."""

from __future__ import annotations

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
        super().__init__(tr("图标检查"), theme=theme, parent=parent)
        self.resize(380, 560)
        self._setup_ui()
        self._apply_content_theme()
        self.text.setHtml(tr("正在扫描图标、路径和命令风险..."))
        QTimer.singleShot(80, self.refresh)

    def _setup_ui(self):
        self.set_subtitle(tr("扫描缺失图标、失效路径、重复项、URL 和命令风险"))

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.text.setFont(font)
        self.content_layout.addWidget(self.text)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("重新扫描"))
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton(tr("复制报告"))
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        buttons.addWidget(self.copy_btn)

        self.fix_btn = QPushButton(tr("应用修复"))
        self.fix_btn.clicked.connect(self.apply_safe_fixes)
        buttons.addWidget(self.fix_btn)

        self.clean_cache_btn = QPushButton(tr("清理缓存"))
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
        self.text.setHtml(tr("正在扫描图标、路径和命令风险..."))
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
            self.text.setHtml(tr("扫描失败: {error}", error=error))
            return
        self.issues = self._sorted_issues(list(issues or []))
        self.fix_btn.setEnabled(any(issue.fix_action for issue in self.issues))
        self.clean_cache_btn.setEnabled(True)
        self.text.setHtml(self._format_issues())

    def apply_safe_fixes(self):
        fix_ids = [issue.id for issue in self.issues if issue.fix_action]
        if not fix_ids:
            return

        # 先展示修复预览，让用户确认
        previews = preview_health_fixes(self.data_manager, fix_ids)
        destructive = [p for p in previews if not p.safe]
        safe_items = [p for p in previews if p.safe]

        if previews:
            preview_lines = []
            if destructive:
                preview_lines.append(tr("⚠️ 以下操作不可逆：\n"))
                for p in destructive:
                    preview_lines.append(f"  • {p.description}")
                preview_lines.append("")
            if safe_items:
                preview_lines.append(tr("安全修复：\n"))
                for p in safe_items:
                    preview_lines.append(f"  • {p.description}")
            preview_text = "\n".join(preview_lines)

            confirm_msg = preview_text + "\n\n" + tr("确定要执行以上修复吗？")
            if destructive:
                result = ThemedMessageBox.question(
                    self,
                    tr("确认修复"),
                    confirm_msg,
                    ThemedMessageBox.Yes | ThemedMessageBox.No,
                )
                if result != ThemedMessageBox.Yes:
                    return
            else:
                result = ThemedMessageBox.question(
                    self,
                    tr("应用修复"),
                    confirm_msg,
                    ThemedMessageBox.Yes | ThemedMessageBox.No,
                )
                if result != ThemedMessageBox.Yes:
                    return

        result = apply_health_fixes(self.data_manager, fix_ids)
        self.refresh()
        skipped = result.get("skipped", 0)
        failed = result.get("failed", 0)
        detail = tr("已应用 {count} 项修复。", count=result.get("applied", 0))
        if skipped:
            detail += tr("\n已跳过 {skipped} 项被删除图标覆盖的重复修复。", skipped=skipped)
        if failed:
            detail += tr("\n有 {failed} 项修复失败，请重新扫描后查看报告。", failed=failed)
        ThemedMessageBox.information(
            self,
            tr("修复完成"),
            detail,
        )

    def clean_unused_favicon_cache(self):
        if self._cache_clean_thread and self._cache_clean_thread.isRunning():
            return
        self.clean_cache_btn.setEnabled(False)
        self.clean_cache_btn.setText(tr("清理中..."))
        self._cache_clean_thread = FaviconCacheCleanThread(self.data_manager)
        self._cache_clean_thread.finished_signal.connect(self._on_cache_clean_finished)
        self._cache_clean_thread.finished.connect(lambda: setattr(self, "_cache_clean_thread", None))
        self._cache_clean_thread.finished.connect(self._cache_clean_thread.deleteLater)
        self._cache_clean_thread.start()

    def _on_cache_clean_finished(self, stats: dict, error: str):
        self.clean_cache_btn.setText(tr("清理缓存"))
        self.clean_cache_btn.setEnabled(True)
        if error:
            ThemedMessageBox.warning(self, tr("清理失败"), tr("无法清理未使用图标缓存:\n{error}", error=error))
            return

        removed = int(stats.get("files_removed", stats.get("total_removed", 0)) or 0)
        freed = float(stats.get("size_freed_mb", stats.get("total_size_freed_mb", 0)) or 0)
        self.refresh()
        ThemedMessageBox.information(
            self,
            tr("清理完成"),
            tr("已清理 {removed} 个未使用的网页图标缓存，释放 {freed:.1f} MB。", removed=removed, freed=freed),
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
            return f'<pre style="font-family: Consolas, Courier New, monospace; font-size: 9pt;">{tr("未发现问题。")}\n\n{cache_summary}</pre>'

        counts = self._count_by_severity(self.issues)
        fixable_count = sum(1 for issue in self.issues if issue.fix_action)

        lines = ['<pre style="font-family: Consolas, Courier New, monospace; font-size: 9pt;">']
        lines.append(tr("<b>摘要</b>"))
        lines.append(f'  <span style="color: {severity_colors["error"]};">ERROR: {counts.get("error", 0)}</span>')
        lines.append(f'  <span style="color: {severity_colors["warn"]};">WARN : {counts.get("warn", 0)}</span>')
        lines.append(f'  <span style="color: {severity_colors["debug"]};">DEBUG: {counts.get("debug", 0)}</span>')
        lines.append(f"  可修复: {fixable_count}")
        lines.append(cache_summary)
        lines.append("")
        lines.append(tr("<b>明细</b>"))

        for issue in self.issues:
            target = issue.shortcut_name or issue.folder_name or issue.shortcut_id or issue.folder_id
            color = severity_colors.get(issue.severity.lower(), "#888888")
            lines.append(
                f'<span style="color: {color};">[{issue.severity.upper()}] {self._html_escape(issue.title)} - {self._html_escape(target)}</span>'
            )
            lines.append(f"  {tr('分类:')} {self._html_escape(issue.folder_name or issue.folder_id)}")
            lines.append(f"  {tr('类型:')} {self._html_escape(issue.issue_type)}")
            lines.append(f"  {tr('说明:')} {self._html_escape(issue.message)}")
            if issue.fix_action:
                lines.append(f"  {tr('修复动作:')} {self._html_escape(self._format_fix_action(issue.fix_action))}")
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
            return tr(
                "缓存\n"
                "  网页图标: {total_files} 个，{total_size_mb} MB\n"
                "  未使用: {unused_files} 个，{unused_size_mb} MB",
                total_files=stats.get("total_files", 0),
                total_size_mb=stats.get("total_size_mb", 0),
                unused_files=stats.get("unused_files", 0),
                unused_size_mb=stats.get("unused_size_mb", 0),
            )
        except Exception as exc:
            return tr("缓存\n  网页图标: 无法读取 ({exc})", exc=exc)

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
            "clear_icon": tr("清除失效图标路径"),
            "delete_shortcut": tr("删除该图标"),
            "clear_working_dir": tr("清空失效工作目录"),
            "disable_folder_sync": tr("关闭该分类自动同步"),
            "disable_shortcut": tr("禁用该快捷方式"),
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
