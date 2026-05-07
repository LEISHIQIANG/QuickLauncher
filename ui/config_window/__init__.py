"""
配置窗口模块

延迟导入：只在实际使用时才加载各子模块，
避免 `from ui.config_window import ConfigWindow` 时加载所有对话框造成 ~1s 的冷启动延迟。
"""


def __getattr__(name):
    """模块级 __getattr__，实现延迟导入"""
    _lazy_imports = {
        'ConfigWindow': ('.main_window', 'ConfigWindow'),
        'FolderPanel': ('.folder_panel', 'FolderPanel'),
        'IconGrid': ('.icon_grid', 'IconGrid'),
        'SettingsPanel': ('.settings_panel', 'SettingsPanel'),
        'ShortcutDialog': ('.shortcut_dialog', 'ShortcutDialog'),
        'HotkeyDialog': ('.hotkey_dialog', 'HotkeyDialog'),
        'UrlDialog': ('.url_dialog', 'UrlDialog'),
        'CommandDialog': ('.command_dialog', 'CommandDialog'),
        'BuiltinIconsDialog': ('.builtin_icons_dialog', 'BuiltinIconsDialog'),
        'apply_theme_to_dialog': ('.theme_helper', 'apply_theme_to_dialog'),
        'get_dialog_stylesheet': ('.theme_helper', 'get_dialog_stylesheet'),
    }

    if name in _lazy_imports:
        module_name, attr_name = _lazy_imports[name]
        import importlib
        module = importlib.import_module(module_name, __package__)
        value = getattr(module, attr_name)
        # 缓存到模块全局，下次直接访问不再触发 __getattr__
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'ConfigWindow',
    'FolderPanel',
    'IconGrid',
    'SettingsPanel',
    'ShortcutDialog',
    'HotkeyDialog',
    'UrlDialog',
    'CommandDialog',
    'BuiltinIconsDialog',
    'apply_theme_to_dialog',
    'get_dialog_stylesheet'
]