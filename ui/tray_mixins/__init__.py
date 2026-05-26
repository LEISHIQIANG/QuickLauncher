"""
TrayApp mixin 拆分模块。

每个 mixin 不定义 __init__，只定义操作 self.* 属性的方法。
主类 TrayApp.__init__ 负责初始化所有属性。
"""

from ui.tray_mixins.hooks_mixin import HooksMixin
from ui.tray_mixins.popup_mixin import PopupMixin
from ui.tray_mixins.sleep_mixin import SleepMixin
from ui.tray_mixins.startup_mixin import StartupMixin
from ui.tray_mixins.update_mixin import UpdateMixin
from ui.tray_mixins.windows_mixin import WindowsMixin

__all__ = [
    "UpdateMixin",
    "HooksMixin",
    "SleepMixin",
    "PopupMixin",
    "StartupMixin",
    "WindowsMixin",
]
