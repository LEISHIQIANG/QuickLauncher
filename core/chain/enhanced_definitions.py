"""Enhanced processor definitions for action chain.

This module provides definitions for new processors that extend the action chain system.
"""

from __future__ import annotations

from .definitions import (
    ChainProcessorDefinition,
    ChainProcessorSafety,
)

__all__ = [
    "ENHANCED_PROCESSOR_DEFINITIONS",
    "get_enhanced_definitions",
]

# ── Port Constants ───────────────────────────────────────────────────────────

TEXT_OUTPUTS = ["output", "length", "empty"]
BOOL_OUTPUTS = ["output", "not"]
LIST_OUTPUTS = ["output", "count", "first", "last", "items_json"]
NUMBER_OUTPUTS = ["output"]
FILE_OUTPUTS = ["output", "path", "folder", "filename", "exists"]
FOLDER_OUTPUTS = ["output", "path", "exists"]
JSON_OUTPUTS = ["output"]

# ── Enhanced Processor Definitions ───────────────────────────────────────────

ENHANCED_PROCESSOR_DEFINITIONS: dict[str, ChainProcessorDefinition] = {
    # ── Text Processing (Extended) ──
    "text_trim": ChainProcessorDefinition(
        "text_trim",
        "文本修剪",
        ["text", "chars"],
        TEXT_OUTPUTS,
        category="文本",
        description="移除文本两端的空白字符或指定字符。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_contains": ChainProcessorDefinition(
        "text_contains",
        "文本包含",
        ["text", "substring", "case_sensitive"],
        BOOL_OUTPUTS,
        category="文本",
        description="检查文本是否包含指定子串。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_startswith": ChainProcessorDefinition(
        "text_startswith",
        "文本开头",
        ["text", "prefix", "case_sensitive"],
        BOOL_OUTPUTS,
        category="文本",
        description="检查文本是否以指定前缀开头。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_endswith": ChainProcessorDefinition(
        "text_endswith",
        "文本结尾",
        ["text", "suffix", "case_sensitive"],
        BOOL_OUTPUTS,
        category="文本",
        description="检查文本是否以指定后缀结尾。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_regex_replace": ChainProcessorDefinition(
        "text_regex_replace",
        "正则替换",
        ["text", "pattern", "replacement", "count"],
        TEXT_OUTPUTS,
        category="文本",
        description="使用正则表达式替换文本。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_count": ChainProcessorDefinition(
        "text_count",
        "文本计数",
        ["text", "substring", "case_sensitive"],
        NUMBER_OUTPUTS,
        category="文本",
        description="计算子串在文本中出现的次数。",
        safety=ChainProcessorSafety("safe"),
    ),
    "text_reverse": ChainProcessorDefinition(
        "text_reverse",
        "文本反转",
        ["text"],
        TEXT_OUTPUTS,
        category="文本",
        description="反转文本内容。",
        safety=ChainProcessorSafety("safe"),
    ),
    # ── Logic Control (Extended) ──
    "switch_case": ChainProcessorDefinition(
        "switch_case",
        "条件分支",
        ["value", "cases_json", "default"],
        TEXT_OUTPUTS,
        category="逻辑",
        description="根据值选择不同的输出。",
        safety=ChainProcessorSafety("safe"),
    ),
    "try_catch": ChainProcessorDefinition(
        "try_catch",
        "错误捕获",
        ["input", "default"],
        ["output", "success", "error"],
        category="逻辑",
        description="捕获执行错误并返回默认值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "assert_type": ChainProcessorDefinition(
        "assert_type",
        "类型断言",
        ["value", "type"],
        BOOL_OUTPUTS,
        category="逻辑",
        description="断言值是否为指定类型。",
        safety=ChainProcessorSafety("safe"),
    ),
    "is_empty": ChainProcessorDefinition(
        "is_empty",
        "检查空值",
        ["value"],
        BOOL_OUTPUTS,
        category="逻辑",
        description="检查值是否为空。",
        safety=ChainProcessorSafety("safe"),
    ),
    "is_numeric": ChainProcessorDefinition(
        "is_numeric",
        "检查数字",
        ["text"],
        BOOL_OUTPUTS,
        category="逻辑",
        description="检查文本是否为数字。",
        safety=ChainProcessorSafety("safe"),
    ),
    "is_json": ChainProcessorDefinition(
        "is_json",
        "检查JSON",
        ["text"],
        BOOL_OUTPUTS,
        category="逻辑",
        description="检查文本是否为有效的JSON。",
        safety=ChainProcessorSafety("safe"),
    ),
    # ── Math (Extended) ──
    "math_abs": ChainProcessorDefinition(
        "math_abs",
        "绝对值",
        ["number"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="计算数字的绝对值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "math_ceil": ChainProcessorDefinition(
        "math_ceil",
        "向上取整",
        ["number"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="向上取整到最接近的整数。",
        safety=ChainProcessorSafety("safe"),
    ),
    "math_floor": ChainProcessorDefinition(
        "math_floor",
        "向下取整",
        ["number"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="向下取整到最接近的整数。",
        safety=ChainProcessorSafety("safe"),
    ),
    "math_round": ChainProcessorDefinition(
        "math_round",
        "四舍五入",
        ["number", "decimals"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="四舍五入到指定小数位。",
        safety=ChainProcessorSafety("safe"),
    ),
    "math_clamp": ChainProcessorDefinition(
        "math_clamp",
        "数值限制",
        ["number", "min", "max"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="将数值限制在指定范围内。",
        safety=ChainProcessorSafety("safe"),
    ),
    # ── List (Extended) ──
    "list_count": ChainProcessorDefinition(
        "list_count",
        "列表计数",
        ["list", "value"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="计算值在列表中出现的次数。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_sum": ChainProcessorDefinition(
        "list_sum",
        "列表求和",
        ["list"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="计算列表中所有数值的和。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_min": ChainProcessorDefinition(
        "list_min",
        "列表最小值",
        ["list"],
        TEXT_OUTPUTS,
        category="数学与列表",
        description="找到列表中的最小值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_max": ChainProcessorDefinition(
        "list_max",
        "列表最大值",
        ["list"],
        TEXT_OUTPUTS,
        category="数学与列表",
        description="找到列表中的最大值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_avg": ChainProcessorDefinition(
        "list_avg",
        "列表平均值",
        ["list"],
        NUMBER_OUTPUTS,
        category="数学与列表",
        description="计算列表中数值的平均值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_find": ChainProcessorDefinition(
        "list_find",
        "列表查找",
        ["list", "value"],
        TEXT_OUTPUTS,
        category="数学与列表",
        description="在列表中查找指定值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "list_remove": ChainProcessorDefinition(
        "list_remove",
        "列表移除",
        ["list", "value"],
        LIST_OUTPUTS,
        category="数学与列表",
        description="从列表中移除指定值。",
        safety=ChainProcessorSafety("safe"),
    ),
    # ── File Operations (Extended) ──
    "file_copy": ChainProcessorDefinition(
        "file_copy",
        "文件复制",
        ["src", "dst", "overwrite"],
        FILE_OUTPUTS,
        category="文件与路径",
        description="复制文件到目标位置。",
        safety=ChainProcessorSafety("caution", reads_files=True, writes_files=True),
    ),
    "file_move": ChainProcessorDefinition(
        "file_move",
        "文件移动",
        ["src", "dst", "overwrite"],
        FILE_OUTPUTS,
        category="文件与路径",
        description="移动文件到目标位置。",
        safety=ChainProcessorSafety("dangerous", reads_files=True, writes_files=True, requires_confirmation=True),
    ),
    "file_delete": ChainProcessorDefinition(
        "file_delete",
        "文件删除",
        ["path", "to_trash"],
        BOOL_OUTPUTS,
        category="文件与路径",
        description="删除文件（可选择移到回收站）。",
        safety=ChainProcessorSafety("dangerous", writes_files=True, requires_confirmation=True),
    ),
    "file_size": ChainProcessorDefinition(
        "file_size",
        "文件大小",
        ["path"],
        NUMBER_OUTPUTS,
        category="文件与路径",
        description="获取文件大小（字节）。",
        safety=ChainProcessorSafety("safe", reads_files=True),
    ),
    "file_modified": ChainProcessorDefinition(
        "file_modified",
        "修改时间",
        ["path"],
        NUMBER_OUTPUTS,
        category="文件与路径",
        description="获取文件最后修改时间。",
        safety=ChainProcessorSafety("safe", reads_files=True),
    ),
    "file_list_dir": ChainProcessorDefinition(
        "file_list_dir",
        "目录列表",
        ["path", "pattern", "recursive"],
        LIST_OUTPUTS,
        category="文件与路径",
        description="列出目录中的文件。",
        safety=ChainProcessorSafety("safe", reads_files=True),
    ),
    # ── JSON Operations (Extended) ──
    "json_merge": ChainProcessorDefinition(
        "json_merge",
        "JSON合并",
        ["a", "b", "c"],
        JSON_OUTPUTS,
        category="网络与结构化",
        description="合并多个JSON对象。",
        safety=ChainProcessorSafety("safe"),
    ),
    "json_flatten": ChainProcessorDefinition(
        "json_flatten",
        "JSON扁平化",
        ["json", "separator"],
        JSON_OUTPUTS,
        category="网络与结构化",
        description="将嵌套的JSON对象扁平化。",
        safety=ChainProcessorSafety("safe"),
    ),
    "json_keys": ChainProcessorDefinition(
        "json_keys",
        "JSON键列表",
        ["json"],
        LIST_OUTPUTS,
        category="网络与结构化",
        description="获取JSON对象的所有键。",
        safety=ChainProcessorSafety("safe"),
    ),
    "json_values": ChainProcessorDefinition(
        "json_values",
        "JSON值列表",
        ["json"],
        LIST_OUTPUTS,
        category="网络与结构化",
        description="获取JSON对象的所有值。",
        safety=ChainProcessorSafety("safe"),
    ),
    "json_length": ChainProcessorDefinition(
        "json_length",
        "JSON长度",
        ["json"],
        NUMBER_OUTPUTS,
        category="网络与结构化",
        description="获取JSON对象/数组的长度。",
        safety=ChainProcessorSafety("safe"),
    ),
    "json_to_csv": ChainProcessorDefinition(
        "json_to_csv",
        "JSON转CSV",
        ["json", "delimiter"],
        TEXT_OUTPUTS,
        category="网络与结构化",
        description="将JSON数组转换为CSV格式。",
        safety=ChainProcessorSafety("safe"),
    ),
}


def get_enhanced_definitions() -> dict[str, ChainProcessorDefinition]:
    """Get all enhanced processor definitions."""
    return dict(ENHANCED_PROCESSOR_DEFINITIONS)
