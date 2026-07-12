import json
import logging
import os
from logging.handlers import RotatingFileHandler

from runtime_paths import config_dir, is_nuitka_compiled, is_packaged_runtime

logger = logging.getLogger(__name__)


def get_log_dir() -> str:
    return str(config_dir())


def setup_logging(log_dir: str) -> tuple:
    """初始化日志系统，返回 (log_file, logger)"""
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.join(os.path.expanduser("~"), "QuickLauncher")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "error.log")

    log_level = logging.INFO
    disable_logging = False
    try:
        data_path = config_dir() / "data.json"
        raw = json.loads(data_path.read_text(encoding="utf-8")) if data_path.is_file() else {}
        settings = raw.get("settings", {}) if isinstance(raw, dict) else {}
        if settings.get("enable_debug_log", False) is True:
            log_level = logging.DEBUG
        disable_logging = settings.get("disable_logging", False) is True
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError) as exc:
        logger.debug("获取日志设置失败: %s", exc, exc_info=True)

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


# 全局引用，防止回调函数被垃圾回收
_crash_handler_ref = None


def _install_native_crash_handler(crash_log_path: str):
    """安装 Windows 原生异常处理器，捕获 faulthandler 抓不到的硬崩溃。"""
    global _crash_handler_ref
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

    class _EXCEPTION_RECORD(ctypes.Structure):
        _fields_ = [
            ("ExceptionCode", wintypes.DWORD),
            ("ExceptionFlags", wintypes.DWORD),
            ("ExceptionRecord", ctypes.c_void_p),
            ("ExceptionAddress", ctypes.c_void_p),
            ("NumberParameters", wintypes.DWORD),
            ("ExceptionInformation", ctypes.c_ulonglong * 15),
        ]

    class _EXCEPTION_POINTERS(ctypes.Structure):
        _fields_ = [
            ("ExceptionRecord", ctypes.POINTER(_EXCEPTION_RECORD)),
            ("ContextRecord", ctypes.c_void_p),
        ]

    @ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p)
    def _handler(exc_ptr):
        try:
            pointers = ctypes.cast(exc_ptr, ctypes.POINTER(_EXCEPTION_POINTERS)).contents
            record = pointers.ExceptionRecord.contents
            code = int(record.ExceptionCode) & 0xFFFFFFFF
            addr = int(record.ExceptionAddress or 0)
            code_name = _EXCEPTION_CODES.get(code, "")
            param_count = max(0, min(int(record.NumberParameters), 15))
            params = ",".join(f"0x{int(record.ExceptionInformation[i]):X}" for i in range(param_count))

            msg = (
                f"[NATIVE_CRASH] code=0x{code:08X} name={code_name} addr=0x{addr:016X} params=[{params}]\r\n"
            ).encode("utf-8", errors="replace")

            h = kernel32.CreateFileW(
                ctypes.c_wchar_p(crash_log_path),
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
        except Exception as exc:
            logger.debug("写入崩溃日志失败: %s", exc, exc_info=True)
        return EXCEPTION_CONTINUE_SEARCH

    try:
        _crash_handler_ref = _handler  # 保持引用防止GC
        kernel32.AddVectoredExceptionHandler(0, _crash_handler_ref)
    except Exception as exc:
        logger.debug("添加异常处理器失败: %s", exc, exc_info=True)


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
        is_frozen = is_packaged_runtime()
        is_nuitka = is_nuitka_compiled()
        exe = sys.executable
        py_ver = sys.version.split()[0]
        try:
            win_ver = platform.version()
        except OSError:
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

        # 安装 Python 级未捕获异常钩子 (sys.excepthook + threading.excepthook)
        _install_excepthooks(crash_path)

    except Exception as exc:
        logger.debug("初始化崩溃日志失败: %s", exc, exc_info=True)


def _write_to_crash_log(crash_log_path: str, message: str) -> None:
    """Append a text line to crash.log (plain Python, not VEH)."""
    import builtins as _b

    try:
        with _b.open(crash_log_path, "a", encoding="utf-8") as _f:
            _f.write(message)
    except OSError:
        return


def _install_excepthooks(crash_log_path: str) -> None:
    """Install sys.excepthook and threading.excepthook.

    Uses lazy imports from core.thread_errors to avoid circular imports
    during early bootstrap.
    """
    import sys as _sys
    import threading as _threading
    import traceback as _traceback

    _original_sys_excepthook = getattr(_sys, "excepthook", None)

    def _sys_hook(exc_type, exc_value, exc_tb) -> None:
        try:
            from core.thread_errors import record_thread_error as _record

            thread = _threading.current_thread()
            _record(
                thread_name=thread.name or "",
                exc=exc_value,
                owner="sys.excepthook",
                trace="".join(_traceback.format_exception(exc_type, exc_value, exc_tb)),
            )
        except Exception:
            logger.debug("sys.excepthook record_thread_error failed")
        _write_to_crash_log(
            crash_log_path,
            f"[UNCAUGHT] type={exc_type.__qualname__} value={exc_value}\n",
        )
        if _original_sys_excepthook is not None and _original_sys_excepthook is not _sys_hook:
            try:
                _original_sys_excepthook(exc_type, exc_value, exc_tb)
            except Exception:
                return

    def _thread_hook(args) -> None:
        try:
            from core.thread_errors import record_thread_error as _record

            _record(
                thread_name=args.thread.name if args.thread else "",
                exc=args.exc_value,
                owner="threading.excepthook",
                trace="".join(_traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb)),
            )
        except Exception:
            logger.debug("threading.excepthook record_thread_error failed")
        _write_to_crash_log(
            crash_log_path,
            f"[UNCAUGHT_THREAD] name={args.thread.name if args.thread else '?'} "
            f"type={args.exc_type.__qualname__} value={args.exc_value}\n",
        )

    _sys.excepthook = _sys_hook
    _threading.excepthook = _thread_hook
