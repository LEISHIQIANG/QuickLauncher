import os
import logging
from logging.handlers import RotatingFileHandler


def get_log_dir() -> str:
    import sys
    from pathlib import Path
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).parent / 'config')
    return str(Path(__file__).parent.parent / 'config')


def setup_logging(log_dir: str) -> tuple:
    """初始化日志系统，返回 (log_file, logger)"""
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = os.path.join(os.path.expanduser("~"), "QuickLauncher")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'error.log')

    log_level = logging.INFO
    disable_logging = False
    try:
        from core import DataManager
        dm = DataManager()
        settings = dm.get_settings()
        if getattr(settings, 'enable_debug_log', False):
            log_level = logging.DEBUG
        disable_logging = getattr(settings, 'disable_logging', False)
    except Exception:
        pass

    handlers = [logging.StreamHandler()]
    if not disable_logging:
        handlers.append(RotatingFileHandler(
            log_file, maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
        ))

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    return log_file, logging.getLogger('main')


def setup_faulthandler(log_dir: str):
    import faulthandler
    try:
        fh_path = os.path.join(log_dir, "faulthandler.log")
        if os.path.exists(fh_path) and os.path.getsize(fh_path) > 5*1024*1024:
            for i in range(1, 0, -1):
                old = f"{fh_path}.{i}"
                new = f"{fh_path}.{i+1}"
                if os.path.exists(old):
                    if os.path.exists(new):
                        os.remove(new)
                    os.rename(old, new)
            if os.path.exists(fh_path):
                os.rename(fh_path, f"{fh_path}.1")
        faulthandler.enable(file=open(fh_path, "a", encoding="utf-8", errors="ignore"), all_threads=True)
    except Exception:
        pass
