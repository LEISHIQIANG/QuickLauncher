"""File helper commands for QuickLauncher."""

from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path

from core.command_registry import CommandAction, CommandResult

ALGORITHMS = {"md5", "sha1", "sha256"}
MAX_HASH_SIZE = 128 * 1024 * 1024


def register(api):
    api.register_command(
        id="file_tools.copy_path",
        title="复制文件路径",
        aliases=["copy-path", "copypath", "path", "复制路径"],
        description="复制资源管理器选中文件路径，支持 name/dir/full 模式",
        category="文件",
        handler=handle_copy_path,
    )
    api.register_command(
        id="file_tools.hash",
        title="文件哈希",
        aliases=["hash", "sha256", "md5"],
        description="计算指定文件或选中文件的 MD5/SHA1/SHA256",
        category="文件",
        handler=handle_hash,
    )


def _split_args(text: str) -> list[str]:
    try:
        return [p.strip("\"'") for p in shlex.split(text or "", posix=False)]
    except ValueError:
        return (text or "").split()


def _selected_or_args(context, args: list[str]) -> list[str]:
    if args:
        return args
    return list(context.selected_files or [])


def _copy_action(value: str, label: str = "复制结果") -> list[CommandAction]:
    return [CommandAction(type="copy", label=label, value=value)]


def handle_copy_path(context):
    args = _split_args(context.args_text)
    mode = "full"
    if args and args[0].lower() in {"full", "name", "dir", "folder", "完整", "文件名", "目录"}:
        mode = args.pop(0).lower()

    files = _selected_or_args(context, args)
    if not files:
        return CommandResult(
            success=False,
            message="未检测到选中文件。也可以输入: /copy-path C:\\path\\file.txt",
            error="缺少文件",
        )

    values: list[str] = []
    for item in files:
        path = Path(item)
        if mode in {"name", "文件名"}:
            values.append(path.name)
        elif mode in {"dir", "folder", "目录"}:
            values.append(str(path.parent))
        else:
            values.append(str(path))

    result = "\n".join(values)
    return CommandResult(
        success=True,
        message=result,
        actions=_copy_action(result, "复制路径"),
    )


def handle_hash(context):
    args = _split_args(context.args_text)
    algorithm = "sha256"
    if args and args[0].lower() in ALGORITHMS:
        algorithm = args.pop(0).lower()

    files = _selected_or_args(context, args)
    if not files:
        return CommandResult(
            success=False,
            message="用法: /hash [md5|sha1|sha256] <文件路径>，或先在资源管理器中选择文件",
            error="缺少文件",
        )

    lines: list[str] = []
    for raw_path in files[:10]:
        path = Path(raw_path)
        if not path.is_file():
            lines.append(f"{raw_path}: 文件不存在或不是普通文件")
            continue
        size = path.stat().st_size
        if size > MAX_HASH_SIZE:
            lines.append(f"{path.name}: 文件超过 128 MB，已跳过以避免插件超时")
            continue
        digest = _hash_file(path, algorithm)
        lines.append(f"{algorithm.upper()}  {digest}  {os.fspath(path)}")

    if len(files) > 10:
        lines.append(f"已省略 {len(files) - 10} 个文件")

    result = "\n".join(lines)
    success = any("  " in line for line in lines)
    return CommandResult(
        success=success,
        message=result,
        display_type="log",
        payload={
            "window_size": "large",
            "wrap": False,
            "algorithm": algorithm,
            "file_count": len(files),
        },
        actions=_copy_action(result, "复制哈希"),
    )


def _hash_file(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
