"""Native acceleration services exposed to Python code.

This module wraps the native DLLs behind clean Python APIs.
All functions are hard dependencies on the native DLLs — there is no Python
fallback path.
"""

from __future__ import annotations

import ctypes
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from bootstrap.native_loader import (
    QLautostart,
    QLclipboard,
    QLcrypto,
    QLicon,
    QLsearch,
    QLshell,
    QLupdate,
    QLvalidate,
    QLwatch,
    QLwindow,
)

if TYPE_CHECKING:
    from .fuzzy_search import FuzzyMatchResult

logger = logging.getLogger(__name__)

_QLCRYPTO_MAX_HEX_LEN = 65
_HASH_ALGOS = frozenset({"md5", "sha1", "sha256"})


def hash_file(path: str | Path, algorithm: str = "sha256", max_bytes: int = 0) -> str:
    """Compute a file hash using the native QLcrypto DLL.

    Args:
        path: File path (str or Path).
        algorithm: One of "md5", "sha1", "sha256".
        max_bytes: Maximum bytes to read (0 = unlimited).

    Returns:
        Lowercase hexadecimal digest string.

    Raises:
        ValueError: If the algorithm is unsupported.
        OSError: If the file cannot be opened or read.
        RuntimeError: If the DLL reports an internal error.
    """
    algo = algorithm.lower()
    if algo not in _HASH_ALGOS:
        raise ValueError(f"不支持的哈希算法: {algorithm}")

    dll = QLcrypto().dll
    dll.QLcrypto_lastError.restype = ctypes.c_char_p
    out_buf = ctypes.create_string_buffer(_QLCRYPTO_MAX_HEX_LEN)
    path_utf8 = str(path).encode("utf-8")
    algo_b = algo.encode("ascii")

    rc = dll.QLcrypto_hashFile(
        path_utf8,
        algo_b,
        ctypes.c_ulonglong(max_bytes),
        out_buf,
        ctypes.c_uint(_QLCRYPTO_MAX_HEX_LEN),
    )
    if rc != 0:
        err_msg = dll.QLcrypto_lastError().decode("utf-8", errors="replace")
        if rc == -1:
            raise ValueError(f"哈希参数错误: {err_msg}")
        if rc in (-2, -3):
            raise OSError(f"文件操作失败 (code={rc}): {err_msg}")
        raise RuntimeError(f"原生哈希失败 (code={rc}): {err_msg}")

    return out_buf.value.decode("ascii")


# ---------------------------------------------------------------------------
# QLsearch: ctypes structures and engine singleton
# ---------------------------------------------------------------------------

_FIELD_NAMES = ("name", "alias", "tags", "target_path", "url", "command", "hotkey")


class QLResult(ctypes.Structure):
    _fields_ = [
        ("shortcut_id", ctypes.c_int),
        ("folder_id", ctypes.c_int),
        ("score", ctypes.c_double),
        ("matched_fields_mask", ctypes.c_uint),
    ]


class _QLsearchEngine:
    """Singleton managing the native search engine lifecycle and data sync."""

    _instance: _QLsearchEngine | None = None

    def __init__(self) -> None:
        self.dll = QLsearch().dll
        self.dll.QLsearch_init()
        self._loaded = False
        self._id_to_shortcut: dict[int, object] = {}
        self._id_to_folder: dict[int, object] = {}
        self._str_id_to_int: dict[str, int] = {}

    @classmethod
    def get(cls) -> _QLsearchEngine:
        if cls._instance is not None:
            return cls._instance
        cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            try:
                cls._instance.dll.QLsearch_release()
            except Exception:
                logger.debug("QLsearch release failed", exc_info=True)
            cls._instance = None

    def load_all(self, data: bytes) -> None:
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        rc = self.dll.QLsearch_loadAll(buf, ctypes.c_int(len(data)))
        if rc != 0:
            err_ptr = self.dll.QLsearch_lastError()
            err_msg = ctypes.string_at(err_ptr).decode("utf-8", errors="replace") if err_ptr else ""
            raise RuntimeError(f"QLsearch_loadAll 失败 (code={rc}): {err_msg}")
        self._loaded = True

    def sync_from_folders(
        self,
        folders: Sequence[object],
        sort_mode: str = "custom",
    ) -> None:
        from .native_search_serializer import serialize_search_data

        data, folder_map, shortcut_map = serialize_search_data(folders)
        self.load_all(data)
        self._id_to_folder = folder_map
        self._id_to_shortcut = shortcut_map
        self._str_id_to_int.clear()
        for sid, sc in shortcut_map.items():
            str_id = getattr(sc, "id", None)
            if str_id:
                self._str_id_to_int[str(str_id).strip()] = sid

    def search(self, query_normalized: str, sort_mode: int, limit: int) -> list[QLResult]:
        if not self._loaded:
            return []
        if not query_normalized:
            return []
        cap = min(max(limit, 1), 512)
        out_buf = (QLResult * cap)()
        n = self.dll.QLsearch_search(
            query_normalized.encode("utf-8"),
            ctypes.c_int(sort_mode),
            ctypes.c_int(cap),
            out_buf,
            ctypes.c_int(cap),
        )
        if n < 0:
            err_ptr = self.dll.QLsearch_lastError()
            err_msg = ctypes.string_at(err_ptr).decode("utf-8", errors="replace") if err_ptr else ""
            raise RuntimeError(f"QLsearch_search 失败 (code={n}): {err_msg}")
        return [out_buf[i] for i in range(min(n, cap))]

    def search_with_mapping(
        self,
        query_normalized: str,
        sort_mode: int,
        limit: int,
    ) -> list[FuzzyMatchResult]:
        from .fuzzy_search import FuzzyMatchResult, _text

        results: list[FuzzyMatchResult] = []
        for i, r in enumerate(self.search(query_normalized, sort_mode, limit)):
            sc = self._id_to_shortcut.get(r.shortcut_id)
            if sc is None:
                logger.debug(
                    "native search returned unknown shortcut_id=%d, skipping",
                    r.shortcut_id,
                )
                continue
            folder = self._id_to_folder.get(r.folder_id)
            folder_id = _text(getattr(folder, "id", "")) if folder else ""
            folder_name = _text(getattr(folder, "name", "")) if folder else ""
            matched = matched_fields_from_mask(r.matched_fields_mask)
            results.append(
                FuzzyMatchResult(
                    shortcut=sc,
                    folder_id=folder_id,
                    folder_name=folder_name,
                    score=r.score,
                    original_index=i,
                    matched_fields=matched,
                )
            )
        return results

    def set_history_bonuses(self, bonuses: dict[int, float]) -> None:
        if not bonuses:
            self.dll.QLsearch_setHistoryBonuses(None, None, ctypes.c_int(0))
            return
        ids = (ctypes.c_int * len(bonuses))(*bonuses.keys())
        vals = (ctypes.c_double * len(bonuses))(*bonuses.values())
        self.dll.QLsearch_setHistoryBonuses(ids, vals, ctypes.c_int(len(bonuses)))

    def set_history_bonuses_from_str_ids(self, str_bonuses: dict[str, float]) -> None:
        bonuses: dict[int, float] = {}
        for str_id, bonus in str_bonuses.items():
            sid = self._str_id_to_int.get(str_id)
            if sid is not None:
                bonuses[sid] = bonus
        self.set_history_bonuses(bonuses)

    @property
    def loaded(self) -> bool:
        return self._loaded


def matched_fields_from_mask(mask: int) -> list[str]:
    """Decode the bitmask returned by QLsearch into field names."""
    return [_FIELD_NAMES[i] for i in range(7) if mask & (1 << i)]


# ---------------------------------------------------------------------------
# QLwindow: native window management
# ---------------------------------------------------------------------------


class _QLWindowEngine:
    """Singleton wrapping QLwindow.dll for window activation and enumeration."""

    _instance: _QLWindowEngine | None = None

    def __init__(self) -> None:
        self._dll = QLwindow().dll

    @classmethod
    def get(cls) -> _QLWindowEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def activate(self, exe_path: str, restore_minimized: bool = True) -> tuple[bool, int | None]:
        hwnd = ctypes.c_int()
        rc = self._dll.QLwindow_Activate(
            ctypes.c_wchar_p(exe_path),
            ctypes.c_int(1 if restore_minimized else 0),
            ctypes.byref(hwnd),
        )
        if rc == 0:
            return True, hwnd.value
        return False, None

    def get_windows_for_pids(self, pids: list[int]) -> dict[int, list[int]]:
        if not pids:
            return {}
        pid_arr = (ctypes.c_int * len(pids))(*pids)
        max_infos = len(pids) * 16
        info_buf = (QLWindowInfo * max_infos)()
        n = self._dll.QLwindow_GetWindowsForPids(
            pid_arr,
            ctypes.c_int(len(pids)),
            info_buf,
            ctypes.c_int(max_infos),
        )
        result: dict[int, list[int]] = {pid: [] for pid in pids}
        for i in range(max(0, n)):
            result.setdefault(info_buf[i].pid, []).append(info_buf[i].hwnd)
        return result

    def get_process_windows(self, pid: int) -> list[int]:
        max_hwnds = 32
        buf = (ctypes.c_int * max_hwnds)()
        n = self._dll.QLwindow_GetProcessWindows(ctypes.c_int(pid), buf, ctypes.c_int(max_hwnds))
        return list(buf[: max(0, n)])

    def activate_hwnd(self, hwnd: int, restore_minimized: bool = True) -> bool:
        return cast(
            bool,
            self._dll.QLwindow_ActivateHwnd(
                ctypes.c_int(hwnd),
                ctypes.c_int(1 if restore_minimized else 0),
            )
            == 0,
        )

    def is_minimized(self, hwnd: int) -> bool:
        return bool(self._dll.QLwindow_IsMinimized(ctypes.c_int(hwnd)))


class QLWindowInfo(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_int),
        ("pid", ctypes.c_int),
        ("title", ctypes.c_wchar * 256),
    ]


# ---------------------------------------------------------------------------
# QLvalidate: native IP/URL validation
# ---------------------------------------------------------------------------

_VALIDATE_RESULT_LABELS: dict[int, str] = {
    0: "ok",
    1: "empty_url",
    2: "unsupported_scheme",
    3: "missing_host",
    4: "localhost",
    5: "private_ip",
    6: "dns_failed",
    7: "dns_private",
}


class QLIpResult(ctypes.Structure):
    _fields_ = [
        ("family", ctypes.c_int),
        ("address", ctypes.c_char * 46),
        ("is_public", ctypes.c_int),
    ]


class _QLValidateEngine:
    """Singleton wrapping QLvalidate.dll for IP/URL security validation."""

    _instance: _QLValidateEngine | None = None

    def __init__(self) -> None:
        self._dll = QLvalidate().dll
        self._dll.QLvalidate_lastError.restype = ctypes.c_char_p

    @classmethod
    def get(cls) -> _QLValidateEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_public_ipv4(self, ip_be: int) -> bool:
        return bool(self._dll.QLvalidate_IsPublicIpv4(ctypes.c_uint(ip_be)))

    def is_public_ipv6(self, ipv6: bytes) -> bool:
        buf = (ctypes.c_ubyte * 16).from_buffer_copy(ipv6)
        return bool(self._dll.QLvalidate_IsPublicIpv6(buf))

    def is_public_ip_string(self, ip_str: str) -> bool | None:
        rc = self._dll.QLvalidate_IsPublicIpString(ip_str.encode("utf-8"))
        if rc < 0:
            return None
        return bool(rc)

    def resolve_host(self, hostname: str, max_results: int = 16) -> list[dict]:
        buf = (QLIpResult * max_results)()
        n = self._dll.QLvalidate_ResolveHost(hostname.encode("utf-8"), buf, ctypes.c_int(max_results))
        if n < 0:
            return []
        results: list[dict] = []
        for i in range(min(n, max_results)):
            results.append(
                {
                    "family": buf[i].family,
                    "address": buf[i].address.decode("ascii"),
                    "is_public": bool(buf[i].is_public),
                }
            )
        return results

    def normalize_url(self, url: str) -> str:
        buf = ctypes.create_string_buffer(2048)
        n = self._dll.QLvalidate_NormalizeUrl(url.encode("utf-8"), buf, ctypes.c_int(2048))
        if n < 0:
            return url
        return buf.value.decode("utf-8")

    def validate_public_url(self, url: str, trust_proxy: bool = False) -> tuple[bool, str, str]:
        error_buf = ctypes.create_string_buffer(256)
        rc = self._dll.QLvalidate_PublicUrl(
            url.encode("utf-8"),
            ctypes.c_int(1 if trust_proxy else 0),
            error_buf,
            ctypes.c_int(256),
        )
        label = _VALIDATE_RESULT_LABELS.get(rc, f"unknown({rc})")
        error_msg = error_buf.value.decode("utf-8", errors="replace") if rc != 0 else ""
        return rc == 0, label, error_msg

    def is_loopback_ipv4(self, ip_be: int) -> bool:
        return bool(self._dll.QLvalidate_IsLoopbackIpv4(ctypes.c_uint(ip_be)))

    def is_private_ipv4(self, ip_be: int) -> bool:
        return bool(self._dll.QLvalidate_IsPrivateIpv4(ctypes.c_uint(ip_be)))

    def is_link_local_ipv4(self, ip_be: int) -> bool:
        return bool(self._dll.QLvalidate_IsLinkLocalIpv4(ctypes.c_uint(ip_be)))

    def is_multicast_ipv4(self, ip_be: int) -> bool:
        return bool(self._dll.QLvalidate_IsMulticastIpv4(ctypes.c_uint(ip_be)))


# ---------------------------------------------------------------------------
# QLshell: native shell operations
# ---------------------------------------------------------------------------


class _QLShellEngine:
    """Singleton wrapping QLshell.dll for shell / process operations."""

    _instance: _QLShellEngine | None = None

    def __init__(self) -> None:
        self._dll = QLshell().dll

    @classmethod
    def get(cls) -> _QLShellEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def open_path(self, path: str) -> bool:
        return cast(bool, self._dll.QLshell_OpenPath(ctypes.c_wchar_p(path)) == 0)

    def relaunch(self, exe_path: str, argv: list[str] | None = None) -> bool:
        if argv:
            arr = (ctypes.c_wchar_p * (len(argv) + 1))()
            for i, a in enumerate(argv):
                arr[i] = ctypes.c_wchar_p(a)
            arr[len(argv)] = None
        else:
            arr = (ctypes.c_wchar_p * 1)()
            arr[0] = None
        return cast(bool, self._dll.QLshell_Relaunch(ctypes.c_wchar_p(exe_path), arr) == 0)

    def run_detached(self, exe_path: str, argv: list[str], working_dir: str | None = None) -> bool:
        arr = (ctypes.c_wchar_p * (len(argv) + 1))()
        for i, a in enumerate(argv):
            arr[i] = ctypes.c_wchar_p(a)
        arr[len(argv)] = None
        wd = ctypes.c_wchar_p(working_dir) if working_dir else None
        return cast(bool, self._dll.QLshell_RunDetached(ctypes.c_wchar_p(exe_path), arr, wd) == 0)

    def launch_with_file(
        self, exe_path: str, file_path: str, working_dir: str | None = None, use_cmd_start: bool = False
    ) -> bool:
        wd = ctypes.c_wchar_p(working_dir) if working_dir else None
        return cast(
            bool,
            self._dll.QLshell_LaunchWithFile(
                ctypes.c_wchar_p(exe_path),
                ctypes.c_wchar_p(file_path),
                wd,
                ctypes.c_int(1 if use_cmd_start else 0),
            )
            == 0,
        )


# ---------------------------------------------------------------------------
# QLwatch: native folder watcher
# ---------------------------------------------------------------------------

WATCH_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_char_p)


class _QLWatchEngine:
    """Singleton wrapping QLwatch.dll for folder change monitoring."""

    _instance: _QLWatchEngine | None = None

    def __init__(self) -> None:
        self._dll = QLwatch().dll
        self._dll.QLwatch_Init()
        self._callbacks: dict[str, Callable[[str], None]] = {}
        self._callback_refs: dict[str, ctypes._FuncPointer] = {}

    @classmethod
    def get(cls) -> _QLWatchEngine:
        if cls._instance is not None:
            return cls._instance
        cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            try:
                cls._instance._dll.QLwatch_StopAll()
                cls._instance._dll.QLwatch_Release()
            except Exception:
                logger.debug("QLwatch release failed", exc_info=True)
            cls._instance = None

    def start_watch(self, folder_id: str, folder_path: str, callback: Callable[[str], None]) -> None:
        def _bridge(fid_bytes: bytes) -> None:
            fid = fid_bytes.decode("utf-8") if fid_bytes else ""
            try:
                if fid in self._callbacks:
                    self._callbacks[fid](fid)
            except Exception:
                logger.debug("QLwatch callback error for %s", fid, exc_info=True)

        cb = WATCH_CALLBACK(_bridge)
        self._callback_refs[folder_id] = cb
        self._callbacks[folder_id] = callback
        rc = self._dll.QLwatch_Start(
            folder_id.encode("utf-8"),
            ctypes.c_wchar_p(folder_path),
            cb,
        )
        if rc != 0:
            del self._callback_refs[folder_id]
            del self._callbacks[folder_id]
            raise RuntimeError(f"QLwatch_Start failed for {folder_id} (code={rc})")

    def stop_watch(self, folder_id: str) -> None:
        self._dll.QLwatch_Stop(folder_id.encode("utf-8"))
        self._callback_refs.pop(folder_id, None)
        self._callbacks.pop(folder_id, None)

    def stop_all(self) -> None:
        self._dll.QLwatch_StopAll()
        self._callback_refs.clear()
        self._callbacks.clear()


# ---------------------------------------------------------------------------
# QLclipboard: native clipboard service
# ---------------------------------------------------------------------------


class QLClipboardFormatInfo(ctypes.Structure):
    _fields_ = [
        ("formatId", ctypes.c_int),
        ("name", ctypes.c_char * 128),
    ]


class _QLClipboardEngine:
    """Singleton wrapping QLclipboard.dll for clipboard operations."""

    _instance: _QLClipboardEngine | None = None
    _MAX_TEXT_BUFFER = 65536

    def __init__(self) -> None:
        self._dll = QLclipboard().dll
        self._dll.QLclipboard_EnsureComInit()
        self._snapshot_sizes: dict[int, int] = {}

    @classmethod
    def get(cls) -> _QLClipboardEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def read_text(self) -> str | None:
        buf = ctypes.create_unicode_buffer(self._MAX_TEXT_BUFFER)
        n = self._dll.QLclipboard_ReadText(buf, ctypes.c_int(self._MAX_TEXT_BUFFER))
        if n <= 0:
            return None
        return buf.value

    def write_text(self, text: str) -> bool:
        return cast(bool, self._dll.QLclipboard_WriteText(ctypes.c_wchar_p(text)) == 0)

    def create_snapshot(self) -> tuple[int, int]:
        sid = ctypes.c_int()
        count = ctypes.c_int()
        rc = self._dll.QLclipboard_CreateSnapshot(ctypes.byref(sid), ctypes.byref(count))
        if rc != 0:
            raise RuntimeError(f"QLclipboard_CreateSnapshot failed (code={rc})")
        self._snapshot_sizes[sid.value] = count.value
        return sid.value, count.value

    def get_snapshot_entry(
        self, snapshot_id: int, entry_index: int, data_buf_size: int = 1048576
    ) -> tuple[int, bytes | None]:
        format_id = ctypes.c_int()
        if data_buf_size > 0:
            out_data = (ctypes.c_ubyte * data_buf_size)()
            size = self._dll.QLclipboard_GetSnapshotEntry(
                ctypes.c_int(snapshot_id),
                ctypes.c_int(entry_index),
                ctypes.byref(format_id),
                out_data,
                ctypes.c_int(data_buf_size),
            )
            if size < 0:
                return -1, None
            return format_id.value, bytes(out_data[:size])
        else:
            size = self._dll.QLclipboard_GetSnapshotEntry(
                ctypes.c_int(snapshot_id),
                ctypes.c_int(entry_index),
                ctypes.byref(format_id),
                None,
                ctypes.c_int(0),
            )
            return format_id.value, None

    def get_snapshot_entry_name(self, snapshot_id: int, entry_index: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        n = self._dll.QLclipboard_GetSnapshotEntryName(
            ctypes.c_int(snapshot_id),
            ctypes.c_int(entry_index),
            buf,
            ctypes.c_int(256),
        )
        if n < 0:
            return ""
        return buf.value

    def restore_snapshot(self, snapshot_id: int) -> bool:
        return cast(bool, self._dll.QLclipboard_RestoreSnapshot(ctypes.c_int(snapshot_id)) == 0)

    def free_snapshot(self, snapshot_id: int) -> None:
        self._dll.QLclipboard_FreeSnapshot(ctypes.c_int(snapshot_id))
        self._snapshot_sizes.pop(snapshot_id, None)

    def enum_formats(self, max_formats: int = 64) -> list[dict]:
        buf = (QLClipboardFormatInfo * max_formats)()
        n = self._dll.QLclipboard_EnumFormats(buf, ctypes.c_int(max_formats))
        if n < 0:
            return []
        results: list[dict] = []
        for i in range(min(n, max_formats)):
            results.append(
                {
                    "formatId": buf[i].formatId,
                    "name": buf[i].name.decode("utf-8", errors="replace").rstrip("\x00"),
                }
            )
        return results

    def get_sequence_number(self) -> int:
        seq = ctypes.c_int()
        self._dll.QLclipboard_GetSequenceNumber(ctypes.byref(seq))
        return seq.value

    def build_html_format(self, html_content: str) -> bytes:
        html_b = html_content.encode("utf-8")
        buf = ctypes.create_string_buffer(65536)
        n = self._dll.QLclipboard_BuildHtmlFormat(html_b, buf, ctypes.c_int(65536))
        if n < 0:
            raise RuntimeError("QLclipboard_BuildHtmlFormat failed")
        return buf.raw[:n]

    @property
    def snapshot_sizes(self) -> dict[int, int]:
        return dict(self._snapshot_sizes)


# ---------------------------------------------------------------------------
# QLautostart: native auto-start management
# ---------------------------------------------------------------------------

_AUTOSTART_ERROR_LABELS: dict[int, str] = {
    0: "ok",
    1: "cancelled",
    2: "failed",
    3: "bad_args",
    4: "target_missing",
    5: "not_supported",
}


class QLAutostartStatus(ctypes.Structure):
    _fields_ = [
        ("method", ctypes.c_int),
        ("enabled", ctypes.c_int),
        ("reason", ctypes.c_wchar_p),
    ]


class _QLAutostartEngine:
    """Singleton wrapping QLautostart.dll for Windows auto-start management."""

    _instance: _QLAutostartEngine | None = None

    def __init__(self) -> None:
        self._dll = QLautostart().dll

    @classmethod
    def get(cls) -> _QLAutostartEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def enable(
        self, exe_path: str, arguments: str = "", working_dir: str = "", is_admin: bool = False
    ) -> tuple[int, str]:
        rc = self._dll.QLautostart_Enable(
            ctypes.c_wchar_p(exe_path),
            ctypes.c_wchar_p(arguments) if arguments else None,
            ctypes.c_wchar_p(working_dir) if working_dir else None,
            ctypes.c_int(1 if is_admin else 0),
        )
        return rc, _AUTOSTART_ERROR_LABELS.get(rc, f"unknown({rc})")

    def disable(self, is_admin: bool = False) -> tuple[int, str]:
        rc = self._dll.QLautostart_Disable(ctypes.c_int(1 if is_admin else 0))
        return rc, _AUTOSTART_ERROR_LABELS.get(rc, f"unknown({rc})")

    def is_enabled(self) -> bool:
        return bool(self._dll.QLautostart_IsEnabled())

    def get_method(self) -> int:
        return cast(int, self._dll.QLautostart_GetMethod())

    def get_status(self) -> dict:
        status = QLAutostartStatus()
        self._dll.QLautostart_GetStatus(ctypes.byref(status))
        return {
            "method": status.method,
            "enabled": bool(status.enabled),
            "reason": status.reason if status.reason else "",
        }

    def run_helper(self, action: str, exe_path: str, arguments: str = "", working_dir: str = "") -> int:
        return cast(
            int,
            self._dll.QLautostart_RunHelper(
                ctypes.c_wchar_p(action),
                ctypes.c_wchar_p(exe_path),
                ctypes.c_wchar_p(arguments) if arguments else None,
                ctypes.c_wchar_p(working_dir) if working_dir else None,
            ),
        )

    def run_launcher(self, exe_path: str, arguments: str = "", working_dir: str = "") -> int:
        return cast(
            int,
            self._dll.QLautostart_RunLauncher(
                ctypes.c_wchar_p(exe_path),
                ctypes.c_wchar_p(arguments) if arguments else None,
                ctypes.c_wchar_p(working_dir) if working_dir else None,
            ),
        )

    def is_allowed_target(self, exe_path: str, arguments: str = "", working_dir: str = "") -> bool:
        return bool(
            self._dll.QLautostart_IsAllowedTarget(
                ctypes.c_wchar_p(exe_path),
                ctypes.c_wchar_p(arguments) if arguments else None,
                ctypes.c_wchar_p(working_dir) if working_dir else None,
            )
        )

    def cleanup_legacy_tasks(self) -> int:
        return cast(int, self._dll.QLautostart_CleanupLegacyTasks())


# ---------------------------------------------------------------------------
# QLicon: native icon extraction
# ---------------------------------------------------------------------------


class QLIconOptions(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("iconIndex", ctypes.c_int),
    ]


class QLIconResult(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("channels", ctypes.c_int),
        ("pixelCount", ctypes.c_int),
    ]


class _QLIconEngine:
    """Singleton wrapping QLicon.dll for file icon extraction."""

    _instance: _QLIconEngine | None = None
    _MAX_RGBA_SIZE = 256 * 256 * 4  # 256KB for 256px icons

    def __init__(self) -> None:
        self._dll = QLicon().dll

    @classmethod
    def get(cls) -> _QLIconEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def extract_from_file(self, file_path: str, size: int = 32, flags: int = 0x05, icon_index: int = 0) -> dict | None:
        opt = QLIconOptions(size=size, flags=flags, iconIndex=icon_index)
        result = QLIconResult()
        buf = (ctypes.c_ubyte * self._MAX_RGBA_SIZE)()
        rc = self._dll.QLicon_ExtractFromFile(
            ctypes.c_wchar_p(file_path),
            ctypes.byref(opt),
            buf,
            ctypes.byref(result),
        )
        if rc != 0:
            return None
        return {
            "width": result.width,
            "height": result.height,
            "channels": result.channels,
            "pixel_count": result.pixelCount,
            "rgba": bytes(buf[: result.pixelCount * 4]),
        }

    def extract_from_resource(self, file_path: str, icon_index: int = 0, size: int = 32) -> dict | None:
        out_width = ctypes.c_int()
        out_height = ctypes.c_int()
        buf = (ctypes.c_ubyte * self._MAX_RGBA_SIZE)()
        rc = self._dll.QLicon_ExtractFromResource(
            ctypes.c_wchar_p(file_path),
            ctypes.c_int(icon_index),
            ctypes.c_int(size),
            buf,
            ctypes.byref(out_width),
            ctypes.byref(out_height),
        )
        if rc != 0:
            return None
        pixels = out_width.value * out_height.value
        return {
            "width": out_width.value,
            "height": out_height.value,
            "rgba": bytes(buf[: pixels * 4]),
        }

    def load_image_file(self, image_path: str, size: int = 0) -> dict | None:
        out_width = ctypes.c_int()
        out_height = ctypes.c_int()
        buf = (ctypes.c_ubyte * self._MAX_RGBA_SIZE)()
        rc = self._dll.QLicon_LoadImageFile(
            ctypes.c_wchar_p(image_path),
            ctypes.c_int(size),
            buf,
            ctypes.byref(out_width),
            ctypes.byref(out_height),
        )
        if rc != 0:
            return None
        pixels = out_width.value * out_height.value
        return {
            "width": out_width.value,
            "height": out_height.value,
            "rgba": bytes(buf[: pixels * 4]),
        }

    def is_empty(self, rgba: bytes, width: int, height: int) -> bool:
        buf = (ctypes.c_ubyte * len(rgba)).from_buffer_copy(rgba)
        return bool(self._dll.QLicon_IsEmpty(buf, ctypes.c_int(width), ctypes.c_int(height)))

    def get_file_type_name(self, file_path: str) -> str:
        buf = ctypes.create_unicode_buffer(256)
        n = self._dll.QLicon_GetFileTypeName(ctypes.c_wchar_p(file_path), buf, ctypes.c_int(256))
        if n < 0:
            return ""
        return buf.value


# ---------------------------------------------------------------------------
# QLupdate: native update management
# ---------------------------------------------------------------------------

UPDATE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)


class _QLUpdateEngine:
    """Singleton wrapping QLupdate.dll for update check/download/install."""

    _instance: _QLUpdateEngine | None = None

    _EVENT_NAMES: dict[int, str] = {
        0: "check_complete",
        1: "check_failed",
        2: "up_to_date",
        3: "update_available",
        4: "update_skipped",
        5: "auto_download",
        6: "download_progress",
        7: "download_finished",
        8: "download_failed",
        9: "download_cancelled",
        10: "install_started",
        11: "install_failed",
        12: "error",
    }

    def __init__(self) -> None:
        self._dll = QLupdate().dll
        self._callback: ctypes._FuncPointer | None = None
        self._listeners: list[Callable[[int, str], None]] = []

    @classmethod
    def get(cls) -> _QLUpdateEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _make_callback(self, listener: Callable[[int, str], None]) -> ctypes._FuncPointer:
        def bridge(event: int, json_data: bytes | None) -> None:
            try:
                data_str = json_data.decode("utf-8") if json_data else "{}"
                listener(event, data_str)
            except Exception:
                logger.debug("QLupdate callback error", exc_info=True)

        self._callback = UPDATE_CALLBACK(bridge)
        return self._callback

    def check(
        self, current_version: str, update_source: str, config_json: str, listener: Callable[[int, str], None]
    ) -> int:
        cb = self._make_callback(listener)
        return cast(
            int,
            self._dll.QLupdate_Check(
                current_version.encode("utf-8"),
                update_source.encode("utf-8"),
                config_json.encode("utf-8"),
                cb,
            ),
        )

    def download(
        self,
        url: str,
        target_dir: str,
        version: str,
        expected_hash: str = "",
        expected_size: int = 0,
        max_bytes: int = 0,
        allowed_hosts_json: str = "[]",
        verify_ssl: bool = True,
        allow_insecure_http: bool = False,
        listener: Callable[[int, str], None] | None = None,
    ) -> int:
        cb = self._make_callback(listener) if listener else None
        return cast(
            int,
            self._dll.QLupdate_Download(
                url.encode("utf-8"),
                expected_hash.encode("utf-8") if expected_hash else None,
                ctypes.c_longlong(expected_size),
                ctypes.c_longlong(max_bytes),
                target_dir.encode("utf-8"),
                version.encode("utf-8"),
                allowed_hosts_json.encode("utf-8"),
                ctypes.c_int(1 if verify_ssl else 0),
                ctypes.c_int(1 if allow_insecure_http else 0),
                cb if cb else None,
            ),
        )

    def cancel_download(self) -> None:
        self._dll.QLupdate_CancelDownload()

    def install(
        self,
        installer_path: str,
        install_dir: str,
        expected_hash: str = "",
        trusted_dir: str = "",
        log_path: str = "",
        listener: Callable[[int, str], None] | None = None,
    ) -> int:
        cb = self._make_callback(listener) if listener else None
        return cast(
            int,
            self._dll.QLupdate_Install(
                installer_path.encode("utf-8"),
                expected_hash.encode("utf-8") if expected_hash else None,
                install_dir.encode("utf-8"),
                trusted_dir.encode("utf-8") if trusted_dir else None,
                log_path.encode("utf-8") if log_path else None,
                cb if cb else None,
            ),
        )

    def get_latest_session(self, base_dir: str) -> str | None:
        buf = ctypes.create_string_buffer(65536)
        n = self._dll.QLupdate_GetLatestSession(base_dir.encode("utf-8"), buf, ctypes.c_int(65536))
        if n < 0:
            return None
        return buf.value.decode("utf-8")

    def confirm_first_start(self, base_dir: str) -> bool:
        return cast(bool, self._dll.QLupdate_ConfirmFirstStart(base_dir.encode("utf-8")) == 0)

    def validate_download_url(self, url: str, allowed_hosts_json: str = "[]", allow_insecure: bool = False) -> bool:
        return cast(
            bool,
            self._dll.QLupdate_ValidateDownloadUrl(
                url.encode("utf-8"),
                allowed_hosts_json.encode("utf-8"),
                ctypes.c_int(1 if allow_insecure else 0),
            )
            == 0,
        )

    def check_connectivity(self) -> bool:
        return cast(bool, self._dll.QLupdate_CheckConnectivity() == 0)
