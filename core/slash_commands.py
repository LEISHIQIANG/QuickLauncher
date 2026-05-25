"""
Slash command definitions for command mode.

Phase 1 migration: find/get functions redirect to the new CommandRegistry
when available, falling back to the old local implementation.
The static SLASH_COMMANDS list is kept for backward compatibility
(e.g. slash_help_window.py imports it directly).
"""

from dataclasses import dataclass

# Avoid circular import at module level — imported lazily inside functions
# from core.command_registry import _CallbackHandler


@dataclass
class SlashCommand:
    canonical: str
    aliases: list[str]
    description: str
    category: str
    handler: str
    icon_path: str = ""
    display_name: str = ""
    interaction_mode: str = "direct"


SLASH_COMMANDS = [
    SlashCommand("config", ["config", "settings", "配置"], "打开配置窗口", "system", "show_config_window", "assets/command_icons/config.png", "配置"),
    SlashCommand("quit", ["quit", "exit", "退出"], "退出应用", "system", "quit_app", "assets/command_icons/quit.png", "退出"),
    SlashCommand("restart", ["restart", "重启"], "重启应用", "system", "restart_app", "assets/command_icons/restart.png", "重启"),
    SlashCommand("log", ["log", "日志"], "显示日志窗口", "system", "show_log", "assets/command_icons/log.png", "日志"),
    SlashCommand("diagnostics", ["diagnostics", "diag", "诊断", "诊断中心"], "打开诊断中心", "internal", "show_diagnostics", "assets/command_icons/diagnostics.png", "诊断中心"),
    SlashCommand("shortcut-health", ["shortcut-health", "health", "icons", "图标检查", "图标诊断", "诊断图标"], "检查图标、路径和命令风险", "internal", "show_shortcut_health", "assets/command_icons/shortcut-health.png", "图标检查"),
    SlashCommand("config-history", ["config-history", "配置历史"], "查看配置历史快照", "internal", "show_config_history", "assets/command_icons/config-history.png", "配置历史"),
    SlashCommand("clean-icons", ["clean-icons", "icon-cache", "clear-icons", "清理图标", "图标缓存"], "立即清理图标缓存", "internal", "clean_icon_cache", "assets/command_icons/icon-cache.png", "清理图标"),
    SlashCommand("clean-cache", ["clean-cache", "cache-clean", "clear-cache", "清理缓存", "缓存清理"], "清理项目目录下未使用的临时缓存", "internal", "clean-cache", "assets/command_icons/icon-cache.png", "清理缓存", "panel"),
    SlashCommand("reload-hooks", ["reload-hooks", "hooks", "reinstall-hooks", "重装钩子", "钩子"], "重装鼠标和键盘钩子", "internal", "reload_hooks", "assets/command_icons/hooks.png", "重装钩子"),
    SlashCommand("data-dir", ["data-dir", "app-data", "config-dir", "数据目录", "配置目录"], "打开配置数据目录", "internal", "open_data_dir", "assets/command_icons/data-dir.png", "数据目录"),
    SlashCommand("install-dir", ["install-dir", "program-dir", "project-dir", "安装目录", "项目目录", "软件目录"], "打开软件安装目录", "internal", "open_install_dir", "assets/command_icons/install-dir.png", "安装目录"),
    SlashCommand("config-file", ["config-file", "config_file", "data-json", "data.json", "配置文件"], "打开 data.json 配置文件", "internal", "open_config_file", "assets/command_icons/config-file.png", "配置文件"),
    SlashCommand("icons-dir", ["icons-dir", "icon-dir", "user-icons", "图标目录", "用户图标"], "打开用户图标目录", "internal", "open_icons_dir", "assets/command_icons/icons-dir.png", "图标目录"),
    SlashCommand("history-dir", ["history-dir", "config-history-dir", "历史目录", "快照目录"], "打开配置历史快照目录", "internal", "open_history_dir", "assets/command_icons/history-dir.png", "历史目录"),
    SlashCommand("auto-backups", ["auto-backups", "backup-dir", "backups-dir", "自动备份", "备份目录"], "打开自动备份目录", "internal", "open_auto_backups_dir", "assets/command_icons/auto-backups.png", "自动备份"),
    SlashCommand("error-log", ["error-log", "error.log", "log-file", "错误日志"], "打开 error.log 或日志目录", "internal", "open_error_log", "assets/command_icons/error-log.png", "错误日志"),
    SlashCommand("topmost", ["topmost", "pin", "置顶"], "切换窗口置顶", "window", "toggle_topmost", "assets/command_icons/topmost.png", "置顶"),
    SlashCommand("pin-on", ["pin-on", "置顶开"], "开启窗口置顶", "window", "pin_on", "assets/command_icons/pin-on.png", "置顶开"),
    SlashCommand("pin-off", ["pin-off", "unpin", "置顶关"], "关闭窗口置顶", "window", "pin_off", "assets/command_icons/pin-off.png", "置顶关"),
    SlashCommand("help", ["help", "帮助"], "显示所有命令", "help", "show_help", "assets/command_icons/help.png", "帮助"),
    SlashCommand("about", ["about", "关于"], "关于 QuickLauncher", "help", "show_about", "assets/command_icons/about.png", "关于"),
    # ── Phase 3: Power-User Superpower Commands ──
    SlashCommand("wifi", ["wifi", "wlan", "无线密码"], "列出已保存的 Wi-Fi 或查询明文密码", "system", "wifi", "", "Wi-Fi 密码查询"),
    SlashCommand("hosts", ["hosts", "host"], "以管理员权限编辑系统 hosts 文件", "system", "hosts", "", "编辑 Hosts"),
    SlashCommand("port", ["port", "端口", "netstat"], "查询端口占用进程，支持 kill 子命令释放", "developer", "port", "", "端口占用查询"),
    SlashCommand("dns", ["dns", "flushdns", "清理dns"], "静默刷新 Windows DNS 缓存", "network", "dns", "", "清理 DNS"),
    SlashCommand("cidr", ["cidr", "subnet", "子网", "网段"], "计算网段、掩码、广播地址和可用地址范围", "network", "cidr", "", "CIDR 子网计算"),
    SlashCommand("tls", ["tls", "cert", "certificate", "ssl", "证书"], "检查域名 TLS 协议、证书颁发者与到期时间", "network", "tls", "", "TLS 证书检查"),
    SlashCommand("path-audit", ["path-audit", "path", "env-path", "环境变量", "path体检"], "检查 PATH 失效目录、重复目录和常用命令遮蔽", "developer", "path-audit", "", "PATH 体检"),
    SlashCommand("explorer", ["explorer", "重启资源管理器", "restart-explorer"], "安全重启 Windows Explorer 进程", "system", "explorer", "", "重启资源管理器"),
    SlashCommand("conflict", ["conflict", "冲突", "hotkey-conflict"], "扫描快捷键冲突和占用报告", "internal", "conflict", "", "快捷键冲突"),
]

_ALIAS_TO_COMMAND = {}
for cmd in SLASH_COMMANDS:
    for alias in cmd.aliases:
        _ALIAS_TO_COMMAND[alias.lower()] = cmd


def _convert_to_slash_command(cmd_def) -> SlashCommand | None:
    """Convert a CommandDefinition back to SlashCommand for backward compat callers.

    Preserves the original callback name (e.g. 'show_config_window') when the
    handler is a _CallbackHandler wrapper so the old execution path can dispatch it.
    """
    try:
        from core.command_registry import _CallbackHandler

        handler_name = cmd_def.id
        if isinstance(cmd_def.handler, _CallbackHandler):
            handler_name = cmd_def.handler._callback_name

        # Append parameter hints to display name
        display = cmd_def.title
        if cmd_def.params:
            hints = " ".join(
                f"[{p.name}]" if p.required else f"[{p.name}?]"
                for p in cmd_def.params
            )
            display = f"{display}  {hints}"

        return SlashCommand(
            canonical=cmd_def.id,
            aliases=cmd_def.aliases,
            description=cmd_def.description,
            category=cmd_def.category,
            handler=handler_name,
            icon_path=getattr(cmd_def, 'icon_path', ''),
            display_name=display,
            interaction_mode=getattr(cmd_def, "interaction_mode", "direct"),
        )
    except Exception:
        return None


def _registry_available():
    """Check whether the new CommandRegistry has been initialized and has data.

    Lazily initializes the registry on first call so the migration
    from old SLASH_COMMANDS / BUILTIN_COMMAND_ALIASES happens automatically.
    """
    try:
        from core import ensure_registry_initialized, registry
        ensure_registry_initialized()
        return registry is not None and registry.count() > 0
    except Exception:
        return False


def find_matching_commands(query: str) -> list[SlashCommand]:
    """Find matching slash commands — prefers registry when available."""
    parts = (query or "").strip().split(None, 1)
    cmd_word = parts[0] if parts else ""

    if _registry_available():
        try:
            from core import registry
            results = registry.find(cmd_word)
            converted = [_convert_to_slash_command(c) for c in results]
            return [c for c in converted if c is not None]
        except Exception:
            pass

    # Fall back to old implementation
    query_lower = cmd_word.lower()
    if not query_lower:
        return SLASH_COMMANDS

    if query_lower in _ALIAS_TO_COMMAND:
        return [_ALIAS_TO_COMMAND[query_lower]]

    exact_matches = []
    prefix_matches = []
    substring_matches = []

    for cmd in SLASH_COMMANDS:
        matched_exact = False
        matched_prefix = False
        matched_substring = False

        for alias in cmd.aliases:
            alias_lower = alias.lower()
            if alias_lower == query_lower:
                matched_exact = True
                break
            elif alias_lower.startswith(query_lower):
                matched_prefix = True
            elif query_lower in alias_lower:
                matched_substring = True

        if matched_exact:
            exact_matches.append(cmd)
        elif matched_prefix:
            prefix_matches.append(cmd)
        elif matched_substring:
            substring_matches.append(cmd)

    result = []
    seen = set()
    for cmd in exact_matches + prefix_matches + substring_matches:
        if cmd.canonical not in seen:
            seen.add(cmd.canonical)
            result.append(cmd)
    return result


def get_command_by_alias(alias: str) -> SlashCommand | None:
    """Look up a command by alias — prefers registry when available."""
    if _registry_available():
        try:
            from core import registry
            canonical = registry.get_canonical(alias)
            if canonical:
                cmd_def = registry.get(canonical)
                if cmd_def is not None:
                    return _convert_to_slash_command(cmd_def)
        except Exception:
            pass
    return _ALIAS_TO_COMMAND.get(alias.lower())
