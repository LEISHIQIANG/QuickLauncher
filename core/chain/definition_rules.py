"""Pure defaults used while constructing action-chain processor schemas."""

from __future__ import annotations

from typing import Any


def build_parts(
    processor_id: str,
    title: str,
    inputs: list[Any],
    outputs: list[Any],
    *,
    port_type: type,
    param_type: type,
    safety_type: type,
    example_type: type,
) -> tuple[list[Any], list[Any], list[Any], Any, Any]:
    input_defs = [_port(processor_id, value, "input", port_type) for value in inputs]
    output_defs = [_port(processor_id, value, "output", port_type) for value in outputs]
    params = [_param(processor_id, port, param_type) for port in input_defs]
    safety = processor_safety(processor_id, safety_type)
    example = example_type(title=f"{title} 示例", args={p.id: p.default for p in params if p.default})
    return input_defs, output_defs, params, safety, example


def _port(processor_id: str, value: Any, direction: str, port_type: type) -> Any:
    if isinstance(value, port_type):
        return value
    port_id = str(value or "").strip()
    kind = input_kind(processor_id, port_id) if direction == "input" else output_kind(processor_id, port_id)
    return port_type(
        id=port_id,
        label=port_label(port_id),
        kind=kind,
        required=direction == "input"
        and processor_id not in {"text_input", "num_input", "bool_value"}
        and port_id in {"path", "filepath", "url", "json", "json_str", "text", "list", "a", "b"},
        multiple=port_id in {"input", "list", "items", "values"},
        default=port_default(processor_id, port_id),
        description=port_description(port_id, direction),
        role=port_role(port_id, direction),
    )


def _param(processor_id: str, port: Any, param_type: type) -> Any:
    choices = param_choices(processor_id, port.id)
    kind = param_kind(processor_id, port.id, port.kind, choices)
    return param_type(
        id=port.id,
        label=port.label or port_label(port.id),
        kind=kind,
        default=port.default,
        choices=choices,
        multiline=port.id in {"text", "template", "input", "headers", "data", "json", "json_str", "list"},
        required=port.required,
        placeholder={
            "json": '{"key":"value"}',
            "list": "每行一项",
            "file": "选择或输入文件路径",
            "folder": "选择或输入文件夹路径",
            "url": "https://example.com",
            "number": "0",
        }.get(port.kind, ""),
        description=port.description,
    )


def processor_category(processor_id: str) -> str:
    if processor_id in {"python_cell", "panel_node", "logger_node", "sleep_node"}:
        return "输入与调试"
    if processor_id.startswith("text_") or processor_id == "regex_extract":
        return "文本"
    if processor_id.startswith(("bool_", "compare_", "if_", "conditional_", "assert_", "coalesce_", "type_", "loop_")):
        return "逻辑"
    if processor_id.startswith("img_"):
        return "图像"
    if processor_id.startswith(("http_", "json_")) or processor_id == "url_encode":
        return "网络与结构化"
    if processor_id.startswith(("math_", "series_", "num_", "list_")) or processor_id in {
        "base_convert",
        "dec_to_hex",
        "hex_to_dec",
    }:
        return "数学与列表"
    if processor_id.startswith(("file_", "folder_", "path_")):
        return "文件与路径"
    return "通用"


def processor_description(processor_id: str, title: str) -> str:
    return {
        "python_cell": "执行本地 Python 脚本片段并返回自定义端口输出。",
        "http_get": "向指定 URL 发起 GET 请求并输出响应文本。",
        "http_post": "向指定 URL 提交请求体并输出响应文本。",
        "http_download": "下载 URL 指向的文件到本地目录。",
        "file_read_text": "读取文本文件内容。",
        "file_write_text": "写入或追加文本到本地文件。",
        "folder_create": "创建本地文件夹。",
    }.get(processor_id, f"{title} 电池。")


def processor_safety(processor_id: str, safety_type: type) -> Any:
    capability = f"chain.processor.{processor_id}" if processor_id else ""
    if processor_id == "python_cell":
        return safety_type("dangerous", executes_code=True, requires_confirmation=True, capability="chain.script_cell")
    if processor_id in {"http_get", "http_post"}:
        return safety_type("caution", network=True, capability=capability)
    if processor_id == "http_download":
        return safety_type(
            "dangerous", writes_files=True, network=True, requires_confirmation=True, capability=capability
        )
    if processor_id in {"img_resize", "img_watermark", "img_crop", "img_rotate", "file_write_text", "folder_create"}:
        return safety_type("dangerous", writes_files=True, requires_confirmation=True, capability=capability)
    if processor_id == "img_convert":
        return safety_type("caution", reads_files=True, writes_files=True, capability=capability)
    if processor_id == "file_read_text":
        return safety_type("caution", reads_files=True, capability=capability)
    if processor_id in {"file_path_input", "folder_path_input", "path_exists", "path_split"}:
        return safety_type("safe", reads_files=True, capability=capability)
    return safety_type("safe", capability=capability)


def port_label(port: str) -> str:
    return {
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
    }.get(str(port or ""), str(port or ""))


def port_default(processor_id: str, port: str) -> str:
    return {
        ("sleep_node", "ms"): "1000",
        ("bool_value", "value"): "false",
        ("loop_repeat", "count"): "1",
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
    }.get((processor_id, port), "")


def port_description(port: str, direction: str) -> str:
    if direction == "output":
        return f"{port_label(port)}输出。"
    if port == "headers":
        return "JSON 对象格式的请求头。"
    if port in {"json", "json_str"}:
        return "JSON 数据。"
    if port in {"path", "filepath"}:
        return "本地文件或文件夹路径。"
    return f"{port_label(port)}输入。"


def port_role(port: str, direction: str) -> str:
    port = str(port or "").lower().strip()
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
    if port.startswith(("files.", "folders.", "urls.")) or port == "items_json":
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


def param_choices(processor_id: str, port: str) -> list[str]:
    return {
        ("text_case", "mode"): ["upper", "lower", "title", "trim"],
        ("compare_value", "operator"): ["等于", "不等于", "大于", "小于", "包含", "不包含"],
        ("url_encode", "mode"): ["encode", "decode"],
        ("list_sort", "mode"): ["升序", "降序", "数字", "数字降序"],
        ("list_flatten", "mode"): ["递归", "一级"],
        ("file_write_text", "mode"): ["overwrite", "append"],
        ("img_convert", "format"): ["png", "jpg", "webp", "bmp"],
        ("img_watermark", "position"): ["bottom-right", "top-left", "center"],
        ("type_convert", "type"): ["string", "number", "bool", "json", "list"],
    }.get((processor_id, port), [])


def param_kind(processor_id: str, port: str, kind: str, choices: list[str]) -> str:
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


def input_kind(processor_id: str, port: str) -> str:
    p = str(port or "").lower().strip()
    if processor_id.startswith("json_") and p == "path":
        return "text"
    if processor_id in {"folder_path_input", "folder_create"} and p == "path":
        return "folder"
    if p in {"filepath", "path"}:
        return "file"
    if p == "save_dir":
        return "folder"
    if p == "url":
        return "url"
    if p in {"json", "json_str"}:
        return "json"
    if p == "list":
        return "list"
    if processor_id.startswith("bool_") and p in {"value", "a", "b"}:
        return "bool"
    if p == "condition":
        return "bool"
    if p in {"value", "input"}:
        return "any"
    numeric = {
        "width",
        "height",
        "x",
        "y",
        "start",
        "end",
        "step",
        "index",
        "count",
        "ms",
        "angle",
        "length",
        "group",
        "a",
        "b",
        "number",
        "base",
        "exp",
        "from_base",
        "to_base",
        "ratio",
    }
    numeric_processors = {
        "base_convert",
        "dec_to_hex",
        "hex_to_dec",
        "loop_counter",
        "loop_repeat",
        "text_slice",
        "regex_extract",
        "list_slice",
    }
    if p in numeric and (processor_id.startswith(("math_", "series_", "num_")) or processor_id in numeric_processors):
        return "number"
    if p in {"width", "height", "x", "y", "index", "ms", "angle"}:
        return "number"
    return "text"


def output_kind(processor_id: str, port: str) -> str:
    p = str(port or "").lower().strip()
    if p in {"length", "count", "ms", "exit_code", "status_code"}:
        return "number"
    if p in {"empty", "not", "exists", "success"}:
        return "bool"
    if p == "headers" and processor_id.startswith("http_"):
        return "json"
    if p == "folder":
        return "folder"
    if p in {"path", "output"} and processor_id in {"folder_path_input", "folder_create"}:
        return "folder"
    if p == "path":
        return "file"
    if p == "items_json":
        return "list"
    if p in {"first", "last"}:
        return "text"
    if processor_id in {"text_split", "text_lines", "loop_counter", "series_arith", "series_geom"} and p == "output":
        return "list"
    if (
        processor_id.startswith("list_")
        and processor_id not in {"list_item", "list_len", "list_contains", "list_join"}
        and p == "output"
    ):
        return "list"
    if processor_id in {"text_len", "list_len", "hex_to_dec"} and p == "output":
        return "number"
    if processor_id in {"list_contains", "path_exists"} and p == "output":
        return "bool"
    if processor_id.startswith(("math_", "num_")) and p == "output":
        return "number"
    if processor_id.startswith("bool_") or processor_id == "compare_value":
        return "bool" if p == "output" else "text"
    file_processors = {
        "file_path_input",
        "path_join",
        "path_split",
        "file_write_text",
        "img_resize",
        "img_convert",
        "img_watermark",
        "img_crop",
        "img_rotate",
        "http_download",
    }
    if processor_id in file_processors:
        return "file" if p in {"output", "path"} else "text"
    if processor_id in {"json_get", "json_parse", "json_set"} and p == "output":
        return "json"
    return "text"
