import logging
import os
from logging.handlers import RotatingFileHandler


def get_log_dir() -> str:
    import sys
    from pathlib import Path

    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent / "config")
    return str(Path(__file__).parent.parent / "config")


def setup_logging(log_dir: str) -> tuple:
    """初始化日志系统，返回 (log_file, logger)"""
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = os.path.join(os.path.expanduser("~"), "QuickLauncher")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "error.log")

    log_level = logging.INFO
    disable_logging = False
    try:
        from core import DataManager

        dm = DataManager()
        settings = dm.get_settings()
        if getattr(settings, "enable_debug_log", False):
            log_level = logging.DEBUG
        disable_logging = getattr(settings, "disable_logging", False)
    except Exception:
        pass

    import sys

    # Use a dedicated stream wrapping stdout's fd for consistent UTF-8 encoding.
    # The stream is kept for the process lifetime (closed on exit by the OS).
    _stdout_stream = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)  # noqa: SIM115
    stream_handler = logging.StreamHandler(_stdout_stream)
    handlers = [stream_handler]
    if not disable_logging:
        handlers.append(RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"))

    logging.basicConfig(
        level=log_level, format="%(asctime)s - [PID: %(process)d] - %(levelname)s - %(message)s", handlers=handlers
    )

    return log_file, logging.getLogger("main")


def _install_native_crash_handler(crash_log_path: str):
    """安装 Windows 原生异常处理器，捕获 faulthandler 抓不到的硬崩溃。"""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    EXCEPTION_CONTINUE_SEARCH = 0
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_RW = 0x00000003
    OPEN_ALWAYS = 0x00000004
    FILE_ATTRIBUTE_NORMAL = 0x00000080
    FILE_END = 0x00000002

    _EXCEPTION_CODES = {
        0xC0000005: "ACCESS_VIOLATION",
        0xC0000017: "NO_MEMORY",
        0xC00000FD: "STACK_OVERFLOW",
        0x8001010E: "RPC_E_WRONG_THREAD",
        0x8001010D: "RPC_E_CANTCALLOUT_ININPUTSYNCCALL",
        0xC0000374: "HEAP_CORRUPTION",
        0xE06D7363: "CPP_EH_EXCEPTION",
        0xC0000409: "STACK_BUFFER_OVERRUN",
        0xC0000417: "INVALID_CRUNTIME_PARAMETER",
        0xC000008C: "ARRAY_BOUNDS_EXCEEDED",
        0xC0000094: "INT_DIVIDE_BY_ZERO",
        0xC0000095: "INT_OVERFLOW",
        0xC0000096: "PRIV_INSTRUCTION",
        0xC0000135: "DLL_NOT_FOUND",
    }

    # 预先编码路径为窄字符串（bytes），崩溃时直接用指针写文件
    _crash_log_bytes = crash_log_path.encode("utf-8", errors="ignore") + b"\x00"

    @ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p)
    def _handler(exc_ptr):
        try:
            record = ctypes.cast(exc_ptr, ctypes.POINTER(ctypes.c_ulonglong * 18))
            code = record.contents[0] & 0xFFFFFFFF
            addr = record.contents[1]
            code_name = _EXCEPTION_CODES.get(code, "")

            msg = (f"[NATIVE_CRASH] code=0x{code:08X} name={code_name} addr=0x{addr:016X}\r\n").encode(
                "utf-8", errors="replace"
            )

            h = kernel32.CreateFileA(
                ctypes.c_char_p(_crash_log_bytes),
                GENERIC_WRITE,
                FILE_SHARE_RW,
                None,
                OPEN_ALWAYS,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if h != wintypes.HANDLE(-1).value:
                kernel32.SetFilePointer(h, 0, None, FILE_END)
                written = wintypes.DWORD(0)
                kernel32.WriteFile(h, ctypes.c_char_p(msg), len(msg), ctypes.byref(written), None)
                kernel32.FlushFileBuffers(h)
                kernel32.CloseHandle(h)
        except Exception:
            pass
        return EXCEPTION_CONTINUE_SEARCH

    try:
        kernel32.AddVectoredExceptionHandler(0, _handler)
    except Exception:
        pass


def _rotate_log(path: str, backup_count: int = 3, max_bytes: int = 5 * 1024 * 1024):
    """Rotate a log file if it exceeds max_bytes, keeping up to backup_count backups."""
    if not os.path.exists(path) or os.path.getsize(path) <= max_bytes:
        return
    for i in range(backup_count - 1, 0, -1):
        old = f"{path}.{i}"
        new = f"{path}.{i + 1}"
        if os.path.exists(old):
            if os.path.exists(new):
                os.remove(new)
            os.rename(old, new)
    if os.path.exists(path):
        os.rename(path, f"{path}.1")


def setup_faulthandler(log_dir: str):
    import faulthandler
    import platform
    import sys
    from datetime import datetime

    try:
        fh_path = os.path.join(log_dir, "faulthandler.log")
        crash_path = os.path.join(log_dir, "crash.log")

        # Rotate both logs at startup (max 3 backups, 5MB each)
        _rotate_log(fh_path, backup_count=3, max_bytes=5 * 1024 * 1024)
        _rotate_log(crash_path, backup_count=3, max_bytes=5 * 1024 * 1024)

        fh_file = open(fh_path, "a", encoding="utf-8", errors="ignore")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_frozen = getattr(sys, "frozen", False)
        is_nuitka = "__compiled__" in dir(__builtins__) or globals().get("__compiled__", False)
        exe = sys.executable
        py_ver = sys.version.split()[0]
        try:
            win_ver = platform.version()
        except Exception:
            win_ver = "unknown"
        fh_file.write(
            f"\n{'='*60}\n"
            f"[STARTUP] {now}\n"
            f"  exe     : {exe}\n"
            f"  python  : {py_ver}  frozen={is_frozen}  nuitka={is_nuitka}\n"
            f"  windows : {win_ver}\n"
            f"{'='*60}\n"
        )
        fh_file.flush()

        faulthandler.enable(file=fh_file, all_threads=True)

        # 写入 crash.log 启动标记 + 安装原生崩溃处理器
        with open(crash_path, "a", encoding="utf-8") as cf:
            cf.write(f"[BOOT] {now}  exe={exe}\n")
        _install_native_crash_handler(crash_path)

    except Exception:
        pass
