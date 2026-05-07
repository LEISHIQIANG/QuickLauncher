"""
文件夹监听器
使用 watchdog 库监听文件夹变化
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logging.warning("watchdog库未安装,文件夹自动同步功能不可用")
    # 创建虚拟基类以避免 NameError
    class FileSystemEventHandler:
        """虚拟基类 - watchdog 不可用时使用"""
        pass


logger = logging.getLogger(__name__)


class FolderChangeHandler(FileSystemEventHandler):
    """文件夹变化处理器"""

    def __init__(self, folder_id: str, callback: Callable):
        self.folder_id = folder_id
        self.callback = callback
        self._last_trigger_time = 0.0
        self._debounce_seconds = 2.0  # 防抖动时间

    def _trigger_sync(self):
        """触发同步(防抖动)"""
        now = time.time()
        if now - self._last_trigger_time < self._debounce_seconds:
            return

        self._last_trigger_time = now
        try:
            self.callback(self.folder_id)
        except Exception as e:
            logger.error(f"文件夹同步回调失败: {e}")

    def on_created(self, event):
        """文件或文件夹创建"""
        # 监听文件（.exe, .lnk）和文件夹的创建
        self._trigger_sync()

    def on_deleted(self, event):
        """文件或文件夹删除"""
        # 监听文件（.exe, .lnk）和文件夹的删除
        self._trigger_sync()

    def on_modified(self, event):
        """文件修改"""
        # 只在文件修改时触发（文件夹修改不触发）
        if not event.is_directory:
            self._trigger_sync()

    def on_moved(self, event):
        """文件或文件夹移动/重命名"""
        # 监听文件和文件夹的移动/重命名
        self._trigger_sync()


class FolderWatcherManager:
    """文件夹监听管理器(单例)"""

    def __init__(self):
        self.observer: Optional[Observer] = None
        self.watches: Dict[str, any] = {}  # folder_id -> watch_handle

        if WATCHDOG_AVAILABLE:
            self.observer = Observer()
            self.observer.start()

    def start_watch(self, folder_id: str, folder_path: str, callback: Callable):
        """开始监听文件夹

        Args:
            folder_id: 分类ID
            folder_path: 要监听的文件夹路径
            callback: 变化回调函数 callback(folder_id)
        """
        if not WATCHDOG_AVAILABLE or not self.observer:
            logger.warning("watchdog不可用,无法启动文件夹监听")
            return

        # 停止旧的监听
        self.stop_watch(folder_id)

        watch_path = Path(folder_path)
        if not watch_path.exists() or not watch_path.is_dir():
            logger.warning(f"跳过启动文件夹监听，路径不可用: {folder_path}")
            return

        # 创建处理器
        handler = FolderChangeHandler(folder_id, callback)

        # 启动监听(不递归,用户需求)
        try:
            watch = self.observer.schedule(
                handler,
                str(watch_path),
                recursive=False  # 不递归(用户需求)
            )
            self.watches[folder_id] = watch
            logger.info(f"开始监听文件夹: {folder_path}")
        except Exception as e:
            logger.error(f"启动文件夹监听失败: {e}")

    def stop_watch(self, folder_id: str):
        """停止监听文件夹"""
        if folder_id in self.watches:
            try:
                if self.observer:
                    self.observer.unschedule(self.watches[folder_id])
                del self.watches[folder_id]
                logger.info(f"停止监听文件夹: {folder_id}")
            except Exception as e:
                logger.error(f"停止监听失败: {e}")

    def stop_all(self):
        """停止所有监听"""
        observer = self.observer
        self.observer = None
        if observer:
            try:
                observer.stop()
                observer.join(timeout=1.5)
            except Exception:
                pass
        self.watches.clear()


# 全局单例
_watcher_manager: Optional[FolderWatcherManager] = None
_watcher_lock = threading.Lock()


def get_watcher_manager() -> FolderWatcherManager:
    """获取全局监听管理器（线程安全）"""
    global _watcher_manager
    if _watcher_manager is None:
        with _watcher_lock:
            if _watcher_manager is None:
                _watcher_manager = FolderWatcherManager()
    return _watcher_manager


def shutdown_watcher_manager():
    """Stop and reset the global watcher manager."""
    global _watcher_manager
    with _watcher_lock:
        manager = _watcher_manager
        _watcher_manager = None

    if manager is not None:
        manager.stop_all()
