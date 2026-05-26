"""Shared built-in command aliases."""

from __future__ import annotations

CONFIG_WINDOW_COMMANDS = {"show_config", "show_config_window", "config_window"}
TOPMOST_TOGGLE_COMMANDS = {"topmost", "置顶", "pin", "toggle_topmost"}
TOPMOST_ON_COMMANDS = {"topmost_on", "置顶开", "pin_on"}
TOPMOST_OFF_COMMANDS = {"topmost_off", "置顶关", "unpin", "pin_off"}
WINDOWS_SYSTEM_BUILTIN_COMMANDS = {
    "open_control_panel",
    "open_this_pc",
    "open_recycle_bin",
    "open_task_manager",
    "open_windows_settings",
    "open_services",
    "open_device_manager",
    "open_disk_management",
    "open_network_connections",
    "open_startup_folder",
    "open_system_info",
}
SIMPLE_WINDOWS_SYSTEM_COMMAND_ALIASES = {
    **{command: command for command in WINDOWS_SYSTEM_BUILTIN_COMMANDS},
    "taskmgr": "open_task_manager",
    "task-manager": "open_task_manager",
    "task_manager": "open_task_manager",
    "任务管理器": "open_task_manager",
    "win-settings": "open_windows_settings",
    "windows-settings": "open_windows_settings",
    "windows_settings": "open_windows_settings",
    "ms-settings": "open_windows_settings",
    "系统设置": "open_windows_settings",
    "windows设置": "open_windows_settings",
    "windows 设置": "open_windows_settings",
    "services": "open_services",
    "service": "open_services",
    "services.msc": "open_services",
    "服务": "open_services",
    "device-manager": "open_device_manager",
    "device_manager": "open_device_manager",
    "devmgmt": "open_device_manager",
    "devmgmt.msc": "open_device_manager",
    "设备管理器": "open_device_manager",
    "disk-management": "open_disk_management",
    "disk_manager": "open_disk_management",
    "diskmgmt": "open_disk_management",
    "diskmgmt.msc": "open_disk_management",
    "磁盘管理": "open_disk_management",
    "network-connections": "open_network_connections",
    "network_connections": "open_network_connections",
    "ncpa": "open_network_connections",
    "ncpa.cpl": "open_network_connections",
    "网络连接": "open_network_connections",
    "startup-folder": "open_startup_folder",
    "startup": "open_startup_folder",
    "shell-startup": "open_startup_folder",
    "启动文件夹": "open_startup_folder",
    "开机启动文件夹": "open_startup_folder",
    "system-info": "open_system_info",
    "msinfo32": "open_system_info",
    "systeminfo": "open_system_info",
    "系统信息": "open_system_info",
}
APP_CONTROL_COMMANDS = {"quit_app", "restart_app", "show_log", "show_about", "show_help"}
INTERNAL_PATH_BUILTIN_COMMANDS = {
    "open_config_file",
    "open_icons_dir",
    "open_history_dir",
    "open_auto_backups_dir",
    "open_error_log",
}
MAINTENANCE_BUILTIN_COMMANDS = {
    "show_diagnostics",
    "show_shortcut_health",
    "show_config_history",
    "clean_icon_cache",
    "reload_hooks",
    "open_data_dir",
    "open_install_dir",
    *INTERNAL_PATH_BUILTIN_COMMANDS,
}
UI_CALLBACK_BUILTIN_COMMANDS = {
    "show_config_window",
    "quit_app",
    "restart_app",
    "show_log",
    "show_about",
    "show_help",
    "show_diagnostics",
    "show_shortcut_health",
    "show_config_history",
    "clean_icon_cache",
    "clean-cache",
    "reload_hooks",
    "open_data_dir",
    "open_install_dir",
}

BUILTIN_COMMAND_ALIASES = {
    **{command: "show_config_window" for command in CONFIG_WINDOW_COMMANDS},
    "配置窗口": "show_config_window",
    **{command: "toggle_topmost" for command in TOPMOST_TOGGLE_COMMANDS},
    **{command: "pin_on" for command in TOPMOST_ON_COMMANDS},
    **{command: "pin_off" for command in TOPMOST_OFF_COMMANDS},
    **{command: command for command in APP_CONTROL_COMMANDS},
    **{command: command for command in MAINTENANCE_BUILTIN_COMMANDS},
    "diagnostics": "show_diagnostics",
    "diag": "show_diagnostics",
    "诊断": "show_diagnostics",
    "诊断中心": "show_diagnostics",
    "shortcut_health": "show_shortcut_health",
    "shortcut-health": "show_shortcut_health",
    "health": "show_shortcut_health",
    "icons": "show_shortcut_health",
    "图标检查": "show_shortcut_health",
    "图标诊断": "show_shortcut_health",
    "诊断图标": "show_shortcut_health",
    "config_history": "show_config_history",
    "config-history": "show_config_history",
    "配置历史": "show_config_history",
    "清理图标": "clean_icon_cache",
    "图标缓存": "clean_icon_cache",
    "icon_cache": "clean_icon_cache",
    "icon-cache": "clean_icon_cache",
    "clean-icons": "clean_icon_cache",
    "clear_icons": "clean_icon_cache",
    "clear-icons": "clean_icon_cache",
    "清理缓存": "clean-cache",
    "缓存清理": "clean-cache",
    "clean_cache": "clean-cache",
    "clean-cache": "clean-cache",
    "cache-clean": "clean-cache",
    "clear-cache": "clean-cache",
    "hooks": "reload_hooks",
    "reinstall_hooks": "reload_hooks",
    "reload-hooks": "reload_hooks",
    "reinstall-hooks": "reload_hooks",
    "重装钩子": "reload_hooks",
    "钩子": "reload_hooks",
    "app_data": "open_data_dir",
    "app-data": "open_data_dir",
    "config_dir": "open_data_dir",
    "config-dir": "open_data_dir",
    "data-dir": "open_data_dir",
    "数据目录": "open_data_dir",
    "配置目录": "open_data_dir",
    "install_dir": "open_install_dir",
    "install-dir": "open_install_dir",
    "program_dir": "open_install_dir",
    "program-dir": "open_install_dir",
    "project_dir": "open_install_dir",
    "project-dir": "open_install_dir",
    "安装目录": "open_install_dir",
    "项目目录": "open_install_dir",
    "软件目录": "open_install_dir",
    "config_file": "open_config_file",
    "config-file": "open_config_file",
    "data_json": "open_config_file",
    "data-json": "open_config_file",
    "data.json": "open_config_file",
    "配置文件": "open_config_file",
    "icons_dir": "open_icons_dir",
    "icons-dir": "open_icons_dir",
    "icon_dir": "open_icons_dir",
    "icon-dir": "open_icons_dir",
    "user-icons": "open_icons_dir",
    "图标目录": "open_icons_dir",
    "用户图标": "open_icons_dir",
    "history_dir": "open_history_dir",
    "history-dir": "open_history_dir",
    "config-history-dir": "open_history_dir",
    "历史目录": "open_history_dir",
    "快照目录": "open_history_dir",
    "auto_backups": "open_auto_backups_dir",
    "auto-backups": "open_auto_backups_dir",
    "auto_backup_dir": "open_auto_backups_dir",
    "backup-dir": "open_auto_backups_dir",
    "backups-dir": "open_auto_backups_dir",
    "自动备份": "open_auto_backups_dir",
    "备份目录": "open_auto_backups_dir",
    "error_log": "open_error_log",
    "error-log": "open_error_log",
    "error.log": "open_error_log",
    "log-file": "open_error_log",
    "错误日志": "open_error_log",
    # ── Phase 3: Power-User Superpower Commands ──
    "wifi": "wifi",
    "wlan": "wifi",
    "无线密码": "wifi",
    "wi-fi": "wifi",
    "wifi密码": "wifi",
    "wifi密码查询": "wifi",
    "wi-fi 密码查询": "wifi",
    "wi-fi密码查询": "wifi",
    "wi-fi密码": "wifi",
    "hosts": "hosts",
    "host": "hosts",
    "port": "port",
    "端口": "port",
    "netstat": "port",
    "dns": "dns",
    "flushdns": "dns",
    "清理dns": "dns",
    "cidr": "cidr",
    "subnet": "cidr",
    "子网": "cidr",
    "网段": "cidr",
    "tls": "tls",
    "cert": "tls",
    "certificate": "tls",
    "ssl": "tls",
    "证书": "tls",
    "path-audit": "path-audit",
    "path": "path-audit",
    "env-path": "path-audit",
    "环境变量": "path-audit",
    "path体检": "path-audit",
    "explorer": "explorer",
    "重启资源管理器": "explorer",
    "restart-explorer": "explorer",
    "conflict": "conflict",
    "冲突": "conflict",
    "hotkey-conflict": "conflict",
}


def canonical_builtin_command(command: str) -> str:
    """Resolve a command alias to its canonical name — prefers registry when available.

    Returns the handler callback name (e.g. 'toggle_topmost', 'show_config_window'),
    not the command ID — callers use it for dispatch, not display.
    """
    clean_cmd = (command or "").strip()
    if not clean_cmd:
        return ""

    # 1. Try to resolve the entire string first (e.g., "Wi-Fi 密码查询", "windows 设置")
    try:
        from core import ensure_registry_initialized, registry
        from core.command_registry import _CallbackHandler

        ensure_registry_initialized()
        if registry is not None and registry.count() > 0:
            canonical = registry.get_canonical(clean_cmd)
            if canonical:
                cmd_def = registry.get(canonical)
                if cmd_def is not None and isinstance(cmd_def.handler, _CallbackHandler):
                    return cmd_def.handler._callback_name
                return canonical
    except Exception:
        pass

    val = BUILTIN_COMMAND_ALIASES.get(clean_cmd.lower())
    if val:
        return val
    val = SIMPLE_WINDOWS_SYSTEM_COMMAND_ALIASES.get(clean_cmd.lower())
    if val:
        return val

    # 2. Fallback to splitting by space (e.g., "port 8080", "wifi profile_name")
    parts = clean_cmd.split(None, 1)
    cmd_name = parts[0] if parts else ""
    if not cmd_name:
        return ""
    try:
        from core import ensure_registry_initialized, registry
        from core.command_registry import _CallbackHandler

        ensure_registry_initialized()
        if registry is not None and registry.count() > 0:
            canonical = registry.get_canonical(cmd_name)
            if canonical:
                cmd_def = registry.get(canonical)
                if cmd_def is not None and isinstance(cmd_def.handler, _CallbackHandler):
                    return cmd_def.handler._callback_name
                return canonical
    except Exception:
        pass
    return BUILTIN_COMMAND_ALIASES.get(cmd_name.lower(), "") or SIMPLE_WINDOWS_SYSTEM_COMMAND_ALIASES.get(
        cmd_name.lower(), ""
    )


def is_builtin_command_alias(command: str) -> bool:
    return bool(canonical_builtin_command(command))
