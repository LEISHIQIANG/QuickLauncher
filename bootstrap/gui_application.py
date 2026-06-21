"""
QuickLauncher - 快捷启动器
主入口文件
"""

import logging
import os
import sys
import time
import traceback
from datetime import datetime

from bootstrap.startup_tasks import (
    cleanup_stale_command_cache,
    merge_default_special_apps,
    process_startup_events,
    sync_autostart_setting_from_task,
    sync_frozen_autostart_from_config,
)
from runtime_paths import app_root


# 确保项目根目录在 sys.path 中（双击运行时工作目录可能不是项目根目录）
def _ensure_project_root_on_path():
    root = str(app_root())
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


logger = logging.getLogger(__name__)
log_file = ""


def _initialize_gui_environment() -> tuple[str, logging.Logger]:
    """Initialize DPI, COM, logging, and GUI environment only in GUI mode."""
    setup_dpi_awareness = _load_setup_dpi_awareness()
    setup_dpi_awareness()
    try:
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except (AttributeError, OSError):
        logger.debug("主线程 COM STA 初始化失败", exc_info=True)

    _sanitize_gui_env()
    get_log_dir, setup_faulthandler, setup_logging = _load_logging_helpers()
    log_dir = get_log_dir()
    initialized_log_file, initialized_logger = setup_logging(log_dir)
    setup_faulthandler(log_dir)
    safe_execute = _load_safe_execute()
    env_values = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "QT_AUTO_SCREEN_SCALE_FACTOR": "0",
        "QT_ENABLE_HIGHDPI_SCALING": "1",
        "QT_SCALE_FACTOR_ROUNDING_POLICY": "PassThrough",
        "QT_LOGGING_RULES": "qt.qpa.fonts.warning=false",
    }
    for key, value in env_values.items():
        safe_execute(
            lambda key=key, value=value: os.environ.__setitem__(key, value),
            f"设置{key}环境变量失败",
            exceptions=(OSError, ValueError),
            log_level="debug",
        )
    return initialized_log_file, initialized_logger


def _native_error_box(title: str, text: str):
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except (AttributeError, OSError) as e:
        logger.debug("ignored startup exception %s: %s", 2, e)


def main():
    global log_file, logger
    log_file, logger = _initialize_gui_environment()
    logger.info(f"QuickLauncher 启动 - {datetime.now()}")
    app_context = None
    if os.environ.get("QL_SAFE_MODE"):
        logger.warning("安全模式已启用：插件/钩子/更新/自定义背景已禁用")

    # Clean up cached command wrapper scripts from previous session
    cleanup_stale_command_cache(logger)

    try:
        root_dir = str(app_root())
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        sync_frozen_autostart_from_config(root_dir, logger)

        from bootstrap.venv import maybe_reexec_in_venv

        maybe_reexec_in_venv(root_dir)

        logger.debug(f"Python: {sys.executable}")

        from bootstrap.deps import bootstrap_requirements

        bootstrap_requirements(root_dir, logger, _native_error_box)

        try:
            from core.windows_uipi import format_process_elevation_status

            logger.info("启动权限状态: %s", format_process_elevation_status())
        except (ImportError, OSError, RuntimeError) as e:
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
        except (ImportError, RuntimeError) as e:
            logger.warning(f"初始化主线程调度器失败: {e}")
        # QToolTip 样式由各窗口的玻璃拟态主题样式表动态控制，不再全局硬编码

        try:
            from ui.utils.font_manager import get_qfont

            default_font = get_qfont(13)
            app.setFont(default_font)
            logger.info(f"应用字体设置为: {default_font.family()}, {default_font.pointSize()}pt")
        except (ImportError, OSError, RuntimeError) as e:
            logger.warning(f"设置默认字体失败: {e}")
            try:
                from qt_compat import QFont

                app.setFont(QFont("Microsoft YaHei", 9))
            except (ImportError, RuntimeError) as e:
                logger.debug("ignored startup exception %s: %s", 4, e)

        server_name = "QuickLauncherInstance_v3"

        from bootstrap.ipc import acquire_instance_mutex, create_ipc_server, try_connect_existing

        instance_mutex = acquire_instance_mutex(server_name)
        if instance_mutex is None:
            for _attempt in range(10):
                if try_connect_existing(server_name):
                    logger.info("已有实例运行，唤起设置窗口后退出")
                    return 0
                time.sleep(0.05)
            logger.warning("已有实例持有单实例锁，但 IPC 唤起失败")
            return 0

        def _ipc_show_config_callback():
            tray = tray_app
            return getattr(tray, "_show_config", None) if tray is not None else None

        tray_app = None
        server, ipc_pending = create_ipc_server(
            app,
            server_name,
            _ipc_show_config_callback,
            remove_stale=True,
        )

        process_startup_events(app, logger)

        logger.info("启动托盘应用...")
        from bootstrap.composition_root import build_application_services
        from ui.tray_app import TrayApp

        services = build_application_services()
        tray_app = TrayApp(
            data_manager=services.data_manager,
            command_registry=services.command_registry,
            module_registry=services.module_registry,
            plugin_manager=services.plugin_manager,
        )
        logger.info("托盘应用启动成功")

        merge_default_special_apps(tray_app, logger)

        try:
            from bootstrap.composition_root import build_app_context

            app_context = build_app_context(tray_app, server, instance_mutex)
            app_context.start()
            logger.debug("应用上下文和 UIActions 已初始化")
        except (ImportError, AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.warning("初始化应用上下文失败: %s", e, exc_info=True)

        if ipc_pending.get("show_config"):
            QTimer.singleShot(50, tray_app._show_config)

        sync_autostart_setting_from_task(tray_app, logger)

        tray_app.start()

        settings = tray_app.data_manager.get_settings()
        if getattr(settings, "show_on_startup", True):
            logger.info("启动时显示设置窗口...")
            QTimer.singleShot(100, tray_app._show_config)
        else:
            logger.info("静默启动")

        logger.debug("进入事件循环")
        result = exec_app(app)
        if app_context is not None:
            failures = app_context.shutdown()
            if failures:
                logger.warning("应用资源关闭失败: %s", failures)
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
        except (ImportError, OSError, RuntimeError) as dialog_error:
            logger.debug("startup themed error dialog failed: %s", dialog_error)
            _native_error_box("QuickLauncher 启动失败", f"程序启动失败:\n{e}\n\n详情请查看日志:\n{log_file}")
        return 1


def _run_smoke_test_from_argv(argv: list[str]) -> int:
    """Run a non-interactive packaged-runtime smoke test and exit."""

    import json

    checks: dict[str, object] = {}
    errors: list[str] = []

    def record(name: str, callback):
        try:
            checks[name] = callback()
        except Exception as exc:
            logger.debug("Smoke check '%s' failed: %s: %s", name, type(exc).__name__, exc)
            checks[name] = "failed"
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    root_dir = app_root()
    checks["root_dir"] = str(root_dir)
    checks["safe_mode"] = bool(os.environ.get("QL_SAFE_MODE"))

    def check_version():
        from core.version import APP_VERSION, RELEASE_STATUS

        return {"app_version": APP_VERSION, "release_status": RELEASE_STATUS}

    def check_runtime_files():
        required = [
            root_dir / "assets" / "app.ico",
            root_dir / "hooks" / "hooks.dll",
            root_dir / "modules" / "action_chain" / "module.json",
            root_dir / "plugins",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return {"required_files": len(required)}

    def check_qt_application():
        from qt_compat import QT_LIB, QApplication

        app = QApplication.instance()
        created = app is None
        if app is None:
            app = QApplication([argv[0], "--smoke-test"])
        app.processEvents()
        if created:
            app.quit()
        return {"binding": QT_LIB, "created": created}

    def check_dialog_runtime():
        from types import SimpleNamespace

        from core.data_models import Folder
        from qt_compat import QApplication, QDialog, QTimer, QWidget
        from ui.config_window.icon_grid import MoveFolderDialog

        app = QApplication.instance()
        created = app is None
        if app is None:
            app = QApplication([argv[0], "--smoke-test-dialog"])

        parent = QWidget()
        parent.theme = "dark"
        parent.data_manager = SimpleNamespace(get_settings=lambda: SimpleNamespace(theme="dark"))
        dialog = MoveFolderDialog([Folder(id="target", name="Target")], parent)
        try:
            QTimer.singleShot(150, dialog.accept)
            result = dialog.exec_()
            app.processEvents()
            if result != QDialog.Accepted:
                raise RuntimeError(f"MoveFolderDialog returned {result}")
            return {"dialog": type(dialog).__name__, "result": int(result)}
        finally:
            dialog.deleteLater()
            parent.deleteLater()
            app.processEvents()
            if created:
                app.quit()

    def check_core_services():
        from core.command_registry import CommandRegistry
        from core.data_manager import DataManager
        from core.plugin_manager import PluginManager

        data_manager = DataManager()
        registry = CommandRegistry()
        plugin_manager = PluginManager(registry, plugins_dir=str(root_dir / "plugins"))
        return {
            "config_dir": str(data_manager.config_dir),
            "registry_sources": len(getattr(registry, "_sources", {})),
            "plugins_loaded": len(getattr(plugin_manager, "_plugins", {})),
        }

    def check_network_runtime():
        import hashlib
        import ssl

        import core.shortcut_url_exec as url_exec
        from core.shortcut_url_exec import UrlExecutionMixin

        class FakeResponse:
            def read(self, size=-1):
                return b""

            def close(self):
                pass

        original_safe_urlopen = url_exec.safe_urlopen
        original_perf_counter = url_exec.time.perf_counter
        ticks = iter([10.0, 10.123])

        def fake_safe_urlopen(request, timeout=0):
            target = getattr(request, "full_url", "")
            if not str(target).startswith("https://"):
                raise RuntimeError(f"unexpected URL latency target: {target}")
            return FakeResponse()

        try:
            ssl_context = ssl.create_default_context()
            digest = hashlib.sha256(b"quicklauncher-smoke").hexdigest()
            url_exec.safe_urlopen = fake_safe_urlopen  # type: ignore[assignment]
            url_exec.time.perf_counter = lambda: next(ticks)
            latency = UrlExecutionMixin.test_url_latency("https://example.com")
        finally:
            url_exec.safe_urlopen = original_safe_urlopen
            url_exec.time.perf_counter = original_perf_counter

        if not latency.get("success") or latency.get("latency_ms") != 123:
            raise RuntimeError(f"URL latency probe failed: {latency}")

        return {
            "openssl": ssl.OPENSSL_VERSION,
            "verify_mode": int(ssl_context.verify_mode),
            "hash_prefix": digest[:12],
            "url_latency_ms": latency["latency_ms"],
        }

    def check_image_runtime():
        from io import BytesIO

        from PIL import (
            BmpImagePlugin,
            GifImagePlugin,
            IcoImagePlugin,
            Image,
            JpegImagePlugin,
            PngImagePlugin,
            WebPImagePlugin,
        )

        decoder_plugins = (
            BmpImagePlugin,
            GifImagePlugin,
            IcoImagePlugin,
            JpegImagePlugin,
            PngImagePlugin,
            WebPImagePlugin,
        )
        formats = ("PNG", "JPEG", "GIF", "WEBP", "BMP", "ICO")
        checked = []
        for image_format in formats:
            mode = "RGB" if image_format == "JPEG" else "RGBA"
            image = Image.new(mode, (32, 32), (40, 120, 200) if mode == "RGB" else (40, 120, 200, 255))
            payload = BytesIO()
            image.save(payload, format=image_format)
            payload.seek(0)
            with Image.open(payload) as decoded:
                decoded.load()
                if decoded.size != (32, 32):
                    raise RuntimeError(f"{image_format} decoder returned {decoded.size}")
            checked.append(image_format.lower())
        return {"formats": checked, "decoder_plugins": len(decoder_plugins)}

    def check_folder_watch_runtime():
        from core.folder_watcher import WATCHDOG_AVAILABLE

        if not WATCHDOG_AVAILABLE:
            raise RuntimeError("watchdog is unavailable")
        return {"watchdog": True}

    for name, callback in (
        ("version", check_version),
        ("runtime_files", check_runtime_files),
        ("network_runtime", check_network_runtime),
        ("image_runtime", check_image_runtime),
        ("folder_watch_runtime", check_folder_watch_runtime),
        ("qt_application", check_qt_application),
        ("dialog_runtime", check_dialog_runtime),
        ("core_services", check_core_services),
    ):
        record(name, callback)

    payload = {"status": "ok" if not errors else "failed", "checks": checks, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1
