"""Application localization helpers.

The app stores Chinese source strings in code and translates them at runtime
when the active language is switched to English. Default language is Chinese.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

DEFAULT_LANGUAGE = "zh_CN"
SUPPORTED_LANGUAGES = ("zh_CN", "en_US")

_current_language = DEFAULT_LANGUAGE


_EN_US: dict[str, str] = {
    "是": "Yes",
    "否": "No",
    "确定": "OK",
    "取消": "Cancel",
    "正在处理...": "Processing...",
    "设置": "Settings",
    "检查更新": "Check for Updates",
    "启动失败": "Startup Failed",
    "程序启动失败\n\n{error}\n\n详情请查看日志:\n{log_file}": (
        "The application failed to start.\n\n{error}\n\nSee the log for details:\n{log_file}"
    ),
    "QuickLauncher\n左键=设置 | 中键=启动器": "QuickLauncher\nLeft click = Settings | Middle click = Launcher",
    "错误": "Error",
    "无法打开设置窗口:\n{error}": "Unable to open the settings window:\n{error}",
    "重启失败": "Restart Failed",
    "无法重新启动程序\n\n{error}": "Unable to restart the application.\n\n{error}",
    "图标缓存正在清理中": "Icon cache cleanup is already running",
    "正在清理图标缓存...": "Cleaning icon cache...",
    "图标缓存清理失败，请查看日志": "Icon cache cleanup failed. Check the log.",
    "图标缓存已清理：{removed} 个文件，释放 {freed:.1f} MB": (
        "Icon cache cleaned: {removed} files removed, {freed:.1f} MB freed"
    ),
    "全局钩子已重装": "Global hooks reinstalled",
    "发现更新": "Update Available",
    "暂无更新说明。": "No release notes.",
    "\n\n这是强制更新，不能跳过。": "\n\nThis is a mandatory update and cannot be skipped.",
    "新版本 {version} 可用\n\n{changelog}\n\n文件大小: {size_mb:.1f} MB{mandatory_text}": (
        "Version {version} is available.\n\n{changelog}\n\nFile size: {size_mb:.1f} MB{mandatory_text}"
    ),
    "{message}\n\n是否立即下载更新？": "{message}\n\nDownload the update now?",
    "正在下载更新... {done:.1f}/{total:.1f} MB ({pct:.0f}%)": (
        "Downloading update... {done:.1f}/{total:.1f} MB ({pct:.0f}%)"
    ),
    "更新失败": "Update Failed",
    "更新失败:\n{error}": "Update failed:\n{error}",
    "下载完成": "Download Complete",
    "新版本已下载完成，是否立即安装并重启？": (
        "The new version has been downloaded. Install and restart now?"
    ),
    "当前已经是最新版本。": "You are already using the latest version.",
    "检查更新失败": "Update Check Failed",
    "无法检查更新:\n{error}": "Unable to check for updates:\n{error}",
    "启动与运行": "Startup and Runtime",
    "开机自动启动": "Start with Windows",
    "启动时显示设置窗口": "Show settings window on startup",
    "启用硬件加速 (性能优先)": "Enable hardware acceleration (performance first)",
    "开启后将提高进程优先级并优化资源调度，可能会增加系统资源占用": (
        "Raises process priority and optimizes scheduling. May increase resource usage."
    ),
    "隐藏托盘图标": "Hide tray icon",
    "隐藏后可通过内置命令'配置窗口'唤出设置面板": (
        "After hiding it, use the built-in command 'Configuration Window' to open settings."
    ),
    "10秒无操作后轻睡眠": "Light sleep after 10 seconds idle",
    "无操作一段时间后进入低占用状态，下一次中键立即唤醒": (
        "Reduces resource usage after idle time. Middle click wakes it immediately."
    ),
    "关闭日志": "Disable logging",
    "停止记录日志到error.log，减少硬盘写入（配置信息仍会保存）": (
        "Stops writing to error.log to reduce disk writes. Settings are still saved."
    ),
    "开启DEBUG日志": "Enable DEBUG logging",
    "开启后将记录详细的调试信息，用于问题排查": (
        "Records detailed debug information for troubleshooting."
    ),
    "自动更新": "Auto update",
    "开启后仅在每次启动软件时检查一次新版本，其他时间不自动检查": (
        "Checks for a new version once when the app starts."
    ),
    "排序方式": "Sort Mode",
    "自定义排序": "Custom sort",
    "智能排序": "Smart sort",
    "按你拖拽调整的顺序显示，不会删除智能排序结果": (
        "Uses your drag-and-drop order. Smart sort data is kept."
    ),
    "按使用次数和最近使用时间显示，保留自定义排序可随时切回": (
        "Sorts by usage count and recent use. Custom order remains available."
    ),
    "主题风格": "Theme",
    "跟随系统": "Follow system",
    "深色模式": "Dark mode",
    "浅色模式": "Light mode",
    "日志修复": "Logs and Repair",
    "运行日志": "Runtime Log",
    "查看 error.log，排查最近运行异常": "View error.log to inspect recent runtime errors",
    "诊断中心": "Diagnostics",
    "查看钩子、热键、配置、权限和最近错误状态": (
        "View hook, hotkey, config, permission, and recent error status"
    ),
    "图标检查": "Icon Check",
    "扫描缺失图标、失效路径、重复项和命令风险": (
        "Scan missing icons, invalid paths, duplicates, and command risks"
    ),
    "配置历史": "Config History",
    "查看最近 20 次配置快照，并可恢复到历史版本": (
        "View the latest 20 config snapshots and restore older versions"
    ),
    "打开失败": "Open Failed",
    "无法打开工具窗口:\n{error}": "Unable to open the tool window:\n{error}",
    "弹窗背景": "Popup Background",
    "跟随主题": "Follow theme",
    "图片背景": "Image background",
    "亚克力背景": "Acrylic background",
    "选择背景图片...": "Choose background image...",
    "浏览...": "Browse...",
    "尺寸布局": "Size and Layout",
    "图标大小": "Icon size",
    "格子大小": "Cell size",
    "每行列数": "Columns",
    "窗口圆角": "Corner radius",
    "Dock高度": "Dock height",
    "每列行数": "Rows per column",
    "隐藏": "Hidden",
    "透明度": "Opacity",
    "背景不透明度": "Background opacity",
    "图标不透明度": "Icon opacity",
    "Dock不透明度": "Dock opacity",
    "视觉特效": "Visual Effects",
    "模糊度": "Blur",
    "边缘高光": "Edge highlight",
    "列": " columns",
    "行": " rows",
    "弹窗位置": "Popup Position",
    "鼠标-弹窗中心": "Mouse to popup center",
    "鼠标-弹窗左上角": "Mouse to popup top-left",
    "自动关闭": "Auto close",
    "鼠标移出窗口后延迟自动关闭": "Close automatically after the mouse leaves the window",
    "需要点击窗口内图标或窗口外其他地方才会关闭": (
        "Only closes after clicking an icon or somewhere outside the window"
    ),
    "固定时多开": "Multi-open when pinned",
    "窗口固定时，再次中键保留当前窗口并新开一个弹窗": (
        "When pinned, middle click keeps the current popup and opens another"
    ),
    "窗口固定时，再次中键仍隐藏当前弹窗": (
        "When pinned, middle click still hides the current popup"
    ),
    "消失延迟": "Close delay",
    "双击间隔": "Double-click interval",
    "特殊触发 (Ctrl+中键)": "Special Triggers (Ctrl + Middle Click)",
    "新建": "New",
    "删除": "Delete",
    "重置默认": "Reset Defaults",
    "应用更改": "Apply Changes",
    "配置管理": "Config Management",
    "导出配置": "Export Config",
    "导入配置": "Import Config",
    "导出分享配置": "Export Shareable Config",
    "导入分享配置": "Import Shareable Config",
    "仅导出快捷键、打开网址、运行命令三种类型": (
        "Only exports hotkeys, URLs, and command shortcuts"
    ),
    "导入后会自动创建「导入图标」分类": (
        "Creates an 'Imported Icons' category after import"
    ),
    "危险操作": "Danger Zone",
    "以下操作不可逆，请谨慎使用": "The following actions cannot be undone. Use with caution.",
    "清除所有配置": "Clear All Config",
    "清除所有配置、图标缓存、快速搜索列表、右键扩展注册表项，并重启应用": (
        "Clears all config, icon cache, quick search list, context menu registry entries, and restarts the app"
    ),
    "系统设置": "System",
    "弹窗外观": "Appearance",
    "弹窗行为": "Popup",
    "弹窗交互": "Interaction",
    "数据管理": "Data",
    "插件管理": "Plugins",
    "命令管理": "Commands",
    "关于软件": "About",
    "支持作者": "Support",
    "支持一下": "Support",
    "当前: {folder} {count}项  共计: {total} 项": " Current: {folder} {count} items  Total: {total} items",
    "确认删除": "Confirm Delete",
    "确定要删除 '{name}' 吗?": "Delete '{name}'?",
    "收藏命令": "Favorite Commands",
    "收藏的命令会显示在 / 默认页顶部，方便快速访问。\n可以使用下方“内置命令管理”中的“收藏”按钮或从结果卡片的星标按钮添加。": (
        "Favorite commands appear at the top of the default / page for quick access.\n"
        "Use the Favorite button in Built-in Command Management below, or add one from a result card's star button."
    ),
    "暂未收藏任何命令": "No favorite commands yet",
    "内置命令管理": "Built-in Command Management",
    "可在下方直接启用或禁用特定的系统内置命令，以优化匹配列表。": (
        "Enable or disable specific built-in system commands below to optimize matching results."
    ),
    "搜索内置命令 (支持名称、快捷键、描述)...": (
        "Search built-in commands (name, shortcut, description)..."
    ),
    "取消收藏": "Unfavorite",
    "收藏": "Favorite",
    "启用": "Enable",
    "禁用": "Disable",
    "无法读取注册表命令": "Unable to read registered commands",
    "操作失败": "Action Failed",
    "取消收藏失败:\n{error}": "Failed to unfavorite:\n{error}",
    "保存命令状态失败:\n{error}": "Failed to save command state:\n{error}",
    "收藏失败:\n{error}": "Failed to favorite:\n{error}",
    "重新排序失败:\n{error}": "Failed to reorder:\n{error}",
    "刷新": "Refresh",
    "关闭": "Close",
    "清除": "Clear",
    "选择图标...": "Choose Icon...",
    "随主题反转": "Invert with theme",
    "当前反转": "Invert now",
    "基本信息": "Basic Info",
    "图标": "Icon",
    "启动参数": "Launch Arguments",
    "以管理员身份运行": "Run as administrator",
    "编辑快捷方式": "Edit Shortcut",
    "添加快捷方式": "Add Shortcut",
    "编辑快捷键": "Edit Hotkey",
    "添加快捷键": "Add Hotkey",
    "快捷键": "Hotkey",
    "区分左右修饰键": "Distinguish left/right modifiers",
    "触发模式": "Trigger Mode",
    "测试发送": "Test Send",
    "发送中...": "Sending...",
    "未检测到明显冲突": "No obvious conflict detected",
    "快捷键冲突": "Hotkey Conflict",
    "{conflict}\n\n是否仍要使用此快捷键？": "{conflict}\n\nUse this hotkey anyway?",
    "编辑打开网址": "Edit URL",
    "添加打开网址": "Add URL",
    "测试延迟": "Test Latency",
    "未测试": "Not tested",
    "浏览器": "Browser",
    "自动获取": "Auto Fetch",
    "获取中...": "Fetching...",
    "未获取到": "Not Found",
    "编辑运行命令": "Edit Command",
    "添加运行命令": "Add Command",
    "命令内容": "Command Content",
    "输入命令内容:": "Command content:",
    "插入": "Insert",
    "测试": "Test",
    "显示执行窗口": "Show execution window",
    "高级选项": "Advanced Options",
    "兼容旧 Python": "Legacy Python compatibility",
    "解析变量": "Expand variables",
    "输入要执行的CMD命令（静默运行，不显示窗口）:": "Enter the CMD command to run silently:",
    "输入要执行的Python代码（提供 os, sys, subprocess 等上下文）:": (
        "Enter Python code to run (os, sys, subprocess are available):"
    ),
    "选择内置命令:": "Choose a built-in command:",
    "校验失败": "Validation Failed",
    "请输入命令名称！": "Enter a command name.",
    "请输入命令内容！": "Enter command content.",
    "快捷方式": "Shortcut",
    "打开网址": "Open URL",
    "运行命令": "Run Command",
    "拖拽文件到此处添加\n或点击下方按钮新建\n\n拖拽图标可调整顺序": (
        "Drop files here to add them\nor use the buttons below\n\nDrag icons to reorder"
    ),
    "未命名": "Unnamed",
    "内置图标": "Built-in Icons",
    "导入文件夹": "Import Folder",
    "启用自动同步": "Enable auto sync",
    "恢复选中快照": "Restore Selected Snapshot",
    "恢复完成": "Restore Complete",
    "历史快照已恢复，请重启或刷新窗口查看。": (
        "The snapshot has been restored. Restart or refresh the window to view it."
    ),
    "恢复失败": "Restore Failed",
    "无法恢复该历史快照。": "Unable to restore this snapshot.",
    "复制摘要": "Copy Summary",
    "导出诊断包": "Export Diagnostics Package",
    "导出完成": "Export Complete",
    "诊断包已导出:\n{path}": "Diagnostics package exported:\n{path}",
    "导出失败": "Export Failed",
    "无法导出诊断包，请查看运行日志。": "Unable to export diagnostics package. Check the runtime log.",
    "清空日志": "Clear Log",
    "无法清空日志: {error}": "Unable to clear log: {error}",
    "重新扫描": "Rescan",
    "复制报告": "Copy Report",
    "应用修复": "Apply Fixes",
    "清理缓存": "Clean Cache",
    "清理中...": "Cleaning...",
    "清理失败": "Cleanup Failed",
    "无法清理未使用图标缓存:\n{error}": "Unable to clean unused icon cache:\n{error}",
    "复制全部": "Copy All",
    "欢迎使用 QuickLauncher": "Welcome to QuickLauncher",
    "不再显示": "Don't show again",
    "跳过": "Skip",
    "上一步": "Back",
    "下一步": "Next",
    "开始使用": "Get Started",
    "最多6个字符": "Up to 6 characters",
    "程序或文件路径": "Program or file path",
    "可选，启动参数": "Optional, launch arguments",
    "可选，工作目录": "Optional, working directory",
    "留空则使用默认图标": "Leave empty for default icon",
    "留空使用系统默认浏览器": "Leave empty for system default browser",
    "可选，自定义图标路径": "Optional, custom icon path",
    "可选，例如 --profile-directory=Default {url}": "Optional, e.g. --profile-directory=Default {url}",
    "例如: https://www.google.com/search?q={input}": "e.g. https://www.google.com/search?q={input}",
    "点击后直接按下快捷键": "Click here then press a shortcut",
    "点击后马上运行": "Run immediately",
    "马上发送按键": "Send keys immediately",
    "先关闭面板，再发送按键": "Close panel first, then send keys",
    "先关闭面板，再运行": "Close panel first, then run",
    "清空": "Clear",
    "未找到可选图标": "No selectable icon found",
    "正在读取图标...": "Loading icons...",
    "正在清理数据...": "Cleaning data...",
    "运行结果会显示在这里": "Output will be displayed here",
    "检测开机自启状态失败，请查看日志。": "Failed to detect auto-start status. Check the log.",
    "＋ 新建分类": "+ New Category",
    "是否启用文件夹自动同步?\n(启用后,文件夹内容变化时会自动更新)": "Enable auto folder sync?\n(When enabled, folder changes will update automatically)",
    "复制列表": "Copy List",
    "没有找到任何插件": "No plugins found",
    "插件管理器未初始化": "Plugin manager not initialized",
    "新建开发插件...": "New Dev Plugin...",
    "安装插件 (.zip)...": "Install Plugin (.zip)...",
    "刷新插件列表": "Refresh Plugin List",
    "打开插件目录": "Open Plugin Directory",
    "打开目录": "Open Directory",
    "创建": "Create",
    "创建新的插件开发模板": "Create a new plugin development template",
    "插件ID (仅限小写字母、数字、下划线和减号):": "Plugin ID (lowercase letters, digits, underscores and hyphens only):",
    "插件显示名称:": "Plugin Display Name:",
    "插件描述 (可选):": "Plugin Description (optional):",
    "作者信息": "Author Info",
    "作者名称 (可选):": "Author Name (optional):",
    "例如: my_plugin": "e.g. my_plugin",
    "例如: 我的自定义插件": "e.g. My Custom Plugin",
    "例如: 开发者名字": "e.g. Developer Name",
    "例如: shutdown /s /t 0": "e.g. shutdown /s /t 0",
    "一句话描述插件功能...": "Describe the plugin in one sentence...",
    "重载": "Reload",
    "软件简介": "Software Introduction",
    "关于 QuickLauncher": "About QuickLauncher",
    "请开发者喝杯咖啡吧": "Buy the developer a coffee",
    "⛶ 放大查看": "⛶ Zoom In",
    "✕ 关闭二维码": "✕ Close QR Code",
    "⭐ 点个 Star 鼓励一下": "⭐ Give a Star to Encourage",
    "👇 点击上方任一饮品，获取赞助二维码 (也可点击咖啡杯互动哦)": "👇 Click a drink above to get a sponsorship QR code (click the coffee cup to interact)",
    "💬 反馈建议 / 进群交流": "💬 Feedback / Join Us",
    "🧩 运行模式: 兼容模式 (in-process, 未强隔离)": "🧩 Run Mode: Compatibility Mode (in-process, no strong isolation)",
}


_TRANSLATIONS = {"en_US": _EN_US}


def normalize_language(language: str | None) -> str:
    value = (language or DEFAULT_LANGUAGE).strip()
    value = value.replace("-", "_")
    if value.lower() in {"zh", "zh_cn", "zh_hans", "chinese"}:
        return "zh_CN"
    if value.lower() in {"en", "en_us", "english"}:
        return "en_US"
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(language: str | None) -> str:
    global _current_language
    _current_language = normalize_language(language)
    return _current_language


def get_language() -> str:
    return _current_language


def is_chinese() -> bool:
    return _current_language == "zh_CN"


def tr(text: str, **kwargs) -> str:
    translated = _TRANSLATIONS.get(_current_language, {}).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except Exception:
            return translated
    return translated


@contextmanager
def using_language(language: str | None) -> Iterator[None]:
    previous = get_language()
    set_language(language)
    try:
        yield
    finally:
        set_language(previous)
