"""Public auto-start entry point for new infrastructure code.

This module is the recommended import path for production code that
needs auto-start functionality. The Windows-specific implementation
lives in :mod:`core.auto_start_manager` for historical reasons
(test-suite monkeypatch compatibility); this module re-exports the
public API so new callers can depend on a stable
:mod:`infrastructure.windows` path.

Example::

    from infrastructure.windows.auto_start_helper import enable_auto_start

The implementation is intentionally not duplicated here so the
``core.auto_start_manager`` module stays the single source of truth
for the auto-start state machine.
"""

from __future__ import annotations

from core.auto_start_manager import (  # noqa: F401  (re-export)
    APP_NAME,
    AUTOSTART_ADMIN_TRIGGER_DELAY,
    AUTOSTART_FALLBACK_POLL_SECONDS,
    AUTOSTART_FALLBACK_TIMEOUT_SECONDS,
    AUTOSTART_HELPER_TIMEOUT_MS,
    AUTOSTART_LAUNCH_ARG,
    AUTOSTART_STANDARD_TRIGGER_DELAY,
    HELPER_ACTION_DISABLE,
    HELPER_ACTION_ENABLE,
    HELPER_ARG,
    HELPER_EXIT_BAD_ARGS,
    HELPER_EXIT_CANCELLED,
    HELPER_EXIT_FAILED,
    HELPER_EXIT_SUCCESS,
    HELPER_TARGET_ARG,
    HELPER_TARGET_ARGS_ARG,
    HELPER_TARGET_CWD_ARG,
    LEGACY_TASK_NAMES,
    PROCESS_INFORMATION,
    SHELLEXECUTEINFO,
    STARTUPINFO,
    TASK_NAME,
    TOKEN_ELEVATION,
    _ensure_auto_start,
    _get_app_launch_spec,
    _is_current_account_admin,
    _read_registry_value,
    disable_auto_start,
    disable_task_scheduler,
    enable_auto_start,
    enable_task_scheduler,
    get_auto_start_check_result,
    get_auto_start_method,
    get_exe_path,
    get_task_scheduler_check_result,
    is_auto_start_enabled,
    is_auto_start_repair_needed,
    is_task_scheduler_enabled,
    run_autostart_helper,
    run_autostart_launcher,
)

__all__ = [
    "APP_NAME",
    "AUTOSTART_ADMIN_TRIGGER_DELAY",
    "AUTOSTART_FALLBACK_POLL_SECONDS",
    "AUTOSTART_FALLBACK_TIMEOUT_SECONDS",
    "AUTOSTART_HELPER_TIMEOUT_MS",
    "AUTOSTART_LAUNCH_ARG",
    "AUTOSTART_STANDARD_TRIGGER_DELAY",
    "HELPER_ACTION_DISABLE",
    "HELPER_ACTION_ENABLE",
    "HELPER_ARG",
    "HELPER_EXIT_BAD_ARGS",
    "HELPER_EXIT_CANCELLED",
    "HELPER_EXIT_FAILED",
    "HELPER_EXIT_SUCCESS",
    "HELPER_TARGET_ARG",
    "HELPER_TARGET_ARGS_ARG",
    "HELPER_TARGET_CWD_ARG",
    "LEGACY_TASK_NAMES",
    "PROCESS_INFORMATION",
    "SHELLEXECUTEINFO",
    "STARTUPINFO",
    "TASK_NAME",
    "TOKEN_ELEVATION",
    "_ensure_auto_start",
    "_get_app_launch_spec",
    "_is_current_account_admin",
    "_read_registry_value",
    "disable_auto_start",
    "disable_task_scheduler",
    "enable_auto_start",
    "enable_task_scheduler",
    "get_auto_start_check_result",
    "get_auto_start_method",
    "get_exe_path",
    "get_task_scheduler_check_result",
    "is_auto_start_enabled",
    "is_auto_start_repair_needed",
    "is_task_scheduler_enabled",
    "run_autostart_helper",
    "run_autostart_launcher",
]
