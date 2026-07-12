"""Run-mode argument parsing regression tests."""

from bootstrap.process_handlers import _parse_autostart_args
from core.auto_start_manager import (
    HELPER_TARGET_ARG,
    HELPER_TARGET_ARGS_ARG,
    HELPER_TARGET_CWD_ARG,
)


def test_parse_autostart_cli_args_reads_target_values():
    argv = [
        "QuickLauncher.exe",
        "--autostart-helper",
        "enable",
        HELPER_TARGET_ARG,
        r"C:\Apps\QuickLauncher.exe",
        HELPER_TARGET_ARGS_ARG,
        "--minimized --safe-mode",
        HELPER_TARGET_CWD_ARG,
        r"C:\Apps",
    ]

    assert _parse_autostart_args(argv, 3) == (
        r"C:\Apps\QuickLauncher.exe",
        "--minimized --safe-mode",
        r"C:\Apps",
    )


def test_parse_autostart_cli_args_missing_values_are_empty():
    argv = ["QuickLauncher.exe", "--autostart-launch", HELPER_TARGET_ARG]

    assert _parse_autostart_args(argv, 2) == ("", "", "")
