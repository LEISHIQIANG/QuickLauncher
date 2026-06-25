from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.config.schema import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    MIGRATIONS,
    SUPPORTED_SCHEMA_VERSIONS,
    ConfigMigrationError,
    _v1_to_v2_template,
    migrate_config,
    register_migration,
)
from core.config_validation import load_valid_data_file
from core.data_loader import DataLoader

FIXTURES = Path(__file__).parent / "fixtures" / "config"


@pytest.mark.parametrize("name", ["1.6-normal.json", "1.6-missing-fields.json"])
def test_legacy_golden_corpus_migrates_idempotently(name: str):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    first = migrate_config(raw)
    second = migrate_config(first.data)

    assert first.changed is True
    assert first.data["config_schema_version"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert second.changed is False
    assert second.data == first.data
    assert "config_schema_version" not in raw


def test_loader_applies_schema_before_deserialization(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text((FIXTURES / "1.6-normal.json").read_text(encoding="utf-8"), encoding="utf-8")

    loaded, issues = load_valid_data_file(path)

    assert loaded.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    assert "config_schema_migrated:0->1" in issues


def test_normal_schema_migration_is_info_not_warning(tmp_path: Path, caplog):
    path = tmp_path / "data.json"
    path.write_text((FIXTURES / "1.6-normal.json").read_text(encoding="utf-8"), encoding="utf-8")
    reports = []
    dm = SimpleNamespace(data_file=path, _write_recovery_report=reports.append)

    with caplog.at_level(logging.INFO, logger="core.data_loader"):
        loaded = DataLoader(dm).load()

    assert loaded.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    assert dm._config_status["status"] == "ok"
    assert dm._config_status["issues"] == []
    assert dm._config_schema_migration_notes == ["config_schema_migrated:0->1"]
    assert "配置架构迁移完成" in caplog.text
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


@pytest.mark.parametrize("version", [-1, True, "1", 999])
def test_invalid_or_future_schema_fails_closed(version):
    with pytest.raises(ConfigMigrationError):
        migrate_config({"config_schema_version": version, "folders": []})


def test_supported_schema_versions_cover_migration_chain():
    """The supported set must cover the entire chain reachable from raw=0.

    Otherwise a freshly-migrated file would still trip the
    ``not in supported set`` check on the next run.
    """
    expected = set(range(0, CURRENT_CONFIG_SCHEMA_VERSION + 1))
    assert expected <= SUPPORTED_SCHEMA_VERSIONS


def test_register_migration_rejects_duplicates():
    """Registering the same source version twice must fail loudly."""
    with pytest.raises(ConfigMigrationError, match="already registered"):
        register_migration(0, _v1_to_v2_template)


def test_register_migration_rejects_future_target():
    """Migration target newer than CURRENT is forbidden at registration time."""
    with pytest.raises(ConfigMigrationError, match="newer than CURRENT"):
        register_migration(CURRENT_CONFIG_SCHEMA_VERSION, _v1_to_v2_template)


def test_v1_to_v2_template_is_pure_and_idempotent_when_re_applied():
    """The template must deep-copy, stamp the version, and be safe to re-run.

    The test only validates the template function; the chain does not
    include it yet.  Promoting the template to a real migration is a
    small code change (3 lines) plus a golden corpus fixture.
    """
    raw = {
        "config_schema_version": 1,
        "popup_trigger_button": "middle",
        "popup_trigger_modifiers": ["ctrl"],
        "popup_trigger_keys": [],
        "popup_trigger_mode": "mouse",
    }

    first = _v1_to_v2_template(raw)
    second = _v1_to_v2_template(first)

    assert first["config_schema_version"] == 2
    assert first["popup_trigger"] == {
        "button": "middle",
        "modifiers": ["ctrl"],
        "keys": [],
        "mode": "mouse",
    }
    # The legacy fields must be removed on first apply and absent on second.
    assert "popup_trigger_button" not in first
    assert first == second
    # The input must not be mutated.
    assert "popup_trigger" not in raw
    assert raw["popup_trigger_button"] == "middle"


def test_v1_to_v2_template_does_not_run_during_normal_migration():
    """The chain is not silently extended when the template is in the module."""
    raw = {"config_schema_version": 1, "folders": []}
    result = migrate_config(raw)
    assert result.to_version == CURRENT_CONFIG_SCHEMA_VERSION == 1
    assert 1 not in MIGRATIONS or MIGRATIONS[1] is _v1_to_v2_template  # noqa: E501
    # The function exists; the chain does not invoke it.
    assert result.data == {"config_schema_version": 1, "folders": []}
