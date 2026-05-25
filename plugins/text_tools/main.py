"""Text Tools plugin — text processing commands for QuickLauncher."""

from __future__ import annotations

from core.command_registry import CommandAction, CommandResult


def register(api):
    api.register_command(
        id="text_tools.reverse",
        title="反转文本",
        aliases=["reverse", "反转"],
        description="反转输入文本",
        category="文本",
        handler=reverse_text,
    )
    api.register_command(
        id="text_tools.count",
        title="文本统计",
        aliases=["count", "统计", "字数"],
        description="统计行数、字数、字符数",
        category="文本",
        handler=count_text,
    )
    api.register_command(
        id="text_tools.case",
        title="大小写转换",
        aliases=["case", "大小写"],
        description="转换文本为大写或小写",
        category="文本",
        handler=case_text,
    )


def reverse_text(context):
    text = context.args_text or context.clipboard_text or ""
    if not text:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")
    result = text[::-1]
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label="复制结果", value=result)],
    )


def count_text(context):
    text = context.args_text or context.clipboard_text or ""
    if not text:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")
    lines = text.count("\n") + 1
    words = len(text.split())
    chars = len(text)
    msg = f"行数: {lines}\n字数: {words}\n字符数: {chars}"
    return CommandResult(
        success=True,
        message=msg,
        actions=[CommandAction(type="copy", label="复制统计", value=msg)],
    )


def case_text(context):
    raw_text = (context.args_text or "").strip()
    clipboard = (context.clipboard_text or "").strip()
    
    mode = "upper"
    remaining = ""
    
    first_word = raw_text.split(None, 1)[0].lower() if raw_text.split(None, 1) else ""
    if first_word in ("upper", "lower", "大写", "小写"):
        mode = first_word
        parts = raw_text.split(None, 1)
        remaining = parts[1].strip() if len(parts) > 1 else ""
    else:
        remaining = raw_text
        
    if not remaining:
        remaining = clipboard
        
    if not remaining:
        return CommandResult(success=False, message="请输入文本或确保剪贴板有内容", error="缺少输入")
        
    if mode in ("upper", "大写"):
        result = remaining.upper()
        label = "大写"
    elif mode in ("lower", "小写"):
        result = remaining.lower()
        label = "小写"
    else:
        result = remaining.upper()
        label = "大写"
        
    return CommandResult(
        success=True,
        message=result,
        actions=[CommandAction(type="copy", label=f"复制{label}", value=result)],
    )
