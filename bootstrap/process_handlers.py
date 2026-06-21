"""Handlers for non-GUI executable modes.

This module intentionally avoids importing Qt and the tray application.
"""

from __future__ import annotations

import json
import logging
import os
import runpy
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _mode_index(argv: list[str], mode: Any) -> int:
    flag = f"--{getattr(mode, 'value', mode)}"
    try:
        return argv.index(flag)
    except ValueError:
        return 1


def _parse_autostart_args(argv: list[str], start_index: int) -> tuple[str, str, str]:
    from core.auto_start_manager import HELPER_TARGET_ARG, HELPER_TARGET_ARGS_ARG, HELPER_TARGET_CWD_ARG

    def value(flag: str) -> str:
        try:
            index = argv.index(flag, start_index)
        except ValueError:
            return ""
        return argv[index + 1] if index + 1 < len(argv) else ""

    return value(HELPER_TARGET_ARG), value(HELPER_TARGET_ARGS_ARG), value(HELPER_TARGET_CWD_ARG)


def run_plugin_helper(argv: list[str]) -> int:
    index = _mode_index(argv, "plugin-helper")
    if len(argv) <= index + 1:
        print("missing plugin helper script", file=sys.stderr)
        return 2
    script_path = Path(argv[index + 1]).resolve(strict=False)
    site_paths: list[Path] = []
    helper_args: list[str] = []
    output_path: Path | None = None
    cursor = index + 2
    while cursor < len(argv):
        arg = argv[cursor]
        if arg == "--":
            helper_args = argv[cursor + 1 :]
            break
        if arg in {"--plugin-site", "--plugin-output"} and cursor + 1 < len(argv):
            value = Path(argv[cursor + 1]).resolve(strict=False)
            if arg == "--plugin-site":
                site_paths.append(value)
            else:
                output_path = value
            cursor += 2
            continue
        print(f"unknown plugin helper argument: {arg}", file=sys.stderr)
        return 2
    if not script_path.is_file():
        print(f"plugin helper script not found: {script_path}", file=sys.stderr)
        return 2

    output_handle = None
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_handle = output_path.open("w", encoding="utf-8", buffering=1)
            sys.stdout = output_handle
            sys.stderr = output_handle
        search_paths = [script_path.parent, *site_paths]
        for path in reversed(search_paths):
            if path.is_dir() and str(path) not in sys.path:
                sys.path.insert(0, str(path))
        for dll_dir in [script_path.parent, *(path for site in site_paths for path in (site, site / "wx"))]:
            if not dll_dir.is_dir():
                continue
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
            add_dll_directory = getattr(os, "add_dll_directory", None)
            if add_dll_directory is not None:
                try:
                    add_dll_directory(str(dll_dir))
                except OSError as exc:
                    print(f"plugin helper could not add DLL directory {dll_dir}: {exc}", file=sys.stderr)
        sys.argv = [str(script_path), *helper_args]
        try:
            runpy.run_path(str(script_path), run_name="__main__")
            return 0
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 0
        except Exception:
            logger.exception("插件辅助脚本执行失败")
            return 1
    except OSError as exc:
        print(f"plugin helper I/O failure: {exc}", file=old_stderr)
        return 2
    finally:
        if output_handle is not None:
            output_handle.flush()
            output_handle.close()
        sys.stdout, sys.stderr = old_stdout, old_stderr


def run_plugin_worker(argv: list[str]) -> int:
    index = _mode_index(argv, "plugin-worker")
    if len(argv) <= index + 1:
        return 2
    script_path = str(Path(argv[index + 1]).resolve(strict=False))
    site_paths: list[str] = []
    port = 0
    token = ""
    cursor = index + 2
    while cursor < len(argv):
        arg = argv[cursor]
        if arg == "--plugin-site" and cursor + 1 < len(argv):
            site_paths.append(str(Path(argv[cursor + 1]).resolve(strict=False)))
        elif arg == "--plugin-port" and cursor + 1 < len(argv):
            try:
                port = int(argv[cursor + 1])
            except ValueError:
                return 2
        elif arg == "--plugin-token" and cursor + 1 < len(argv):
            token = argv[cursor + 1]
        else:
            return 2
        cursor += 2
    if not port or not token:
        return 2
    from core.plugin_worker_runtime import run_worker_process

    return run_worker_process(script_path, site_paths=site_paths, port=port, token=token)


def run_smoke_test(argv: list[str]) -> int:
    import atexit
    import shutil
    import tempfile

    smoke_dir = tempfile.mkdtemp(prefix="quicklauncher-smoke-")
    os.environ["QL_SMOKE_CONFIG_DIR"] = smoke_dir
    atexit.register(shutil.rmtree, smoke_dir, ignore_errors=True)
    cleaned = [arg for arg in argv if arg != "--smoke-test"]
    from bootstrap.gui_application import _run_smoke_test_from_argv

    return int(_run_smoke_test_from_argv(cleaned))


def run_process_mode(mode: Any, argv: list[str]) -> int:
    index = _mode_index(argv, mode)
    mode_value = str(getattr(mode, "value", mode))
    if mode_value == "file-dialog":
        sys.argv = [argv[0], *argv[index + 1 :]]
        try:
            from ui.utils.file_dialog_subprocess import main as run_dialog

            run_dialog()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}))
        return 0
    if mode_value == "plugin-helper":
        return run_plugin_helper(argv)
    if mode_value == "plugin-worker":
        return run_plugin_worker(argv)
    if mode_value in {"install-service", "uninstall-service"}:
        from core.service_manager import disable_service_autostart, enable_service_autostart

        operation = enable_service_autostart if mode_value == "install-service" else disable_service_autostart
        success, message = operation()
        print(message)
        return 0 if success else 1
    if mode_value == "service":
        import servicemanager

        from core.windows_service import QuickLauncherService

        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(QuickLauncherService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0

    from core.auto_start_manager import HELPER_EXIT_BAD_ARGS

    if mode_value == "configure-autostart":
        from core.auto_start_manager import (
            HELPER_ACTION_DISABLE,
            HELPER_ACTION_ENABLE,
            disable_auto_start,
            enable_auto_start,
        )

        action = argv[index + 1] if len(argv) > index + 1 else ""
        target_exe, target_args, target_cwd = _parse_autostart_args(argv, index + 2)
        if action == HELPER_ACTION_ENABLE:
            success, message = enable_auto_start(target_exe, target_args, target_cwd)
        elif action == HELPER_ACTION_DISABLE:
            success, message = disable_auto_start()
        else:
            return HELPER_EXIT_BAD_ARGS
        print(message)
        return 0 if success else 1
    if mode_value == "autostart-helper":
        from core.auto_start_manager import run_autostart_helper

        action = argv[index + 1] if len(argv) > index + 1 else ""
        target_exe, target_args, target_cwd = _parse_autostart_args(argv, index + 2)
        return run_autostart_helper(action, target_exe, target_args, target_cwd) if action else HELPER_EXIT_BAD_ARGS
    if mode_value == "autostart-launch":
        from core.auto_start_manager import run_autostart_launcher

        target_exe, target_args, target_cwd = _parse_autostart_args(argv, index + 1)
        return run_autostart_launcher(target_exe, target_args, target_cwd) if target_exe else HELPER_EXIT_BAD_ARGS
    raise ValueError(f"unsupported run mode: {mode_value}")
