"""Data import/export and reset actions for SettingsPanel."""

import logging
import os
import sys

from qt_compat import (
    QApplication,
    QtCompat,
    QThread,
    pyqtSignal,
)
from ui.config_window.settings_helpers import ExportThread, ImportThread, ProgressDialog
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.safe_file_dialog import get_open_file_name, get_save_file_name

logger = logging.getLogger(__name__)


def CompactProgressDialog(*args, **kwargs):
    from ui.config_window.settings_panel import CompactProgressDialog as Dialog

    return Dialog(*args, **kwargs)


class SettingsDataActionsMixin:
    def _is_progress_dialog_alive(self, progress) -> bool:
        return not getattr(progress, "_dialog_finished", False) and progress.isVisible()

    def _on_export_clicked(self):
        # Same as old settings
        logger.info(f"[导出配置] 按钮被点击, frozen={getattr(sys, 'frozen', False)}")
        try:
            file_path, _ = get_save_file_name(self, "导出配置", "", "QuickLauncher 配置包 (*.qlpack)")
            if not file_path:
                return
            if not file_path.endswith(".qlpack"):
                file_path += ".qlpack"

            progress = CompactProgressDialog(self, "导出配置", self.data_manager.get_settings().theme)
            progress.show()

            self.export_thread = ExportThread(self.data_manager, file_path)
            self.export_thread.finished.connect(self.export_thread.deleteLater)
            self.export_thread.finished.connect(lambda: setattr(self, "export_thread", None))

            def on_finished(success, msg):
                if not self._is_progress_dialog_alive(progress):
                    return
                progress.show_success(msg) if success else progress.show_failure(msg)

            self.export_thread.finished_signal.connect(on_finished)
            self.export_thread.start()
        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_import_clicked(self):
        logger.info(f"[导入配置] 按钮被点击, frozen={getattr(sys, 'frozen', False)}")
        try:
            file_path, _ = get_open_file_name(self, "导入配置", "", "QuickLauncher 配置包 (*.qlpack)")
            if not file_path:
                return

            progress = CompactProgressDialog(self, "导入配置", self.data_manager.get_settings().theme)
            progress.show()

            self.import_thread = ImportThread(self.data_manager, file_path)
            self.import_thread.finished.connect(self.import_thread.deleteLater)
            self.import_thread.finished.connect(lambda: setattr(self, "import_thread", None))

            def on_finished(success, count, msg):
                if not self._is_progress_dialog_alive(progress):
                    return
                if success:
                    progress.show_success(msg if count <= 0 else f"成功导入 {count} 项配置")
                    self.import_completed.emit(count)
                    try:
                        # Refresh settings
                        self._load_settings()
                        # Apply theme again to ensure styles
                        theme = self.data_manager.get_settings().theme
                        self.apply_theme(theme)
                        self.settings_changed.emit()
                    except Exception as e:
                        logger.debug("Failed to refresh settings after import: %s", e)
                else:
                    progress.show_failure(msg)

            self.import_thread.finished_signal.connect(on_finished)
            self.import_thread.start()
        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_backup_full_clicked(self):
        try:
            from datetime import datetime

            default_name = f"QuickLauncher_FullBackup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            path, _ = get_save_file_name(self, "保存全量备份", default_name, "Zip Files (*.zip)")
            if not path:
                return

            if self.data_manager.backup_full_config(path):
                ThemedMessageBox.information(self, "备份成功", f"全量备份已保存至:\n{path}")
            else:
                ThemedMessageBox.warning(self, "备份失败", "无法创建备份文件，请检查日志。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_restore_full_clicked(self):
        path, _ = get_open_file_name(self, "选择全量备份文件", "", "Zip Files (*.zip)")
        if not path:
            return

        if not path.lower().endswith(".zip"):
            ThemedMessageBox.warning(self, "错误", "请选择 .zip 格式的备份文件")
            return

        result = ThemedMessageBox.question(
            self,
            "确认恢复",
            "确认要从备份恢复吗？\n\n此操作将覆盖当前所有配置、图标和背景图片。\n操作完成后程序将自动重启。",
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )

        if result == ThemedMessageBox.Yes:
            QApplication.setOverrideCursor(QtCompat.WaitCursor)
            try:
                success = self.data_manager.restore_full_config(path)
            except Exception:
                success = False
            QApplication.restoreOverrideCursor()

            if success:
                report = getattr(self.data_manager, "get_last_import_report", lambda: {})()
                if report.get("has_warnings"):
                    ThemedMessageBox.warning(self, "导入提示", "部分不安全内容已跳过，请查看日志或诊断信息。")
                ThemedMessageBox.information(self, "恢复成功", "配置已恢复，程序即将重启。")
                self._restart_application()
            else:
                ThemedMessageBox.warning(self, "恢复失败", "无法恢复备份，文件可能已损坏或格式不正确。")

    def _on_export_shareable_clicked(self):
        """导出分享配置"""
        try:
            from datetime import datetime

            default_name = f"QuickLauncher_Share_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            path, _ = get_save_file_name(self, "导出分享配置", default_name, "Zip Files (*.zip)")
            if not path:
                return

            if self.data_manager.export_shareable_config(path):
                ThemedMessageBox.information(
                    self,
                    "导出成功",
                    f"分享配置已导出至:\n{path}\n\n此配置可分享给其他用户使用",
                    max_width=320,
                )
            else:
                ThemedMessageBox.warning(self, "导出失败", "无法导出分享配置，请检查日志。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_import_shareable_clicked(self):
        """导入分享配置"""
        try:
            path, _ = get_open_file_name(self, "选择分享配置文件", "", "Zip Files (*.zip)")
            if not path:
                return

            if self.data_manager.import_shareable_config(path):
                report = getattr(self.data_manager, "get_last_import_report", lambda: {})()
                if report.get("has_warnings"):
                    ThemedMessageBox.warning(self, "导入提示", "部分不安全内容已跳过，请查看日志或诊断信息。")
                ThemedMessageBox.information(
                    self, "导入成功", "分享配置已导入到「导入图标」分类\n\n请重启应用以查看效果"
                )
                # 导入成功后需要刷新以显示新分类
                self.settings_changed.emit()
            else:
                ThemedMessageBox.warning(self, "导入失败", "无法导入分享配置，文件可能已损坏或格式不正确。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_config_history_clicked(self):
        """打开配置历史窗口。"""
        try:
            from ui.config_history_window import ConfigHistoryWindow

            if not hasattr(self, "_config_history_window") or self._config_history_window is None:
                self._config_history_window = ConfigHistoryWindow(self.data_manager, parent=self)
            else:
                try:
                    self._config_history_window.set_theme(self.data_manager.get_settings().theme)
                except Exception:
                    pass
                self._config_history_window.refresh()
            self._config_history_window.show()
            self._config_history_window.raise_()
            self._config_history_window.activateWindow()
        except Exception as e:
            ThemedMessageBox.warning(self, "打开失败", f"无法打开配置历史:\n{e}")

    def _on_factory_reset_clicked(self):
        """处理清除所有配置按钮点击"""
        try:
            theme = self.data_manager.get_settings().theme or "dark"
        except Exception:
            theme = "dark"

        # 第一次确认
        result = ThemedMessageBox.question(
            self,
            "清除所有配置",
            "⚠️ 确定要清除所有配置吗？\n\n"
            "此操作将删除以下所有数据：\n\n"
            "• 所有文件夹和快捷方式配置\n"
            "• 图标缓存文件\n"
            "• 开机自启设置\n"
            "• 所有个性化设置\n\n"
            "此操作不可撤销！",
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )

        if result != ThemedMessageBox.Yes:
            return

        # 第二次确认（防止误操作）
        result2 = ThemedMessageBox.question(
            self,
            "最后确认",
            "🚨 最后确认\n\n所有数据将被永久删除，应用将自动重启。\n\n确定继续吗？",
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )

        if result2 != ThemedMessageBox.Yes:
            return

        # 执行清除所有配置
        progress = ProgressDialog(self, "清除所有配置", theme=theme)
        try:
            progress.msg_label.setText("正在清理数据...")
            progress.ok_btn.setVisible(False)
        except Exception:
            pass
        progress.show()

        class _FactoryResetThread(QThread):
            finished_signal = pyqtSignal(dict)
            progress_signal = pyqtSignal(str, float)

            def __init__(self, data_manager):
                super().__init__()
                self.data_manager = data_manager

            def run(self):
                try:

                    def on_progress(msg, pct):
                        try:
                            self.progress_signal.emit(msg, pct)
                        except Exception:
                            pass

                    stats = self.data_manager.factory_reset(callback=on_progress)
                    self.finished_signal.emit(stats)
                except Exception as e:
                    self.finished_signal.emit({"error": str(e)})

        def on_progress_update(msg, pct):
            try:
                progress.msg_label.setText(msg)
                progress.progress_bar.setValue(int(pct * 100))
            except Exception:
                pass

        def on_reset_finished(stats):
            try:
                progress.close()
            except Exception:
                pass

            error = stats.get("error")
            if error:
                ThemedMessageBox.critical(self, "错误", f"清除所有配置失败:\n{error}")
                return

            # 显示完成信息
            ThemedMessageBox.information(
                self,
                "完成",
                f"✅ 清除所有配置完成\n\n"
                f"已清理:\n"
                f"• {stats.get('files_removed', 0)} 个文件\n"
                f"• {stats.get('dirs_removed', 0)} 个目录\n"
                f"• {stats.get('registry_keys_removed', 0)} 个注册表项\n\n"
                "点击「确定」重启应用程序。",
            )

            # 重启应用
            self._restart_application(theme=theme)

        thread = _FactoryResetThread(self.data_manager)
        thread.progress_signal.connect(on_progress_update)
        thread.finished_signal.connect(on_reset_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

        # 保存线程引用防止被回收
        self._factory_reset_thread = thread

    def _restart_application(self, theme: str = "light"):
        """重启应用程序

        Args:
            theme: 用于错误消息框的主题，默认为 "light"
        """
        import subprocess

        try:
            # 关闭 IPC 服务器，避免新进程单实例检查误判
            import main as _main_mod

            _srv = getattr(_main_mod, "_server", None)
            if _srv:
                _srv.close()
                _main_mod._server = None

            # 获取当前exe路径
            if getattr(sys, "frozen", False):
                # 打包后的exe：直接启动 exe
                exe_path = sys.executable
                # 使用 CREATE_NEW_PROCESS_GROUP 和 DETACHED_PROCESS
                # CREATE_BREAKAWAY_FROM_JOB (0x01000000) 确保新进程不受当前作业对象限制
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000
                subprocess.Popen([exe_path], creationflags=creationflags)
            else:
                # 开发模式：重启 Python 脚本
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                subprocess.Popen(
                    [exe_path, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
                )

            # 退出当前进程
            from qt_compat import QApplication

            QApplication.instance().quit()

        except Exception as e:
            ThemedMessageBox.warning(self, "警告", f"自动重启失败，请手动重启应用。\n错误: {e}")
