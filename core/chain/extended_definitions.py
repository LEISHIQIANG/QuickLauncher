"""Extended processor definitions for action chain.

This module provides definitions for extended processors covering:
- Date/Time operations
- Encoding/Decoding
- System information
- Network utilities
- Data validation
- Encryption/Hashing
- Color processing
- Set/Dictionary operations
- String formatting
- Data compression
- Environment variables
- Extended math
"""

from __future__ import annotations

from .definitions import (
    ChainProcessorDefinition,
    ChainPortDefinition,
    ChainParamDefinition,
    ChainProcessorSafety,
    ChainProcessorExample,
)

__all__ = [
    "EXTENDED_PROCESSOR_DEFINITIONS",
    "get_extended_definitions",
]

# ── Port Constants ───────────────────────────────────────────────────────────

TEXT_OUTPUTS = ["output", "length", "empty"]
BOOL_OUTPUTS = ["output", "not"]
LIST_OUTPUTS = ["output", "count", "first", "last", "items_json"]
NUMBER_OUTPUTS = ["output"]
FILE_OUTPUTS = ["output", "path", "folder", "filename", "exists"]
JSON_OUTPUTS = ["output"]

# ── Extended Processor Definitions ───────────────────────────────────────────

EXTENDED_PROCESSOR_DEFINITIONS: dict[str, ChainProcessorDefinition] = {
    # ── Date/Time Processors ──
    "datetime_now": ChainProcessorDefinition(
        "datetime_now",
        "当前时间",
        ["format"],
        TEXT_OUTPUTS,
        category="日期时间",
        description="获取当前日期时间。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_format": ChainProcessorDefinition(
        "datetime_format",
        "时间格式化",
        ["datetime", "format"],
        TEXT_OUTPUTS,
        category="日期时间",
        description="格式化日期时间字符串。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_parse": ChainProcessorDefinition(
        "datetime_parse",
        "时间解析",
        ["datetime", "format"],
        JSON_OUTPUTS,
        category="日期时间",
        description="解析日期时间字符串为组件。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_add": ChainProcessorDefinition(
        "datetime_add",
        "时间加减",
        ["datetime", "days", "hours", "minutes", "seconds", "format"],
        TEXT_OUTPUTS,
        category="日期时间",
        description="对日期时间进行加减运算。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_diff": ChainProcessorDefinition(
        "datetime_diff",
        "时间差计算",
        ["datetime1", "datetime2", "unit"],
        NUMBER_OUTPUTS,
        category="日期时间",
        description="计算两个日期时间之间的差值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_part": ChainProcessorDefinition(
        "datetime_part",
        "时间提取",
        ["datetime", "part", "format"],
        NUMBER_OUTPUTS,
        category="日期时间",
        description="从日期时间中提取指定部分。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "timestamp_now": ChainProcessorDefinition(
        "timestamp_now",
        "当前时间戳",
        [],
        NUMBER_OUTPUTS,
        category="日期时间",
        description="获取当前时间戳。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "timestamp_to_datetime": ChainProcessorDefinition(
        "timestamp_to_datetime",
        "时间戳转时间",
        ["timestamp", "format"],
        TEXT_OUTPUTS,
        category="日期时间",
        description="将时间戳转换为日期时间字符串。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "datetime_to_timestamp": ChainProcessorDefinition(
        "datetime_to_timestamp",
        "时间转时间戳",
        ["datetime", "format"],
        NUMBER_OUTPUTS,
        category="日期时间",
        description="将日期时间字符串转换为时间戳。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Encoding/Decoding Processors ──
    "base64_encode": ChainProcessorDefinition(
        "base64_encode",
        "Base64编码",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="将文本编码为Base64。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "base64_decode": ChainProcessorDefinition(
        "base64_decode",
        "Base64解码",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="将Base64解码为文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "url_encode": ChainProcessorDefinition(
        "url_encode",
        "URL编码",
        ["text"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="URL编码文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "url_decode": ChainProcessorDefinition(
        "url_decode",
        "URL解码",
        ["text"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="URL解码文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "html_encode": ChainProcessorDefinition(
        "html_encode",
        "HTML编码",
        ["text"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="HTML编码文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "html_decode": ChainProcessorDefinition(
        "html_decode",
        "HTML解码",
        ["text"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="HTML解码文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hex_encode": ChainProcessorDefinition(
        "hex_encode",
        "十六进制编码",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="将文本编码为十六进制。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hex_decode": ChainProcessorDefinition(
        "hex_decode",
        "十六进制解码",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="编码解码",
        description="将十六进制解码为文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── System Info Processors ──
    "sys_platform": ChainProcessorDefinition(
        "sys_platform",
        "系统平台",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取操作系统平台。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_version": ChainProcessorDefinition(
        "sys_version",
        "Python版本",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取Python版本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_hostname": ChainProcessorDefinition(
        "sys_hostname",
        "主机名",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取系统主机名。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_username": ChainProcessorDefinition(
        "sys_username",
        "用户名",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取当前用户名。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_cpu_count": ChainProcessorDefinition(
        "sys_cpu_count",
        "CPU数量",
        [],
        NUMBER_OUTPUTS,
        category="系统信息",
        description="获取CPU核心数。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_current_dir": ChainProcessorDefinition(
        "sys_current_dir",
        "当前目录",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取当前工作目录。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_home_dir": ChainProcessorDefinition(
        "sys_home_dir",
        "用户目录",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取用户主目录。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "sys_temp_dir": ChainProcessorDefinition(
        "sys_temp_dir",
        "临时目录",
        [],
        TEXT_OUTPUTS,
        category="系统信息",
        description="获取临时目录。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Network Processors ──
    "net_ip_address": ChainProcessorDefinition(
        "net_ip_address",
        "IP地址",
        ["hostname"],
        TEXT_OUTPUTS,
        category="网络工具",
        description="获取主机IP地址。",
        safety=ChainProcessorSafety("safe", network=True),
    ),
    
    "net_ping": ChainProcessorDefinition(
        "net_ping",
        "Ping测试",
        ["host", "timeout"],
        BOOL_OUTPUTS,
        category="网络工具",
        description="Ping测试主机是否可达。",
        safety=ChainProcessorSafety("safe", network=True),
    ),
    
    "net_port_check": ChainProcessorDefinition(
        "net_port_check",
        "端口检查",
        ["host", "port", "timeout"],
        BOOL_OUTPUTS,
        category="网络工具",
        description="检查端口是否开放。",
        safety=ChainProcessorSafety("safe", network=True),
    ),
    
    "net_url_parse": ChainProcessorDefinition(
        "net_url_parse",
        "URL解析",
        ["url"],
        JSON_OUTPUTS,
        category="网络工具",
        description="解析URL为组件。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Validation Processors ──
    "validate_email": ChainProcessorDefinition(
        "validate_email",
        "邮箱验证",
        ["email"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证邮箱地址格式。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_url": ChainProcessorDefinition(
        "validate_url",
        "URL验证",
        ["url"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证URL格式。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_ip": ChainProcessorDefinition(
        "validate_ip",
        "IP验证",
        ["ip"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证IP地址格式。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_phone": ChainProcessorDefinition(
        "validate_phone",
        "手机号验证",
        ["phone", "country"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证手机号码格式。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_regex": ChainProcessorDefinition(
        "validate_regex",
        "正则验证",
        ["text", "pattern"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="使用正则表达式验证文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_range": ChainProcessorDefinition(
        "validate_range",
        "范围验证",
        ["value", "min", "max"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证值是否在范围内。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "validate_length": ChainProcessorDefinition(
        "validate_length",
        "长度验证",
        ["text", "min", "max"],
        BOOL_OUTPUTS,
        category="数据验证",
        description="验证文本长度。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Hash Processors ──
    "hash_md5": ChainProcessorDefinition(
        "hash_md5",
        "MD5哈希",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="计算MD5哈希值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hash_sha1": ChainProcessorDefinition(
        "hash_sha1",
        "SHA1哈希",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="计算SHA1哈希值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hash_sha256": ChainProcessorDefinition(
        "hash_sha256",
        "SHA256哈希",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="计算SHA256哈希值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hash_sha512": ChainProcessorDefinition(
        "hash_sha512",
        "SHA512哈希",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="计算SHA512哈希值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hash_crc32": ChainProcessorDefinition(
        "hash_crc32",
        "CRC32校验",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="计算CRC32校验值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "hash_uuid": ChainProcessorDefinition(
        "hash_uuid",
        "UUID生成",
        [],
        TEXT_OUTPUTS,
        category="加密哈希",
        description="生成UUID。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Color Processors ──
    "color_hex_to_rgb": ChainProcessorDefinition(
        "color_hex_to_rgb",
        "十六进制转RGB",
        ["hex"],
        TEXT_OUTPUTS,
        category="颜色处理",
        description="将十六进制颜色转换为RGB。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "color_rgb_to_hex": ChainProcessorDefinition(
        "color_rgb_to_hex",
        "RGB转十六进制",
        ["r", "g", "b"],
        TEXT_OUTPUTS,
        category="颜色处理",
        description="将RGB转换为十六进制颜色。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "color_brightness": ChainProcessorDefinition(
        "color_brightness",
        "颜色亮度",
        ["hex"],
        NUMBER_OUTPUTS,
        category="颜色处理",
        description="计算颜色亮度。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "color_complementary": ChainProcessorDefinition(
        "color_complementary",
        "互补色",
        ["hex"],
        TEXT_OUTPUTS,
        category="颜色处理",
        description="获取互补色。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "color_random": ChainProcessorDefinition(
        "color_random",
        "随机颜色",
        [],
        TEXT_OUTPUTS,
        category="颜色处理",
        description="生成随机颜色。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Set Operations ──
    "set_union": ChainProcessorDefinition(
        "set_union",
        "集合并集",
        ["set1", "set2"],
        LIST_OUTPUTS,
        category="集合操作",
        description="计算两个集合的并集。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "set_intersection": ChainProcessorDefinition(
        "set_intersection",
        "集合交集",
        ["set1", "set2"],
        LIST_OUTPUTS,
        category="集合操作",
        description="计算两个集合的交集。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "set_difference": ChainProcessorDefinition(
        "set_difference",
        "集合差集",
        ["set1", "set2"],
        LIST_OUTPUTS,
        category="集合操作",
        description="计算两个集合的差集。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "set_unique": ChainProcessorDefinition(
        "set_unique",
        "列表去重",
        ["list"],
        LIST_OUTPUTS,
        category="集合操作",
        description="去除列表中的重复元素。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Dictionary Operations ──
    "dict_keys": ChainProcessorDefinition(
        "dict_keys",
        "字典键列表",
        ["json"],
        LIST_OUTPUTS,
        category="字典操作",
        description="获取字典的所有键。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "dict_values": ChainProcessorDefinition(
        "dict_values",
        "字典值列表",
        ["json"],
        LIST_OUTPUTS,
        category="字典操作",
        description="获取字典的所有值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "dict_merge": ChainProcessorDefinition(
        "dict_merge",
        "字典合并",
        ["a", "b", "c"],
        JSON_OUTPUTS,
        category="字典操作",
        description="合并多个字典。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "dict_get": ChainProcessorDefinition(
        "dict_get",
        "字典取值",
        ["json", "key", "default"],
        TEXT_OUTPUTS,
        category="字典操作",
        description="从字典中获取值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "dict_set": ChainProcessorDefinition(
        "dict_set",
        "字典设值",
        ["json", "key", "value"],
        JSON_OUTPUTS,
        category="字典操作",
        description="设置字典中的值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "dict_filter": ChainProcessorDefinition(
        "dict_filter",
        "字典过滤",
        ["json", "keys"],
        JSON_OUTPUTS,
        category="字典操作",
        description="过滤字典保留指定键。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── String Formatting ──
    "str_format": ChainProcessorDefinition(
        "str_format",
        "字符串格式化",
        ["template", "args"],
        TEXT_OUTPUTS,
        category="字符串格式化",
        description="格式化字符串。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "str_pad_left": ChainProcessorDefinition(
        "str_pad_left",
        "左填充",
        ["text", "width", "fillchar"],
        TEXT_OUTPUTS,
        category="字符串格式化",
        description="在字符串左侧填充字符。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "str_pad_right": ChainProcessorDefinition(
        "str_pad_right",
        "右填充",
        ["text", "width", "fillchar"],
        TEXT_OUTPUTS,
        category="字符串格式化",
        description="在字符串右侧填充字符。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "str_truncate": ChainProcessorDefinition(
        "str_truncate",
        "字符串截断",
        ["text", "max_length", "suffix"],
        TEXT_OUTPUTS,
        category="字符串格式化",
        description="截断字符串到指定长度。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "str_repeat": ChainProcessorDefinition(
        "str_repeat",
        "字符串重复",
        ["text", "count"],
        TEXT_OUTPUTS,
        category="字符串格式化",
        description="重复字符串指定次数。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Compression Processors ──
    "compress_gzip": ChainProcessorDefinition(
        "compress_gzip",
        "Gzip压缩",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="数据压缩",
        description="使用Gzip压缩数据。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "decompress_gzip": ChainProcessorDefinition(
        "decompress_gzip",
        "Gzip解压",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="数据压缩",
        description="解压Gzip数据。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "compress_zlib": ChainProcessorDefinition(
        "compress_zlib",
        "Zlib压缩",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="数据压缩",
        description="使用Zlib压缩数据。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "decompress_zlib": ChainProcessorDefinition(
        "decompress_zlib",
        "Zlib解压",
        ["text", "encoding"],
        TEXT_OUTPUTS,
        category="数据压缩",
        description="解压Zlib数据。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Environment Processors ──
    "env_get": ChainProcessorDefinition(
        "env_get",
        "环境变量",
        ["key", "default"],
        TEXT_OUTPUTS,
        category="环境变量",
        description="获取环境变量值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "env_set": ChainProcessorDefinition(
        "env_set",
        "设置环境变量",
        ["key", "value"],
        TEXT_OUTPUTS,
        category="环境变量",
        description="设置环境变量。",
        safety=ChainProcessorSafety("caution"),
    ),
    
    "env_list": ChainProcessorDefinition(
        "env_list",
        "环境变量列表",
        [],
        JSON_OUTPUTS,
        category="环境变量",
        description="列出所有环境变量。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "env_expand": ChainProcessorDefinition(
        "env_expand",
        "变量展开",
        ["text"],
        TEXT_OUTPUTS,
        category="环境变量",
        description="展开文本中的环境变量。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    # ── Math Extended ──
    "math_sin": ChainProcessorDefinition(
        "math_sin",
        "正弦函数",
        ["angle"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算角度的正弦值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_cos": ChainProcessorDefinition(
        "math_cos",
        "余弦函数",
        ["angle"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算角度的余弦值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_tan": ChainProcessorDefinition(
        "math_tan",
        "正切函数",
        ["angle"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算角度的正切值。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_sqrt": ChainProcessorDefinition(
        "math_sqrt",
        "平方根",
        ["number"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算平方根。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_log": ChainProcessorDefinition(
        "math_log",
        "对数函数",
        ["number", "base"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算对数。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_factorial": ChainProcessorDefinition(
        "math_factorial",
        "阶乘",
        ["number"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算阶乘。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_gcd": ChainProcessorDefinition(
        "math_gcd",
        "最大公约数",
        ["a", "b"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算最大公约数。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_lcm": ChainProcessorDefinition(
        "math_lcm",
        "最小公倍数",
        ["a", "b"],
        NUMBER_OUTPUTS,
        category="数学扩展",
        description="计算最小公倍数。",
        safety=ChainProcessorSafety("safe"),
    ),
    
    "math_fibonacci": ChainProcessorDefinition(
        "math_fibonacci",
        "斐波那契数列",
        ["count"],
        LIST_OUTPUTS,
        category="数学扩展",
        description="生成斐波那契数列。",
        safety=ChainProcessorSafety("safe"),
    ),
}


def get_extended_definitions() -> dict[str, ChainProcessorDefinition]:
    """Get all extended processor definitions."""
    return dict(EXTENDED_PROCESSOR_DEFINITIONS)
