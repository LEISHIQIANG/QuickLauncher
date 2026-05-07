"""
快捷键冲突检测器
"""

import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger(__name__)

# Windows 系统快捷键列表
SYSTEM_HOTKEYS = {
    "Win+D": "显示桌面",
    "Win+E": "打开资源管理器",
    "Win+L": "锁定计算机",
    "Win+R": "运行",
    "Win+Tab": "任务视图",
    "Win+I": "设置",
    "Win+A": "操作中心",
    "Win+S": "搜索",
    "Win+X": "快速链接菜单",
    "Win+P": "投影",
    "Win+K": "连接",
    "Ctrl+Alt+Delete": "安全选项",
    "Ctrl+Shift+Esc": "任务管理器",
    "Alt+Tab": "切换窗口",
    "Alt+F4": "关闭窗口",
    "Ctrl+C": "复制",
    "Ctrl+V": "粘贴",
    "Ctrl+X": "剪切",
    "Ctrl+Z": "撤销",
    "Ctrl+A": "全选",
}


def normalize_hotkey(hotkey_str: str) -> str:
    """标准化快捷键字符串"""
    parts = [p.strip().lower() for p in hotkey_str.replace("+", " ").split()]

    # 排序修饰键
    modifiers = []
    key = ""

    for part in parts:
        if part in ["ctrl", "control"]:
            modifiers.append("ctrl")
        elif part in ["alt"]:
            modifiers.append("alt")
        elif part in ["shift"]:
            modifiers.append("shift")
        elif part in ["win", "windows", "super"]:
            modifiers.append("win")
        else:
            key = part

    # 按固定顺序排列
    order = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}
    modifiers.sort(key=lambda x: order.get(x, 99))

    result = "+".join(modifiers)
    if key:
        result = result + "+" + key if result else key

    return result.title()


def check_conflict(hotkey_str: str) -> tuple:
    """
    检查快捷键是否与系统快捷键冲突

    Returns:
        (is_conflict: bool, conflict_desc: str)
    """
    if not hotkey_str or not hotkey_str.strip():
        return False, ""

    normalized = normalize_hotkey(hotkey_str)

    # 检查系统快捷键
    for sys_key, desc in SYSTEM_HOTKEYS.items():
        if normalize_hotkey(sys_key) == normalized:
            return True, f"与系统快捷键冲突：{desc}"

    # 检查常见软件快捷键
    common_conflicts = {
        "Ctrl+S": "保存（常用）",
        "Ctrl+O": "打开（常用）",
        "Ctrl+N": "新建（常用）",
        "Ctrl+W": "关闭（常用）",
        "Ctrl+P": "打印（常用）",
        "Ctrl+F": "查找（常用）",
        "Ctrl+H": "替换（常用）",
    }

    for common_key, desc in common_conflicts.items():
        if normalize_hotkey(common_key) == normalized:
            return True, f"与常用快捷键冲突：{desc}"

    return False, ""


def is_hotkey_registered(modifiers: list, key: str) -> bool:
    """
    检查快捷键是否已被其他程序注册（Windows API）
    注意：此方法可能不完全准确，仅供参考
    """
    try:
        user32 = ctypes.windll.user32

        # 转换修饰键
        mod_flags = 0
        for mod in modifiers:
            mod_lower = mod.lower()
            if mod_lower == "alt":
                mod_flags |= 0x0001  # MOD_ALT
            elif mod_lower == "ctrl":
                mod_flags |= 0x0002  # MOD_CONTROL
            elif mod_lower == "shift":
                mod_flags |= 0x0004  # MOD_SHIFT
            elif mod_lower == "win":
                mod_flags |= 0x0008  # MOD_WIN

        # 转换按键
        vk_code = _get_vk_code(key)
        if vk_code == 0:
            return False

        # 尝试注册，如果失败说明已被占用
        result = user32.RegisterHotKey(None, 1, mod_flags, vk_code)

        if result:
            # 注册成功，立即取消注册
            user32.UnregisterHotKey(None, 1)
            return False
        else:
            # 注册失败，可能已被占用
            return True

    except Exception as e:
        logger.debug(f"检查快捷键注册状态失败: {e}")
        return False


def _get_vk_code(key: str) -> int:
    """获取虚拟键码"""
    key_upper = key.upper()

    # 字母和数字
    if len(key_upper) == 1:
        if 'A' <= key_upper <= 'Z':
            return ord(key_upper)
        if '0' <= key_upper <= '9':
            return ord(key_upper)

    # 功能键
    vk_map = {
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
        "SPACE": 0x20, "ENTER": 0x0D, "ESC": 0x1B,
        "TAB": 0x09, "BACKSPACE": 0x08, "DELETE": 0x2E,
        "INSERT": 0x2D, "HOME": 0x24, "END": 0x23,
        "PAGEUP": 0x21, "PAGEDOWN": 0x22,
        "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    }

    return vk_map.get(key_upper, 0)
