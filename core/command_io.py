"""Pure command-panel input/output contracts."""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from core.command_registry import CommandDefinition, CommandParam, CommandResult
from core.data_models import ShortcutItem

OUTPUT_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
INPUT_TOKEN_RE = re.compile(r"\{\{input(?::([^}]+))?\}\}", re.IGNORECASE)
MAX_OUTPUT_VALUE_CHARS = 64 * 1024
MAX_OUTPUT_TOTAL_CHARS = 256 * 1024
RUNTIME_ATTRS = (
    "_runtime_param_values",
    "_runtime_input_values",
    "_runtime_selected_files",
    "_chain_values",
    "_destructive_command_confirmed",
)


@dataclass
class CommandInvocationSnapshot:
    command_id: str = ""
    command_title: str = ""
    raw_input: str = ""
    source: str = ""
    args_text: str = ""
    args: dict[str, str] = field(default_factory=dict)
    masked_args: dict[str, str] = field(default_factory=dict)
    input_values: dict[str, str] = field(default_factory=dict)
    clipboard_text: str = ""
    clipboard_kind: str = ""
    clipboard_files: list[str] = field(default_factory=list)
    clipboard_html: str = ""
    selected_text: str = ""
    selected_text_method: str = ""
    selected_files: list[str] = field(default_factory=list)
    chain_values: dict[str, str] = field(default_factory=dict)
    context_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandOutputArtifact:
    success: bool = True
    text: str = ""
    output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: str = ""
    command: str = ""
    error: str = ""
    outputs: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    json_text: str = ""
    table_tsv: str = ""


def command_params_from_shortcut(shortcut: ShortcutItem | None) -> list[CommandParam]:
    if shortcut is None:
        return []
    return [
        CommandParam(**raw) for raw in ShortcutItem._normalize_command_params(getattr(shortcut, "command_params", []))
    ]


def mask_sensitive_args(args: dict[str, Any], params: list[CommandParam] | None) -> dict[str, str]:
    sensitive_names = {param.name for param in params or [] if bool(getattr(param, "sensitive", False))}
    masked = {}
    for key, value in dict(args or {}).items():
        name = str(key)
        masked[name] = "******" if name in sensitive_names and str(value or "") else str(value or "")
    return masked


def remembered_args(args: dict[str, Any], params: list[CommandParam] | None) -> dict[str, str]:
    param_map = {param.name: param for param in params or []}
    remembered = {}
    for key, value in dict(args or {}).items():
        name = str(key)
        param = param_map.get(name)
        if param is not None and (
            bool(getattr(param, "sensitive", False)) or not bool(getattr(param, "remember", True))
        ):
            continue
        remembered[name] = str(value or "")
    return remembered


def has_sensitive_args(args: dict[str, Any], params: list[CommandParam] | None) -> bool:
    sensitive_names = {param.name for param in params or [] if bool(getattr(param, "sensitive", False))}
    return any(str(name) in sensitive_names and str(value or "") for name, value in dict(args or {}).items())


def resolve_param_default(
    param: CommandParam,
    *,
    context_meta: dict[str, Any] | None = None,
    last_args: dict[str, Any] | None = None,
) -> str:
    if bool(getattr(param, "sensitive", False)):
        return str(param.default or "")
    context = dict(context_meta or {})
    source = str(getattr(param, "source", "") or "").lower().strip()
    if source == "last" and last_args and param.name in last_args:
        return str(last_args.get(param.name) or "")
    if source == "clipboard":
        return str(context.get("clipboard_text") or "")
    if source == "selected_text":
        return str(context.get("selected_text") or "")
    selected_files = list(context.get("selected_files") or [])
    if source == "selected_file" and selected_files:
        return str(selected_files[0])
    if source == "selected_file_dir" and selected_files:
        return os.path.dirname(str(selected_files[0]))
    return str(param.default or "")


def discover_input_variables(command_text: str) -> list[tuple[str, str]]:
    variables: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in INPUT_TOKEN_RE.finditer(command_text or ""):
        prompt = str(match.group(1) or "").strip()
        key = prompt or "input"
        if key in seen:
            continue
        seen.add(key)
        variables.append((key, prompt))
    return variables


def build_invocation_snapshot(
    request: Any,
    command_def: CommandDefinition | None = None,
    shortcut: ShortcutItem | None = None,
) -> CommandInvocationSnapshot:
    existing = getattr(request, "invocation", None)
    if isinstance(existing, CommandInvocationSnapshot):
        return existing

    context_meta = dict(getattr(request, "context_meta", {}) or {})
    params = (
        list(getattr(command_def, "params", []) or [])
        if command_def is not None
        else command_params_from_shortcut(shortcut)
    )
    args = {str(k): str(v) for k, v in dict(getattr(request, "args", {}) or {}).items()}
    input_values = _string_dict(context_meta.get("input_values"))
    input_values.update(_string_dict(getattr(request, "input_values", None)))
    chain_values = _string_dict(context_meta.get("chain_values"))
    chain_values.update(_string_dict(getattr(request, "chain_values", None)))
    selected_files = [str(path) for path in list(context_meta.get("selected_files") or [])]
    clipboard_files = [str(path) for path in list(context_meta.get("clipboard_files") or [])]
    return CommandInvocationSnapshot(
        command_id=str(getattr(request, "command_id", "") or getattr(shortcut, "id", "") or ""),
        command_title=str(getattr(command_def, "title", "") or getattr(shortcut, "name", "") or ""),
        raw_input=str(getattr(request, "raw_input", "") or ""),
        source=str(getattr(request, "source", "") or getattr(command_def, "source", "") or ""),
        args_text=str(getattr(request, "args_text", "") or ""),
        args=args,
        masked_args=mask_sensitive_args(args, params),
        input_values=input_values,
        clipboard_text=str(context_meta.get("clipboard_text") or ""),
        clipboard_kind=str(context_meta.get("clipboard_kind") or ""),
        clipboard_files=clipboard_files,
        clipboard_html=str(context_meta.get("clipboard_html") or ""),
        selected_text=str(context_meta.get("selected_text") or ""),
        selected_text_method=str(context_meta.get("selected_text_method") or ""),
        selected_files=selected_files,
        chain_values=chain_values,
        context_meta=_safe_context_meta(context_meta),
    )


def prepare_runtime_shortcut(shortcut: ShortcutItem, snapshot: CommandInvocationSnapshot) -> ShortcutItem:
    runtime = copy.copy(shortcut)
    for attr in RUNTIME_ATTRS:
        if hasattr(runtime, attr):
            delattr(runtime, attr)
    runtime._runtime_param_values = dict(snapshot.args)  # type: ignore[attr-defined]
    runtime._runtime_input_values = dict(snapshot.input_values)  # type: ignore[attr-defined]
    runtime._runtime_selected_files = list(snapshot.selected_files)  # type: ignore[attr-defined]
    runtime._chain_values = dict(snapshot.chain_values)  # type: ignore[attr-defined]
    if bool(snapshot.context_meta.get("destructive_confirmed", False)):
        runtime._destructive_command_confirmed = True  # type: ignore[attr-defined]
    return runtime


def build_output_artifact(result: CommandResult) -> CommandOutputArtifact:
    payload = result.payload if isinstance(result.payload, dict) else {}
    display_type = str(result.display_type or "text").lower().strip()
    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")
    exit_code = "" if payload.get("exit_code") is None else str(payload.get("exit_code"))
    command = str(payload.get("command") or "")
    text = _display_text(result, payload)
    output = stdout or text or str(result.message or result.error or "")
    outputs = normalize_outputs(payload.get("outputs") or {})
    json_text = ""
    table_tsv = ""

    if display_type == "table":
        table_tsv = _table_tsv(payload)
        table_csv = _table_csv(payload)
        rows = payload.get("rows") or []
        if table_tsv:
            outputs.setdefault("table.tsv", table_tsv)
        if table_csv:
            outputs.setdefault("table.csv", table_csv)
        outputs.setdefault("table.rows_json", _stable_json(rows))
        if rows:
            outputs.setdefault("table.first_row_json", _stable_json(rows[0]))
    elif display_type == "kv":
        items = payload.get("items") or []
        outputs.setdefault("items_json", _stable_json(items))
        for item in items:
            if isinstance(item, list | tuple) and len(item) >= 2:
                key = _output_key(str(item[0]))
                if key:
                    outputs.setdefault(key, str(item[1]))
    elif display_type == "json":
        json_text = str(payload.get("formatted") or "")
        compact = str(payload.get("compact") or "")
        if not json_text and "data" in payload:
            json_text = _stable_json(payload.get("data"), indent=2)
        if not compact and "data" in payload:
            compact = _stable_json(payload.get("data"))
        if json_text:
            outputs.setdefault("json", json_text)
        if compact:
            outputs.setdefault("json.compact", compact)

    standard_outputs = {
        "success": "true" if result.success else "false",
        "output": output,
        "text": text,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "command": command,
        "error": result.error or "",
    }
    if json_text:
        standard_outputs["json"] = json_text
    if table_tsv:
        standard_outputs["table.tsv"] = table_tsv
    outputs.update(normalize_outputs(standard_outputs))
    outputs = normalize_outputs(outputs)
    return CommandOutputArtifact(
        success=bool(result.success),
        text=text,
        output=output,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        command=command,
        error=str(result.error or ""),
        outputs=outputs,
        files=_string_list(payload.get("files")),
        folders=_string_list(payload.get("folders")),
        urls=_string_list(payload.get("urls")),
        json_text=json_text,
        table_tsv=table_tsv,
    )


def normalize_outputs(outputs: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    total = 0
    truncated = False
    if not isinstance(outputs, dict):
        return normalized
    for key, value in outputs.items():
        key_text = str(key or "").strip()
        if not key_text or not OUTPUT_KEY_RE.match(key_text) or value is None:
            continue
        value_text = _output_value(value)
        if len(value_text) > MAX_OUTPUT_VALUE_CHARS:
            value_text = value_text[:MAX_OUTPUT_VALUE_CHARS]
            truncated = True
        if total + len(value_text) > MAX_OUTPUT_TOTAL_CHARS:
            remaining = max(0, MAX_OUTPUT_TOTAL_CHARS - total)
            value_text = value_text[:remaining]
            truncated = True
        normalized[key_text] = value_text
        total += len(value_text)
        if total >= MAX_OUTPUT_TOTAL_CHARS:
            break
    if truncated:
        normalized["outputs_truncated"] = "true"
    return normalized


def chain_values_from_artifact(index: int, artifact: CommandOutputArtifact) -> dict[str, str]:
    values: dict[str, str] = {}
    for prefix in (f"{index}", "prev"):
        values[f"{prefix}.success"] = "true" if artifact.success else "false"
        values[f"{prefix}.exit_code"] = artifact.exit_code
        values[f"{prefix}.stdout"] = artifact.stdout
        values[f"{prefix}.stderr"] = artifact.stderr
        values[f"{prefix}.output"] = artifact.output
        values[f"{prefix}.text"] = artifact.text
        values[f"{prefix}.error"] = artifact.error
        if artifact.json_text:
            values[f"{prefix}.json"] = artifact.json_text
        if artifact.table_tsv:
            values[f"{prefix}.table.tsv"] = artifact.table_tsv
        for name, value in artifact.outputs.items():
            values[f"{prefix}.outputs.{name}"] = value
        _expand_list(values, prefix, "files", artifact.files)
        _expand_list(values, prefix, "folders", artifact.folders)
        _expand_list(values, prefix, "urls", artifact.urls)
    return values


def _safe_context_meta(context_meta: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    skip = {
        "clipboard_text",
        "clipboard_html",
        "selected_text",
        "input_values",
        "chain_values",
        "destructive_confirmed",
    }
    for key, value in dict(context_meta or {}).items():
        if key in skip:
            continue
        if isinstance(value, str | int | float | bool) or value is None:
            safe[key] = value
        elif key in ("selected_files", "clipboard_files"):
            safe[key] = [str(item) for item in list(value or [])]  # type: ignore[assignment]
        else:
            safe[key] = str(value)
    return safe


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(k)}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _display_text(result: CommandResult, payload: dict[str, Any]) -> str:
    if str(result.display_type or "").lower() == "log":
        parts = [str(payload.get("stdout") or ""), str(payload.get("stderr") or "")]
        text = "\n".join(part for part in parts if part)
        return text or str(result.message or result.error or "")
    return str(result.message or result.error or "")


def _table_tsv(payload: dict[str, Any]) -> str:
    columns, matrix = _table_matrix(payload)
    if not matrix and not columns:
        return ""
    lines = ["\t".join(str(col) for col in columns)]
    lines.extend("\t".join(str(value) for value in row) for row in matrix)
    return "\n".join(lines)


def _table_csv(payload: dict[str, Any]) -> str:
    columns, matrix = _table_matrix(payload)
    if not matrix and not columns:
        return ""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([str(col) for col in columns])
    for row in matrix:
        writer.writerow([str(value) for value in row])
    return buffer.getvalue()


def _table_matrix(payload: dict[str, Any]) -> tuple[list[Any], list[list[Any]]]:
    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    if not rows and not columns:
        return [], []
    matrix = []
    if rows and isinstance(rows[0], dict):
        columns = columns or list(rows[0].keys())
        matrix = [[row.get(col, "") for col in columns] for row in rows]
    else:
        matrix = [list(row) if isinstance(row, list | tuple) else [row] for row in rows]
        if not columns:
            col_count = max([len(row) for row in matrix] or [1])
            columns = [f"列 {idx + 1}" for idx in range(col_count)]
    return list(columns), matrix


def _output_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return key if key and OUTPUT_KEY_RE.match(key) else ""


def _output_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, dict | list | tuple):
        return _stable_json(value)
    try:
        return str(value)
    except Exception:
        return ""


def _stable_json(value: Any, *, indent: int | None = None) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=None if indent else (",", ":"), indent=indent
        )
    except Exception:
        return str(value)


def _expand_list(values: dict[str, str], prefix: str, name: str, items: list[str]) -> None:
    values[f"{prefix}.{name}.count"] = str(len(items))
    for idx, item in enumerate(items):
        values[f"{prefix}.{name}.{idx}"] = str(item)
