"""Built-in encoding and hashing (urlencode, color, hash, uuid, timestamp, base64) commands.

Auto-extracted from :mod:`core.commands` in 1.6.3.2 to keep the file size
manageable. Public API stays on :mod:`core.commands`; this module is
internal and may be imported directly by tests.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import urllib.parse
import uuid
from datetime import UTC, datetime

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def cmd_urlencode(context: CommandContext) -> CommandResult:
    raw_text = (context.args_text or "").strip()
    clipboard = (context.clipboard_text or "").strip()

    is_decode = False
    target = ""

    first_word = raw_text.split(None, 1)[0].lower() if raw_text.split(None, 1) else ""
    if first_word in ("decode", "d", "解码"):
        is_decode = True
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    elif first_word in ("encode", "e", "编码"):
        is_decode = False
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    else:
        mode_arg = context.args.get("mode", "").lower() if context.args else ""
        if mode_arg in ("decode", "d", "解码"):
            is_decode = True
        target = raw_text

    if not target:
        target = clipboard

    if not target:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")

    if is_decode:
        try:
            decoded = urllib.parse.unquote(target)
            return CommandResult(
                success=True,
                message=decoded,
                actions=[CommandAction(type="copy", label="复制结果", value=decoded)],
            )
        except Exception:
            logger.debug("URL解码失败", exc_info=True)
            return CommandResult(success=False, message="URL 解码失败", error="解码失败")
    else:
        encoded = urllib.parse.quote(target, safe="")
        return CommandResult(
            success=True,
            message=encoded,
            actions=[CommandAction(type="copy", label="复制结果", value=encoded)],
        )


# ---------------------------------------------------------------------------
# ── /color ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int, int | None] | None:
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 4:
        h = "".join(c * 2 for c in h)

    if len(h) == 6:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), None)
        except ValueError:
            return None
    elif len(h) == 8:
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        except ValueError:
            return None
    return None


def cmd_color(context: CommandContext) -> CommandResult:
    text = (context.args_text or context.clipboard_text or "").strip()
    if not text:
        return CommandResult(success=False, message="请输入 HEX 颜色代码（如 #ff8800）", error="缺少输入")
    rgba = _hex_to_rgb(text)
    if rgba is None:
        return CommandResult(success=False, message=f"无法识别颜色: {text}", error="格式错误")
    r, g, b, a = rgba
    if a is None:
        hex_upper = f"#{r:02X}{g:02X}{b:02X}"
        hex_lower = f"#{r:02x}{g:02x}{b:02x}"
        msg = f"HEX: {hex_upper}\nRGB: rgb({r}, {g}, {b})"
        actions = [
            CommandAction(type="copy", label="复制 HEX", value=hex_lower),
            CommandAction(type="copy", label="复制 RGB", value=f"rgb({r},{g},{b})"),
        ]
    else:
        hex_upper = f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        hex_lower = f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        msg = f"HEX: {hex_upper}\nRGBA: rgba({r}, {g}, {b}, {a / 255:.2f})"
        actions = [
            CommandAction(type="copy", label="复制 HEX", value=hex_lower),
            CommandAction(type="copy", label="复制 RGBA", value=f"rgba({r},{g},{b},{a / 255:.2f})"),
        ]
    return CommandResult(
        success=True,
        message=msg,
        payload={"r": r, "g": g, "b": b, "a": a},
        actions=actions,
    )


# ---------------------------------------------------------------------------
# ── /ip ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _hash_file(filepath: str, algo: str) -> str:
    h = hashlib.new(algo)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def cmd_hash(context: CommandContext) -> CommandResult:
    structured_args = dict(context.args or {})
    args = context.args_text.strip()
    algo = str(structured_args.get("algorithm") or ("sha256" if structured_args else "md5")).lower()
    file_path = str(structured_args.get("file") or "").strip() or None

    if args:
        first_word = args.split(None, 1)[0].lower() if args.split(None, 1) else ""
        if first_word in ("md5", "sha1", "sha256", "sha512"):
            algo = first_word
            file_path = args[len(first_word) :].strip()
        else:
            last_word = args.rsplit(None, 1)[-1].lower() if args.rsplit(None, 1) else ""
            if last_word in ("md5", "sha1", "sha256", "sha512"):
                algo = last_word
                file_path = args[: -len(last_word)].strip()
            else:
                file_path = args

    if file_path:
        file_path = file_path.strip("'\"")

    if not file_path and context.selected_files:
        file_path = context.selected_files[0]

    if not file_path:
        return CommandResult(success=False, message="请指定文件路径或选中文件", error="缺少输入")
    if not os.path.isfile(file_path):
        return CommandResult(success=False, message=f"文件不存在: {file_path}", error="文件未找到")
    try:
        digest = _hash_file(file_path, algo)
        return CommandResult(
            success=True,
            message=f"{algo.upper()}: {digest}",
            payload={"outputs": {"file": file_path, "algorithm": algo, "hash": digest}, "files": [file_path]},
            actions=[CommandAction(type="copy", label="复制哈希", value=digest)],
        )
    except (OSError, PermissionError) as e:
        return CommandResult(success=False, message=f"无法读取文件: {e}", error="读取失败")


# ---------------------------------------------------------------------------
# ── Phase 2 commands (previous) ────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_uuid(context: CommandContext) -> CommandResult:
    uid = str(uuid.uuid4())
    return CommandResult(
        success=True,
        message=uid,
        display_type="text",
        actions=[CommandAction(type="copy", label="复制", value=uid)],
    )


def cmd_timestamp(context: CommandContext) -> CommandResult:
    args = context.args_text.strip()
    if not args:
        now = datetime.now(UTC)
        local = now.astimezone()
        return CommandResult(
            success=True,
            message=f"{local.strftime('%Y-%m-%d %H:%M:%S')}\n{int(now.timestamp())}",
            display_type="text",
            actions=[CommandAction(type="copy", label="复制时间戳", value=str(int(now.timestamp())))],
        )
    try:
        ts = int(args)
        if ts > 1e12:
            ts /= 1000  # type: ignore[assignment]
        dt = datetime.fromtimestamp(ts, tz=UTC).astimezone()
        return CommandResult(
            success=True,
            message=dt.strftime("%Y-%m-%d %H:%M:%S"),
            display_type="text",
            actions=[CommandAction(type="copy", label="复制日期", value=dt.strftime("%Y-%m-%d %H:%M:%S"))],
        )
    except (ValueError, OSError, OverflowError):
        return CommandResult(
            success=False,
            message="无效的时间戳",
            error="请输入秒级或毫秒级 Unix 时间戳",
        )


def cmd_base64(context: CommandContext) -> CommandResult:
    raw_text = (context.args_text or "").strip()
    clipboard = (context.clipboard_text or "").strip()

    is_decode = False
    target = ""

    first_word = raw_text.split(None, 1)[0].lower() if raw_text.split(None, 1) else ""
    if first_word in ("decode", "d", "解码"):
        is_decode = True
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    elif first_word in ("encode", "e", "编码"):
        is_decode = False
        parts = raw_text.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
    else:
        mode_arg = context.args.get("mode", "").lower() if context.args else ""
        if mode_arg in ("decode", "d", "解码"):
            is_decode = True
        target = raw_text

    if not target:
        target = clipboard

    if not target:
        return CommandResult(
            success=False,
            message="请输入文本或确保剪贴板有内容",
            error="缺少输入",
        )

    if len(target.encode("utf-8")) > 256 * 1024:
        return CommandResult(
            success=False,
            message="输入文本超过 256KB 限制",
            error="输入过大",
        )

    if is_decode:
        try:
            missing_padding = len(target) % 4
            padded_target = target
            if missing_padding:
                padded_target += "=" * (4 - missing_padding)
            decoded = base64.b64decode(padded_target.encode("utf-8")).decode("utf-8")
            return CommandResult(
                success=True,
                message=decoded,
                display_type="text",
                actions=[CommandAction(type="copy", label="复制结果", value=decoded)],
            )
        except Exception:
            logger.debug("Base64解码失败", exc_info=True)
            return CommandResult(
                success=False,
                message="Base64 解码失败，请检查输入是否为合法的 Base64 编码",
                error="解码失败",
            )
    else:
        encoded = base64.b64encode(target.encode("utf-8")).decode("utf-8")
        return CommandResult(
            success=True,
            message=encoded,
            display_type="text",
            actions=[CommandAction(type="copy", label="复制结果", value=encoded)],
        )
