"""Command registry factory owned by the composition root."""

from __future__ import annotations

import logging

from core.builtin_command_catalog import PANEL_COMMAND_IDS, build_builtin_command_definitions
from core.command_registry import (
    COMMAND_INTERACTION_DIRECT,
    COMMAND_INTERACTION_PANEL,
    CommandRegistry,
    builtin_command_metadata,
)

logger = logging.getLogger(__name__)


def create_command_registry() -> CommandRegistry:
    registry = CommandRegistry()
    definitions = build_builtin_command_definitions()
    for definition in definitions:
        definition.metadata = builtin_command_metadata(definition.id, definition.category)
        definition.interaction_mode = (
            COMMAND_INTERACTION_PANEL if definition.id in PANEL_COMMAND_IDS else COMMAND_INTERACTION_DIRECT
        )
    for definition in definitions:
        registry.register(definition)
    migrated = registry.migrate_slash_commands() + registry.migrate_builtin_aliases()
    from core.slash_commands import set_command_registry

    set_command_registry(registry)
    logger.info("命令注册中心初始化完成: %d 条命令 (%d 迁移)", registry.count(), migrated)
    return registry
