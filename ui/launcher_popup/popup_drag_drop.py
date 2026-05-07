"""Drag and drop helpers for LauncherPopup."""

import logging
import os
import subprocess
import traceback

from qt_compat import QTimer
from core import ShortcutItem, ShortcutType

try:
    from core import ShortcutExecutor
    HAS_EXECUTOR = True
except ImportError:
    ShortcutExecutor = None
    HAS_EXECUTOR = False

logger = logging.getLogger(__name__)


class PopupDragDropMixin:
    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            # 检查是否有本地文件
            for url in mime_data.urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    self._is_dragging = True
                    logger.debug("接受拖放文件")
                    return
        event.ignore()
    def dragMoveEvent(self, event):
        """拖拽移动事件 - 更新悬停状态"""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        
        pos = self._get_event_pos(event)
        new_drag_hover = -1
        new_drag_dock_hover = -1
        
        # 检查 Dock 区域
        if pos.y() >= self.dock_y and self.dock_items:
            dock_height_mode = getattr(self.settings, 'dock_height_mode', 1)
            visible_count = len(self.dock_items)
            if dock_height_mode == 1:
                visible_count = min(visible_count, self.cols)
            max_cols = self.cols
            line_width = max_cols * self.cell_size if (dock_height_mode > 1 and visible_count > max_cols) else min(visible_count, max_cols) * self.cell_size
            start_x = (self.width() - line_width) // 2
            dock_row_stride = self.icon_size + 6  # 行间距6px
            
            if start_x <= pos.x() < start_x + line_width:
                dock_col = (pos.x() - start_x) // self.cell_size
                dock_row = (pos.y() - self.dock_y - 8) // dock_row_stride
                if 0 <= dock_col < max_cols and 0 <= dock_row < dock_height_mode:
                    idx = dock_row * max_cols + dock_col
                    if 0 <= idx < visible_count:
                        item = self.dock_items[idx]
                        # 只有 FILE 和 FOLDER 类型支持拖放
                        if item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
                            new_drag_dock_hover = idx
        
        # 检查主图标区域
        elif self.padding <= pos.x() and self.padding <= pos.y() < self.content_height:
            col = (pos.x() - self.padding) // self.cell_size
            row = (pos.y() - self.padding) // self.cell_h

            if 0 <= col < self.cols and row < self.fixed_rows:
                index = row * self.cols + col

                if self.pages and self.current_page < len(self.pages):
                    items = self.pages[self.current_page].items
                    if 0 <= index < len(items):
                        item = items[index]
                        # 只有 FILE 和 FOLDER 类型支持拖放
                        if item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
                            new_drag_hover = index
        
        # 更新状态并重绘
        if new_drag_hover != self._drag_hover_index or new_drag_dock_hover != self._drag_dock_hover_index:
            self._drag_hover_index = new_drag_hover
            self._drag_dock_hover_index = new_drag_dock_hover
            self.update()
        
        # 如果悬停在有效目标上，接受拖放
        if new_drag_hover >= 0 or new_drag_dock_hover >= 0:
            event.acceptProposedAction()
        else:
            event.ignore()
    def dragLeaveEvent(self, event):
        """拖拽离开事件"""
        self._drag_hover_index = -1
        self._drag_dock_hover_index = -1
        self._is_dragging = False
        self.update()
    def dropEvent(self, event):
        """拖放释放事件"""
        self._is_dragging = False
        mime_data = event.mimeData()
        
        if not mime_data.hasUrls():
            event.ignore()
            self._reset_drag_state()
            return
        
        # 获取拖放的文件列表
        dropped_files = []
        for url in mime_data.urls():
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if os.path.exists(file_path):
                    dropped_files.append(file_path)
        
        if not dropped_files:
            event.ignore()
            self._reset_drag_state()
            return
        
        # 确定目标快捷方式
        target_item = None
        
        if self._drag_dock_hover_index >= 0 and self._drag_dock_hover_index < len(self.dock_items):
            target_item = self.dock_items[self._drag_dock_hover_index]
        elif self._drag_hover_index >= 0:
            if self.pages and self.current_page < len(self.pages):
                items = self.pages[self.current_page].items
                if self._drag_hover_index < len(items):
                    target_item = items[self._drag_hover_index]
        
        # 重置拖放状态
        self._reset_drag_state()
        
        if target_item and target_item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
            event.acceptProposedAction()
            logger.info(f"拖放文件到: {target_item.name}, 文件数: {len(dropped_files)}")
            
            # 执行拖放打开
            self._execute_drop(target_item, dropped_files)
        else:
            event.ignore()
    def _reset_drag_state(self):
        """重置拖放状态"""
        self._drag_hover_index = -1
        self._drag_dock_hover_index = -1
        self._is_dragging = False
        self.update()
    def _execute_drop(self, item: ShortcutItem, files: list):
        """执行拖放打开操作"""
        if self._executing:
            return
        
        self._executing = True
        logger.info(f"拖放执行: {item.name} 打开 {len(files)} 个文件")
        
        should_close = not self.is_pinned
        
        if should_close:
            self.hide()
        
        QTimer.singleShot(100, lambda: self._do_execute_drop(item, files, should_close))
    def _do_execute_drop(self, item: ShortcutItem, files: list, should_close: bool):
        """实际执行拖放打开"""
        try:
            if HAS_EXECUTOR and ShortcutExecutor:
                ShortcutExecutor.execute_with_files(item, files)
            else:
                # 后备方案：使用 subprocess（确保子进程独立于父进程）
                target = item.target_path
                if target:
                    import subprocess
                    # 进程创建标志：确保子进程脱离 Job Object，不随父进程终止
                    DETACHED_PROCESS = 0x00000008
                    CREATE_NEW_PROCESS_GROUP = 0x00000200
                    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
                    for file_path in files:
                        try:
                            if target.lower().endswith('.exe'):
                                subprocess.Popen(
                                    [target, file_path],
                                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
                                    close_fds=True,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                            else:
                                subprocess.Popen(
                                    f'start "" "{target}" "{file_path}"',
                                    shell=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
                                    close_fds=True,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                            logger.info(f"后备方案打开: {target} -> {file_path}")
                        except Exception as e:
                            logger.error(f"后备方案失败: {e}")
        except Exception as e:
            logger.error(f"拖放执行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._executing = False
            if should_close:
                self.close()
