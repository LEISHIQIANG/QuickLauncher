"""Screenshot OCR plugin for QuickLauncher."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from core.command_registry import COMMAND_INTERACTION_DIRECT, CommandAction, CommandParam, CommandResult

SENTINEL = "QL_SCREENSHOT_OCR_RESULT="
HELPER_TIMEOUT_SECONDS = 300
_TASK_LOCK = threading.Lock()
_INJECTED_SITE: str | None = None
_CACHED_HELPER_CMD: list[str] | None = None


def _runtime_site() -> Path | None:
    site = Path(__file__).resolve().parent / "runtime" / "site-packages"
    return site if (site / "wx").is_dir() else None


def register(api):
    global _INJECTED_SITE
    site = _runtime_site()
    if site is not None:
        site_str = str(site)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)
        _INJECTED_SITE = site_str
        wx_dir = site / "wx"
        wx_str = str(wx_dir)
        if wx_str not in sys.path:
            sys.path.insert(0, wx_str)
        for d in (site_str, wx_str):
            if os.path.isdir(d):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                add_dll = getattr(os, "add_dll_directory", None)
                if add_dll:
                    try:
                        add_dll(d)
                    except OSError:
                        pass

    api.register_builtin_command(
        id="screenshot-ocr",
        title="截图OCR",
        aliases=["screenshot_ocr", "截图ocr"],
        description="框选屏幕区域并 OCR 识别文字，结果显示在命令面板。",
        category="system",
        handler=handle_capture,
        interaction_mode=COMMAND_INTERACTION_DIRECT,
        search_terms=["screen ocr", "截图识别", "文字识别"],
        result_window_size="medium",
        params=[
            CommandParam(name="show_window", type="bool", required=False, default="false", label="显示执行窗口", advanced=True),
            CommandParam(name="capture_output", type="bool", required=False, default="true", label="捕获输出", advanced=True),
        ],
    )
    # 后台提前检测并缓存命令路径
    threading.Thread(target=_warmup_cmd, daemon=True).start()


def dispose(api=None):
    global _INJECTED_SITE, _CACHED_HELPER_CMD
    _CACHED_HELPER_CMD = None
    if _INJECTED_SITE:
        wx_str = str(Path(_INJECTED_SITE) / "wx")
        for p in (_INJECTED_SITE, wx_str):
            try:
                sys.path.remove(p)
            except ValueError:
                pass
        _INJECTED_SITE = None


def handle_capture(context) -> CommandResult:
    with _TASK_LOCK:
        return _run_helper_as_result([])


def _warmup_cmd() -> None:
    helper = Path(__file__).resolve().parent / "ocr_runner.py"
    _find_helper_command(helper)


def _run_helper_as_result(helper_args: list[str]) -> CommandResult:
    payload = _run_helper(helper_args)
    return _payload_to_result(payload)


def _run_helper(helper_args: list[str]) -> dict:
    helper = Path(__file__).resolve().parent / "ocr_runner.py"
    helper_cmd = _find_helper_command(helper)
    if not helper_cmd:
        return {"status": "error", "message": "未找到可运行截图 OCR 的运行环境"}

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            [*helper_cmd, *helper_args],
            cwd=str(helper.parent),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=HELPER_TIMEOUT_SECONDS,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "OCR 任务超时"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    parsed = _parse_helper_stdout(completed.stdout)
    if parsed:
        return parsed
    stderr = (completed.stderr or "").strip()
    message = stderr or (completed.stdout or "").strip() or f"OCR Helper 退出码: {completed.returncode}"
    return {"status": "error", "message": message}


def _parse_helper_stdout(stdout: str) -> dict:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(SENTINEL):
            try:
                parsed = json.loads(line[len(SENTINEL):])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _payload_to_result(payload: dict) -> CommandResult:
    status = str(payload.get("status") or "")
    message = str(payload.get("message") or "")
    text = str(payload.get("text") or "")
    line_count = int(payload.get("line_count") or 0)

    if status == "cancelled":
        return CommandResult(
            success=True,
            message=message or "已取消 OCR 截图",
            payload={"_suppress_result_panel": True, "outputs": {"text": ""}},
        )
    if status != "ok":
        return CommandResult(
            success=False,
            message=message or "OCR 识别失败",
            error="识别失败",
            payload={"outputs": {"text": ""}},
        )
    if not text:
        return CommandResult(
            success=True,
            message="未识别到文字。",
            display_type="text",
            payload={"line_count": 0, "outputs": {"text": ""}},
        )
    return CommandResult(
        success=True,
        message=text,
        display_type="text",
        payload={
            "line_count": line_count,
            "outputs": {"text": text, "line_count": str(line_count)},
        },
        actions=[
            CommandAction(type="copy", label="复制文字", value=text, primary=True),
            CommandAction(type="save_text", label="保存文本", value=text),
        ],
    )


def _find_helper_command(helper: Path) -> list[str]:
    global _CACHED_HELPER_CMD
    if _CACHED_HELPER_CMD is not None:
        return _CACHED_HELPER_CMD

    site_packages = Path(__file__).resolve().parent / "runtime" / "site-packages"
    current = Path(sys.executable or "")

    if (site_packages / "wx").is_dir() and current.exists():
        _inject_site_to_env(site_packages)
        _CACHED_HELPER_CMD = [str(current), str(helper)]
        return _CACHED_HELPER_CMD

    cmd = _find_system_python_command()
    if cmd:
        _CACHED_HELPER_CMD = [*cmd, str(helper)]
        return _CACHED_HELPER_CMD
    return []


def _inject_site_to_env(site_packages: Path) -> None:
    site_str = str(site_packages)
    wx_str = str(site_packages / "wx")
    parts = [p for p in (os.environ.get("PYTHONPATH", "") or "").split(os.pathsep) if p]
    for p in (wx_str, site_str):
        if p not in parts:
            parts.insert(0, p)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)


def _find_system_python_command() -> list[str]:
    candidates: list[list[str]] = []
    current = Path(sys.executable or "")
    if current.name.lower().startswith("python") and current.exists():
        candidates.append([str(current)])
    for name in ("python.exe", "python", "py.exe"):
        found = shutil.which(name)
        if found:
            if Path(found).name.lower() == "py.exe":
                candidates.extend([[found, "-3.13"], [found, "-3.12"], [found]])
            else:
                candidates.append([found])
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key in seen:
            continue
        seen.add(key)
        if _python_has_wx(candidate):
            return candidate
    return []


def _python_has_wx(command: list[str]) -> bool:
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run(
            [*command, "-c", "import importlib.util,sys;raise SystemExit(0 if importlib.util.find_spec('wx') else 1)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, creationflags=creationflags,
        )
        return r.returncode == 0
    except Exception:
        return False
