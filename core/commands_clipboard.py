"""Built-in clipboard and selection helpers (clip, copy_path, selected) commands.

Auto-extracted from :mod:`core.commands` in 1.6.3.2 to keep the file size
manageable. Public API stays on :mod:`core.commands`; this module is
internal and may be imported directly by tests.
"""

from __future__ import annotations

import logging
import os
import urllib.parse

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def cmd_copy_path(context: CommandContext) -> CommandResult:
    files = context.selected_files or []
    if not files:
        return CommandResult(success=False, message="未检测到资源管理器选中文件", error="缺少输入")
    mode = context.args.get("mode", "").lower() or context.args_text.strip().lower()
    if mode in ("name", "文件名"):
        parts = [os.path.basename(f) for f in files]
    elif mode in ("dir", "目录", "folder"):
        parts = [os.path.dirname(f) for f in files]
    else:
        parts = files
    result = "\n".join(parts)
    label = "复制路径" if not mode else {"name": "复制文件名", "dir": "复制目录"}.get(mode, "复制")
    try:
        from core.clipboard_service import clipboard_service

        if clipboard_service.write_text(result):
            return CommandResult(
                success=True,
                message=result,
                payload={"_suppress_result_panel": True},
                actions=[CommandAction(type="copy", label=label, value=result)],
            )
    except ImportError as exc:
        logger.debug("直接写入剪贴板失败: %s", exc, exc_info=True)
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label=label, value=result)],
    )


# ---------------------------------------------------------------------------
# ── /hash ──────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_selected(context: CommandContext) -> CommandResult:
    """Display selected text information."""
    selected = (context.selected_text or "").strip()
    method = (context.selected_text_method or "").strip()

    if not selected:
        # Try reading directly
        try:
            from .selected_text_service import selected_text_service

            result = selected_text_service.get_selected_text(allow_clipboard_fallback=True)
            if result.success and result.text:
                selected = result.text
                method = result.method
        except Exception as exc:
            logger.debug("读取选中文字失败: %s", exc, exc_info=True)

    if not selected:
        return CommandResult(
            success=False,
            message="未检测到选中文字",
            display_type="text",
            actions=[CommandAction(type="copy", label="复制选中文字", value=selected)],
            error="empty",
        )

    lines = [
        f"选中文字: {selected[:200]}",
        f"读取方式: {method or 'unknown'}",
    ]
    if len(selected) > 200:
        lines.append(f"(共 {len(selected)} 字，仅显示前 200 字)")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        display_type="text",
        actions=[
            CommandAction(type="copy", label="复制选中文字", value=selected),
            CommandAction(type="copy", label="复制选中文字(URL编码)", value=urllib.parse.quote(selected)),
        ],
    )


# ---------------------------------------------------------------------------
# ── /clip ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cmd_clip(context: CommandContext) -> CommandResult:
    """Display clipboard information and classification."""
    clipboard_text = (context.clipboard_text or "").strip()
    clipboard_kind = (context.clipboard_kind or "").strip()

    if not clipboard_text and not clipboard_kind:
        try:
            from .clipboard_classifiers import classify_clipboard
            from .clipboard_service import clipboard_service

            snapshot = clipboard_service.read_snapshot()
            if snapshot.text:
                clipboard_text = snapshot.text
            classification = classify_clipboard(snapshot)
            clipboard_kind = classification.kind
        except Exception as exc:
            logger.debug("读取剪贴板分类信息失败: %s", exc, exc_info=True)

    if not clipboard_text:
        return CommandResult(
            success=False,
            message="剪贴板为空",
            error="empty",
        )

    lines = [f"类型: {clipboard_kind or 'text'}"]

    if clipboard_kind == "file_list":
        try:
            files = context.clipboard_files or []
            if files:
                lines.append(f"文件: {len(files)} 个")
                for f in files[:5]:
                    lines.append(f"  {f}")
                if len(files) > 5:
                    lines.append(f"  ... 还有 {len(files) - 5} 个文件")
        except Exception:
            logger.debug("读取剪贴板文件列表失败", exc_info=True)
            lines.append(f"内容: {clipboard_text[:200]}")
    else:
        lines.append(f"内容: {clipboard_text[:200]}")

    if len(clipboard_text) > 200:
        lines.append(f"(共 {len(clipboard_text)} 字，仅显示前 200 字)")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        display_type="text",
        actions=[
            CommandAction(type="copy", label="复制内容", value=clipboard_text),
        ],
    )
