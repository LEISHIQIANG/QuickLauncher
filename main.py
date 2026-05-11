"""
QuickLauncher - 快捷启动器
主入口文件
"""

import sys
import os
import traceback
import logging
from datetime import datetime

# 确保项目根目录在 sys.path 中（双击运行时工作目录可能不是项目根目录）
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from bootstrap.dpi import setup_dpi_awareness
setup_dpi_awareness()

from bootstrap.logging_init import get_log_dir, setup_logging, setup_faulthandler

def _sanitize_gui_env():
    for k in list(os.environ.keys()):
        if k.upper().startswith("PYTHON"):
            os.environ.pop(k, None)
    for k in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
        os.environ.pop(k, None)

_sanitize_gui_env()
log_dir = get_log_dir()
log_file, logger = setup_logging(log_dir)
setup_faulthandler(log_dir)

from core.error_handler import safe_execute

safe_execute(
    lambda: os.environ.setdefault("PYTHONUTF8", "1"),
    "设置PYTHONUTF8环境变量失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)
safe_execute(
    lambda: os.environ.setdefault("PYTHONIOENCODING", "utf-8"),
    "设置PYTHONIOENCODING环境变量失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)
safe_execute(
    lambda: os.environ.__setitem__("QT_AUTO_SCREEN_SCALE_FACTOR", "0"),
    "设置QT_AUTO_SCREEN_SCALE_FACTOR失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)
safe_execute(
    lambda: os.environ.__setitem__("QT_ENABLE_HIGHDPI_SCALING", "1"),
    "设置QT_ENABLE_HIGHDPI_SCALING失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)
safe_execute(
    lambda: os.environ.__setitem__("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough"),
    "设置QT_SCALE_FACTOR_ROUNDING_POLICY失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)
safe_execute(
    lambda: os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false"),
    "设置QT_LOGGING_RULES失败",
    exceptions=(OSError, ValueError),
    log_level="debug"
)


_tray_app = None
_server = None
_pending_show_config = False


def get_tray_app():
    return _tray_app


def show_config_window_direct() -> bool:
    global _tray_app
    if _tray_app is not None:
        try:
            from qt_compat import QTimer
            QTimer.singleShot(0, _tray_app._show_config)
            return True
        except Exception as e:
            logger.error(f"直接显示配置窗口失败: {e}")
    return False


def _native_error_box(title: str, text: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception as e:
        logger.debug("ignored startup exception %s: %s", 2, e)


def main():
    global _tray_app, _server, _pending_show_config

    logger.info(f"QuickLauncher 启动 - {datetime.now()}")

    try:
        root_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        if getattr(sys, "frozen", False):
            try:
                import json as _json
                _cfg_path = os.path.join(root_dir, "config", "data.json")
                _auto = False
                if os.path.isfile(_cfg_path):
                    with open(_cfg_path, "r", encoding="utf-8") as _f:
                        _auto = _json.load(_f).get("settings", {}).get("auto_start", False)
                from core.auto_start_manager import _ensure_auto_start
                _ensure_auto_start(_auto)
            except Exception as e:
                logger.debug(f"自启动检查失败（可忽略）: {e}")

        from bootstrap.venv import maybe_reexec_in_venv
        maybe_reexec_in_venv(root_dir)

        logger.debug(f"Python: {sys.executable}")

        from bootstrap.deps import bootstrap_requirements
        bootstrap_requirements(root_dir, logger, _native_error_box)

        from qt_compat import QApplication, QLocalServer, QLocalSocket, setup_high_dpi, QT_LIB, QTimer, exec_app
        logger.info(f"Qt binding: {QT_LIB}")

        setup_high_dpi()
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setStyle("Fusion")
        app.setStyleSheet("""
            QToolTip {
                background: rgba(44, 44, 48, 240);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)

        try:
            from qt_compat import QFont
            default_font = QFont("Microsoft YaHei", 9)
            default_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            default_font.setWeight(QFont.Weight.Normal)
            default_font.setKerning(True)
            app.setFont(default_font)
            logger.info(f"应用字体设置为: {default_font.family()}, {default_font.pointSize()}pt")
        except Exception as e:
            logger.warning(f"设置默认字体失败: {e}")
            try:
                app.setFont(QFont("Microsoft YaHei", 9))
            except Exception as e:
                logger.debug("ignored startup exception %s: %s", 4, e)

        server_name = "QuickLauncherInstance_v3"

        from bootstrap.ipc import try_connect_existing
        if try_connect_existing(server_name):
            logger.info("已有实例运行，唤起设置窗口后退出")
            return 0

        from bootstrap.ipc import create_ipc_server
        _server, _ipc_pending = create_ipc_server(app, server_name, lambda: _tray_app._show_config if _tray_app else None)

        try:
            app.processEvents()
            if getattr(sys, 'frozen', False):
                import time
                time.sleep(0.05)
                app.processEvents()
        except Exception as e:
            logger.debug("ignored startup exception %s: %s", 5, e)

        logger.info("启动托盘应用...")
        from ui.tray_app import TrayApp
        _tray_app = TrayApp()
        logger.info("托盘应用启动成功")

        try:
            from core import APP_VERSION
            from core.data_models import DEFAULT_SPECIAL_APPS
            _version_marker = _tray_app.data_manager.app_dir / ".special_apps_merged_version"
            _last_merged = ""
            if _version_marker.exists():
                try:
                    _last_merged = _version_marker.read_text(encoding="utf-8").strip()
                except Exception as e:
                    logger.debug("ignored startup exception %s: %s", 6, e)
            if _last_merged != APP_VERSION:
                _settings = _tray_app.data_manager.get_settings()
                _user_apps = list(_settings.special_apps or [])
                _added = [a for a in DEFAULT_SPECIAL_APPS if a not in _user_apps]
                if _added:
                    _tray_app.data_manager.update_settings(special_apps=_user_apps + _added)
                    logger.info(f"新版本合并特殊应用列表，新增: {_added}")
                try:
                    _version_marker.write_text(APP_VERSION, encoding="utf-8")
                except Exception as e:
                    logger.debug("ignored startup exception %s: %s", 7, e)
        except Exception as e:
            logger.debug(f"合并特殊应用列表失败（可忽略）: {e}")

        try:
            from core import register_callback
            register_callback('show_config_window', _tray_app.show_config_signal.emit)
            logger.debug("已注册 show_config_window 回调")
        except Exception as e:
            logger.warning(f"注册回调失败: {e}")

        if _ipc_pending.get('show_config') or _pending_show_config:
            _pending_show_config = False
            QTimer.singleShot(50, _tray_app._show_config)

        if getattr(sys, "frozen", False):
            try:
                from core.auto_start_manager import is_auto_start_enabled
                _ts_enabled = is_auto_start_enabled()
                _cfg_settings = _tray_app.data_manager.get_settings()
                if getattr(_cfg_settings, 'auto_start', False) != _ts_enabled:
                    _tray_app.data_manager.update_settings(auto_start=_ts_enabled)
                    logger.info(f"同步自启动状态: {_ts_enabled}")
            except Exception as e:
                logger.debug(f"同步自启动状态失败（可忽略）: {e}")

        settings = _tray_app.data_manager.get_settings()
        if getattr(settings, 'show_on_startup', True):
            logger.info("启动时显示设置窗口...")
            QTimer.singleShot(100, _tray_app._show_config)
        else:
            logger.info("静默启动")

        logger.debug("进入事件循环")
        result = exec_app(app)
        logger.info(f"程序退出，返回码: {result}")
        return result

    except Exception as e:
        logger.error(f"启动失败: {e}\n{traceback.format_exc()}")
        try:
            from qt_compat import QApplication
            from ui.styles.themed_messagebox import ThemedMessageBox
            if not QApplication.instance():
                QApplication(sys.argv)
            ThemedMessageBox.critical(None, "启动失败", f"程序启动失败\n\n{e}\n\n详情请查看日志:\n{log_file}")
        except Exception as dialog_error:
            logger.debug("startup themed error dialog failed: %s", dialog_error)
            _native_error_box("QuickLauncher 启动失败", f"程序启动失败:\n{e}\n\n详情请查看日志:\n{log_file}")
        return 1


def _parse_autostart_cli_args(start_index: int = 3):
    from core.auto_start_manager import HELPER_TARGET_ARG, HELPER_TARGET_ARGS_ARG, HELPER_TARGET_CWD_ARG
    target_exe = target_args = target_cwd = ""
    for arg, attr in [(HELPER_TARGET_ARG, 'target_exe'), (HELPER_TARGET_ARGS_ARG, 'target_args'), (HELPER_TARGET_CWD_ARG, 'target_cwd')]:
        if arg in sys.argv[start_index:]:
            try:
                idx = sys.argv.index(arg, start_index)
                if idx + 1 < len(sys.argv):
                    locals()[attr]  # just reference
            except ValueError:
                pass
    # parse properly
    def _get(arg):
        try:
            i = sys.argv.index(arg, start_index)
            return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        except (ValueError, IndexError):
            return ""
    return _get(HELPER_TARGET_ARG), _get(HELPER_TARGET_ARGS_ARG), _get(HELPER_TARGET_CWD_ARG)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--install-service":
            from core.service_manager import enable_service_autostart
            success, msg = enable_service_autostart()
            print(msg)
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--configure-autostart":
            from core.auto_start_manager import (
                HELPER_ACTION_DISABLE, HELPER_ACTION_ENABLE, HELPER_EXIT_BAD_ARGS,
                disable_auto_start, enable_auto_start,
            )
            action = sys.argv[2] if len(sys.argv) > 2 else ""
            target_exe, target_args, target_cwd = _parse_autostart_cli_args(3)
            if action == HELPER_ACTION_ENABLE:
                success, msg = enable_auto_start(target_exe, target_args, target_cwd)
            elif action == HELPER_ACTION_DISABLE:
                success, msg = disable_auto_start()
            else:
                sys.exit(HELPER_EXIT_BAD_ARGS)
            print(msg)
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--autostart-helper":
            from core.auto_start_manager import HELPER_EXIT_BAD_ARGS, run_autostart_helper
            action = sys.argv[2] if len(sys.argv) > 2 else ""
            target_exe, target_args, target_cwd = _parse_autostart_cli_args(3)
            if not action:
                sys.exit(HELPER_EXIT_BAD_ARGS)
            sys.exit(run_autostart_helper(action, target_exe, target_args, target_cwd))
        elif sys.argv[1] == "--uninstall-service":
            from core.service_manager import disable_service_autostart
            success, msg = disable_service_autostart()
            print(msg)
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--service-mode":
            import servicemanager
            from core.windows_service import QuickLauncherService
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(QuickLauncherService)
            servicemanager.StartServiceCtrlDispatcher()
            sys.exit(0)

    try:
        sys.exit(main())
    except Exception as e:
        logger.error(f"主函数异常: {e}\n{traceback.format_exc()}")
        input("按回车键退出...")
        sys.exit(1)
