import logging
import os
import subprocess
import sys

from runtime_paths import is_packaged_runtime

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
    except (OSError, subprocess.SubprocessError):
        return False


def maybe_reexec_in_venv(root_dir: str):
    try:
        if is_packaged_runtime():
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
    except (OSError, subprocess.SubprocessError):
        return
