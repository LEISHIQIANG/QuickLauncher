"""Screenshot OCR plugin for QuickLauncher."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path

from core.command_registry import COMMAND_INTERACTION_DIRECT, CommandAction, CommandParam, CommandResult

SENTINEL = "QL_SCREENSHOT_OCR_RESULT="
HELPER_TIMEOUT_SECONDS = 300
_TASK_LOCK = threading.Lock()
_HELPER_CMD_LOCK = threading.Lock()
_PLUGIN_API = None
_INJECTED_SITE: str | None = None
_CACHED_HELPER_CMD: list[str] | None = None
_WARMUP_TIMER: threading.Timer | None = None


def _runtime_site() -> Path | None:
    site = Path(__file__).resolve().parent / "runtime" / "site-packages"
    return site if (site / "wx").is_dir() else None


def register(api):
    global _PLUGIN_API, _INJECTED_SITE, _WARMUP_TIMER
    _PLUGIN_API = api
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
            CommandParam(
                name="show_window", type="bool", required=False, default="false", label="显示执行窗口", advanced=True
            ),
            CommandParam(
                name="capture_output", type="bool", required=False, default="true", label="捕获输出", advanced=True
            ),
        ],
    )
    # Avoid competing with QuickLauncher's first paint and popup preparation.
    _WARMUP_TIMER = threading.Timer(2.0, _warmup_cmd)
    _WARMUP_TIMER.daemon = True
    _WARMUP_TIMER.start()


def dispose(api=None):
    global _INJECTED_SITE, _CACHED_HELPER_CMD, _WARMUP_TIMER
    if _WARMUP_TIMER is not None:
        _WARMUP_TIMER.cancel()
        _WARMUP_TIMER = None
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
    if _PLUGIN_API is None:
        return {"status": "error", "message": "插件 API 未初始化"}
    helper = Path(__file__).resolve().parent / "ocr_runner.py"
    helper_cmd = _find_helper_command(helper)
    if not helper_cmd:
        return {"status": "error", "message": "未找到可运行截图 OCR 的运行环境"}

    try:
        completed = _PLUGIN_API.run_process_capture(
            [*helper_cmd, *helper_args],
            cwd=str(helper.parent),
            timeout=HELPER_TIMEOUT_SECONDS,
            inherit_environment=True,
            helper_output_file=True,
        )
    except TimeoutError:
        return {"status": "error", "message": "OCR 任务超时"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    if completed.get("timed_out"):
        return {"status": "error", "message": "OCR 任务超时"}

    parsed = _parse_helper_stdout(str(completed.get("stdout") or ""))
    if parsed:
        return parsed
    stderr = str(completed.get("stderr") or "").strip()
    stdout = str(completed.get("stdout") or "").strip()
    message = stderr or stdout or f"OCR Helper 退出码: {completed.get('returncode')}"
    return {"status": "error", "message": message}


def _parse_helper_stdout(stdout: str) -> dict:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(SENTINEL):
            try:
                parsed = json.loads(line[len(SENTINEL) :])
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
    with _HELPER_CMD_LOCK:
        if _CACHED_HELPER_CMD is not None:
            return _CACHED_HELPER_CMD

        site_packages = Path(__file__).resolve().parent / "runtime" / "site-packages"
        current = Path(sys.executable or "")
        runtime_tag = _bundled_wx_python_tag(site_packages)

        if (
            current.exists()
            and current.name.lower().startswith("python")
            and _current_python_matches(runtime_tag)
            and _python_has_wx([str(current)])
        ):
            _inject_site_to_env(site_packages)
            _CACHED_HELPER_CMD = [str(current), str(helper)]
            return _CACHED_HELPER_CMD

        if current.exists() and not current.name.lower().startswith("python"):
            cmd = [str(current), "--plugin-helper", str(helper)]
            if site_packages.is_dir():
                cmd.extend(["--plugin-site", str(site_packages)])
            cmd.append("--")
            _CACHED_HELPER_CMD = cmd
            return _CACHED_HELPER_CMD

        cmd = _find_system_python_command()
        if cmd:
            _CACHED_HELPER_CMD = [*cmd, str(helper)]
        else:
            _CACHED_HELPER_CMD = []
        return _CACHED_HELPER_CMD


def _inject_site_to_env(site_packages: Path) -> None:
    site_str = str(site_packages)
    wx_str = str(site_packages / "wx")
    parts = [p for p in (os.environ.get("PYTHONPATH", "") or "").split(os.pathsep) if p]
    for p in (wx_str, site_str):
        if p not in parts:
            parts.insert(0, p)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)


def _find_system_python_command() -> list[str]:
    site_packages = Path(__file__).resolve().parent / "runtime" / "site-packages"
    runtime_tag = _bundled_wx_python_tag(site_packages)
    candidates: list[list[str]] = []
    current = Path(sys.executable or "")
    if current.name.lower().startswith("python") and current.exists() and _current_python_matches(runtime_tag):
        candidates.append([str(current)])
    py_versions = []
    if runtime_tag and runtime_tag.startswith("cp") and len(runtime_tag) >= 4:
        py_versions.append(f"-{runtime_tag[2]}.{runtime_tag[3:]}")
    py_versions.extend(["-3.12", "-3.13"])

    for name in ("py.exe", "python.exe", "python"):
        found = shutil.which(name)
        if found:
            if Path(found).name.lower() == "py.exe":
                candidates.extend([[found, version] for version in py_versions])
                candidates.append([found])
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
    if _PLUGIN_API is None:
        return False
    site_packages = Path(__file__).resolve().parent / "runtime" / "site-packages"
    wx_dir = site_packages / "wx"
    runtime_tag = _bundled_wx_python_tag(site_packages)
    code = (
        "import os,sys\n"
        f"wx_dir = r'{str(wx_dir)}'\n"
        f"site = r'{str(site_packages)}'\n"
        "for p in (wx_dir, site):\n"
        "    sys.path.insert(0, p)\n"
        "    os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')\n"
        "    add = getattr(os, 'add_dll_directory', None)\n"
        "    if add:\n"
        "        add(p)\n"
        "tag = f'cp{sys.version_info[0]}{sys.version_info[1]}'\n"
        f"runtime_tag = {runtime_tag!r}\n"
        "if runtime_tag and tag != runtime_tag:\n"
        "    raise SystemExit(1)\n"
        "import wx\n"
        "import win32gui\n"
        "raise SystemExit(0)\n"
    )
    try:
        r = _PLUGIN_API.run_process_capture(
            [*command, "-c", code],
            timeout=5,
            inherit_environment=True,
        )
        return int(r.get("returncode", -1)) == 0
    except Exception:
        return False


def _bundled_wx_python_tag(site_packages: Path) -> str:
    try:
        wx_dir = site_packages / "wx"
        for path in wx_dir.glob("_core.cp*-win_amd64.pyd"):
            name = path.name
            start = name.find(".cp")
            if start >= 0:
                return name[start + 1 :].split("-", 1)[0]
    except Exception:
        return ""
    return ""


def _current_python_matches(runtime_tag: str) -> bool:
    if not runtime_tag:
        return True
    return runtime_tag == f"cp{sys.version_info[0]}{sys.version_info[1]}"
