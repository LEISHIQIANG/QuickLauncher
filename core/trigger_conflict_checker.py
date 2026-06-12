"""触发按键冲突检测"""

from .hotkey_conflict_checker import check_conflict, normalize_hotkey
from .trigger_config import normalize_trigger_config, trigger_config_to_hotkey


def check_trigger_conflict(
    button: str = "",
    modifiers: list[str] = None,
    mode: str = "mouse",
    keys: list[str] = None,
    shortcuts: list | None = None,
) -> tuple[bool, str]:
    """
    检查触发按键配置是否有冲突

    Args:
        button: 鼠标按键
        modifiers: 修饰键列表
        mode: 触发模式 keyboard/mouse/hybrid
        keys: 键盘按键列表（keyboard/hybrid模式使用）

    Returns:
        (is_conflict: bool, conflict_desc: str)
    """
    config = normalize_trigger_config(mode, keys or [], button, modifiers or [])
    mode = config.mode
    keys = config.keys
    button = config.button
    modifiers = config.modifiers

    # keyboard 模式验证
    if mode == "keyboard":
        if not keys:
            return True, "键盘模式必须指定至少一个按键"

        # 必须有修饰键
        if not modifiers:
            return True, "键盘触发必须配合修饰键（Ctrl/Shift/Win）\n否则可能影响正常输入"

        # 检查系统热键冲突
        hotkey_str = trigger_config_to_hotkey(mode, keys, modifiers)
        is_conflict, msg = check_conflict(hotkey_str)
        if is_conflict:
            return True, f"键盘触发冲突：{msg}"
        duplicate = _find_shortcut_hotkey_duplicate(hotkey_str, shortcuts or [])
        if duplicate:
            return True, f"键盘触发与快捷方式「{duplicate}」的快捷键重复"

    # hybrid 模式验证
    elif mode == "hybrid":
        if not keys or not button:
            return True, "混合模式必须同时指定键盘按键和鼠标按键"

        # 检查鼠标按键部分
        if button in ("left", "right") and not modifiers:
            return True, f"「{_button_name(button)}」必须配合修饰键使用"

    # mouse 模式验证（原有逻辑）
    elif mode == "mouse":
        # 必须指定鼠标按键
        if not button:
            return True, "鼠标模式必须指定鼠标按键\n请录制或选择一个按键"

        # 左键/右键必须配合修饰键
        if button in ("left", "right") and not modifiers:
            return True, f"「{_button_name(button)}」必须配合修饰键使用（如 Ctrl、Shift）\n否则会影响正常点击操作"

    # 系统快捷键冲突警告（所有模式）
    if modifiers:
        mod_set = set(modifiers)
        if mod_set == {"alt"} and (button in ("left", "right", "middle") or keys):
            return True, "Alt 键组合可能与系统快捷键冲突\n建议使用 Ctrl 或 Shift"
        if "alt" in modifiers and "ctrl" not in modifiers and "shift" not in modifiers:
            return False, "提示：Alt 组合可能与系统快捷键冲突（如 Alt+Tab）"

    return False, ""


def _button_name(button: str) -> str:
    """按键显示名称"""
    mapping = {"left": "左键", "right": "右键", "middle": "中键", "x1": "侧键后", "x2": "侧键前"}
    return mapping.get(button, button)


def _find_shortcut_hotkey_duplicate(hotkey_str: str, shortcuts: list) -> str:
    target = normalize_hotkey(hotkey_str)
    if not target:
        return ""
    for shortcut in shortcuts:
        raw_hotkey = getattr(shortcut, "hotkey", "") or ""
        if not raw_hotkey:
            mods = getattr(shortcut, "hotkey_modifiers", []) or []
            key = getattr(shortcut, "hotkey_key", "") or ""
            raw_hotkey = "+".join([*mods, key]) if key else ""
        if raw_hotkey and normalize_hotkey(raw_hotkey) == target:
            return str(getattr(shortcut, "name", "") or getattr(shortcut, "id", "") or raw_hotkey)
    return ""
