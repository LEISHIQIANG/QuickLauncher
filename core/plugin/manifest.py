"""Plugin manifest parsing and validation without runtime side effects."""

from __future__ import annotations

import json
from pathlib import Path

from core.path_security import UnsafePathError, resolve_under

from .constants import PERMISSIONS_KNOWN
from .models import PluginInfo, PluginManifest
from .paths import safe_relative_plugin_path


def validate_manifest(manifest: PluginManifest) -> str:
    if not manifest.id:
        return "缺少 plugin.id"
    if not manifest.name:
        return "缺少 plugin.name"
    if not manifest.version:
        return "缺少 plugin.version"
    if not manifest.entry:
        return "缺少 plugin.entry"
    if safe_relative_plugin_path(manifest.entry) is None:
        return f"plugin.entry 包含不安全路径: {manifest.entry}"
    if manifest.icon and safe_relative_plugin_path(manifest.icon) is None:
        return f"plugin.icon 包含不安全路径: {manifest.icon}"
    if not manifest.id.isidentifier() and not all(char.isalnum() or char in "-_" for char in manifest.id):
        return f"plugin.id 包含非法字符: {manifest.id}"
    for permission in manifest.permissions:
        if permission not in PERMISSIONS_KNOWN:
            return f"未知权限: {permission}"
    for command in manifest.commands:
        command_id = command.get("id", "")
        if "." not in command_id:
            return f"命令 ID 必须包含点号: {command_id}"
    return ""


class PluginManifestParser:
    def parse(self, directory: str | Path, manifest_path: str | Path) -> PluginInfo:
        directory_path = Path(directory).resolve(strict=False)
        path = Path(manifest_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("plugin manifest root must be an object")
            manifest = PluginManifest.from_dict(raw)
            if manifest.id and directory_path.name != manifest.id:
                return PluginInfo(
                    manifest=manifest,
                    directory=str(directory_path),
                    status="error",
                    error=f"plugin.id must match directory name: {manifest.id} != {directory_path.name}",
                )
            error = validate_manifest(manifest)
            if error:
                return PluginInfo(manifest=manifest, directory=str(directory_path), status="error", error=error)
            safe_entry = safe_relative_plugin_path(manifest.entry)
            if safe_entry is None:
                return PluginInfo(
                    manifest=manifest,
                    directory=str(directory_path),
                    status="error",
                    error=f"plugin.entry 包含不安全路径: {manifest.entry}",
                )
            try:
                entry_path = resolve_under(directory_path, directory_path / safe_entry)
            except UnsafePathError:
                return PluginInfo(
                    manifest=manifest,
                    directory=str(directory_path),
                    status="error",
                    error=f"plugin.entry 包含不安全路径: {manifest.entry}",
                )
            if not entry_path.is_file():
                return PluginInfo(
                    manifest=manifest,
                    directory=str(directory_path),
                    status="error",
                    error=f"插件入口文件不存在: {entry_path}",
                )
            return PluginInfo(manifest=manifest, directory=str(directory_path), status="loaded")
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            return PluginInfo(
                manifest=PluginManifest(id="?", name="?", version="0"),
                directory=str(directory_path),
                status="error",
                error=str(exc),
            )
