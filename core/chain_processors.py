"""Built-in processor nodes for action chains."""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from core.command_registry import CommandResult

logger = logging.getLogger(__name__)

ChainProcessorHandler = Callable[[dict[str, Any]], CommandResult | dict[str, Any] | str]


@dataclass(frozen=True)
class ChainPortDefinition:
    id: str
    label: str = ""
    kind: str = "text"
    required: bool = False
    multiple: bool = False
    default: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "multiple": self.multiple,
            "default": self.default,
            "description": self.description,
        }


@dataclass(frozen=True)
class ChainParamDefinition:
    id: str
    label: str
    kind: str = "text"
    default: str = ""
    choices: list[str] = field(default_factory=list)
    multiline: bool = False
    required: bool = False
    placeholder: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "choices": list(self.choices),
            "multiline": self.multiline,
            "required": self.required,
            "placeholder": self.placeholder,
            "description": self.description,
        }


@dataclass(frozen=True)
class ChainProcessorSafety:
    level: str = "safe"
    reads_files: bool = False
    writes_files: bool = False
    network: bool = False
    executes_code: bool = False
    requires_confirmation: bool = False
    capability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "reads_files": self.reads_files,
            "writes_files": self.writes_files,
            "network": self.network,
            "executes_code": self.executes_code,
            "requires_confirmation": self.requires_confirmation,
            "capability": self.capability,
        }


@dataclass(frozen=True)
class ChainProcessorExample:
    title: str
    args: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "args": dict(self.args), "expected": dict(self.expected)}


@dataclass(frozen=True, init=False)
class ChainProcessorDefinition:
    id: str
    title: str
    inputs: list[ChainPortDefinition]
    outputs: list[ChainPortDefinition]
    source: str
    category: str
    description: str
    params: list[ChainParamDefinition]
    safety: ChainProcessorSafety
    examples: list[ChainProcessorExample]

    def __init__(
        self,
        id: str,
        title: str,
        inputs: list[str | ChainPortDefinition] | None = None,
        outputs: list[str | ChainPortDefinition] | None = None,
        source: str = "",
        *,
        category: str = "",
        description: str = "",
        params: list[ChainParamDefinition] | None = None,
        safety: ChainProcessorSafety | None = None,
        examples: list[ChainProcessorExample] | None = None,
    ):
        processor_id = str(id or "").strip()
        input_defs = [_port_definition(processor_id, value, "input") for value in list(inputs or [])]
        output_defs = [_port_definition(processor_id, value, "output") for value in list(outputs or ["output"])]
        param_defs = list(params) if params is not None else [_param_definition(processor_id, port) for port in input_defs]
        example_defs = list(examples) if examples is not None else [_default_example(str(title or processor_id), param_defs)]
        object.__setattr__(self, "id", processor_id)
        object.__setattr__(self, "title", str(title or processor_id))
        object.__setattr__(self, "inputs", input_defs)
        object.__setattr__(self, "outputs", output_defs)
        object.__setattr__(self, "source", str(source or ""))
        object.__setattr__(self, "category", category or _processor_category(processor_id))
        object.__setattr__(self, "description", description or _processor_description(processor_id, str(title or processor_id)))
        object.__setattr__(self, "params", param_defs)
        object.__setattr__(self, "safety", safety or _processor_safety(processor_id))
        object.__setattr__(self, "examples", example_defs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "params": [param.to_dict() for param in self.params],
            "safety": self.safety.to_dict(),
            "examples": [example.to_dict() for example in self.examples],
            "source": self.source,
        }


TEXT_OUTPUTS = ["output", "length", "empty"]
BOOL_OUTPUTS = ["output", "not"]
LIST_OUTPUTS = ["output", "count", "first", "last", "items_json"]
NUMBER_OUTPUTS = ["output"]
FILE_OUTPUTS = ["output", "path", "folder", "filename", "exists"]
FOLDER_OUTPUTS = ["output", "path", "exists"]
JSON_OUTPUTS = ["output"]


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
        "text": "文本",
        "template": "模板",
        "path": "路径",
        "filepath": "文件路径",
        "folder": "文件夹",
        "filename": "文件名",
        "url": "网址",
        "headers": "请求头",
        "data": "数据",
        "json": "结构化文本",
        "json_str": "结构化文本",
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
        return "JSON 文本。"
    if port in {"path", "filepath"}:
        return "本地文件或文件夹路径。"
    return f"{_default_port_label(port)}输入。"


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
        return ["text", "number", "bool", "json", "list"]
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
    if port in {"value", "input"}:
        return "any"
    if port in {"width", "height", "x", "y", "start", "end", "index", "count", "ms", "angle", "length", "a", "b", "number", "base", "exp", "from_base", "to_base", "ratio"} and (
        processor_id.startswith(("math_", "series_", "num_"))
        or processor_id in {"base_convert", "dec_to_hex", "hex_to_dec", "loop_counter", "loop_repeat"}
    ):
        return "number"
    if port in {"width", "height", "x", "y", "index", "ms", "angle"}:
        return "number"
    if processor_id.startswith("bool_") and port in {"value", "a", "b"}:
        return "bool"
    if port == "condition":
        return "bool"
    return "text"


def _early_processor_output_kind(processor_id: str, port: str) -> str:
    processor_id = str(processor_id or "")
    port = str(port or "").lower().strip()
    if port in {"length", "count", "ms", "exit_code"}:
        return "number"
    if port in {"empty", "not", "exists", "success"}:
        return "bool"
    if port == "folder":
        return "folder"
    if port in {"path", "output"} and processor_id in {"folder_path_input", "folder_create"}:
        return "folder"
    if port == "path":
        return "file"
    if port in {"items_json"} or processor_id.startswith("list_") and processor_id not in {"list_item", "list_len", "list_contains"}:
        return "list"
    if processor_id in {"text_split", "text_lines"} and port == "output":
        return "list"
    if processor_id.startswith(("math_", "series_", "num_")) and port == "output":
        return "number"
    if processor_id.startswith("bool_") or processor_id == "compare_value":
        return "bool" if port == "output" else "text"
    if processor_id in {"file_path_input", "path_join", "file_write_text", "img_resize", "img_convert", "img_watermark", "img_crop", "img_rotate", "http_download"}:
        return "file" if port in {"output", "path"} else "text"
    if processor_id in {"json_get", "json_parse", "json_set"} and port == "output":
        return "json"
    return "text"


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
    "json_get": ChainProcessorDefinition("json_get", "取结构化字段", ["json", "path"], JSON_OUTPUTS),
    "json_set": ChainProcessorDefinition("json_set", "设置结构化字段", ["json", "path", "value"], JSON_OUTPUTS),
    "http_get": ChainProcessorDefinition("http_get", "网页请求", ["url", "headers"], TEXT_OUTPUTS),
    "http_post": ChainProcessorDefinition("http_post", "提交请求", ["url", "data", "headers"], TEXT_OUTPUTS),
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
    return ChainProcessorDefinition(
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
    except Exception:
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
            return _ok(_loop_counter(_string_values(values)))

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
            return _ok(_http_get(_string_values(values)))
        if processor_id == "http_post":
            return _ok(_http_post(_string_values(values)))
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

    except Exception as exc:
        return CommandResult(success=False, message=str(exc), display_type="text", error=str(exc))
    return CommandResult(success=False, message=f"未知处理节点: {processor_id}", display_type="text", error="Unknown processor")


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
            "output": output,
            "count": str(len(items)),
            "first": items[0] if items else "",
            "last": items[-1] if items else "",
            "items_json": items,
        }
    )


def _ok_outputs(outputs: dict[str, Any]) -> CommandResult:
    normalized = {str(k): _value_to_text(v) for k, v in dict(outputs or {}).items() if str(k).strip()}
    first = next(iter(normalized.values()), "")
    return CommandResult(
        success=True,
        message=first,
        display_type="text",
        payload={"stdout": first, "outputs": normalized},
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
    t = values.get("type", "文本").strip().lower()
    if t in {"int", "整数"}:
        return str(int(float(val))) if val else "0"
    elif t in {"float", "小数", "数字"}:
        return str(float(val)) if val else "0.0"
    elif t in {"bool", "boolean", "布尔", "真假"}:
        return _bool_text(_to_bool(val))
    elif t in {"json", "结构化文本"}:
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
    logger.info(f"[Action Chain Log] [{level.upper()}] {text}")
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
        return [part for part in text.split(delimiter)]
    return [part for part in re.split(r"\s+", text.strip()) if part]


def _text_lines(values: dict[str, str]) -> list[str]:
    return [line for line in values.get("text", "").splitlines()]


# ── 图像处理逻辑（安全包装以防 Pillow 未安装） ──

def _run_img_op(op_func, values):
    try:
        import PIL  # noqa: F401 - trigger ImportError if PIL not installed
    except ImportError:
        raise ImportError("检测到您的系统未安装 Pillow 库。请在 cmd/terminal 中运行 'pip install Pillow' 以执行本图像处理节点。")
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
    if not isinstance(data, (dict, list)):
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
            if not isinstance(current[index], (dict, list)):
                current[index] = {}
            current = current[index]
        else:
            if part not in current or not isinstance(current.get(part), (dict, list)):
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


def _http_get(values: dict[str, str]) -> str:
    url = values.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    headers_str = values.get("headers", "").strip()
    headers = {}
    if headers_str:
        headers = json.loads(headers_str)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def _http_post(values: dict[str, str]) -> str:
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
        return response.read().decode("utf-8")


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
    if isinstance(value, (list, dict)):
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
        raise ValueError(f"幂运算失败: {e}")


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
