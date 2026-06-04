"""
QuickLauncher - 快捷启动器
主入口文件
"""

import os
import sys
import traceback
from datetime import datetime


# 确保项目根目录在 sys.path 中（双击运行时工作目录可能不是项目根目录）
def _ensure_project_root_on_path():
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _load_setup_dpi_awareness():
    _ensure_project_root_on_path()
    from bootstrap.dpi import setup_dpi_awareness

    return setup_dpi_awareness


def _load_logging_helpers():
    from bootstrap.logging_init import get_log_dir, setup_faulthandler, setup_logging

    return get_log_dir, setup_faulthandler, setup_logging


def _load_safe_execute():
    from core.error_handler import safe_execute

    return safe_execute


def _sanitize_gui_env():
    for k in list(os.environ.keys()):
        if k.upper().startswith("PYTHON"):
            os.environ.pop(k, None)
    for k in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
        os.environ.pop(k, None)


setup_dpi_awareness = _load_setup_dpi_awareness()
setup_dpi_awareness()

# 在主线程以 STA 模式初始化 COM，防止 Nuitka 打包后 QFileDialog 触发
# RPC_E_WRONG_THREAD (0x8001010e)。后台线程各自调用 CoInitialize 不影响此处。
try:
    import ctypes

    ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED = 0x2
except Exception:
    import logging

    logging.getLogger(__name__).debug("主线程 COM STA 初始化失败", exc_info=True)

_sanitize_gui_env()
get_log_dir, setup_faulthandler, setup_logging = _load_logging_helpers()
log_dir = get_log_dir()
log_file, logger = setup_logging(log_dir)
setup_faulthandler(log_dir)

safe_execute = _load_safe_execute()

safe_execute(
    lambda: os.environ.setdefault("PYTHONUTF8", "1"),
    "设置PYTHONUTF8环境变量失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
)
safe_execute(
    lambda: os.environ.setdefault("PYTHONIOENCODING", "utf-8"),
    "设置PYTHONIOENCODING环境变量失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
)
safe_execute(
    lambda: os.environ.__setitem__("QT_AUTO_SCREEN_SCALE_FACTOR", "0"),
    "设置QT_AUTO_SCREEN_SCALE_FACTOR失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
)
safe_execute(
    lambda: os.environ.__setitem__("QT_ENABLE_HIGHDPI_SCALING", "1"),
    "设置QT_ENABLE_HIGHDPI_SCALING失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
)
safe_execute(
    lambda: os.environ.__setitem__("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough"),
    "设置QT_SCALE_FACTOR_ROUNDING_POLICY失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
)
safe_execute(
    lambda: os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false"),
    "设置QT_LOGGING_RULES失败",
    exceptions=(OSError, ValueError),
    log_level="debug",
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
    if os.environ.get("QL_SAFE_MODE"):
        logger.warning("安全模式已启用：插件/钩子/更新/自定义背景已禁用")

    # Clean up cached command wrapper scripts from previous session
    try:
        from core.shortcut_command_exec import CommandExecutionMixin

        CommandExecutionMixin._cleanup_cmd_cache()
        logger.debug("已清理命令缓存目录")
    except Exception:
        logger.debug("清理命令缓存目录失败", exc_info=True)

    try:
        root_dir = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__))
        )
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        if getattr(sys, "frozen", False):
            try:
                import json as _json

                _cfg_path = os.path.join(root_dir, "config", "data.json")
                _auto = False
                if os.path.isfile(_cfg_path):
                    with open(_cfg_path, encoding="utf-8") as _f:
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

        try:
            from core.windows_uipi import format_process_elevation_status

            logger.info("启动权限状态: %s", format_process_elevation_status())
        except Exception as e:
            logger.debug("启动权限状态检测失败（可忽略）: %s", e)

        from qt_compat import QT_LIB, QApplication, QTimer, exec_app, setup_high_dpi

        logger.info(f"Qt binding: {QT_LIB}")

        setup_high_dpi()
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setStyle("Fusion")

        try:
            from core.shortcut_command_exec import init_main_thread_invoker

            init_main_thread_invoker()
            logger.debug("已初始化主线程 UI 命令调度器")
        except Exception as e:
            logger.warning(f"初始化主线程调度器失败: {e}")
        # QToolTip 样式由各窗口的玻璃拟态主题样式表动态控制，不再全局硬编码

        try:
            from ui.utils.font_manager import get_qfont

            default_font = get_qfont(13)
            app.setFont(default_font)
            logger.info(f"应用字体设置为: {default_font.family()}, {default_font.pointSize()}pt")
        except Exception as e:
            logger.warning(f"设置默认字体失败: {e}")
            try:
                from qt_compat import QFont

                app.setFont(QFont("Microsoft YaHei", 9))
            except Exception as e:
                logger.debug("ignored startup exception %s: %s", 4, e)

        server_name = "QuickLauncherInstance_v3"

        from bootstrap.ipc import try_connect_existing

        if try_connect_existing(server_name):
            logger.info("已有实例运行，唤起设置窗口后退出")
            return 0

        from bootstrap.ipc import create_ipc_server

        _server, _ipc_pending = create_ipc_server(
            app, server_name, lambda: _tray_app._show_config if _tray_app else None
        )

        try:
            app.processEvents()
            if getattr(sys, "frozen", False):
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

            callbacks = {
                "show_config_window": _tray_app.show_config_signal.emit,
                "quit_app": _tray_app._quit,
                "restart_app": _tray_app._restart,
                "show_log": _tray_app._show_log,
                "show_about": _tray_app._show_about,
                "show_help": _tray_app._show_slash_help,
                "show_diagnostics": _tray_app._show_diagnostics,
                "show_shortcut_health": _tray_app._show_shortcut_health,
                "show_config_history": _tray_app._show_config_history,
                "clean_icon_cache": _tray_app._clean_icon_cache_now,
                "reload_hooks": _tray_app._reload_hooks_now,
                "open_data_dir": _tray_app._open_data_dir,
                "open_install_dir": _tray_app._open_install_dir,
            }
            for name, callback in callbacks.items():
                register_callback(name, callback)
            logger.debug("已注册内置命令回调: %s", ", ".join(callbacks))
        except Exception as e:
            logger.warning(f"注册回调失败: {e}")

        if _ipc_pending.get("show_config") or _pending_show_config:
            _pending_show_config = False
            QTimer.singleShot(50, _tray_app._show_config)

        if getattr(sys, "frozen", False):
            try:
                from core.auto_start_manager import get_auto_start_check_result

                _ts_enabled, _ts_reason = get_auto_start_check_result()
                _cfg_settings = _tray_app.data_manager.get_settings()
                _cfg_auto_start = bool(getattr(_cfg_settings, "auto_start", False))
                if _ts_enabled and not _cfg_auto_start:
                    _tray_app.data_manager.update_settings(auto_start=True)
                    logger.info("检测到有效自启动任务，已同步配置为开启: %s", _ts_reason)
                elif _cfg_auto_start and not _ts_enabled:
                    _tray_app.data_manager.update_settings(auto_start=False)
                    logger.warning(
                        "配置要求开机自启，但任务缺失或定义已过期；已同步配置为关闭，避免误导用户: %s", _ts_reason
                    )
            except Exception as e:
                logger.debug(f"同步自启动状态失败（可忽略）: {e}")

        settings = _tray_app.data_manager.get_settings()
        if getattr(settings, "show_on_startup", True):
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
            from core.i18n import tr as _tr
            from qt_compat import QApplication
            from ui.styles.themed_messagebox import ThemedMessageBox

            if not QApplication.instance():
                QApplication(sys.argv)
            ThemedMessageBox.critical(
                None,
                _tr("启动失败"),
                _tr("程序启动失败\n\n{error}\n\n详情请查看日志:\n{log_file}", error=e, log_file=log_file),
            )
        except Exception as dialog_error:
            logger.debug("startup themed error dialog failed: %s", dialog_error)
            _native_error_box("QuickLauncher 启动失败", f"程序启动失败:\n{e}\n\n详情请查看日志:\n{log_file}")
        return 1


def _parse_autostart_cli_args(start_index: int = 3):
    from core.auto_start_manager import HELPER_TARGET_ARG, HELPER_TARGET_ARGS_ARG, HELPER_TARGET_CWD_ARG

    def _get(arg):
        try:
            i = sys.argv.index(arg, start_index)
            return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        except (ValueError, IndexError):
            return ""

    return _get(HELPER_TARGET_ARG), _get(HELPER_TARGET_ARGS_ARG), _get(HELPER_TARGET_CWD_ARG)


def _run_plugin_helper_from_argv(argv: list[str]) -> int:
    """Run a plugin helper script in a clean child QuickLauncher process."""

    import runpy

    if len(argv) < 3:
        print("missing plugin helper script", file=sys.stderr)
        return 2

    script_path = os.path.abspath(argv[2])
    site_paths: list[str] = []
    helper_args: list[str] = []
    i = 3
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            helper_args = argv[i + 1 :]
            break
        if arg == "--plugin-site" and i + 1 < len(argv):
            site_paths.append(os.path.abspath(argv[i + 1]))
            i += 2
            continue
        print(f"unknown plugin helper argument: {arg}", file=sys.stderr)
        return 2

    if not os.path.isfile(script_path):
        print(f"plugin helper script not found: {script_path}", file=sys.stderr)
        return 2

    script_dir = os.path.dirname(script_path)
    search_paths = [script_dir, *site_paths]
    for path in reversed(search_paths):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    dll_dirs = [script_dir]
    for site_path in site_paths:
        dll_dirs.extend([site_path, os.path.join(site_path, "wx")])
    for dll_dir in dll_dirs:
        if not os.path.isdir(dll_dir):
            continue
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory:
            try:
                add_dll_directory(dll_dir)
            except OSError:
                pass

    sys.argv = [script_path, *helper_args]
    try:
        runpy.run_path(script_path, run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # --safe-mode: disable plugins, hooks, update checks, custom background
    if "--safe-mode" in sys.argv:
        os.environ["QL_SAFE_MODE"] = "1"
        sys.argv = [a for a in sys.argv if a != "--safe-mode"]
        print("[safe-mode] 已启用安全模式：插件/钩子/更新/自定义背景已禁用")

    if len(sys.argv) > 1:
        if sys.argv[1] == "--file-dialog":
            # 独立进程运行文件对话框
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            try:
                from ui.utils.file_dialog_subprocess import main as run_dialog

                run_dialog()
            except Exception as e:
                import json

                print(json.dumps({"error": str(e)}))
            sys.exit(0)
        elif sys.argv[1] == "--plugin-helper":
            sys.exit(_run_plugin_helper_from_argv(sys.argv))
        elif sys.argv[1] == "--install-service":
            from core.service_manager import enable_service_autostart

            success, msg = enable_service_autostart()
            print(msg)
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--configure-autostart":
            from core.auto_start_manager import (
                HELPER_ACTION_DISABLE,
                HELPER_ACTION_ENABLE,
                HELPER_EXIT_BAD_ARGS,
                disable_auto_start,
                enable_auto_start,
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
        elif sys.argv[1] == "--autostart-launch":
            from core.auto_start_manager import HELPER_EXIT_BAD_ARGS, run_autostart_launcher

            target_exe, target_args, target_cwd = _parse_autostart_cli_args(2)
            if not target_exe:
                sys.exit(HELPER_EXIT_BAD_ARGS)
            sys.exit(run_autostart_launcher(target_exe, target_args, target_cwd))
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
