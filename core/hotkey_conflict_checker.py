"""
快捷键冲突检测器
"""

import ctypes
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
    "Win+V": "剪贴板历史",
    "Win+Shift+S": "截图工具",
    "Win+;": "Emoji面板",
    "Win+.": "符号面板",
    "Win+G": "Xbox Game Bar",
    "Win+H": "语音输入",
    "Win+PrtScn": "截屏到图片",
    "Win+Ctrl+D": "新建虚拟桌面",
    "Win+Ctrl+F4": "关闭虚拟桌面",
    "Win+Ctrl+Left": "切换到左侧虚拟桌面",
    "Win+Ctrl+Right": "切换到右侧虚拟桌面",
    "Win+1": "打开任务栏第1个应用",
    "Win+2": "打开任务栏第2个应用",
    "Win+3": "打开任务栏第3个应用",
    "Win+4": "打开任务栏第4个应用",
    "Win+5": "打开任务栏第5个应用",
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
    parts = [p.strip().lower().replace("<", "").replace(">", "") for p in hotkey_str.replace("+", " ").split()]

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
        elif part in ["win", "windows", "cmd", "meta", "super"]:
            modifiers.append("win")
        else:
            aliases = {
                "return": "enter",
                "escape": "esc",
                "del": "delete",
                "ins": "insert",
                "pgup": "pageup",
                "pgdn": "pagedown",
                "prtscr": "printscreen",
            }
            key = aliases.get(part, part)

    # 按固定顺序排列
    order = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}
    modifiers.sort(key=lambda x: order.get(x, 99))

    result = "+".join(modifiers)
    if key:
        result = result + "+" + key if result else key

    titled = []
    for part in result.split("+"):
        if len(part) > 1 and part.startswith("f") and part[1:].isdigit():
            titled.append(part.upper())
        elif part == "esc":
            titled.append("Esc")
        else:
            titled.append(part.title())
    return "+".join(titled)


# 新增：在模块加载时一次性计算出规范化后的哈希字典，将冲突判断优化至 O(1)
_NORMALIZED_SYSTEM_HOTKEYS = {normalize_hotkey(k): v for k, v in SYSTEM_HOTKEYS.items()}

_NORMALIZED_COMMON_CONFLICTS = {
    normalize_hotkey(k): v
    for k, v in {
        "Ctrl+S": "保存（常用）",
        "Ctrl+O": "打开（常用）",
        "Ctrl+N": "新建（常用）",
        "Ctrl+W": "关闭（常用）",
        "Ctrl+P": "打印（常用）",
        "Ctrl+F": "查找（常用）",
        "Ctrl+H": "替换（常用）",
        "Ctrl+Shift+P": "VS Code: 命令面板",
        "Ctrl+`": "终端切换",
        "Ctrl+Shift+N": "Chrome: 无痕模式",
        "Ctrl+Shift+T": "Chrome: 恢复标签",
        "Ctrl+Shift+B": "Chrome: 书签栏",
        "Ctrl+Shift+Delete": "清除浏览数据",
        "Ctrl+Shift+O": "Chrome: 书签管理器",
        "Ctrl+Alt+Left": "音乐播放器: 上一曲",
        "Ctrl+Alt+Right": "音乐播放器: 下一曲",
        "Ctrl+Alt+Space": "音乐播放器: 播放/暂停",
    }.items()
}


def check_conflict(hotkey_str: str) -> tuple:
    """
    检查快捷键是否与系统快捷键冲突

    Returns:
        (is_conflict: bool, conflict_desc: str)
    """
    if not hotkey_str or not hotkey_str.strip():
        return False, ""

    normalized = normalize_hotkey(hotkey_str)

    # 1. O(1) 查表：检查系统快捷键
    if normalized in _NORMALIZED_SYSTEM_HOTKEYS:
        return True, f"与系统快捷键冲突：{_NORMALIZED_SYSTEM_HOTKEYS[normalized]}"

    # 2. O(1) 查表：检查常见软件快捷键
    if normalized in _NORMALIZED_COMMON_CONFLICTS:
        return True, f"与常用快捷键冲突：{_NORMALIZED_COMMON_CONFLICTS[normalized]}"

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
    from hooks.key_map import key_to_vk

    return key_to_vk(key)
