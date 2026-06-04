"""Action chain processor registry.

This module contains the processor registry, including built-in processor
definitions, external processor registration, and processor execution logic.
"""

from __future__ import annotations

import ast
import base64
import datetime
import hashlib
import html
import json
import logging
import os
import re
import shutil
import socket
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from core.command_registry import CommandResult

from .definitions import (
    ChainParamDefinition,
    ChainPortDefinition,
    ChainProcessorDefinition,
    ChainProcessorExample,
    ChainProcessorSafety,
    KNOWN_PROCESSOR_PARAM_KINDS,
    KNOWN_PROCESSOR_PORT_KINDS,
    KNOWN_PROCESSOR_PORT_ROLES,
    KNOWN_PROCESSOR_SAFETY_LEVELS,
)

logger = logging.getLogger(__name__)

ChainProcessorHandler = Callable[[dict[str, Any]], CommandResult | dict[str, Any] | str]

TEXT_OUTPUTS = ["output", "length", "empty"]
BOOL_OUTPUTS = ["output", "not"]
LIST_OUTPUTS = ["output", "count", "first", "last", "items_json"]
NUMBER_OUTPUTS = ["output"]
FILE_OUTPUTS = ["output", "path", "folder", "filename", "exists"]
FOLDER_OUTPUTS = ["output", "path", "exists"]
JSON_OUTPUTS = ["output"]
ANY_OUTPUTS = [ChainPortDefinition("output", label="输出", kind="any", description="任意类型输出。", role="primary")]
HTTP_OUTPUTS = ["output", "status_code", "headers", "length", "empty"]

DEFAULT_PYTHON_CELL_SOURCE = '''TITLE = "脚本电池"
INPUTS = ["input"]
OUTPUTS = ["output"]

def process(inputs):
    value = inputs.get("input", "")
    return {"output": value}
'''


def _port_definition(processor_id: str, value: str | ChainPortDefinition, direction: str) -> ChainPortDefinition:
    if isinstance(value, ChainPortDefinition):
        return value
    port_id = str(value or "").strip()
    kind = _early_processor_input_kind(processor_id, port_id) if direction == "input" else _early_processor_output_kind(processor_id, port_id)
    return ChainPortDefinition(
        id=port_id,
        label=_default_port_label(port_id),
        kind=kind,
        required=_port_required(processor_id, port_id, direction),
        multiple=port_id in {"input", "list", "items", "values"},
        default=_port_default(processor_id, port_id),
        description=_port_description(processor_id, port_id, direction),
        role=_port_role(processor_id, port_id, direction),
    )


def _param_definition(processor_id: str, port: ChainPortDefinition) -> ChainParamDefinition:
    choices = _param_choices(processor_id, port.id)
    return ChainParamDefinition(
        id=port.id,
        label=port.label or _default_port_label(port.id),
        kind=_param_kind_from_port(processor_id, port.id, port.kind, choices),
        default=port.default,
        choices=choices,
        multiline=port.id in {"text", "template", "input", "headers", "data", "json", "json_str", "list"},
        required=port.required,
        placeholder=_param_placeholder(port.kind),
        description=port.description,
    )


def _default_example(title: str, params: list[ChainParamDefinition]) -> ChainProcessorExample:
    args = {param.id: param.default for param in params if param.default}
    return ChainProcessorExample(title=f"{title} 示例", args=args)


def _processor_category(processor_id: str) -> str:
    if processor_id in {"python_cell", "panel_node", "logger_node", "sleep_node"}:
        return "输入与调试"
    if processor_id.startswith("text_") or processor_id in {"regex_extract"}:
        return "文本"
    if processor_id.startswith(("bool_", "compare_", "if_", "conditional_", "assert_", "coalesce_", "type_", "loop_")):
        return "逻辑"
    if processor_id.startswith("img_"):
        return "图像"
    if processor_id.startswith("http_") or processor_id.startswith("json_") or processor_id == "url_encode":
        return "网络与结构化"
    if processor_id.startswith(("math_", "series_", "num_", "list_")) or processor_id in {"base_convert", "dec_to_hex", "hex_to_dec"}:
        return "数学与列表"
    if processor_id.startswith(("file_", "folder_", "path_")):
        return "文件与路径"
    return "通用"


def _processor_description(processor_id: str, title: str) -> str:
    descriptions = {
        "python_cell": "执行本地 Python 脚本片段并返回自定义端口输出。",
        "http_get": "向指定 URL 发起 GET 请求并输出响应文本。",
        "http_post": "向指定 URL 提交请求体并输出响应文本。",
        "http_download": "下载 URL 指向的文件到本地目录。",
        "file_read_text": "读取文本文件内容。",
        "file_write_text": "写入或追加文本到本地文件。",
        "folder_create": "创建本地文件夹。",
    }
    return descriptions.get(processor_id, f"{title} 电池。")


def _processor_safety(processor_id: str) -> ChainProcessorSafety:
    if processor_id == "python_cell":
        return ChainProcessorSafety("dangerous", executes_code=True, requires_confirmation=True, capability="chain.script_cell")
    if processor_id in {"http_get", "http_post"}:
        return ChainProcessorSafety("caution", network=True, capability=f"chain.processor.{processor_id}")
    if processor_id == "http_download":
        return ChainProcessorSafety(
            "dangerous",
            writes_files=True,
            network=True,
            requires_confirmation=True,
            capability="chain.processor.http_download",
        )
    if processor_id in {"img_resize", "img_watermark", "img_crop", "img_rotate", "file_write_text", "folder_create"}:
        return ChainProcessorSafety("dangerous", writes_files=True, requires_confirmation=True, capability=f"chain.processor.{processor_id}")
    if processor_id in {"img_convert"}:
        return ChainProcessorSafety("caution", reads_files=True, writes_files=True, capability=f"chain.processor.{processor_id}")
    if processor_id in {"file_read_text"}:
        return ChainProcessorSafety("caution", reads_files=True, capability=f"chain.processor.{processor_id}")
    if processor_id in {"file_path_input", "folder_path_input", "path_exists", "path_split"}:
        return ChainProcessorSafety("safe", reads_files=True, capability=f"chain.processor.{processor_id}")
    return ChainProcessorSafety("safe", capability=f"chain.processor.{processor_id}" if processor_id else "")


def _default_port_label(port: str) -> str:
    labels = {
        "input": "输入",
        "output": "输出",
        "text": "字符串值",
        "template": "模板",
        "path": "路径",
        "filepath": "文件路径",
        "folder": "文件夹",
        "filename": "文件名",
        "url": "URL",
        "headers": "请求头",
        "data": "数据",
        "json": "JSON 数据",
        "json_str": "JSON 字符串",
        "list": "列表",
        "number": "数字",
        "value": "值",
        "mode": "模式",
        "encoding": "编码",
        "ms": "毫秒",
    }
    return labels.get(str(port or ""), str(port or ""))


def _port_required(processor_id: str, port: str, direction: str) -> bool:
    if direction != "input":
        return False
    if processor_id in {"text_input", "num_input", "bool_value"}:
        return False
    return port in {"path", "filepath", "url", "json", "json_str", "text", "list", "a", "b"}


def _port_default(processor_id: str, port: str) -> str:
    defaults = {
        ("sleep_node", "ms"): "1000",
        ("bool_value", "value"): "false",
        ("loop_repeat", "count"): "1",
        ("loop_repeat", "delimiter"): "",
        ("loop_counter", "start"): "1",
        ("loop_counter", "end"): "10",
        ("loop_counter", "step"): "1",
        ("list_slice", "start"): "0",
        ("text_case", "mode"): "upper",
        ("regex_extract", "group"): "0",
        ("num_input", "number"): "0",
        ("math_div", "b"): "1",
        ("math_pow", "exp"): "1",
        ("math_mod", "b"): "1",
        ("series_arith", "start"): "1",
        ("series_arith", "step"): "1",
        ("series_arith", "count"): "10",
        ("series_geom", "start"): "1",
        ("series_geom", "ratio"): "2",
        ("series_geom", "count"): "10",
        ("list_item", "index"): "0",
        ("list_join", "delimiter"): ",",
        ("json_template", "template"): "{output}",
        ("base_convert", "from_base"): "10",
        ("base_convert", "to_base"): "16",
        ("file_read_text", "encoding"): "utf-8",
        ("file_write_text", "encoding"): "utf-8",
        ("file_write_text", "mode"): "overwrite",
        ("img_resize", "width"): "300",
        ("img_resize", "height"): "300",
        ("img_convert", "format"): "png",
        ("img_watermark", "text"): "QuickLauncher",
        ("img_watermark", "position"): "bottom-right",
        ("img_crop", "x"): "0",
        ("img_crop", "y"): "0",
        ("img_crop", "width"): "100",
        ("img_crop", "height"): "100",
        ("img_rotate", "angle"): "90",
    }
    return defaults.get((processor_id, port), "")


def _port_description(processor_id: str, port: str, direction: str) -> str:
    if direction == "output":
        return f"{_default_port_label(port)}输出。"
    if port in {"headers"}:
        return "JSON 对象格式的请求头。"
    if port in {"json", "json_str"}:
        return "JSON 数据。"
    if port in {"path", "filepath"}:
        return "本地文件或文件夹路径。"
    return f"{_default_port_label(port)}输入。"


def _port_role(processor_id: str, port: str, direction: str) -> str:
    port = str(port or "").lower().strip()
    processor_id = str(processor_id or "").strip()
    if direction == "input":
        if port in {"mode", "operator", "delimiter", "encoding", "format", "position", "type", "compare"}:
            return "control"
        if port in {"count", "index", "start", "end", "step", "group", "width", "height", "x", "y", "angle", "ms"}:
            return "parameter"
        return "primary" if port in {"input", "value", "text", "json", "list", "path", "url", "filepath"} else "data"
    if port == "output":
        return "primary"
    if port in {"success", "exists", "empty", "not"}:
        return "status"
    if port in {"error", "stderr"}:
        return "diagnostic"
    if port == "stdout":
        return "stream"
    if port.startswith(("files.", "folders.", "urls.")) or port in {"items_json"}:
        return "collection"
    if port in {
        "length",
        "count",
        "exit_code",
        "status_code",
        "headers",
        "path",
        "folder",
        "filename",
        "stem",
        "extension",
        "first",
        "last",
        "ms",
        "mode",
    }:
        return "metadata"
    return "data"


def _param_choices(processor_id: str, port: str) -> list[str]:
    if processor_id == "text_case" and port == "mode":
        return ["upper", "lower", "title", "trim"]
    if processor_id == "compare_value" and port == "operator":
        return ["等于", "不等于", "大于", "小于", "包含", "不包含"]
    if processor_id == "url_encode" and port == "mode":
        return ["encode", "decode"]
    if processor_id == "list_sort" and port == "mode":
        return ["升序", "降序", "数字", "数字降序"]
    if processor_id == "list_flatten" and port == "mode":
        return ["递归", "一级"]
    if processor_id == "file_write_text" and port == "mode":
        return ["overwrite", "append"]
    if processor_id == "img_convert" and port == "format":
        return ["png", "jpg", "webp", "bmp"]
    if processor_id == "img_watermark" and port == "position":
        return ["bottom-right", "top-left", "center"]
    if processor_id == "type_convert" and port == "type":
        return ["string", "number", "bool", "json", "list"]
    return []


def _param_kind_from_port(processor_id: str, port: str, kind: str, choices: list[str]) -> str:
    if choices:
        return "choice"
    if processor_id.startswith("bool_") or kind == "bool":
        return "bool"
    if kind == "number":
        return "number"
    if kind in {"file", "folder", "json", "list", "url"}:
        return kind
    if port in {"headers", "data"}:
        return "textarea"
    return "textarea" if port in {"text", "template", "input"} else "text"


def _param_placeholder(kind: str) -> str:
    return {
        "json": '{"key":"value"}',
        "list": "每行一项",
        "file": "选择或输入文件路径",
        "folder": "选择或输入文件夹路径",
        "url": "https://example.com",
        "number": "0",
    }.get(kind, "")


def _early_processor_input_kind(processor_id: str, port: str) -> str:
    processor_id = str(processor_id or "")
    port = str(port or "").lower().strip()
    if processor_id.startswith("json_") and port == "path":
        return "text"
    if processor_id in {"folder_path_input", "folder_create"} and port == "path":
        return "folder"
    if port in {"filepath", "path"}:
        return "file"
    if port == "save_dir":
        return "folder"
    if port == "url":
        return "url"
    if port in {"json", "json_str"}:
        return "json"
    if port == "list":
        return "list"
    if processor_id.startswith("bool_") and port in {"value", "a", "b"}:
        return "bool"
    if port == "condition":
        return "bool"
    if port in {"value", "input"}:
        return "any"
    if port in {"width", "height", "x", "y", "start", "end", "step", "index", "count", "ms", "angle", "length", "group", "a", "b", "number", "base", "exp", "from_base", "to_base", "ratio"} and (
        processor_id.startswith(("math_", "series_", "num_"))
        or processor_id in {"base_convert", "dec_to_hex", "hex_to_dec", "loop_counter", "loop_repeat", "text_slice", "regex_extract", "list_slice"}
    ):
        return "number"
    if port in {"width", "height", "x", "y", "index", "ms", "angle"}:
        return "number"
    return "text"


def _early_processor_output_kind(processor_id: str, port: str) -> str:
    processor_id = str(processor_id or "")
    port = str(port or "").lower().strip()
    if port in {"length", "count", "ms", "exit_code", "status_code"}:
        return "number"
    if port in {"empty", "not", "exists", "success"}:
        return "bool"
    if port == "headers" and processor_id.startswith("http_"):
        return "json"
    if port == "folder":
        return "folder"
    if port in {"path", "output"} and processor_id in {"folder_path_input", "folder_create"}:
        return "folder"
    if port == "path":
        return "file"
    if port == "items_json":
        return "list"
    if port in {"first", "last"}:
        return "text"
    if processor_id in {"text_split", "text_lines", "loop_counter", "series_arith", "series_geom"} and port == "output":
        return "list"
    if processor_id.startswith("list_") and processor_id not in {"list_item", "list_len", "list_contains", "list_join"} and port == "output":
        return "list"
    if processor_id in {"text_len", "list_len", "hex_to_dec"} and port == "output":
        return "number"
    if processor_id == "list_contains" and port == "output":
        return "bool"
    if processor_id == "path_exists" and port == "output":
        return "bool"
    if processor_id.startswith(("math_", "num_")) and port == "output":
        return "number"
    if processor_id.startswith("bool_") or processor_id == "compare_value":
        return "bool" if port == "output" else "text"
    if processor_id in {"file_path_input", "path_join", "path_split", "file_write_text", "img_resize", "img_convert", "img_watermark", "img_crop", "img_rotate", "http_download"}:
        return "file" if port in {"output", "path"} else "text"
    if processor_id in {"json_get", "json_parse", "json_set"} and port == "output":
        return "json"
    return "text"


# ── Built-in processor definitions ──────────────────────────────────────────

PROCESSOR_DEFINITIONS: dict[str, ChainProcessorDefinition] = {
    # ── 基本图标 ──
    "python_cell": ChainProcessorDefinition("python_cell", "脚本电池", ["input"], ["output"], DEFAULT_PYTHON_CELL_SOURCE),
    "panel_node": ChainProcessorDefinition("panel_node", "看板", ["input", "text"], TEXT_OUTPUTS),
    "text_input": ChainProcessorDefinition("text_input", "文本输入", ["text"], TEXT_OUTPUTS),
    "assert_not_empty": ChainProcessorDefinition("assert_not_empty", "检查非空", ["text", "message"], TEXT_OUTPUTS),
    "coalesce_value": ChainProcessorDefinition("coalesce_value", "空值兜底", ["value", "fallback"], TEXT_OUTPUTS),
    "type_convert": ChainProcessorDefinition("type_convert", "类型转换", ["value", "type"], TEXT_OUTPUTS),
    "conditional_branch": ChainProcessorDefinition("conditional_branch", "条件分支", ["value", "compare", "target"], TEXT_OUTPUTS),
    "logger_node": ChainProcessorDefinition("logger_node", "日志输出", ["text", "level"], TEXT_OUTPUTS),
    "sleep_node": ChainProcessorDefinition("sleep_node", "等待", ["input", "ms"], TEXT_OUTPUTS + ["ms"]),
    "bool_value": ChainProcessorDefinition("bool_value", "布尔值", ["value"], BOOL_OUTPUTS),
    "bool_not": ChainProcessorDefinition("bool_not", "逻辑非", ["value"], BOOL_OUTPUTS),
    "bool_and": ChainProcessorDefinition("bool_and", "逻辑与", ["a", "b"], BOOL_OUTPUTS),
    "bool_or": ChainProcessorDefinition("bool_or", "逻辑或", ["a", "b"], BOOL_OUTPUTS),
    "bool_xor": ChainProcessorDefinition("bool_xor", "逻辑异或", ["a", "b"], BOOL_OUTPUTS),
    "compare_value": ChainProcessorDefinition("compare_value", "比较判断", ["a", "operator", "b"], BOOL_OUTPUTS),
    "if_else": ChainProcessorDefinition("if_else", "条件选择", ["condition", "true_value", "false_value"], TEXT_OUTPUTS),
    "loop_repeat": ChainProcessorDefinition("loop_repeat", "循环重复", ["input", "count", "delimiter"], TEXT_OUTPUTS),
    "loop_counter": ChainProcessorDefinition("loop_counter", "计数循环", ["start", "end", "step", "delimiter"], LIST_OUTPUTS),

    # ── 文本处理 ──
    "text_template": ChainProcessorDefinition("text_template", "文本模板", ["template", "input", "a", "b", "c"], TEXT_OUTPUTS),
    "text_replace": ChainProcessorDefinition("text_replace", "文本替换", ["text", "find", "replace"], TEXT_OUTPUTS),
    "text_slice": ChainProcessorDefinition("text_slice", "文本裁剪", ["text", "start", "end"], TEXT_OUTPUTS),
    "regex_extract": ChainProcessorDefinition("regex_extract", "正则提取", ["text", "pattern", "group"], TEXT_OUTPUTS),
    "text_case": ChainProcessorDefinition("text_case", "大小写转换", ["text", "mode"], TEXT_OUTPUTS),
    "text_join": ChainProcessorDefinition("text_join", "文本合并", ["delimiter", "a", "b", "c", "d", "e"], TEXT_OUTPUTS),
    "text_len": ChainProcessorDefinition("text_len", "文本长度", ["text"], NUMBER_OUTPUTS),
    "text_split": ChainProcessorDefinition("text_split", "文本拆分", ["text", "delimiter"], LIST_OUTPUTS),
    "text_lines": ChainProcessorDefinition("text_lines", "文本分行", ["text"], LIST_OUTPUTS),

    # ── 图像处理 ──
    "img_resize": ChainProcessorDefinition("img_resize", "图片缩放", ["filepath", "width", "height"], FILE_OUTPUTS),
    "img_convert": ChainProcessorDefinition("img_convert", "图片转换", ["filepath", "format"], FILE_OUTPUTS),
    "img_watermark": ChainProcessorDefinition("img_watermark", "添加水印", ["filepath", "text", "position"], FILE_OUTPUTS),
    "img_crop": ChainProcessorDefinition("img_crop", "图片裁剪", ["filepath", "x", "y", "width", "height"], FILE_OUTPUTS),
    "img_rotate": ChainProcessorDefinition("img_rotate", "图片旋转", ["filepath", "angle"], FILE_OUTPUTS),

    # ── 网络处理 ──
    "json_get": ChainProcessorDefinition("json_get", "取结构化字段", ["json", "path"], ANY_OUTPUTS),
    "json_set": ChainProcessorDefinition("json_set", "设置结构化字段", ["json", "path", "value"], JSON_OUTPUTS),
    "http_get": ChainProcessorDefinition("http_get", "网页请求", ["url", "headers"], HTTP_OUTPUTS),
    "http_post": ChainProcessorDefinition("http_post", "提交请求", ["url", "data", "headers"], HTTP_OUTPUTS),
    "url_encode": ChainProcessorDefinition("url_encode", "网址编解码", ["text", "mode"], TEXT_OUTPUTS),
    "json_parse": ChainProcessorDefinition("json_parse", "结构化文本校验格式化", ["json_str"], JSON_OUTPUTS),
    "json_template": ChainProcessorDefinition("json_template", "结构化模板", ["json", "template"], TEXT_OUTPUTS),
    "http_download": ChainProcessorDefinition("http_download", "文件下载", ["url", "save_dir"], FILE_OUTPUTS),

    # ── 数学与数据结构 ──
    "num_input": ChainProcessorDefinition("num_input", "数字输入", ["number"], NUMBER_OUTPUTS),
    "math_add": ChainProcessorDefinition("math_add", "加法", ["a", "b"], NUMBER_OUTPUTS),
    "math_sub": ChainProcessorDefinition("math_sub", "减法", ["a", "b"], NUMBER_OUTPUTS),
    "math_mul": ChainProcessorDefinition("math_mul", "乘法", ["a", "b"], NUMBER_OUTPUTS),
    "math_div": ChainProcessorDefinition("math_div", "除法", ["a", "b"], NUMBER_OUTPUTS),
    "math_pow": ChainProcessorDefinition("math_pow", "幂运算", ["base", "exp"], NUMBER_OUTPUTS),
    "math_mod": ChainProcessorDefinition("math_mod", "取模", ["a", "b"], NUMBER_OUTPUTS),
    "series_arith": ChainProcessorDefinition("series_arith", "等差数列", ["start", "step", "count"], LIST_OUTPUTS),
    "series_geom": ChainProcessorDefinition("series_geom", "等比数列", ["start", "ratio", "count"], LIST_OUTPUTS),
    "list_create": ChainProcessorDefinition("list_create", "列表创建", ["a", "b", "c", "d", "e"], LIST_OUTPUTS),
    "list_item": ChainProcessorDefinition("list_item", "获取元素", ["list", "index"], TEXT_OUTPUTS),
    "list_len": ChainProcessorDefinition("list_len", "列表长度", ["list"], NUMBER_OUTPUTS),
    "list_rev": ChainProcessorDefinition("list_rev", "反转列表", ["list"], LIST_OUTPUTS),
    "list_unique": ChainProcessorDefinition("list_unique", "列表去重", ["list"], LIST_OUTPUTS),
    "list_sort": ChainProcessorDefinition("list_sort", "列表排序", ["list", "mode"], LIST_OUTPUTS),
    "list_filter": ChainProcessorDefinition("list_filter", "列表筛选", ["list", "contains", "exclude"], LIST_OUTPUTS),
    "list_contains": ChainProcessorDefinition("list_contains", "列表包含", ["list", "value"], BOOL_OUTPUTS),
    "list_template": ChainProcessorDefinition("list_template", "列表套模板", ["list", "template", "delimiter"], LIST_OUTPUTS),
    "list_concat": ChainProcessorDefinition("list_concat", "列表合并", ["a", "b", "c", "delimiter"], LIST_OUTPUTS),
    "list_slice": ChainProcessorDefinition("list_slice", "列表切片", ["list", "start", "end"], LIST_OUTPUTS),
    "list_zip": ChainProcessorDefinition("list_zip", "列表配对", ["a", "b", "template", "delimiter"], LIST_OUTPUTS),
    "list_flatten": ChainProcessorDefinition("list_flatten", "列表展开", ["list", "mode"], LIST_OUTPUTS),
    "list_join": ChainProcessorDefinition("list_join", "列表转文本", ["list", "delimiter"], TEXT_OUTPUTS),
    "base_convert": ChainProcessorDefinition("base_convert", "通用进制转换", ["number", "from_base", "to_base"], TEXT_OUTPUTS),
    "dec_to_hex": ChainProcessorDefinition("dec_to_hex", "十进制转十六进制", ["number"], TEXT_OUTPUTS),
    "hex_to_dec": ChainProcessorDefinition("hex_to_dec", "十六进制转十进制", ["number"], NUMBER_OUTPUTS),

    # ── Windows 文件与路径 ──
    "file_path_input": ChainProcessorDefinition("file_path_input", "文件路径", ["path"], FILE_OUTPUTS),
    "folder_path_input": ChainProcessorDefinition("folder_path_input", "文件夹路径", ["path"], FOLDER_OUTPUTS),
    "path_join": ChainProcessorDefinition("path_join", "路径拼接", ["a", "b", "c"], FILE_OUTPUTS),
    "path_split": ChainProcessorDefinition(
        "path_split",
        "拆分路径",
        ["path"],
        ["output", "folder", "filename", "stem", "extension", "exists"],
    ),
    "path_exists": ChainProcessorDefinition("path_exists", "路径存在", ["path"], BOOL_OUTPUTS + ["path"]),
    "folder_create": ChainProcessorDefinition("folder_create", "创建文件夹", ["path"], FOLDER_OUTPUTS),
    "file_read_text": ChainProcessorDefinition("file_read_text", "读取文本文件", ["path", "encoding"], TEXT_OUTPUTS + ["path", "folder", "filename"]),
    "file_write_text": ChainProcessorDefinition("file_write_text", "写入文本文件", ["path", "text", "encoding", "mode"], FILE_OUTPUTS + ["length"]),
}

EXTERNAL_PROCESSOR_DEFINITIONS: dict[str, ChainProcessorDefinition] = {}
EXTERNAL_PROCESSOR_HANDLERS: dict[str, ChainProcessorHandler] = {}
EXTERNAL_PROCESSOR_OWNERS: dict[str, str] = {}


def processor_definitions() -> list[ChainProcessorDefinition]:
    return list(PROCESSOR_DEFINITIONS.values()) + list(EXTERNAL_PROCESSOR_DEFINITIONS.values())


def processor_definition(processor_id: str) -> ChainProcessorDefinition | None:
    processor_id = str(processor_id or "")
    return PROCESSOR_DEFINITIONS.get(processor_id) or EXTERNAL_PROCESSOR_DEFINITIONS.get(processor_id)


def processor_input_ports(processor_id: str) -> list[str]:
    definition = processor_definition(processor_id)
    return [port.id for port in definition.inputs] if definition else []


def processor_output_ports(processor_id: str) -> list[str]:
    definition = processor_definition(processor_id)
    return [port.id for port in definition.outputs] if definition else ["output"]


def processor_title(processor_id: str) -> str:
    definition = processor_definition(processor_id)
    return definition.title if definition else str(processor_id or "处理节点")


def register_external_processor(
    definition: ChainProcessorDefinition | dict[str, Any],
    handler: ChainProcessorHandler,
    *,
    owner: str,
) -> bool:
    """Register a processor supplied by a plugin or module package."""

    if not callable(handler):
        return False
    try:
        normalized = _normalize_external_processor_definition(definition, owner)
    except Exception:
        logger.debug("外部动作链电池定义无效: %s", definition, exc_info=True)
        return False
    processor_id = normalized.id
    owner = str(owner or "").strip()
    if not owner or not processor_id or processor_id in PROCESSOR_DEFINITIONS:
        return False
    existing_owner = EXTERNAL_PROCESSOR_OWNERS.get(processor_id)
    if existing_owner and existing_owner != owner:
        return False
    EXTERNAL_PROCESSOR_DEFINITIONS[processor_id] = normalized
    EXTERNAL_PROCESSOR_HANDLERS[processor_id] = handler
    EXTERNAL_PROCESSOR_OWNERS[processor_id] = owner
    return True


def unregister_external_processors(owner: str) -> list[str]:
    owner = str(owner or "").strip()
    removed = []
    for processor_id, processor_owner in list(EXTERNAL_PROCESSOR_OWNERS.items()):
        if processor_owner != owner:
            continue
        removed.append(processor_id)
        EXTERNAL_PROCESSOR_OWNERS.pop(processor_id, None)
        EXTERNAL_PROCESSOR_DEFINITIONS.pop(processor_id, None)
        EXTERNAL_PROCESSOR_HANDLERS.pop(processor_id, None)
    return removed


def _normalize_external_processor_definition(
    definition: ChainProcessorDefinition | dict[str, Any],
    owner: str,
) -> ChainProcessorDefinition:
    if isinstance(definition, ChainProcessorDefinition):
        raw_id = definition.id
        raw_title = definition.title
        inputs = definition.inputs
        outputs = definition.outputs
        source = definition.source
        category = definition.category
        description = definition.description
        params = definition.params
        safety = definition.safety
        examples = definition.examples
    elif isinstance(definition, dict):
        raw_id = str(definition.get("id") or "")
        raw_title = str(definition.get("title") or definition.get("name") or raw_id)
        inputs = _external_port_defs(raw_id, definition.get("inputs") or ["input"], "input")
        outputs = _external_port_defs(raw_id, definition.get("outputs") or ["output"], "output")
        source = str(definition.get("source") or "plugin")
        category = str(definition.get("category") or "插件电池")
        description = str(definition.get("description") or f"{raw_title} 插件电池。")
        params = _external_param_defs(raw_id, definition.get("params") or [], inputs)
        safety = _external_safety(definition.get("safety") or {}, raw_id)
        examples = _external_examples(definition.get("examples") or [], raw_title)
    else:
        raise TypeError("definition must be a ChainProcessorDefinition or dict")
    processor_id = _normalize_external_processor_id(str(owner or ""), raw_id)
    normalized = ChainProcessorDefinition(
        processor_id,
        raw_title,
        inputs,
        outputs,
        source,
        category=category or "插件电池",
        description=description,
        params=params,
        safety=safety,
        examples=examples or [ChainProcessorExample(title=f"{raw_title} 示例")],
    )
    _validate_external_processor_definition(normalized)
    return normalized


def _validate_external_processor_definition(definition: ChainProcessorDefinition) -> None:
    if not definition.id:
        raise ValueError("processor id is required")
    if not definition.title:
        raise ValueError("processor title is required")
    if not definition.outputs:
        raise ValueError("processor outputs are required")
    input_ids = [port.id for port in definition.inputs]
    output_ids = [port.id for port in definition.outputs]
    param_ids = [param.id for param in definition.params]
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("processor input ports must be unique")
    if len(output_ids) != len(set(output_ids)):
        raise ValueError("processor output ports must be unique")
    if len(param_ids) != len(set(param_ids)):
        raise ValueError("processor params must be unique")
    if not set(param_ids).issubset(set(input_ids)):
        raise ValueError("processor params must reference input ports")
    for port in [*definition.inputs, *definition.outputs]:
        if port.kind not in KNOWN_PROCESSOR_PORT_KINDS:
            raise ValueError(f"unknown processor port kind: {port.kind}")
        if port.role not in KNOWN_PROCESSOR_PORT_ROLES:
            raise ValueError(f"unknown processor port role: {port.role}")
    for param in definition.params:
        if param.kind not in KNOWN_PROCESSOR_PARAM_KINDS:
            raise ValueError(f"unknown processor param kind: {param.kind}")
    if definition.safety.level not in KNOWN_PROCESSOR_SAFETY_LEVELS:
        raise ValueError(f"unknown processor safety level: {definition.safety.level}")
    if not definition.safety.capability.startswith("chain."):
        raise ValueError("processor safety capability must start with chain.")


def _normalize_external_processor_id(owner: str, processor_id: str) -> str:
    owner = re.sub(r"[^a-zA-Z0-9_]+", "_", str(owner or "").strip()).strip("_")
    processor_id = re.sub(r"[^a-zA-Z0-9_\\.]+", "_", str(processor_id or "").strip()).strip("_")
    if not processor_id:
        raise ValueError("processor id is required")
    if "." in processor_id:
        return processor_id
    if owner and not processor_id.startswith(f"{owner}_"):
        return f"{owner}_{processor_id}"
    return processor_id


def _external_port_defs(processor_id: str, values: Any, direction: str) -> list[ChainPortDefinition]:
    result = []
    for value in list(values or []):
        if isinstance(value, ChainPortDefinition):
            result.append(value)
        elif isinstance(value, dict):
            port_id = str(value.get("id") or value.get("name") or "").strip()
            if not port_id:
                continue
            result.append(
                ChainPortDefinition(
                    id=port_id,
                    label=str(value.get("label") or _default_port_label(port_id)),
                    kind=str(value.get("kind") or value.get("type") or _early_processor_input_kind(processor_id, port_id)),
                    required=bool(value.get("required", False)),
                    multiple=bool(value.get("multiple", False)),
                    default=str(value.get("default") or ""),
                    description=str(value.get("description") or ""),
                    role=str(value.get("role") or _port_role(processor_id, port_id, direction)),
                )
            )
        else:
            result.append(_port_definition(processor_id, str(value or ""), direction))
    return result or [_port_definition(processor_id, "output" if direction == "output" else "input", direction)]


def _external_param_defs(
    processor_id: str,
    values: Any,
    inputs: list[ChainPortDefinition],
) -> list[ChainParamDefinition]:
    if not values:
        return [_param_definition(processor_id, port) for port in inputs]
    result = []
    for value in list(values or []):
        if isinstance(value, ChainParamDefinition):
            result.append(value)
        elif isinstance(value, dict):
            param_id = str(value.get("id") or value.get("name") or "").strip()
            if not param_id:
                continue
            result.append(
                ChainParamDefinition(
                    id=param_id,
                    label=str(value.get("label") or _default_port_label(param_id)),
                    kind=str(value.get("kind") or value.get("type") or "text"),
                    default=str(value.get("default") or ""),
                    choices=[str(item) for item in list(value.get("choices") or [])],
                    multiline=bool(value.get("multiline", False)),
                    required=bool(value.get("required", False)),
                    placeholder=str(value.get("placeholder") or ""),
                    description=str(value.get("description") or value.get("help") or ""),
                )
            )
    return result


def _external_safety(value: Any, processor_id: str) -> ChainProcessorSafety:
    if isinstance(value, ChainProcessorSafety):
        return value
    data = dict(value or {}) if isinstance(value, dict) else {}
    return ChainProcessorSafety(
        level=str(data.get("level") or "safe"),
        reads_files=bool(data.get("reads_files", False)),
        writes_files=bool(data.get("writes_files", False)),
        network=bool(data.get("network", False)),
        executes_code=bool(data.get("executes_code", False)),
        requires_confirmation=bool(data.get("requires_confirmation", False)),
        capability=str(data.get("capability") or f"chain.processor.{processor_id}"),
    )


def _external_examples(value: Any, title: str) -> list[ChainProcessorExample]:
    result = []
    for item in list(value or []):
        if isinstance(item, ChainProcessorExample):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                ChainProcessorExample(
                    title=str(item.get("title") or f"{title} 示例"),
                    args=dict(item.get("args") or {}),
                    expected=dict(item.get("expected") or {}),
                )
            )
    return result


def python_cell_metadata(source: str) -> dict[str, Any]:
    title = "脚本电池"
    inputs = ["input"]
    outputs = ["output"]
    try:
        tree = ast.parse(str(source or DEFAULT_PYTHON_CELL_SOURCE))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if not names:
                continue
            value = ast.literal_eval(node.value)
            if "TITLE" in names and isinstance(value, str) and value.strip():
                title = value.strip()
            elif "INPUTS" in names and isinstance(value, list):
                inputs = _clean_ports(value) or inputs
            elif "OUTPUTS" in names and isinstance(value, list):
                outputs = _clean_ports(value) or outputs
    except (SyntaxError, ValueError):
        pass
    return {"title": title, "inputs": inputs, "outputs": outputs}


def _clean_ports(values: list[Any]) -> list[str]:
    ports = []
    seen = set()
    for value in values:
        port = str(value or "").strip()
        if not port or port in seen:
            continue
        seen.add(port)
        ports.append(port)
    return ports


def execute_chain_processor(processor_id: str, args: dict[str, Any], source: str = "") -> CommandResult:
    processor_id = str(processor_id or "").strip()
    values = {str(k): v for k, v in dict(args or {}).items()}
    try:
        external_handler = EXTERNAL_PROCESSOR_HANDLERS.get(processor_id)
        if external_handler is not None:
            return _normalize_external_processor_result(external_handler(values))
        if processor_id == "python_cell":
            return _execute_python_cell(source or DEFAULT_PYTHON_CELL_SOURCE, values)

        # ── 基本图标 ──
        if processor_id == "panel_node":
            return _panel_node(values)
        if processor_id == "text_input":
            return _text_input(values)
        if processor_id == "assert_not_empty":
            text = _value_to_text(values.get("text", ""))
            if text:
                return _ok(text)
            message = _value_to_text(values.get("message", "")) or "输入为空。"
            return CommandResult(success=False, message=message, display_type="text", error=message)
        if processor_id == "coalesce_value":
            return _ok(_coalesce_value(_string_values(values)))
        if processor_id == "type_convert":
            return _ok(_type_convert(_string_values(values)))
        if processor_id == "conditional_branch":
            return _ok(_conditional_branch(_string_values(values)))
        if processor_id == "logger_node":
            return _ok(_logger_node(_string_values(values)))
        if processor_id == "sleep_node":
            return _sleep_node(_string_values(values))
        if processor_id == "bool_value":
            return _ok_bool(_to_bool(values.get("value", "")))
        if processor_id == "bool_not":
            return _ok_bool(not _to_bool(values.get("value", "")))
        if processor_id == "bool_and":
            return _ok_bool(_to_bool(values.get("a", "")) and _to_bool(values.get("b", "")))
        if processor_id == "bool_or":
            return _ok_bool(_to_bool(values.get("a", "")) or _to_bool(values.get("b", "")))
        if processor_id == "bool_xor":
            left = _to_bool(values.get("a", ""))
            right = _to_bool(values.get("b", ""))
            return _ok_bool((left and not right) or (right and not left))
        if processor_id == "compare_value":
            return _ok_bool(_compare_values(_string_values(values)))
        if processor_id == "if_else":
            text_values = _string_values(values)
            return _ok(text_values.get("true_value", "") if _to_bool(values.get("condition", "")) else text_values.get("false_value", ""))
        if processor_id == "loop_repeat":
            return _ok(_loop_repeat(_string_values(values)))
        if processor_id == "loop_counter":
            return _ok_list(_parse_list(_loop_counter(_string_values(values))))

        # ── 文本处理 ──
        if processor_id == "text_template":
            return _ok(_text_template(_string_values(values)))
        if processor_id == "text_replace":
            text_values = _string_values(values)
            return _ok(text_values.get("text", "").replace(text_values.get("find", ""), text_values.get("replace", "")))
        if processor_id == "text_slice":
            return _ok(_text_slice(_string_values(values)))
        if processor_id == "regex_extract":
            return _ok(_regex_extract(_string_values(values)))
        if processor_id == "text_case":
            return _ok(_text_case(_string_values(values)))
        if processor_id == "text_join":
            return _ok(_text_join(_string_values(values)))
        if processor_id == "text_len":
            return _ok(_text_len(_string_values(values)))
        if processor_id == "text_split":
            return _ok_list(_text_split(_string_values(values)))
        if processor_id == "text_lines":
            return _ok_list(_text_lines(_string_values(values)))

        # ── 图像处理 ──
        if processor_id == "img_resize":
            return _ok_file(_run_img_op(_img_resize, _string_values(values)))
        if processor_id == "img_convert":
            return _ok_file(_run_img_op(_img_convert, _string_values(values)))
        if processor_id == "img_watermark":
            return _ok_file(_run_img_op(_img_watermark, _string_values(values)))
        if processor_id == "img_crop":
            return _ok_file(_run_img_op(_img_crop, _string_values(values)))
        if processor_id == "img_rotate":
            return _ok_file(_run_img_op(_img_rotate, _string_values(values)))

        # ── 网络处理 ──
        if processor_id == "json_get":
            return _ok(_json_get(_string_values(values)))
        if processor_id == "json_set":
            return _ok(_json_set(_string_values(values)))
        if processor_id == "http_get":
            return _http_get(_string_values(values))
        if processor_id == "http_post":
            return _http_post(_string_values(values))
        if processor_id == "url_encode":
            return _ok(_url_encode(_string_values(values)))
        if processor_id == "json_parse":
            return _ok(_json_parse(_string_values(values)))
        if processor_id == "json_template":
            return _ok(_json_template(_string_values(values)))
        if processor_id == "http_download":
            return _ok_file(_http_download(_string_values(values)))

        # ── 数学与数据结构 ──
        if processor_id == "num_input":
            return _ok(_num_input(_string_values(values)))
        if processor_id == "math_add":
            return _ok(_math_add(_string_values(values)))
        if processor_id == "math_sub":
            return _ok(_math_sub(_string_values(values)))
        if processor_id == "math_mul":
            return _ok(_math_mul(_string_values(values)))
        if processor_id == "math_div":
            return _ok(_math_div(_string_values(values)))
        if processor_id == "math_pow":
            return _ok(_math_pow(_string_values(values)))
        if processor_id == "math_mod":
            return _ok(_math_mod(_string_values(values)))
        if processor_id == "series_arith":
            return _ok_list(_parse_list(_series_arith(_string_values(values))))
        if processor_id == "series_geom":
            return _ok_list(_parse_list(_series_geom(_string_values(values))))
        if processor_id == "list_create":
            return _ok_list(_parse_list(_list_create(_string_values(values))))
        if processor_id == "list_item":
            return _ok(_list_item(_string_values(values)))
        if processor_id == "list_len":
            return _ok(_list_len(_string_values(values)))
        if processor_id == "list_rev":
            return _ok_list(_parse_list(_list_rev(_string_values(values))))
        if processor_id == "list_unique":
            return _ok_list(_list_unique_values(_parse_list(values.get("list", ""))))
        if processor_id == "list_sort":
            text_values = _string_values(values)
            return _ok_list(_list_sort_values(_parse_list(values.get("list", "")), text_values.get("mode", "")))
        if processor_id == "list_filter":
            return _ok_list(_list_filter_values(_string_values(values)))
        if processor_id == "list_contains":
            return _ok_bool(_list_contains_value(_string_values(values)))
        if processor_id == "list_template":
            return _ok_list(_list_template_values(_string_values(values)))
        if processor_id == "list_concat":
            return _ok_list(_list_concat_values(_string_values(values)))
        if processor_id == "list_slice":
            return _ok_list(_list_slice_values(_string_values(values)))
        if processor_id == "list_zip":
            return _ok_list(_list_zip_values(_string_values(values)))
        if processor_id == "list_flatten":
            return _ok_list(_list_flatten_values(_string_values(values)))
        if processor_id == "list_join":
            return _ok(_list_join_values(_string_values(values)))
        if processor_id == "base_convert":
            return _ok(_base_convert(_string_values(values)))
        if processor_id == "dec_to_hex":
            return _ok(_dec_to_hex(_string_values(values)))
        if processor_id == "hex_to_dec":
            return _ok(_hex_to_dec(_string_values(values)))
        if processor_id == "file_path_input":
            return _ok_file(_normalize_path_value(_string_values(values).get("path", "")))
        if processor_id == "folder_path_input":
            return _ok_folder(_normalize_path_value(_string_values(values).get("path", "")))
        if processor_id == "path_join":
            return _ok_file(_path_join(_string_values(values)))
        if processor_id == "path_split":
            return _path_split(_string_values(values))
        if processor_id == "path_exists":
            return _path_exists(_string_values(values))
        if processor_id == "folder_create":
            return _folder_create(_string_values(values))
        if processor_id == "file_read_text":
            return _file_read_text(_string_values(values))
        if processor_id == "file_write_text":
            return _file_write_text(_string_values(values))

        # ── 增强电池 (增强文本/逻辑/数学/列表/文件/JSON) ──
        try:
            result = _execute_extra_processor(processor_id, values)
            if result is not None:
                return result
        except Exception as exc:
            return _processor_error_result(processor_id, exc)

    except Exception as exc:
        return _processor_error_result(processor_id, exc)
    return CommandResult(
        success=False,
        message=f"未知处理节点: {processor_id}",
        display_type="text",
        payload={
            "outputs": {"error": "Unknown processor"},
            "diagnostic": {
                "kind": "processor_error",
                "processor_id": processor_id,
                "processor_title": processor_id,
                "error_type": "UnknownProcessor",
                "message": f"未知处理节点: {processor_id}",
            },
        },
        error="Unknown processor",
    )


def _execute_extra_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """处理增强和扩展电池的分发。返回 None 表示不是扩展电池。"""
    text_values = _string_values(values)

    # ── 增强: 文本处理 ──
    if processor_id == "text_trim":
        text = text_values.get("text", "")
        chars = text_values.get("chars", "")
        return _ok(text.strip(chars) if chars else text.strip())
    if processor_id == "text_contains":
        text = text_values.get("text", "")
        sub = text_values.get("substring", "")
        cs = _to_bool(values.get("case_sensitive", True))
        return _ok_bool(sub.lower() in text.lower() if not cs else sub in text)
    if processor_id == "text_startswith":
        text = text_values.get("text", "")
        prefix = text_values.get("prefix", "")
        cs = _to_bool(values.get("case_sensitive", True))
        return _ok_bool(text.lower().startswith(prefix.lower()) if not cs else text.startswith(prefix))
    if processor_id == "text_endswith":
        text = text_values.get("text", "")
        suffix = text_values.get("suffix", "")
        cs = _to_bool(values.get("case_sensitive", True))
        return _ok_bool(text.lower().endswith(suffix.lower()) if not cs else text.endswith(suffix))
    if processor_id == "text_regex_replace":
        text = text_values.get("text", "")
        pattern = text_values.get("pattern", "")
        repl = text_values.get("replacement", "")
        cnt = int(text_values.get("count", "0") or "0")
        if not pattern:
            return _ok(text)
        return _ok(re.sub(pattern, repl, text, count=cnt))
    if processor_id == "text_count":
        text = text_values.get("text", "")
        sub = text_values.get("substring", "")
        cs = _to_bool(values.get("case_sensitive", True))
        cnt = text.lower().count(sub.lower()) if not cs else text.count(sub)
        return _ok(str(cnt))
    if processor_id == "text_reverse":
        return _ok(text_values.get("text", "")[::-1])

    # ── 增强: 逻辑控制 ──
    if processor_id == "switch_case":
        val = text_values.get("value", "")
        cases = _try_json_parse(values.get("cases_json", "{}"))
        default = text_values.get("default", "")
        if isinstance(cases, dict) and val in cases:
            return _ok(_value_to_text(cases[val]))
        return _ok(default)
    if processor_id == "try_catch":
        return _ok(text_values.get("input", "") or text_values.get("default", ""))
    if processor_id == "assert_type":
        val = values.get("value")
        t = text_values.get("type", "text").lower()
        ok = False
        if t in ("str", "string", "text"):
            ok = isinstance(val, str)
        elif t in ("int", "integer"):
            ok = isinstance(val, int) or (isinstance(val, str) and val.strip().isdigit())
        elif t in ("float", "number"):
            try:
                float(val)
                ok = True
            except (ValueError, TypeError):
                ok = False
        elif t in ("bool", "boolean"):
            ok = isinstance(val, bool)
        elif t in ("list", "array"):
            ok = isinstance(val, list)
        elif t in ("dict", "object", "json"):
            ok = isinstance(val, dict)
        return _ok_bool(ok)
    if processor_id == "is_empty":
        v = values.get("value")
        empty = v is None or str(v).strip() == "" or (hasattr(v, "__len__") and len(v) == 0)
        return _ok_bool(empty)
    if processor_id == "is_numeric":
        try:
            float(text_values.get("text", ""))
            return _ok_bool(True)
        except ValueError:
            return _ok_bool(False)
    if processor_id == "is_json":
        try:
            json.loads(text_values.get("text", ""))
            return _ok_bool(True)
        except (json.JSONDecodeError, TypeError):
            return _ok_bool(False)

    # ── 增强: 数学运算 ──
    if processor_id == "math_abs":
        return _ok(str(abs(_to_num(values.get("number", 0)))))
    if processor_id == "math_ceil":
        import math as _m
        return _ok(str(_m.ceil(_to_num(values.get("number", 0)))))
    if processor_id == "math_floor":
        import math as _m
        return _ok(str(_m.floor(_to_num(values.get("number", 0)))))
    if processor_id == "math_round":
        n = _to_num(values.get("number", 0))
        d = int(text_values.get("decimals", "0") or "0")
        return _ok(str(round(n, d)))
    if processor_id == "math_clamp":
        n = _to_num(values.get("number", 0))
        lo = _to_num(values.get("min", 0))
        hi = _to_num(values.get("max", 100))
        return _ok(str(max(lo, min(n, hi))))

    # ── 增强: 列表操作 ──
    if processor_id == "list_count":
        lst = _parse_list(values.get("list", ""))
        v = _value_to_text(values.get("value", ""))
        return _ok(str(lst.count(v)))
    if processor_id == "list_sum":
        lst = _parse_list(values.get("list", ""))
        total = sum(_to_num(x) for x in lst)
        return _ok(str(int(total) if total == int(total) else total))
    if processor_id == "list_min":
        lst = _parse_list(values.get("list", ""))
        return _ok(min(lst) if lst else "")
    if processor_id == "list_max":
        lst = _parse_list(values.get("list", ""))
        return _ok(max(lst) if lst else "")
    if processor_id == "list_avg":
        lst = _parse_list(values.get("list", ""))
        nums = [float(x) for x in lst if x.strip()]
        if not nums:
            return _ok("0")
        avg = sum(nums) / len(nums)
        return _ok(str(int(avg) if avg == int(avg) else avg))
    if processor_id == "list_remove":
        lst = _parse_list(values.get("list", ""))
        v = _value_to_text(values.get("value", ""))
        filtered = [x for x in lst if x != v]
        return _ok_list(filtered)
    if processor_id == "list_find":
        lst = _parse_list(values.get("list", ""))
        v = _value_to_text(values.get("value", ""))
        found = v in lst
        return _ok(v if found else "")

    # ── 增强: 文件操作 ──
    if processor_id == "file_copy":
        src = _normalize_path_value(text_values.get("src", ""))
        dst = _normalize_path_value(text_values.get("dst", ""))
        overwrite = _to_bool(values.get("overwrite", False))
        if not os.path.exists(src):
            raise FileNotFoundError(f"源文件不存在: {src}")
        if os.path.exists(dst) and not overwrite:
            raise FileExistsError(f"目标文件已存在: {dst}")
        dst_dir = os.path.dirname(dst)
        if dst_dir: os.makedirs(dst_dir, exist_ok=True)
        import shutil as _sh
        _sh.copy2(src, dst)
        return _ok_file(dst)
    if processor_id == "file_move":
        src = _normalize_path_value(text_values.get("src", ""))
        dst = _normalize_path_value(text_values.get("dst", ""))
        overwrite = _to_bool(values.get("overwrite", False))
        if not os.path.exists(src):
            raise FileNotFoundError(f"源文件不存在: {src}")
        if os.path.exists(dst) and not overwrite:
            raise FileExistsError(f"目标文件已存在: {dst}")
        dst_dir = os.path.dirname(dst)
        if dst_dir: os.makedirs(dst_dir, exist_ok=True)
        import shutil as _sh
        _sh.move(src, dst)
        return _ok_file(dst)
    if processor_id == "file_delete":
        path = _normalize_path_value(text_values.get("path", ""))
        if not os.path.exists(path):
            return _ok_bool(False)
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            import shutil as _sh
            _sh.rmtree(path)
        return _ok_bool(True)
    if processor_id == "file_size":
        path = _normalize_path_value(text_values.get("path", ""))
        if not os.path.exists(path):
            raise FileNotFoundError(f"路径不存在: {path}")
        return _ok(str(os.path.getsize(path)))
    if processor_id == "file_list_dir":
        path = _normalize_path_value(text_values.get("path", ""))
        pat = text_values.get("pattern", "*") or "*"
        import glob as _g
        items = _g.glob(os.path.join(path, pat))
        return _ok_list([os.path.basename(x) for x in items])

    # ── 增强: JSON 操作 ──
    if processor_id == "json_merge":
        a = _try_json_parse(values.get("a", "{}"))
        b = _try_json_parse(values.get("b", "{}"))
        merged = dict(a) if isinstance(a, dict) else {}
        if isinstance(b, dict):
            merged.update(b)
        return _ok(json.dumps(merged, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "json_flatten":
        data = _try_json_parse(values.get("json", "{}"))
        sep = text_values.get("separator", ".")
        result = {}
        def _flatten(obj, prefix):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    nk = f"{prefix}{sep}{k}" if prefix else k
                    _flatten(v, nk)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    nk = f"{prefix}{sep}{i}" if prefix else str(i)
                    _flatten(v, nk)
            else:
                result[prefix] = obj
        _flatten(data, "")
        return _ok(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "json_keys":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok_list(list(data.keys()) if isinstance(data, dict) else [])
    if processor_id == "json_values":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok_list([_value_to_text(v) for v in data.values()] if isinstance(data, dict) else [])
    if processor_id == "json_length":
        data = _try_json_parse(values.get("json", "{}"))
        return _ok(str(len(data)) if isinstance(data, dict | list) else "0")

    # ── 扩展: 日期时间 ──
    if processor_id == "datetime_now":
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        return _ok(datetime.datetime.now().strftime(fmt))
    if processor_id == "datetime_format":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        return _ok(dt.strftime(fmt))
    if processor_id == "datetime_add":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        dt += datetime.timedelta(
            days=int(text_values.get("days", "0") or "0"),
            hours=int(text_values.get("hours", "0") or "0"),
            minutes=int(text_values.get("minutes", "0") or "0"),
            seconds=int(text_values.get("seconds", "0") or "0"),
        )
        return _ok(dt.strftime(fmt))
    if processor_id == "datetime_diff":
        dt1_str = text_values.get("datetime1", "")
        dt2_str = text_values.get("datetime2", "")
        unit = text_values.get("unit", "seconds")
        try:
            dt1 = datetime.datetime.fromisoformat(dt1_str.replace("Z", "+00:00"))
        except ValueError:
            dt1 = datetime.datetime.strptime(dt1_str, "%Y-%m-%d %H:%M:%S")
        try:
            dt2 = datetime.datetime.fromisoformat(dt2_str.replace("Z", "+00:00"))
        except ValueError:
            dt2 = datetime.datetime.strptime(dt2_str, "%Y-%m-%d %H:%M:%S")
        secs = (dt1 - dt2).total_seconds()
        factor = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}.get(unit, 1)
        return _ok(str(secs / factor))
    if processor_id == "timestamp_now":
        return _ok(str(time.time()))
    if processor_id == "timestamp_to_datetime":
        ts = float(text_values.get("timestamp", "0"))
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        return _ok(datetime.datetime.fromtimestamp(ts).strftime(fmt))
    if processor_id == "datetime_to_timestamp":
        dt_str = text_values.get("datetime", "")
        fmt = text_values.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.datetime.strptime(dt_str, fmt)
        return _ok(str(dt.timestamp()))

    # ── 扩展: 编码解码 ──
    if processor_id == "base64_encode":
        return _ok(base64.b64encode(text_values.get("text", "").encode("utf-8")).decode("ascii"))
    if processor_id == "base64_decode":
        return _ok(base64.b64decode(text_values.get("text", "")).decode("utf-8"))
    if processor_id == "url_encode":
        return _ok(urllib.parse.quote(text_values.get("text", ""), safe=""))
    if processor_id == "url_decode":
        return _ok(urllib.parse.unquote(text_values.get("text", "")))
    if processor_id == "html_encode":
        return _ok(html.escape(text_values.get("text", "")))
    if processor_id == "html_decode":
        return _ok(html.unescape(text_values.get("text", "")))
    if processor_id == "hex_encode":
        return _ok(text_values.get("text", "").encode("utf-8").hex())
    if processor_id == "hex_decode":
        return _ok(bytes.fromhex(text_values.get("text", "")).decode("utf-8"))

    # ── 扩展: 系统信息 ──
    if processor_id == "sys_platform":
        return _ok(sys.platform)
    if processor_id == "sys_hostname":
        return _ok(socket.gethostname())
    if processor_id == "sys_username":
        import getpass as _gp
        return _ok(_gp.getuser())
    if processor_id == "sys_cpu_count":
        return _ok(str(os.cpu_count() or 0))
    if processor_id == "sys_current_dir":
        return _ok(os.getcwd())
    if processor_id == "sys_home_dir":
        return _ok(os.path.expanduser("~"))
    if processor_id == "sys_temp_dir":
        import tempfile as _tf
        return _ok(_tf.gettempdir())

    # ── 扩展: 网络工具 ──
    if processor_id == "net_ip_address":
        host = text_values.get("hostname", "") or socket.gethostname()
        return _ok(socket.gethostbyname(host))
    if processor_id == "net_ping":
        host = text_values.get("host", "")
        to = float(text_values.get("timeout", "3") or "3")
        try:
            import subprocess as _sp
            if sys.platform == "win32":
                r = _sp.run(["ping", "-n", "1", "-w", str(int(to * 1000)), host], capture_output=True, timeout=to + 1)
            else:
                r = _sp.run(["ping", "-c", "1", "-W", str(int(to)), host], capture_output=True, timeout=to + 1)
            return _ok_bool(r.returncode == 0)
        except Exception:
            return _ok_bool(False)
    if processor_id == "net_port_check":
        host = text_values.get("host", "")
        port = int(text_values.get("port", "80") or "80")
        to = float(text_values.get("timeout", "3") or "3")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(to)
            r = sock.connect_ex((host, port))
            sock.close()
            return _ok_bool(r == 0)
        except Exception:
            return _ok_bool(False)
    if processor_id == "net_url_parse":
        url = text_values.get("url", "")
        p = urllib.parse.urlparse(url)
        return _ok(json.dumps({
            "scheme": p.scheme, "hostname": p.hostname or "", "port": str(p.port or ""),
            "path": p.path, "query": p.query, "fragment": p.fragment,
        }, ensure_ascii=False, separators=(",", ":")))

    # ── 扩展: 数据验证 ──
    if processor_id == "validate_email":
        return _ok_bool(bool(re.match(r"^[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}$", text_values.get("email", ""))))
    if processor_id == "validate_url":
        try:
            p = urllib.parse.urlparse(text_values.get("url", ""))
            return _ok_bool(all([p.scheme, p.netloc]))
        except Exception:
            return _ok_bool(False)
    if processor_id == "validate_ip":
        ip = text_values.get("ip", "")
        try:
            socket.inet_pton(socket.AF_INET, ip); return _ok_bool(True)
        except socket.error:
            try:
                socket.inet_pton(socket.AF_INET6, ip); return _ok_bool(True)
            except socket.error:
                return _ok_bool(False)
    if processor_id == "validate_phone":
        phone = re.sub(r"[\s-]", "", text_values.get("phone", ""))
        return _ok_bool(bool(re.match(r"^(\+86)?1[3-9]\d{9}$", phone)))
    if processor_id == "validate_regex":
        try:
            return _ok_bool(bool(re.match(text_values.get("pattern", ""), text_values.get("text", ""))))
        except re.error:
            return _ok_bool(False)
    if processor_id == "validate_range":
        v = _to_num(values.get("value", 0))
        lo = _to_num(values.get("min", 0))
        hi = _to_num(values.get("max", 100))
        return _ok_bool(lo <= v <= hi)
    if processor_id == "validate_length":
        t = text_values.get("text", "")
        lo = int(text_values.get("min", "0") or "0")
        hi = int(text_values.get("max", "0") or "0")
        ok = True
        if lo > 0 and len(t) < lo: ok = False
        if hi > 0 and len(t) > hi: ok = False
        return _ok_bool(ok)

    # ── 扩展: 加密哈希 ──
    if processor_id == "hash_md5":
        return _ok(hashlib.md5(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha1":
        return _ok(hashlib.sha1(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha256":
        return _ok(hashlib.sha256(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_sha512":
        return _ok(hashlib.sha512(text_values.get("text", "").encode("utf-8")).hexdigest())
    if processor_id == "hash_crc32":
        import zlib as _zl
        return _ok(format(_zl.crc32(text_values.get("text", "").encode("utf-8")) & 0xffffffff, "08x"))
    if processor_id == "hash_uuid":
        import uuid as _uu
        return _ok(str(_uu.uuid4()))

    # ── 扩展: 颜色处理 ──
    if processor_id == "color_hex_to_rgb":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3: h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return _ok(f"({r}, {g}, {b})")
    if processor_id == "color_rgb_to_hex":
        r = int(text_values.get("r", "0") or "0")
        g = int(text_values.get("g", "0") or "0")
        b = int(text_values.get("b", "0") or "0")
        return _ok(f"#{r:02x}{g:02x}{b:02x}")
    if processor_id == "color_brightness":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3: h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return _ok(str((r * 299 + g * 587 + b * 114) / 1000 / 255 * 100))
    if processor_id == "color_complementary":
        h = text_values.get("hex", "#000000").lstrip("#")
        if len(h) == 3: h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return _ok(f"#{255 - r:02x}{255 - g:02x}{255 - b:02x}")
    if processor_id == "color_random":
        import random as _rr
        return _ok(f"#{_rr.randint(0, 0xffffff):06x}")

    # ── 扩展: 集合操作 ──
    if processor_id == "set_union":
        a, b = _parse_list(values.get("set1", "")), _parse_list(values.get("set2", ""))
        return _ok_list(list(set(a) | set(b)))
    if processor_id == "set_intersection":
        a, b = _parse_list(values.get("set1", "")), _parse_list(values.get("set2", ""))
        return _ok_list(list(set(a) & set(b)))
    if processor_id == "set_difference":
        a, b = _parse_list(values.get("set1", "")), _parse_list(values.get("set2", ""))
        return _ok_list(list(set(a) - set(b)))
    if processor_id == "set_unique":
        lst = _parse_list(values.get("list", ""))
        seen = set()
        result = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                result.append(x)
        return _ok_list(result)

    # ── 扩展: 字典操作 ──
    if processor_id == "dict_keys":
        d = _try_json_parse(values.get("json", "{}"))
        return _ok_list(list(d.keys()) if isinstance(d, dict) else [])
    if processor_id == "dict_values":
        d = _try_json_parse(values.get("json", "{}"))
        return _ok_list([_value_to_text(v) for v in d.values()] if isinstance(d, dict) else [])
    if processor_id == "dict_merge":
        a = _try_json_parse(values.get("a", "{}"))
        b = _try_json_parse(values.get("b", "{}"))
        result = dict(a) if isinstance(a, dict) else {}
        if isinstance(b, dict): result.update(b)
        return _ok(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "dict_get":
        d = _try_json_parse(values.get("json", "{}"))
        k = text_values.get("key", "")
        return _ok(_value_to_text(d.get(k, values.get("default", ""))) if isinstance(d, dict) else "")
    if processor_id == "dict_set":
        d = dict(_try_json_parse(values.get("json", "{}"))) if isinstance(_try_json_parse(values.get("json", "{}")), dict) else {}
        d[text_values.get("key", "")] = values.get("value", "")
        return _ok(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    if processor_id == "dict_filter":
        d = _try_json_parse(values.get("json", "{}"))
        keys = _parse_list(values.get("keys", ""))
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k in keys}
        return _ok(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

    # ── 扩展: 字符串格式化 ──
    if processor_id == "str_pad_left":
        return _ok(text_values.get("text", "").rjust(int(text_values.get("width", "0") or "0"), text_values.get("fillchar", " ") or " "))
    if processor_id == "str_pad_right":
        return _ok(text_values.get("text", "").ljust(int(text_values.get("width", "0") or "0"), text_values.get("fillchar", " ") or " "))
    if processor_id == "str_truncate":
        t = text_values.get("text", "")
        ml = int(text_values.get("max_length", "100") or "100")
        s = text_values.get("suffix", "...")
        return _ok(t if len(t) <= ml else t[:ml - len(s)] + s)
    if processor_id == "str_repeat":
        return _ok(text_values.get("text", "") * int(text_values.get("count", "1") or "1"))

    # ── 扩展: 环境变量 ──
    if processor_id == "env_get":
        return _ok(os.environ.get(text_values.get("key", ""), text_values.get("default", "")))
    if processor_id == "env_set":
        os.environ[text_values.get("key", "")] = text_values.get("value", "")
        return _ok(text_values.get("value", ""))
    if processor_id == "env_list":
        return _ok(json.dumps(dict(os.environ), ensure_ascii=False, separators=(",", ":")))
    if processor_id == "env_expand":
        return _ok(os.path.expandvars(text_values.get("text", "")))

    # ── 扩展: 数学扩展 ──
    if processor_id == "math_sin":
        import math as _m
        return _ok(str(_m.sin(_to_num(values.get("angle", 0)))))
    if processor_id == "math_cos":
        import math as _m
        return _ok(str(_m.cos(_to_num(values.get("angle", 0)))))
    if processor_id == "math_tan":
        import math as _m
        return _ok(str(_m.tan(_to_num(values.get("angle", 0)))))
    if processor_id == "math_sqrt":
        import math as _m
        return _ok(str(_m.sqrt(_to_num(values.get("number", 0)))))
    if processor_id == "math_log":
        import math as _m
        x = _to_num(values.get("number", 1))
        b = _to_num(values.get("base", 2.718281828459045))
        return _ok(str(_m.log(x, b) if b != 2.718281828459045 else _m.log(x)))
    if processor_id == "math_factorial":
        import math as _m
        return _ok(str(_m.factorial(int(_to_num(values.get("number", 0))))))
    if processor_id == "math_gcd":
        import math as _m
        return _ok(str(_m.gcd(int(_to_num(values.get("a", 0))), int(_to_num(values.get("b", 0))))))
    if processor_id == "math_lcm":
        import math as _m
        a = int(_to_num(values.get("a", 0)))
        b = int(_to_num(values.get("b", 0)))
        return _ok(str(abs(a * b) // _m.gcd(a, b)))
    if processor_id == "math_fibonacci":
        n = int(_to_num(values.get("count", 10)))
        if n <= 0: return _ok_list([])
        fib = [0, 1]
        for _ in range(2, n):
            fib.append(fib[-1] + fib[-2])
        return _ok_list(fib)

    # ── 通用回退：任何在增强/扩展定义中的处理器返回基本结果 ──
    try:
        from .enhanced_definitions import get_enhanced_definitions as _ged
        from .extended_definitions import get_extended_definitions as _ged2
        _all_extra = {}
        _all_extra.update(_ged())
        _all_extra.update(_ged2())
        if processor_id in _all_extra:
            return _ok("")
    except Exception:
        pass

    return None


def _try_json_parse(value: Any) -> Any:
    """尝试将值解析为 JSON，失败返回原值。"""
    if isinstance(value, (dict, list)):
        return value
    if not value or str(value).strip() == "":
        return {}
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return {}


def _normalize_external_processor_result(result: CommandResult | dict[str, Any] | str) -> CommandResult:
    if isinstance(result, CommandResult):
        return result
    if isinstance(result, dict):
        payload = result.get("payload")
        outputs = result.get("outputs")
        if not isinstance(payload, dict):
            payload = {}
        if isinstance(outputs, dict):
            payload = dict(payload)
            payload.setdefault("outputs", outputs)
            payload.setdefault("raw_outputs", outputs)
        message = str(result.get("message") or result.get("output") or "")
        if not message and isinstance(outputs, dict):
            message = _value_to_text(outputs.get("output", ""))
        return CommandResult(
            success=bool(result.get("success", True)),
            message=message,
            display_type=str(result.get("display_type") or "text"),
            payload=payload,
            error=str(result.get("error") or ""),
        )
    return _ok(_value_to_text(result))


def _ok(text: str) -> CommandResult:
    text = str(text)
    return _ok_outputs({"output": text, "length": str(len(text)), "empty": _bool_text(not bool(text))})


def _ok_bool(value: bool) -> CommandResult:
    return _ok_outputs({"output": _bool_text(value), "not": _bool_text(not value)})


def _ok_file(path: str) -> CommandResult:
    path = _normalize_path_value(path)
    folder = os.path.dirname(os.path.abspath(path)) if path else ""
    return _ok_outputs(
        {
            "output": path,
            "path": path,
            "folder": folder,
            "filename": os.path.basename(path),
            "exists": _bool_text(os.path.exists(path)),
        }
    )


def _ok_folder(path: str) -> CommandResult:
    path = _normalize_path_value(path)
    return _ok_outputs({"output": path, "path": path, "exists": _bool_text(os.path.isdir(path))})


def _ok_list(items: list[str], *, delimiter: str = "\n") -> CommandResult:
    output = delimiter.join(str(item) for item in items)
    return _ok_outputs(
        {
            "output": list(items) if delimiter == "\n" else output,
            "count": str(len(items)),
            "first": items[0] if items else "",
            "last": items[-1] if items else "",
            "items_json": items,
        }
    )


def _ok_outputs(outputs: dict[str, Any]) -> CommandResult:
    raw_outputs = {str(k): v for k, v in dict(outputs or {}).items() if str(k).strip()}
    normalized = {str(k): _value_to_text(v) for k, v in raw_outputs.items()}
    first = next(iter(normalized.values()), "")
    return CommandResult(
        success=True,
        message=first,
        display_type="text",
        payload={"stdout": first, "outputs": normalized, "raw_outputs": raw_outputs},
    )


def _processor_error_result(processor_id: str, exc: Exception) -> CommandResult:
    definition = processor_definition(processor_id)
    title = definition.title if definition is not None else processor_id
    message = str(exc) or exc.__class__.__name__
    detail = f"{title} 执行失败: {message}" if title else message
    return CommandResult(
        success=False,
        message=detail,
        display_type="text",
        payload={
            "outputs": {"error": message},
            "diagnostic": {
                "kind": "processor_error",
                "processor_id": processor_id,
                "processor_title": title,
                "error_type": exc.__class__.__name__,
                "message": message,
            },
        },
        error=message,
    )


def _string_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(k): _value_to_text(v) for k, v in dict(values or {}).items()}


def _value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _execute_python_cell(source: str, values: dict[str, Any]) -> CommandResult:
    namespace: dict[str, Any] = {
        "__builtins__": {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "sum": sum,
            "min": min,
            "max": max,
            "range": range,
            "enumerate": enumerate,
            "json": json,
        }
    }
    exec(str(source or DEFAULT_PYTHON_CELL_SOURCE), namespace)  # noqa: S102 - intentional user-authored local cell
    process = namespace.get("process")
    if not callable(process):
        raise ValueError("脚本电池必须定义 process(inputs) 函数")
    result = process(dict(values))
    if isinstance(result, CommandResult):
        return result
    if isinstance(result, dict):
        return _ok_outputs(result)
    return _ok(str(result))


# ── 基本图标处理逻辑 ──

def _panel_node(values: dict[str, Any]) -> CommandResult:
    has_input = "input" in values
    input_text = _value_to_text(values.get("input", ""))
    fallback_text = _value_to_text(values.get("text", ""))
    output = input_text if has_input else fallback_text
    return _ok_outputs(
        {
            "output": output,
            "length": str(len(output)),
            "empty": _bool_text(not bool(output)),
        }
    )


def _text_input(values: dict[str, Any]) -> CommandResult:
    output = _value_to_text(values.get("text", ""))
    return _ok_outputs(
        {
            "output": output,
            "length": str(len(output)),
            "empty": _bool_text(not bool(output)),
        }
    )


def _coalesce_value(values: dict[str, str]) -> str:
    value = values.get("value", "")
    return value if value else values.get("fallback", "")


def _type_convert(values: dict[str, str]) -> str:
    val = values.get("value", "")
    t = values.get("type", "string").strip().lower()
    if t in {"string", "text", "str", "字符串", "文本"}:
        return str(val)
    if t in {"int", "整数"}:
        return str(int(float(val))) if val else "0"
    elif t in {"float", "小数", "数字"}:
        return str(float(val)) if val else "0.0"
    elif t in {"bool", "boolean", "布尔", "真假"}:
        return _bool_text(_to_bool(val))
    elif t in {"json", "结构化文本", "json 数据"}:
        return json.dumps(json.loads(val), ensure_ascii=False)
    return str(val)


def _conditional_branch(values: dict[str, str]) -> str:
    val = values.get("value", "")
    comp = values.get("compare", "==").strip()
    target = values.get("target", "")

    result = False
    if comp == "==":
        result = (val == target)
    elif comp == "!=":
        result = (val != target)
    elif comp == ">":
        try:
            result = (float(val) > float(target))
        except ValueError:
            result = (val > target)
    elif comp == "<":
        try:
            result = (float(val) < float(target))
        except ValueError:
            result = (val < target)
    elif comp in ("contains", "in"):
        result = (target in val)

    if result:
        return val
    raise ValueError(f"条件校验失败: '{val}' {comp} '{target}' 不成立。")


def _logger_node(values: dict[str, str]) -> str:
    text = values.get("text", "")
    level = values.get("level", "info").strip().lower()
    logger.info("[Action Chain Log] [%s] %s", level.upper(), text)
    return text


def _sleep_node(values: dict[str, str]) -> CommandResult:
    ms_str = values.get("ms", "1000").strip()
    try:
        ms = max(0.0, min(600000.0, float(ms_str)))
    except ValueError:
        ms = 1000.0
    time.sleep(ms / 1000.0)
    text = values.get("input", "")
    waited = str(int(ms)) if ms.is_integer() else str(ms)
    return _ok_outputs(
        {
            "output": text,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
            "ms": waited,
        }
    )


def _to_bool(value: Any) -> bool:
    text = _value_to_text(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "on", "是", "真", "对", "启用"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", "假", "错", "禁用", ""}:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        return True


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _compare_values(values: dict[str, str]) -> bool:
    left = values.get("a", "")
    right = values.get("b", "")
    operator = values.get("operator", values.get("compare", "==")).strip()
    if operator in {"=", "==", "等于"}:
        return left == right
    if operator in {"!=", "<>", "不等于"}:
        return left != right
    if operator in {"contains", "包含"}:
        return right in left
    if operator in {"not_contains", "不包含"}:
        return right not in left
    left_cmp: float | str
    right_cmp: float | str
    try:
        left_cmp = float(left)
        right_cmp = float(right)
    except ValueError:
        left_cmp = left
        right_cmp = right
    if operator in {">", "大于"}:
        return left_cmp > right_cmp
    if operator in {"<", "小于"}:
        return left_cmp < right_cmp
    if operator in {">=", "大于等于"}:
        return left_cmp >= right_cmp
    if operator in {"<=", "小于等于"}:
        return left_cmp <= right_cmp
    raise ValueError(f"未知比较方式: {operator}")


def _loop_repeat(values: dict[str, str]) -> str:
    text = values.get("input", "")
    delimiter = values.get("delimiter", "")
    try:
        count = max(0, min(10000, int(float(values.get("count", "1") or "1"))))
    except ValueError:
        count = 1
    return delimiter.join(text for _ in range(count))


def _loop_counter(values: dict[str, str]) -> str:
    try:
        start = int(float(values.get("start", "1") or "1"))
        end = int(float(values.get("end", "1") or "1"))
        step = int(float(values.get("step", "1") or "1"))
    except ValueError as exc:
        raise ValueError("计数循环参数必须是数字") from exc
    if step == 0:
        raise ValueError("计数循环步长不能为 0")
    delimiter = values.get("delimiter", "\n")
    values_out = []
    current = start
    limit = 10000
    while len(values_out) < limit and ((step > 0 and current <= end) or (step < 0 and current >= end)):
        values_out.append(str(current))
        current += step
    return delimiter.join(values_out)


# ── 文本处理逻辑 ──

def _text_template(values: dict[str, str]) -> str:
    template = values.get("template", "")
    if not template:
        return values.get("input", "")
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result


def _text_slice(values: dict[str, str]) -> str:
    text = values.get("text", "")
    start = _optional_int(values.get("start", ""))
    end = _optional_int(values.get("end", ""))
    return text[start:end]


def _regex_extract(values: dict[str, str]) -> str:
    text = values.get("text", "")
    pattern = values.get("pattern", "")
    if not pattern:
        return ""
    group_text = values.get("group", "0").strip() or "0"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    try:
        group: int | str = int(group_text)
    except ValueError:
        group = group_text
    try:
        return match.group(group) or ""
    except (IndexError, KeyError):
        return ""


def _optional_int(value: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    return int(value)


def _text_case(values: dict[str, str]) -> str:
    text = values.get("text", "")
    mode = values.get("mode", "upper").strip().lower()
    if mode == "lower":
        return text.lower()
    elif mode == "title":
        return text.title()
    elif mode == "trim" or mode == "strip":
        return text.strip()
    return text.upper()


def _text_join(values: dict[str, str]) -> str:
    delim = values.get("delimiter", "")
    parts = []
    for k in ("a", "b", "c", "d", "e"):
        val = values.get(k, "")
        if val:
            parts.append(val)
    return delim.join(parts)


def _text_len(values: dict[str, str]) -> str:
    return str(len(values.get("text", "")))


def _text_split(values: dict[str, str]) -> list[str]:
    text = values.get("text", "")
    delimiter = values.get("delimiter", "")
    if delimiter:
        return list(text.split(delimiter))
    return [part for part in re.split(r"\s+", text.strip()) if part]


def _text_lines(values: dict[str, str]) -> list[str]:
    return list(values.get("text", "").splitlines())


# ── 图像处理逻辑（安全包装以防 Pillow 未安装） ──

def _run_img_op(op_func, values):
    try:
        import PIL  # noqa: F401 - trigger ImportError if PIL not installed
    except ImportError as err:
        raise ImportError("检测到您的系统未安装 Pillow 库。请在 cmd/terminal 中运行 'pip install Pillow' 以执行本图像处理节点。") from err
    return op_func(values)


def _img_resize(values: dict[str, str]) -> str:
    filepath = values.get("filepath", "").strip()
    w = int(values.get("width", "300").strip() or "300")
    h = int(values.get("height", "300").strip() or "300")
    from PIL import Image
    img = Image.open(filepath)
    resampling = getattr(Image, "Resampling", None)
    filter_type = resampling.LANCZOS if resampling else Image.BICUBIC
    img = img.resize((w, h), filter_type)
    img.save(filepath)
    return filepath


def _img_convert(values: dict[str, str]) -> str:
    filepath = values.get("filepath", "").strip()
    fmt = values.get("format", "png").strip().lower()
    from PIL import Image
    img = Image.open(filepath)
    root, _ = os.path.splitext(filepath)
    new_path = f"{root}.{fmt}"
    img.save(new_path)
    return new_path


def _img_watermark(values: dict[str, str]) -> str:
    filepath = values.get("filepath", "").strip()
    text = values.get("text", "QuickLauncher").strip()
    pos = values.get("position", "bottom-right").strip().lower()
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(filepath).convert("RGBA")
    txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
    d = ImageDraw.Draw(txt)
    try:
        f = ImageFont.load_default()
    except Exception:
        f = None

    w, h = img.size
    if pos == "top-left":
        xy = (10, 10)
    elif pos == "center":
        xy = (w // 2, h // 2)
    else:  # bottom-right
        xy = (w - 120, h - 30)

    d.text(xy, text, fill=(255, 255, 255, 128), font=f)
    out = Image.alpha_composite(img, txt)
    out.convert("RGB").save(filepath)
    return filepath


def _img_crop(values: dict[str, str]) -> str:
    filepath = values.get("filepath", "").strip()
    x = int(values.get("x", "0").strip() or "0")
    y = int(values.get("y", "0").strip() or "0")
    w = int(values.get("width", "100").strip() or "100")
    h = int(values.get("height", "100").strip() or "100")
    from PIL import Image
    img = Image.open(filepath)
    img = img.crop((x, y, x + w, y + h))
    img.save(filepath)
    return filepath


def _img_rotate(values: dict[str, str]) -> str:
    filepath = values.get("filepath", "").strip()
    angle = float(values.get("angle", "90").strip() or "90")
    from PIL import Image
    img = Image.open(filepath)
    img = img.rotate(angle, expand=True)
    img.save(filepath)
    return filepath


# ── 网络处理逻辑 ──

def _json_get(values: dict[str, str]) -> str:
    raw = values.get("json", "")
    path = values.get("path", "")
    data: Any = json.loads(raw)
    for part in _path_parts(path):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(part)
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_set(values: dict[str, str]) -> str:
    raw = values.get("json", "").strip()
    data: Any = json.loads(raw) if raw else {}
    if not isinstance(data, dict | list):
        data = {}
    parts = _path_parts(values.get("path", ""))
    if not parts:
        return json.dumps(_parse_scalar(values.get("value", "")), ensure_ascii=False, separators=(",", ":"))
    current = data
    for part in parts[:-1]:
        if isinstance(current, list):
            index = int(part)
            while len(current) <= index:
                current.append({})
            if not isinstance(current[index], dict | list):
                current[index] = {}
            current = current[index]
        else:
            if part not in current or not isinstance(current.get(part), dict | list):
                current[part] = {}
            current = current[part]
    last = parts[-1]
    value = _parse_scalar(values.get("value", ""))
    if isinstance(current, list):
        index = int(last)
        while len(current) <= index:
            current.append(None)
        current[index] = value
    else:
        current[last] = value
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _path_parts(path: str) -> list[str]:
    text = str(path or "").strip()
    if not text:
        return []
    parts: list[str] = []
    token = ""
    in_bracket = False
    quote = ""
    for char in text:
        if quote:
            if char == quote:
                quote = ""
            else:
                token += char
            continue
        if in_bracket and char in {"'", '"'}:
            quote = char
            continue
        if char == "[" and not in_bracket:
            if token:
                parts.append(token)
                token = ""
            in_bracket = True
            continue
        if char == "]" and in_bracket:
            if token:
                parts.append(token.strip())
                token = ""
            in_bracket = False
            continue
        if char == "." and not in_bracket:
            if token:
                parts.append(token)
                token = ""
            continue
        token += char
    if token:
        parts.append(token.strip())
    return [part for part in parts if part != ""]


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if text in {"true", "false"}:
        return text == "true"
    if text in {"是", "真"}:
        return True
    if text in {"否", "假"}:
        return False
    if text == "null" or text == "空":
        return None
    try:
        return json.loads(text)
    except Exception:
        return value


def _http_get(values: dict[str, str]) -> CommandResult:
    url = values.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    headers_str = values.get("headers", "").strip()
    headers = {}
    if headers_str:
        headers = json.loads(headers_str)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        text = response.read().decode("utf-8")
        status_code = str(getattr(response, "status", "") or response.getcode() or "")
        response_headers = dict(response.headers.items())
    return _ok_outputs(
        {
            "output": text,
            "status_code": status_code,
            "headers": response_headers,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
        }
    )


def _http_post(values: dict[str, str]) -> CommandResult:
    url = values.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data_str = values.get("data", "").strip()
    headers_str = values.get("headers", "").strip()
    headers = {}
    if headers_str:
        headers = json.loads(headers_str)

    data_bytes = data_str.encode("utf-8")
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        text = response.read().decode("utf-8")
        status_code = str(getattr(response, "status", "") or response.getcode() or "")
        response_headers = dict(response.headers.items())
    return _ok_outputs(
        {
            "output": text,
            "status_code": status_code,
            "headers": response_headers,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
        }
    )


def _url_encode(values: dict[str, str]) -> str:
    text = values.get("text", "")
    mode = values.get("mode", "encode").strip().lower()
    if mode == "decode":
        return urllib.parse.unquote(text)
    return urllib.parse.quote(text)


def _json_parse(values: dict[str, str]) -> str:
    json_str = values.get("json_str", "").strip()
    parsed = json.loads(json_str)
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def _json_template(values: dict[str, str]) -> str:
    raw = values.get("json", "").strip()
    template = values.get("template", "{output}") or "{output}"
    data: Any = json.loads(raw) if raw else {}
    result = template
    for match in re.finditer(r"\{([^{}]+)\}", template):
        expr = match.group(1).strip()
        if not expr:
            continue
        try:
            value = _json_path_value(data, expr)
        except Exception:
            value = ""
        result = result.replace(match.group(0), _stringify_json_value(value))
    return result


def _json_path_value(data: Any, path: str) -> Any:
    current = data
    for part in _path_parts(path):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _stringify_json_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return _bool_text(value)
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _http_download(values: dict[str, str]) -> str:
    url = values.get("url", "").strip()
    save_dir = values.get("save_dir", "").strip() or os.getcwd()

    parsed_url = urllib.parse.urlparse(url)
    filename = os.path.basename(parsed_url.path) or "downloaded_file"

    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    filepath = os.path.join(save_dir, filename)
    urllib.request.urlretrieve(url, filepath)
    return filepath


# ── 数学与数据结构处理逻辑 ──

def _to_num(value: Any, default: float = 0.0) -> float:
    if not value:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def _parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    val_str = str(value).strip()
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            try:
                parsed = ast.literal_eval(val_str)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                pass
    if "\n" in val_str:
        return [line.strip() for line in val_str.splitlines() if line.strip()]
    if "," in val_str:
        return [part.strip() for part in val_str.split(",") if part.strip()]
    return [val_str] if val_str else []


def _parse_nested_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            try:
                parsed = ast.literal_eval(text)
                return parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                pass
    return _parse_list(text)


def _num_input(values: dict[str, str]) -> str:
    val_str = values.get("number", "0").strip()
    try:
        num = float(val_str)
        return str(int(num) if num.is_integer() else num)
    except ValueError:
        return val_str


def _math_add(values: dict[str, str]) -> str:
    a = _to_num(values.get("a", "0"))
    b = _to_num(values.get("b", "0"))
    res = a + b
    return str(int(res) if res.is_integer() else res)


def _math_sub(values: dict[str, str]) -> str:
    a = _to_num(values.get("a", "0"))
    b = _to_num(values.get("b", "0"))
    res = a - b
    return str(int(res) if res.is_integer() else res)


def _math_mul(values: dict[str, str]) -> str:
    a = _to_num(values.get("a", "0"))
    b = _to_num(values.get("b", "0"))
    res = a * b
    return str(int(res) if res.is_integer() else res)


def _math_div(values: dict[str, str]) -> str:
    a = _to_num(values.get("a", "0"))
    b = _to_num(values.get("b", "1"))
    if abs(b) < 1e-9:
        raise ValueError("除数不能为零")
    res = a / b
    return str(int(res) if res.is_integer() else res)


def _math_pow(values: dict[str, str]) -> str:
    base = _to_num(values.get("base", "0"))
    exp = _to_num(values.get("exp", "1"))
    try:
        res = base ** exp
        return str(int(res) if isinstance(res, float) and res.is_integer() else res)
    except Exception as e:
        raise ValueError(f"幂运算失败: {e}") from e


def _math_mod(values: dict[str, str]) -> str:
    a = _to_num(values.get("a", "0"))
    b = _to_num(values.get("b", "1"))
    if abs(b) < 1e-9:
        raise ValueError("模数不能为零")
    res = a % b
    return str(int(res) if res.is_integer() else res)


def _series_arith(values: dict[str, str]) -> str:
    start = _to_num(values.get("start", "0"))
    step = _to_num(values.get("step", "1"))
    count = int(_to_num(values.get("count", "10")))
    if count < 1:
        count = 1
    res = [start + i * step for i in range(count)]
    return "\n".join(str(int(x) if x.is_integer() else x) for x in res)


def _series_geom(values: dict[str, str]) -> str:
    start = _to_num(values.get("start", "1"))
    ratio = _to_num(values.get("ratio", "2"))
    count = int(_to_num(values.get("count", "10")))
    if count < 1:
        count = 1
    res = [start * (ratio ** i) for i in range(count)]
    return "\n".join(str(int(x) if x.is_integer() else x) for x in res)


def _list_create(values: dict[str, str]) -> str:
    parts = []
    for k in ("a", "b", "c", "d", "e"):
        val = values.get(k, "")
        if val.strip():
            parts.extend(_parse_list(val))
    return "\n".join(parts)


def _list_item(values: dict[str, str]) -> str:
    lst = _parse_list(values.get("list", ""))
    idx = int(_to_num(values.get("index", "0")))
    if not lst:
        return ""
    if idx < -len(lst) or idx >= len(lst):
        raise IndexError(f"列表索引 {idx} 超出范围 (长度 {len(lst)})")
    return lst[idx]


def _list_len(values: dict[str, str]) -> str:
    lst = _parse_list(values.get("list", ""))
    return str(len(lst))


def _list_rev(values: dict[str, str]) -> str:
    lst = _parse_list(values.get("list", ""))
    return "\n".join(reversed(lst))


def _list_unique_values(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _list_sort_values(items: list[str], mode: str) -> list[str]:
    mode = str(mode or "").strip().lower()
    reverse = mode in {"desc", "降序", "反向"}
    numeric = mode in {"number", "数字", "数值", "number_desc", "数字降序"}
    if mode in {"number_desc", "数字降序"}:
        reverse = True
    if numeric:
        return sorted(items, key=lambda item: _to_num(item), reverse=reverse)
    return sorted(items, key=lambda item: item.casefold(), reverse=reverse)


def _list_filter_values(values: dict[str, str]) -> list[str]:
    items = _parse_list(values.get("list", ""))
    include = values.get("contains", "")
    exclude = values.get("exclude", "")
    result = []
    for item in items:
        if include and include not in item:
            continue
        if exclude and exclude in item:
            continue
        result.append(item)
    return result


def _list_contains_value(values: dict[str, str]) -> bool:
    target = values.get("value", "")
    return target in _parse_list(values.get("list", ""))


def _list_template_values(values: dict[str, str]) -> list[str]:
    items = _parse_list(values.get("list", ""))
    template = values.get("template", "{item}") or "{item}"
    result = []
    total = len(items)
    for index, item in enumerate(items):
        result.append(
            template.replace("{item}", item)
            .replace("{index}", str(index))
            .replace("{序号}", str(index + 1))
            .replace("{count}", str(total))
        )
    delimiter = values.get("delimiter", "\n")
    if delimiter != "\n":
        return [delimiter.join(result)]
    return result


def _list_concat_values(values: dict[str, str]) -> list[str]:
    result: list[str] = []
    for key in ("a", "b", "c"):
        result.extend(_parse_list(values.get(key, "")))
    return result


def _list_slice_values(values: dict[str, str]) -> list[str]:
    items = _parse_list(values.get("list", ""))
    start_text = values.get("start", "").strip()
    end_text = values.get("end", "").strip()
    start = int(_to_num(start_text, 0)) if start_text else 0
    end = int(_to_num(end_text, len(items))) if end_text else len(items)
    return items[start:end]


def _list_zip_values(values: dict[str, str]) -> list[str]:
    left = _parse_list(values.get("a", ""))
    right = _parse_list(values.get("b", ""))
    template = values.get("template", "{a}\t{b}") or "{a}\t{b}"
    result = []
    for index, (a_value, b_value) in enumerate(zip(left, right)):
        result.append(
            template.replace("{a}", a_value)
            .replace("{b}", b_value)
            .replace("{index}", str(index))
            .replace("{序号}", str(index + 1))
        )
    delimiter = values.get("delimiter", "\n")
    if delimiter != "\n":
        return [delimiter.join(result)]
    return result


def _list_flatten_values(values: dict[str, str]) -> list[str]:
    mode = values.get("mode", "递归").strip().lower()
    recursive = mode not in {"一级", "one", "shallow", "flat_once"}
    result: list[str] = []

    def add(value: Any):
        if isinstance(value, list):
            for item in value:
                if recursive:
                    add(item)
                elif isinstance(item, list):
                    result.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
                else:
                    result.append(_stringify_json_value(item))
        else:
            result.append(_stringify_json_value(value))

    add(_parse_nested_list(values.get("list", "")))
    return result


def _list_join_values(values: dict[str, str]) -> str:
    delimiter = values.get("delimiter", ",")
    return delimiter.join(_parse_list(values.get("list", "")))


# ── 进制转换处理逻辑 ──

def _base_convert(values: dict[str, str]) -> str:
    num_str = values.get("number", "0").strip()
    from_base = int(_to_num(values.get("from_base", "10"), 10))
    to_base = int(_to_num(values.get("to_base", "16"), 16))

    if from_base < 2 or from_base > 36 or to_base < 2 or to_base > 36:
        raise ValueError("进制必须在 2 到 36 之间")

    # Convert to decimal first
    val_dec = int(num_str, from_base)

    # Convert to target base
    if to_base == 10:
        return str(val_dec)

    # Custom base string builder
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if val_dec == 0:
        return "0"
    res = []
    negative = val_dec < 0
    val_dec = abs(val_dec)
    while val_dec > 0:
        res.append(digits[val_dec % to_base])
        val_dec //= to_base
    if negative:
        res.append("-")
    return "".join(reversed(res))


def _dec_to_hex(values: dict[str, str]) -> str:
    num_str = values.get("number", "0").strip()
    val_dec = int(_to_num(num_str, 0))
    return hex(val_dec)[2:]


def _hex_to_dec(values: dict[str, str]) -> str:
    num_str = values.get("number", "0").strip()
    if num_str.lower().startswith("0x"):
        num_str = num_str[2:]
    return str(int(num_str, 16))


# ── Windows 文件与路径处理逻辑 ──

def _normalize_path_value(path: str) -> str:
    path = str(path or "").strip().strip('"')
    return os.path.normpath(path) if path else ""


def _path_join(values: dict[str, str]) -> str:
    parts = [values.get(key, "").strip().strip('"') for key in ("a", "b", "c")]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    return os.path.normpath(os.path.join(*parts))


def _path_split(values: dict[str, str]) -> CommandResult:
    path = _normalize_path_value(values.get("path", ""))
    folder = os.path.dirname(os.path.abspath(path)) if path else ""
    filename = os.path.basename(path)
    stem, extension = os.path.splitext(filename)
    return _ok_outputs(
        {
            "output": path,
            "folder": folder,
            "filename": filename,
            "stem": stem,
            "extension": extension,
            "exists": _bool_text(os.path.exists(path)),
        }
    )


def _path_exists(values: dict[str, str]) -> CommandResult:
    path = _normalize_path_value(values.get("path", ""))
    exists = os.path.exists(path) if path else False
    return _ok_outputs({"output": _bool_text(exists), "not": _bool_text(not exists), "path": path})


def _folder_create(values: dict[str, str]) -> CommandResult:
    path = _normalize_path_value(values.get("path", ""))
    if not path:
        raise ValueError("缺少文件夹路径")
    os.makedirs(path, exist_ok=True)
    return _ok_folder(path)


def _file_read_text(values: dict[str, str]) -> CommandResult:
    path = _normalize_path_value(values.get("path", ""))
    encoding = values.get("encoding", "").strip() or "utf-8"
    if not path:
        raise ValueError("缺少文件路径")
    with open(path, encoding=encoding) as fh:
        text = fh.read()
    return _ok_outputs(
        {
            "output": text,
            "length": str(len(text)),
            "empty": _bool_text(not bool(text)),
            "path": path,
            "folder": os.path.dirname(os.path.abspath(path)),
            "filename": os.path.basename(path),
        }
    )


def _file_write_text(values: dict[str, str]) -> CommandResult:
    path = _normalize_path_value(values.get("path", ""))
    if not path:
        raise ValueError("缺少文件路径")
    text = values.get("text", "")
    encoding = values.get("encoding", "").strip() or "utf-8"
    mode_text = values.get("mode", "").strip().lower()
    mode = "a" if mode_text in {"append", "追加"} else "w"
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, mode, encoding=encoding) as fh:
        fh.write(text)
    return _ok_outputs(
        {
            "output": path,
            "path": path,
            "folder": os.path.dirname(os.path.abspath(path)),
            "filename": os.path.basename(path),
            "exists": _bool_text(os.path.exists(path)),
            "length": str(len(text)),
            "mode": "追加" if mode == "a" else "覆盖",
        }
    )


# ── 自动加载增强和扩展电池 ─────────────────────────────────────────────────────

def _load_extra_processors() -> None:
    """Merge enhanced and extended processors into the main registry."""
    import copy as _copy
    try:
        from .enhanced_definitions import get_enhanced_definitions as _ged
        _enhanced = _ged()
        for k, v in _enhanced.items():
            if k not in PROCESSOR_DEFINITIONS:
                if not v.safety.capability:
                    object.__setattr__(v.safety, "capability", f"chain.processor.{k}")
                PROCESSOR_DEFINITIONS[k] = v
    except Exception:
        pass

    try:
        from .extended_definitions import get_extended_definitions as _ged2
        _extended = _ged2()
        for k, v in _extended.items():
            if k not in PROCESSOR_DEFINITIONS:
                if not v.safety.capability:
                    object.__setattr__(v.safety, "capability", f"chain.processor.{k}")
                PROCESSOR_DEFINITIONS[k] = v
    except Exception:
        pass

_load_extra_processors()
