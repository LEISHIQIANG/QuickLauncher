import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".venv", ".venv-py38", ".venv-py311", ".venv-py312", "dist", "__pycache__"}


def iter_source_files():
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def test_all_project_python_files_parse():
    failures = []
    for path in iter_source_files():
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")

    assert not failures, "\n".join(failures)


def test_core_import_health():
    modules = [
        "bootstrap.dpi",
        "bootstrap.ipc",
        "bootstrap.logging_init",
        "core.config_migrator",
        "core.data_manager",
        "core.data_models",
        "core.memory_guard",
        "core.service_manager",
        "core.shortcut_executor",
        "hooks.hotkey_manager",
        "ui.launcher_popup.popup_window",
        "ui.config_window.settings_panel",
        "qt_compat",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
