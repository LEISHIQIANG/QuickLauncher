"""钩子模块"""

import logging


class _MouseHookUnavailable:
    """MouseHook DLL 加载失败时的占位类"""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "鼠标钩子不可用：DLL 加载失败，请检查 hooks_dll/hooks.dll 是否存在"
        )


class _KeyboardHookUnavailable:
    """KeyboardHook DLL 加载失败时的占位类"""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "键盘钩子不可用：DLL 加载失败，请检查 hooks_dll/hooks.dll 是否存在"
        )


MouseHook = _MouseHookUnavailable
KeyboardHook = _KeyboardHookUnavailable

try:
    from .mouse_hook_dll import MouseHook
except Exception as e:
    logging.warning(f"MouseHook 导入失败: {e}")

try:
    from .keyboard_hook_dll import KeyboardHook
except Exception as e:
    logging.warning(f"KeyboardHook 导入失败: {e}")

__all__ = ["MouseHook", "KeyboardHook"]
