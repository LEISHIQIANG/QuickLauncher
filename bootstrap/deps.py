import os
import sys
import subprocess
import logging


def bootstrap_requirements(root_dir: str, logger: logging.Logger, native_error_box):
    try:
        if getattr(sys, "frozen", False):
            return
        req = os.path.join(root_dir, "requirements.txt")
        if not os.path.exists(req):
            return
        missing = []
        for pkg, name in [("psutil", "psutil"), ("pynput", "pynput"),
                          ("win32api", "pywin32"), ("PIL", "Pillow")]:
            try:
                __import__(pkg)
            except Exception:
                missing.append(name)
        if not missing:
            return
        logger.warning(f"检测到缺少依赖: {missing}，尝试自动安装")
        p = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, check=False, encoding="utf-8", errors="replace"
        )
        if p.returncode != 0:
            logger.error("依赖自动安装失败:\n" + (p.stdout or ""))
            native_error_box(
                "QuickLauncher 依赖缺失",
                f"依赖缺失且自动安装失败。\n\n请执行:\n{sys.executable} -m pip install -r requirements.txt\n\n{(p.stdout or '').strip()[:1800]}"
            )
            raise RuntimeError("requirements install failed")
        logger.info("依赖自动安装完成")
    except Exception:
        raise
