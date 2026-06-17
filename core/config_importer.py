import copy
import json
import logging
import os
import uuid
import zipfile
from datetime import datetime

from .config_validation import sanitize_settings_dict
from .data_manager import DataManager
from .data_models import Folder, ShortcutItem, ShortcutType
from .icon_extractor import IconExtractor, get_icon_dir
from .import_security import (
    MAX_CONFIG_BYTES,
    MAX_ICON_BYTES,
    UnsafeZipError,
    build_safe_zip_index,
    has_zip_entry,
    is_allowed_icon_path,
    new_import_report,
    read_zip_bytes,
    read_zip_text,
    set_imported_items,
    skip_file,
)

logger = logging.getLogger(__name__)


class ConfigImporter:
    """配置导入导出管理器"""

    @staticmethod
    def export_config(data_manager: DataManager, file_path: str) -> bool:
        """
        导出完整配置到文件（包含所有数据和配置文件）

        Args:
            data_manager: 数据管理器
            file_path: 目标文件路径

        Returns:
            bool: 是否成功
        """
        try:
            if not data_manager or not data_manager.data:
                logger.warning("数据管理器或数据为空，无法导出")
                return False

            success = data_manager.backup_full_config(file_path)
            if success:
                logger.info("完整配置导出完成")
            return success
        except Exception as e:
            logger.exception("导出配置失败: %s", e)
            return False

    @staticmethod
    def export_config_legacy(data_manager: DataManager, file_path: str) -> bool:
        """
        导出配置（快捷键、URL、命令）到文件 - 旧版本兼容

        Args:
            data_manager: 数据管理器
            file_path: 目标文件路径

        Returns:
            bool: 是否成功
        """
        try:
            if not data_manager or not data_manager.data or not data_manager.data.folders:
                logger.warning("数据管理器或数据为空，无法导出")
                return False

            items_to_export = []
            icon_files_to_include = []  # (src_path, arcname)
            icon_blobs_to_include = []  # (arcname, bytes)

            def _qimage_to_bytes(image, fmt: str) -> bytes | None:
                try:
                    from qt_compat import QBuffer, QByteArray, QIODevice

                    data = QByteArray()
                    buf = QBuffer(data)
                    if hasattr(QIODevice, "OpenModeFlag"):
                        mode = QIODevice.OpenModeFlag.WriteOnly
                    else:
                        mode = QIODevice.WriteOnly  # type: ignore[unused-ignore, attr-defined]
                    buf.open(mode)
                    ok = image.save(buf, fmt)
                    buf.close()
                    if not ok:
                        return None
                    return bytes(data)
                except Exception:
                    return None

            def _extract_icon_blob(icon_path: str) -> bytes | None:
                try:
                    image = IconExtractor.from_file(icon_path, size=256, return_image=True)
                    if not image or image.isNull():
                        return None
                    blob = _qimage_to_bytes(image, "ICO")
                    if blob:
                        return blob
                    return _qimage_to_bytes(image, "PNG")
                except Exception:
                    return None

            logger.info("开始遍历数据，文件夹数量: %s", len(data_manager.data.folders))

            # 遍历所有文件夹
            for folder in data_manager.data.folders:
                if not folder or not folder.items:
                    continue

                for item in folder.items:
                    # 只导出指定类型
                    if item.type in (ShortcutType.HOTKEY, ShortcutType.URL, ShortcutType.COMMAND):
                        item_dict = item.to_dict()

                        # 处理图标
                        icon_path = item.icon_path
                        if icon_path:
                            is_resource_icon = False
                            if "," in icon_path:
                                parts = icon_path.split(",")
                                if len(parts) >= 2 and parts[-1].strip().lstrip("-").isdigit():
                                    is_resource_icon = True

                            ext = os.path.splitext(icon_path)[1].lower()
                            should_extract = is_resource_icon or ext in (".exe", ".dll")

                            if should_extract:
                                blob = _extract_icon_blob(icon_path)
                                if blob:
                                    new_icon_name = (
                                        f"{item.id}.ico" if blob[:4] == b"\x00\x00\x01\x00" else f"{item.id}.png"
                                    )
                                    arcname = f"icons/{new_icon_name}"
                                    item_dict["icon_path"] = arcname
                                    icon_blobs_to_include.append((arcname, blob))
                                else:
                                    item_dict["icon_path"] = ""
                            else:
                                if os.path.exists(icon_path):
                                    if not ext:
                                        ext = ".png"
                                    new_icon_name = f"{item.id}{ext}"
                                    arcname = f"icons/{new_icon_name}"
                                    item_dict["icon_path"] = arcname
                                    icon_files_to_include.append((icon_path, arcname))
                                else:
                                    item_dict["icon_path"] = ""
                        else:
                            item_dict["icon_path"] = ""

                        items_to_export.append(item_dict)

            if not items_to_export:
                logger.info("没有符合导出条件的项目")
                return False

            logger.info(
                "找到 %s 个项目需要导出，包含 %s 个图标",
                len(items_to_export),
                len(icon_files_to_include) + len(icon_blobs_to_include),
            )

            # 创建压缩包
            with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 写入 items.json
                zf.writestr("items.json", json.dumps(items_to_export, indent=2, ensure_ascii=False))

                # 写入 settings.json (新增)
                try:
                    settings_dict = data_manager.data.settings.to_dict()
                    zf.writestr("settings.json", json.dumps(settings_dict, indent=2, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"导出设置失败: {e}")

                # 写入图标文件
                for orig_path, arcname in icon_files_to_include:
                    try:
                        zf.write(orig_path, arcname)
                    except Exception as e:
                        msg = f"无法添加图标到导出包: {orig_path}, {e}"
                        logger.warning(msg)

                for arcname, blob in icon_blobs_to_include:
                    try:
                        zf.writestr(arcname, blob)
                    except Exception as e:
                        msg = f"无法写入图标到导出包: {arcname}, {e}"
                        logger.warning(msg)

            logger.info("导出完成")
            return True
        except Exception as e:
            logger.exception("导出配置失败: %s", e)
            return False

    @staticmethod
    def import_config(
        data_manager: DataManager,
        file_path: str,
        target_folder_id: str | None = None,
        *,
        dry_run: bool = False,
    ) -> int:
        """
        从文件导入配置（支持完整备份和旧版格式）

        Args:
            data_manager: 数据管理器
            file_path: 源文件路径
            target_folder_id: 目标文件夹ID，仅用于旧版格式

        Returns:
            int: 导入的项目数量
        """
        try:
            if not zipfile.is_zipfile(file_path):
                logger.error("无效的ZIP文件: %s", file_path)
                return -1

            report = (
                data_manager._reset_import_report()
                if hasattr(data_manager, "_reset_import_report")
                else new_import_report()
            )
            with zipfile.ZipFile(file_path, "r") as zf:
                safe_index = build_safe_zip_index(zf, report)
                names = set(safe_index.keys())
                # 检查是否为完整备份
                report["dry_run"] = bool(dry_run)
                if "data.json" in names:
                    if dry_run:
                        return ConfigImporter._preview_full_backup(data_manager, zf, safe_index, report)
                    return ConfigImporter._import_full_backup(data_manager, file_path)
                elif "items.json" in names:
                    if dry_run:
                        return ConfigImporter._preview_legacy(data_manager, zf, safe_index, report)
                    return ConfigImporter._import_legacy(data_manager, zf, target_folder_id, safe_index, report)
                else:
                    logger.error("文件格式错误: 缺少必要文件")
                    return -1

        except Exception as e:
            logger.exception("导入配置失败: %s", e)
            return -1

    @staticmethod
    def _import_full_backup(data_manager: DataManager, file_path: str) -> int:
        """导入完整备份"""
        try:
            if not data_manager.restore_full_config(file_path):
                return -1
            total_items = sum(len(f.items) for f in data_manager.data.folders)
            logger.info("完整备份恢复完成，共 %s 项", total_items)
            return total_items

        except Exception as e:
            logger.exception("导入完整备份失败: %s", e)
            return -1

    @staticmethod
    def _preview_full_backup(
        data_manager: DataManager,
        zf: zipfile.ZipFile,
        safe_index: dict,
        report: dict,
    ) -> int:
        try:
            data_json = read_zip_text(
                zf,
                safe_index,
                "data.json",
                max_bytes=MAX_CONFIG_BYTES,
                report=report,
                required=True,
            )
            if data_json is None:
                return -1
            data = json.loads(data_json)
            folders = data.get("folders", []) if isinstance(data, dict) else []
            count = 0
            if isinstance(folders, list):
                for folder in folders:
                    items = folder.get("items", []) if isinstance(folder, dict) else []
                    if isinstance(items, list):
                        count += len([item for item in items if isinstance(item, dict)])
            report["mode"] = "full_backup"
            set_imported_items(report, count)
            return count
        except (UnsafeZipError, ValueError, json.JSONDecodeError) as e:
            logger.warning("full backup preview rejected unsafe package: %s", e)
            return -1
        except Exception as e:
            logger.exception("full backup preview failed: %s", e)
            return -1

    @staticmethod
    def _preview_legacy(
        data_manager: DataManager,
        zf: zipfile.ZipFile,
        safe_index: dict,
        report: dict,
    ) -> int:
        try:
            items_text = read_zip_text(
                zf,
                safe_index,
                "items.json",
                max_bytes=MAX_CONFIG_BYTES,
                report=report,
                required=True,
            )
            if items_text is None:
                return -1
            items_data = json.loads(items_text)
            if not isinstance(items_data, list):
                return -1
            count = 0
            for raw_item in items_data[:2048]:
                if not isinstance(raw_item, dict):
                    continue
                count += 1
                zip_icon_path = str(raw_item.get("icon_path") or "")
                if (
                    zip_icon_path
                    and has_zip_entry(safe_index, zip_icon_path)
                    and not is_allowed_icon_path(zip_icon_path)
                ):
                    skip_file(report, zip_icon_path, "unsupported icon extension")
            if has_zip_entry(safe_index, "settings.json"):
                settings_text = read_zip_text(
                    zf,
                    safe_index,
                    "settings.json",
                    max_bytes=MAX_CONFIG_BYTES,
                    report=report,
                )
                if settings_text:
                    sanitize_settings_dict(json.loads(settings_text), report)
            report["mode"] = "legacy"
            set_imported_items(report, count)
            return count
        except (UnsafeZipError, ValueError, json.JSONDecodeError) as e:
            logger.warning("legacy config preview rejected unsafe package: %s", e)
            return -1
        except Exception as e:
            logger.exception("legacy config preview failed: %s", e)
            return -1

    @staticmethod
    def _import_legacy_safe(
        data_manager: DataManager,
        zf: zipfile.ZipFile,
        target_folder_id: str | None,
        safe_index: dict | None = None,
        report: dict | None = None,
    ) -> int:
        old_data = None
        old_saved = None
        old_config_status = None
        written_icon_paths: list[str] = []
        try:
            if safe_index is None:
                report = report or new_import_report()
                safe_index = build_safe_zip_index(zf, report)
            if not has_zip_entry(safe_index, "items.json"):
                logger.error("legacy import missing items.json")
                return -1

            items_text = read_zip_text(
                zf,
                safe_index,
                "items.json",
                max_bytes=MAX_CONFIG_BYTES,
                report=report,
                required=True,
            )
            if items_text is None:
                return -1
            items_data = json.loads(items_text)
            if not isinstance(items_data, list):
                logger.error("legacy import items.json is not a list")
                return -1

            old_data = copy.deepcopy(data_manager.data)
            old_saved = copy.deepcopy(getattr(data_manager, "_last_saved_data_dict", None))
            old_config_status = dict(getattr(data_manager, "_config_status", {}) or {})

            target_folder = data_manager.data.get_folder_by_id(target_folder_id) if target_folder_id else None
            if not target_folder:
                folder_name = f"导入的项目 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                target_folder = Folder(name=folder_name, is_system=False, is_dock=False)
                data_manager.data.folders.append(target_folder)

            imported_count = 0
            local_icon_dir = get_icon_dir()
            os.makedirs(local_icon_dir, exist_ok=True)

            with data_manager.batch_update(immediate=True):
                for raw_item in items_data[:2048]:
                    if not isinstance(raw_item, dict):
                        continue
                    item_dict = dict(raw_item)
                    item_dict["id"] = str(uuid.uuid4())
                    zip_icon_path = str(item_dict.get("icon_path") or "")
                    if zip_icon_path and has_zip_entry(safe_index, zip_icon_path):
                        ext = os.path.splitext(zip_icon_path)[1].lower()
                        if not is_allowed_icon_path(zip_icon_path):
                            skip_file(report, zip_icon_path, "unsupported icon extension")
                            item_dict["icon_path"] = ""
                        else:
                            icon_content = read_zip_bytes(
                                zf,
                                safe_index,
                                zip_icon_path,
                                max_bytes=MAX_ICON_BYTES,
                                report=report,
                            )
                            if icon_content:
                                new_icon_name = f"{item_dict['id']}{ext or '.png'}"
                                local_icon_path = os.path.join(local_icon_dir, new_icon_name)
                                with open(local_icon_path, "wb") as target:
                                    target.write(icon_content)
                                written_icon_paths.append(local_icon_path)
                                item_dict["icon_path"] = local_icon_path
                            else:
                                item_dict["icon_path"] = ""
                    else:
                        item_dict["icon_path"] = ""

                    item = ShortcutItem.from_dict(item_dict)
                    target_folder.items.append(item)
                    imported_count += 1

                if has_zip_entry(safe_index, "settings.json"):
                    settings_text = read_zip_text(
                        zf,
                        safe_index,
                        "settings.json",
                        max_bytes=MAX_CONFIG_BYTES,
                        report=report,
                    )
                    if settings_text:
                        settings_data = json.loads(settings_text)
                        for key, value in sanitize_settings_dict(settings_data, report).items():
                            if hasattr(data_manager.data.settings, key):
                                setattr(data_manager.data.settings, key, value)

                if imported_count > 0:
                    repair = getattr(data_manager, "_apply_config_repairs_to_current", None)
                    if callable(repair):
                        repair()
                    data_manager.save()

            set_imported_items(report, imported_count)
            logger.info("legacy config import completed: imported=%s", imported_count)
            return imported_count
        except (UnsafeZipError, ValueError, json.JSONDecodeError) as e:
            ConfigImporter._rollback_legacy_import(
                data_manager, old_data, old_saved, old_config_status, written_icon_paths
            )
            logger.warning("legacy config import rejected unsafe package: %s", e)
            return -1
        except Exception as e:
            ConfigImporter._rollback_legacy_import(
                data_manager, old_data, old_saved, old_config_status, written_icon_paths
            )
            logger.exception("legacy config import failed: %s", e)
            return -1

    @staticmethod
    def _rollback_legacy_import(
        data_manager, old_data, old_saved, old_config_status, written_icon_paths: list[str]
    ) -> None:
        try:
            if old_data is not None:
                data_manager.data = old_data
            if old_saved is not None:
                data_manager._last_saved_data_dict = old_saved
            if old_config_status is not None:
                data_manager._config_status = old_config_status
        except Exception as rollback_error:
            logger.debug("legacy import memory rollback failed: %s", rollback_error)
        for path in written_icon_paths:
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except Exception as cleanup_error:
                logger.debug("legacy import icon rollback failed %s: %s", path, cleanup_error)

    @staticmethod
    def _import_legacy(
        data_manager: DataManager,
        zf: zipfile.ZipFile,
        target_folder_id: str | None,
        safe_index: dict | None = None,
        report: dict | None = None,
    ) -> int:
        """导入旧版格式（仅快捷键、URL、命令）"""
        return ConfigImporter._import_legacy_safe(data_manager, zf, target_folder_id, safe_index, report)
