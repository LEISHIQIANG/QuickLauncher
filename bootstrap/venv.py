import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def _is_working_python(exe_path: str) -> bool:
    try:
        p = subprocess.run(
            [exe_path, "-c", "import sys; print(sys.version_info[:2])"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=2,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode == 0
    except Exception:
        return False


def maybe_reexec_in_venv(root_dir: str):
    try:
        is_compiled = (
            getattr(sys, "frozen", False)
            or getattr(sys, "_MEIPASS", False)
            or ("__compiled__" in sys.builtin_module_names)
        )
        if not is_compiled:
            try:
                import builtins

                if hasattr(builtins, "__compiled__"):
                    is_compiled = True
            except Exception:
                logger.debug("检测编译状态失败", exc_info=True)

        if is_compiled:
            return
        venv_py = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
        if not os.path.exists(venv_py):
            return
        cur = os.path.normcase(os.path.abspath(sys.executable))
        tgt = os.path.normcase(os.path.abspath(venv_py))
        if cur == tgt:
            return
        if not _is_working_python(venv_py):
            return
        os.environ["QL_REEXECED"] = "1"
        sys.exit(subprocess.call([venv_py] + sys.argv))
    except Exception:
        return
