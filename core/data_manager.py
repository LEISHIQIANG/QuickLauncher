"""
数据管理器
"""

import os
import json
import shutil
import tempfile
import uuid
import zipfile
import threading
import logging
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional
from .data_models import AppData, AppSettings, Folder, ShortcutItem

logger = logging.getLogger(__name__)


class DataManager:
    """数据管理器 - 单例模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        import sys
        if getattr(sys, 'frozen', False):
            install_dir = Path(sys.executable).parent
        else:
            install_dir = Path(__file__).parent.parent

        self.install_dir = install_dir
        self.app_dir = install_dir / 'config'
        self.data_file = self.app_dir / 'data.json'
        self.icons_dir = install_dir / 'icons'
        self.auto_backup_dir = self.app_dir / 'auto_backups'
        self._max_auto_backups = 5

        # 执行配置迁移
        from .config_migrator import ConfigMigrator
        if ConfigMigrator.needs_migration():
            ConfigMigrator.migrate()

        # 保存节流控制
        self._save_timer = None
        self._save_pending = False
        self._save_lock = threading.Lock()
        self._save_delay = 0.5  # 500ms 内的连续保存会被合并
        self._batch_depth = 0
        self._batch_dirty = False
        self._batch_force_immediate = False
        self._runtime_revision = 0
        
        self._ensure_dirs()
        self.data = self._load()

    def get_runtime_revision(self) -> int:
        """杩斿洖鍐呭瓨鏁版嵁鐨勮繍琛屾椂淇鍙枫€?"""
        return int(self._runtime_revision)
    
    def _ensure_dirs(self):
        """确保目录存在"""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.icons_dir.mkdir(parents=True, exist_ok=True)
    
    def _load(self) -> AppData:
        """加载数据"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return AppData.from_dict(json.load(f))
            except Exception as e:
                logger.warning("加载数据失败: %s", e)
        return AppData()
    
    def save(self, immediate: bool = False):
        """保存数据（带节流）
        
        Args:
            immediate: 是否立即保存，忽略节流
        """
        self._runtime_revision += 1
        with self._save_lock:
            if self._batch_depth > 0:
                self._save_pending = True
                self._batch_dirty = True
                if immediate:
                    self._batch_force_immediate = True
                return

        if immediate:
            self._do_save()
            return
            
        with self._save_lock:
            self._save_pending = True
            if self._save_timer is None:
                self._save_timer = threading.Timer(self._save_delay, self._delayed_save)
                self._save_timer.daemon = True
                self._save_timer.start()
    
    def _delayed_save(self):
        """延迟保存执行"""
        with self._save_lock:
            self._save_timer = None
            if self._save_pending:
                self._save_pending = False
                self._do_save()

    @contextmanager
    def batch_update(self, immediate: bool = False):
        """在一个批次中合并多次数据修改，避免重复落盘。"""
        with self._save_lock:
            self._batch_depth += 1
            if immediate:
                self._batch_force_immediate = True

        try:
            yield self
        finally:
            should_flush = False
            flush_immediately = False
            with self._save_lock:
                if self._batch_depth > 0:
                    self._batch_depth -= 1

                if self._batch_depth == 0:
                    if self._save_pending or self._batch_dirty:
                        should_flush = True
                        flush_immediately = self._batch_force_immediate
                        if self._save_timer is not None:
                            self._save_timer.cancel()
                            self._save_timer = None
                        self._save_pending = False

                    self._batch_dirty = False
                    self._batch_force_immediate = False

            if should_flush:
                if flush_immediately:
                    self._do_save()
                else:
                    self.save()
    
    def _do_save(self):
        """Save data to disk atomically."""
        temp_file = self.data_file.with_name(f"{self.data_file.stem}.{uuid.uuid4().hex}.tmp")
        try:
            payload = self._serialize_data()
            self._create_auto_backup()

            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(payload)

            self._replace_data_file(temp_file)

        except Exception as e:
            logger.error("save data failed: %s", e)
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as cleanup_error:
                    logger.debug("cleanup temp file failed: %s", cleanup_error)

    def _serialize_data(self) -> str:
        """Serialize data and validate the JSON before writing it to disk."""
        payload = json.dumps(self.data.to_dict(), ensure_ascii=False, separators=(',', ':'))
        json.loads(payload)
        return payload

    def _replace_data_file(self, temp_file: Path):
        """Replace data.json, falling back when Windows denies atomic rename."""
        try:
            os.replace(temp_file, self.data_file)
            return
        except OSError as replace_error:
            logger.debug("atomic data replace failed, using guarded copy fallback: %s", replace_error)

        fallback_backup = self.data_file.with_suffix(".write_backup")
        had_original = self.data_file.exists()
        try:
            if had_original:
                shutil.copy2(self.data_file, fallback_backup)
            shutil.copyfile(temp_file, self.data_file)
            try:
                os.remove(temp_file)
            except Exception as cleanup_error:
                logger.debug("cleanup temp file after fallback copy failed: %s", cleanup_error)
        except Exception:
            if had_original and fallback_backup.exists():
                try:
                    shutil.copyfile(fallback_backup, self.data_file)
                except Exception as restore_error:
                    logger.error("restore data file after fallback failure failed: %s", restore_error)
            raise
        finally:
            if fallback_backup.exists():
                try:
                    fallback_backup.unlink()
                except Exception as cleanup_error:
                    logger.debug("cleanup data write backup failed: %s", cleanup_error)

    def _create_auto_backup(self):
        """Create a timestamped backup of the current data file before replacing it."""
        if not self.data_file.exists():
            return

        try:
            self.auto_backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_path = self.auto_backup_dir / f"data_{timestamp}.json"
            shutil.copy2(self.data_file, backup_path)
            self._prune_auto_backups()
        except Exception as e:
            logger.debug("auto backup failed: %s", e)

    def _prune_auto_backups(self):
        """Keep only the newest configured automatic backups."""
        if not self.auto_backup_dir.exists():
            return

        try:
            backups = sorted(
                self.auto_backup_dir.glob("data_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old_backup in backups[self._max_auto_backups:]:
                try:
                    old_backup.unlink()
                except Exception as e:
                    logger.debug("delete old auto backup failed %s: %s", old_backup, e)
        except Exception as e:
            logger.debug("prune auto backups failed: %s", e)

    def flush_pending_save(self):
        """强制执行待保存的操作（用于在 reload 前确保数据已保存）"""
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
            if self._save_pending:
                self._save_pending = False
                self._do_save()
    
    def reload(self):
        """重新加载数据"""
        # 先刷新待保存的数据，避免丢失
        self.flush_pending_save()
        self.data = self._load()
        self._runtime_revision += 1
    
    def add_folder(self, name: str) -> Folder:
        """添加文件夹"""
        max_order = max((f.order for f in self.data.folders), default=0)
        folder = Folder(name=name, order=max_order + 1)
        self.data.folders.append(folder)
        self.save()
        return folder
    
    def rename_folder(self, folder_id: str, new_name: str) -> bool:
        """重命名文件夹"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder:
            folder.name = new_name
            self.save()
            return True
        return False
    
    def delete_folder(self, folder_id: str) -> bool:
        """删除文件夹"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder and not folder.is_system:
            self.data.folders.remove(folder)
            self.save()
            return True
        return False
    
    def reorder_folders(self, folder_ids: List[str]):
        """重排序文件夹"""
        order_map = {fid: i for i, fid in enumerate(folder_ids)}
        for folder in self.data.folders:
            if folder.id in order_map:
                folder.order = order_map[folder.id]
        self.data.folders.sort(key=lambda f: f.order)
        self.save()
    
    def add_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """添加快捷方式"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder:
            max_order = max((s.order for s in folder.items), default=-1)
            shortcut.order = max_order + 1
            folder.items.append(shortcut)
            self.save(immediate=True)  # 立即保存，避免数据丢失
            return True
        return False
        
    def add_shortcuts(self, folder_id: str, shortcuts: List[ShortcutItem]) -> int:
        """批量添加快捷方式"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder and shortcuts:
            max_order = max((s.order for s in folder.items), default=-1)
            count = 0
            for shortcut in shortcuts:
                shortcut.order = max_order + 1 + count
                folder.items.append(shortcut)
                count += 1
            self.save(immediate=True)  # 批量操作后只进行一次保存
            return count
        return 0
        
    def move_shortcut_to_folder(self, shortcut_id: str, target_folder_id: str) -> bool:
        """移动快捷方式到指定文件夹"""
        source_folder = None
        target_shortcut = None
        
        # 查找快捷方式所在的源文件夹
        for folder in self.data.folders:
            for item in folder.items:
                if item.id == shortcut_id:
                    source_folder = folder
                    target_shortcut = item
                    break
            if source_folder:
                break
        
        if not source_folder or not target_shortcut:
            return False
            
        target_folder = self.data.get_folder_by_id(target_folder_id)
        if not target_folder:
            return False
            
        # 如果目标文件夹和源文件夹相同，无需移动
        if source_folder.id == target_folder.id:
            return False
            
        # 从源文件夹移除
        source_folder.items.remove(target_shortcut)
        
        # 添加到目标文件夹末尾
        max_order = max((s.order for s in target_folder.items), default=-1)
        target_shortcut.order = max_order + 1
        target_folder.items.append(target_shortcut)
        
        self.save(immediate=True)  # 立即保存
        return True
    
    def update_shortcut(self, folder_id: str, shortcut: ShortcutItem) -> bool:
        """更新快捷方式"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder:
            for i, item in enumerate(folder.items):
                if item.id == shortcut.id:
                    folder.items[i] = shortcut
                    self.save(immediate=True)  # 立即保存
                    return True
        return False
    
    def delete_shortcut(self, folder_id: str, shortcut_id: str) -> bool:
        """删除快捷方式"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder:
            for i, item in enumerate(folder.items):
                if item.id == shortcut_id:
                    folder.items.pop(i)
                    self.save(immediate=True)  # 立即保存
                    return True
        return False
    
    def reorder_shortcuts(self, folder_id: str, shortcut_ids: List[str]):
        """重排序快捷方式"""
        folder = self.data.get_folder_by_id(folder_id)
        if folder:
            order_map = {sid: i for i, sid in enumerate(shortcut_ids)}
            for item in folder.items:
                if item.id in order_map:
                    item.order = order_map[item.id]
            folder.items.sort(key=lambda x: x.order)
            self.save()
    
    def update_settings(self, **kwargs):
        """更新设置"""
        changed = False
        for key, value in kwargs.items():
            if hasattr(self.data.settings, key):
                current_value = getattr(self.data.settings, key)

                if current_value is value:
                    # 调用方可能直接原地修改了 list/dict 等可变对象，
                    # 这时仍需落盘，否则配置改动不会持久化。
                    if isinstance(value, (list, dict, set)):
                        changed = True
                    continue

                if current_value == value:
                    continue

                setattr(self.data.settings, key, value)
                changed = True

        if changed:
            self.save()
    
    def get_settings(self) -> AppSettings:
        """获取设置"""
        return self.data.settings
    
    def clean_icon_cache(self, dry_run: bool = False) -> dict:
        """清理图标缓存
        
        清理规则：
        1. 删除可执行文件/动态库（.exe, .dll 等）
        2. 删除过大的文件（>10MB）
        3. 删除不再被任何快捷方式引用的孤儿图标文件
        4. 删除重复的图标文件（基于内容哈希）
        
        Args:
            dry_run: 如果为 True，只统计不实际删除
            
        Returns:
            dict: 清理统计信息
        """
        import hashlib
        import logging
        logger = logging.getLogger(__name__)
        
        stats = {
            "exe_files_removed": 0,
            "exe_files_size_mb": 0,
            "large_files_removed": 0,
            "large_files_size_mb": 0,
            "orphan_files_removed": 0,
            "orphan_files_size_mb": 0,
            "duplicate_files_removed": 0,
            "duplicate_files_size_mb": 0,
            "total_removed": 0,
            "total_size_freed_mb": 0,
            "dry_run": dry_run
        }
        
        if not self.icons_dir.exists():
            return stats
        
        # 收集所有正在使用的图标路径
        used_icons = set()
        for folder in self.data.folders:
            for item in folder.items:
                if item.icon_path:
                    # 标准化路径
                    used_icons.add(os.path.normcase(os.path.abspath(item.icon_path)))
        
        # 用于检测重复的哈希表
        seen_hashes = {}  # hash -> file_path
        
        # 无效扩展名
        invalid_exts = {".exe", ".dll", ".sys", ".com", ".bat", ".cmd", ".msi", ".scr"}
        max_size = 10 * 1024 * 1024  # 10MB
        
        for file_path in self.icons_dir.iterdir():
            if not file_path.is_file():
                continue
                
            file_path_str = str(file_path)
            file_path_normalized = os.path.normcase(os.path.abspath(file_path_str))
            ext = file_path.suffix.lower()
            
            try:
                file_size = file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
            except Exception:
                continue
            
            # 关键：检查文件是否正在被使用
            is_in_use = file_path_normalized in used_icons
            
            should_delete = False
            reason = ""
            
            # 规则1: 删除可执行文件（但保留正在使用的）
            if ext in invalid_exts:
                if not is_in_use:
                    should_delete = True
                    reason = "executable"
                    stats["exe_files_removed"] += 1
                    stats["exe_files_size_mb"] += file_size_mb
                # 如果是正在使用的 exe，跳过删除，但记录到 seen_hashes 以便后续去重
            
            # 规则2: 删除过大的文件（但保留正在使用的）
            elif file_size > max_size:
                if not is_in_use:
                    should_delete = True
                    reason = "too_large"
                    stats["large_files_removed"] += 1
                    stats["large_files_size_mb"] += file_size_mb
            
            # 规则3: 删除孤儿文件（不在使用列表中的）
            elif not is_in_use:
                should_delete = True
                reason = "orphan"
                stats["orphan_files_removed"] += 1
                stats["orphan_files_size_mb"] += file_size_mb
            
            # 规则4: 处理重复文件
            # 注意：只有不删除的文件才需要检查重复（正在使用的文件不会被删除，需要记录哈希）
            if not should_delete:
                try:
                    with open(file_path, "rb") as f:
                        # 只读取文件的前 64KB 用于快速哈希
                        content = f.read(65536)
                        file_hash = hashlib.md5(content).hexdigest()
                        
                    if file_hash in seen_hashes:
                        # 发现重复内容
                        # 如果当前文件正在使用，则不删除当前文件，而是标记之前的可以被删除（但已经处理过了，所以这里只跳过）
                        # 如果当前文件不在使用，可以安全删除
                        if not is_in_use:
                            should_delete = True
                            reason = "duplicate"
                            stats["duplicate_files_removed"] += 1
                            stats["duplicate_files_size_mb"] += file_size_mb
                        # 如果正在使用，更新 seen_hashes 指向正在使用的文件（优先保留使用中的）
                        else:
                            seen_hashes[file_hash] = file_path_str
                    else:
                        seen_hashes[file_hash] = file_path_str
                except Exception:
                    pass
            
            if should_delete:
                stats["total_removed"] += 1
                stats["total_size_freed_mb"] += file_size_mb
                
                if not dry_run:
                    try:
                        os.remove(file_path)
                        logger.info(f"已清理图标: {file_path.name} ({reason}, {file_size_mb:.2f} MB)")
                    except Exception as e:
                        logger.warning(f"无法删除文件 {file_path}: {e}")
                        # 回滚统计
                        stats["total_removed"] -= 1
                        stats["total_size_freed_mb"] -= file_size_mb
        
        # 四舍五入统计值
        for key in stats:
            if isinstance(stats[key], float):
                stats[key] = round(stats[key], 2)
        
        return stats
    
    def get_icon_cache_stats(self) -> dict:
        """获取图标缓存统计信息
        
        Returns:
            dict: 缓存统计信息
        """
        stats = {
            "total_files": 0,
            "total_size_mb": 0,
            "by_extension": {},
            "invalid_files": 0,
            "invalid_size_mb": 0
        }
        
        if not self.icons_dir.exists():
            return stats
        
        invalid_exts = {".exe", ".dll", ".sys", ".com", ".bat", ".cmd", ".msi", ".scr"}
        
        for file_path in self.icons_dir.iterdir():
            if not file_path.is_file():
                continue
                
            try:
                file_size = file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
            except Exception:
                continue
            
            ext = file_path.suffix.lower() or ".unknown"
            
            stats["total_files"] += 1
            stats["total_size_mb"] += file_size_mb
            
            if ext not in stats["by_extension"]:
                stats["by_extension"][ext] = {"count": 0, "size_mb": 0}
            stats["by_extension"][ext]["count"] += 1
            stats["by_extension"][ext]["size_mb"] += file_size_mb
            
            if ext in invalid_exts or file_size > 10 * 1024 * 1024:
                stats["invalid_files"] += 1
                stats["invalid_size_mb"] += file_size_mb
        
        # 四舍五入
        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        stats["invalid_size_mb"] = round(stats["invalid_size_mb"], 2)
        for ext_stats in stats["by_extension"].values():
            ext_stats["size_mb"] = round(ext_stats["size_mb"], 2)
        
        return stats
    
    def get_all_cache_paths(self) -> dict:
        """获取所有缓存路径和注册表键

        Returns:
            dict: 包含所有需要清理的路径和信息
        """
        import winreg

        cache_info = {
            "app_data_dir": str(self.app_dir),
            "icons_dir": str(self.icons_dir),
            "files": [],
            "directories": [],
            "registry_keys": []
        }

        # 应用数据文件
        if self.app_dir.exists():
            cache_info["directories"].append(str(self.app_dir))
            for item in self.app_dir.iterdir():
                cache_info["files"].append(str(item))

        # 图标缓存
        if self.icons_dir.exists():
            cache_info["directories"].append(str(self.icons_dir))

        # 开机自启注册表键
        registry_keys = [
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ]

        for key_path in registry_keys:
            try:
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                cache_info["registry_keys"].append(key_path)
            except WindowsError:
                pass

        return cache_info
    
    def factory_reset(self, callback=None) -> dict:
        """恢复出厂设置 - 清除所有缓存和配置
        
        Args:
            callback: 可选的进度回调函数 (message: str, progress: float)
            
        Returns:
            dict: 清理统计信息
        """
        import winreg
        import shutil
        import logging
        logger = logging.getLogger(__name__)
        
        stats = {
            "files_removed": 0,
            "dirs_removed": 0,
            "registry_keys_removed": 0,
            "errors": []
        }
        
        def report(msg, progress):
            if callback:
                try:
                    callback(msg, progress)
                except Exception:
                    pass
            logger.info(msg)
        
        # 1. 删除开机自启注册表项
        report("正在清理注册表...", 0.1)
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_ALL_ACCESS
            )
            try:
                winreg.DeleteValue(reg_key, "QuickLauncher")
                stats["registry_keys_removed"] += 1
            except WindowsError:
                pass
            winreg.CloseKey(reg_key)
        except Exception as e:
            stats["errors"].append(f"清理自启注册表失败: {e}")
        
        # 2. 删除图标缓存目录
        report("正在清理图标缓存...", 0.3)
        if self.icons_dir.exists():
            try:
                for item in self.icons_dir.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                            stats["files_removed"] += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            stats["dirs_removed"] += 1
                    except Exception as e:
                        stats["errors"].append(f"删除 {item} 失败: {e}")
            except Exception as e:
                stats["errors"].append(f"遍历图标目录失败: {e}")
        
        # 3. 删除应用数据目录下的所有文件
        report("正在清理应用数据...", 0.6)
        if self.app_dir.exists():
            try:
                for item in self.app_dir.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                            stats["files_removed"] += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            stats["dirs_removed"] += 1
                    except Exception as e:
                        stats["errors"].append(f"删除 {item} 失败: {e}")
            except Exception as e:
                stats["errors"].append(f"遍历应用目录失败: {e}")
        
        # 4. 重置内存中的数据
        report("正在重置配置...", 0.9)
        try:
            from .data_models import AppData
            self.data = AppData()
        except Exception as e:
            stats["errors"].append(f"重置数据失败: {e}")
        
    
    def backup_full_config(self, save_path: str) -> bool:
        """备份本机所有配置（包括图标、背景图、设置等）

        Args:
            save_path: 备份文件保存路径 (.zip)

        Returns:
            bool: 是否成功
        """
        try:
            # 确保当前数据已保存
            self.save(immediate=True)

            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. 准备数据字典
                data_dict = self.data.to_dict()

                # 2. 处理背景图片
                bg_path = getattr(self.data.settings, 'custom_bg_path', '')
                if bg_path and os.path.exists(bg_path):
                    ext = os.path.splitext(bg_path)[1]
                    arc_bg_name = f"background{ext}"
                    # 添加到 zip
                    zf.write(bg_path, arc_bg_name)
                    # 修改配置中的路径为相对路径
                    data_dict['settings']['custom_bg_path'] = arc_bg_name

                # 3. 写入 data.json
                zf.writestr('data.json', json.dumps(data_dict, ensure_ascii=False, indent=2))

                # 4. 备份图标文件夹
                if self.icons_dir.exists():
                    for file_path in self.icons_dir.iterdir():
                        if file_path.is_file():
                            zf.write(file_path, f"icons/{file_path.name}")


            return True
        except Exception as e:
            logger.error("backup_full_config failed: %s", e)
            return False

    def restore_full_config(self, backup_path: str) -> bool:
        """从全量备份恢复配置

        Args:
            backup_path: 备份文件路径 (.zip)

        Returns:
            bool: 是否成功
        """
        try:
            if not os.path.exists(backup_path):
                return False

            with zipfile.ZipFile(backup_path, 'r') as zf:
                # 1. 检查文件结构
                if 'data.json' not in zf.namelist():
                    logger.warning("invalid backup file: missing data.json")
                    return False

                # 2. 读取 data.json
                data_json_bytes = zf.read('data.json')
                data_dict = json.loads(data_json_bytes.decode('utf-8'))

                from .data_models import AppData
                restored_data = AppData.from_dict(data_dict)

                temp_icons_dir = Path(tempfile.mkdtemp(prefix="ql_restore_icons_", dir=str(self.install_dir)))
                # 3. 恢复背景图片
                bg_rel_path = data_dict.get('settings', {}).get('custom_bg_path', '')
                if bg_rel_path and not os.path.isabs(bg_rel_path):
                    # 如果是相对路径，说明是包内备份的背景
                    if bg_rel_path in zf.namelist():
                        # 解压到 app_dir 下
                        target_bg_path = self.app_dir / f"restored_bg_{os.path.basename(bg_rel_path)}"
                        with open(target_bg_path, 'wb') as f:
                            f.write(zf.read(bg_rel_path))
                        # 更新配置为绝对路径
                        data_dict['settings']['custom_bg_path'] = str(target_bg_path)

                # 4. 恢复图标
                for name in zf.namelist():
                    if name.startswith('icons/') and not name.endswith('/'):
                        # 解压图标
                        filename = os.path.basename(name)
                        if filename:
                            target_path = temp_icons_dir / filename
                            with open(target_path, 'wb') as f:
                                f.write(zf.read(name))

                # 5. 应用配置数据
                restored_data = AppData.from_dict(data_dict)

                backup_icons_dir = None
                try:
                    if self.icons_dir.exists():
                        backup_icons_dir = self.icons_dir.with_name(f"{self.icons_dir.name}_backup_restore")
                        if backup_icons_dir.exists():
                            shutil.rmtree(backup_icons_dir, ignore_errors=True)
                        self.icons_dir.replace(backup_icons_dir)

                    self.icons_dir.mkdir(parents=True, exist_ok=True)
                    for item in temp_icons_dir.iterdir():
                        shutil.move(str(item), str(self.icons_dir / item.name))

                    self.data = restored_data
                    self.save(immediate=True)
                except Exception:
                    shutil.rmtree(self.icons_dir, ignore_errors=True)
                    if backup_icons_dir and backup_icons_dir.exists():
                        backup_icons_dir.replace(self.icons_dir)
                    raise
                finally:
                    shutil.rmtree(temp_icons_dir, ignore_errors=True)

                if backup_icons_dir and backup_icons_dir.exists():
                    shutil.rmtree(backup_icons_dir, ignore_errors=True)

                return True

        except Exception as e:
            logger.exception("restore_full_config failed: %s", e)
            return False

    def export_shareable_config(self, save_path: str) -> bool:
        """导出可分享的配置（仅包含快捷键、网址、命令类型及其图标）

        Args:
            save_path: 保存路径 (.zip)

        Returns:
            bool: 是否成功
        """
        try:
            # 确保当前数据已保存
            self.save(immediate=True)

            # 获取完整配置
            data_dict = self.data.to_dict()

            # 创建可分享的配置副本
            shareable_dict = {
                'version': data_dict.get('version', '1.0'),
                'items': []
            }

            # 收集需要导出的图标文件
            icon_entries = []  # [(source_path, mode, archive_name)]

            # 遍历所有文件夹，只导出快捷键、命令、网址类型
            folders = data_dict.get('folders', [])
            for folder in folders:
                items = folder.get('items', folder.get('shortcuts', []))
                for shortcut in items:
                    shortcut_type = shortcut.get('type', 'file')
                    # 只导出这三种类型，排除 file（快捷方式）类型
                    if shortcut_type in ['hotkey', 'command', 'url']:
                        # 完整复制所有字段
                        original_id = shortcut.get('id') or str(uuid.uuid4())
                        item_copy = {
                            'id': original_id,
                            'name': shortcut.get('name', ''),
                            'type': shortcut.get('type', ''),
                            'order': shortcut.get('order', 0),
                            'target_path': shortcut.get('target_path', ''),
                            'target_args': shortcut.get('target_args', ''),
                            'working_dir': shortcut.get('working_dir', ''),
                            'hotkey': shortcut.get('hotkey', ''),
                            'hotkey_modifiers': shortcut.get('hotkey_modifiers', []),
                            'hotkey_key': shortcut.get('hotkey_key', ''),
                            'url': shortcut.get('url', ''),
                            'command': shortcut.get('command', ''),
                            'command_type': shortcut.get('command_type', 'cmd'),
                            'trigger_mode': shortcut.get('trigger_mode', 'immediate'),
                            'icon_data': shortcut.get('icon_data', ''),
                            'icon_invert_with_theme': shortcut.get('icon_invert_with_theme', False),
                            'icon_invert_current': shortcut.get('icon_invert_current', False),
                            'icon_invert_theme_when_set': shortcut.get('icon_invert_theme_when_set', '')
                        }

                        # 处理图标
                        icon_path = shortcut.get('icon_path', '')
                        if icon_path:
                            # 处理带图标索引的路径（如 "path.exe,0"）
                            actual_path = icon_path.split(',')[0] if ',' in icon_path else icon_path

                            if os.path.exists(actual_path):
                                # 如果是 exe/dll 文件，需要提取图标，使用 ICO 格式
                                ext = os.path.splitext(actual_path)[1].lower()
                                if ext in ['.exe', '.dll']:
                                    new_icon_name = f"{original_id}.png"
                                    # 标记需要提取图标，保留完整路径（包含索引）
                                    icon_entries.append((icon_path, 'extract', new_icon_name))
                                else:
                                    # 直接复制图标文件，保持原扩展名
                                    original_ext = os.path.splitext(actual_path)[1] or '.png'
                                    new_icon_name = f"{original_id}{original_ext}"
                                    icon_entries.append((actual_path, 'copy', new_icon_name))

                                item_copy['icon_path'] = f"icons/{new_icon_name}"
                            else:
                                item_copy['icon_path'] = ''
                        else:
                            item_copy['icon_path'] = ''

                        shareable_dict['items'].append(item_copy)

            # 创建 ZIP 压缩包
            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 写入配置文件
                zf.writestr('config.json', json.dumps(shareable_dict, ensure_ascii=False, indent=2))

                # 写入图标文件
                for orig_path, mode, new_name in icon_entries:
                    try:
                        if mode == 'extract':
                            # 从 exe/dll 提取图标
                            from core.icon_extractor import IconExtractor
                            # 使用 from_file 方法，它支持带索引的路径
                            pixmap = IconExtractor.from_file(orig_path, size=256, return_image=False)
                            if pixmap and not pixmap.isNull():
                                # 保存为临时文件
                                temp_path = os.path.join(tempfile.gettempdir(), new_name)
                                # 使用 PNG 格式保存更可靠
                                success = pixmap.save(temp_path, 'PNG')
                                if success:
                                    zf.write(temp_path, f"icons/{new_name}")
                                    os.remove(temp_path)
                        else:
                            # 直接复制图标文件
                            zf.write(orig_path, f"icons/{new_name}")
                    except Exception as e:
                        logger.warning("failed to add icon %s: %s", orig_path, e)

            return True

        except Exception as e:
            logger.exception("export_shareable_config failed: %s", e)
            return False

    def import_shareable_config(self, import_path: str, merge: bool = True) -> bool:
        """导入分享配置（仅导入快捷键、网址、命令类型及其图标）

        Args:
            import_path: 导入路径 (.zip)
            merge: 是否合并（保留参数兼容性）

        Returns:
            bool: 是否成功
        """
        try:
            if not os.path.exists(import_path):
                return False

            # 检查是否为 ZIP 文件
            if not zipfile.is_zipfile(import_path):
                return False

            with zipfile.ZipFile(import_path, 'r') as zf:
                # 读取配置文件
                if 'config.json' not in zf.namelist():
                    return False

                config_data = zf.read('config.json').decode('utf-8')
                import_dict = json.loads(config_data)

                # 获取导入的项目列表
                import_items = import_dict.get('items', [])
                if not import_items:
                    return False

                # 创建或查找"导入图标"分类
                from .data_models import Folder, ShortcutItem
                target_folder = None
                for folder in self.data.folders:
                    if folder.name == "导入图标":
                        target_folder = folder
                        break

                if not target_folder:
                    # 创建新分类
                    max_order = max((f.order for f in self.data.folders), default=0)
                    target_folder = Folder(name="导入图标", order=max_order + 1)
                    self.data.folders.append(target_folder)

                # 确保 icons 目录存在
                self.icons_dir.mkdir(parents=True, exist_ok=True)

                # 导入所有项目到"导入图标"分类
                max_order = max((s.order for s in target_folder.items), default=-1)
                for item_dict in import_items:
                    # 只导入快捷键、命令、网址类型
                    item_type = item_dict.get('type', 'file')
                    if item_type in ['hotkey', 'command', 'url']:
                        item_dict = dict(item_dict)
                        item_dict['id'] = str(uuid.uuid4())
                        # 处理图标
                        icon_path = item_dict.get('icon_path', '')
                        if icon_path and icon_path.startswith('icons/'):
                            # 从 ZIP 中提取图标
                            if icon_path in zf.namelist():
                                icon_ext = os.path.splitext(icon_path)[1] or '.png'
                                icon_filename = f"{item_dict['id']}{icon_ext}"
                                local_icon_path = self.icons_dir / icon_filename
                                with open(local_icon_path, 'wb') as f:
                                    f.write(zf.read(icon_path))
                                item_dict['icon_path'] = str(local_icon_path)
                            else:
                                item_dict['icon_path'] = ''
                        else:
                            item_dict['icon_path'] = ''

                        shortcut = ShortcutItem.from_dict(item_dict)
                        max_order += 1
                        shortcut.order = max_order
                        target_folder.items.append(shortcut)

            # 保存
            self.save(immediate=True)
            return True

        except Exception as e:
            logger.exception("import_shareable_config failed: %s", e)
            return False

    def redirect_missing_icon_paths(self, new_icon_path: str) -> int:
        """当用户修改某个图标路径后，自动将同目录下能匹配的缺失图标批量重定向。

        匹配规则：其他快捷方式的 icon_path 文件不存在，但文件名在 new_icon_path 所在目录中存在。
        保留原有的 icon_invert_with_theme / icon_invert_current 等属性不变。

        Returns:
            int: 重定向的数量
        """
        if not new_icon_path:
            return 0

        def _split_icon_location(path: str):
            raw = (path or '').strip()
            if not raw:
                return '', ''
            if ',' in raw:
                file_part, suffix = raw.rsplit(',', 1)
                suffix = suffix.strip()
                if suffix.lstrip('-').isdigit():
                    return file_part.strip(), f",{suffix}"
            return raw, ''

        new_icon_file, _ = _split_icon_location(new_icon_path)
        if not new_icon_file or not os.path.isfile(new_icon_file):
            return 0

        new_dir = os.path.dirname(os.path.abspath(new_icon_file))
        count = 0

        for folder in self.data.folders:
            for item in folder.items:
                if not item.icon_path:
                    continue
                raw_icon_path = (item.icon_path or '').strip()
                if os.path.normcase(raw_icon_path) == os.path.normcase(new_icon_path):
                    continue
                item_icon_file, item_icon_suffix = _split_icon_location(raw_icon_path)
                if not item_icon_file or os.path.isfile(item_icon_file):
                    continue
                # 文件名在新目录中存在则重定向
                filename = os.path.basename(item_icon_file)
                candidate_file = os.path.join(new_dir, filename)
                if os.path.isfile(candidate_file):
                    item.icon_path = f"{candidate_file}{item_icon_suffix}"
                    count += 1

        if count:
            self.save(immediate=True)

        return count
