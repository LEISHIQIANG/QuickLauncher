"""
配置文件迁移工具
将配置从 APPDATA 迁移到安装目录
"""

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_MARKER = ".migration_done"
_BACKUP_DIR = ".pre_migration_backup"


class ConfigMigrator:
    """配置迁移器"""

    @staticmethod
    def get_old_config_dir() -> Path:
        """获取旧的配置目录（APPDATA）"""
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return Path(appdata) / "QuickLauncher"

    @staticmethod
    def get_new_config_dir() -> Path:
        """获取新的配置目录（安装路径/config）"""
        if getattr(sys, "frozen", False):
            install_dir = Path(sys.executable).parent
        else:
            install_dir = Path(__file__).parent.parent
        return install_dir / "config"

    @staticmethod
    def needs_migration() -> bool:
        """检查是否需要迁移

        增加 marker 检查：即使 new_data 已存在，如果 old 目录仍有残留且 marker 缺失，
        说明上次迁移中断，应返回 True 让 migrate() 内部走前向恢复逻辑。
        """
        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()

        old_data = old_dir / "data.json"
        new_data = new_dir / "data.json"

        if not old_data.exists():
            return False

        if not new_data.exists():
            return True

        # new_data 存在但 marker 缺失 → 上次迁移中断，需要补全
        if old_dir.exists() and not (new_dir / _MIGRATION_MARKER).exists():
            return True

        return False

    @staticmethod
    def needs_partial_recovery() -> bool:
        """检测上次迁移中断的残留状态。

        条件：旧目录仍存在，新目录已有 data.json，但无迁移完成标记。
        """
        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()

        if not old_dir.exists():
            return False
        if not (new_dir / "data.json").exists():
            return False
        return not (new_dir / _MIGRATION_MARKER).exists()

    @staticmethod
    def recover_partial(progress_callback=None) -> dict:
        """恢复上次中断的迁移：将旧目录中剩余文件补拷到新目录。

        Returns:
            dict: 恢复结果统计
        """
        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()
        stats = {"success": False, "files_recovered": 0, "errors": []}

        def report(msg, progress):
            logger.info(msg)
            if progress_callback:
                try:
                    progress_callback(msg, progress)
                except Exception as exc:
                    logger.debug("调用进度回调失败: %s", exc, exc_info=True)

        if not old_dir.exists():
            stats["success"] = True
            return stats

        try:
            report("检测到上次迁移中断，正在补全迁移...", 0.1)
            for item in old_dir.iterdir():
                try:
                    target = new_dir / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                        shutil.rmtree(str(item))
                    else:
                        shutil.move(str(item), str(target))
                    stats["files_recovered"] += 1
                    logger.debug("已补迁: %s", item.name)
                except Exception as e:
                    stats["errors"].append(f"补迁 {item.name} 失败: {e}")
                    logger.error("补迁 %s 失败: %s", item.name, e)

            # 清理空的旧目录
            try:
                if old_dir.exists() and not any(old_dir.iterdir()):
                    old_dir.rmdir()
            except Exception as exc:
                logger.debug("删除空旧目录失败: %s", exc, exc_info=True)

            # 写入完成标记
            try:
                (new_dir / _MIGRATION_MARKER).write_text("recovered_from_partial\n", encoding="utf-8")
            except Exception as e:
                logger.warning("写入迁移标记失败: %s", e)

            stats["success"] = len(stats["errors"]) == 0
            report("中断迁移已恢复", 1.0)
        except Exception as e:
            stats["errors"].append(f"恢复失败: {e}")
            logger.error("恢复中断迁移失败: %s", e)

        return stats

    @staticmethod
    def migrate(progress_callback=None) -> dict:
        """执行迁移（原子性：先备份，成功后写标记）。

        Args:
            progress_callback: 进度回调 (message: str, progress: float)

        Returns:
            dict: 迁移结果统计
        """
        old_dir = ConfigMigrator.get_old_config_dir()
        new_dir = ConfigMigrator.get_new_config_dir()

        stats = {"success": False, "files_moved": 0, "errors": []}

        def report(msg, progress):
            logger.info(msg)
            if progress_callback:
                try:
                    progress_callback(msg, progress)
                except Exception as e:
                    logger.debug("progress_callback 调用失败: %s", e)

        try:
            if not old_dir.exists():
                logger.debug("旧配置目录不存在: %s", old_dir)
                stats["success"] = True
                return stats

            old_data = old_dir / "data.json"
            new_data = new_dir / "data.json"

            # 处理部分迁移恢复：data.json 已到新目录但 marker 缺失
            if not old_data.exists() and new_data.exists() and old_dir.exists():
                logger.info("检测到部分迁移状态（data.json 已迁移），补全剩余文件")
                report("正在补全上次中断的迁移...", 0.1)
                return ConfigMigrator.recover_partial(progress_callback)

            if not old_data.exists():
                logger.info("旧配置文件不存在: %s", old_data)
                stats["success"] = True
                return stats

            logger.debug("开始迁移配置: %s -> %s", old_dir, new_dir)
            new_dir.mkdir(parents=True, exist_ok=True)
            report("正在迁移配置文件...", 0.1)

            # Step 1: 创建旧目录完整备份
            backup_dir = new_dir / _BACKUP_DIR
            try:
                if backup_dir.exists():
                    shutil.rmtree(str(backup_dir))
                shutil.copytree(str(old_dir), str(backup_dir))
                logger.info("已创建迁移前备份: %s", backup_dir)
                report("备份完成，开始迁移...", 0.2)
            except Exception as e:
                stats["errors"].append(f"创建备份失败: {e}")
                logger.error("创建迁移备份失败: %s", e)
                return stats

            # Step 2: 迁移所有文件和文件夹
            for item in old_dir.iterdir():
                try:
                    target = new_dir / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                        shutil.rmtree(str(item))
                    else:
                        shutil.move(str(item), str(target))
                    stats["files_moved"] += 1
                    logger.debug("已迁移: %s", item.name)
                except Exception as e:
                    stats["errors"].append(f"迁移 {item.name} 失败: {e}")
                    logger.error("迁移 %s 失败: %s", item.name, e)

            report(f"迁移完成，共迁移 {stats['files_moved']} 个文件", 0.9)

            # Step 3: 写入完成标记
            try:
                (new_dir / _MIGRATION_MARKER).write_text("migration_completed\n", encoding="utf-8")
            except Exception as e:
                logger.warning("写入迁移标记失败: %s", e)
                stats["errors"].append(f"写入标记失败: {e}")

            # Step 4: 删除旧目录
            try:
                if old_dir.exists():
                    remaining = list(old_dir.iterdir())
                    if not remaining:
                        old_dir.rmdir()
                        logger.debug("已删除旧配置目录: %s", old_dir)
                    else:
                        logger.warning("旧配置目录仍有残留文件: %s", [f.name for f in remaining])
            except Exception as e:
                logger.warning("删除旧目录失败: %s", e)

            # Step 5: 清理备份（仅在迁移无错误时删除）
            if not stats["errors"]:
                try:
                    if backup_dir.exists():
                        shutil.rmtree(str(backup_dir))
                except Exception as exc:
                    logger.debug("删除备份目录失败: %s", exc, exc_info=True)

            stats["success"] = len(stats["errors"]) == 0
            report("配置迁移成功", 1.0)

        except Exception as e:
            stats["errors"].append(f"迁移失败: {e}")
            logger.error("配置迁移失败: %s", e)

        return stats
