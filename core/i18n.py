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
    "是": "Y",
    "否": "N",
    "确定": "OK",
    "取消": "X",
    "正在处理...": "Wait...",
    "设置": "Set",
    "就绪": "OK",
    "检查更新": "Update",
    "启动失败": "Fail",
    "程序启动失败\n\n{error}\n\n详情请查看日志:\n{log_file}": (
        "The application failed to start.\n\n{error}\n\nSee the log for details:\n{log_file}"
    ),
    "QuickLauncher\n左键=设置 | 中键=启动器": "QuickLauncher\nLeft click = Settings | Middle click = Launcher",
    "错误": "Err",
    "无法打开设置窗口:\n{error}": "Unable to open the settings window:\n{error}",
    "重启失败": "Reboot",
    "无法重新启动程序\n\n{error}": "Unable to restart the application.\n\n{error}",
    "图标缓存正在清理中": "Cache busy",
    "正在清理图标缓存...": "Cleaning icon cache...",
    "图标缓存清理失败，请查看日志": "Icon cache cleanup failed. Check the log.",
    "图标缓存已清理：{removed} 个文件，释放 {freed:.1f} MB": (
        "Icon cache cleaned: {removed} files removed, {freed:.1f} MB freed"
    ),
    "全局钩子已重装": "Hooks",
    "发现更新": "Update",
    "暂无更新说明。": "No notes",
    "\n\n这是强制更新，不能跳过。": "\n\nThis is a mandatory update and cannot be skipped.",
    "新版本 {version} 可用\n\n{changelog}\n\n文件大小: {size_mb:.1f} MB{mandatory_text}": (
        "Version {version} is available.\n\n{changelog}\n\nFile size: {size_mb:.1f} MB{mandatory_text}"
    ),
    "{message}\n\n是否立即下载更新？": "{message}\n\nDownload the update now?",
    "正在下载更新... {done:.1f}/{total:.1f} MB ({pct:.0f}%)": (
        "Downloading update... {done:.1f}/{total:.1f} MB ({pct:.0f}%)"
    ),
    "更新失败": "Fail",
    "更新失败:\n{error}": "Update failed:\n{error}",
    "下载完成": "Done",
    "新版本已下载完成，是否立即安装并重启？": ("The new version has been downloaded. Install and restart now?"),
    "当前已经是最新版本。": "Latest",
    "检查更新失败": "Fail",
    "无法检查更新:\n{error}": "Unable to check for updates:\n{error}",
    "启动与运行": "Start",
    "开机自动启动": "Auto",
    "启动时显示设置窗口": "On start",
    "启用硬件加速 (性能优先)": "Hardware",
    "开启后将提高进程优先级并优化资源调度，可能会增加系统资源占用": (
        "Raises process priority and optimizes scheduling. May increase resource usage."
    ),
    "隐藏托盘图标": "Tray",
    "隐藏后可通过内置命令'配置窗口'唤出设置面板": (
        "After hiding it, use the built-in command 'Configuration Window' to open settings."
    ),
    "10秒无操作后轻睡眠": "Light sleep",
    "无操作一段时间后进入低占用状态，下一次中键立即唤醒": (
        "Reduces resource usage after idle time. Middle click wakes it immediately."
    ),
    "关闭日志": "Log",
    "停止记录日志到error.log，减少硬盘写入（配置信息仍会保存）": (
        "Stops writing to error.log to reduce disk writes. Settings are still saved."
    ),
    "开启DEBUG日志": "Debug",
    "开启后将记录详细的调试信息，用于问题排查": ("Records detailed debug information for troubleshooting."),
    "自动更新": "Update",
    "开启后仅在每次启动软件时检查一次新版本，其他时间不自动检查": (
        "Checks for a new version once when the app starts."
    ),
    "排序方式": "Sort",
    "自定义排序": "Custom",
    "智能排序": "Smart",
    "按你拖拽调整的顺序显示，不会删除智能排序结果": ("Uses your drag-and-drop order. Smart sort data is kept."),
    "按使用次数和最近使用时间显示，保留自定义排序可随时切回": (
        "Sorts by usage count and recent use. Custom order remains available."
    ),
    "主题风格": "Mode",
    "跟随系统": "Sys",
    "深色模式": "Dark",
    "浅色模式": "Light",
    "语言": "Lang",
    "中文": "CN",
    "English": "English",
    "日志修复": "Tool",
    "运行日志": "Log",
    "查看 error.log，排查最近运行异常": "View error.log to inspect recent runtime errors",
    "诊断中心": "Diag",
    "查看钩子、热键、配置、权限和最近错误状态": ("View hook, hotkey, config, permission, and recent error status"),
    "图标检查": "Icons",
    "扫描缺失图标、失效路径、重复项和命令风险": ("Scan missing icons, invalid paths, duplicates, and command risks"),
    "配置历史": "Hist",
    "查看最近 20 次配置快照，并可恢复到历史版本": ("View the latest 20 config snapshots and restore older versions"),
    "打开失败": "Fail",
    "无法打开工具窗口:\n{error}": "Unable to open the tool window:\n{error}",
    "弹窗背景": "Bg",
    "跟随主题": "Mode",
    "图片背景": "Img",
    "亚克力背景": "Acryl",
    "选择背景图片...": "Image...",
    "浏览...": "View",
    "尺寸布局": "Size",
    "图标大小": "Icon",
    "格子大小": "Cell",
    "每行列数": "Cols",
    "窗口圆角": "Rad",
    "Dock高度": "Dock",
    "每列行数": "Rows",
    "隐藏": "Hide",
    "透明度": "Alpha",
    "背景不透明度": "Bg",
    "图标不透明度": "Icons",
    "Dock不透明度": "Dock",
    "视觉特效": "FX",
    "模糊度": "Blur",
    "边缘高光": "Edge",
    "列": "c",
    "行": "r",
    "弹窗位置": "Pos",
    "鼠标-弹窗中心": "Center",
    "鼠标-弹窗左上角": "Top-left",
    "自动关闭": "Auto",
    "鼠标移出窗口后延迟自动关闭": "Close automatically after the mouse leaves the window",
    "需要点击窗口内图标或窗口外其他地方才会关闭": (
        "Only closes after clicking an icon or somewhere outside the window"
    ),
    "固定时多开": "Multi",
    "窗口固定时，再次中键保留当前窗口并新开一个弹窗": (
        "When pinned, middle click keeps the current popup and opens another"
    ),
    "窗口固定时，再次中键仍隐藏当前弹窗": ("When pinned, middle click still hides the current popup"),
    "消失延迟": "Delay",
    "双击间隔": "Dbl",
    "特殊触发 (Ctrl+中键)": "Special trigger",
    "新建": "New",
    "删除": "Del",
    "重置默认": "Reset",
    "应用更改": "Apply",
    "配置管理": "Data",
    "导出配置": "Out",
    "导入配置": "In",
    "导出分享配置": "Share",
    "导入分享配置": "Share",
    "仅导出快捷键、打开网址、运行命令三种类型": ("Only exports hotkeys, URLs, and command shortcuts"),
    "导入后会自动创建「导入图标」分类": ("Creates an 'Imported Icons' category after import"),
    "危险操作": "Risk",
    "以下操作不可逆，请谨慎使用": "The following actions cannot be undone. Use with caution.",
    "清除所有配置": "Clr",
    "清除所有配置、图标缓存、快速搜索列表、右键扩展注册表项，并重启应用": (
        "Clears all config, icon cache, quick search list, context menu registry entries, and restarts the app"
    ),
    "系统设置": "Sys",
    "弹窗外观": "Look",
    "弹窗行为": "Pop",
    "弹窗交互": "Act",
    "数据管理": "Data",
    "插件管理": "Plug",
    "命令管理": "Cmd",
    "关于软件": "Info",
    "支持作者": "Help",
    "支持一下": "Help",
    "当前: {folder} {count}项  共计: {total} 项": " Current: {folder} {count} items  Total: {total} items",
    "确认删除": "Sure",
    "确定要删除 '{name}' 吗?": "Delete '{name}'?",
    "收藏命令": "Fav",
    "收藏的命令会显示在 / 默认页顶部，方便快速访问。\n可以使用下方“内置命令管理”中的“收藏”按钮或从结果卡片的星标按钮添加。": (
        "Favorite commands appear at the top of the default / page for quick access.\n"
        "Use the Favorite button in Built-in Command Management below, or add one from a result card's star button."
    ),
    "暂未收藏任何命令": "No favs",
    "内置命令管理": "Built",
    "可在下方直接启用或禁用特定的系统内置命令，以优化匹配列表。": (
        "Enable or disable specific built-in system commands below to optimize matching results."
    ),
    "搜索内置命令 (支持名称、快捷键、描述)...": "Search...",
    "取消收藏": "Unfav",
    "收藏": "Fav",
    "启用": "On",
    "禁用": "Off",
    "无法读取注册表命令": "Read fail",
    "操作失败": "Fail",
    "取消收藏失败:\n{error}": "Failed to unfavorite:\n{error}",
    "保存命令状态失败:\n{error}": "Failed to save command state:\n{error}",
    "收藏失败:\n{error}": "Failed to favorite:\n{error}",
    "重新排序失败:\n{error}": "Failed to reorder:\n{error}",
    "刷新": "Ref",
    "关闭": "X",
    "清除": "Clr",
    "选择图标...": "Icon...",
    "随主题反转": "Invert",
    "当前反转": "Inv",
    "基本信息": "Base",
    "图标": "Ic",
    "启动参数": "Args",
    "以管理员身份运行": "Admin",
    "编辑快捷方式": "EditSC",
    "添加快捷方式": "AddSC",
    "编辑快捷键": "EditKey",
    "添加快捷键": "AddKey",
    "快捷键": "Key",
    "区分左右修饰键": "L/R keys",
    "触发模式": "Trig",
    "测试发送": "Test",
    "发送中...": "Sending",
    "未检测到明显冲突": "OK",
    "快捷键冲突": "Warn",
    "{conflict}\n\n是否仍要使用此快捷键？": "{conflict}\n\nUse this hotkey anyway?",
    "编辑打开网址": "Edit URL",
    "添加打开网址": "Add URL",
    "测试延迟": "Ping",
    "未测试": "Unt",
    "浏览器": "Web",
    "选择浏览器": "Browser",
    "自动获取": "Auto",
    "获取中...": "Fetch...",
    "未获取到": "None",
    "编辑运行命令": "EditCmd",
    "添加运行命令": "AddCmd",
    "命令内容": "Cmd",
    "输入命令内容:": "Command:",
    "插入": "Ins",
    "测试": "Try",
    "显示执行窗口": "Window",
    "高级选项": "Adv",
    "解析变量": "Vars",
    "输入要执行的CMD命令（静默运行，不显示窗口）:": "Enter the CMD command to run silently:",
    "输入要执行的 Python 代码（通过系统 Python 运行）:": "Enter Python code to run with system Python:",
    "选择内置命令:": "Built-in:",
    "校验失败": "Bad",
    "请输入命令名称！": "Need name",
    "请输入命令内容！": "Need cmd",
    "快捷方式": "SC",
    "打开网址": "URL",
    "运行命令": "Cmd",
    "新建动作链": "Chain",
    "动作链": "Chain",
    "编辑动作链": "EditChain",
    "基本设置": "Basic",
    "动作链名称": "Chain name",
    "失败时停止后续步骤": "Stop on error",
    "步骤列表": "Steps",
    "执行结果": "Result",
    "测试运行": "Test",
    "禁用": "Off",
    "启用": "On",
    "共 {n} 个步骤": "{n} step(s)",
    "✓ 未发现明显风险": "No risks found",
    "暂无步骤。": "No steps yet.",
    "点击「添加」将已有快捷方式加入动作链。": "Click Add to add shortcuts.",
    "  步骤 {n}: 引用的快捷方式不存在": "  Step {n}: shortcut not found",
    "  步骤 {n}: 将以管理员权限运行": "  Step {n}: runs as admin",
    "  步骤 {n}: 快捷键操作，可能产生冲突": "  Step {n}: hotkey may conflict",
    "  步骤 {n}: 将执行命令": "  Step {n}: runs a command",
    "正在执行...": "Running...",
    "总耗时: {t:.2f}s": "Total: {t:.2f}s",
    "错误: {e}": "Error: {e}",
    "错误: 无法获取数据管理器": "Error: no data manager",
    "拖拽文件到此处添加\n或点击下方按钮新建\n\n拖拽图标可调整顺序": (
        "Drop files here to add them\nor use the buttons below\n\nDrag icons to reorder"
    ),
    "未命名": "None",
    "导入文件夹": "Import",
    "新建分类": "New",
    "＋ 新建分类": "+ New",
    "请输入分类名称:": "Category:",
    "重命名": "Name",
    "请输入新名称:": "Name:",
    "删除所选": "Del",
    "批量删除": "BDel",
    "批量移动": "Move",
    "撤销上次批量操作": "Undo",
    "确定要对 {count} 个快捷方式执行此操作吗？": "Apply this action to {count} shortcuts?",
    "确定要删除文件夹 '{name}' 吗?\n其中的快捷方式也会被删除。": (
        "Delete folder '{name}'?\nShortcuts in it will also be deleted."
    ),
    "将创建新分类: {folder_name}": "A new category will be created: {folder_name}",
    "是否启用文件夹自动同步?\n(启用后,文件夹内容变化时会自动更新)": (
        "Enable automatic folder sync?\nWhen enabled, changes in the folder will update automatically."
    ),
    "启用自动同步": "Sync",
    "恢复选中快照": "Back",
    "恢复完成": "Done",
    "历史快照已恢复，请重启或刷新窗口查看。": (
        "The snapshot has been restored. Restart or refresh the window to view it."
    ),
    "恢复失败": "Fail",
    "无法恢复该历史快照。": "Restore fail",
    "复制摘要": "Copy",
    "导出诊断包": "Export",
    "导出完成": "Out",
    "诊断包已导出:\n{path}": "Diagnostics package exported:\n{path}",
    "导出失败": "Fail",
    "无法导出诊断包，请查看运行日志。": "Unable to export diagnostics package. Check the runtime log.",
    "清空日志": "Clr",
    "无法清空日志: {error}": "Unable to clear log: {error}",
    "重新扫描": "Scan",
    "复制报告": "Copy",
    "应用修复": "Fix",
    "清理缓存": "Trim",
    "清理中...": "Clean...",
    "清理失败": "Fail",
    "无法清理未使用图标缓存:\n{error}": "Unable to clean unused icon cache:\n{error}",
    "复制全部": "Copy",
    "欢迎使用 QuickLauncher": "Welcome",
    "不再显示": "Hide",
    "跳过": "Go",
    "上一步": "Back",
    "下一步": "Next",
    "开始使用": "Go",
    "最多6个字符": "Max 6",
    "程序或文件路径": "Path",
    "可选，启动参数": "Arguments",
    "可选，工作目录": "Work dir",
    "选择工作目录": "Work dir",
    "选择目标": "Target",
    "留空则使用默认图标": "Def icon",
    "留空使用系统默认浏览器": "System browser",
    "可选，自定义图标路径": "Icon path",
    "可选，例如 --profile-directory=Default {{url}}": "Optional, e.g. --profile-directory=Default {{url}}",
    "例如: https://www.google.com/search?q={{input}}": "e.g. https://www.google.com/search?q={{input}}",
    "点击后直接按下快捷键": "Press key",
    "无延迟运行": "No delay",
    "无延迟发送": "Send without delay",
    "窗口淡出后发送": "Send after fade",
    "窗口淡出后运行": "After fade",
    "清空": "Clr",
    "未找到可选图标": "No icons",
    "正在读取图标...": "Load icons",
    "正在清理数据...": "Clean data",
    "运行结果会显示在这里": "Output",
    "检测开机自启状态失败，请查看日志。": "Failed to detect auto-start status. Check the log.",
    "＋ 新建分类": "+ New",
    "是否启用文件夹自动同步?\n(启用后,文件夹内容变化时会自动更新)": "Enable auto folder sync?\n(When enabled, folder changes will update automatically)",
    "复制列表": "Copy",
    "没有找到任何插件": "No plugin",
    "插件管理器未初始化": "No manager",
    "新建开发插件...": "New...",
    "安装插件 (.qlzip)...": "Install...",
    "刷新插件列表": "Refresh",
    "打开插件目录": "Folder",
    "打开目录": "Open",
    "创建": "New",
    "创建新的插件开发模板": "Template",
    "插件ID (仅限小写字母、数字、下划线和减号):": "Plugin ID:",
    "插件显示名称:": "Name:",
    "插件描述 (可选):": "Description:",
    "作者信息": "Author",
    "作者名称 (可选):": "Author:",
    "例如: my_plugin": "e.g. my_plugin",
    "例如: 我的自定义插件": "e.g. My Custom Plugin",
    "例如: 开发者名字": "e.g. Dev",
    "例如: shutdown /s /t 0": "e.g. shutdown /s /t 0",
    "一句话描述插件功能...": "Description...",
    "重载": "Load",
    "软件简介": "Intro",
    "关于 QuickLauncher": "About",
    "请开发者喝杯咖啡吧": "Coffee",
    "⛶ 放大查看": "⛶ View",
    "✕ 关闭二维码": "✕ QR",
    "⭐ 点个 Star 鼓励一下": "⭐ Star",
    "👇 点击上方任一饮品，获取赞助二维码 (也可点击咖啡杯互动哦)": "👇 Click a drink above to get a sponsorship QR code (click the coffee cup to interact)",
    "💬 反馈建议 / 进群交流": "💬 Feedback",
    "🧩 运行模式: 兼容模式 (in-process, 未强隔离)": "🧩 Run Mode: Compatibility Mode (in-process, no strong isolation)",
}

_EN_US.update(
    {
        "名称:": "Name:",
        "类型:": "Type:",
        "CMD 命令": "CMD",
        "Python 代码": "Py",
        "内置命令": "Built",
        "目标:": "Tgt:",
        "网址:": "URL:",
        "延迟:": "Lag:",
        "路径:": "Path:",
        "参数:": "Args:",
        "工作目录:": "Work:",
        "选择图标": "Icon",
        "可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)": "Executable Files (*.exe);;Shortcuts (*.lnk);;All Files (*.*)",
        "基本操作": "Basics",
        "添加与管理": "Add",
        "分类与同步": "Sync",
        "高级功能": "Adv",
        "配置管理": "Data",
        "使用技巧": "Tips",
        "呼出弹窗": "Pop",
        "隐藏弹窗": "Hide",
        "搜索和执行": "Search",
        "锁定与翻页": "PinPg",
        "拖拽添加（推荐）": "Drag add",
        "五类快捷入口": "Types",
        "批量管理与重定向": "Batch",
        "分类与 Dock 栏": "Cat/Dock",
        "物理文件夹同步": "Sync",
        "命令与网址变量": "Variables",
        "高级物理反馈": "Feedback",
        "完整环境备份": "Backup",
        "社交化分享配置": "Share",
        "按键防冲突机制": "Guard",
        "后台无感与托盘": "Tray",
        "关于 QuickLauncher": "About",
        "软件简介": "Intro",
        "作者信息": "Author",
        "QuickLauncher 是一款面向 Windows 桌面的极速启动与轻量自动化效率工具。": "QuickLauncher is a fast launcher and lightweight automation tool for Windows desktop.",
        "按下鼠标中键即可快速呼出启动面板，集中管理常用程序、文件夹、网址、命令和快捷键；": "Press the middle mouse button to open the launcher and manage apps, folders, URLs, commands, and hotkeys in one place;",
        "同时支持搜索、Dock、分类同步、拖拽投递、智能排序、配置备份和高度自定义外观。": "it also supports search, Dock, category sync, drag-and-drop delivery, smart sorting, config backup, and highly customizable appearance.",
        "Windows 极速快捷启动与轻量自动化效率工具": "Fast Windows launcher",
        "开发者: NAYTON": "Developer: NAYTON",
        "开源协议：MIT License": "License: MIT License",
        "感谢您的支持！": "Thanks!",
        "在任意位置按下鼠标中键，弹窗会按设置显示在鼠标附近": "Press the middle mouse button anywhere and the popup appears near the cursor based on your settings",
        "支持普通中键、特殊应用中的 Ctrl + 中键，以及全局热键 fallback": "Supports normal middle click, Ctrl + middle click in special apps, and a global hotkey fallback",
        "再次按下鼠标中键，或点击弹窗外部的任意区域": "Press the middle mouse button again, or click anywhere outside the popup",
        "按下 Esc 键，或在启动项目后自动隐藏（可在弹窗交互中开关）": "Press Esc, or auto-hide after launching an item (configurable in popup interaction)",
        "弹窗打开后直接输入关键字进行模糊匹配（支持名称、别名、标签）": "Type after opening the popup for fuzzy matching by name, alias, or tag",
        "支持快捷网页搜索：g (Google)、b (Baidu)、y (Yandex)、e (Bing)": "Supports quick web search: g (Google), b (Baidu), y (Yandex), e (Bing)",
        "斜杠命令模式：输入 / 快速执行系统动作，如 /config、/quit 等": "Slash command mode: type / to run system actions such as /config and /quit",
        "右键点击弹窗空白区或右上角图钉，弹窗将不会自动隐藏": "Right-click the popup blank area or top-right pin to keep it from auto-hiding",
        "支持鼠标滚轮滚动或左右方向键（←/→）进行流畅的分类翻页": "Use the mouse wheel or left/right arrow keys (←/→) to page through categories smoothly",
        "将程序、文件、文件夹或快捷方式直接拖入弹窗或设置窗口中": "Drag apps, files, folders, or shortcuts directly into the popup or settings window",
        "支持桌面、文件资源管理器、开始菜单拖拽，支持一键批量拖入": "Supports dragging from Desktop, File Explorer, and Start Menu, including batch drag-in",
        "<b>快捷方式</b>：配置启动参数、工作目录、以及管理员运行权限": "<b>Shortcuts</b>: configure launch arguments, working directory, and administrator privileges",
        "<b>网址与目录</b>：支持延迟测试，使用默认或指定浏览器及命令行参数": "<b>URLs and directories</b>: latency testing, default or specified browser, and command-line arguments",
        "<b>命令与快捷键</b>：运行 CMD、Python 脚本以及录制发送复杂组合键": "<b>Commands and hotkeys</b>: run CMD/Python scripts and record complex key combinations",
        "支持 Ctrl/Shift 多选图标进行批量删除、移动、启用与禁用（支持撤销）": "Use Ctrl/Shift multi-select to batch delete, move, enable, or disable icons, with undo support",
        "提供独立图标仓库，在图标路径失效时支持在目录中自动重定向": "Provides a standalone icon repository and can redirect automatically when icon paths become invalid",
        "左侧分类栏支持新建、重命名、上下拖拽重排与快速删除": "The left category bar supports create, rename, drag reorder, and quick delete",
        "提供专用常驻 Dock 分类，用于放置高频全局快捷入口": "Provides a dedicated persistent Dock category for high-frequency global shortcuts",
        "拖入本地文件夹即可自动生成动态分类，增量同步 Lnk 与 Exe 文件": "Drag in a local folder to create a dynamic category and incrementally sync Lnk and Exe files",
        "物理同步监听文件新增、删除与重命名，防止手动拖放引起的冲突": "Physical sync watches file create, delete, and rename events to prevent conflicts from manual dragging",
        "支持 {{clipboard}}、{{input}}、{{date}}、{{time}} 等丰富环境变量": "Supports variables such as {{clipboard}}, {{input}}, {{date}}, and {{time}}",
        "支持 {{selected_text}}，配合 :q 安全引用规则，实现选中即处理": "Supports {{selected_text}} with the :q safe quoting rule for processing selected text",
        "<b>文件投递</b>：支持将任意文件拖到快捷图标上，调用对应程序打开": "<b>File drop</b>: drag any file onto a shortcut icon to open it with the corresponding app",
        "<b>触控调节</b>：Ctrl/Shift + 鼠标滚轮精细微调弹窗背景与图标透明度": "<b>Fine controls</b>: Ctrl/Shift + mouse wheel adjusts popup background and icon opacity",
        "<b>轻睡眠模式</b>：双击 Alt 临时暂停热键弹窗，支持内存整理与睡眠保护": "<b>Light sleep mode</b>: double-tap Alt to temporarily pause the hotkey popup, with memory cleanup and sleep protection",
        "导出独立配置包，完美备份所有设置、分类、本地图标、背景等资源": "Export a standalone config package to back up settings, categories, local icons, backgrounds, and other resources",
        "适合在新机上瞬间恢复工作环境，或将配置轻松回滚到之前备份": "Useful for instantly restoring your workspace on a new machine or rolling back to a previous backup",
        "可单独导出网址或命令分类，自动隐藏本地敏感路径生成分享包": "Export URL or command categories separately, hiding local sensitive paths automatically",
        "导入分享配置时会自动建立隔离的「导入图标」分类，极度安全": "Importing shared config creates an isolated 'Imported Icons' category for safety",
        "自定义防冲突进程列表（如 CAD、3D 建模、大型游戏或设计软件）": "Customize conflict-protection processes such as CAD, 3D modeling tools, large games, or design software",
        "在此类全屏或特定应用中，必须使用 Ctrl + 中键呼出，完美防误触": "In these fullscreen or specific apps, use Ctrl + middle click to open the popup and avoid accidental triggers",
        "支持开机静默自启动，并可选择彻底隐藏托盘图标实现完全无感后台": "Supports silent startup at boot and optionally hiding the tray icon for an invisible background mode",
        "托盘菜单支持一键查看精细运行日志、快捷配置同步、重启或安全退出": "The tray menu provides quick access to detailed logs, config sync, restart, and safe exit",
        "支持一下": "Help",
        "请开发者喝杯咖啡吧": "Coffee",
        "QuickLauncher 是一款开源且免费的桌面效率工具，由开发者在业余时间独立开发维护。\n您的赞助将被全额用于产品的日常维护与服务器开销。非常感谢您的暖心支持！❤️": "QuickLauncher is an open-source, free desktop productivity tool independently developed and maintained in the developer's spare time.\nYour sponsorship will be used entirely for daily maintenance and server costs. Thank you for your kind support! ❤️",
        "👇 点击上方任一饮品，获取赞助二维码 (也可点击咖啡杯互动哦)": "👇 Click any drink above to show the sponsorship QR code (you can also click the coffee cup)",
        "⛶ 放大查看": "⛶ View",
        "✕ 关闭二维码": "✕ QR",
        "⭐ 点个 Star 鼓励一下": "⭐ Star",
        "💬 反馈建议 / 进群交流": "💬 Feedback",
        "纯净矿泉水": "Water",
        "香浓拿铁": "Latte",
        "沁心绿茶": "Tea",
        "芝芝莓莓": "Berry",
        "「感谢这瓶清爽的矿泉水！开发者喝完活力满满，瞬间充满干劲～ 💧🧊」": "Thanks for the refreshing mineral water! The developer is recharged and ready to build. 💧🧊",
        "「哇，是一杯拿铁咖啡！开发者大受鼓舞，今晚又要敲几百行代码了！🚀☕」": "A latte! The developer is encouraged and may write hundreds more lines tonight. 🚀☕",
        "「静心品茗，灵感如潮。感谢您的支持与厚爱，愿您每天工作顺心！🍃🍵」": "A calm cup of tea brings fresh ideas. Thank you for the support, and may your work go smoothly. 🍃🍵",
        "「超棒的芝芝莓莓！开发者开心到起飞，甜度直接拉满啦！🍓✨🌈」": "Cheese strawberry! The developer is delighted, with sweetness at full power. 🍓✨🌈",
        "「感谢您的支持！赞助金额: ¥{price:.2f} ❤️」": "Thank you for your support! Sponsorship amount: ¥{price:.2f} ❤️",
        "无法拉起全屏收款窗口": "Pay fail",
        "✕ 点击空白处关闭": "✕ Blank",
        "插件是扩展 QuickLauncher 功能的扩展模块。\n当前兼容模式：插件与主程序同权限运行，仅安装您信任的插件。\n插件声明权限为高风险提示，并非强权限隔离。\n插件目录: plugins/": "Plugins extend QuickLauncher with additional features.\nCurrent compatibility mode: plugins run with the same privileges as the main app. Only install plugins you trust.\nDeclared plugin permissions are high-risk warnings, not strong permission isolation.\nPlugin directory: plugins/",
    }
)


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
