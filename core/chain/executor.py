"""Action-chain processor execution dispatch and built-in processor implementations.

Extracted from :mod:`core.chain.registry` in 2026-06-20 to separate the
execution engine from the processor definition registry.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
from typing import Any

from core.command_registry import CommandResult

from .processors_data import execute_extra_data_processor as _execute_data_processor
from .processors_datetime import execute_extra_datetime_processor as _execute_datetime_processor
from .processors_encoding import execute_extra_encoding_processor as _execute_encoding_processor
from .processors_encoding import execute_extra_system_processor as _execute_system_processor
from .processors_files import execute_extra_file_processor as _execute_file_processor
from .processors_math import execute_extra_list_processor as _execute_list_processor
from .processors_math import execute_extra_math_processor as _execute_math_processor
from .processors_structured import execute_extra_json_processor as _execute_json_processor
from .processors_text import execute_extra_text_processor as _execute_text_processor
from .processors_validation import execute_extra_validation_processor as _execute_validation_processor
from .registry import (
    DEFAULT_PYTHON_CELL_SOURCE,
    EXTERNAL_PROCESSOR_HANDLERS,
    _base_convert,
    _dec_to_hex,
    _hex_to_dec,
)

logger = logging.getLogger(__name__)

_EXTERNAL_PROCESSOR_TIMEOUT_SECONDS = 30.0


def execute_chain_processor(
    processor_id: str,
    args: dict[str, Any],
    source: str = "",
    cancel_event=None,
) -> CommandResult:
    processor_id = str(processor_id or "").strip()
    values = {str(k): v for k, v in dict(args or {}).items()}
    if cancel_event is not None:
        values["__cancel_event"] = cancel_event
    try:
        if _is_cancelled(cancel_event):
            return CommandResult(success=False, message="已取消", display_type="text", error="cancelled")
        external_handler = EXTERNAL_PROCESSOR_HANDLERS.get(processor_id)
        if external_handler is not None:
            return _execute_external_with_timeout(processor_id, external_handler, values, cancel_event)
        if processor_id == "python_cell":
            return _execute_python_cell(source or DEFAULT_PYTHON_CELL_SOURCE, values)
        if processor_id == "panel_node":
            return _ok(_panel_node(values))
        if processor_id == "text_input":
            return _text_input(values)
        if processor_id == "assert_not_empty":
            text = _value_to_text(values.get("text", ""))
            if text:
                return _ok(text)
            message = _value_to_text(values.get("message", "")) or "输入为空。"
            return CommandResult(success=False, message=message, display_type="text", error=message)
        if processor_id == "coalesce_value":
            return _ok(_coalesce_value(values))
        if processor_id == "type_convert":
            return _ok(_type_convert(values))
        if processor_id == "bool_and":
            return _ok_bool(all(_to_bool(values.get(k, "")) for k in ("a", "b")))
        if processor_id == "bool_or":
            return _ok_bool(any(_to_bool(values.get(k, "")) for k in ("a", "b")))
        if processor_id == "bool_not":
            return _ok_bool(not _to_bool(values.get("value", "")))
        if processor_id == "compare_value":
            return _compare_values(values)
        if processor_id == "if_else":
            return _conditional_branch(values)
        if processor_id == "loop_repeat":
            return _ok(_loop_repeat(values))
        if processor_id == "loop_counter":
            return _ok(_loop_counter(values))
        if processor_id == "text_template":
            return _ok(_text_template(values))
        if processor_id == "text_slice":
            return _ok(_text_slice(values))
        if processor_id == "regex_extract":
            return _regex_extract(values)
        if processor_id == "text_case":
            return _ok(_text_case(values))
        if processor_id == "text_join":
            return _ok(_text_join(values))
        if processor_id == "text_len":
            return _ok(str(_text_len(values)))
        if processor_id == "text_split":
            return _ok(_text_split(values))
        if processor_id == "text_lines":
            return _ok(_text_lines(values))
        if processor_id.startswith("img_"):
            return _run_img_op(processor_id, values)
        if processor_id == "num_input":
            return _num_input(values)
        if processor_id.startswith("math_"):
            return _run_math(processor_id, values)
        if processor_id.startswith("series_"):
            return _run_series(processor_id, values)
        if processor_id.startswith("list_"):
            return _run_list(processor_id, values)
        if processor_id == "base_convert":
            return _coerce_processor_result(_base_convert(values), processor_id)
        if processor_id == "dec_to_hex":
            return _coerce_processor_result(_dec_to_hex(values), processor_id)
        if processor_id == "hex_to_dec":
            return _coerce_processor_result(_hex_to_dec(values), processor_id)
        if processor_id == "logger_node":
            return _ok(_logger_node(values))
        if processor_id == "sleep_node":
            return _sleep_node(values, cancel_event)
        return _execute_extra_processor(processor_id, values)
    except Exception as exc:
        logger.error("Processor execution error: %s - %s: %s", processor_id, type(exc).__name__, exc, exc_info=True)
        return CommandResult(success=False, message=f"执行失败: {exc}", display_type="text", error=str(exc))


def _execute_extra_processor(processor_id: str, values: dict[str, Any]) -> CommandResult:
    if processor_id.startswith("text_"):
        return _coerce_processor_result(_execute_text_processor(processor_id, values), processor_id)
    if processor_id.startswith("file_") or processor_id.startswith("folder_") or processor_id.startswith("path_"):
        return _coerce_processor_result(_execute_file_processor(processor_id, values), processor_id)
    if processor_id.startswith(("bool_", "if_", "conditional_", "coalesce_", "loop_", "compare_", "assert_", "type_")):
        return _coerce_processor_result(_execute_data_processor(processor_id, values), processor_id)
    if processor_id.startswith("math_") or processor_id.startswith("series_") or processor_id.startswith("num_"):
        return _coerce_processor_result(_execute_math_processor(processor_id, values), processor_id)
    if processor_id.startswith("list_"):
        return _coerce_processor_result(_execute_list_processor(processor_id, values), processor_id)
    if processor_id.startswith("http_") or processor_id.startswith("json_") or processor_id in {"url_encode"}:
        return _coerce_processor_result(_execute_json_processor(processor_id, values), processor_id)
    if processor_id.startswith("encoding_"):
        return _coerce_processor_result(_execute_encoding_processor(processor_id, values), processor_id)
    if processor_id.startswith("datetime_"):
        return _coerce_processor_result(_execute_datetime_processor(processor_id, values), processor_id)
    if processor_id.startswith("sys_"):
        return _coerce_processor_result(_execute_system_processor(processor_id, values), processor_id)
    if processor_id.startswith("validation_"):
        return _coerce_processor_result(_execute_validation_processor(processor_id, values), processor_id)
    return CommandResult(
        success=False, message=f"未知处理器: {processor_id}", display_type="text", error="unknown_processor"
    )


def _coerce_processor_result(result: Any, processor_id: str) -> CommandResult:
    if isinstance(result, CommandResult):
        return result
    if result is None:
        return CommandResult(
            success=False,
            message=f"未知处理器: {processor_id}",
            display_type="text",
            error="unknown_processor",
        )
    return _ok(_value_to_text(result))


def _try_json_parse(value: str) -> Any:
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _execute_external_with_timeout(
    processor_id: str,
    handler: Any,
    values: dict[str, Any],
    cancel_event: Any,
) -> CommandResult:
    result = handler(values)
    if isinstance(result, dict):
        return CommandResult(
            success=True, message=json.dumps(result, ensure_ascii=False), display_type="json", payload=result
        )
    if isinstance(result, CommandResult):
        return result
    return CommandResult(success=True, message=str(result), display_type="text")


def _normalize_external_processor_result(result: Any) -> CommandResult:
    if isinstance(result, CommandResult):
        return result
    return CommandResult(success=True, message=str(result), display_type="text")


def _ok(message: str = "") -> CommandResult:
    return CommandResult(success=True, message=message, display_type="text")


def _ok_bool(value: bool) -> CommandResult:
    return CommandResult(
        success=True, message="true" if value else "false", display_type="text", payload={"value": value}
    )


def _ok_file(path: str) -> CommandResult:
    return CommandResult(success=True, message=path, display_type="text", payload={"file": path})


def _ok_folder(path: str) -> CommandResult:
    return CommandResult(success=True, message=path, display_type="text", payload={"folder": path})


def _ok_list(items: list[str]) -> CommandResult:
    text = "\n".join(items)
    return CommandResult(success=True, message=text, display_type="text", payload={"items": items})


def _ok_outputs(outputs: dict[str, str]) -> CommandResult:
    text = str(outputs.get("output", outputs.get("text", "")))
    return CommandResult(success=True, message=text, display_type="text", payload=outputs)


def _processor_error_result(error: str, detail: str = "") -> CommandResult:
    return CommandResult(success=False, message=error, display_type="text", error=error, payload={"detail": detail})


def _string_values(values: dict[str, Any]) -> list[str]:
    return [str(v) for v in values.values() if v is not None and v != ""]


def _value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v is not None)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _execute_python_cell(source: str, values: dict[str, Any]) -> CommandResult:
    try:
        compiled = compile(source, "<action_chain_python_cell>", "exec")
        local_vars: dict[str, Any] = {"inputs": values, "outputs": {}}
        exec(compiled, {"__builtins__": __builtins__}, local_vars)
        outputs = local_vars.get("outputs", local_vars.get("output", {}))
        if isinstance(outputs, dict):
            return _ok_outputs(outputs)
        return _ok_outputs({"output": str(outputs)})
    except Exception as exc:
        logger.debug("电池执行失败: %s", exc, exc_info=True)
        return CommandResult(success=False, message=f"脚本电池执行失败: {exc}", display_type="text", error=str(exc))


def _parse_python_cell_metadata(source: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"title": "脚本电池", "inputs": ["input"], "outputs": ["output"]}
    for line in source.splitlines():
        line = line.strip()
        if line.startswith("TITLE ="):
            metadata["title"] = ast.literal_eval(line.partition("=")[2].strip())
        elif line.startswith("INPUTS ="):
            metadata["inputs"] = ast.literal_eval(line.partition("=")[2].strip())
        elif line.startswith("OUTPUTS ="):
            metadata["outputs"] = ast.literal_eval(line.partition("=")[2].strip())
    return metadata


def _panel_node(values: dict[str, str]) -> str:
    text = values.get("text", "")
    return _value_to_text(values.get("input", "")) + ("\n" + text if text else "")


def _text_input(values: dict[str, str]) -> CommandResult:
    text = values.get("text", "")
    return _ok(text)


def _coalesce_value(values: dict[str, str]) -> str:
    return _value_to_text(values.get("value", "") or values.get("fallback", ""))


def _type_convert(values: dict[str, str]) -> str:
    value = values.get("value", "")
    target = values.get("target", "string").strip().lower()
    if target in ("int", "integer", "整数"):
        try:
            return str(int(float(value)))
        except (ValueError, TypeError):
            return "0"
    if target in ("float", "小数"):
        try:
            return str(float(value))
        except (ValueError, TypeError):
            return "0.0"
    if target in ("bool", "boolean", "布尔"):
        return "true" if _to_bool(value) else "false"
    if target in ("json", "JSON"):
        parsed = _try_json_parse(_value_to_text(value))
        if parsed is not None:
            return json.dumps(parsed, ensure_ascii=False)
        return "{}"
    return str(value)


def _conditional_branch(values: dict[str, str]) -> CommandResult:
    condition = _to_bool(values.get("condition", ""))
    true_value = _value_to_text(values.get("true_value", ""))
    false_value = _value_to_text(values.get("false_value", ""))
    if condition:
        return _ok(true_value)
    return _ok(false_value)


def _logger_node(values: dict[str, str]) -> str:
    text = values.get("text", "")
    level = values.get("level", "info").strip().lower()
    logger.info("[Action Chain Log] [%s] %s", level.upper(), text)
    return text


def _sleep_node(values: dict[str, str], cancel_event=None) -> CommandResult:
    ms_str = values.get("ms", "1000").strip()
    try:
        ms = max(0.0, min(600000.0, float(ms_str)))
    except ValueError:
        ms = 1000.0
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        if _is_cancelled(cancel_event):
            return CommandResult(success=False, message="已取消", display_type="text", error="cancelled")
        time.sleep(min(0.05, max(0.0, end - time.monotonic())))
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


def _is_cancelled(cancel_event) -> bool:
    return bool(cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)())


def _to_bool(value: Any) -> bool:
    text = _value_to_text(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "on", "是", "真", "对", "启用"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", "假", "错", "禁用", ""}:
        return False
    return False


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _compare_values(values: dict[str, str]) -> CommandResult:
    a = _value_to_text(values.get("a", ""))
    b = _value_to_text(values.get("b", ""))
    operator = values.get("operator", "等于").strip()
    result = False
    try:
        num_a = float(a) if a else 0.0
        num_b = float(b) if b else 0.0
        can_numeric = True
    except (ValueError, TypeError):
        can_numeric = False
    if operator in {"等于", "==", "=", "eq"}:
        result = a == b
    elif operator in {"不等于", "!=", "ne"}:
        result = a != b
    elif operator in {"大于", ">", "gt"} and can_numeric:
        result = num_a > num_b
    elif operator in {"小于", "<", "lt"} and can_numeric:
        result = num_a < num_b
    elif operator in {"大于等于", ">=", "gte"} and can_numeric:
        result = num_a >= num_b
    elif operator in {"小于等于", "<=", "lte"} and can_numeric:
        result = num_a <= num_b
    elif operator in {"包含", "contains"}:
        result = b in a
    elif operator in {"正则", "regex", "match"}:
        try:
            result = bool(re.search(b, a))
        except re.error:
            result = False
    return _ok_bool(result)


def _loop_repeat(values: dict[str, str]) -> str:
    input_text = _value_to_text(values.get("input", ""))
    count = 0
    count_str = values.get("count", "1").strip()
    try:
        count = max(0, int(float(count_str)))
    except (ValueError, TypeError):
        logger.debug("silent except in executor.py:389", exc_info=True)
    delimiter = values.get("delimiter", ",")
    return delimiter.join([input_text] * count)


def _loop_counter(values: dict[str, str]) -> str:
    start = 0
    end = 0
    step = 1
    try:
        start = int(float(values.get("start", "0")))
        end = int(float(values.get("end", "0")))
        step = max(1, int(float(values.get("step", "1"))))
    except (ValueError, TypeError):
        logger.debug("silent except in executor.py:404", exc_info=True)
    items: list[str] = []
    i = start
    while i < end if end > start else i > end:
        items.append(str(i))
        i += step
    delimiter = values.get("delimiter", "\n")
    return delimiter.join(items)


def _text_template(values: dict[str, str]) -> str:
    template = values.get("template", "")
    input_text = _value_to_text(values.get("input", ""))
    text = values.get("text", "")
    return template.replace("{input}", input_text).replace("{text}", text or input_text)


def _text_slice(values: dict[str, str]) -> str:
    text = _value_to_text(values.get("text", ""))
    start = _optional_int(values.get("start"), 0)
    end_str = values.get("end", "").strip()
    end = _optional_int(end_str, len(text)) if end_str else len(text)
    step = _optional_int(values.get("step"), 1)
    return text[start:end:step]


def _regex_extract(values: dict[str, str]) -> CommandResult:
    text = _value_to_text(values.get("text", ""))
    pattern = values.get("pattern", "")
    group = _optional_int(values.get("group"), 0)
    try:
        m = re.search(pattern, text)
        if m:
            return _ok(m.group(group))
        return _ok("")
    except re.error as e:
        return CommandResult(success=False, message=f"正则错误: {e}", display_type="text", error=str(e))


def _optional_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except (ValueError, AttributeError, TypeError):
        return default


def _text_case(values: dict[str, str]) -> str:
    text = _value_to_text(values.get("text", ""))
    case = values.get("case", "lower").strip().lower()
    if case in ("upper", "大写"):
        return text.upper()
    if case in ("lower", "小写"):
        return text.lower()
    if case in ("title", "首字母大写"):
        return text.title()
    return text


def _text_join(values: dict[str, str]) -> str:
    inputs = [v for v in _string_values(values) if v]
    delim = values.get("delimiter", values.get("separator", ", "))
    return delim.join(inputs)


def _text_len(values: dict[str, str]) -> int:
    return len(_value_to_text(values.get("text", "")))


def _text_split(values: dict[str, str]) -> str:
    text = _value_to_text(values.get("text", ""))
    delimiter = values.get("delimiter", values.get("separator", ","))
    items = text.split(delimiter) if delimiter else list(text)
    return "\n".join(item.strip() for item in items)


def _text_lines(values: dict[str, str]) -> str:
    text = _value_to_text(values.get("text", ""))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _run_img_op(processor_id: str, values: dict[str, Any]) -> CommandResult:
    if processor_id == "img_resize":
        return _img_resize(values)
    if processor_id == "img_convert":
        return _img_convert(values)
    if processor_id == "img_watermark":
        return _img_watermark(values)
    if processor_id == "img_crop":
        return _img_crop(values)
    if processor_id == "img_rotate":
        return _img_rotate(values)
    return _processor_error_result(f"未知图像处理器: {processor_id}")


def _img_resize(values: dict[str, Any]) -> CommandResult:
    path = _value_to_text(values.get("path", ""))
    width = _optional_int(values.get("width", ""), 0)
    height = _optional_int(values.get("height", ""), 0)
    if not path or not width or not height:
        return _processor_error_result("缺少必要参数: path, width, height")
    try:
        from PIL import Image

        with Image.open(path) as source_img:
            img = source_img.resize((width, height), Image.Resampling.LANCZOS)
        new_path = os.path.splitext(path)[0] + f"_{width}x{height}.png"
        img.save(new_path)
        return _ok_file(new_path)
    except Exception as exc:
        logger.debug("图片调整失败: %s", exc, exc_info=True)
        return _processor_error_result(f"图片调整失败: {exc}")


def _img_convert(values: dict[str, Any]) -> CommandResult:
    path = _value_to_text(values.get("path", ""))
    fmt = values.get("format", "png").strip().lower()
    if not path:
        return _processor_error_result("缺少必要参数: path")
    try:
        from PIL import Image

        img = Image.open(path)
        new_path = os.path.splitext(path)[0] + f".{fmt}"
        img.save(new_path)
        return _ok_file(new_path)
    except Exception as exc:
        logger.debug("图片转换失败: %s", exc, exc_info=True)
        return _processor_error_result(f"图片转换失败: {exc}")


def _img_watermark(values: dict[str, Any]) -> CommandResult:
    path = _value_to_text(values.get("path", ""))
    text = _value_to_text(values.get("text", ""))
    if not path or not text:
        return _processor_error_result("缺少必要参数: path, text")
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(path)
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        position = values.get("position", "bottom_right")
        x, y = 10.0, 10.0
        if "right" in position:
            x = img.width - tw - 10
        elif "center" in position:
            x = (img.width - tw) // 2
        if "bottom" in position:
            y = img.height - th - 10
        elif "center" in position:
            y = (img.height - th) // 2
        draw.text((x, y), text, fill=(255, 255, 255, 128), font=font)
        new_path = os.path.splitext(path)[0] + "_watermark.png"
        img.save(new_path)
        return _ok_file(new_path)
    except Exception as exc:
        logger.debug("水印添加失败: %s", exc, exc_info=True)
        return _processor_error_result(f"水印添加失败: {exc}")


def _img_crop(values: dict[str, Any]) -> CommandResult:
    path = _value_to_text(values.get("path", ""))
    box = _value_to_text(values.get("box", "")).strip()
    if not path or not box:
        return _processor_error_result("缺少必要参数: path, box")
    try:
        from PIL import Image

        img = Image.open(path)
        parts = box.split(",")
        if len(parts) != 4:
            return _processor_error_result("裁剪区域必须包含 left,top,right,bottom 四个整数")
        left, top, right, bottom = (float(int(p.strip())) for p in parts)
        coords = (left, top, right, bottom)
        new_img = img.crop(coords)
        new_path = os.path.splitext(path)[0] + "_crop.png"
        new_img.save(new_path)
        return _ok_file(new_path)
    except Exception as exc:
        logger.debug("图片裁剪失败: %s", exc, exc_info=True)
        return _processor_error_result(f"图片裁剪失败: {exc}")


def _img_rotate(values: dict[str, Any]) -> CommandResult:
    path = _value_to_text(values.get("path", ""))
    angle = _optional_int(values.get("angle", ""), 90)
    if not path:
        return _processor_error_result("缺少必要参数: path")
    try:
        from PIL import Image

        img = Image.open(path)
        new_img = img.rotate(angle, expand=True)
        new_path = os.path.splitext(path)[0] + f"_rotate{angle}.png"
        new_img.save(new_path)
        return _ok_file(new_path)
    except Exception as exc:
        logger.debug("图片旋转失败: %s", exc, exc_info=True)
        return _processor_error_result(f"图片旋转失败: {exc}")


def _to_num(value: Any) -> float:
    text = _value_to_text(value).strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def _parse_list(value: Any) -> list[str]:
    text = _value_to_text(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.debug("silent except in executor.py:625", exc_info=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_nested_list(value: Any) -> list[list[str]]:
    text = _value_to_text(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [[str(item) for item in sub] if isinstance(sub, list) else [str(sub)] for sub in parsed]
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.debug("silent except in executor.py:638", exc_info=True)
    return [[line.strip() for line in text.splitlines() if line.strip()]]


def _stringify_json_value(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _num_input(values: dict[str, str]) -> CommandResult:
    number = values.get("number", "0").strip()
    try:
        val = float(number)
        return _ok(str(val) if val != int(val) else str(int(val)))
    except ValueError:
        return _processor_error_result("无效的数字输入")


def _math_add(values: dict[str, str]) -> CommandResult:
    return _ok(str(_to_num(values.get("a", 0)) + _to_num(values.get("b", 0))))


def _math_sub(values: dict[str, str]) -> CommandResult:
    return _ok(str(_to_num(values.get("a", 0)) - _to_num(values.get("b", 0))))


def _math_mul(values: dict[str, str]) -> CommandResult:
    return _ok(str(_to_num(values.get("a", 0)) * _to_num(values.get("b", 0))))


def _math_div(values: dict[str, str]) -> CommandResult:
    b = _to_num(values.get("b", 0))
    if b == 0:
        return _processor_error_result("除数不能为0")
    return _ok(str(_to_num(values.get("a", 0)) / b))


def _math_pow(values: dict[str, str]) -> CommandResult:
    return _ok(str(_to_num(values.get("base", 0)) ** _to_num(values.get("exp", 0))))


def _math_mod(values: dict[str, str]) -> CommandResult:
    b = _to_num(values.get("b", 0))
    if b == 0:
        return _processor_error_result("模数不能为0")
    return _ok(str(_to_num(values.get("a", 0)) % b))


def _series_arith(values: dict[str, str]) -> CommandResult:
    start = _to_num(values.get("start", 0))
    step = _to_num(values.get("step", 1))
    count = int(_to_num(values.get("count", 1)))
    items = [str(start + step * i) for i in range(count)]
    return _ok_list(items)


def _series_geom(values: dict[str, str]) -> CommandResult:
    start = _to_num(values.get("start", 1))
    ratio = _to_num(values.get("ratio", 2))
    count = int(_to_num(values.get("count", 1)))
    items = [str(start * (ratio**i)) for i in range(count)]
    return _ok_list(items)


def _list_create(values: dict[str, str]) -> str:
    return "\n".join(str(v) for v in values.values() if v is not None and str(v).strip())


def _list_item(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    index = int(_to_num(values.get("index", 0)))
    if not items:
        return ""
    try:
        return items[index]
    except IndexError:
        return ""


def _list_len(values: dict[str, str]) -> int:
    return len(_parse_list(values.get("list", "")))


def _list_rev(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    return "\n".join(reversed(items))


def _list_unique_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    seen = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return "\n".join(result)


def _list_sort_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    mode = values.get("mode", "text").strip().lower()
    reverse = values.get("reverse", "false").strip().lower() in ("true", "1")
    if mode in ("num", "number", "数字"):
        try:
            items.sort(key=lambda x: float(x), reverse=reverse)
        except ValueError:
            items.sort(reverse=reverse)
    else:
        items.sort(reverse=reverse)
    return "\n".join(items)


def _list_filter_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    contains = values.get("contains", "").strip()
    mode = values.get("mode", "keep").strip().lower()
    result = [item for item in items if contains in item]
    if mode in ("remove", "排除"):
        result = [item for item in items if contains not in item]
    return "\n".join(result)


def _list_contains_value(values: dict[str, str]) -> bool:
    items = _parse_list(values.get("list", ""))
    value = values.get("value", "").strip()
    return value in items


def _list_template_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    template = values.get("template", "{item}")
    result: list[str] = []
    for idx, item in enumerate(items):
        result.append(template.replace("{序号}", str(idx + 1)).replace("{index}", str(idx)).replace("{item}", item))
    return "\n".join(result)


def _list_concat_values(values: dict[str, str]) -> str:
    result: list[str] = []
    for key in sorted(values.keys()):
        vals = _parse_list(values[key])
        result.extend(vals)
    return "\n".join(result)


def _list_slice_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    start = _optional_int(values.get("start"), 0)
    end = _optional_int(values.get("end"), len(items))
    step = _optional_int(values.get("step"), 1)
    return "\n".join(items[start:end:step])


def _list_zip_values(values: dict[str, str]) -> str:
    lists: list[list[str]] = []
    for key in sorted(values.keys()):
        vals = _parse_list(values[key])
        lists.append(vals)
    if not lists:
        return ""
    rows: list[str] = []
    for i in range(max(len(lst) for lst in lists)):
        parts = [lst[i] if i < len(lst) else "" for lst in lists]
        rows.append("\t".join(parts))
    return "\n".join(rows)


def _list_flatten_values(values: dict[str, str]) -> str:
    items = _parse_nested_list(values.get("list", ""))
    flat: list[str] = []
    for sub in items:
        flat.extend(sub)
    return "\n".join(flat)


def _list_join_values(values: dict[str, str]) -> str:
    items = _parse_list(values.get("list", ""))
    delim = values.get("delimiter", ", ")
    return delim.join(items)


def _run_math(processor_id: str, values: dict[str, Any]) -> CommandResult:
    return _coerce_processor_result(_execute_math_processor(processor_id, values), processor_id)


def _run_series(processor_id: str, values: dict[str, Any]) -> CommandResult:
    return _coerce_processor_result(_execute_math_processor(processor_id, values), processor_id)


def _run_list(processor_id: str, values: dict[str, Any]) -> CommandResult:
    return _coerce_processor_result(_execute_list_processor(processor_id, values), processor_id)


__all__ = [
    "execute_chain_processor",
]
