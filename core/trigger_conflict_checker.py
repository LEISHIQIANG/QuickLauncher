"""触发按键冲突检测"""

from .hotkey_conflict_checker import check_conflict, normalize_hotkey
from .trigger_config import normalize_trigger_config, trigger_config_to_hotkey


def check_trigger_conflict(
    button: str = "",
    modifiers: list[str] = None,  # type: ignore[assignment]
    mode: str = "mouse",
    keys: list[str] = None,  # type: ignore[assignment]
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

        # 检查系统热键冲突
        hotkey_str = trigger_config_to_hotkey(mode, keys, modifiers)
        is_conflict, msg = check_conflict(hotkey_str)
        if is_conflict:
            return False, f"键盘触发会覆盖现有组合：{msg}"
        duplicate = _find_shortcut_hotkey_duplicate(hotkey_str, shortcuts or [])
        if duplicate:
            return False, f"键盘触发与快捷方式「{duplicate}」的快捷键重复"

    # hybrid 模式验证
    elif mode == "hybrid":
        if not keys or not button:
            return True, "混合模式必须同时指定键盘按键和鼠标按键"

    # mouse 模式验证（原有逻辑）
    elif mode == "mouse":
        # 必须指定鼠标按键
        if not button:
            return True, "鼠标模式必须指定鼠标按键\n请录制或选择一个按键"

        if button in ("left", "right") and not modifiers:
            return False, f"「{_button_name(button)}」会拦截正常点击并触发弹窗"

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
            keys = list(getattr(shortcut, "hotkey_keys", []) or [])
            if not keys:
                key = getattr(shortcut, "hotkey_key", "") or ""
                keys = [key] if key else []
            raw_hotkey = "+".join([*mods, *keys]) if keys else ""
        if raw_hotkey and normalize_hotkey(raw_hotkey) == target:
            return str(getattr(shortcut, "name", "") or getattr(shortcut, "id", "") or raw_hotkey)
    return ""
