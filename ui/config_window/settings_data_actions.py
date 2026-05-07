"""Data import/export and reset actions for SettingsPanel."""

import logging
import os
import sys
import shutil
import time
import winreg
from datetime import datetime

from ui.tooltip_helper import install_tooltip
from qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QFormLayout, QSlider, QSpinBox, QRadioButton, QButtonGroup,
    QLabel, QFrame, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QScrollArea, QMessageBox,
    QPainter, QPixmap, QColor, QPen, QBrush, QRect, QRectF, QDialog,
    QTimer, QIcon, QStackedWidget, Qt, QtCompat, pyqtSignal, PYQT_VERSION,
    QThread, QStyledItemDelegate, QSize, QKeySequence, QMenu, QAction,
    QComboBox, QPainterPath, exec_dialog, QPoint, QApplication
)
from core import APP_VERSION, DEFAULT_SPECIAL_APPS, ShortcutItem, ShortcutType
from core.app_scanner import AppScanner
from ui.config_window.settings_helpers import NumberedListDelegate, ProgressDialog, ExportThread, ImportThread
from ui.config_window.folder_panel import PopupMenu
from ui.styles.themed_messagebox import ThemedMessageBox
from ui.utils.font_manager import get_font_css_with_size

logger = logging.getLogger(__name__)


def CompactProgressDialog(*args, **kwargs):
    from ui.config_window.settings_panel import CompactProgressDialog as Dialog
    return Dialog(*args, **kwargs)

class SettingsDataActionsMixin:
    def _on_export_clicked(self):
        # Same as old settings
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "导出配置", "", "QuickLauncher 配置包 (*.qlpack)")
            if not file_path: return
            if not file_path.endswith('.qlpack'): file_path += '.qlpack'
            
            progress = CompactProgressDialog(self, "导出配置", self.data_manager.get_settings().theme)
            progress.show()
            
            self.export_thread = ExportThread(self.data_manager, file_path)
            self.export_thread.finished_signal.connect(lambda s, m: progress.show_success(m) if s else progress.show_failure(m))
            self.export_thread.start()
        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))
    def _on_import_clicked(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "QuickLauncher 配置包 (*.qlpack)")
            if not file_path: return
            
            progress = CompactProgressDialog(self, "导入配置", self.data_manager.get_settings().theme)
            progress.show()
            
            self.import_thread = ImportThread(self.data_manager, file_path)
            def on_finished(success, count, msg):
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
            path, _ = QFileDialog.getSaveFileName(
                self, "保存全量备份", default_name, "Zip Files (*.zip)"
            )
            if not path:
                return

            if self.data_manager.backup_full_config(path):
                ThemedMessageBox.information(self, "备份成功", f"全量备份已保存至:\n{path}")
            else:
                ThemedMessageBox.warning(self, "备份失败", "无法创建备份文件，请检查日志。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))
    def _on_restore_full_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择全量备份文件", "", "Zip Files (*.zip)"
        )
        if not path:
            return
            
        if not path.lower().endswith('.zip'):
             ThemedMessageBox.warning(self, "错误", "请选择 .zip 格式的备份文件")
             return

        theme = self.data_manager.get_settings().theme

        result = ThemedMessageBox.question(
            self,
            "确认恢复",
            "确认要从备份恢复吗？\n\n此操作将覆盖当前所有配置、图标和背景图片。\n操作完成后程序将自动重启。",
            ThemedMessageBox.Yes | ThemedMessageBox.No
        )

        if result == ThemedMessageBox.Yes:
            QApplication.setOverrideCursor(QtCompat.WaitCursor)
            try:
                success = self.data_manager.restore_full_config(path)
            except Exception:
                success = False
            QApplication.restoreOverrideCursor()

            if success:
                ThemedMessageBox.information(self, "恢复成功", "配置已恢复，程序即将重启。")
                self._restart_application()
            else:
                ThemedMessageBox.warning(self, "恢复失败", "无法恢复备份，文件可能已损坏或格式不正确。")
    def _on_export_shareable_clicked(self):
        """导出分享配置"""
        try:
            from datetime import datetime
            default_name = f"QuickLauncher_Share_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            path, _ = QFileDialog.getSaveFileName(
                self, "导出分享配置", default_name, "Zip Files (*.zip)"
            )
            if not path:
                return

            if self.data_manager.export_shareable_config(path):
                ThemedMessageBox.information(
                    self,
                    "导出成功",
                    f"分享配置已导出至:\n{path}\n\n此配置可分享给其他用户使用"
                )
            else:
                ThemedMessageBox.warning(self, "导出失败", "无法导出分享配置，请检查日志。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))
    def _on_import_shareable_clicked(self):
        """导入分享配置"""
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择分享配置文件", "", "Zip Files (*.zip)"
            )
            if not path:
                return

            if self.data_manager.import_shareable_config(path):
                ThemedMessageBox.information(
                    self,
                    "导入成功",
                    f"分享配置已导入到「导入图标」分类\n\n请重启应用以查看效果"
                )
                # 导入成功后需要刷新以显示新分类
                self.settings_changed.emit()
            else:
                ThemedMessageBox.warning(self, "导入失败", "无法导入分享配置，文件可能已损坏或格式不正确。")

        except Exception as e:
            ThemedMessageBox.critical(self, "错误", str(e))
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
            ThemedMessageBox.Yes | ThemedMessageBox.No
        )

        if result != ThemedMessageBox.Yes:
            return
        
        # 第二次确认（防止误操作）
        result2 = ThemedMessageBox.question(
            self,
            "最后确认",
            "🚨 最后确认\n\n所有数据将被永久删除，应用将自动重启。\n\n确定继续吗？",
            ThemedMessageBox.Yes | ThemedMessageBox.No
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
                "点击「确定」重启应用程序。"
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
        import sys
        import os
        import subprocess

        try:
            # 关闭 IPC 服务器，避免新进程单实例检查误判
            import main as _main_mod
            _srv = getattr(_main_mod, '_server', None)
            if _srv:
                _srv.close()
                _main_mod._server = None

            # 获取当前exe路径
            if getattr(sys, 'frozen', False):
                # 打包后的exe：直接启动 exe
                exe_path = sys.executable
                # 使用 CREATE_NEW_PROCESS_GROUP 和 DETACHED_PROCESS
                # CREATE_BREAKAWAY_FROM_JOB (0x01000000) 确保新进程不受当前作业对象限制
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000
                subprocess.Popen(
                    [exe_path],
                    creationflags=creationflags
                )
            else:
                # 开发模式：重启 Python 脚本
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                subprocess.Popen(
                    [exe_path, script_path],
                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                )

            # 退出当前进程
            from qt_compat import QApplication
            QApplication.instance().quit()
            
        except Exception as e:
            ThemedMessageBox.warning(self, "警告", f"自动重启失败，请手动重启应用。\n错误: {e}")
