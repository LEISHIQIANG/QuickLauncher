"""Command execution audit metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from core.command_risk import assess_command_risk
from core.data_models import ShortcutItem

from .runtime import normalize_command_type


@dataclass
class CommandExecutionAudit:
    command_type: str
    uses_shell: bool
    uses_shell_reason: str = ""
    run_as_admin: bool = False
    capture_output: bool = False
    show_window: bool = False
    timeout_seconds: float = 0.0
    requires_confirmation: bool = False
    risk_codes: list[str] = field(default_factory=list)
    risk_levels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "command_type": self.command_type,
            "uses_shell": self.uses_shell,
            "uses_shell_reason": self.uses_shell_reason,
            "run_as_admin": self.run_as_admin,
            "capture_output": self.capture_output,
            "show_window": self.show_window,
            "timeout_seconds": self.timeout_seconds,
            "requires_confirmation": self.requires_confirmation,
            "risk_codes": list(self.risk_codes),
            "risk_levels": list(self.risk_levels),
        }


@dataclass(frozen=True)
class ShellExecutionEntryAudit:
    """Static audit record for an intentional shell execution path."""

    identifier: str
    module: str
    owner: str
    python_shell_true: bool
    uses_system_shell: bool
    input_source: str
    reason: str
    mitigation: str

    def to_dict(self) -> dict:
        return asdict(self)


KNOWN_SHELL_EXECUTION_ENTRIES: tuple[ShellExecutionEntryAudit, ...] = (
    ShellExecutionEntryAudit(
        identifier="shortcut_command.user_cmd_shell",
        module="core.shortcut_command_exec",
        owner="ShortcutExecutor COMMAND/cmd fallback",
        python_shell_true=True,
        uses_system_shell=True,
        input_source="User-created COMMAND shortcut after preflight and variable preprocessing.",
        reason="Arbitrary CMD snippets, batch built-ins, redirection and shell operators require cmd.exe compatibility.",
        mitigation=(
            "Preflight rejects unsafe unquoted external variables; destructive command risk detection marks "
            "requires_confirmation before execution; captured commands prefer explicit cmd.exe argv wrappers."
        ),
    ),
    ShellExecutionEntryAudit(
        identifier="shortcut_file.association_start_fallback",
        module="core.shortcut_file_exec",
        owner="FileExecutionMixin non-exe association fallback",
        python_shell_true=True,
        uses_system_shell=True,
        input_source="Saved file shortcut target path plus dropped/selected file path.",
        reason="Windows start is the fallback when ShellExecute cannot open a non-exe association directly.",
        mitigation="ShellExecute is attempted first; arguments are quoted before fallback.",
    ),
    ShellExecutionEntryAudit(
        identifier="popup_drag_drop.association_start_fallback",
        module="ui.launcher_popup.popup_drag_drop",
        owner="Drag-and-drop non-exe association fallback",
        python_shell_true=True,
        uses_system_shell=True,
        input_source="User drop target shortcut plus file path supplied by the current drag operation.",
        reason="Windows start is the last-resort fallback for non-exe targets after privilege-aware launch fails.",
        mitigation="Privilege-aware ShellExecute path is attempted first; fallback is detached and does not capture output.",
    ),
    ShellExecutionEntryAudit(
        identifier="shortcut_command.windows_shell_execute_cmd",
        module="core.shortcut_command_exec",
        owner="ShellExecute cmd.exe launcher",
        python_shell_true=False,
        uses_system_shell=True,
        input_source="User-created COMMAND shortcut after preflight and variable preprocessing.",
        reason="Admin/non-admin launch routing uses ShellExecute with cmd.exe so Windows owns UAC and token boundaries.",
        mitigation="Command text is wrapped in cmd.exe /d /s /c or /k arguments; destructive risk detection runs beforehand.",
    ),
    ShellExecutionEntryAudit(
        identifier="shortcut_command.powershell_encoded_command",
        module="core.shortcut_command_exec",
        owner="PowerShell direct argv launcher",
        python_shell_true=False,
        uses_system_shell=True,
        input_source="User-created PowerShell COMMAND shortcut after preflight and variable preprocessing.",
        reason="PowerShell scripts require PowerShell parsing; -EncodedCommand carries the original script text by argv.",
        mitigation="No script file is written; command length is checked before launch; destructive risk detection runs first.",
    ),
    ShellExecutionEntryAudit(
        identifier="shortcut_command.git_bash_c",
        module="core.shortcut_command_exec",
        owner="Git Bash direct argv launcher",
        python_shell_true=False,
        uses_system_shell=True,
        input_source="User-created Git Bash COMMAND shortcut after preflight and variable preprocessing.",
        reason="Bash snippets, multiline commands, pipes and expansions require bash -c compatibility.",
        mitigation="No temp script/output/marker files are written; command length is checked before launch.",
    ),
)


def known_shell_execution_entries() -> list[dict]:
    """Return the reviewed shell execution paths for diagnostics and release review."""
    return [entry.to_dict() for entry in KNOWN_SHELL_EXECUTION_ENTRIES]


def build_command_execution_audit(
    shortcut: ShortcutItem,
    command: str | None = None,
    command_type: str | None = None,
) -> CommandExecutionAudit:
    effective_type = normalize_command_type(
        command_type if command_type is not None else getattr(shortcut, "command_type", "cmd") or "cmd"
    )
    uses_shell = effective_type in ("cmd", "powershell", "bash")
    shell_reasons = {
        "cmd": "cmd commands use the system shell for compatibility",
        "powershell": "PowerShell commands execute through powershell.exe",
        "bash": "Git Bash commands execute through bash.exe -c",
    }
    risks = assess_command_risk(shortcut, command=command, command_type=effective_type)
    return CommandExecutionAudit(
        command_type=effective_type,
        uses_shell=uses_shell,
        uses_shell_reason=shell_reasons.get(effective_type, "") if uses_shell else "",
        run_as_admin=bool(getattr(shortcut, "run_as_admin", False)),
        capture_output=bool(getattr(shortcut, "capture_output", False)),
        show_window=bool(getattr(shortcut, "show_window", False)),
        timeout_seconds=float(getattr(shortcut, "command_timeout_seconds", 0) or 0),
        requires_confirmation=any(risk.requires_confirmation for risk in risks),
        risk_codes=[risk.code for risk in risks],
        risk_levels=[risk.level for risk in risks],
    )
