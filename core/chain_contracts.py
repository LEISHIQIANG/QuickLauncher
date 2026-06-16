"""Action-chain port contracts and connection validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.chain_processors import (
    DEFAULT_PYTHON_CELL_SOURCE,
    processor_definition,
    processor_input_ports,
    processor_output_ports,
    python_cell_metadata,
)
from core.chain_values import ChainValueKind
from core.command_io import discover_input_variables
from core.data_models import ShortcutItem, ShortcutType

STANDARD_OUTPUT_PORTS = [
    "success",
    "output",
    "stdout",
    "stderr",
    "exit_code",
    "error",
    "files.0",
    "folders.0",
    "urls.0",
]
DIRECT_OUTPUT_PORTS = set(STANDARD_OUTPUT_PORTS)

TEXT_TARGET_COMPATIBLE_KINDS = {"any", "text", "json", "file", "folder", "url", "list", "number", "bool"}
PARAM_TOKEN_RE = re.compile(r"\{\{param:([^}:]+)(?::q)?\}\}", re.IGNORECASE)


@dataclass(frozen=True)
class ChainPortSpec:
    id: str
    direction: str
    kind: str = "text"
    multiple: bool = False
    label: str = ""
    description: str = ""
    role: str = "data"


@dataclass(frozen=True)
class ChainConnectionIssue:
    code: str
    message: str
    connection_id: str = ""


def input_port_specs_for_node(node: dict, shortcuts: dict[str, ShortcutItem]) -> list[ChainPortSpec]:
    if _node_type(node) == "processor":
        processor_id = str(node.get("processor_id") or "")
        if processor_id == "python_cell":
            ports = python_cell_metadata(str(node.get("source") or DEFAULT_PYTHON_CELL_SOURCE))["inputs"]
            return [
                ChainPortSpec(
                    port, "input", ChainValueKind.ANY, _allows_multiple(port), port, "脚本电池自定义输入。", "data"
                )
                for port in ports
            ]
        definition = processor_definition(processor_id)
        if definition is not None:
            return [
                ChainPortSpec(
                    port.id, "input", port.kind, port.multiple, port.label or port.id, port.description, port.role
                )
                for port in definition.inputs
            ]
        ports = processor_input_ports(processor_id)
        return [
            ChainPortSpec(port, "input", _processor_input_kind(processor_id, port), _allows_multiple(port))
            for port in ports
        ]

    shortcut = shortcuts.get(str(node.get("shortcut_id") or ""))
    ports: list[ChainPortSpec] = [  # type: ignore[no-redef]
        ChainPortSpec("input", "input", "text", True, "输入值", "传给快捷方式的主输入值，通常是字符串。", "primary")
    ]
    if shortcut is None:
        return ports  # type: ignore[no-any-return]

    if shortcut.type == ShortcutType.FILE:
        ports.append(
            ChainPortSpec(
                "open_file",
                "input",
                "file",
                True,
                "待打开文件",
                "传入一个或多个文件路径，由文件快捷方式打开。",
                "collection",
            )
        )
    elif shortcut.type == ShortcutType.FOLDER:
        ports.append(
            ChainPortSpec(
                "open_file",
                "input",
                "file",
                True,
                "传入文件",
                "传入一个或多个文件路径，由文件夹快捷方式处理。",
                "collection",
            )
        )

    existing = {"input", "open_file"}
    for param in ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", []) or []):
        name = str(param.get("name") or "").strip()
        if not name or name in existing:
            continue
        existing.add(name)
        ports.append(
            ChainPortSpec(
                name, "input", _param_kind(param), False, str(param.get("label") or ""), "命令参数输入。", "parameter"
            )
        )

    command_text = " ".join(
        str(value or "")
        for value in (
            getattr(shortcut, "command", ""),
            getattr(shortcut, "target_args", ""),
            getattr(shortcut, "preferred_browser_args", ""),
        )
    )
    for key, prompt in discover_input_variables(command_text):
        port = "input" if key == "input" else key
        if port in existing:
            continue
        existing.add(port)
        ports.append(
            ChainPortSpec(
                port, "input", "text", port == "input", prompt, "从命令模板变量生成的字符串输入。", "parameter"
            )
        )
    for match in PARAM_TOKEN_RE.finditer(command_text):
        port = str(match.group(1) or "").strip()
        if not port or port in existing:
            continue
        existing.add(port)
        ports.append(
            ChainPortSpec(port, "input", "text", False, port, "从 {{param:name}} 变量生成的字符串输入。", "parameter")
        )
    return ports  # type: ignore[no-any-return]


def output_port_specs_for_node(node: dict, shortcuts: dict[str, ShortcutItem] | None = None) -> list[ChainPortSpec]:
    if _node_type(node) == "processor":
        processor_id = str(node.get("processor_id") or "")
        if processor_id == "python_cell":
            ports = python_cell_metadata(str(node.get("source") or DEFAULT_PYTHON_CELL_SOURCE))["outputs"]
            return [
                ChainPortSpec(port, "output", ChainValueKind.ANY, False, port, "脚本电池自定义输出。", "data")
                for port in ports
            ]
        definition = processor_definition(processor_id)
        if definition is not None:
            return [
                ChainPortSpec(
                    port.id, "output", port.kind, port.multiple, port.label or port.id, port.description, port.role
                )
                for port in definition.outputs
            ]
        ports = processor_output_ports(processor_id)
        return [ChainPortSpec(port, "output", _processor_output_kind(processor_id, port)) for port in ports]

    shortcut = (shortcuts or {}).get(str(node.get("shortcut_id") or ""))
    if shortcut is None:
        return []
    base = [
        ChainPortSpec(
            "success", "output", "bool", False, "成功状态", "布尔状态。成功为 1/true，失败为 0/false。", "status"
        ),
        ChainPortSpec("output", "output", "text", False, "主输出", "该快捷方式的主结果字符串。", "primary"),
        ChainPortSpec("error", "output", "text", False, "错误信息", "失败时的错误说明；成功时通常为空。", "diagnostic"),
    ]
    if shortcut.type == ShortcutType.COMMAND and bool(getattr(shortcut, "capture_output", False)):
        base.extend(
            [
                ChainPortSpec("stdout", "output", "text", False, "标准输出", "命令进程 stdout 字符串。", "stream"),
                ChainPortSpec("stderr", "output", "text", False, "标准错误", "命令进程 stderr 字符串。", "diagnostic"),
                ChainPortSpec(
                    "exit_code", "output", "number", False, "退出码", "命令进程退出码，通常 0 表示成功。", "status"
                ),
                ChainPortSpec(
                    "files.0", "output", "file", False, "结果文件[0]", "执行结果文件集合的第 0 项。", "collection"
                ),
                ChainPortSpec(
                    "folders.0",
                    "output",
                    "folder",
                    False,
                    "结果文件夹[0]",
                    "执行结果文件夹集合的第 0 项。",
                    "collection",
                ),
                ChainPortSpec(
                    "urls.0", "output", "url", False, "结果 URL[0]", "执行结果 URL 集合的第 0 项。", "collection"
                ),
            ]
        )
    elif shortcut.type == ShortcutType.FILE:
        base.append(
            ChainPortSpec("files.0", "output", "file", False, "结果文件[0]", "文件快捷方式目标路径。", "collection")
        )
    elif shortcut.type == ShortcutType.FOLDER:
        base.append(
            ChainPortSpec(
                "folders.0", "output", "folder", False, "结果文件夹[0]", "文件夹快捷方式目标路径。", "collection"
            )
        )
    elif shortcut.type == ShortcutType.URL:
        base.append(
            ChainPortSpec("urls.0", "output", "url", False, "结果 URL[0]", "URL 快捷方式目标地址。", "collection")
        )
    return _dedupe_specs(base)


def binding_key(source_index: int, source_port: str) -> str:
    source_port = str(source_port or "").strip()
    if source_port in DIRECT_OUTPUT_PORTS:
        return f"{source_index}.{source_port}"
    return f"{source_index}.outputs.{source_port}"


def validate_canvas_connection(
    canvas: dict,
    shortcuts: dict[str, ShortcutItem],
    source_node: str,
    source_port: str,
    target_node: str,
    target_port: str,
    *,
    multi: bool = False,
) -> ChainConnectionIssue | None:
    nodes = {str(node.get("id") or ""): node for node in list(canvas.get("nodes") or []) if isinstance(node, dict)}
    source = nodes.get(str(source_node or ""))
    target = nodes.get(str(target_node or ""))
    if source is None or target is None:
        return ChainConnectionIssue("missing_node", "连接端点不存在。")
    if source is target:
        return ChainConnectionIssue("self_connection", "不能连接同一个节点。")

    source_order = _order(source)
    target_order = _order(target)
    if source_order >= target_order:
        return ChainConnectionIssue("future_dependency", "动作链按从左到右顺序执行，只能连接到后续节点。")

    source_specs = {spec.id: spec for spec in output_port_specs_for_node(source, shortcuts)}
    target_specs = {spec.id: spec for spec in input_port_specs_for_node(target, shortcuts)}
    source_spec = source_specs.get(str(source_port or ""))
    target_spec = target_specs.get(str(target_port or ""))
    if source_spec is None:
        return ChainConnectionIssue("missing_source_port", f"来源端口不可用: {source_port}")
    if target_spec is None:
        return ChainConnectionIssue("missing_target_port", f"目标端口不可用: {target_port}")
    if multi and not target_spec.multiple:
        return ChainConnectionIssue("single_input", f"{target_port} 只能接入一个来源。")
    if not _kinds_compatible(source_spec.kind, target_spec.kind):
        return ChainConnectionIssue(
            "type_mismatch",
            f"{source_port}({_kind_label(source_spec.kind)}) 不能连接到 {target_port}({_kind_label(target_spec.kind)})。",
        )
    return None


def validate_canvas(canvas: dict, shortcuts: dict[str, ShortcutItem]) -> list[ChainConnectionIssue]:
    issues: list[ChainConnectionIssue] = []
    seen = set()
    for connection in list(canvas.get("connections") or []):
        if not isinstance(connection, dict):
            continue
        key = (
            str(connection.get("source_node") or ""),
            str(connection.get("source_port") or ""),
            str(connection.get("target_node") or ""),
            str(connection.get("target_port") or ""),
        )
        if key in seen:
            issues.append(ChainConnectionIssue("duplicate", "重复连接。", str(connection.get("id") or "")))
            continue
        seen.add(key)
        issue = validate_canvas_connection(
            canvas,
            shortcuts,
            key[0],
            key[1],
            key[2],
            key[3],
            multi=_target_has_other_incoming(canvas, key[2], key[3], str(connection.get("id") or "")),
        )
        if issue is not None:
            issues.append(ChainConnectionIssue(issue.code, issue.message, str(connection.get("id") or "")))
    return issues


def validate_step_bindings(
    steps: list[dict],
    index: int,
    step: dict,
    target: ShortcutItem | None,
    shortcut_map: dict[str, ShortcutItem],
) -> str:
    target_ports = {spec.id: spec for spec in _step_input_specs(step, target, shortcut_map)}
    for port, binding in dict(step.get("param_bindings") or {}).items():
        target_spec = target_ports.get(str(port or ""))
        if target_spec is None:
            if target is not None:
                target_spec = ChainPortSpec(str(port or ""), "input", "text")
            else:
                return f"目标端口不可用: {port}"
        for source_ref in _binding_items(binding):
            error = _validate_binding_source(steps, index, source_ref, target_spec, shortcut_map)
            if error:
                return error

    input_binding = step.get("input_binding", "")
    if input_binding:
        target_spec = target_ports.get("input")
        if target_spec is None:
            return "目标端口不可用: input"
        for source_ref in _binding_items(input_binding):
            error = _validate_binding_source(steps, index, source_ref, target_spec, shortcut_map)
            if error:
                return error
    return ""


def _step_input_specs(
    step: dict, target: ShortcutItem | None, shortcut_map: dict[str, ShortcutItem]
) -> list[ChainPortSpec]:
    if _node_type(step) == "processor":
        return input_port_specs_for_node(step, shortcut_map)
    if target is None:
        return []
    return input_port_specs_for_node({"node_type": "shortcut", "shortcut_id": target.id}, {target.id: target})


def _validate_binding_source(
    steps: list[dict],
    target_index: int,
    binding: str,
    target_spec: ChainPortSpec,
    shortcut_map: dict[str, ShortcutItem],
) -> str:
    source_index, source_port, custom_output = _parse_binding(binding, target_index)
    if source_index < 1:
        return ""
    if source_index >= target_index:
        return f"绑定来源必须是更早的步骤: {binding}"
    source_step = steps[source_index - 1] if source_index <= len(steps) else None
    if not isinstance(source_step, dict):
        return f"绑定来源步骤不存在: {binding}"
    source_specs = {spec.id: spec for spec in _step_output_specs(source_step, shortcut_map)}
    source_spec = source_specs.get(source_port)
    if source_spec is None:
        if custom_output:
            source_spec = ChainPortSpec(source_port, "output", "text")
        else:
            return f"来源端口不可用: {binding}"
    if not _kinds_compatible(source_spec.kind, target_spec.kind):
        return (
            f"端口类型不兼容: {binding}({_kind_label(source_spec.kind)}) "
            f"-> {target_spec.id}({_kind_label(target_spec.kind)})"
        )
    return ""


def _step_output_specs(step: dict, shortcut_map: dict[str, ShortcutItem]) -> list[ChainPortSpec]:
    standard = [
        ChainPortSpec("success", "output", "bool"),
        ChainPortSpec("output", "output", "text"),
        ChainPortSpec("stdout", "output", "text"),
        ChainPortSpec("stderr", "output", "text"),
        ChainPortSpec("exit_code", "output", "number"),
        ChainPortSpec("error", "output", "text"),
        ChainPortSpec("files.0", "output", "file"),
        ChainPortSpec("folders.0", "output", "folder"),
        ChainPortSpec("urls.0", "output", "url"),
    ]
    if _node_type(step) == "processor":
        return _dedupe_specs(output_port_specs_for_node(step, shortcut_map) + standard)
    target = shortcut_map.get(str(step.get("shortcut_id") or ""))
    if target is None:
        return standard
    return _dedupe_specs(
        output_port_specs_for_node({"node_type": "shortcut", "shortcut_id": target.id}, {target.id: target}) + standard
    )


def _parse_binding(binding: str, current_index: int) -> tuple[int, str, bool]:
    binding = str(binding or "").strip()
    if binding.startswith("prev."):
        source_index = current_index - 1
        port = binding[5:]
    elif "." in binding:
        raw_index, port = binding.split(".", 1)
        try:
            source_index = int(raw_index)
        except (TypeError, ValueError):
            return 0, "", False
    else:
        return 0, "", False
    custom_output = port.startswith("outputs.")
    if port.startswith("outputs."):
        port = port[8:]
    return source_index, port, custom_output


def _binding_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _target_has_other_incoming(canvas: dict, target_node: str, target_port: str, current_id: str) -> bool:
    return any(
        str(connection.get("id") or "") != current_id
        and str(connection.get("target_node") or "") == target_node
        and str(connection.get("target_port") or "") == target_port
        for connection in list(canvas.get("connections") or [])
        if isinstance(connection, dict)
    )


def _node_type(node: dict) -> str:
    value = str(node.get("node_type") or "shortcut").strip().lower()
    return value if value in ("shortcut", "processor") else "shortcut"


def _order(node: dict) -> int:
    try:
        return int(node.get("order", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _allows_multiple(port: str) -> bool:
    port = str(port or "").strip().lower()
    return port in {"input", "list", "items", "values"}


def _param_kind(param: dict) -> str:
    param_type = str(param.get("type") or "text").lower().strip()
    validator = str(param.get("validator") or "").lower().strip()
    if validator in {"file", "path"} or param_type == "file":
        return "file"
    if validator == "folder" or param_type == "folder":
        return "folder"
    if validator == "url":
        return "url"
    if validator in {"number", "port"} or param_type == "number":
        return "number"
    if validator == "json":
        return "json"
    if param_type == "bool":
        return "bool"
    return "text"


def _processor_input_kind(processor_id: str, port: str) -> str:
    processor_id = str(processor_id or "")
    port = str(port or "").lower().strip()
    if processor_id in {"folder_path_input", "folder_create"} and port == "path":
        return "folder"
    if port in {"filepath", "path"}:
        return "file"
    if port in {"save_dir"}:
        return "folder"
    if port == "url":
        return "url"
    if port in {"json", "json_str", "headers", "data"} or processor_id.startswith("json_"):
        return "json" if port in {"json", "json_str"} else "text"
    if processor_id.startswith(("math_", "series_", "num_")) or processor_id in {
        "base_convert",
        "dec_to_hex",
        "hex_to_dec",
        "loop_counter",
    }:
        if port in {"a", "b", "start", "step", "count", "number", "base", "exp", "from_base", "to_base", "ratio"}:
            return "number"
    if processor_id.startswith("bool_") or processor_id in {"compare_value", "if_else"}:
        if port in {"value", "a", "b", "condition"}:
            return "bool" if processor_id.startswith("bool_") or port == "condition" else "text"
    if processor_id == "loop_repeat" and port == "count":
        return "number"
    if port in {"width", "height", "x", "y", "start", "end", "index", "count", "ms", "angle", "length"}:
        return "number"
    if port == "list":
        return "list"
    if port in {"value", "input"}:
        return "any"
    return "text"


def _processor_output_kind(processor_id: str, port: str) -> str:
    processor_id = str(processor_id or "")
    port = str(port or "").lower().strip()
    if port in {"length", "count", "ms", "status_code"}:
        return "number"
    if port in {"empty", "not", "exists"}:
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
    if processor_id.startswith(("math_", "series_", "num_")) or processor_id in {
        "base_convert",
        "dec_to_hex",
        "hex_to_dec",
        "text_len",
        "list_len",
        "loop_counter",
    }:
        return "number" if port == "output" else "text"
    if processor_id.startswith("bool_") or processor_id == "compare_value":
        return "bool" if port == "output" else "text"
    if processor_id.startswith("list_") and processor_id not in {"list_item", "list_len", "list_contains"}:
        return "list"
    if processor_id in {"text_split", "text_lines"}:
        return "list" if port == "output" else "number" if port == "count" else "text"
    if processor_id in {"panel_node", "text_input", "file_read_text"}:
        if port == "length":
            return "number"
        if port == "empty":
            return "bool"
    if processor_id == "path_split":
        if port == "folder":
            return "folder"
        if port in {"filename", "stem", "extension"}:
            return "text"
        return "file" if port == "output" else _standard_port_kind(port)
    if processor_id == "path_exists":
        if port == "path":
            return "file"
        return "bool" if port == "output" else "text"
    if processor_id in {"file_path_input", "path_join", "file_write_text"}:
        return "file" if port in {"output", "path"} else _standard_port_kind(port)
    if processor_id == "file_read_text":
        if port in {"length"}:
            return "number"
        if port in {"empty"}:
            return "bool"
        if port == "path":
            return "file"
        if port == "folder":
            return "folder"
        return "text"
    if processor_id in {"img_resize", "img_convert", "img_watermark", "img_crop", "img_rotate", "http_download"}:
        return "file"
    if processor_id in {"json_get", "json_parse"}:
        return "json" if port == "output" else "text"
    return _standard_port_kind(port)


def _standard_port_kind(port: str) -> str:
    port = str(port or "").lower().strip()
    if port == "success":
        return "bool"
    if port == "exit_code":
        return "number"
    if port.startswith("files."):
        return "file"
    if port.startswith("folders."):
        return "folder"
    if port.startswith("urls."):
        return "url"
    if port in {"json", "table.tsv"}:
        return "json" if port == "json" else "text"
    return "text"


def _kinds_compatible(source: str, target: str) -> bool:
    source = str(source or "text").lower()
    target = str(target or "text").lower()
    if source == target or source == "any" or target == "any":
        return True
    if target == "text" and source in TEXT_TARGET_COMPATIBLE_KINDS:
        return True
    if source in {"file", "folder", "url"} and target == "text":
        return True
    if source == "number" and target == "text":
        return True
    if source == "bool" and target == "text":
        return True
    return False


def _kind_label(kind: str) -> str:
    labels = {
        "any": "任意",
        "text": "字符串",
        "json": "JSON/结构化",
        "file": "文件",
        "folder": "文件夹",
        "url": "URL",
        "list": "列表",
        "number": "数字",
        "bool": "布尔",
    }
    return labels.get(str(kind or ""), str(kind or ""))


def _dedupe_specs(specs: list[ChainPortSpec]) -> list[ChainPortSpec]:
    result = []
    seen = set()
    for spec in specs:
        if spec.id in seen:
            continue
        seen.add(spec.id)
        result.append(spec)
    return result
