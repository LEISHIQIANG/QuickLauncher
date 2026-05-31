"""Git built-in command handler."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)

_ALLOWED_SUBCOMMANDS = {"status", "branch", "log", "diff", "fetch", "pull", "checkout"}


def _large_log_payload(**values) -> dict:
    return {**values, "window_size": "large"}


def _run_git(repo: str, extra: list[str], timeout: float = 20.0) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        ["git", *extra],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        finally:
            try:
                proc.communicate(timeout=2.0)
            except Exception:
                logger.debug("终止进程后读取输出失败", exc_info=True)
        raise
    return proc.returncode, stdout or "", stderr or "", time.perf_counter() - started


def cmd_git(context: CommandContext) -> CommandResult:
    args = shlex.split(context.args_text or "", posix=False)
    subcommand = (args[0].lower() if args else "status").strip()
    if subcommand not in _ALLOWED_SUBCOMMANDS:
        return CommandResult(
            success=False,
            message="用法: /git status|branch|log|diff|fetch|pull|checkout [参数]",
            display_type="log",
            error="未知 Git 子命令",
            payload=_large_log_payload(),
        )

    rest = args[1:]
    cwd = os.getcwd()
    branch = ""
    if subcommand == "checkout":
        if not rest:
            return CommandResult(
                success=False,
                message="用法: /git checkout <branch> [repo]",
                display_type="log",
                error="缺少分支名",
                payload=_large_log_payload(),
            )
        branch = rest[0]
        repo = rest[1] if len(rest) > 1 else ""
    else:
        repo = rest[0] if rest else ""
    repo = os.path.abspath(repo or cwd)
    if not os.path.isdir(repo):
        return CommandResult(
            success=False,
            message=f"Git 工作目录不存在: {repo}",
            display_type="log",
            error="目录不存在",
            payload=_large_log_payload(repo=repo, subcommand=subcommand),
        )

    try:
        code, stdout, stderr, duration = _run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=5.0)
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"无法运行 git: {e}",
            display_type="log",
            error=str(e),
            payload=_large_log_payload(repo=repo, subcommand=subcommand),
        )
    if code != 0 or stdout.strip().lower() != "true":
        return CommandResult(
            success=False,
            message=f"不是 Git 仓库: {repo}\n{stderr.strip()}",
            display_type="log",
            error="不是 Git 仓库",
            payload=_large_log_payload(
                repo=repo,
                subcommand=subcommand,
                exit_code=code,
                stderr=stderr,
            ),
        )

    git_args = {
        "status": ["status", "--short", "--branch"],
        "branch": ["branch", "--all", "--verbose", "--no-abbrev"],
        "log": ["log", "--oneline", "--decorate", "-n", "30"],
        "diff": ["diff", "--stat"],
        "fetch": ["fetch", "--all", "--prune"],
        "pull": ["pull", "--ff-only"],
        "checkout": ["checkout", branch],
    }[subcommand]

    try:
        code, stdout, stderr, duration = _run_git(repo, git_args, timeout=60.0)
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            message="Git 命令执行超时。",
            display_type="log",
            error="执行超时",
            payload=_large_log_payload(repo=repo, subcommand=subcommand, timed_out=True),
        )
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"Git 命令执行失败: {e}",
            display_type="log",
            error=str(e),
            payload=_large_log_payload(repo=repo, subcommand=subcommand),
        )

    payload = {
        "repo": repo,
        "subcommand": subcommand,
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
        "duration": duration,
        "window_size": "large",
        "wrap": False,
    }
    if subcommand == "status":
        rows = []
        for line in stdout.splitlines():
            if line.startswith("##"):
                rows.append(["branch", line[2:].strip(), ""])
            elif len(line) >= 3:
                rows.append([line[:2].strip() or "changed", line[3:], ""])
        return CommandResult(
            success=code == 0,
            message=stdout or stderr,
            display_type="table",
            payload={**payload, "columns": ["Status", "Path", "Detail"], "rows": rows},
            error="" if code == 0 else (stderr.strip() or f"exit {code}"),
        )
    if subcommand == "branch":
        rows = [[line[:2].strip(), line[2:].strip()] for line in stdout.splitlines() if line.strip()]
        return CommandResult(
            success=code == 0,
            message=stdout or stderr,
            display_type="table",
            payload={**payload, "columns": ["Current", "Branch"], "rows": rows},
            error="" if code == 0 else (stderr.strip() or f"exit {code}"),
        )
    message = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part) or "(无输出)"
    return CommandResult(
        success=code == 0,
        message=message,
        display_type="log",
        payload=payload,
        actions=[CommandAction(type="copy", label="复制输出", value=message)],
        error="" if code == 0 else (stderr.strip().splitlines()[0] if stderr.strip() else f"exit {code}"),
    )
