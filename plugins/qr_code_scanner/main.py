"""Screenshot QR code scanner plugin for QuickLauncher."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import threading
from pathlib import Path

from core.command_registry import COMMAND_INTERACTION_DIRECT, CommandAction, CommandResult

logger = logging.getLogger(__name__)
SENTINEL = "QL_SCREENSHOT_QR_RESULT="
HELPER_TIMEOUT_SECONDS = 120
_TASK_LOCK = threading.Lock()
_PLUGIN_API = None
_CACHED_HELPER_CMD: list[str] | None = None
_WARMUP_TIMER: threading.Timer | None = None
PERSISTENT_WORKER = "qr_worker.py"
PERSISTENT_SITE_PATHS = ["runtime/site-packages"]
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_DOMAIN_RE = re.compile(r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d{1,5})?(?:/[^\s]*)?$")


def register(api):
    global _PLUGIN_API, _WARMUP_TIMER
    _PLUGIN_API = api
    api.register_builtin_command(
        id="screenshot-qr",
        title="截图二维码识别",
        aliases=["screenshot_qr", "qr", "二维码识别", "截图二维码"],
        description="框选屏幕区域并识别单个二维码，直接显示内容并提供复制/打开动作。",
        category="system",
        handler=handle_capture,
        interaction_mode=COMMAND_INTERACTION_DIRECT,
        search_terms=["qr code", "qrcode", "截图识别二维码", "扫码"],
        result_window_size="medium",
    )
    _WARMUP_TIMER = threading.Timer(2.5, _warmup_cmd)
    _WARMUP_TIMER.daemon = True
    _WARMUP_TIMER.start()


def dispose(api=None):
    global _PLUGIN_API, _CACHED_HELPER_CMD, _WARMUP_TIMER
    if _WARMUP_TIMER is not None:
        _WARMUP_TIMER.cancel()
        _WARMUP_TIMER = None
    plugin_api = api or _PLUGIN_API
    if plugin_api is not None and hasattr(plugin_api, "stop_persistent_helper"):
        try:
            plugin_api.stop_persistent_helper(PERSISTENT_WORKER)
        except Exception:
            logger.debug("停止二维码识别常驻 worker 失败", exc_info=True)
    _CACHED_HELPER_CMD = None
    _PLUGIN_API = None


def handle_capture(context) -> CommandResult:
    with _TASK_LOCK:
        payload = _run_helper([])
    return _payload_to_result(payload)


def _warmup_cmd() -> None:
    if _PLUGIN_API is None:
        return
    try:
        _PLUGIN_API.prewarm_persistent_helper(
            PERSISTENT_WORKER,
            site_paths=PERSISTENT_SITE_PATHS,
            timeout=30.0,
            inherit_environment=True,
        )
    except Exception as exc:
        _PLUGIN_API.logger.warning("二维码常驻运行时预热失败，将在执行时回退: %s", exc)


def _run_helper(helper_args: list[str]) -> dict:
    if _PLUGIN_API is None:
        return {"status": "error", "message": "插件 API 未初始化"}
    try:
        return _PLUGIN_API.request_persistent_helper(
            PERSISTENT_WORKER,
            {"operation": "capture", "args": list(helper_args or [])},
            site_paths=PERSISTENT_SITE_PATHS,
            timeout=HELPER_TIMEOUT_SECONDS,
            inherit_environment=True,
        )
    except Exception as exc:
        _PLUGIN_API.logger.warning("二维码常驻运行时请求失败，回退到单次 helper: %s", exc)

    helper = Path(__file__).resolve().parent / "qr_runner.py"
    helper_cmd = _find_helper_command(helper)
    if not helper_cmd:
        return {"status": "error", "message": "未找到可运行截图二维码识别的运行环境"}

    try:
        completed = _PLUGIN_API.run_process_capture(
            [*helper_cmd, *helper_args],
            cwd=str(helper.parent),
            timeout=HELPER_TIMEOUT_SECONDS,
            inherit_environment=True,
            helper_output_file=True,
        )
    except TimeoutError:
        return {"status": "error", "message": "二维码识别任务超时"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    if completed.get("timed_out"):
        return {"status": "error", "message": "二维码识别任务超时"}

    parsed = _parse_helper_stdout(str(completed.get("stdout") or ""))
    if parsed:
        return parsed
    stderr = str(completed.get("stderr") or "").strip()
    stdout = str(completed.get("stdout") or "").strip()
    message = stderr or stdout or f"二维码识别 Helper 退出码: {completed.get('returncode')}"
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
    primary_text = str(payload.get("text") or "")

    if status == "cancelled":
        return CommandResult(
            success=True,
            message=message or "已取消二维码截图",
            payload={"_suppress_result_panel": True, "outputs": {"text": "", "url": ""}},
        )
    if status == "no_qr":
        return CommandResult(
            success=True,
            message=message or "未识别到二维码。",
            display_type="text",
            payload={"outputs": {"text": "", "url": ""}},
        )
    if status != "ok":
        return CommandResult(
            success=False,
            message=message or "二维码识别失败",
            error="识别失败",
            payload={"outputs": {"text": "", "url": ""}},
        )

    url = _normalize_url(primary_text)
    actions = [CommandAction(type="copy", label="复制内容", value=primary_text, primary=not bool(url))]
    if url:
        actions.insert(0, CommandAction(type="open_url", label="打开链接", value=url, primary=True))

    return CommandResult(
        success=True,
        message=primary_text or "已识别二维码。",
        display_type="text",
        payload={"outputs": {"text": primary_text, "url": url}},
        actions=actions,
    )


def _normalize_url(text: str) -> str:
    value = (text or "").strip()
    if not value or any(ch.isspace() for ch in value):
        return ""
    if _SCHEME_RE.match(value):
        return value if value.lower().startswith(("http://", "https://")) else ""
    if value.lower().startswith("www.") or _DOMAIN_RE.match(value):
        return f"https://{value}"
    return ""


def _find_helper_command(helper: Path) -> list[str]:
    global _CACHED_HELPER_CMD
    if _CACHED_HELPER_CMD is not None:
        return _CACHED_HELPER_CMD

    current = Path(sys.executable or "")
    site_packages = Path(__file__).resolve().parent / "runtime" / "site-packages"

    host_helper = _host_helper_command(current, helper, site_packages)
    if host_helper:
        _CACHED_HELPER_CMD = host_helper
        return _CACHED_HELPER_CMD

    if (
        current.exists()
        and current.name.lower().startswith("python")
        and _python_has_qr_runtime([str(current)], site_packages)
    ):
        _inject_site_to_env(site_packages)
        _CACHED_HELPER_CMD = [str(current), str(helper)]
        return _CACHED_HELPER_CMD

    system_python = _find_system_python_command(site_packages)
    if system_python:
        _inject_site_to_env(site_packages)
        _CACHED_HELPER_CMD = [*system_python, str(helper)]
        return _CACHED_HELPER_CMD
    return []


def _host_helper_command(current: Path, helper: Path, site_packages: Path) -> list[str]:
    candidates: list[Path] = []
    if current.exists() and not current.name.lower().startswith("python"):
        candidates.append(current)
    if current.parent:
        candidates.append(current.parent / "QuickLauncher.exe")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if not candidate.is_file():
            continue
        cmd = [str(candidate), "--plugin-helper", str(helper)]
        if site_packages.is_dir():
            cmd.extend(["--plugin-site", str(site_packages)])
        cmd.append("--")
        return cmd
    return []


def _inject_site_to_env(site_packages: Path) -> None:
    if not site_packages.is_dir():
        return
    site_str = str(site_packages)
    parts = [p for p in (os.environ.get("PYTHONPATH", "") or "").split(os.pathsep) if p]
    if site_str not in parts:
        parts.insert(0, site_str)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    os.environ["PATH"] = site_str + os.pathsep + os.environ.get("PATH", "")


def _find_system_python_command(site_packages: Path) -> list[str]:
    candidates: list[list[str]] = []
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
        if _python_has_qr_runtime(candidate, site_packages):
            return candidate
    return []


def _python_has_qr_runtime(command: list[str], site_packages: Path) -> bool:
    if _PLUGIN_API is None:
        return False
    app_root = ""
    try:
        app_root = str(Path(command[0]).resolve().parent) if command else ""
    except OSError:
        app_root = ""
    code = (
        "import os, sys\n"
        f"site = {str(site_packages)!r}\n"
        f"app_root = {app_root!r}\n"
        "for p in (site, app_root):\n"
        "    if p and os.path.isdir(p) and p not in sys.path:\n"
        "        sys.path.insert(0, p)\n"
        "for p in (site, app_root, os.path.join(app_root, 'PyQt5')):\n"
        "    if p and os.path.isdir(p):\n"
        "        os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')\n"
        "        add = getattr(os, 'add_dll_directory', None)\n"
        "        if add:\n"
        "            try:\n"
        "                add(p)\n"
        "            except OSError:\n"
        "                pass\n"
        "from PyQt5.QtCore import QPoint\n"
        "from PIL import Image\n"
        "import zxingcpp\n"
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
