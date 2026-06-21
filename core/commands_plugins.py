"""Plugin management built-in command handlers."""

from __future__ import annotations

import logging
import os

from .command_registry import CommandAction, CommandContext, CommandResult

logger = logging.getLogger(__name__)


def _get_plugin_manager():
    try:
        import types

        import core

        pm = getattr(core, "plugin_manager", None)
        if pm is not None and not isinstance(pm, types.ModuleType):
            return pm
        return None
    except Exception:
        logger.debug("获取插件管理器实例失败", exc_info=True)
        return None


def cmd_plugin_list(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    plugins = pm.list_plugins()
    if not plugins:
        return CommandResult(success=False, message="没有找到插件", error="空")
    lines = []
    for plugin in plugins:
        manifest = plugin.manifest
        status = plugin.status
        command_count = len(plugin.registered_commands)
        error = f" [{plugin.error}]" if plugin.error else ""
        lines.append(f"{manifest.id} v{manifest.version} — {status}{error}")
        lines.append(f"  {manifest.description}")
        if command_count:
            lines.append(f"  已注册 {command_count} 个命令")
    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=message,
        actions=[CommandAction(type="copy", label="复制列表", value=message)],
    )


def cmd_plugin_reload(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    plugin_id = context.args_text.strip()
    if not plugin_id:
        count = 0
        for plugin in pm.list_plugins():
            if plugin.status == "enabled":
                if pm.reload_plugin(plugin.manifest.id):
                    count += 1
        return CommandResult(
            success=True,
            message=f"已重载 {count} 个已启用的插件",
            payload={"_suppress_result_panel": True},
        )
    if pm.reload_plugin(plugin_id):
        return CommandResult(
            success=True,
            message=f"插件已重载: {plugin_id}",
            payload={"_suppress_result_panel": True},
        )
    return CommandResult(success=False, message=f"重载失败: {plugin_id}", error="重载错误")


def cmd_plugin_new(context: CommandContext) -> CommandResult:
    pm = _get_plugin_manager()
    if pm is None:
        return CommandResult(success=False, message="插件管理器未初始化", error="不可用")
    plugin_id = context.args_text.strip()
    if not plugin_id:
        return CommandResult(success=False, message="请指定插件 ID", error="缺少输入")
    safe = "".join(char for char in plugin_id if char.isalnum() or char in "-_")
    if safe != plugin_id:
        return CommandResult(success=False, message="插件 ID 只能包含字母、数字、短横线和下划线", error="格式错误")

    plugin_dir = os.path.join(pm.plugins_dir, plugin_id)
    if os.path.exists(plugin_dir):
        return CommandResult(success=False, message=f"插件目录已存在: {plugin_dir}", error="已存在")

    from core.plugin_template import write_plugin_template

    write_plugin_template(plugin_dir, plugin_id)
    return CommandResult(success=True, message=f"已创建插件模板: {plugin_dir}\n使用 /plugin reload {plugin_id} 加载")
