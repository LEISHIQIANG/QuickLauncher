"""
配置文件迁移工具
将配置从 APPDATA 迁移到安装目录
"""

import os
import shutil
import json
from pathlib import Path
from typing import Optional


class ConfigMigrator:
    """配置迁移器"""

    @staticmethod
    def get_old_config_dir() -> Path:
        """获取旧的配置目录（APPDATA）"""
        appdata = os.environ.get('APPDATA', '')
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return Path(appdata) / 'QuickLauncher'

    @staticmethod
    def get_new_config_dir() -> Path:
        """获取新的配置目录（安装路径/config）"""
        import sys
        if getattr(sys, 'frozen', False):
            install_dir = Path(sys.executable).parent
        else:
            install_dir = Path(__file__).parent.parent
        return install_dir / 'config'

    @staticmethod
    def needs_migration() -> bool:
        """检查是否需要迁移"""
        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()

        # 如果旧目录存在且有 data.json，新目录不存在或为空
        old_data = old_dir / 'data.json'
        new_data = new_dir / 'data.json'

        return old_data.exists() and not new_data.exists()

    @staticmethod
    def migrate(progress_callback=None) -> dict:
        """执行迁移

        Args:
            progress_callback: 进度回调 (message: str, progress: float)

        Returns:
            dict: 迁移结果统计
        """
        import logging
        logger = logging.getLogger(__name__)

        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()

        stats = {
            'success': False,
            'files_moved': 0,
            'errors': []
        }

        def report(msg, progress):
            logger.info(msg)
            if progress_callback:
                try:
                    progress_callback(msg, progress)
                except Exception as e:
                    logger.debug(f"progress_callback 调用失败: {e}")

        try:
            if not old_dir.exists():
                logger.info(f"旧配置目录不存在: {old_dir}")
                stats['success'] = True
                return stats

            old_data = old_dir / 'data.json'
            if not old_data.exists():
                logger.info(f"旧配置文件不存在: {old_data}")
                stats['success'] = True
                return stats

            logger.info(f"开始迁移配置: {old_dir} -> {new_dir}")
            new_dir.mkdir(parents=True, exist_ok=True)
            report("正在迁移配置文件...", 0.1)

            # 迁移所有文件和文件夹
            for item in old_dir.iterdir():
                try:
                    target = new_dir / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                        shutil.rmtree(str(item))
                    else:
                        shutil.move(str(item), str(target))
                    stats['files_moved'] += 1
                    logger.info(f"已迁移: {item.name}")
                except Exception as e:
                    stats['errors'].append(f"迁移 {item.name} 失败: {e}")
                    logger.error(f"迁移 {item.name} 失败: {e}")

            report(f"迁移完成，共迁移 {stats['files_moved']} 个文件", 0.9)

            # 删除旧目录
            try:
                if old_dir.exists() and not any(old_dir.iterdir()):
                    old_dir.rmdir()
                    logger.info(f"已删除旧配置目录: {old_dir}")
            except Exception as e:
                logger.warning(f"删除旧目录失败: {e}")

            stats['success'] = True
            report("配置迁移成功", 1.0)

        except Exception as e:
            stats['errors'].append(f"迁移失败: {e}")
            logger.error(f"配置迁移失败: {e}")

        return stats

