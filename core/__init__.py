"""核心模块"""

from .version import APP_VERSION as APP_VERSION

from .data_manager import DataManager as DataManager
from .data_models import DEFAULT_SPECIAL_APPS as DEFAULT_SPECIAL_APPS  # 添加这个
from .data_models import AppData as AppData
from .data_models import AppSettings as AppSettings
from .data_models import Folder as Folder
from .data_models import ShortcutItem as ShortcutItem
from .data_models import ShortcutType as ShortcutType

# 可选模块
try:
    from .icon_extractor import IconExtractor
except ImportError:
    IconExtractor = None

try:
    from .shortcut_parser import ShortcutParser
except ImportError:
    ShortcutParser = None

try:
    from .shortcut_executor import ShortcutExecutor
except ImportError:
    ShortcutExecutor = None

try:
    from .window_manager import WindowManager
except ImportError:
    WindowManager = None


# 自启动管理器（优化开机启动速度）
try:
    from . import auto_start_manager
except ImportError:
    auto_start_manager = None


# ============================================================
# 全局回调注册机制
# 用于跨模块通信，解决打包版本中模块导入问题
# ============================================================

# 全局回调存储
_callbacks = {}


def register_callback(name: str, callback):
    """注册全局回调函数

    Args:
        name: 回调名称，如 'show_config_window'
        callback: 回调函数
    """
    _callbacks[name] = callback


def call_callback(name: str, *args, **kwargs):
    """调用已注册的回调函数

    Args:
        name: 回调名称
        *args, **kwargs: 传递给回调函数的参数

    Returns:
        回调函数的返回值，如果回调不存在则返回 None
    """
    import logging

    logger = logging.getLogger(__name__)

    callback = _callbacks.get(name)
    if callback is not None:
        try:
            logger.debug(f"执行回调: {name}")
            result = callback(*args, **kwargs)
            logger.debug(f"回调执行完成: {name}")
            return result
        except Exception as e:
            logger.error(f"回调执行失败 {name}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None
    else:
        logger.warning(f"回调未找到: {name}")
    return None


def has_callback(name: str) -> bool:
    """检查回调是否已注册

    Args:
        name: 回调名称

    Returns:
        bool: 回调是否存在
    """
    return name in _callbacks


# ============================================================
# 命令注册中心 & 全局管理器
# ============================================================

from .command_registry import CommandRegistry

logger = __import__("logging").getLogger(__name__)

registry = CommandRegistry()
_registry_initialized = False

plugin_manager = None
data_manager = None


def ensure_registry_initialized():
    """初始化命令注册中心（只执行一次）。"""
    global _registry_initialized
    if _registry_initialized:
        return
    try:
        _register_builtin_commands()
        c1 = registry.migrate_slash_commands()
        c2 = registry.migrate_builtin_aliases()
        total = registry.count()
        _registry_initialized = True
        logger.info(
            "命令注册中心初始化完成: %d 条命令 (%d 旧, %d 新)",
            total,
            c1 + c2,
            total - c1 - c2,
        )
    except Exception as e:
        logger.warning("命令注册中心初始化失败：%s", e, exc_info=True)


def ensure_plugin_manager_initialized():
    """初始化插件管理器（只执行一次）。"""
    global plugin_manager
    if plugin_manager is not None:
        return
    try:
        from .plugin_manager import PluginManager

        plugin_manager = PluginManager(registry)
        plugin_manager.scan_plugins()
        logger.info("插件管理器初始化完成")
    except Exception as e:
        logger.warning("插件管理器初始化失败: %s", e)


def set_data_manager(dm):
    """设置全局 DataManager 实例。"""
    global data_manager
    data_manager = dm


def _register_builtin_commands():
    """注册所有 Phase 2/3 内置命令到 registry。"""
    from .command_registry import (
        COMMAND_INTERACTION_DIRECT,
        COMMAND_INTERACTION_PANEL,
        CommandDefinition,
    )
    from .commands import (
        cmd_base64,
        cmd_cidr,
        cmd_clean_cache,
        cmd_color,
        cmd_config_repair,
        cmd_conflict,
        cmd_copy_path,
        cmd_dns,
        cmd_explorer,
        cmd_git,
        cmd_hash,
        cmd_hosts,
        cmd_ip,
        cmd_json,
        cmd_jwt,
        cmd_netdiag,
        cmd_path_audit,
        cmd_plugin_list,
        cmd_plugin_new,
        cmd_plugin_reload,
        cmd_port,
        cmd_process,
        cmd_qr,
        cmd_sysreport,
        cmd_timestamp,
        cmd_tls,
        cmd_urlencode,
        cmd_uuid,
        cmd_wifi,
    )

    _builtin_defs = [
        CommandDefinition(
            id="uuid",
            title="UUID",
            aliases=["uuid", "guid"],
            description="生成 UUID / GUID",
            category="developer",
            handler=cmd_uuid,
        ),
        CommandDefinition(
            id="timestamp",
            title="时间戳",
            aliases=["timestamp", "ts", "时间戳"],
            description="当前 Unix 时间戳",
            category="developer",
            handler=cmd_timestamp,
        ),
        CommandDefinition(
            id="base64",
            title="Base64",
            aliases=["base64", "b64"],
            description="Base64 编码 / 解码",
            category="developer",
            handler=cmd_base64,
        ),
        CommandDefinition(
            id="urlencode",
            title="URL 编码",
            aliases=["urlencode", "url", "urldecode"],
            description="URL 编码 / 解码",
            category="developer",
            handler=cmd_urlencode,
        ),
        CommandDefinition(
            id="color",
            title="颜色",
            aliases=["color", "colour", "颜色", "hex"],
            description="颜色代码转换",
            category="developer",
            handler=cmd_color,
        ),
        CommandDefinition(
            id="ip",
            title="IP",
            aliases=["ip", "本机ip", "内网ip", "公网ip", "wanip"],
            description="查询当前内网 IP 与公网 IP",
            category="network",
            handler=cmd_ip,
        ),
        CommandDefinition(
            id="copy-path",
            title="复制路径",
            aliases=["copy-path", "copypath", "复制路径"],
            description="复制当前路径",
            category="system",
            handler=cmd_copy_path,
        ),
        CommandDefinition(
            id="hash",
            title="Hash",
            aliases=["hash", "哈希"],
            description="计算文本哈希",
            category="developer",
            handler=cmd_hash,
        ),
        CommandDefinition(
            id="qr",
            title="二维码",
            aliases=["qr", "qrcode", "二维码"],
            description="生成 QR 二维码",
            category="developer",
            handler=cmd_qr,
        ),
        CommandDefinition(
            id="json",
            title="JSON 工具",
            aliases=["json", "json-format", "jsonfmt", "json美化", "json压缩"],
            description="JSON 格式化、压缩与校验",
            category="developer",
            handler=cmd_json,
        ),
        CommandDefinition(
            id="jwt",
            title="JWT 解码",
            aliases=["jwt", "jwt-decode", "token"],
            description="解码 JWT Header 与 Payload（不验证签名）",
            category="developer",
            handler=cmd_jwt,
        ),
        CommandDefinition(
            id="netdiag",
            title="网络诊断",
            aliases=["netdiag", "net", "网络诊断", "连通性"],
            description="诊断 DNS、TCP 端口与 Ping 延迟",
            category="network",
            handler=cmd_netdiag,
        ),
        CommandDefinition(
            id="cidr",
            title="CIDR 子网计算",
            aliases=["cidr", "subnet", "子网", "网段"],
            description="计算网段、掩码、广播地址与可用地址范围",
            category="network",
            handler=cmd_cidr,
        ),
        CommandDefinition(
            id="tls",
            title="TLS 证书检查",
            aliases=["tls", "cert", "certificate", "ssl", "证书"],
            description="检查域名 TLS 协议、证书颁发者与到期时间",
            category="network",
            handler=cmd_tls,
        ),
        CommandDefinition(
            id="path-audit",
            title="PATH 体检",
            aliases=["path-audit", "path", "env-path", "环境变量", "path体检"],
            description="检查 PATH 失效目录、重复目录和常用命令遮蔽",
            category="developer",
            handler=cmd_path_audit,
        ),
        CommandDefinition(
            id="process",
            title="进程分析",
            aliases=["process", "proc", "ps", "进程"],
            description="查看高占用进程、搜索进程或按 PID 终止",
            category="system",
            handler=cmd_process,
        ),
        CommandDefinition(
            id="sysreport",
            title="系统快照",
            aliases=["sysreport", "sys", "system-report", "系统快照"],
            description="汇总 CPU、内存、磁盘、网络与启动时间",
            category="system",
            handler=cmd_sysreport,
        ),
        CommandDefinition(
            id="plugin-list",
            title="插件列表",
            aliases=["plugin-list", "plugins", "插件列表"],
            description="列出已加载的插件",
            category="plugin",
            handler=cmd_plugin_list,
        ),
        CommandDefinition(
            id="plugin-reload",
            title="重载插件",
            aliases=["plugin-reload", "preload"],
            description="重新加载插件",
            category="plugin",
            handler=cmd_plugin_reload,
        ),
        CommandDefinition(
            id="plugin-new",
            title="新建插件",
            aliases=["plugin-new", "pnew"],
            description="创建插件模板",
            category="plugin",
            handler=cmd_plugin_new,
        ),
        CommandDefinition(
            id="wifi",
            title="Wi-Fi 密码查询",
            aliases=[
                "wifi",
                "wlan",
                "无线密码",
                "Wi-Fi 密码查询",
                "Wi-Fi",
                "wi-fi",
                "wifi密码",
                "wifi密码查询",
            ],
            description="查询已保存的 Wi-Fi 密码",
            category="system",
            handler=cmd_wifi,
        ),
        CommandDefinition(
            id="hosts",
            title="编辑 Hosts 文件",
            aliases=["hosts", "host"],
            description="打开 Hosts 文件进行编辑",
            category="system",
            handler=cmd_hosts,
        ),
        CommandDefinition(
            id="port",
            title="端口占用查询",
            aliases=["port", "端口", "netstat"],
            description="查询端口占用情况",
            category="developer",
            handler=cmd_port,
        ),
        CommandDefinition(
            id="dns",
            title="清理 DNS 缓存",
            aliases=["dns", "flushdns", "清理dns"],
            description="清理 DNS 缓存",
            category="network",
            handler=cmd_dns,
        ),
        CommandDefinition(
            id="clean-cache",
            title="清理缓存",
            aliases=["clean-cache", "cache-clean", "clear-cache", "清理缓存", "缓存清理"],
            description="清理项目目录下未使用的临时缓存",
            category="internal",
            handler=cmd_clean_cache,
        ),
        CommandDefinition(
            id="config-repair",
            title="配置修复",
            aliases=["config-repair", "repair-config", "config-fix", "配置修复", "旧配置修复"],
            description="扫描或修复旧版本配置变量语法",
            category="system",
            handler=cmd_config_repair,
        ),
        CommandDefinition(
            id="explorer",
            title="重启资源管理器",
            aliases=["explorer", "重启资源管理器", "restart-explorer"],
            description="重启 Windows 资源管理器",
            category="system",
            handler=cmd_explorer,
        ),
        CommandDefinition(
            id="conflict",
            title="热键冲突检查",
            aliases=["conflict", "冲突", "hotkey-conflict"],
            description="检查快捷键冲突",
            category="system",
            handler=cmd_conflict,
        ),
        CommandDefinition(
            id="git",
            title="Git",
            aliases=["git", "git-status", "git-pull", "git-checkout"],
            description="Git status/branch/log/diff/fetch/pull/checkout",
            category="developer",
            handler=cmd_git,
            result_window_size="large",
        ),
    ]

    panel_command_ids = {
        "uuid",
        "timestamp",
        "base64",
        "urlencode",
        "color",
        "ip",
        "copy-path",
        "hash",
        "qr",
        "json",
        "jwt",
        "netdiag",
        "cidr",
        "tls",
        "path-audit",
        "process",
        "sysreport",
        "plugin-list",
        "plugin-new",
        "wifi",
        "port",
        "conflict",
        "clean-cache",
        "config-repair",
        "git",
    }

    count = 0
    for cmd_def in _builtin_defs:
        cmd_def.interaction_mode = (
            COMMAND_INTERACTION_PANEL if cmd_def.id in panel_command_ids else COMMAND_INTERACTION_DIRECT
        )
        if registry.register(cmd_def):
            count += 1
    if count:
        logger.info("已注册 %d 个 Phase 2/3 内置命令", count)
