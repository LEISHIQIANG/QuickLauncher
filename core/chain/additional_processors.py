"""Additional processors for action chains.

This module provides additional processors for:
- Control flow (switch, for_each, while)
- Data conversion (to_json, to_list, to_number)
- System operations (clipboard, environment, datetime)
- String operations (pad, trim, substring)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any

from .definitions import (
    ChainProcessorDefinition,
    ChainPortDefinition,
    ChainParamDefinition,
    ChainProcessorSafety,
    ChainProcessorExample,
)

__all__ = [
    "get_additional_processors",
    "register_additional_processors",
]


def get_additional_processors() -> dict[str, ChainProcessorDefinition]:
    """Get all additional processor definitions."""
    processors = {}
    
    # Control flow processors
    processors.update(_get_control_flow_processors())
    
    # Data conversion processors
    processors.update(_get_data_conversion_processors())
    
    # System operation processors
    processors.update(_get_system_processors())
    
    # String operation processors
    processors.update(_get_string_processors())
    
    # Math processors
    processors.update(_get_math_processors())
    
    return processors


def _get_control_flow_processors() -> dict[str, ChainProcessorDefinition]:
    """Get control flow processor definitions."""
    return {
        "switch": ChainProcessorDefinition(
            id="switch",
            title="条件切换",
            inputs=["value", "case1", "case2", "case3", "default"],
            outputs=["output", "matched"],
            category="逻辑",
            description="根据值匹配不同的情况",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "for_each": ChainProcessorDefinition(
            id="for_each",
            title="循环遍历",
            inputs=["list", "template"],
            outputs=["output", "item", "index"],
            category="逻辑",
            description="遍历列表中的每个元素",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "while_loop": ChainProcessorDefinition(
            id="while_loop",
            title="条件循环",
            inputs=["condition", "body", "max_iterations"],
            outputs=["output", "iterations"],
            category="逻辑",
            description="当条件为真时循环执行",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "try_catch": ChainProcessorDefinition(
            id="try_catch",
            title="错误捕获",
            inputs=["input", "fallback"],
            outputs=["output", "error", "success"],
            category="逻辑",
            description="捕获错误并返回备用值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "delay": ChainProcessorDefinition(
            id="delay",
            title="延迟执行",
            inputs=["input", "ms"],
            outputs=["output"],
            category="逻辑",
            description="延迟指定毫秒后继续",
            safety=ChainProcessorSafety(level="safe"),
        ),
    }


def _get_data_conversion_processors() -> dict[str, ChainProcessorDefinition]:
    """Get data conversion processor definitions."""
    return {
        "to_json": ChainProcessorDefinition(
            id="to_json",
            title="转为JSON",
            inputs=["input"],
            outputs=["output"],
            category="数据转换",
            description="将输入转换为JSON格式",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "from_json": ChainProcessorDefinition(
            id="from_json",
            title="解析JSON",
            inputs=["json_str"],
            outputs=["output"],
            category="数据转换",
            description="解析JSON字符串",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "to_list": ChainProcessorDefinition(
            id="to_list",
            title="转为列表",
            inputs=["input", "delimiter"],
            outputs=["output", "count"],
            category="数据转换",
            description="将输入转换为列表",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "to_number": ChainProcessorDefinition(
            id="to_number",
            title="转为数字",
            inputs=["input"],
            outputs=["output"],
            category="数据转换",
            description="将输入转换为数字",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "to_bool": ChainProcessorDefinition(
            id="to_bool",
            title="转为布尔",
            inputs=["input"],
            outputs=["output"],
            category="数据转换",
            description="将输入转换为布尔值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "to_string": ChainProcessorDefinition(
            id="to_string",
            title="转为字符串",
            inputs=["input"],
            outputs=["output"],
            category="数据转换",
            description="将输入转换为字符串",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "flatten": ChainProcessorDefinition(
            id="flatten",
            title="展平列表",
            inputs=["input"],
            outputs=["output", "count"],
            category="数据转换",
            description="展平嵌套列表",
            safety=ChainProcessorSafety(level="safe"),
        ),
    }


def _get_system_processors() -> dict[str, ChainProcessorDefinition]:
    """Get system operation processor definitions."""
    return {
        "clipboard_get": ChainProcessorDefinition(
            id="clipboard_get",
            title="读取剪贴板",
            inputs=[],
            outputs=["output"],
            category="系统",
            description="读取系统剪贴板内容",
            safety=ChainProcessorSafety(level="caution", reads_files=True),
        ),
        "clipboard_set": ChainProcessorDefinition(
            id="clipboard_set",
            title="设置剪贴板",
            inputs=["text"],
            outputs=["output"],
            category="系统",
            description="设置系统剪贴板内容",
            safety=ChainProcessorSafety(level="caution", writes_files=True),
        ),
        "env_get": ChainProcessorDefinition(
            id="env_get",
            title="读取环境变量",
            inputs=["name"],
            outputs=["output"],
            category="系统",
            description="读取系统环境变量",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "datetime_now": ChainProcessorDefinition(
            id="datetime_now",
            title="当前时间",
            inputs=["format"],
            outputs=["output", "timestamp"],
            category="系统",
            description="获取当前日期时间",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "datetime_format": ChainProcessorDefinition(
            id="datetime_format",
            title="格式化时间",
            inputs=["timestamp", "format"],
            outputs=["output"],
            category="系统",
            description="格式化时间戳",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "uuid_generate": ChainProcessorDefinition(
            id="uuid_generate",
            title="生成UUID",
            inputs=[],
            outputs=["output"],
            category="系统",
            description="生成唯一标识符",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "hash_generate": ChainProcessorDefinition(
            id="hash_generate",
            title="计算哈希",
            inputs=["input", "algorithm"],
            outputs=["output"],
            category="系统",
            description="计算输入的哈希值",
            safety=ChainProcessorSafety(level="safe"),
        ),
    }


def _get_string_processors() -> dict[str, ChainProcessorDefinition]:
    """Get string operation processor definitions."""
    return {
        "str_pad": ChainProcessorDefinition(
            id="str_pad",
            title="字符串填充",
            inputs=["text", "length", "char", "direction"],
            outputs=["output"],
            category="文本",
            description="在字符串左侧/右侧填充字符",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_trim": ChainProcessorDefinition(
            id="str_trim",
            title="字符串修剪",
            inputs=["text", "chars"],
            outputs=["output"],
            category="文本",
            description="修剪字符串两端的指定字符",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_repeat": ChainProcessorDefinition(
            id="str_repeat",
            title="字符串重复",
            inputs=["text", "count"],
            outputs=["output"],
            category="文本",
            description="重复字符串指定次数",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_contains": ChainProcessorDefinition(
            id="str_contains",
            title="字符串包含",
            inputs=["text", "substring"],
            outputs=["output"],
            category="文本",
            description="检查字符串是否包含子串",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_starts_with": ChainProcessorDefinition(
            id="str_starts_with",
            title="字符串开头",
            inputs=["text", "prefix"],
            outputs=["output"],
            category="文本",
            description="检查字符串是否以指定前缀开头",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_ends_with": ChainProcessorDefinition(
            id="str_ends_with",
            title="字符串结尾",
            inputs=["text", "suffix"],
            outputs=["output"],
            category="文本",
            description="检查字符串是否以指定后缀结尾",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_count": ChainProcessorDefinition(
            id="str_count",
            title="子串计数",
            inputs=["text", "substring"],
            outputs=["output"],
            category="文本",
            description="计算子串出现的次数",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "str_reverse": ChainProcessorDefinition(
            id="str_reverse",
            title="字符串反转",
            inputs=["text"],
            outputs=["output"],
            category="文本",
            description="反转字符串",
            safety=ChainProcessorSafety(level="safe"),
        ),
    }


def _get_math_processors() -> dict[str, ChainProcessorDefinition]:
    """Get math processor definitions."""
    return {
        "math_abs": ChainProcessorDefinition(
            id="math_abs",
            title="绝对值",
            inputs=["value"],
            outputs=["output"],
            category="数学",
            description="计算数字的绝对值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_round": ChainProcessorDefinition(
            id="math_round",
            title="四舍五入",
            inputs=["value", "decimals"],
            outputs=["output"],
            category="数学",
            description="四舍五入到指定小数位",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_floor": ChainProcessorDefinition(
            id="math_floor",
            title="向下取整",
            inputs=["value"],
            outputs=["output"],
            category="数学",
            description="向下取整",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_ceil": ChainProcessorDefinition(
            id="math_ceil",
            title="向上取整",
            inputs=["value"],
            outputs=["output"],
            category="数学",
            description="向上取整",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_min": ChainProcessorDefinition(
            id="math_min",
            title="最小值",
            inputs=["a", "b"],
            outputs=["output"],
            category="数学",
            description="返回两个数中的较小值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_max": ChainProcessorDefinition(
            id="math_max",
            title="最大值",
            inputs=["a", "b"],
            outputs=["output"],
            category="数学",
            description="返回两个数中的较大值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_clamp": ChainProcessorDefinition(
            id="math_clamp",
            title="数值限制",
            inputs=["value", "min", "max"],
            outputs=["output"],
            category="数学",
            description="将数值限制在指定范围内",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "math_random": ChainProcessorDefinition(
            id="math_random",
            title="随机数",
            inputs=["min", "max"],
            outputs=["output"],
            category="数学",
            description="生成指定范围内的随机数",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "list_sum": ChainProcessorDefinition(
            id="list_sum",
            title="列表求和",
            inputs=["list"],
            outputs=["output"],
            category="数学",
            description="计算列表所有元素的和",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "list_avg": ChainProcessorDefinition(
            id="list_avg",
            title="列表平均值",
            inputs=["list"],
            outputs=["output"],
            category="数学",
            description="计算列表所有元素的平均值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "list_min": ChainProcessorDefinition(
            id="list_min",
            title="列表最小值",
            inputs=["list"],
            outputs=["output"],
            category="数学",
            description="返回列表中的最小值",
            safety=ChainProcessorSafety(level="safe"),
        ),
        "list_max": ChainProcessorDefinition(
            id="list_max",
            title="列表最大值",
            inputs=["list"],
            outputs=["output"],
            category="数学",
            description="返回列表中的最大值",
            safety=ChainProcessorSafety(level="safe"),
        ),
    }


def register_additional_processors(registry) -> int:
    """Register all additional processors with the registry.
    
    Args:
        registry: ProcessorRegistry instance
        
    Returns:
        Number of processors registered
    """
    processors = get_additional_processors()
    
    count = 0
    for processor_id, definition in processors.items():
        if registry.register(definition):
            count += 1
    
    return count
