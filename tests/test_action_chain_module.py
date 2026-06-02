import json

from core.data_models import (
    ACTION_CHAIN_MODULE_ID,
    ACTION_CHAIN_MODULE_VERSION,
    ACTION_CHAIN_SCHEMA_VERSION,
    Folder,
    ShortcutItem,
    ShortcutType,
)
from core.module_registry import ACTION_CHAIN_MODULE_ID as REGISTRY_ACTION_CHAIN_ID
from core.module_registry import MODULE_AVAILABLE, MODULE_INCOMPATIBLE, ModuleRecord, _host_version_compatible, module_registry
from core.shortcut_chain_exec import execute_shortcut_chain


class _Data:
    def __init__(self, items):
        self.data = type("AppData", (), {"folders": [Folder(id="f", name="F", items=items)]})()


def test_action_chain_manifest_and_registry_load():
    record = module_registry.get(REGISTRY_ACTION_CHAIN_ID)

    assert record.status == MODULE_AVAILABLE
    assert record.is_available() is True
    assert record.manifest["id"] == REGISTRY_ACTION_CHAIN_ID
    assert record.manifest["entry"] == "modules.action_chain.entry:ActionChainModule"
    assert record.api.module_version == record.manifest["module_version"]
    assert record.api.schema_version == record.manifest["schema_version"]


def test_action_chain_module_can_be_disabled(monkeypatch):
    step = ShortcutItem(id="step", name="Step", type=ShortcutType.FILE)
    chain = ShortcutItem(id="chain", name="Chain", type=ShortcutType.CHAIN, chain_steps=[{"shortcut_id": "step"}])

    class Executor:
        @staticmethod
        def execute(shortcut, force_new=False):
            raise AssertionError("disabled action-chain module must not execute steps")

    monkeypatch.setattr("core.ShortcutExecutor", Executor)
    module_registry.set_disabled(REGISTRY_ACTION_CHAIN_ID, True)
    try:
        result = execute_shortcut_chain(chain, _Data([step, chain]))
    finally:
        module_registry.set_disabled(REGISTRY_ACTION_CHAIN_ID, False)

    assert result.success is False
    assert "模块" in result.message
    assert result.payload["items"][0]["error"] == "disabled"


def test_action_chain_unavailable_status_result_is_clear():
    from modules.action_chain.entry import unavailable_result

    result = unavailable_result(MODULE_INCOMPATIBLE)

    assert result.success is False
    assert "不兼容" in result.message
    assert result.payload["items"][0]["error"] == MODULE_INCOMPATIBLE


def test_module_record_requires_api_availability():
    class Api:
        def is_available(self):
            return False

    record = ModuleRecord(REGISTRY_ACTION_CHAIN_ID, MODULE_AVAILABLE, {}, Api())

    assert record.is_available() is False


def test_host_version_compatibility_uses_manifest_range():
    assert _host_version_compatible("1.6.2.0", {"min_host_version": "1.6.2.0", "max_host_version": ""})
    assert not _host_version_compatible("1.6.1.0", {"min_host_version": "1.6.2.0", "max_host_version": ""})
    assert not _host_version_compatible("1.7.0.0", {"min_host_version": "1.6.0.0", "max_host_version": "1.6.9.9"})


def test_shortcut_item_chain_module_fields_roundtrip():
    item = ShortcutItem.from_dict(
        {
            "id": "chain",
            "name": "Chain",
            "type": "chain",
            "chain_ref": "chain-uuid",
            "chain_schema_version": "2",
            "chain_data": {"schema_version": 2, "unknown_future_field": {"kept": True}},
            "module_id": ACTION_CHAIN_MODULE_ID,
            "module_version": "0.2.0",
        }
    )

    data = item.to_dict()
    loaded = ShortcutItem.from_dict(json.loads(json.dumps(data, ensure_ascii=False)))

    assert loaded.module_id == ACTION_CHAIN_MODULE_ID
    assert loaded.module_version == "0.2.0"
    assert loaded.chain_schema_version == 2
    assert loaded.chain_ref == "chain-uuid"
    assert loaded.chain_data["unknown_future_field"] == {"kept": True}


def test_old_chain_data_gets_default_module_identity():
    loaded = ShortcutItem.from_dict({"id": "old", "name": "Old", "type": "chain"})

    assert loaded.module_id == ACTION_CHAIN_MODULE_ID
    assert loaded.module_version == ACTION_CHAIN_MODULE_VERSION
    assert loaded.chain_schema_version == ACTION_CHAIN_SCHEMA_VERSION


def test_action_chain_can_be_registered_from_plugin_manifest(tmp_path):
    from core.command_registry import CommandRegistry
    from core.plugin_manager import PluginManager

    plugin_dir = tmp_path / "action_chain_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "action_chain_plugin",
                "name": "Action Chain Plugin",
                "version": "0.1.0",
                "entry": "main.py",
                "permissions": [],
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "module.json").write_text(
        json.dumps(
            {
                "id": REGISTRY_ACTION_CHAIN_ID,
                "name": "Action Chain",
                "display_name": "动作链",
                "module_version": "9.9.9",
                "schema_version": 1,
                "api_version": "1.0",
                "min_host_version": "1.6.2.0",
                "max_host_version": "",
                "entry": "plugin_action_chain_entry:PluginActionChainModule",
                "license_mode": "plugin",
                "capabilities": ["chain.runtime"],
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "plugin_action_chain_entry.py").write_text(
        "class PluginActionChainModule:\n"
        "    def __init__(self, host_api=None, manifest=None):\n"
        "        self.host_api = host_api\n"
        "        self.manifest = manifest or {}\n"
        "        self.module_version = self.manifest.get('module_version', '')\n"
        "        self.schema_version = self.manifest.get('schema_version', 1)\n"
        "        self.api_version = self.manifest.get('api_version', '1.0')\n"
        "    def is_available(self):\n"
        "        return True\n"
        "    def availability_status(self):\n"
        "        return 'available'\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "def register(api):\n"
        "    assert api.register_module('quicklauncher.action_chain', 'module.json')\n",
        encoding="utf-8",
    )

    manager = PluginManager(CommandRegistry(), plugins_dir=str(tmp_path))
    manager.scan_plugins()
    try:
        assert manager.enable_plugin("action_chain_plugin")
        record = module_registry.get(REGISTRY_ACTION_CHAIN_ID)
        assert record.status == MODULE_AVAILABLE
        assert record.provider == "plugin"
        assert record.api.module_version == "9.9.9"
        assert record.manifest_path.endswith("module.json")

        assert manager.disable_plugin("action_chain_plugin")
        record = module_registry.get(REGISTRY_ACTION_CHAIN_ID)
        assert record.provider == "builtin"
    finally:
        module_registry.unregister_external_manifest(REGISTRY_ACTION_CHAIN_ID)
