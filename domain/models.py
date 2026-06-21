"""Pure domain models — @dataclass base classes, no DTO/compat logic."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Constants inlined to avoid circular import with core.*
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 300.0
_DEFAULT_COMMAND_OUTPUT_MAX_CHARS = 2000

DEFAULT_SPECIAL_APPS = [
    "acad",
    "autocad",
    "revit",
    "sketchup",
    "rhino",
    "rhino8",
    "blender",
    "maya",
    "3dsmax",
    "zbrush",
    "substance",
    "cinema4d",
    "houdini",
    "nuke",
    "aftereffects",
    "premiere",
    "fusion360",
    "solidworks",
    "catia",
    "inventor",
    "navisworks",
    # 国产CAD
    "gcad",
    "gstarcad",
    "zwcad",
    "caxa",
    "bricscad",
    # CAD看图软件
    "cadreader",
    "fastcad",
    "dwgviewr",
    "cadsee",
]


def normalize_command_timeout_seconds(value: float | None) -> float:
    return max(1.0, min(86400.0, float(value or _DEFAULT_COMMAND_TIMEOUT_SECONDS)))


def normalize_command_output_max_chars(value: int) -> int:
    return max(100, min(100000, int(value or _DEFAULT_COMMAND_OUTPUT_MAX_CHARS)))


def normalize_chain_step_delay_ms(value: float) -> float:
    return max(0.0, min(60000.0, float(value or 0)))


def normalize_trigger_settings(settings: Any) -> Any:
    return settings or {}


class ShortcutType(Enum):
    """快捷方式类型"""

    FILE = "file"
    FOLDER = "folder"
    URL = "url"
    HOTKEY = "hotkey"
    COMMAND = "command"
    CHAIN = "chain"
    BATCH_LAUNCH = "batch_launch"
    MACRO = "macro"


ACTION_CHAIN_MODULE_ID = "quicklauncher.action_chain"
ACTION_CHAIN_MODULE_VERSION = "0.1.0"
ACTION_CHAIN_SCHEMA_VERSION = 1
BATCH_LAUNCH_MODULE_ID = "quicklauncher.batch_launch"
BATCH_LAUNCH_MODULE_VERSION = "0.1.0"


@dataclass
class ShortcutItem:
    """快捷方式项"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: ShortcutType = ShortcutType.FILE
    order: int = 0
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    last_used_at: float = 0.0
    use_count: int = 0
    smart_order: int | None = None

    # 文件类型
    target_path: str = ""
    target_args: str = ""
    working_dir: str = ""

    # 快捷键类型
    hotkey: str = ""
    hotkey_modifiers: list[str] = field(default_factory=list)
    hotkey_key: str = ""
    hotkey_keys: list[str] = field(default_factory=list)

    # URL类型
    url: str = ""
    preferred_browser_path: str = ""
    preferred_browser_args: str = ""

    # 命令类型
    command: str = ""
    command_type: str = "cmd"  # cmd, powershell, python, bash, builtin
    show_window: bool = False
    command_variables_enabled: bool = False
    capture_output: bool = False
    command_timeout_seconds: float = _DEFAULT_COMMAND_TIMEOUT_SECONDS
    command_output_max_chars: int = _DEFAULT_COMMAND_OUTPUT_MAX_CHARS
    command_panel_size: str = "medium"  # small, medium, large
    command_params: list[dict] = field(default_factory=list)
    command_env: dict = field(default_factory=dict)
    command_encoding: str = "auto"
    chain_steps: list[dict] = field(default_factory=list)
    chain_canvas: dict = field(default_factory=dict)
    chain_result_window: str = "medium"  # none, small, medium, large
    module_id: str = ""
    module_version: str = ""
    chain_schema_version: int = ACTION_CHAIN_SCHEMA_VERSION
    chain_ref: str = ""
    chain_data: dict = field(default_factory=dict)
    batch_launch_steps: list[dict] = field(default_factory=list)
    raw_mode: bool = False  # 原始模式，跳过变量预处理

    # 宏录制类型
    macro_events: list[dict] = field(default_factory=list)
    macro_speed: float = 1.0
    macro_hide_while_recording: bool = False

    # 触发模式
    trigger_mode: str = "immediate"  # immediate (立即触发), after_close (窗口关闭后触发)

    # 图标
    icon_path: str = ""
    icon_data: str = ""
    alias: str = ""

    # 图标反转设置（按主题独立控制）
    icon_invert_light: bool = False
    icon_invert_dark: bool = False
    # 旧版兼容字段（迁移后不再使用）
    icon_invert_with_theme: bool = False
    icon_invert_current: bool = False
    icon_invert_theme_when_set: str = ""

    # 以管理员身份运行
    run_as_admin: bool = False


@dataclass
class Folder:
    """文件夹"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    order: int = 0
    is_system: bool = False
    is_dock: bool = False
    is_icon_repo: bool = False
    items: list[ShortcutItem] = field(default_factory=list)

    # 文件夹自动导入功能
    linked_path: str = ""  # 绑定的物理文件夹路径
    auto_sync: bool = False  # 是否启用自动同步
    last_sync_time: float = 0.0  # 最后同步时间戳


@dataclass
class AppSettings:
    """应用设置"""

    theme: str = "dark"
    theme_follow_system: bool = True  # 主题跟随系统
    bg_alpha: int = 90  # 0-100 范围
    dock_bg_alpha: int = 90  # Dock栏背景透明度 0-100 范围
    icon_alpha: float = 1.0
    icon_size: int = 24
    cell_size: int = 44
    cols: int = 5
    corner_radius: int = 10
    last_page_index: int = 0
    close_after_launch: bool = True
    show_on_startup: bool = True  # 新增：启动时是否显示设置窗口
    auto_start: bool = False  # 开机自启
    sort_mode: str = "custom"  # custom, smart
    hardware_acceleration: bool = False  # 硬件加速
    hide_tray_icon: bool = False  # 隐藏托盘图标
    enable_debug_log: bool = False  # 开启DEBUG日志
    auto_update_enabled: bool = False  # 启动时自动检查更新
    disable_logging: bool = False  # 关闭日志记录
    sleep_mode_enabled: bool = True  # 10秒无操作后轻睡眠
    sleep_timeout_seconds: int = 10
    show_welcome_guide: bool = True  # 显示欢迎引导
    first_run: bool = True  # 首次运行标记
    last_version: str = ""  # 上次运行的版本号

    # Dock设置
    dock_enabled: bool = True
    dock_height_mode: int = 1  # 0=隐藏(由 dock_enabled 控制), 1~8=Dock 行数
    popup_max_rows: int = 8  # 中键弹窗每列最大行数

    # 命令与插件设置
    enabled_plugins: list[str] = field(default_factory=list)
    favorite_commands: list[str] = field(default_factory=list)
    disabled_builtin_commands: list[str] = field(default_factory=list)
    plugin_dev_mode: bool = False

    # 预处理设置
    preprocessing_enabled: bool = True  # 启用命令预处理
    preprocessing_strict_mode: bool = False  # 严格模式（警告也阻止）
    preprocessing_audit_enabled: bool = True  # 启用审计日志
    preprocessing_rate_limiting_enabled: bool = True  # 启用速率限制
    security_block_dangerous_patterns: bool = True  # 阻止危险模式
    security_require_variable_quoting: bool = True  # 强制外部变量引用

    # 功能降级开关
    enable_context_detection: bool = True
    enable_plugins: bool = True
    language: str = "zh_CN"

    # 弹窗设置
    popup_align_mode: str = "mouse_center"  # mouse_center, mouse_top_left, screen_center, bottom_right
    hover_leave_delay: int = 200  # 消失延迟 (ms)
    popup_auto_close: bool = True  # 自动关闭弹窗（鼠标离开后自动关闭），False 则需要点击才关闭
    popup_multi_open_when_pinned: bool = False  # 固定时再次中键是否新开弹窗
    double_click_interval: int = 300  # 双击间隔 (ms)
    search_default_active: bool = False  # 是否默认显示搜索框而不是标题栏

    # 弹窗触发按键配置
    popup_trigger_mode: str = "mouse"  # 触发模式: keyboard, mouse, hybrid
    popup_trigger_keys: list[str] = field(default_factory=list)  # 键盘按键列表
    popup_trigger_button: str = "middle"  # 鼠标按键: left, right, middle, x1, x2
    popup_trigger_modifiers: list[str] = field(default_factory=list)  # 修饰键
    popup_special_trigger_mode: str = "mouse"  # 特殊触发模式
    popup_special_trigger_keys: list[str] = field(default_factory=list)  # 特殊键盘按键
    popup_special_trigger_button: str = "middle"  # 特殊鼠标按键
    popup_special_trigger_modifiers: list[str] = field(default_factory=lambda: ["ctrl"])  # 特殊修饰键

    # 弹窗背景与视觉
    bg_mode: str = "theme"  # theme, image, acrylic, glass
    bg_solid_color: str = "#2b2b2b"
    bg_blur_radius: int = 0  # 模糊半径 (Legacy / Current Effective)

    # 独立模式参数 (Separate parameters for each mode)
    theme_bg_alpha: int = 90
    theme_blur_radius: int = 0
    theme_edge_opacity: float = 0.0

    image_bg_alpha: int = 90
    image_blur_radius: int = 0
    image_edge_opacity: float = 0.0

    acrylic_bg_alpha: int = 90
    acrylic_blur_radius: int = 0
    acrylic_edge_opacity: float = 0.0

    glass_bg_alpha: int = 30
    glass_blur_radius: int = 20
    glass_edge_opacity: float = 0.9

    # 边缘与阴影效果
    shadow_size: int = 0  # 模糊大小 (阴影/发光大小)
    shadow_distance: int = 0  # 模糊距离 (阴影偏移)
    edge_highlight_color: str = "#ffffff"
    edge_highlight_opacity: float = 0.0  # Shared/Default, keeping for compatibility or fallback

    custom_bg_path: str = ""

    special_apps: list[str] = field(default_factory=lambda: DEFAULT_SPECIAL_APPS.copy())

    # 高级颜色滤镜参数 (仅 Win11)
    dark_black_point: int = 50
    dark_white_point: int = 50
    dark_mid_gamma: int = 50
    dark_temperature: int = 50
    dark_acrylic: int = 30
    dark_bg_alpha_filter: int = 100
    light_black_point: int = 50
    light_white_point: int = 50
    light_mid_gamma: int = 50
    light_temperature: int = 50
    light_acrylic: int = 30
    light_bg_alpha_filter: int = 100

    # UI 全局缩放百分比 (独立于 Windows/Qt DPI)
    ui_scale_percent: int = 100

    @property
    def bg_alpha_255(self) -> int:
        """将 0-100 的透明度转换为 0-255"""
        return int(self.bg_alpha * 255 / 100)

    @property
    def dock_bg_alpha_255(self) -> int:
        """将 0-100 的 Dock 透明度转换为 0-255"""
        return int(self.dock_bg_alpha * 255 / 100)


@dataclass
class AppData:
    """应用数据"""

    version: str = "2.5"
    config_schema_version: int = 1
    settings: AppSettings = field(default_factory=AppSettings)
    folders: list[Folder] = field(default_factory=list)

    def __post_init__(self):
        if not self.folders:
            self._create_default_folders()

    def _create_default_folders(self):
        dock = Folder(id="dock", name="Dock", order=0, is_system=True, is_dock=True)
        default = Folder(id="default", name="常用", order=1, is_system=True, is_dock=False)
        self.folders = [dock, default]

    def get_dock(self) -> Folder | None:
        for folder in self.folders:
            if folder.is_dock:
                return folder
        return None

    def get_pages(self) -> list[Folder]:
        return [f for f in self.folders if not f.is_dock]

    def get_folder_by_id(self, folder_id: str) -> Folder | None:
        for folder in self.folders:
            if folder.id == folder_id:
                return folder
        return None
