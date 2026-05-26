"""Disk Cleaner plugin — analyze disk usage and safely clean C drive space."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from pathlib import Path

from core.command_registry import CommandAction, CommandResult

SAFE_CLEAN_CATEGORIES = {
    "recycle": "回收站",
    "temp": "%TEMP% 缓存",
    "prefetch": "Windows Prefetch",
    "cache_chrome": "Chrome 缓存",
    "cache_edge": "Edge 缓存",
    "recent": "最近文档历史",
    "delivery_opt": "Delivery Optimization 缓存",
    "thumbcache": "缩略图缓存",
}

SCAN_TIMEOUT = 5.0
MAX_ANALYZE_DEPTH = 3
_PLUGIN_API = None

CATEGORY_ALIASES = {
    "recycle": "recycle",
    "recyclebin": "recycle",
    "bin": "recycle",
    "回收站": "recycle",
    "temp": "temp",
    "tmp": "temp",
    "临时文件": "temp",
    "prefetch": "prefetch",
    "pf": "prefetch",
    "chrome": "cache_chrome",
    "cache_chrome": "cache_chrome",
    "edge": "cache_edge",
    "cache_edge": "cache_edge",
    "recent": "recent",
    "最近文档": "recent",
    "delivery_opt": "delivery_opt",
    "update": "delivery_opt",
    "windows update": "delivery_opt",
    "更新": "delivery_opt",
    "thumbcache": "thumbcache",
    "thumb": "thumbcache",
    "thumbnail": "thumbcache",
    "缩略图": "thumbcache",
}


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_elevated(cmd: str, args: str) -> tuple[bool, str]:
    """Run an elevated cleanup command through QuickLauncher's plugin API."""
    if _PLUGIN_API is None:
        return (False, "插件 API 未初始化，无法请求管理员权限")
    ok, error = _PLUGIN_API.launch_target(
        cmd,
        args,
        show_window=False,
        run_as_admin=True,
    )
    if ok:
        return (True, "已请求以管理员权限执行清理")
    return (False, error or "管理员权限请求失败")


def register(api):
    global _PLUGIN_API
    _PLUGIN_API = api
    api.register_command(
        id="disk_cleaner.analyze",
        title="目录大小分析",
        aliases=["disk-analyze", "dir-size", "磁盘分析", "目录大小"],
        description="扫描指定目录，按子目录大小排序显示 Top 10",
        category="系统工具",
        handler=_handle_analyze,
        search_terms=["directory size", "folder size", "磁盘占用", "文件夹大小"],
    )

    api.register_command(
        id="disk_cleaner.scan",
        title="可清理项扫描",
        aliases=["disk-scan", "clean-scan", "清理扫描", "可清理"],
        description="扫描 C 盘可安全清理的项并估算可释放空间",
        category="系统工具",
        handler=_handle_scan,
        search_terms=["disk cleanup", "c盘清理", "free space", "释放空间"],
    )

    api.register_command(
        id="disk_cleaner.clean",
        title="执行清理",
        aliases=["disk-clean", "clean-do", "执行清理"],
        description="清理指定类别（或全部）的可安全清理文件",
        category="系统工具",
        handler=_handle_clean,
        search_terms=["clean disk", "清理回收站", "清理临时文件", "clean cache"],
    )


def _format_bytes(size: int | float) -> str:
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(size)
    for u in units:
        if s < 1024 or u == units[-1]:
            return f"{s:.1f} {u}" if u != "B" else f"{int(s)} B"
        s /= 1024
    return f"{s:.1f} TB"


def _safe_path(path: str) -> Path | None:
    p = Path(path)
    return p if p.exists() else None


def _dir_size(path: Path, max_depth: int = 2, timeout_at: float = 0) -> int:
    total = 0
    try:
        if timeout_at and time.time() > timeout_at:
            return total
        with os.scandir(str(path)) as it:
            for entry in it:
                if timeout_at and time.time() > timeout_at:
                    break
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False) and max_depth > 0:
                        total += _dir_size(entry.path, max_depth - 1, timeout_at)
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


# ── Category scanners ─────────────────────────────────────────────────────

def _scan_recycle_bin() -> tuple[int, str]:
    try:
        from ctypes import wintypes
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("i64Size", ctypes.c_int64),
                ("i64NumItems", ctypes.c_int64),
            ]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if info.i64Size > 0:
            return (info.i64Size, f"回收站: {info.i64NumItems} 项 / ~{_format_bytes(info.i64Size)}")
    except Exception:
        pass
    return (0, "回收站 (请使用 '/disk-clean recycle' 清空)")


def _scan_temp() -> tuple[int, str]:
    temp_path = os.environ.get("TEMP") or os.environ.get("TMP") or ""
    temp = _safe_path(temp_path)
    if not temp:
        return (0, "%TEMP% 文件夹 (未找到)")

    size = _dir_size(temp, max_depth=2)
    return (size, f"%TEMP% 缓存 ({_format_bytes(size)})")


def _scan_prefetch() -> tuple[int, str]:
    path = _safe_path("C:\\Windows\\Prefetch")
    if not path:
        return (0, "Prefetch (未找到)")
    size = _dir_size(path, max_depth=1)
    need_admin = " [需管理员]" if not _is_admin() and size > 0 else ""
    return (size, f"Windows Prefetch ({_format_bytes(size)}){need_admin}")


def _scan_browser_cache(name: str, *paths: str) -> tuple[int, str]:
    for p in paths:
        expanded = os.path.expandvars(p)
        path = _safe_path(expanded)
        if path:
            size = _dir_size(path, max_depth=3)
            return (size, f"{name} 缓存 ({_format_bytes(size)})")
    return (0, f"{name} 缓存 (未找到)")


def _scan_recent() -> tuple[int, str]:
    recent = _safe_path(os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Recent"))
    if not recent:
        return (0, "最近文档 (未找到)")
    count = 0
    try:
        count = sum(1 for _ in os.scandir(str(recent)))
    except (OSError, PermissionError):
        pass
    return (0, f"最近文档: {count} 个快捷方式 (清理后不会释放大量空间)")


def _scan_delivery_opt() -> tuple[int, str]:
    path = _safe_path("C:\\Windows\\SoftwareDistribution\\Download")
    if not path:
        return (0, "Delivery Optimization (未找到)")
    size = _dir_size(path, max_depth=2)
    need_admin = " [需管理员]" if not _is_admin() and size > 0 else ""
    return (size, f"Delivery Optimization 缓存 ({_format_bytes(size)}){need_admin}")


def _scan_thumbcache() -> tuple[int, str]:
    path = _safe_path(os.path.expandvars("%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer"))
    if not path:
        return (0, "缩略图缓存 (未找到)")
    size = _dir_size(path, max_depth=1)
    return (size, f"缩略图缓存 ({_format_bytes(size)})")


SCANNERS_DICT = {
    "recycle": _scan_recycle_bin,
    "temp": _scan_temp,
    "prefetch": _scan_prefetch,
    "cache_chrome": lambda: _scan_browser_cache("Chrome",
        "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache",
        "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Code Cache"),
    "cache_edge": lambda: _scan_browser_cache("Edge",
        "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache",
        "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Code Cache"),
    "recent": _scan_recent,
    "delivery_opt": _scan_delivery_opt,
    "thumbcache": _scan_thumbcache,
}


# ── Cleaners ──────────────────────────────────────────────────────────────

def _clean_recycle_bin() -> tuple[bool, str]:
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
        return (True, "回收站已清空")
    except Exception as e:
        return (False, f"清空回收站失败: {e}")


def _clean_temp() -> tuple[bool, str]:
    temp_path = os.environ.get("TEMP") or os.environ.get("TMP") or ""
    if not temp_path or not os.path.isdir(temp_path):
        return (False, "%TEMP% 目录不存在")
    count = 0
    errors = 0
    try:
        for entry in os.scandir(temp_path):
            try:
                if entry.is_file(follow_symlinks=False):
                    os.remove(entry.path)
                    count += 1
                elif entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path, ignore_errors=True)
                    count += 1
            except (OSError, PermissionError, FileNotFoundError):
                errors += 1
    except (OSError, PermissionError, FileNotFoundError) as e:
        return (False, f"扫描 %TEMP% 失败: {e}")
    msg = f"已清理 {count} 项"
    if errors:
        msg += f" ({errors} 项跳过)"
    return (True, msg)


def _clean_prefetch() -> tuple[bool, str]:
    path = "C:\\Windows\\Prefetch"
    if not os.path.isdir(path):
        return (False, "Prefetch 目录不存在")
    if not _is_admin():
        return _run_elevated("cmd.exe", "/c del /f /q \"C:\\Windows\\Prefetch\\*.*\" >nul 2>&1")
    count = 0
    errors = 0
    for entry in os.scandir(path):
        try:
            if entry.is_file():
                os.remove(entry.path)
                count += 1
        except (OSError, PermissionError, FileNotFoundError):
            errors += 1
    msg = f"已清理 {count} 个 Prefetch 文件"
    if errors:
        msg += f" ({errors} 个跳过)"
    return (True, msg)


def _clean_browser_cache(name: str, *paths: str) -> tuple[bool, str]:
    count = 0
    errors = 0
    for p in paths:
        expanded = os.path.expandvars(p)
        path = Path(expanded)
        if not path.exists():
            continue
        try:
            c, e = _rmtree_fast(str(path), max_depth=4)
            count += c
            errors += e
        except Exception:
            errors += 1
    msg = f"已清理 {count} 个 {name} 缓存文件"
    if errors:
        msg += f" ({errors} 个跳过)"
    return (True, msg)


def _rmtree_fast(root: str, max_depth: int) -> tuple[int, int]:
    count = 0
    errors = 0
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        os.remove(entry.path)
                        count += 1
                    elif entry.is_dir(follow_symlinks=False) and max_depth > 0:
                        sc, se = _rmtree_fast(entry.path, max_depth - 1)
                        count += sc
                        errors += se
                        try:
                            os.rmdir(entry.path)
                        except OSError:
                            pass
                except (OSError, PermissionError, FileNotFoundError):
                    errors += 1
    except (OSError, PermissionError, FileNotFoundError):
        errors += 1
    return count, errors


def _clean_recent() -> tuple[bool, str]:
    recent = os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Recent")
    if not os.path.isdir(recent):
        return (False, "最近文档目录不存在")
    count = 0
    for entry in os.scandir(recent):
        try:
            if entry.is_file():
                os.remove(entry.path)
                count += 1
        except (OSError, PermissionError):
            pass
    return (True, f"已清理 {count} 个最近文档快捷方式")


def _clean_delivery_opt() -> tuple[bool, str]:
    path = "C:\\Windows\\SoftwareDistribution\\Download"
    if not os.path.isdir(path):
        return (False, "Delivery Optimization 目录不存在")
    if not _is_admin():
        cmd = ("/c net stop wuauserv /y >nul 2>&1 & net stop bits /y >nul 2>&1 & "
               "del /f /q \"C:\\Windows\\SoftwareDistribution\\Download\\*.*\" >nul 2>&1 & "
               "for /d %i in (\"C:\\Windows\\SoftwareDistribution\\Download\\*\") do "
               "rd /s /q \"%i\" 2>nul & net start wuauserv >nul 2>&1 & net start bits >nul 2>&1")
        return _run_elevated("cmd.exe", cmd)
    try:
        service_stopped = False
        try:
            subprocess.run(
                ["net", "stop", "wuauserv", "/y"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, creationflags=0x08000000,
            )
            subprocess.run(
                ["net", "stop", "bits", "/y"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, creationflags=0x08000000,
            )
            service_stopped = True
        except Exception:
            pass

        count = 0
        for entry in os.scandir(path):
            try:
                if entry.is_file():
                    os.remove(entry.path)
                    count += 1
                elif entry.is_dir():
                    shutil.rmtree(entry.path, ignore_errors=True)
                    count += 1
            except (OSError, PermissionError, FileNotFoundError):
                pass

        if service_stopped:
            try:
                subprocess.run(
                    ["net", "start", "wuauserv"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, creationflags=0x08000000,
                )
                subprocess.run(
                    ["net", "start", "bits"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, creationflags=0x08000000,
                )
            except Exception:
                pass

        return (True, f"已清理 {count} 个更新缓存文件")
    except Exception as e:
        return (False, f"清理更新缓存失败: {e}")


def _clean_thumbcache() -> tuple[bool, str]:
    path = os.path.expandvars("%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer")
    if not os.path.isdir(path):
        return (False, "缩略图缓存目录不存在")
    count = 0
    for entry in os.scandir(path):
        try:
            if entry.is_file() and entry.name.endswith(".db"):
                os.remove(entry.path)
                count += 1
        except (OSError, PermissionError):
            pass
    return (True, f"已清理 {count} 个缩略图缓存文件")


CLEANERS = {
    "recycle": _clean_recycle_bin,
    "temp": _clean_temp,
    "prefetch": _clean_prefetch,
    "cache_chrome": lambda: _clean_browser_cache("Chrome",
        "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache",
        "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Code Cache"),
    "cache_edge": lambda: _clean_browser_cache("Edge",
        "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache",
        "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Code Cache"),
    "recent": _clean_recent,
    "delivery_opt": _clean_delivery_opt,
    "thumbcache": _clean_thumbcache,
}


# ── Handlers ──────────────────────────────────────────────────────────────

def _handle_analyze(context) -> CommandResult:
    target = (context.args_text or "").strip()
    if not target:
        if context.selected_files:
            target = context.selected_files[0]
        else:
            target = os.environ.get("SystemDrive", "C:") + "\\"

    path = _safe_path(target)
    if not path:
        return CommandResult(
            success=False,
            message=f"路径不存在: {target}",
            error="路径无效",
        )

    if path.is_file():
        size = path.stat().st_size
        return CommandResult(
            success=True,
            message=f"{path}\n大小: {_format_bytes(size)}",
            actions=[CommandAction(type="copy", label="复制路径", value=str(path))],
        )

    timeout_at = time.time() + SCAN_TIMEOUT
    entries: list[tuple[str, int]] = []

    try:
        with os.scandir(str(path)) as it:
            for entry in it:
                if time.time() > timeout_at:
                    entries.append(("(扫描超时)", 0))
                    break
                try:
                    if entry.is_dir(follow_symlinks=False):
                        sz = _dir_size(entry.path, max_depth=MAX_ANALYZE_DEPTH, timeout_at=timeout_at)
                        entries.append((entry.name, sz))
                    elif entry.is_file(follow_symlinks=False):
                        sz = entry.stat(follow_symlinks=False).st_size
                        entries.append((entry.name, sz))
                except (OSError, PermissionError):
                    entries.append((entry.name + " (无权限)", 0))
    except (OSError, PermissionError) as e:
        return CommandResult(
            success=False,
            message=f"无法扫描目录: {e}",
            error=str(e),
        )

    entries.sort(key=lambda x: -x[1])
    total = sum(sz for _, sz in entries)

    lines = [f"目录: {path}", f"总量: {_format_bytes(total)}", ""]
    lines.append("Top 10 最大子项:")
    for name, sz in entries[:10]:
        pct = (sz / total * 100) if total > 0 else 0
        lines.append(f"  {_format_bytes(sz):>10}  {pct:5.1f}%  {name}")

    if len(entries) > 10:
        lines.append(f"  ... 共 {len(entries)} 个子项")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=result,
        display_type="table",
        payload={
            "window_size": "large",
            "columns": ["Name", "Size", "Percent"],
            "rows": [
                [name, _format_bytes(size), f"{(size / total * 100) if total > 0 else 0:.1f}%"]
                for name, size in entries[:10]
            ],
            "copy_format": "tsv",
        },
        actions=[CommandAction(type="copy", label="复制报告", value=result)],
    )


def _handle_scan(context) -> CommandResult:
    lines = ["C 盘可安全清理项扫描", "=" * 40, ""]
    total_safe = 0
    results: list[tuple[str, str, int]] = []

    for cat_id, name in SAFE_CLEAN_CATEGORIES.items():
        scanner = SCANNERS_DICT.get(cat_id)
        if not scanner:
            continue
        try:
            size, desc = scanner()
        except Exception as e:
            results.append((name, f"扫描失败: {e}", 0))
            continue
        results.append((name, desc, size))
        total_safe += size

    for name, desc, _ in results:
        lines.append(f"  {name}")
        lines.append(f"    {desc}")
        lines.append("")

    lines.append(f"估算可释放: {_format_bytes(total_safe)}")
    lines.append("使用 '/disk-clean' 一键清理全部。")

    result = "\n".join(lines)
    return CommandResult(
        success=True,
        message=result,
        display_type="list",
        payload={
            "window_size": "medium",
            "items": [
                {
                    "title": name,
                    "status": "success" if size > 0 else "skipped",
                    "detail": desc,
                }
                for name, desc, size in results
            ],
        },
        actions=[CommandAction(type="copy", label="复制扫描报告", value=result)],
    )


def _handle_clean(context) -> CommandResult:
    try:
        args = (context.args_text or "").strip().lower()
        if not args or args == "all":
            categories = list(CLEANERS.keys())
        else:
            canonical = CATEGORY_ALIASES.get(args)
            if canonical and canonical in CLEANERS:
                categories = [canonical]
            else:
                return CommandResult(
                    success=False,
                    message=f"未知类别: {args}\n可用: recycle / temp / prefetch / chrome / edge / update / thumb / all，也支持中文",
                    error="未知类别",
                )

        cat_id = categories[0] if len(categories) == 1 else None
        if cat_id:
            name = SAFE_CLEAN_CATEGORIES.get(cat_id, cat_id)
            try:
                ok, msg = CLEANERS[cat_id]()
            except (OSError, PermissionError) as e:
                ok, msg = False, str(e) or "无权限访问"
            status = "✅" if ok else "❌"
            result = f"清理 {name}...\n{status} {msg}"
            return CommandResult(
                success=ok,
                message=result,
                display_type="list",
                payload={
                    "window_size": "medium",
                    "items": [
                        {
                            "title": name,
                            "status": "success" if ok else "failed",
                            "detail": msg,
                        }
                    ],
                },
                actions=[CommandAction(type="copy", label="复制结果", value=result)],
            )

        lines = ["批量清理结果:"]
        all_ok = True
        for cat_id in categories:
            name = SAFE_CLEAN_CATEGORIES.get(cat_id, cat_id)
            try:
                ok, msg = CLEANERS[cat_id]()
                status = "✅" if ok else "❌"
                lines.append(f"{status} [{name}] {msg}")
                if not ok:
                    all_ok = False
            except BaseException as e:
                err = str(e) or "未知错误"
                lines.append(f"❌ [{name}] 清理失败: {err}")
                all_ok = False

        result = "\n".join(lines)
        return CommandResult(
            success=all_ok,
            message=result,
            display_type="list",
            payload={
                "window_size": "medium",
                "items": [
                    {
                        "title": line.split("]", 1)[0].strip("✅❌ [") if "]" in line else line,
                        "status": "failed" if line.startswith("❌") else "success",
                        "detail": line,
                    }
                    for line in lines[1:]
                ],
            },
            actions=[CommandAction(type="copy", label="复制结果", value=result)],
        )
    except BaseException as e:
        err = str(e) or "未知错误"
        return CommandResult(
            success=False,
            message=f"清理任务异常: {err}",
            error=err,
        )
