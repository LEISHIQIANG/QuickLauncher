import json

from scripts.validate_runtime_manifest import DEFAULT_MANIFEST, validate


def test_runtime_manifest_matches_active_build_targets():
    assert validate() == []


def test_runtime_manifest_versions_match_source_contracts():
    from application.config.schema import CURRENT_CONFIG_SCHEMA_VERSION
    from extensions.sdk import API_VERSION

    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["versions"]["config_schema"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert manifest["versions"]["plugin_sdk"] == API_VERSION
