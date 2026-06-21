"""Versioned application configuration contracts."""

from .schema import CURRENT_CONFIG_SCHEMA_VERSION, ConfigMigrationError, migrate_config

__all__ = ["CURRENT_CONFIG_SCHEMA_VERSION", "ConfigMigrationError", "migrate_config"]
