"""Internal command execution helpers.

The existing shortcut execution modules remain the public facade while this
package becomes the stable home for shared execution metadata and future
process helpers.
"""

from .audit import (
    KNOWN_SHELL_EXECUTION_ENTRIES,
    CommandExecutionAudit,
    ShellExecutionEntryAudit,
    build_command_execution_audit,
    known_shell_execution_entries,
)
from .launcher_mixin import CommandLauncherMixin
from .output import build_bash_fallback_result, decode_command_output, truncate_command_output
from .profiles import (
    chain_values,
    command_panel_size,
    command_param_defs,
    command_param_values,
    effective_command_type,
    merge_runtime_env,
)
from .runtime import SUPPORTED_COMMAND_TYPES, is_supported_command_type, normalize_command_type
from .standalone import _write_atomic

__all__ = [
    "build_bash_fallback_result",
    "chain_values",
    "command_panel_size",
    "command_param_defs",
    "command_param_values",
    "CommandExecutionAudit",
    "CommandLauncherMixin",
    "effective_command_type",
    "KNOWN_SHELL_EXECUTION_ENTRIES",
    "merge_runtime_env",
    "ShellExecutionEntryAudit",
    "SUPPORTED_COMMAND_TYPES",
    "build_command_execution_audit",
    "decode_command_output",
    "is_supported_command_type",
    "known_shell_execution_entries",
    "normalize_command_type",
    "truncate_command_output",
    "_write_atomic",
]
