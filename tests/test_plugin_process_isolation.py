from __future__ import annotations

import json
import os
from pathlib import Path

from core.command_registry import CommandContext, CommandRegistry
from core.plugin_manager import PluginManager


def _write_plugin(root: Path, plugin_id: str, source: str, permissions: list[str] | None = None) -> None:
    directory = root / plugin_id
    directory.mkdir()
    (directory / "plugin.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": plugin_id,
                "version": "1.0.0",
                "entry": "main.py",
                "trust_level": "community-unverified",
                "install_source": "third_party",
                "permissions": permissions or [],
            }
        ),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(source, encoding="utf-8")


def test_unverified_plugin_executes_in_worker_and_is_reaped(tmp_path):
    _write_plugin(
        tmp_path,
        "isolated_demo",
        """
import os
def execute(context):
    return {"success": True, "message": "isolated", "payload": {"pid": os.getpid()}}
def register(api):
    assert api.register_command(id="isolated_demo.pid", title="PID", handler=execute)
""",
    )
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(tmp_path))
    manager.scan_plugins()

    assert manager.load_plugin("isolated_demo") is True
    snapshot = manager.worker_snapshot()["isolated_demo"]
    assert snapshot["running"] is True
    assert snapshot["pid"] != os.getpid()

    result = registry.get("isolated_demo.pid").handler(CommandContext())
    assert result.success is True
    assert result.payload["pid"] == snapshot["pid"]

    assert manager.disable_plugin("isolated_demo") is True
    assert "isolated_demo" not in manager.worker_snapshot()


def test_worker_host_api_enforces_declared_permissions(tmp_path):
    _write_plugin(
        tmp_path,
        "permission_demo",
        """
def execute(context):
    api.write_data_file("forbidden.txt", "data")
    return {"success": True}
def register(plugin_api):
    global api
    api = plugin_api
    assert api.register_command(id="permission_demo.write", title="Write", handler=execute)
""",
    )
    registry = CommandRegistry()
    manager = PluginManager(registry, plugins_dir=str(tmp_path))
    manager.scan_plugins()
    assert manager.load_plugin("permission_demo") is True

    result = registry.get("permission_demo.write").handler(CommandContext())
    assert result.success is False
    assert "file.write" in (result.error or result.message)
    manager.shutdown()
