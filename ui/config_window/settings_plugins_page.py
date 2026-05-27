"""Plugin management settings page."""

from __future__ import annotations

import logging
import os

from core.i18n import tr
from core.plugin_manager import PLUGIN_PACKAGE_EXTENSION, is_plugin_package_path
from qt_compat import (
    QDialog,
    QEvent,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.tooltip_helper import install_tooltip
from ui.utils.font_manager import get_font_css_with_size

logger = logging.getLogger(__name__)


class SettingsPluginsPageMixin:
    def _setup_plugins_page(self, page):
        layout, group = page.add_group(tr("插件管理"))
        self._setup_plugin_package_drop_targets(page, group)

        # Description
        desc = QLabel(
            tr(
                "插件是扩展 QuickLauncher 功能的扩展模块。\n"
                "当前兼容模式：插件与主程序同权限运行，仅安装您信任的插件。\n"
                "插件声明权限为高风险提示，并非强权限隔离。\n"
                "插件目录: plugins/"
            )
        )
        desc.setObjectName("plugins_desc")
        desc.setWordWrap(True)
        desc.setMinimumWidth(0)
        desc.setStyleSheet(f"""
            {get_font_css_with_size(11, 400)}
            color: {self._get_desc_color()};
            padding: 0px;
            margin: 0px 0px 8px 0px;
        """)
        layout.addWidget(desc)

        # Plugin list area
        self._plugin_widgets_container = QWidget()
        self._plugin_layout = QVBoxLayout(self._plugin_widgets_container)
        self._plugin_layout.setContentsMargins(0, 8, 0, 0)
        self._plugin_layout.setSpacing(6)
        layout.addWidget(self._plugin_widgets_container)

        # Action buttons arranged in two rows to prevent horizontal overflow
        btn_layout1 = QHBoxLayout()
        btn_layout1.setSpacing(8)

        self.create_plugin_btn = QPushButton("新建开发插件...")
        self.create_plugin_btn.clicked.connect(self._on_create_plugin_clicked)
        install_tooltip(self.create_plugin_btn, "输入信息以创建并生成新的插件开发模板")
        btn_layout1.addWidget(self.create_plugin_btn)

        self.install_plugin_btn = QPushButton("安装插件 (.qlzip)...")
        self.install_plugin_btn.clicked.connect(self._on_install_plugin_clicked)
        install_tooltip(self.install_plugin_btn, "选择并安装 .qlzip 格式的插件包")
        btn_layout1.addWidget(self.install_plugin_btn)

        layout.addLayout(btn_layout1)

        btn_layout2 = QHBoxLayout()
        btn_layout2.setSpacing(8)

        self.refresh_btn = QPushButton("刷新插件列表")
        self.refresh_btn.clicked.connect(self._on_refresh_plugins)
        install_tooltip(self.refresh_btn, "重新扫描插件目录并刷新列表")
        btn_layout2.addWidget(self.refresh_btn)

        self.open_dir_btn = QPushButton("打开插件目录")
        self.open_dir_btn.clicked.connect(self._on_open_plugins_dir)
        install_tooltip(self.open_dir_btn, "在文件管理器中打开插件目录")
        btn_layout2.addWidget(self.open_dir_btn)

        layout.addLayout(btn_layout2)

        self._plugin_cards = {}

        # Initial load
        self._rebuild_plugin_list()

    def _setup_plugin_package_drop_targets(self, *widgets):
        targets = list(getattr(self, "_plugin_package_drop_targets", []) or [])
        for widget in widgets:
            if widget is None or widget in targets:
                continue
            try:
                widget.setAcceptDrops(True)
                widget.installEventFilter(self)
            except Exception:
                continue
            targets.append(widget)

            viewport = getattr(widget, "viewport", lambda: None)()
            if viewport is not None and viewport not in targets:
                try:
                    viewport.setAcceptDrops(True)
                    viewport.installEventFilter(self)
                    targets.append(viewport)
                except Exception:
                    pass

            content_widget = getattr(widget, "content_widget", None)
            if content_widget is not None and content_widget not in targets:
                try:
                    content_widget.setAcceptDrops(True)
                    content_widget.installEventFilter(self)
                    targets.append(content_widget)
                except Exception:
                    pass
        self._plugin_package_drop_targets = targets

    def eventFilter(self, obj, event):
        if obj in (getattr(self, "_plugin_package_drop_targets", []) or []):
            event_type = event.type()
            if event_type in (QEvent.DragEnter, QEvent.DragMove):
                if self._plugin_package_path_from_mime(event.mimeData()):
                    event.acceptProposedAction()
                    return True
                event.ignore()
                return True
            if event_type == QEvent.Drop:
                package_path = self._plugin_package_path_from_mime(event.mimeData())
                if package_path:
                    event.acceptProposedAction()
                    self._install_plugin_package(package_path)
                    return True
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def _plugin_package_path_from_mime(self, mime_data):
        if not mime_data or not mime_data.hasUrls():
            return ""
        urls = mime_data.urls()
        if len(urls) != 1:
            return ""
        url = urls[0]
        if not url.isLocalFile():
            return ""
        path = url.toLocalFile()
        if not is_plugin_package_path(path) or not os.path.isfile(path):
            return ""
        return path

    def _plugin_scroll_value(self):
        try:
            if hasattr(self, "page_plugins") and self.page_plugins:
                return self.page_plugins.verticalScrollBar().value()
        except Exception:
            pass
        return None

    def _restore_plugin_scroll(self, value):
        if value is None:
            return
        try:
            if hasattr(self, "page_plugins") and self.page_plugins:
                bar = self.page_plugins.verticalScrollBar()
                bar.setValue(max(bar.minimum(), min(value, bar.maximum())))
                if hasattr(self.page_plugins, "_scroll_pos"):
                    self.page_plugins._scroll_pos = float(bar.value())
                if hasattr(self.page_plugins, "_velocity"):
                    self.page_plugins._velocity = 0.0
        except Exception:
            pass

    def _rebuild_plugin_list(self, preserve_scroll=False):
        """Rebuild the plugin status list from the current plugin manager state."""
        scroll_value = self._plugin_scroll_value() if preserve_scroll else None
        self._plugin_widgets_container.setUpdatesEnabled(False)
        try:
            # Clear existing items
            while self._plugin_layout.count():
                item = self._plugin_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            self._plugin_cards = {}

            from core import plugin_manager

            if plugin_manager is None:
                label = QLabel("插件管理器未初始化")
                self._plugin_layout.addWidget(label)
                return

            plugins = plugin_manager.list_plugins()
            if not plugins:
                label = QLabel("没有找到任何插件")
                self._plugin_layout.addWidget(label)
                return

            for p in plugins:
                row = self._build_plugin_row(p)
                self._plugin_layout.addWidget(row)
                self._plugin_cards[p.manifest.id] = row

            if not preserve_scroll and hasattr(self, "page_plugins") and self.page_plugins:
                self.page_plugins.apply_theme(self.current_theme)
        finally:
            self._plugin_widgets_container.setUpdatesEnabled(True)
            self._restore_plugin_scroll(scroll_value)

    def _build_plugin_row(self, plugin_info):
        """Build a single plugin status card widget."""
        m = plugin_info.manifest
        plugin_id = m.id
        name = m.name
        version = m.version
        description = m.description
        author = m.author
        status = plugin_info.status
        error = plugin_info.error
        cmd_count = len(m.commands) if m.commands else 0
        permissions = m.permissions

        card = QWidget()
        card.setObjectName("PluginCard")

        # Apply theme-aware card styling
        if self.current_theme == "dark":
            bg_color = "rgba(255, 255, 255, 0.04)"
            border_color = "rgba(255, 255, 255, 0.08)"
            hover_bg = "rgba(255, 255, 255, 0.07)"
            text_color = "rgba(255, 255, 255, 0.9)"
            sub_text_color = "rgba(255, 255, 255, 0.65)"
        else:
            bg_color = "rgba(0, 0, 0, 0.02)"
            border_color = "rgba(0, 0, 0, 0.05)"
            hover_bg = "rgba(0, 0, 0, 0.04)"
            text_color = "rgba(28, 28, 30, 0.9)"
            sub_text_color = "rgba(28, 28, 30, 0.65)"

        card.setStyleSheet(f"""
            QWidget#PluginCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QWidget#PluginCard:hover {{
                background-color: {hover_bg};
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # ── Top Row Layout (Status + Name + Buttons) ──
        top_layout = QGridLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setHorizontalSpacing(8)
        top_layout.setVerticalSpacing(2)

        # Status badge / indicator
        is_quarantined = getattr(plugin_info, "quarantined", False)
        status_colors = {
            "enabled": "#4caf50",
            "disabled": "#888888",
            "loaded": "#ff9800",
            "error": "#f44336",
            "quarantined": "#ff5722",
        }
        status_texts = {
            "enabled": "已启用",
            "disabled": "已禁用",
            "loaded": "已加载",
            "error": "错误",
            "quarantined": "已隔离",
        }
        if is_quarantined:
            status = "quarantined"
        color = status_colors.get(status, "#888888")
        text = status_texts.get(status, status)

        name_display = name.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")
        author_display = (
            author.replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b") if author else ""
        )

        status_label = QLabel(f"● {text}")
        status_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
        status_label.setWordWrap(True)
        status_label.setMinimumWidth(0)
        top_layout.addWidget(status_label, 0, 0, QtCompat.AlignLeft | QtCompat.AlignVCenter)

        # Title: Name & Version
        name_label = QLabel(name_display)
        name_label.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 12px;")
        name_label.setWordWrap(True)
        name_label.setMinimumWidth(0)
        top_layout.addWidget(name_label, 0, 1, QtCompat.AlignLeft | QtCompat.AlignVCenter)

        version_label = QLabel(f"v{version}")
        version_label.setStyleSheet(f"color: {sub_text_color}; font-size: 10px; font-weight: 300;")
        version_label.setWordWrap(True)
        version_label.setMinimumWidth(0)
        top_layout.addWidget(version_label, 0, 2, QtCompat.AlignLeft | QtCompat.AlignVCenter)

        top_layout.setColumnStretch(0, 0)
        top_layout.setColumnStretch(1, 1)
        top_layout.setColumnStretch(2, 0)

        # Action buttons
        action_btn = QPushButton()

        # 2. Reload
        reload_btn = QPushButton("重载")
        reload_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_reload_plugin(pid))

        # 3. Open directory
        open_btn = QPushButton("打开目录")
        open_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_open_plugin_dir(pid))

        # 4. Delete
        delete_btn = QPushButton("删除")

        from ui.styles.style import Glassmorphism

        theme = getattr(self, "current_theme", "dark")
        common_style = Glassmorphism.get_action_button_style(theme, is_compact=True, is_delete=False)
        delete_style = Glassmorphism.get_action_button_style(theme, is_compact=False, is_delete=True)

        for btn in (action_btn, reload_btn, open_btn):
            btn.setStyleSheet(common_style)
            btn.setProperty("is_compact_btn", True)

        delete_btn.setStyleSheet(delete_style)
        delete_btn.setProperty("is_delete_btn", True)
        delete_btn.clicked.connect(lambda checked, pinfo=plugin_info: self._on_delete_plugin(pinfo))

        # Fixed button size for neat alignment
        for btn in (action_btn, reload_btn, open_btn, delete_btn):
            btn.setMinimumWidth(68)
            btn.setMinimumHeight(20)

        card_layout.addLayout(top_layout)

        # ── Secondary Info Area (Author, Description, Commands, Permissions, Error) ──
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(12, 0, 0, 0)
        info_layout.setSpacing(4)

        # 1. Author and Description
        desc_parts = []
        if author:
            desc_parts.append(f"作者: {author_display}")
        if description:
            desc_parts.append(description)

        if desc_parts:
            desc_text = " | ".join(desc_parts) if author and description else (description or f"作者: {author_display}")
            desc_lbl = QLabel(desc_text)
            desc_lbl.setWordWrap(True)
            desc_lbl.setMinimumWidth(0)
            desc_lbl.setStyleSheet(f"color: {sub_text_color}; font-size: 11px; line-height: 14px;")
            info_layout.addWidget(desc_lbl)

        # 2. Runtime mode
        mode_lbl = QLabel("🧩 运行模式: 兼容模式 (in-process, 未强隔离)")
        mode_lbl.setWordWrap(True)
        mode_lbl.setMinimumWidth(0)
        mode_lbl.setStyleSheet(f"color: {sub_text_color}; font-size: 11px;")
        info_layout.addWidget(mode_lbl)

        # 3. Commands & Permissions
        cmd_lbl = QLabel(f"📦 包含 {cmd_count} 个命令")
        cmd_lbl.setWordWrap(True)
        cmd_lbl.setMinimumWidth(0)
        cmd_lbl.setStyleSheet(f"color: {sub_text_color}; font-size: 11px;")
        info_layout.addWidget(cmd_lbl)

        # Permissions list
        if permissions:
            from core.plugin_manager import HIGH_RISK_PERMISSIONS

            has_high_risk = any(p in HIGH_RISK_PERMISSIONS for p in permissions)
            perm_text = ", ".join(permissions).replace("_", "_\u200b").replace("-", "-\u200b").replace("/", "/\u200b")

            if has_high_risk:
                perm_lbl = QLabel(f"⚠️ 声明权限 (高风险提醒): {perm_text}")
                perm_lbl.setStyleSheet("color: #ff9800; font-weight: 500; font-size: 11px;")
            else:
                perm_lbl = QLabel(f"🔑 声明权限: {perm_text}")
                perm_lbl.setStyleSheet(f"color: {sub_text_color}; font-size: 11px;")
            perm_lbl.setWordWrap(True)
            perm_lbl.setMinimumWidth(0)
            info_layout.addWidget(perm_lbl)

        # 4. Error message and failure details
        failure_count = getattr(plugin_info, "failure_count", 0)
        last_error_stage = getattr(plugin_info, "last_error_stage", "")
        if error:
            error_display = error.replace("_", "_​").replace("-", "-​").replace("/", "/​")
            err_parts = [f"❌ 错误: {error_display}"]
            if failure_count:
                err_parts.append(f"失败次数: {failure_count}")
            if last_error_stage:
                stage_labels = {"load": "加载", "command": "命令执行", "search": "搜索源", "unload": "卸载"}
                err_parts.append(f"阶段: {stage_labels.get(last_error_stage, last_error_stage)}")
            err_lbl = QLabel(" | ".join(err_parts))
            err_lbl.setWordWrap(True)
            err_lbl.setMinimumWidth(0)
            err_lbl.setStyleSheet(
                "color: #f44336; font-size: 11px; padding: 4px 8px; background-color: rgba(244, 67, 54, 0.08); border-radius: 4px; border: 1px dashed rgba(244, 67, 54, 0.2);"
            )
            info_layout.addWidget(err_lbl)

            # View error details button
            err_detail_btn = QPushButton("查看错误详情")
            err_detail_btn.setStyleSheet(common_style)
            err_detail_btn.setProperty("is_compact_btn", True)
            err_detail_btn.setMinimumWidth(68)
            err_detail_btn.setMinimumHeight(20)
            err_detail_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_view_error_details(pid))
            info_layout.addWidget(err_detail_btn)

        # 5. Trust level
        trust_text = plugin_info.manifest.trust_level
        trust_display = {"builtin": "系统内置", "local-trusted": "本地开发", "community-unverified": "社区未验证"}
        trust_lbl = QLabel(f"🔒 信任等级: {trust_display.get(trust_text, trust_text)}")
        trust_lbl.setWordWrap(True)
        trust_lbl.setMinimumWidth(0)
        trust_lbl.setStyleSheet(f"color: {sub_text_color}; font-size: 11px;")
        info_layout.addWidget(trust_lbl)

        # Add buttons layout to the bottom of the card to prevent horizontal overflow
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(12, 4, 0, 0)
        bottom_layout.addStretch()
        bottom_layout.addWidget(action_btn)
        bottom_layout.addWidget(reload_btn)
        bottom_layout.addWidget(open_btn)
        bottom_layout.addWidget(delete_btn)

        card_layout.addWidget(info_widget)
        card_layout.addLayout(bottom_layout)

        card._plugin_row_refs = {
            "status_label": status_label,
            "action_btn": action_btn,
        }
        self._update_plugin_card_state(card, plugin_info)

        return card

    def _update_plugin_card_state(self, card, plugin_info):
        refs = getattr(card, "_plugin_row_refs", None)
        if not refs:
            return
        status = plugin_info.status
        plugin_id = plugin_info.manifest.id
        is_quarantined = getattr(plugin_info, "quarantined", False)
        if is_quarantined:
            status = "quarantined"
        status_colors = {
            "enabled": "#4caf50",
            "disabled": "#888888",
            "loaded": "#ff9800",
            "error": "#f44336",
            "quarantined": "#ff5722",
        }
        status_texts = {
            "enabled": "已启用",
            "disabled": "已禁用",
            "loaded": "已加载",
            "error": "错误",
            "quarantined": "已隔离",
        }
        color = status_colors.get(status, "#888888")
        text = status_texts.get(status, status)
        failure_count = getattr(plugin_info, "failure_count", 0)
        if is_quarantined and failure_count:
            text = f"已隔离 ({failure_count}次失败)"
        refs["status_label"].setText(f"● {text}")
        refs["status_label"].setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")

        action_btn = refs["action_btn"]
        try:
            action_btn.clicked.disconnect()
        except Exception:
            pass
        if is_quarantined:
            action_btn.setText("清除隔离")
            action_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_clear_quarantine(pid))
        elif status == "enabled":
            action_btn.setText("禁用")
            action_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_disable_plugin(pid))
        else:
            action_btn.setText("启用")
            action_btn.clicked.connect(lambda checked, pid=plugin_id: self._on_enable_plugin(plugin_id))

    def _refresh_plugin_card_state(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        card = getattr(self, "_plugin_cards", {}).get(plugin_id)
        info = plugin_manager.get_plugin(plugin_id)
        if card is None or info is None:
            self._rebuild_plugin_list(preserve_scroll=True)
            return
        card.setUpdatesEnabled(False)
        try:
            self._update_plugin_card_state(card, info)
        finally:
            card.setUpdatesEnabled(True)

    def _on_enable_plugin(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        if plugin_manager.enable_plugin(plugin_id):
            self._refresh_plugin_card_state(plugin_id)
        else:
            info = plugin_manager.get_plugin(plugin_id)
            err = info.error if info else "未知错误"
            ThemedMessageBox.critical(self, "启用失败", f"无法启用插件 {plugin_id}: {err}")

    def _on_disable_plugin(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        plugin_manager.disable_plugin(plugin_id)
        self._refresh_plugin_card_state(plugin_id)

    def _on_clear_quarantine(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        reply = ThemedMessageBox.question(
            self,
            "清除隔离",
            f"确定要清除插件 {plugin_id} 的隔离状态？\n" "清除后插件将变为禁用状态，可重新启用。",
        )
        if not reply:
            return
        if plugin_manager.clear_quarantine(plugin_id):
            self._refresh_plugin_card_state(plugin_id)
            ThemedMessageBox.information(self, "已清除", f"插件 {plugin_id} 已解除隔离。")
        else:
            ThemedMessageBox.critical(self, "操作失败", f"无法清除插件 {plugin_id} 的隔离状态。")

    def _on_view_error_details(self, plugin_id):
        """Show recent plugin errors from plugin_errors.jsonl."""
        import json
        from pathlib import Path

        from qt_compat import QTextEdit

        try:
            config_dir = Path(str(self.data_manager.config_dir))
            errors_file = config_dir / "plugin_errors.jsonl"
            if not errors_file.exists():
                ThemedMessageBox.information(self, "错误详情", "暂无错误记录。")
                return

            # Guard against reading very large files on main thread
            max_read_bytes = 512 * 1024  # 512 KB
            raw = errors_file.read_bytes()
            if len(raw) > max_read_bytes:
                raw = raw[-max_read_bytes:]
            lines = raw.decode("utf-8", errors="replace").splitlines()
            plugin_errors = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get("plugin_id") == plugin_id:
                        plugin_errors.append(entry)
                except Exception:
                    continue

            if not plugin_errors:
                ThemedMessageBox.information(self, "错误详情", f"插件 {plugin_id} 暂无错误记录。")
                return

            # Show last 20 errors
            recent = plugin_errors[-20:]
            stage_labels = {"load": "加载", "command": "命令执行", "search": "搜索源", "unload": "卸载"}
            lines_out = []
            for entry in recent:
                time_str = entry.get("time", "?")
                stage = stage_labels.get(entry.get("stage", ""), entry.get("stage", ""))
                action = entry.get("action", "")
                error_msg = entry.get("error", "")
                trace = entry.get("trace", "")
                lines_out.append(f"[{time_str}] 阶段: {stage}" + (f" | 动作: {action}" if action else ""))
                lines_out.append(f"  错误: {error_msg}")
                if trace:
                    lines_out.append(f"  堆栈: {trace[:500]}")
                lines_out.append("")

            dialog = QDialog(self)
            dialog.setWindowTitle(f"错误详情 - {plugin_id}")
            dialog.resize(600, 400)
            layout = QVBoxLayout(dialog)
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText("\n".join(lines_out))
            layout.addWidget(text_edit)
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            dialog.exec()
        except Exception as exc:
            ThemedMessageBox.critical(self, "读取失败", f"无法读取错误记录: {exc}")

    def _on_reload_plugin(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        if plugin_manager.reload_plugin(plugin_id):
            self._rebuild_plugin_list(preserve_scroll=True)
        else:
            info = plugin_manager.get_plugin(plugin_id)
            err = info.error if info else "未知错误"
            ThemedMessageBox.critical(self, "重载失败", f"无法重载插件 {plugin_id}: {err}")

    def _on_open_plugin_dir(self, plugin_id):
        from core import plugin_manager

        if plugin_manager is None:
            return
        p = plugin_manager.get_plugin(plugin_id)
        if p and p.directory:
            try:
                os.startfile(p.directory)
            except Exception as e:
                logger.error("无法打开插件目录: %s", e)
                ThemedMessageBox.warning(self, "打开失败", f"无法打开插件目录:\n{e}")

    def _on_delete_plugin(self, plugin_info):
        m = plugin_info.manifest
        reply = ThemedMessageBox.question(
            self,
            "确定删除",
            f'您确定要彻底删除插件 "{m.name}" 吗？\n这将删除该插件的全部文件且无法恢复。',
        )
        if reply != ThemedMessageBox.Yes:
            return

        from core import plugin_manager

        if plugin_manager is None:
            return

        try:
            plugin_manager.delete_plugin_files(m.id)
            self._rebuild_plugin_list(preserve_scroll=True)
            ThemedMessageBox.information(self, "删除成功", f'插件 "{m.name}" 已被成功删除。')
        except Exception as e:
            logger.error("删除插件目录失败: %s", e)
            ThemedMessageBox.critical(self, "删除失败", f"删除插件文件失败:\n{e}")

    def _on_refresh_plugins(self):
        """Re-scan the plugins directory and rebuild the list."""
        from core import plugin_manager

        if plugin_manager is None:
            return
        # Preserve enabled state: reload each enabled plugin individually
        # rather than disable-all/scan/enable-all which risks leaving
        # previously-enabled plugins in disabled state on re-enable failure.
        previous_enabled = {p.manifest.id for p in plugin_manager.list_plugins() if p.status == "enabled"}
        plugin_manager.scan_plugins()
        plugin_manager.auto_enable(list(previous_enabled))
        self._rebuild_plugin_list(preserve_scroll=True)

    def _on_open_plugins_dir(self):
        """Open the plugins directory in Explorer."""
        from core import plugin_manager

        if plugin_manager is None:
            return
        try:
            os.startfile(plugin_manager.plugins_dir)
        except Exception as e:
            logger.error("无法打开插件目录: %s", e)

    def _on_create_plugin_clicked(self):
        if getattr(self, "_plugin_create_dialog_active", False):
            return
        self._plugin_create_dialog_active = True
        from core import plugin_manager

        if plugin_manager is None:
            self._plugin_create_dialog_active = False
            ThemedMessageBox.warning(self, "错误", "插件管理器未初始化！")
            return

        dialog = PluginCreateDialog(self, self.current_theme)
        try:
            if not dialog.exec_():
                return
        finally:
            self._plugin_create_dialog_active = False

        plugin_id = dialog.plugin_id
        plugin_dir = os.path.join(plugin_manager.plugins_dir, plugin_id)
        if os.path.exists(plugin_dir):
            ThemedMessageBox.warning(self, "创建失败", f"插件目录已存在: {plugin_id}")
            return

        try:
            from core.plugin_template import write_plugin_template

            write_plugin_template(
                plugin_dir,
                plugin_id,
                dialog.plugin_name,
                dialog.plugin_author,
                dialog.plugin_description,
            )

            # Preserve enabled state: save and restore after scan
            previous_enabled = {p.manifest.id for p in plugin_manager.list_plugins() if p.status == "enabled"}
            plugin_manager.scan_plugins()
            plugin_manager.auto_enable(list(previous_enabled))
            self._rebuild_plugin_list(preserve_scroll=True)

            # Show success message
            ThemedMessageBox.information(
                self,
                "新建成功",
                f'插件 "{dialog.plugin_name}" 模板已成功创建于 plugins/{plugin_id}/。\n即将打开该目录以供编辑。',
            )

            # Open directory
            try:
                os.startfile(plugin_dir)
            except Exception:
                pass

        except Exception as e:
            logger.error("新建开发插件失败: %s", e, exc_info=True)
            ThemedMessageBox.critical(self, "错误", f"新建开发插件失败:\n{e}")

    def _on_install_plugin_clicked(self):
        from core import plugin_manager

        if plugin_manager is None:
            ThemedMessageBox.warning(self, "错误", "插件管理器未初始化！")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择插件安装包",
            "",
            f"QuickLauncher 插件包 (*{PLUGIN_PACKAGE_EXTENSION})",
        )
        if not file_path:
            return

        self._install_plugin_package(file_path)

    def _install_plugin_package(self, file_path):
        from core import plugin_manager

        if plugin_manager is None:
            ThemedMessageBox.warning(self, "错误", "插件管理器未初始化！")
            return

        try:
            previous_enabled = {p.manifest.id for p in plugin_manager.list_plugins() if p.status == "enabled"}
            plugin_id = plugin_manager.install_from_package(
                file_path,
                on_overwrite=lambda name: (
                    ThemedMessageBox.question(
                        self,
                        "插件已存在",
                        f'插件 "{name}" 已经存在。\n是否覆盖安装并替换已有文件？',
                    )
                    == ThemedMessageBox.Yes
                ),
            )
        except ValueError as e:
            ThemedMessageBox.critical(self, "安装失败", f"无法安装插件:\n{e}")
            return

        if plugin_id is None:
            return  # user declined overwrite

        # Success: scan & rebuild, preserving enabled state except the new plugin,
        # which is enabled through the interactive risk-confirmation path below.
        plugin_manager.scan_plugins()
        previous_enabled.discard(plugin_id)
        plugin_manager.auto_enable(list(previous_enabled))

        enabled = plugin_manager.enable_plugin(plugin_id, interactive=True)
        if not enabled:
            plugin_manager.save_enabled_state()
        self._rebuild_plugin_list(preserve_scroll=True)

        info = plugin_manager.get_plugin(plugin_id)
        plugin_name = info.manifest.name if info else plugin_id
        if enabled:
            ThemedMessageBox.information(
                self,
                "安装并启用成功",
                f'插件 "{plugin_name}" 已成功安装并启用。',
            )
        elif info and info.status == "error":
            ThemedMessageBox.warning(
                self,
                "安装成功但启用失败",
                f'插件 "{plugin_name}" 已安装，但启用失败:\n{info.error}',
            )
        else:
            ThemedMessageBox.information(
                self,
                "安装成功",
                f'插件 "{plugin_name}" 已安装，但尚未启用。',
            )


class PluginCreateDialog(QDialog):
    def __init__(self, parent=None, theme="dark"):
        super().__init__(parent)
        self.setWindowTitle("新建开发插件")
        self.setModal(True)
        self.setMinimumSize(340, 320)
        self.theme = theme

        from ui.styles.style import get_dialog_stylesheet

        self.setStyleSheet(get_dialog_stylesheet(theme))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_lbl = QLabel("创建新的插件开发模板")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(title_lbl)

        # ID
        layout.addWidget(QLabel("插件ID (仅限小写字母、数字、下划线和减号):"))
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("例如: my_plugin")
        self.id_edit.setFixedHeight(26)
        layout.addWidget(self.id_edit)

        # Name
        layout.addWidget(QLabel("插件显示名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如: 我的自定义插件")
        self.name_edit.setFixedHeight(26)
        layout.addWidget(self.name_edit)

        # Author
        layout.addWidget(QLabel("作者名称 (可选):"))
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("例如: 开发者名字")
        self.author_edit.setFixedHeight(26)
        layout.addWidget(self.author_edit)

        # Description
        layout.addWidget(QLabel("插件描述 (可选):"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("一句话描述插件功能...")
        self.desc_edit.setFixedHeight(26)
        layout.addWidget(self.desc_edit)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(8)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setFixedHeight(24)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("创建")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._on_ok)
        self.ok_btn.setFixedHeight(24)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def _on_ok(self):
        import re

        plugin_id = self.id_edit.text().strip()
        if not plugin_id:
            ThemedMessageBox.warning(self, "输入错误", "插件ID不能为空！")
            return
        if not re.match(r"^[a-z0-9_-]+$", plugin_id):
            ThemedMessageBox.warning(self, "输入错误", "插件ID只能包含小写字母、数字、下划线 and 减号！")
            return

        self.plugin_id = plugin_id
        self.plugin_name = self.name_edit.text().strip() or plugin_id.replace("_", " ").title()
        self.plugin_author = self.author_edit.text().strip()
        self.plugin_description = self.desc_edit.text().strip() or "自定义开发的插件"
        self.accept()
