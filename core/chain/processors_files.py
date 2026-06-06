"""File and path processors for action chains."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from core.command_registry import CommandResult
from core.path_security import assert_safe_user_path, move_to_trash


def normalize_path_value(path: str) -> str:
    path = str(path or "").strip().strip('"')
    return os.path.normpath(path) if path else ""


def path_join(values: dict[str, str]) -> str:
    parts = [values.get(key, "").strip().strip('"') for key in ("a", "b", "c")]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    return os.path.normpath(os.path.join(*parts))


def path_split(values: dict[str, str]) -> CommandResult:
    path = normalize_path_value(values.get("path", ""))
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


def path_exists(values: dict[str, str]) -> CommandResult:
    path = normalize_path_value(values.get("path", ""))
    exists = os.path.exists(path) if path else False
    return _ok_outputs({"output": _bool_text(exists), "not": _bool_text(not exists), "path": path})


def folder_create(values: dict[str, str]) -> CommandResult:
    path = normalize_path_value(values.get("path", ""))
    if not path:
        raise ValueError("缺少文件夹路径")
    assert_safe_user_path(path, operation="create folder")
    os.makedirs(path, exist_ok=True)
    return ok_folder(path)


def file_read_text(values: dict[str, str]) -> CommandResult:
    path = normalize_path_value(values.get("path", ""))
    encoding = values.get("encoding", "").strip() or "utf-8"
    if not path:
        raise ValueError("缺少文件路径")
    assert_safe_user_path(path, operation="read file")
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


def file_write_text(values: dict[str, str]) -> CommandResult:
    path = normalize_path_value(values.get("path", ""))
    if not path:
        raise ValueError("缺少文件路径")
    text = values.get("text", "")
    encoding = values.get("encoding", "").strip() or "utf-8"
    mode_text = values.get("mode", "").strip().lower()
    mode = "a" if mode_text in {"append", "追加"} else "w"
    assert_safe_user_path(path, operation="write file")
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


def execute_extra_file_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    text_values = _string_values(values)

    if processor_id == "file_copy":
        src = normalize_path_value(text_values.get("src", ""))
        dst = normalize_path_value(text_values.get("dst", ""))
        overwrite = _to_bool(values.get("overwrite", False))
        if not os.path.exists(src):
            raise FileNotFoundError(f"源文件不存在: {src}")
        if os.path.exists(dst) and not overwrite:
            raise FileExistsError(f"目标文件已存在: {dst}")
        assert_safe_user_path(dst, operation="copy file")
        dst_dir = os.path.dirname(dst)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        return ok_file(dst)

    if processor_id == "file_move":
        src = normalize_path_value(text_values.get("src", ""))
        dst = normalize_path_value(text_values.get("dst", ""))
        overwrite = _to_bool(values.get("overwrite", False))
        if not os.path.exists(src):
            raise FileNotFoundError(f"源文件不存在: {src}")
        if os.path.exists(dst) and not overwrite:
            raise FileExistsError(f"目标文件已存在: {dst}")
        assert_safe_user_path(src, operation="move source")
        assert_safe_user_path(dst, operation="move destination")
        dst_dir = os.path.dirname(dst)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        shutil.move(src, dst)
        return ok_file(dst)

    if processor_id == "file_delete":
        path = normalize_path_value(text_values.get("path", ""))
        if not os.path.exists(path):
            return _ok_bool(False)
        move_to_trash(path)
        return _ok_bool(True)

    if processor_id == "file_size":
        path = normalize_path_value(text_values.get("path", ""))
        if not os.path.exists(path):
            raise FileNotFoundError(f"路径不存在: {path}")
        return _ok(str(os.path.getsize(path)))

    if processor_id == "file_list_dir":
        path = normalize_path_value(text_values.get("path", ""))
        pattern = text_values.get("pattern", "*") or "*"
        import glob
        items = glob.glob(os.path.join(path, pattern))
        return _ok_list([os.path.basename(item) for item in items])

    return None


def ok_file(path: str) -> CommandResult:
    path = normalize_path_value(path)
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


def ok_folder(path: str) -> CommandResult:
    path = normalize_path_value(path)
    return _ok_outputs({"output": path, "path": path, "exists": _bool_text(os.path.isdir(path))})


def _ok(text: str) -> CommandResult:
    text = str(text)
    return _ok_outputs({"output": text, "length": str(len(text)), "empty": _bool_text(not bool(text))})


def _ok_bool(value: bool) -> CommandResult:
    return _ok_outputs({"output": _bool_text(value), "not": _bool_text(not value)})


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


def _value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(_value_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _string_values(values: dict[str, Any]) -> dict[str, str]:
    return {str(k): _value_to_text(v) for k, v in dict(values or {}).items()}


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
