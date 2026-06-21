"""Windows utility built-in command handlers."""

from __future__ import annotations

from infrastructure.process import runtime as process_runtime

from .command_registry import CommandContext, CommandResult


def cmd_env(context: CommandContext) -> CommandResult:
    try:
        process_runtime.popen(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
        return CommandResult(
            success=True,
            message="已成功启动 Windows 系统环境变量编辑器。",
            payload={"_suppress_result_panel": True},
        )
    except Exception as e:
        return CommandResult(success=False, message=f"启动环境变量编辑器失败: {e}", error="启动失败")


def cmd_god(context: CommandContext) -> CommandResult:
    god_mode_guid = "shell:::{ED7BA470-8E54-465E-825C-99712043E01C}"
    try:
        process_runtime.startfile(god_mode_guid)
        return CommandResult(
            success=True,
            message="已成功打开 Windows 上帝模式 (God Mode) 文件夹。",
            payload={"_suppress_result_panel": True},
        )
    except Exception:
        try:
            process_runtime.popen(["explorer.exe", god_mode_guid])
            return CommandResult(
                success=True,
                message="已成功打开 Windows 上帝模式 (God Mode) 文件夹。",
                payload={"_suppress_result_panel": True},
            )
        except Exception as e:
            return CommandResult(success=False, message=f"打开上帝模式失败: {e}", error="打开失败")
