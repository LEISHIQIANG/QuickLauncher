import os
import json
import zipfile
import uuid
import shutil
import logging
from typing import List, Dict, Optional
from datetime import datetime

from .data_models import ShortcutItem, ShortcutType, Folder
from .data_manager import DataManager
from .icon_extractor import get_icon_dir, IconExtractor

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

            def _qimage_to_bytes(image, fmt: str) -> Optional[bytes]:
                try:
                    from qt_compat import QBuffer, QByteArray, QIODevice
                    data = QByteArray()
                    buf = QBuffer(data)
                    if hasattr(QIODevice, "OpenModeFlag"):
                        mode = QIODevice.OpenModeFlag.WriteOnly
                    else:
                        mode = QIODevice.WriteOnly
                    buf.open(mode)
                    ok = image.save(buf, fmt)
                    buf.close()
                    if not ok:
                        return None
                    return bytes(data)
                except Exception:
                    return None

            def _extract_icon_blob(icon_path: str) -> Optional[bytes]:
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
                                    new_icon_name = f"{item.id}.ico" if blob[:4] == b"\x00\x00\x01\x00" else f"{item.id}.png"
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
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 写入 items.json
                zf.writestr('items.json', json.dumps(items_to_export, indent=2, ensure_ascii=False))

                # 写入 settings.json (新增)
                try:
                    settings_dict = data_manager.data.settings.to_dict()
                    zf.writestr('settings.json', json.dumps(settings_dict, indent=2, ensure_ascii=False))
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
    def import_config(data_manager: DataManager, file_path: str, target_folder_id: Optional[str] = None) -> int:
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

            with zipfile.ZipFile(file_path, 'r') as zf:
                names = zf.namelist()
                # 检查是否为完整备份
                if 'data.json' in names:
                    return ConfigImporter._import_full_backup(data_manager, file_path)
                elif 'items.json' in names:
                    return ConfigImporter._import_legacy(data_manager, zf, target_folder_id)
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
    def _import_legacy(data_manager: DataManager, zf: zipfile.ZipFile, target_folder_id: Optional[str]) -> int:
        """导入旧版格式（仅快捷键、URL、命令）"""
        try:
                # 读取 items.json
                if 'items.json' not in zf.namelist():
                    logger.error("文件格式错误: 缺少 items.json")
                    return -1
                
                items_data = json.loads(zf.read('items.json').decode('utf-8'))
                if not isinstance(items_data, list):
                    logger.error("文件格式错误: items.json 不是列表")
                    return -1
                
                # 准备目标文件夹
                target_folder = None
                if target_folder_id:
                    target_folder = data_manager.data.get_folder_by_id(target_folder_id)
                
                if not target_folder:
                    # 创建新的导入文件夹
                    folder_name = f"导入的项目 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    target_folder = Folder(name=folder_name, is_system=False, is_dock=False)
                    data_manager.data.folders.append(target_folder)

                imported_count = 0
                local_icon_dir = get_icon_dir()
                if not os.path.exists(local_icon_dir):
                    os.makedirs(local_icon_dir)

                settings_imported = False
                with data_manager.batch_update(immediate=True):
                    for item_dict in items_data:
                        # 生成新 ID
                        item_dict["id"] = str(uuid.uuid4())

                        # 处理图标
                        zip_icon_path = item_dict.get("icon_path")
                        if zip_icon_path and zip_icon_path in zf.namelist():
                            # 解压图标
                            ext = os.path.splitext(zip_icon_path)[1].lower()

                            # 过滤掉可执行文件和动态库，这些不应该被当作图标文件
                            # 正常的图标文件应该是 .ico, .png, .jpg 等
                            invalid_exts = {".exe", ".dll", ".sys", ".com", ".bat", ".cmd", ".msi", ".scr"}
                            if ext in invalid_exts:
                                logger.warning(f"跳过无效图标文件: {zip_icon_path} (不支持的扩展名 {ext})")
                                item_dict["icon_path"] = ""
                            else:
                                try:
                                    # 先读取图标内容
                                    icon_content = zf.read(zip_icon_path)

                                    # 验证文件大小
                                    if len(icon_content) > 10 * 1024 * 1024:  # 10MB
                                        logger.warning(f"跳过过大的图标文件: {zip_icon_path} ({len(icon_content) / 1024 / 1024:.2f} MB)")
                                        item_dict["icon_path"] = ""
                                    else:
                                        # 计算内容哈希，用于去重
                                        import hashlib
                                        content_hash = hashlib.md5(icon_content[:65536]).hexdigest()  # 使用前 64KB 计算哈希

                                        # 检查是否有相同内容的图标已存在
                                        existing_icon_path = None
                                        for existing_file in os.listdir(local_icon_dir):
                                            existing_full_path = os.path.join(local_icon_dir, existing_file)
                                            if not os.path.isfile(existing_full_path):
                                                continue
                                            try:
                                                with open(existing_full_path, "rb") as ef:
                                                    existing_content = ef.read(65536)
                                                    existing_hash = hashlib.md5(existing_content).hexdigest()
                                                    if existing_hash == content_hash:
                                                        # 找到相同内容的图标，复用它
                                                        existing_icon_path = existing_full_path
                                                        break
                                            except Exception as e:
                                                logger.debug("读取现有图标失败: %s, %s", existing_full_path, e)

                                        if existing_icon_path:
                                            # 复用现有图标，不创建新文件
                                            item_dict["icon_path"] = existing_icon_path
                                            logger.debug(f"复用已存在的图标: {existing_icon_path}")
                                        else:
                                            # 创建新图标文件
                                            new_icon_name = f"{item_dict['id']}{ext}"
                                            local_icon_path = os.path.join(local_icon_dir, new_icon_name)
                                            with open(local_icon_path, "wb") as target:
                                                target.write(icon_content)
                                            item_dict["icon_path"] = local_icon_path

                                except Exception as e:
                                    logger.warning(f"解压图标失败: {zip_icon_path}, {e}")
                                    item_dict["icon_path"] = ""
                        else:
                             item_dict["icon_path"] = ""

                        # 创建对象并添加
                        item = ShortcutItem.from_dict(item_dict)
                        target_folder.items.append(item)
                        imported_count += 1

                    if imported_count > 0:
                        data_manager.save()

                    # 导入 settings.json (新增)
                    if 'settings.json' in zf.namelist():
                        try:
                            settings_data = json.loads(zf.read('settings.json').decode('utf-8'))
                            # 更新设置
                            data_manager.update_settings(**settings_data)
                            settings_imported = True
                            logger.info("设置已更新")
                        except Exception as e:
                            logger.exception("导入设置失败: %s", e)

                logger.info("导入完成，共导入 %s 项，设置更新: %s", imported_count, settings_imported)
                return imported_count

        except Exception as e:
            logger.exception("导入旧版配置失败: %s", e)
            return -1
