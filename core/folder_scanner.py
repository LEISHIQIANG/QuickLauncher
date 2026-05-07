"""
文件夹扫描器
扫描物理文件夹,生成快捷方式列表
"""

import os
import logging
from pathlib import Path
from typing import List
from .data_models import ShortcutItem, ShortcutType
import uuid


logger = logging.getLogger(__name__)


class FolderScanner:
    """文件夹扫描器"""

    # 支持的文件扩展名(用户需求: .lnk 和 .exe)
    SUPPORTED_EXTENSIONS = {".lnk", ".exe"}

    # 是否包含子文件夹(用户需求: 识别文件夹)
    INCLUDE_FOLDERS = True

    # 排除的文件名模式(避免扫描无用文件)
    EXCLUDE_PATTERNS = [
        "unins", "uninst", "uninstall",  # 卸载程序
        "setup", "install",  # 安装程序
    ]

    @staticmethod
    def scan_folder(folder_path: str) -> List[ShortcutItem]:
        """扫描文件夹(非递归,仅当前目录)

        Args:
            folder_path: 要扫描的文件夹路径

        Returns:
            List[ShortcutItem]: 扫描到的快捷方式列表
        """
        shortcuts = []

        try:
            folder = Path(folder_path)
            if not folder.exists() or not folder.is_dir():
                return shortcuts

            # 遍历当前文件夹的直接子文件(不递归)
            for file_path in folder.iterdir():
                # 检查是否为文件夹(用户需求: 支持子文件夹)
                if file_path.is_dir():
                    if FolderScanner.INCLUDE_FOLDERS:
                        # 创建文件夹快捷方式
                        shortcut = FolderScanner._create_folder_shortcut(file_path)
                        if shortcut:
                            shortcuts.append(shortcut)
                    continue

                # 检查文件扩展名
                if file_path.suffix.lower() not in FolderScanner.SUPPORTED_EXTENSIONS:
                    continue

                # 检查排除模式
                if FolderScanner._should_exclude(file_path.name):
                    continue

                # 创建快捷方式
                shortcut = FolderScanner._create_shortcut(file_path)
                if shortcut:
                    shortcuts.append(shortcut)

        except Exception as e:
            # 访问权限不足等错误
            logger.error(f"扫描文件夹失败 {folder_path}: {e}")

        return shortcuts

    @staticmethod
    def _should_exclude(filename: str) -> bool:
        """判断文件是否应该被排除"""
        name_lower = filename.lower()
        for pattern in FolderScanner.EXCLUDE_PATTERNS:
            if pattern in name_lower:
                return True
        return False

    @staticmethod
    def _create_shortcut(file_path: Path) -> ShortcutItem:
        """从文件创建快捷方式对象"""
        shortcut = ShortcutItem()
        shortcut.id = str(uuid.uuid4())
        shortcut.name = file_path.stem  # 不含扩展名的文件名
        shortcut.target_path = str(file_path)

        if file_path.suffix.lower() == ".lnk":
            # 快捷方式: 解析目标
            shortcut.type = ShortcutType.FILE
            # 使用 shortcut_parser 解析 .lnk 文件
            try:
                from .shortcut_parser import ShortcutParser
                parsed = ShortcutParser.parse(str(file_path))
                if parsed:
                    shortcut.target_path = parsed.get("target", str(file_path))
                    shortcut.target_args = parsed.get("args", "")
                    shortcut.working_dir = parsed.get("working_dir", "")
                    # 如果没有更友好的名称,使用文件名
                    # .lnk 文件的名称通常就是文件名本身
            except Exception as e:
                logger.debug(f"解析快捷方式失败 {file_path}: {e}")
        else:
            # .exe 文件: 直接作为目标
            shortcut.type = ShortcutType.FILE

        return shortcut

    @staticmethod
    def _create_folder_shortcut(folder_path: Path) -> ShortcutItem:
        """从文件夹创建快捷方式对象"""
        shortcut = ShortcutItem()
        shortcut.id = str(uuid.uuid4())
        shortcut.name = folder_path.name  # 文件夹名称
        shortcut.target_path = str(folder_path)
        shortcut.type = ShortcutType.FOLDER  # 设置为文件夹类型

        return shortcut
