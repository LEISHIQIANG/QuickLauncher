"""Built-in text/JSON/JWT inspection (json, jwt, path-audit) commands.

Auto-extracted from :mod:`core.commands` in 1.6.3.2 to keep the file size
manageable. Public API stays on :mod:`core.commands`; this module is
internal and may be imported directly by tests.
"""

from __future__ import annotations

import base64
import json
import logging
import os

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def _text_from_args_or_clipboard(context: CommandContext, args_text: str | None = None) -> str:
    text = (context.args_text if args_text is None else args_text).strip()
    return text or (context.clipboard_text or "").strip()


def cmd_json(context: CommandContext) -> CommandResult:
    structured_args = dict(context.args or {})
    raw = str(structured_args.get("text") or "").strip() or context.args_text.strip()
    mode = str(structured_args.get("mode") or "format").lower()
    if raw:
        first, _, rest = raw.partition(" ")
        first_lower = first.lower()
        if first_lower in ("pretty", "format", "fmt", "min", "minify", "compact", "validate"):
            mode = first_lower
            raw = rest.strip()

    target = _text_from_args_or_clipboard(context, raw)
    if not target:
        return CommandResult(success=False, message="请输入 JSON 文本或确保剪贴板有 JSON 内容", error="缺少输入")

    try:
        parsed = json.loads(target)
    except json.JSONDecodeError as e:
        return CommandResult(
            success=False,
            message=f"JSON 无效: 第 {e.lineno} 行第 {e.colno} 列，{e.msg}",
            error="JSON 解析失败",
        )

    if mode == "validate":
        if isinstance(parsed, dict):
            summary = f"对象，{len(parsed)} 个键"
        elif isinstance(parsed, list):
            summary = f"数组，{len(parsed)} 项"
        else:
            summary = type(parsed).__name__
        formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
        compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return CommandResult(
            success=True,
            message=f"JSON 有效: {summary}",
            display_type="json",
            payload={
                "data": parsed,
                "formatted": formatted,
                "compact": compact,
                "outputs": {"json": formatted, "json.compact": compact},
            },
        )

    if mode in ("min", "minify", "compact"):
        result = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    else:
        result = json.dumps(parsed, ensure_ascii=False, indent=2)
    compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    formatted = json.dumps(parsed, ensure_ascii=False, indent=2)

    return CommandResult(
        success=True,
        message=result,
        display_type="json",
        payload={
            "data": parsed,
            "formatted": formatted,
            "compact": compact,
            "outputs": {"json": formatted, "json.compact": compact},
        },
        actions=[CommandAction(type="copy", label="复制 JSON", value=result)],
    )


def _decode_base64url_json(part: str) -> dict:
    padded = part + "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("JWT 片段不是 JSON 对象")
    return value


def cmd_jwt(context: CommandContext) -> CommandResult:
    token = str((context.args or {}).get("token") or "").strip() or _text_from_args_or_clipboard(context)
    if not token:
        return CommandResult(success=False, message="请输入 JWT 或确保剪贴板有 JWT", error="缺少输入")

    parts = token.strip().split(".")
    if len(parts) < 2:
        return CommandResult(success=False, message="JWT 至少需要 header.payload 两段", error="格式错误")

    try:
        header = _decode_base64url_json(parts[0])
        payload = _decode_base64url_json(parts[1])
    except Exception as e:
        logger.debug("JWT解码失败", exc_info=True)
        return CommandResult(success=False, message=f"JWT 解码失败: {e}", error="解码失败")

    header_text = json.dumps(header, ensure_ascii=False, indent=2)
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    signature_state = "有签名段，未验证签名" if len(parts) >= 3 and parts[2] else "无签名段"
    message = f"Header:\n{header_text}\n\nPayload:\n{payload_text}\n\n提示: {signature_state}"
    return CommandResult(
        success=True,
        message=message,
        display_type="json",
        payload={
            "header": header,
            "payload": payload,
            "data": {"header": header, "payload": payload},
            "formatted": message,
            "outputs": {"jwt.header": header_text, "jwt.payload": payload_text},
        },
        actions=[
            CommandAction(type="copy", label="复制 Payload", value=payload_text),
            CommandAction(type="copy", label="复制完整解码", value=message),
        ],
    )


def cmd_path_audit(context: CommandContext) -> CommandResult:
    raw_path = (context.args_text or "").strip() or os.environ.get("PATH", "")
    if not raw_path:
        return CommandResult(success=False, message="未检测到 PATH 内容", error="缺少输入")

    parts = [os.path.expandvars(p.strip().strip('"')) for p in raw_path.split(os.pathsep)]
    seen: dict[str, int] = {}
    missing: list[str] = []
    duplicates: list[str] = []
    valid_dirs: list[str] = []

    for part in parts:
        if not part:
            continue
        key = os.path.normcase(os.path.abspath(part))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            duplicates.append(part)
        if os.path.isdir(part):
            valid_dirs.append(part)
        else:
            missing.append(part)

    executable_names: dict[str, list[str]] = {}
    suffixes = [".exe", ".cmd", ".bat", ".ps1"] if os.name == "nt" else [""]
    for directory in valid_dirs[:80]:
        try:
            for name in os.listdir(directory):
                full = os.path.join(directory, name)
                if not os.path.isfile(full):
                    continue
                stem, ext = os.path.splitext(name)
                if os.name == "nt" and ext.lower() not in suffixes:
                    continue
                command_name = stem.lower() if os.name == "nt" else name.lower()
                executable_names.setdefault(command_name, []).append(full)
        except Exception:
            logger.debug("扫描目录中的可执行文件失败", exc_info=True)
            continue

    shadowed = {
        name: paths
        for name, paths in executable_names.items()
        if len(paths) > 1 and name in {"python", "pip", "node", "npm", "git", "java", "code"}
    }

    lines = [
        "PATH 体检",
        f"条目总数: {len([p for p in parts if p])}",
        f"有效目录: {len(valid_dirs)}",
        f"失效目录: {len(missing)}",
        f"重复目录: {len(duplicates)}",
    ]
    if missing:
        lines.append("")
        lines.append("失效目录:")
        lines.extend(f"- {p}" for p in missing[:10])
        if len(missing) > 10:
            lines.append(f"- ... 另有 {len(missing) - 10} 项")
    if duplicates:
        lines.append("")
        lines.append("重复目录:")
        lines.extend(f"- {p}" for p in duplicates[:10])
        if len(duplicates) > 10:
            lines.append(f"- ... 另有 {len(duplicates) - 10} 项")
    if shadowed:
        lines.append("")
        lines.append("可能被前序 PATH 遮蔽的常用命令:")
        for name, paths in sorted(shadowed.items()):
            lines.append(f"- {name}:")
            lines.extend(f"  {path}" for path in paths[:4])

    if not missing and not duplicates and not shadowed:
        lines.append("")
        lines.append("未发现失效目录、重复目录或常用命令遮蔽。")

    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        payload={"missing": missing, "duplicates": duplicates, "shadowed": shadowed},
        actions=[CommandAction(type="copy", label="复制报告", value=message)],
    )


# ---------------------------------------------------------------------------
# ── Phase 3 Power-User Superpower Commands ─────────────────────────────────
# ---------------------------------------------------------------------------
