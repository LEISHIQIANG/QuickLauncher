"""Data import/export and reset actions for SettingsPanel."""

import logging
import os
import sys

from core.i18n import tr
from qt_compat import (
    QApplication,
    QtCompat,
    QThread,
    pyqtSignal,
)
from runtime_paths import app_executable, is_packaged_runtime
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

    def _is_thread_running(self, attr_name: str) -> bool:
        thread = getattr(self, attr_name, None)
        if thread is None:
            return False
        try:
            running = bool(thread.isRunning())
        except RuntimeError:
            setattr(self, attr_name, None)
            return False
        if not running:
            setattr(self, attr_name, None)
        return running

    def _clear_thread_if_current(self, attr_name: str, thread) -> None:
        if getattr(self, attr_name, None) is thread:
            setattr(self, attr_name, None)

    def _on_export_clicked(self):
        # Same as old settings
        logger.info("[导出配置] 按钮被点击, packaged=%s", is_packaged_runtime())
        if self._is_thread_running("export_thread"):
            return
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
            self.export_thread.finished.connect(
                lambda thread=self.export_thread: self._clear_thread_if_current("export_thread", thread)
            )

            def on_finished(success, msg):
                if not self._is_progress_dialog_alive(progress):
                    return
                progress.show_success(msg) if success else progress.show_failure(msg)

            self.export_thread.finished_signal.connect(on_finished)
            self.export_thread.start()
        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_import_clicked(self):
        logger.info("[导入配置] 按钮被点击, packaged=%s", is_packaged_runtime())
        if self._is_thread_running("import_thread"):
            return
        try:
            file_path, _ = get_open_file_name(self, "导入配置", "", "QuickLauncher 配置包 (*.qlpack)")
            if not file_path:
                return

            progress = CompactProgressDialog(self, "导入配置", self.data_manager.get_settings().theme)
            progress.show()

            self.import_thread = ImportThread(self.data_manager, file_path)
            self.import_thread.finished.connect(self.import_thread.deleteLater)
            self.import_thread.finished.connect(
                lambda thread=self.import_thread: self._clear_thread_if_current("import_thread", thread)
            )

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
        if self._is_thread_running("_backup_thread"):
            return
        try:
            from datetime import datetime

            default_name = f"QuickLauncher_FullBackup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            path, _ = get_save_file_name(self, "保存全量备份", default_name, "Zip Files (*.zip)")
            if not path:
                return

            class _BackupThread(QThread):
                finished_signal = pyqtSignal(bool)

                def __init__(self, data_manager, backup_path):
                    super().__init__()
                    self._dm = data_manager
                    self._path = backup_path

                def run(self):
                    try:
                        result = self._dm.backup_full_config(self._path)
                        self.finished_signal.emit(bool(result))
                    except Exception:
                        self.finished_signal.emit(False)

            QApplication.setOverrideCursor(QtCompat.WaitCursor)
            self._backup_thread = _BackupThread(self.data_manager, path)
            backup_thread = self._backup_thread

            def on_backup_done(success):
                QApplication.restoreOverrideCursor()
                self._clear_thread_if_current("_backup_thread", backup_thread)
                if success:
                    ThemedMessageBox.information(self, tr("备份成功"), tr("全量备份已保存至:\n{path}", path=path))
                else:
                    ThemedMessageBox.warning(self, tr("备份失败"), tr("无法创建备份文件，请检查日志。"))

            self._backup_thread.finished_signal.connect(on_backup_done)
            self._backup_thread.finished.connect(
                lambda thread=backup_thread: self._clear_thread_if_current("_backup_thread", thread)
            )
            self._backup_thread.start()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_restore_full_clicked(self):
        if self._is_thread_running("_restore_thread"):
            return
        path, _ = get_open_file_name(self, "选择全量备份文件", "", "Zip Files (*.zip)")
        if not path:
            return

        if not path.lower().endswith(".zip"):
            ThemedMessageBox.warning(self, tr("错误"), tr("请选择 .zip 格式的备份文件"))
            return

        result = ThemedMessageBox.question(
            self,
            "确认恢复",
            "确认要从备份恢复吗？\n\n此操作将覆盖当前所有配置、图标和背景图片。\n操作完成后程序将自动重启。",
            ThemedMessageBox.Yes | ThemedMessageBox.No,
        )

        if result == ThemedMessageBox.Yes:

            class _RestoreThread(QThread):
                finished_signal = pyqtSignal(bool)

                def __init__(self, data_manager, restore_path):
                    super().__init__()
                    self._dm = data_manager
                    self._path = restore_path

                def run(self):
                    try:
                        success = self._dm.restore_full_config(self._path)
                        self.finished_signal.emit(bool(success))
                    except Exception:
                        self.finished_signal.emit(False)

            QApplication.setOverrideCursor(QtCompat.WaitCursor)
            self._restore_thread = _RestoreThread(self.data_manager, path)
            restore_thread = self._restore_thread

            def on_restore_done(success):
                QApplication.restoreOverrideCursor()
                self._clear_thread_if_current("_restore_thread", restore_thread)
                if success:
                    report = getattr(self.data_manager, "get_last_import_report", lambda: {})()
                    if report.get("has_warnings"):
                        ThemedMessageBox.warning(
                            self, tr("导入提示"), tr("部分不安全内容已跳过，请查看日志或诊断信息。")
                        )
                    ThemedMessageBox.information(self, tr("恢复成功"), tr("配置已恢复，程序即将重启。"))
                    self._restart_application()
                else:
                    ThemedMessageBox.warning(self, tr("恢复失败"), tr("无法恢复备份，文件可能已损坏或格式不正确。"))

            self._restore_thread.finished_signal.connect(on_restore_done)
            self._restore_thread.finished.connect(
                lambda thread=restore_thread: self._clear_thread_if_current("_restore_thread", thread)
            )
            self._restore_thread.start()

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
                    tr("导出成功"),
                    tr("分享配置已导出至:\n{path}\n\n此配置可分享给其他用户使用", path=path),
                    max_width=320,
                )
            else:
                ThemedMessageBox.warning(self, tr("导出失败"), tr("无法导出分享配置，请检查日志。"))

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
                    ThemedMessageBox.warning(self, tr("导入提示"), tr("部分不安全内容已跳过，请查看日志或诊断信息。"))
                ThemedMessageBox.information(
                    self, "导入成功", "分享配置已导入到「导入图标」分类\n\n请重启应用以查看效果"
                )
                # 导入成功后需要刷新以显示新分类
                self.settings_changed.emit()
            else:
                ThemedMessageBox.warning(self, tr("导入失败"), tr("无法导入分享配置，文件可能已损坏或格式不正确。"))

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))

    def _on_config_history_clicked(self):
        """打开配置历史窗口。"""
        try:
            from ui.config_history_window import ConfigHistoryWindow

            window = getattr(self, "_config_history_window", None)
            if window is not None:
                try:
                    window.isVisible()
                except RuntimeError:
                    window = None
                    self._config_history_window = None

            if window is None:
                window = ConfigHistoryWindow(self.data_manager, parent=self)
                self._config_history_window = window
            else:
                try:
                    window.set_theme(self.data_manager.get_settings().theme)
                except Exception as exc:
                    logger.debug("设置配置历史窗口主题失败: %s", exc, exc_info=True)
                window.refresh()
            window.show()
            window.raise_()
            window.activateWindow()
        except Exception as e:
            ThemedMessageBox.warning(self, tr("打开失败"), tr("无法打开配置历史:\n{error}", error=e))

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
            progress.msg_label.setText(tr("正在清理数据..."))
            progress.ok_btn.setVisible(False)
        except Exception as exc:
            logger.debug("设置进度对话框失败: %s", exc, exc_info=True)
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
                        except Exception as exc:
                            logger.debug("发送进度信号失败: %s", exc, exc_info=True)

                    stats = self.data_manager.factory_reset(callback=on_progress)
                    self.finished_signal.emit(stats)
                except Exception as e:
                    self.finished_signal.emit({"error": str(e)})

        def on_progress_update(msg, pct):
            try:
                progress.msg_label.setText(msg)
                progress.progress_bar.setValue(int(pct * 100))
            except Exception as exc:
                logger.debug("更新进度显示失败: %s", exc, exc_info=True)

        def on_reset_finished(stats):
            try:
                progress.close()
            except Exception as exc:
                logger.debug("关闭进度对话框失败: %s", exc, exc_info=True)

            error = stats.get("error")
            if error:
                ThemedMessageBox.critical(self, tr("错误"), tr("清除所有配置失败:\n{error}", error=error))
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

            if is_packaged_runtime():
                # 打包后的exe：直接启动 exe
                exe_path = str(app_executable())
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

            QApplication.instance().quit()  # type: ignore[union-attr]

        except Exception as e:
            ThemedMessageBox.warning(self, tr("警告"), tr("自动重启失败，请手动重启应用。\n错误: {error}", error=e))
