"""内置图标管理模块"""
import os
import json
from typing import List, Dict
from core import ShortcutItem, ShortcutType


class BuiltinIconsManager:
    """内置图标管理器"""

    def __init__(self):
        self._builtin_dir = self._get_builtin_dir()
        self._config_file = os.path.join(self._builtin_dir, 'config.json')
        self._icons_dir = os.path.join(self._builtin_dir, 'icons')
        self._items = []
        self._load_builtin_items()

    def _get_builtin_dir(self) -> str:
        """获取内置图标目录"""
        import sys
        if getattr(sys, 'frozen', False):
            # 打包后的环境
            base_dir = sys._MEIPASS
        else:
            # 开发环境
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, 'assets', 'builtin_icons')

    def _load_builtin_items(self):
        """加载内置图标配置"""
        if not os.path.exists(self._config_file):
            return

        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item_data in data.get('items', []):
                    item = self._parse_item(item_data, self._builtin_dir)
                    if item:
                        self._items.append(item)
        except Exception:
            pass

    def _parse_item(self, data: Dict, base_dir: str) -> ShortcutItem:
        """解析配置项为ShortcutItem"""
        item = ShortcutItem()
        item.name = data.get('name', '未命名')

        # 解析类型
        type_str = data.get('type', 'command')
        if type_str == 'hotkey':
            item.type = ShortcutType.HOTKEY
            item.hotkey = data.get('hotkey', '')
        elif type_str == 'url':
            item.type = ShortcutType.URL
            item.url = data.get('url', '')
        elif type_str == 'command':
            item.type = ShortcutType.COMMAND
            item.command = data.get('command', '')
            item.command_type = data.get('command_type', 'cmd')
        else:
            item.type = ShortcutType.FILE
            item.target_path = data.get('target_path', '')

        # 图标路径
        icon_path = data.get('icon_path', '')
        if icon_path and not os.path.isabs(icon_path):
            # 统一使用正斜杠，然后转换为系统路径
            icon_path = icon_path.replace('/', os.sep).replace('\\', os.sep)
            icon_path = os.path.join(base_dir, icon_path)
        item.icon_path = icon_path

        # 图标反转参数
        item.icon_invert_with_theme = data.get('icon_invert_with_theme', False)
        item.icon_invert_current = data.get('icon_invert_current', False)
        item.icon_invert_theme_when_set = data.get('icon_invert_theme_when_set', '')

        return item

    def get_items(self) -> List[ShortcutItem]:
        """获取所有内置图标项（返回副本）"""
        return [self._copy_item(item) for item in self._items]

    def _copy_item(self, item: ShortcutItem) -> ShortcutItem:
        """复制ShortcutItem（生成新ID）"""
        new_item = ShortcutItem()
        new_item.name = item.name
        new_item.type = item.type
        new_item.target_path = item.target_path
        new_item.target_args = item.target_args
        new_item.working_dir = item.working_dir
        new_item.hotkey = item.hotkey
        new_item.url = item.url
        new_item.command = item.command
        new_item.command_type = item.command_type
        new_item.icon_path = item.icon_path
        new_item.icon_invert_with_theme = item.icon_invert_with_theme
        new_item.icon_invert_current = item.icon_invert_current
        new_item.icon_invert_theme_when_set = item.icon_invert_theme_when_set
        return new_item
