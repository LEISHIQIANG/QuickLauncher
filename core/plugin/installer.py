"""Install .qlzip plugin archives into the runtime plugins directory."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

from core.path_security import UnsafePathError, resolve_under, safe_rmtree_child
from core.plugin.constants import (
    PLUGIN_PACKAGE_MAX_FILES,
    PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES,
)
from core.plugin.paths import safe_relative_plugin_path

logger = logging.getLogger(__name__)


def install_zip_archive(
    zip_path: str,
    plugins_dir: str | os.PathLike[str],
    *,
    manifest_from_dict: Callable[[dict], object],
    validate_manifest: Callable[[object], str],
    on_overwrite: Callable[[str], bool] | None = None,
) -> str | None:
    plugins_root = Path(plugins_dir).resolve(strict=False)
    staging_base = resolve_under(plugins_root, plugins_root / ".staging")
    staging_base.mkdir(parents=True, exist_ok=True)

    staging_dir = resolve_under(staging_base, staging_base / f"install-{uuid.uuid4().hex[:12]}")
    backup_dir: Path | None = None
    plugin_id: str | None = None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            has_root = "plugin.json" in names
            sub_manifest: str | None = None
            archive_root: str | None = None
            for name in names:
                if name.endswith("/plugin.json") and len(name.split("/")) == 2:
                    sub_manifest = name
                    archive_root = name.split("/", 1)[0]
                    break
            if not has_root and not sub_manifest:
                raise ValueError(
                    "Could not find a valid plugin.json in the plugin archive.\n"
                    "Please make sure the archive contains plugin.json."
                )

            _validate_archive_limits(zf)

            try:
                manifest_bytes = zf.read("plugin.json") if has_root else zf.read(sub_manifest)  # type: ignore[arg-type]
                manifest_data = json.loads(manifest_bytes.decode("utf-8"))
                plugin_id = manifest_data.get("id")
                plugin_name = str(manifest_data.get("name") or plugin_id)
            except Exception as exc:
                raise ValueError(f"解析 plugin.json 失败:\n{exc}") from exc

            if not plugin_id or not re.match(r"^[a-z0-9_-]+$", str(plugin_id)):
                raise ValueError("插件ID无效或格式不正确！")

            manifest = manifest_from_dict(manifest_data)
            manifest_error = validate_manifest(manifest)
            if manifest_error:
                raise ValueError(manifest_error)

            target_dir = resolve_under(plugins_root, plugins_root / plugin_id)
            if target_dir.exists():
                if target_dir.is_symlink():
                    raise ValueError(f"插件目标目录不安全: {target_dir}")
                if on_overwrite is None:
                    raise ValueError(f'插件 "{plugin_name}" 已存在，且未提供覆盖确认回调')
                if not on_overwrite(plugin_name):
                    return None

            os.makedirs(staging_dir, exist_ok=True)
            _extract_archive(zf, staging_dir, has_root=has_root, archive_root=archive_root)

            if not (staging_dir / "plugin.json").is_file():
                raise ValueError("解压后的插件包缺少 plugin.json 文件")

            if target_dir.exists():
                backup_base = resolve_under(plugins_root, plugins_root / ".backup")
                backup_dir = resolve_under(backup_base, backup_base / plugin_id)
                if backup_dir.exists():
                    safe_rmtree_child(backup_base, backup_dir)
                backup_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(target_dir, backup_dir)

            if target_dir.exists():
                safe_rmtree_child(plugins_root, target_dir)
            shutil.move(str(staging_dir), str(target_dir))
            staging_dir = None  # type: ignore[assignment]

        if backup_dir and backup_dir.exists():
            safe_rmtree_child(backup_dir.parent, backup_dir)
            backup_dir = None

        return plugin_id

    except zipfile.BadZipFile as exc:
        raise exc
    except Exception:
        exc_info = sys.exc_info()
        if backup_dir and backup_dir.exists() and plugin_id:
            try:
                target_dir = resolve_under(plugins_root, plugins_root / plugin_id)
                if target_dir.exists():
                    safe_rmtree_child(plugins_root, target_dir)
                shutil.copytree(backup_dir, target_dir)
                safe_rmtree_child(backup_dir.parent, backup_dir)
            except Exception as rollback_err:
                logger.error("回滚插件安装失败: %s", rollback_err)
        raise exc_info[1].with_traceback(exc_info[2]) from exc_info[1]  # type: ignore[union-attr]
    finally:
        if staging_dir and staging_dir.exists():
            try:
                safe_rmtree_child(staging_base, staging_dir)
            except Exception:
                logger.debug("failed to remove plugin staging dir: %s", staging_dir, exc_info=True)
        if staging_base.exists():
            try:
                if not any(staging_base.iterdir()):
                    staging_base.rmdir()
            except OSError:
                logger.debug("删除插件暂存目录失败", exc_info=True)


def _validate_archive_limits(zf: zipfile.ZipFile) -> None:
    total_size = 0
    file_count = 0
    for member in zf.infolist():
        if member.is_dir():
            continue
        if member.flag_bits & 0x1:
            raise ValueError("plugin archive contains encrypted files, which are not supported")
        file_count += 1
        total_size += max(0, int(member.file_size))
        if total_size > PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES:
            raise ValueError(
                "plugin archive uncompressed size exceeds limit "
                f"({total_size / 1024 / 1024:.1f} MB > "
                f"{PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES / 1024 / 1024:.0f} MB)"
            )
    if file_count == 0:
        raise ValueError("压缩包为空，没有可安装的文件")
    if file_count > PLUGIN_PACKAGE_MAX_FILES:
        raise ValueError(f"插件文件过多 ({file_count} 个)，最大值限制为 {PLUGIN_PACKAGE_MAX_FILES} 个")
    if total_size > PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES:
        raise ValueError(
            f"插件总大小 ({total_size / 1024 / 1024:.1f} MB) 超过限制 "
            f"({PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES / 1024 / 1024:.0f} MB)"
        )


def _extract_archive(
    zf: zipfile.ZipFile,
    staging_dir: Path,
    *,
    has_root: bool,
    archive_root: str | None,
) -> None:
    seen_paths: set[str] = set()
    for member in zf.infolist():
        if member.is_dir():
            continue
        filename = member.filename
        if has_root:
            rel_path = filename
        else:
            normalized_member = safe_relative_plugin_path(filename)
            if normalized_member is None:
                raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}")
            if not archive_root or not normalized_member.startswith(f"{archive_root}/"):
                raise ValueError(f"plugin archive contains files outside its root folder: {filename}")
            rel_path = normalized_member.split("/", 1)[1]
        if not rel_path:
            continue
        safe_rel_path = safe_relative_plugin_path(rel_path)
        if safe_rel_path is None:
            raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}")
        lower_rel_path = safe_rel_path.lower()
        if lower_rel_path in seen_paths:
            raise ValueError(f"插件压缩包包含重复路径，安装已终止: {filename}")
        seen_paths.add(lower_rel_path)
        try:
            dst = resolve_under(staging_dir, staging_dir / safe_rel_path)
        except UnsafePathError:
            raise ValueError(f"检测到路径穿越攻击，安装已终止: {filename}") from None
        dst.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(dst, "wb") as fd:
            shutil.copyfileobj(src, fd)
