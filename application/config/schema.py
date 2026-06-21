"""Pure, deterministic migrations for the root QuickLauncher configuration.

The migration chain is a ``vN -> vN+1`` table keyed by the *source* version.
Each entry must be a pure function: same input always produces the same
output, the caller's data is never mutated, and the returned dict always
carries ``config_schema_version = source + 1``.

To add a new migration:

1. Implement ``_vN_to_vN_plus_one(data)`` using ``deepcopy``.
2. Register the entry in :data:`MIGRATIONS` keyed by ``N``.
3. Bump :data:`CURRENT_CONFIG_SCHEMA_VERSION` to ``N + 1``.
4. Add a golden corpus fixture under ``tests/fixtures/config/`` covering
   the upgrade, then extend ``tests/test_config_schema_migrations.py``
   with a parametrized case that asserts the migration is idempotent and
   produces the expected schema version.
5. Update ``docs/config-file-commit-order.md`` if the new schema changes
   which files participate in a single configuration commit.

The :func:`_v1_to_v2_template` below is a deliberately inert template that
demonstrates the pattern without enabling the v1 -> v2 hop.  It is
intentionally *not* registered in :data:`MIGRATIONS`; promoting it is a
single-line change together with the ``CURRENT_CONFIG_SCHEMA_VERSION``
bump, so the diff for any v1 -> v2 release is reviewable as a small,
discrete commit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from application.errors import InfrastructureError

CURRENT_CONFIG_SCHEMA_VERSION = 1

# Future schema versions.  When raising CURRENT_CONFIG_SCHEMA_VERSION,
# remove the corresponding entry from this set so ``migrate_config`` can
# detect "older executable" data and fail closed.
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({0, 1})


class ConfigMigrationError(ValueError, InfrastructureError):
    """Raised when persisted configuration cannot be migrated safely."""


@dataclass(frozen=True)
class ConfigMigrationResult:
    data: dict[str, Any]
    from_version: int
    to_version: int

    @property
    def changed(self) -> bool:
        return self.from_version != self.to_version


Migration = Callable[[dict[str, Any]], dict[str, Any]]


def _v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(data)
    migrated["config_schema_version"] = 1
    return migrated


# Template for the next schema bump.  Copy this block when you need
# vN -> vN+1 and adapt the field renames / additions.  The function is
# not in MIGRATIONS yet because CURRENT_CONFIG_SCHEMA_VERSION is still 1.
def _v1_to_v2_template(data: dict[str, Any]) -> dict[str, Any]:
    """Reference implementation for the next schema bump.

    Currently unused.  The shape mirrors the v0 -> v1 migration: deep-copy
    the input, perform field-level changes, and stamp the new schema
    version.  Promotion requires:

    * Registering the function in :data:`MIGRATIONS` keyed by ``1``.
    * Bumping :data:`CURRENT_CONFIG_SCHEMA_VERSION` to ``2`` and adding
      ``2`` to :data:`SUPPORTED_SCHEMA_VERSIONS`.
    * Adding a golden corpus fixture + parametrized test case.
    """
    migrated = deepcopy(data)
    # Example field rename: 1.7.x stores ``popup_trigger_button``; 2.0
    # consolidates the trigger triplet into ``popup_trigger`` (dict).
    if "popup_trigger_button" in migrated:
        migrated.setdefault(
            "popup_trigger",
            {
                "button": migrated.pop("popup_trigger_button"),
                "modifiers": migrated.pop("popup_trigger_modifiers", []),
                "keys": migrated.pop("popup_trigger_keys", []),
                "mode": migrated.pop("popup_trigger_mode", "mouse"),
            },
        )
    migrated["config_schema_version"] = 2
    return migrated


MIGRATIONS: dict[int, Migration] = {0: _v0_to_v1}


def register_migration(source_version: int, migration: Migration) -> None:
    """Register a new ``vN -> vN+1`` migration in the chain.

    This helper exists so the W2 review checklist ("vN -> vN+1 chain
    extensible without touching :func:`migrate_config`") is enforceable
    in code.  Calling it more than once for the same source version is a
    programming error: it would mean two competing definitions of the
    same upgrade step.

    The function is deliberately not exposed in a public module — it is
    used by version bumps in the same process and is not part of any
    cross-process contract.  Schema version changes ship as code
    deployments, not as runtime configuration.
    """
    if source_version in MIGRATIONS:
        raise ConfigMigrationError(
            f"migration v{source_version}->v{source_version + 1} already registered"
        )
    if source_version + 1 > CURRENT_CONFIG_SCHEMA_VERSION:
        raise ConfigMigrationError(
            f"cannot register v{source_version}->v{source_version + 1}: "
            f"target newer than CURRENT_CONFIG_SCHEMA_VERSION={CURRENT_CONFIG_SCHEMA_VERSION}"
        )
    MIGRATIONS[source_version] = migration


def migrate_config(raw: Mapping[str, Any]) -> ConfigMigrationResult:
    """Return an upgraded copy without mutating the caller's data.

    Missing schema metadata denotes the compatible 1.6.x (v0) format.
    Future schemas fail closed so an older executable never rewrites them.
    """
    if not isinstance(raw, Mapping):
        raise ConfigMigrationError("root_not_object: config root must be an object")
    data = deepcopy(dict(raw))
    raw_version = data.get("config_schema_version", 0)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version < 0:
        raise ConfigMigrationError(f"invalid config_schema_version: {raw_version!r}")
    if raw_version > CURRENT_CONFIG_SCHEMA_VERSION:
        raise ConfigMigrationError(
            f"config schema {raw_version} is newer than supported {CURRENT_CONFIG_SCHEMA_VERSION}"
        )
    if raw_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ConfigMigrationError(
            f"config schema {raw_version} is not in the supported set "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    version = raw_version
    while version < CURRENT_CONFIG_SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ConfigMigrationError(f"missing config migration v{version}->v{version + 1}")
        data = migration(data)
        next_version = data.get("config_schema_version")
        if next_version != version + 1:
            raise ConfigMigrationError(f"migration v{version} did not produce schema v{version + 1}")
        version += 1
    return ConfigMigrationResult(data=data, from_version=raw_version, to_version=version)
