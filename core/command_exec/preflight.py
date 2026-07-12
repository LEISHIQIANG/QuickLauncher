"""Pre-execution checks and destructive-command confirmation gates.

The functions in this module are extracted from the legacy
``core.shortcut_command_exec.CommandExecutionMixin`` to keep the public
method surface (used by tests, the command panel and the popup) while
moving the implementation details out of the god-class.

The module focuses on three responsibilities:

1. :func:`prepare_command_for_execution` — variable-resolution and
   ``:q`` quoting validation before a command is dispatched.
2. :func:`preflight_command` — full preflight that returns a
   :class:`CommandResult` for the first failure, or ``None`` when the
   command is safe to run.
3. :func:`destructive_confirmation_result` — UI-facing gate that asks
   the user to confirm a command before the executor is invoked.

The :class:`CommandExecutionMixin` keeps its method names and simply
delegates to the functions below.
"""

from __future__ import annotations

import logging

from core.command_exec.profiles import command_panel_size
from core.command_registry import CommandResult
from core.command_risk import assess_command_risk
from core.command_variables import (
    CommandVariableError,
    find_unquoted_external_command_variables,
    is_value_only_variable_command,
    should_expand_command_variables,
)
from core.data_models import ShortcutItem

logger = logging.getLogger(__name__)

DESTRUCTIVE_CONFIRMATION_ATTR = "_destructive_command_confirmed"


# ── destructive confirmation helpers ─────────────────────────────


def requires_confirmation(
    shortcut: ShortcutItem,
    command: str | None = None,
    command_type: str | None = None,
) -> list[dict]:
    """Return the destructive risks that must be confirmed before execution."""
    from core.command_exec.runtime import normalize_command_type

    effective_type = normalize_command_type(
        command_type if command_type is not None else getattr(shortcut, "command_type", "cmd")
    )
    return [
        risk.to_dict()
        for risk in assess_command_risk(shortcut, command=command, command_type=effective_type)
        if risk.requires_confirmation
    ]


def mark_confirmed(shortcut: ShortcutItem, confirmed: bool = True) -> None:
    """Mark a shortcut object as confirmed for its next destructive execution."""
    try:
        setattr(shortcut, DESTRUCTIVE_CONFIRMATION_ATTR, bool(confirmed))
    except Exception as exc:  # noqa: BLE001
        logger.debug("设置确认属性失败: %s", exc, exc_info=True)


def consume_confirmation(shortcut: ShortcutItem) -> bool:
    """Consume the destructive-confirmation flag (one-shot)."""
    try:
        if bool(getattr(shortcut, DESTRUCTIVE_CONFIRMATION_ATTR, False)):
            setattr(shortcut, DESTRUCTIVE_CONFIRMATION_ATTR, False)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("消费确认属性失败: %s", exc, exc_info=True)
    return False


def destructive_confirmation_result(
    shortcut: ShortcutItem,
    command: str,
    command_type: str,
    *,
    panel_size: str | None = None,
) -> CommandResult | None:
    """Build the confirmation-required result, or ``None`` if already confirmed."""
    risks = requires_confirmation(shortcut, command=command, command_type=command_type)
    if not risks:
        return None
    if consume_confirmation(shortcut):
        return None
    risk_lines = [f"- {risk.get('message') or risk.get('code')}" for risk in risks]
    detail = "\n".join(risk_lines)
    return CommandResult(
        success=False,
        message="该命令包含不可逆或强破坏性操作，请确认后执行。",
        display_type="confirm",
        error="需要确认",
        payload={
            "window_size": panel_size or command_panel_size(shortcut),
            "requires_confirmation": True,
            "risks": risks,
            "detail": detail,
            "command_type": command_type,
            "command": command,
            "shortcut": shortcut,
        },
    )


# ── command preparation / variable resolution ─────────────────────


def prepare_command_for_execution(
    shortcut: ShortcutItem,
    command: str,
    command_type: str,
    *,
    panel_size: str | None = None,
    display_type: str = "text",
) -> tuple[str, CommandResult | None]:
    """Resolve variables and validate quoting.  Returns ``(command, error)``."""
    payload = {"window_size": panel_size} if panel_size else {}

    def _invalid(message: str, error: str | None = None) -> tuple[str, CommandResult]:
        return command, CommandResult(
            success=False,
            message=message,
            display_type=display_type,
            error=error if error is not None else message,
            payload=dict(payload),
        )

    raw_mode = bool(getattr(shortcut, "raw_mode", False))
    # The original ``_should_expand_command_variables`` understands the
    # ``raw_mode`` override and treats param-defined variables as
    # implicit-expansion triggers.  We delegate to it to keep behaviour
    # identical to the legacy class method.
    try:
        from core.shortcut_command_exec import CommandExecutionMixin

        expand_variables = CommandExecutionMixin._should_expand_command_variables(shortcut)
    except Exception:  # noqa: BLE001 - fall back to the explicit check
        enabled = getattr(shortcut, "command_variables_enabled", None)
        expand_variables = should_expand_command_variables(command_type, enabled)
    if command_type in ("cmd", "powershell", "bash") and not raw_mode and is_value_only_variable_command(command):
        if expand_variables:
            return _invalid(
                f"命令只包含值占位符，不能直接执行。请改为可执行命令，例如: echo {command}",
                "命令无效",
            )
        return _invalid(
            f"命令只包含变量占位符，但未启用解析变量。请启用解析变量，或改为可执行命令，例如: echo {command}",
            "命令无效",
        )
    if command_type in ("cmd", "powershell", "bash") and expand_variables:
        unsafe_variables = find_unquoted_external_command_variables(command)
        if unsafe_variables:
            examples = ", ".join("{{" + name + ":q}}" for name in unsafe_variables[:3])
            message = f"外部输入变量用于 CMD/PowerShell/Bash 命令时必须使用 :q 引用，例如: {examples}"
            return _invalid(message)
    if expand_variables:
        # Variable resolution depends on the broader shortcut state
        # (runtime inputs, …) and is still owned by the legacy mixin
        # to avoid duplicating that logic here.  Callers can opt into
        # the new module for the validation pieces.
        try:
            from core.shortcut_command_exec import CommandExecutionMixin

            command = CommandExecutionMixin._resolve_command_variables(shortcut, command)
        except CommandVariableError as e:
            return _invalid(str(e), "变量解析失败")
    return command, None


__all__ = [
    "DESTRUCTIVE_CONFIRMATION_ATTR",
    "consume_confirmation",
    "destructive_confirmation_result",
    "mark_confirmed",
    "prepare_command_for_execution",
    "requires_confirmation",
]
