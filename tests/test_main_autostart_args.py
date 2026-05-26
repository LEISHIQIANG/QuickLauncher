"""Main entry-point argument parsing regression tests."""

import ast
import sys
from pathlib import Path

from core.auto_start_manager import (
    HELPER_TARGET_ARG,
    HELPER_TARGET_ARGS_ARG,
    HELPER_TARGET_CWD_ARG,
)


def _load_parse_autostart_cli_args():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    function_node = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "_parse_autostart_cli_args"
    )
    code = compile(ast.Module(body=[function_node], type_ignores=[]), "main.py", "exec")
    namespace = {"sys": sys}
    exec(code, namespace)
    return namespace["_parse_autostart_cli_args"]


def test_parse_autostart_cli_args_reads_target_values(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "QuickLauncher.exe",
            "--autostart-helper",
            "enable",
            HELPER_TARGET_ARG,
            r"C:\Apps\QuickLauncher.exe",
            HELPER_TARGET_ARGS_ARG,
            "--minimized --safe-mode",
            HELPER_TARGET_CWD_ARG,
            r"C:\Apps",
        ],
    )

    parse_autostart_cli_args = _load_parse_autostart_cli_args()

    assert parse_autostart_cli_args(3) == (
        r"C:\Apps\QuickLauncher.exe",
        "--minimized --safe-mode",
        r"C:\Apps",
    )


def test_parse_autostart_cli_args_missing_values_are_empty(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["QuickLauncher.exe", "--autostart-launch", HELPER_TARGET_ARG],
    )

    parse_autostart_cli_args = _load_parse_autostart_cli_args()

    assert parse_autostart_cli_args(2) == ("", "", "")
