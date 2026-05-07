"""
快捷方式解析器
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    logger.warning("win32com 未安装，.lnk 解析功能不可用")


class ShortcutParser:
    """快捷方式解析器"""
    
    @staticmethod
    def parse(file_path: str) -> Dict[str, Any]:
        """解析快捷方式文件"""
        result = {
            'target': file_path,
            'args': '',
            'working_dir': '',
            'icon_location': '',
            'icon_index': 0
        }
        
        if not os.path.exists(file_path):
            return result
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.lnk' and HAS_WIN32COM:
            try:
                result = ShortcutParser._parse_lnk(file_path)
            except Exception as e:
                logger.debug(f"解析 lnk 失败: {e}")
        elif ext == '.url':
            try:
                result = ShortcutParser._parse_url(file_path)
            except Exception as e:
                logger.debug(f"解析 url 失败: {e}")
        
        return result
    
    @staticmethod
    def _parse_lnk(file_path: str) -> Dict[str, Any]:
        """解析 .lnk 快捷方式"""
        result = {
            'target': file_path,
            'args': '',
            'working_dir': '',
            'icon_location': '',
            'icon_index': 0
        }
        
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(file_path)
        
        result['target'] = shortcut.TargetPath or file_path
        result['args'] = shortcut.Arguments or ''
        result['working_dir'] = shortcut.WorkingDirectory or ''
        
        icon_location = shortcut.IconLocation or ''
        if icon_location:
            parts = icon_location.rsplit(',', 1)
            result['icon_location'] = parts[0]
            if len(parts) > 1:
                try:
                    result['icon_index'] = int(parts[1])
                except ValueError:
                    pass
        
        return result
    
    @staticmethod
    def _parse_url(file_path: str) -> Dict[str, Any]:
        """解析 .url 快捷方式"""
        result = {
            'target': file_path,
            'args': '',
            'working_dir': '',
            'icon_location': '',
            'icon_index': 0
        }
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('URL='):
                    result['target'] = line[4:]
                elif line.startswith('IconFile='):
                    result['icon_location'] = line[9:]
                elif line.startswith('IconIndex='):
                    try:
                        result['icon_index'] = int(line[10:])
                    except ValueError:
                        pass
        
        return result