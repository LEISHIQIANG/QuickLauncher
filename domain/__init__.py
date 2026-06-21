"""Pure domain entities and value objects.

Key exports:
- ``ShortcutType`` — Shortcut type enum
- ``ShortcutItem`` — Pure domain model for shortcut items
- ``Folder`` — Pure domain model for folders
- ``AppSettings`` — Pure domain model for app settings
- ``AppData`` — Pure domain model for app data root
- ``DEFAULT_SPECIAL_APPS`` — Default special apps list
- ``normalize_command_timeout_seconds`` — Timeout normalizer
- ``normalize_command_output_max_chars`` — Output max chars normalizer
- ``normalize_chain_step_delay_ms`` — Chain step delay normalizer
- ``normalize_trigger_settings`` — Trigger settings normalizer

Currently consumed by ``core.data_models`` as the target-architecture foundation.
Import rule: ``domain`` must not depend on Qt, Win32, file system, network, subprocess, ``ui``, or any concrete repository.
"""

from domain.models import (
    ACTION_CHAIN_MODULE_ID,
    ACTION_CHAIN_MODULE_VERSION,
    ACTION_CHAIN_SCHEMA_VERSION,
    BATCH_LAUNCH_MODULE_ID,
    BATCH_LAUNCH_MODULE_VERSION,
    DEFAULT_SPECIAL_APPS,
    AppData,
    AppSettings,
    Folder,
    ShortcutItem,
    ShortcutType,
    normalize_chain_step_delay_ms,
    normalize_command_output_max_chars,
    normalize_command_timeout_seconds,
    normalize_trigger_settings,
)

__all__ = [
    "ShortcutType",
    "ShortcutItem",
    "Folder",
    "AppSettings",
    "AppData",
    "DEFAULT_SPECIAL_APPS",
    "normalize_command_timeout_seconds",
    "normalize_command_output_max_chars",
    "normalize_chain_step_delay_ms",
    "normalize_trigger_settings",
    "ACTION_CHAIN_MODULE_ID",
    "ACTION_CHAIN_MODULE_VERSION",
    "ACTION_CHAIN_SCHEMA_VERSION",
    "BATCH_LAUNCH_MODULE_ID",
    "BATCH_LAUNCH_MODULE_VERSION",
]
