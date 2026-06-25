"""
文件夹监听器
使用原生 QLwatch.dll (IOCP + ReadDirectoryChangesW) — 硬依赖，无Python回退
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from .native_services import _QLWatchEngine

logger = logging.getLogger(__name__)


class FolderWatcherManager:
    """文件夹监听管理器(单例) — 硬依赖 QLwatch.dll"""

    def __init__(self):
        self._engine = _QLWatchEngine.get()

    def start_watch(self, folder_id: str, folder_path: str, callback: Callable):
        watch_path = Path(folder_path)
        if not watch_path.exists() or not watch_path.is_dir():
            logger.warning(f"跳过启动文件夹监听，路径不可用: {folder_path}")
            return

        self.stop_watch(folder_id)
        try:
            self._engine.start_watch(folder_id, str(watch_path), callback)
            logger.info(f"开始监听文件夹: {folder_path}")
        except Exception as exc:
            logger.error(f"启动文件夹监听失败: {exc}")
            raise

    def stop_watch(self, folder_id: str):
        try:
            self._engine.stop_watch(folder_id)
            logger.info(f"停止监听文件夹: {folder_id}")
        except Exception as exc:
            logger.debug("停止监听失败: %s", exc)

    def stop_all(self):
        try:
            self._engine.stop_all()
        except Exception as exc:
            logger.debug("停止所有监听失败: %s", exc)


_watcher_manager: FolderWatcherManager | None = None
_watcher_lock = threading.Lock()


def get_watcher_manager() -> FolderWatcherManager:
    global _watcher_manager
    if _watcher_manager is None:
        with _watcher_lock:
            if _watcher_manager is None:
                _watcher_manager = FolderWatcherManager()
    return _watcher_manager


def shutdown_watcher_manager():
    global _watcher_manager
    with _watcher_lock:
        manager = _watcher_manager
        _watcher_manager = None
    if manager is not None:
        manager.stop_all()
