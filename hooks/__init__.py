"""钩子模块"""

MouseHook = None
KeyboardHook = None

try:
    from .mouse_hook_dll import MouseHook
except Exception as e:
    import logging
    logging.warning(f"MouseHook 导入失败: {e}")

try:
    from .keyboard_hook_dll import KeyboardHook
except Exception as e:
    import logging
    logging.warning(f"KeyboardHook 导入失败: {e}")