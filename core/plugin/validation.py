"""Plugin manifest and lifecycle validation extracted from plugin_manager.py."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from core.plugin.constants import (
    HIGH_RISK_PERMISSIONS,
    OFFICIAL_PLUGIN_PACKAGE_SHA256,
    PERMISSIONS_KNOWN,
    PLUGIN_PACKAGE_EXTENSION,
)
from core.plugin.models import PluginManifest
from core.plugin.paths import safe_relative_plugin_path as _safe_relative_plugin_path
from runtime_paths import app_root

logger = logging.getLogger(__name__)


def validate_manifest(m: PluginManifest) -> str:
    if not m.id:
        return "缺少 plugin.id"
    if not m.name:
        return "缺少 plugin.name"
    if not m.version:
        return "缺少 plugin.version"
    if not m.entry:
        return "缺少 plugin.entry"
    if _safe_relative_plugin_path(m.entry) is None:
        return f"plugin.entry 包含不安全路径: {m.entry}"
    if m.icon and _safe_relative_plugin_path(m.icon) is None:
        return f"plugin.icon 包含不安全路径: {m.icon}"
    if not m.id.isidentifier() and not all(c.isalnum() or c in "-_" for c in m.id):
        return f"plugin.id 包含非法字符: {m.id}"
    for perm in m.permissions:
        if perm not in PERMISSIONS_KNOWN:
            return f"未知权限: {perm}"
    for cmd in m.commands:
        cid = cmd.get("id", "")
        if "." not in cid:
            return f"命令 ID 必须包含点号: {cid}"
    return ""


def has_high_risk_permissions(permissions: list[str]) -> bool:
    return any(p in HIGH_RISK_PERMISSIONS for p in permissions)


def _is_builtin_plugin_package(package_path: str, plugin_id: str) -> bool:
    try:
        package = Path(package_path).resolve(strict=False)
        plugins_dir = Path(app_root()) / ".plugins"
        expected = plugins_dir / f"{plugin_id}{PLUGIN_PACKAGE_EXTENSION}"
        if package != expected.resolve(strict=False):
            return False
        expected_hash = OFFICIAL_PLUGIN_PACKAGE_SHA256.get(plugin_id)
        if not expected_hash or not package.is_file():
            return False
        digest = hashlib.sha256()
        with package.open("rb") as package_file:
            for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_hash
    except Exception:
        logger.debug("判断官方插件包来源失败: %s", package_path, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# ── PluginManager ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
