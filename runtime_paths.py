"""Runtime and resource path helpers shared by source and packaged builds."""

from __future__ import annotations

import builtins
import logging
import os
import sys
from pathlib import Path

APP_EXE_NAMES = frozenset({"quicklauncher.exe"})
PYTHON_EXE_NAMES = frozenset({"python.exe", "pythonw.exe", "python", "pythonw"})


def is_nuitka_compiled() -> bool:
    """Return True when running from a Nuitka-compiled binary."""
    if hasattr(builtins, "__compiled__"):
        return True
    try:
        return "__compiled__" in sys.builtin_module_names
    except Exception:
        logger = logging.getLogger(__name__)
        logger.debug("is_nuitka_compiled check failed", exc_info=True)
        return False


def _looks_like_app_executable(path: str | os.PathLike[str] | None) -> bool:
    name = Path(path or "").name.lower()
    if name in PYTHON_EXE_NAMES:
        return False
    return name in APP_EXE_NAMES or (name.startswith("quicklauncher") and name.endswith(".exe"))


def is_packaged_runtime() -> bool:
    """Return True for PyInstaller, Nuitka, and installed QuickLauncher exe runs."""
    if bool(getattr(sys, "frozen", False)) or bool(getattr(sys, "_MEIPASS", False)):
        return True
    if is_nuitka_compiled():
        return True
    if _looks_like_app_executable(sys.executable):
        return True
    argv0 = sys.argv[0] if sys.argv else ""
    return _looks_like_app_executable(argv0) and Path(argv0).suffix.lower() == ".exe"


def app_executable() -> Path:
    """Return the executable that should be relaunched for the current runtime."""
    exe = Path(sys.executable or "")
    if "python" in exe.name.lower() and sys.argv:
        argv0 = Path(sys.argv[0])
        if _looks_like_app_executable(argv0):
            candidate = None
            try:
                candidate = argv0.resolve(strict=False)
            except OSError:
                candidate = None
            if candidate is not None and candidate.is_file():
                return candidate
    return exe.resolve(strict=False)


def app_root() -> Path:
    """Return the installation root in packaged runs, otherwise the source root."""
    if is_packaged_runtime():
        return app_executable().parent
    return Path(__file__).resolve(strict=False).parent


def config_dir() -> Path:
    smoke_config_dir = os.environ.get("QL_SMOKE_CONFIG_DIR", "").strip()
    if smoke_config_dir:
        return Path(smoke_config_dir).resolve(strict=False)
    return app_root() / "config"


def resource_path(*parts: str) -> Path:
    return app_root().joinpath(*parts)
