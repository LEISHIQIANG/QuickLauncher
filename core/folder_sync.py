"""
文件夹同步
比对物理文件夹和数据库,执行增量同步
"""

import logging
import os
import time

from .data_manager import DataManager
from .folder_scanner import FolderScanner

logger = logging.getLogger(__name__)
_last_sync_status: dict[str, dict] = {}


def get_folder_sync_status(folder_id: str | None = None) -> dict:
    """Return last folder sync status for diagnostics."""
    if folder_id:
        return dict(_last_sync_status.get(folder_id, {}))
    return {key: dict(value) for key, value in _last_sync_status.items()}


def _set_sync_status(folder_id: str, **kwargs):
    status = dict(_last_sync_status.get(folder_id, {}))
    status.update(kwargs)
    status["timestamp"] = time.time()
    _last_sync_status[folder_id] = status


def sync_folder(data_manager: DataManager, folder_id: str) -> tuple[int, int]:
    """同步文件夹内容

    根据用户需求: 完全同步(包括删除)
    - 添加新文件
    - 删除不存在的文件

    Args:
        data_manager: 数据管理器
        folder_id: 要同步的分类ID

    Returns:
        Tuple[int, int]: (新增数量, 删除数量)
    """
    folder = data_manager.data.get_folder_by_id(folder_id)
    if not folder or not folder.linked_path:
        _set_sync_status(folder_id, ok=False, reason="folder_not_linked", added=0, removed=0)
        return 0, 0

    linked_path = os.path.abspath(folder.linked_path)
    if not os.path.isdir(linked_path):
        logger.warning(f"文件夹同步已跳过，绑定目录不可用: {folder.linked_path}")
        _set_sync_status(folder_id, ok=False, reason="linked_path_missing", path=folder.linked_path, added=0, removed=0)
        return 0, 0

    # 1. 扫描物理文件夹
    try:
        scanned_shortcuts = FolderScanner.scan_folder(linked_path)
    except Exception as e:
        logger.error("文件夹同步扫描失败: %s", e)
        _set_sync_status(folder_id, ok=False, reason=f"scan_failed: {e}", path=linked_path, added=0, removed=0)
        return 0, 0

    # 2. 构建路径集合(忽略大小写)
    scanned_paths = {(s.target_path or "").lower() for s in scanned_shortcuts}
    existing_items = folder.items[:]  # 复制列表
    existing_paths = {(s.target_path or "").lower() for s in existing_items}

    # 3. 计算差异
    to_add_paths = scanned_paths - existing_paths
    to_remove_paths = existing_paths - scanned_paths

    added_count = 0
    removed_count = 0

    # 4. 合并增删改，整个同步过程只落盘一次
    with data_manager.batch_update(immediate=True):
        to_add_shortcuts = [s for s in scanned_shortcuts if (s.target_path or "").lower() in to_add_paths]
        if to_add_shortcuts:
            data_manager.add_shortcuts(folder_id, to_add_shortcuts)
            added_count = len(to_add_shortcuts)
            logger.info(f"文件夹同步: 新增 {added_count} 个快捷方式")

        for item in existing_items:
            if (item.target_path or "").lower() in to_remove_paths:
                data_manager.delete_shortcut(folder_id, item.id)
                removed_count += 1

        if removed_count > 0:
            logger.info(f"文件夹同步: 删除 {removed_count} 个快捷方式")

        folder.last_sync_time = time.time()
        data_manager.save()

    _set_sync_status(
        folder_id,
        ok=True,
        reason="synced",
        path=linked_path,
        added=added_count,
        removed=removed_count,
        total=len(scanned_shortcuts),
    )
    logger.info(
        "文件夹同步完成: folder=%s added=%s removed=%s total=%s",
        folder_id,
        added_count,
        removed_count,
        len(scanned_shortcuts),
    )
    return added_count, removed_count
