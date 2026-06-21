"""The only composition root for the GUI process."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from application.state import StateStore
from bootstrap.app_context import AppContext
from bootstrap.ipc import release_instance_mutex
from bootstrap.lifecycle import LifecycleManager
from bootstrap.registry_factory import create_command_registry
from core.command_registry import CommandRegistry
from core.data_manager import DataManager
from core.executor_manager import shutdown_all_executors
from core.module_registry import ModuleRegistry
from core.plugin_manager import PluginManager
from core.shortcut_chain_exec import (
    configure_module_registry,
    configure_shortcut_executor_provider,
)
from core.shortcut_executor import ShortcutExecutor
from ui.adapters.action_chain_editor import open_action_chain_editor
from ui.adapters.tray_ui_actions import TrayUIActions
from ui.runtime_settings import configure_settings_provider
from ui.styles.theme_controller import configure_theme_provider


@dataclass(frozen=True)
class ApplicationServices:
    data_manager: DataManager
    command_registry: CommandRegistry
    module_registry: ModuleRegistry
    plugin_manager: PluginManager | None


def build_application_services() -> ApplicationServices:
    data_manager = DataManager()
    command_registry = create_command_registry()
    module_registry = ModuleRegistry()
    plugin_manager: PluginManager | None = None
    safe_mode = bool(os.environ.get("QL_SAFE_MODE"))
    plugins_enabled = bool(getattr(data_manager.get_settings(), "enable_plugins", True))
    if not safe_mode and plugins_enabled:
        from bootstrap.plugin_factory import create_plugin_manager

        plugin_manager = create_plugin_manager(command_registry, data_manager, module_registry)
    return ApplicationServices(
        data_manager=data_manager,
        command_registry=command_registry,
        module_registry=module_registry,
        plugin_manager=plugin_manager,
    )


def build_app_context(tray_app: Any, server: Any, instance_mutex: Any) -> AppContext:
    """Complete GUI composition and register every process-owned resource."""
    ui_actions = TrayUIActions(tray_app)
    tray_app.ui_actions = ui_actions
    registry = tray_app.command_registry
    module_registry = tray_app.module_registry
    configure_module_registry(module_registry)
    configure_shortcut_executor_provider(lambda: ShortcutExecutor)
    configure_theme_provider(lambda: getattr(tray_app.data_manager.get_settings(), "theme", "dark"))
    configure_settings_provider(tray_app.data_manager.get_settings)
    ShortcutExecutor.configure_services(
        data_manager=tray_app.data_manager,
        ui_actions=ui_actions,
    )
    module_registry.set_action_chain_editor(open_action_chain_editor)

    lifecycle = LifecycleManager()
    lifecycle.register("executors", shutdown_all_executors)
    lifecycle.register("instance-mutex", lambda: release_instance_mutex(instance_mutex))
    lifecycle.register("ipc-server", server.close)
    lifecycle.register("tray-app", tray_app.stop)
    return AppContext(
        lifecycle=lifecycle,
        state_store=StateStore(tray_app.data_manager.data.to_dict()),
        ui_actions=ui_actions,
        command_registry=registry,
        data_manager=tray_app.data_manager,
        plugin_manager=tray_app.plugin_manager,
    )
