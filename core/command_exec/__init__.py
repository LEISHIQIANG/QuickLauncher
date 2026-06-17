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
from .capture import (
    build_bash_fallback_result,
    build_capture_builtin_result,
    build_capture_cancel_result,
    build_capture_error_result,
    build_capture_payload,
    build_capture_success_result,
    decode_bytes,
    decode_capture_output,
    truncate_output,
)
from .cleanup import cleanup_file_later, terminate_process_tree
from .launcher_mixin import CommandLauncherMixin
from .output import decode_command_output, truncate_command_output
from .preflight import (
    DESTRUCTIVE_CONFIRMATION_ATTR,
    consume_confirmation,
    destructive_confirmation_result,
    mark_confirmed,
    prepare_command_for_execution,
    requires_confirmation,
)
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
    "build_capture_builtin_result",
    "build_capture_cancel_result",
    "build_capture_error_result",
    "build_capture_payload",
    "build_capture_success_result",
    "chain_values",
    "cleanup_file_later",
    "command_panel_size",
    "command_param_defs",
    "command_param_values",
    "CommandExecutionAudit",
    "CommandLauncherMixin",
    "consume_confirmation",
    "decode_bytes",
    "decode_capture_output",
    "decode_command_output",
    "DESTRUCTIVE_CONFIRMATION_ATTR",
    "destructive_confirmation_result",
    "effective_command_type",
    "KNOWN_SHELL_EXECUTION_ENTRIES",
    "mark_confirmed",
    "merge_runtime_env",
    "prepare_command_for_execution",
    "requires_confirmation",
    "ShellExecutionEntryAudit",
    "SUPPORTED_COMMAND_TYPES",
    "build_command_execution_audit",
    "is_supported_command_type",
    "known_shell_execution_entries",
    "normalize_command_type",
    "terminate_process_tree",
    "truncate_command_output",
    "truncate_output",
    "_write_atomic",
]
