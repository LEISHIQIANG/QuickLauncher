"""
数据模型定义
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from domain.models import DEFAULT_SPECIAL_APPS, ShortcutType  # Re-exported for backward compatibility

from .runtime_constants import (
    COMMAND_CHAIN_MAX_STEPS,
    DEFAULT_COMMAND_OUTPUT_MAX_CHARS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    normalize_chain_step_delay_ms,
    normalize_command_output_max_chars,
    normalize_command_timeout_seconds,
)
from .trigger_config import normalize_trigger_settings


def _normalize_binding_value(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return text


def _binding_value_items(value) -> list[str]:
    normalized = _normalize_binding_value(value)
    if isinstance(normalized, list):
        return normalized
    return [normalized] if normalized else []


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
    command_type: str = "cmd"
    show_window: bool = False
    command_variables_enabled: bool = False
    capture_output: bool = False
    command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS
    command_output_max_chars: int = DEFAULT_COMMAND_OUTPUT_MAX_CHARS
    command_panel_size: str = "medium"
    command_params: list[dict] = field(default_factory=list)
    command_env: dict = field(default_factory=dict)
    command_encoding: str = "auto"
    module_id: str = ""
    module_version: str = ""
    batch_launch_steps: list[dict] = field(default_factory=list)
    raw_mode: bool = False

    # 宏录制类型
    macro_events: list[dict] = field(default_factory=list)
    macro_speed: float = 1.0
    macro_hide_while_recording: bool = False

    # 触发模式
    trigger_mode: str = "immediate"

    # 图标
    icon_path: str = ""
    icon_data: str = ""
    alias: str = ""

    # 图标反转设置
    icon_invert_light: bool = False
    icon_invert_dark: bool = False
    icon_invert_with_theme: bool = False
    icon_invert_current: bool = False
    icon_invert_theme_when_set: str = ""

    # 以管理员身份运行
    run_as_admin: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "order": self.order,
            "enabled": self.enabled,
            "tags": self.tags,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "smart_order": self.smart_order,
            "target_path": self.target_path,
            "target_args": self.target_args,
            "working_dir": self.working_dir,
            "hotkey": self.hotkey,
            "hotkey_modifiers": self.hotkey_modifiers,
            "hotkey_key": self.hotkey_key,
            "hotkey_keys": list(self.hotkey_keys or []),
            "url": self.url,
            "preferred_browser_path": self.preferred_browser_path,
            "preferred_browser_args": self.preferred_browser_args,
            "command": self.command,
            "command_type": self.command_type,
            "trigger_mode": self.trigger_mode,
            "icon_path": self.icon_path,
            "icon_data": self.icon_data,
            "alias": self.alias,
            "icon_invert_light": self.icon_invert_light,
            "icon_invert_dark": self.icon_invert_dark,
            "icon_invert_with_theme": self.icon_invert_with_theme,
            "icon_invert_current": self.icon_invert_current,
            "icon_invert_theme_when_set": self.icon_invert_theme_when_set,
            "run_as_admin": self.run_as_admin,
            "show_window": self.show_window,
            "command_variables_enabled": self.command_variables_enabled,
            "capture_output": self.capture_output,
            "command_timeout_seconds": self.command_timeout_seconds,
            "command_output_max_chars": self.command_output_max_chars,
            "command_panel_size": self.command_panel_size,
            "command_params": list(self.command_params or []),
            "command_env": dict(self.command_env or {}),
            "command_encoding": self.command_encoding,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "batch_launch_steps": list(self.batch_launch_steps or []),
            "raw_mode": self.raw_mode,
            "macro_events": [dict(event) for event in (self.macro_events or []) if isinstance(event, dict)],
            "macro_speed": float(self.macro_speed) if self.macro_speed else 1.0,
            "macro_hide_while_recording": bool(self.macro_hide_while_recording),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ShortcutItem:
        item = cls()
        item.id = data.get("id", str(uuid.uuid4()))
        item.name = data.get("name", "")
        try:
            item.type = ShortcutType(data.get("type", "file"))
        except ValueError:
            item.type = ShortcutType.FILE
        item.order = data.get("order", 0)
        item.enabled = data.get("enabled", True)
        item.tags = cls._normalize_tags(data.get("tags", []))
        item.last_used_at = data.get("last_used_at", 0.0)
        item.use_count = data.get("use_count", 0)
        item.smart_order = data.get("smart_order", None)
        item.target_path = data.get("target_path", "")
        item.target_args = data.get("target_args", "")
        item.working_dir = data.get("working_dir", "")
        item.hotkey = data.get("hotkey", "")
        item.hotkey_modifiers = data.get("hotkey_modifiers", [])
        item.hotkey_key = data.get("hotkey_key", "")
        item.hotkey_keys = _binding_value_items(data.get("hotkey_keys", []))
        if not item.hotkey_keys and item.hotkey_key:
            item.hotkey_keys = [item.hotkey_key]
        if item.hotkey_keys:
            item.hotkey_key = item.hotkey_keys[0]
        item.url = data.get("url", "")
        item.preferred_browser_path = data.get("preferred_browser_path", "")
        item.preferred_browser_args = data.get("preferred_browser_args", "")
        item.command = data.get("command", "")
        item.command_type = data.get("command_type", "cmd")
        item.trigger_mode = data.get("trigger_mode", "immediate")
        item.icon_path = data.get("icon_path", "")
        item.icon_data = data.get("icon_data", "")
        item.alias = data.get("alias", "")
        item.icon_invert_light = data.get("icon_invert_light", False)
        item.icon_invert_dark = data.get("icon_invert_dark", False)
        item.icon_invert_with_theme = data.get("icon_invert_with_theme", False)
        item.icon_invert_current = data.get("icon_invert_current", False)
        item.icon_invert_theme_when_set = data.get("icon_invert_theme_when_set", "")
        # 旧版数据迁移：将旧字段转换为新的浅色/深色独立反转字段
        if item.icon_invert_with_theme and not (item.icon_invert_light or item.icon_invert_dark):
            set_theme = item.icon_invert_theme_when_set
            if item.icon_invert_current:
                # 旧逻辑"当前反转"：只在设置时的主题下反转
                if set_theme == "light":
                    item.icon_invert_light = True
                elif set_theme == "dark":
                    item.icon_invert_dark = True
            else:
                # 旧逻辑"随主题反转"：在相反主题下反转
                if set_theme == "light":
                    item.icon_invert_dark = True
                elif set_theme == "dark":
                    item.icon_invert_light = True
        item.run_as_admin = data.get("run_as_admin", False)
        item.show_window = data.get("show_window", False)
        item.command_variables_enabled = data.get("command_variables_enabled", False)
        item.capture_output = bool(data.get("capture_output", False))
        item.command_timeout_seconds = normalize_command_timeout_seconds(data.get("command_timeout_seconds"))
        item.command_output_max_chars = normalize_command_output_max_chars(data.get("command_output_max_chars"))
        cps = str(data.get("command_panel_size", "medium") or "medium").lower().strip()
        item.command_panel_size = cps if cps in ("small", "medium", "large") else "medium"
        item.command_params = cls._normalize_command_params(data.get("command_params", []))
        item.command_env = cls._normalize_command_env(data.get("command_env", {}))
        encoding = str(data.get("command_encoding", "auto") or "auto").lower().strip()
        item.command_encoding = encoding if encoding in ("auto", "utf-8", "gbk", "mbcs") else "auto"
        if item.type == ShortcutType.BATCH_LAUNCH:
            item.module_id = item.module_id or BATCH_LAUNCH_MODULE_ID
            item.module_version = item.module_version or BATCH_LAUNCH_MODULE_VERSION
        else:
            item.module_id = str(data.get("module_id") or "")
            item.module_version = str(data.get("module_version") or "")
        item.batch_launch_steps = cls._normalize_chain_steps(data.get("batch_launch_steps", []))
        item.raw_mode = bool(data.get("raw_mode", False))
        raw_events = data.get("macro_events", [])
        if isinstance(raw_events, list):
            item.macro_events = [dict(event) for event in raw_events if isinstance(event, dict)]
        else:
            item.macro_events = []
        try:
            item.macro_speed = float(data.get("macro_speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            item.macro_speed = 1.0
        if item.macro_speed <= 0:
            item.macro_speed = 1.0
        item.macro_hide_while_recording = bool(data.get("macro_hide_while_recording", False))
        return item

    @staticmethod
    def _normalize_tags(tags) -> list[str]:
        if not tags:
            return []
        if isinstance(tags, str):
            tags = [tags]
        result = []
        seen = set()
        for tag in tags:
            value = str(tag or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(value)
        return result

    MAX_CHAIN_STEPS = COMMAND_CHAIN_MAX_STEPS

    @staticmethod
    def _normalize_command_params(params) -> list[dict]:
        if not isinstance(params, list):
            return []
        valid_types = {"text", "choice", "bool", "file", "folder", "number", "password", "textarea"}
        valid_sources = {"", "clipboard", "selected_text", "selected_file", "selected_file_dir", "last"}
        valid_validators = {"", "path", "file", "folder", "url", "domain", "ip", "port", "json", "regex", "number"}
        normalized = []
        for param in params:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name") or "").strip()
            if not name:
                continue
            param_type = str(param.get("type") or "text").lower().strip()
            if param_type not in valid_types:
                param_type = "text"
            choices = param.get("choices", [])
            if isinstance(choices, str):
                delimiter = "|" if "|" in choices else ","
                choices = [part.strip() for part in choices.split(delimiter) if part.strip()]
            elif not isinstance(choices, list):
                choices = []
            source = str(param.get("source") or "").lower().strip()
            if source not in valid_sources:
                source = ""
            validator = str(param.get("validator") or "").lower().strip()
            if validator not in valid_validators:
                validator = ""
            sensitive = bool(param.get("sensitive", False) or param_type == "password")
            multiline = bool(param.get("multiline", False) or param_type == "textarea")
            remember = bool(param.get("remember", True))
            if sensitive:
                remember = False
            normalized.append(
                {
                    "name": name,
                    "type": param_type,
                    "required": bool(param.get("required", False)),
                    "default": str(param.get("default") or ""),
                    "choices": [str(choice) for choice in choices],
                    "sensitive": sensitive,
                    "label": str(param.get("label") or ""),
                    "placeholder": str(param.get("placeholder") or ""),
                    "help": str(param.get("help") or ""),
                    "multiline": multiline,
                    "remember": remember,
                    "source": source,
                    "validator": validator,
                    "pattern": str(param.get("pattern") or ""),
                    "min_value": str(param.get("min_value") or ""),
                    "max_value": str(param.get("max_value") or ""),
                    "advanced": bool(param.get("advanced", False)),
                }
            )
        return normalized

    @staticmethod
    def _normalize_command_env(env) -> dict:
        if isinstance(env, str):
            pairs = {}
            for line in env.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key:
                    pairs[key] = value.strip()
            return pairs
        if not isinstance(env, dict):
            return {}
        return {str(k).strip(): str(v) for k, v in env.items() if str(k).strip()}

    @staticmethod
    def _normalize_chain_steps(steps) -> list[dict]:
        if not isinstance(steps, list):
            return []
        if len(steps) > ShortcutItem.MAX_CHAIN_STEPS:
            steps = steps[: ShortcutItem.MAX_CHAIN_STEPS]
        normalized = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            shortcut_id = str(step.get("shortcut_id") or "").strip()
            if not shortcut_id:
                continue
            delay_ms = normalize_chain_step_delay_ms(step.get("delay_ms", 0))
            normalized.append(
                {
                    "id": str(step.get("id") or uuid.uuid4()),
                    "shortcut_id": shortcut_id,
                    "enabled": bool(step.get("enabled", True)),
                    "stop_on_error": bool(step.get("stop_on_error", True)),
                    "delay_ms": delay_ms,
                }
            )
        return normalized

    def mark_used(self, timestamp: float | None = None):
        try:
            self.last_used_at = float(timestamp if timestamp is not None else time.time())
        except (TypeError, ValueError):
            self.last_used_at = time.time()
        try:
            self.use_count = max(0, int(self.use_count)) + 1
        except (TypeError, ValueError):
            self.use_count = 1

    def is_enabled(self) -> bool:
        return bool(self.enabled)


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
    linked_path: str = ""
    auto_sync: bool = False
    last_sync_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "order": self.order,
            "is_system": self.is_system,
            "is_dock": self.is_dock,
            "is_icon_repo": self.is_icon_repo,
            "items": [item.to_dict() for item in self.items],
            "linked_path": self.linked_path,
            "auto_sync": self.auto_sync,
            "last_sync_time": self.last_sync_time,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Folder:
        folder = cls()
        folder.id = data.get("id", str(uuid.uuid4()))
        folder.name = data.get("name", "")
        folder.order = data.get("order", 0)
        folder.is_system = data.get("is_system", False)
        folder.is_dock = data.get("is_dock", False)
        folder.is_icon_repo = data.get("is_icon_repo", False)
        folder.items = [ShortcutItem.from_dict(item) for item in data.get("items", [])]
        folder.linked_path = data.get("linked_path", "")
        folder.auto_sync = data.get("auto_sync", False)
        folder.last_sync_time = data.get("last_sync_time", 0.0)
        return folder


# DEFAULT_SPECIAL_APPS re-exported from domain.models (line 5)


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

    # 任务栏触发设置
    popup_trigger_source: str = "mouse"  # "mouse"=普通鼠标/键盘触发, "taskbar"=任务栏双击触发
    popup_taskbar_trigger_ctrl: bool = False  # 任务栏触发是否需要按住 Ctrl
    # 特殊触发任务栏触发设置
    popup_special_trigger_source: str = "mouse"
    popup_special_taskbar_trigger_ctrl: bool = False

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

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "theme_follow_system": self.theme_follow_system,
            "bg_alpha": self.bg_alpha,
            "dock_bg_alpha": self.dock_bg_alpha,
            "icon_alpha": self.icon_alpha,
            "icon_size": self.icon_size,
            "cell_size": self.cell_size,
            "cols": self.cols,
            "corner_radius": self.corner_radius,
            "last_page_index": self.last_page_index,
            "close_after_launch": self.close_after_launch,
            "show_on_startup": self.show_on_startup,
            "auto_start": self.auto_start,
            "sort_mode": self.sort_mode,
            "hardware_acceleration": self.hardware_acceleration,
            "hide_tray_icon": self.hide_tray_icon,
            "enable_debug_log": self.enable_debug_log,
            "auto_update_enabled": self.auto_update_enabled,
            "disable_logging": self.disable_logging,
            "sleep_mode_enabled": self.sleep_mode_enabled,
            "sleep_timeout_seconds": self.sleep_timeout_seconds,
            "show_welcome_guide": self.show_welcome_guide,
            "first_run": self.first_run,
            "last_version": self.last_version,
            "dock_enabled": self.dock_enabled,
            "dock_height_mode": self.dock_height_mode,
            "popup_max_rows": self.popup_max_rows,
            "popup_align_mode": self.popup_align_mode,
            "popup_auto_close": self.popup_auto_close,
            "popup_multi_open_when_pinned": self.popup_multi_open_when_pinned,
            "hover_leave_delay": self.hover_leave_delay,
            "double_click_interval": self.double_click_interval,
            "search_default_active": self.search_default_active,
            "popup_trigger_mode": self.popup_trigger_mode,
            "popup_trigger_keys": self.popup_trigger_keys,
            "popup_trigger_button": self.popup_trigger_button,
            "popup_trigger_modifiers": self.popup_trigger_modifiers,
            "popup_special_trigger_mode": self.popup_special_trigger_mode,
            "popup_special_trigger_keys": self.popup_special_trigger_keys,
            "popup_special_trigger_button": self.popup_special_trigger_button,
            "popup_special_trigger_modifiers": self.popup_special_trigger_modifiers,
            "popup_trigger_source": self.popup_trigger_source,
            "popup_taskbar_trigger_ctrl": self.popup_taskbar_trigger_ctrl,
            "popup_special_trigger_source": self.popup_special_trigger_source,
            "popup_special_taskbar_trigger_ctrl": self.popup_special_taskbar_trigger_ctrl,
            "bg_mode": self.bg_mode,
            "bg_solid_color": self.bg_solid_color,
            "bg_blur_radius": self.bg_blur_radius,
            "theme_bg_alpha": self.theme_bg_alpha,
            "theme_blur_radius": self.theme_blur_radius,
            "theme_edge_opacity": self.theme_edge_opacity,
            "image_bg_alpha": self.image_bg_alpha,
            "image_blur_radius": self.image_blur_radius,
            "image_edge_opacity": self.image_edge_opacity,
            "acrylic_bg_alpha": self.acrylic_bg_alpha,
            "acrylic_blur_radius": self.acrylic_blur_radius,
            "acrylic_edge_opacity": self.acrylic_edge_opacity,
            "glass_bg_alpha": self.glass_bg_alpha,
            "glass_blur_radius": self.glass_blur_radius,
            "glass_edge_opacity": self.glass_edge_opacity,
            "shadow_size": self.shadow_size,
            "shadow_distance": self.shadow_distance,
            "edge_highlight_color": self.edge_highlight_color,
            "edge_highlight_opacity": self.edge_highlight_opacity,
            "custom_bg_path": self.custom_bg_path,
            "special_apps": self.special_apps,
            "enabled_plugins": self.enabled_plugins,
            "favorite_commands": self.favorite_commands,
            "disabled_builtin_commands": self.disabled_builtin_commands,
            "plugin_dev_mode": self.plugin_dev_mode,
            "enable_context_detection": self.enable_context_detection,
            "enable_plugins": self.enable_plugins,
            "language": self.language,
            "dark_black_point": self.dark_black_point,
            "dark_white_point": self.dark_white_point,
            "dark_mid_gamma": self.dark_mid_gamma,
            "dark_temperature": self.dark_temperature,
            "dark_acrylic": self.dark_acrylic,
            "dark_bg_alpha_filter": self.dark_bg_alpha_filter,
            "light_black_point": self.light_black_point,
            "light_white_point": self.light_white_point,
            "light_mid_gamma": self.light_mid_gamma,
            "light_temperature": self.light_temperature,
            "light_acrylic": self.light_acrylic,
            "light_bg_alpha_filter": self.light_bg_alpha_filter,
            "ui_scale_percent": self.ui_scale_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppSettings:
        settings = cls()
        for key, value in data.items():
            if hasattr(settings, key):
                if key == "bg_alpha" and value > 100:
                    value = int(value * 100 / 255)
                if key == "sort_mode" and value not in ("custom", "smart"):
                    value = "custom"
                setattr(settings, key, value)

        # 如果没有特殊应用设置，使用默认值
        if not settings.special_apps:
            settings.special_apps = DEFAULT_SPECIAL_APPS.copy()

        # 确保触发配置有默认值（向后兼容）
        if not hasattr(settings, "popup_trigger_button"):
            settings.popup_trigger_button = "middle"
        if not hasattr(settings, "popup_trigger_modifiers"):
            settings.popup_trigger_modifiers = []
        if not hasattr(settings, "popup_special_trigger_button"):
            settings.popup_special_trigger_button = "middle"
        if not hasattr(settings, "popup_special_trigger_modifiers"):
            settings.popup_special_trigger_modifiers = ["ctrl"]

        # 向后兼容：确保新触发模式字段有默认值
        if not hasattr(settings, "popup_trigger_mode"):
            settings.popup_trigger_mode = "mouse"
        if not hasattr(settings, "popup_trigger_keys"):
            settings.popup_trigger_keys = []
        if not hasattr(settings, "popup_special_trigger_mode"):
            settings.popup_special_trigger_mode = "mouse"
        if not hasattr(settings, "popup_special_trigger_keys"):
            settings.popup_special_trigger_keys = []

        # 任务栏触发设置迁移
        if not hasattr(settings, "popup_trigger_source"):
            settings.popup_trigger_source = "mouse"
        if not hasattr(settings, "popup_taskbar_trigger_ctrl"):
            settings.popup_taskbar_trigger_ctrl = False

        # 特殊触发任务栏触发设置迁移
        if not hasattr(settings, "popup_special_trigger_source"):
            settings.popup_special_trigger_source = "mouse"
        if not hasattr(settings, "popup_special_taskbar_trigger_ctrl"):
            settings.popup_special_taskbar_trigger_ctrl = False

        for key, value in normalize_trigger_settings(settings).items():
            setattr(settings, key, value)

        return settings


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

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "config_schema_version": int(self.config_schema_version),
            "settings": self.settings.to_dict(),
            "folders": [folder.to_dict() for folder in self.folders],
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppData:
        app_data = cls.__new__(cls)
        app_data.version = data.get("version", "1.0")
        app_data.config_schema_version = int(data.get("config_schema_version", 0))
        app_data.settings = AppSettings.from_dict(data.get("settings", {}))
        app_data.folders = [Folder.from_dict(f) for f in data.get("folders", [])]
        if not app_data.folders:
            app_data._create_default_folders()
        return app_data


# ── Core ↔ Domain 边界类型收窄 ──────────────────────────────────────
#
# core/data_models.py 与 domain/models.py 中的 ShortcutItem / Folder /
# AppSettings / AppData 具有完全相同的字段定义（domain 是纯模型，core 是
# DTO + 序列化）。为避免字段重复继承带来的 mypy 类型错误，此处通过显式
# 类型收窄函数建立边界契约，而不改写模型的继承结构。
#
# 未来方向：当 mypy / dataclass 继承支持足够稳定时，可考虑将 core 的 DTO
# 改为组合模式（持有 domain 模型作为内字段），或改为 Protocol 约束。


def _is_shortcut_item(obj: object) -> bool:
    """Return True if *obj* has the structural shape of a ShortcutItem.

    Structural check — works for both ``core.data_models.ShortcutItem``
    and ``domain.models.ShortcutItem`` since they have identical fields.
    """
    return hasattr(obj, "id") and hasattr(obj, "type") and hasattr(obj, "name")


def _is_folder(obj: object) -> bool:
    """Return True if *obj* has the structural shape of a Folder."""
    return hasattr(obj, "id") and hasattr(obj, "items") and hasattr(obj, "name")


# Type aliases kept private to avoid polluting the public API of this module.
# External code should import from ``domain.models`` for the pure model and
# from ``core.data_models`` for the DTO/serializable version.  The structural
# guards above allow cross-boundary code to narrow from ``object`` without
# importing the domain package directly from core.
