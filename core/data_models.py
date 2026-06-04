"""
数据模型定义
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

from .runtime_constants import (
    COMMAND_CHAIN_MAX_STEPS,
    DEFAULT_COMMAND_OUTPUT_MAX_CHARS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    normalize_chain_step_delay_ms,
    normalize_command_output_max_chars,
    normalize_command_timeout_seconds,
)


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


class ShortcutType(Enum):
    """快捷方式类型"""

    FILE = "file"
    FOLDER = "folder"
    URL = "url"
    HOTKEY = "hotkey"
    COMMAND = "command"
    CHAIN = "chain"
    BATCH_LAUNCH = "batch_launch"


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
    command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS
    command_output_max_chars: int = DEFAULT_COMMAND_OUTPUT_MAX_CHARS
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

    # 触发模式
    trigger_mode: str = "immediate"  # immediate (立即触发), after_close (窗口关闭后触发)

    # 图标
    icon_path: str = ""
    icon_data: str = ""
    alias: str = ""

    # 图标反转设置
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
            "url": self.url,
            "preferred_browser_path": self.preferred_browser_path,
            "preferred_browser_args": self.preferred_browser_args,
            "command": self.command,
            "command_type": self.command_type,
            "trigger_mode": self.trigger_mode,
            "icon_path": self.icon_path,
            "icon_data": self.icon_data,
            "alias": self.alias,
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
            "chain_steps": list(self.chain_steps or []),
            "chain_canvas": dict(self.chain_canvas or {}),
            "chain_result_window": self.chain_result_window,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "chain_schema_version": self.chain_schema_version,
            "chain_ref": self.chain_ref,
            "chain_data": dict(self.chain_data or {}),
            "batch_launch_steps": list(self.batch_launch_steps or []),
            "raw_mode": self.raw_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShortcutItem":
        item = cls()
        item.id = data.get("id", str(uuid.uuid4()))
        item.name = data.get("name", "")
        try:
            item.type = ShortcutType(data.get("type", "file"))
        except ValueError:
            item.type = ShortcutType.FILE
        chain_data = data.get("chain_data", {})
        chain_data = dict(chain_data) if isinstance(chain_data, dict) else {}
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
        item.url = data.get("url", "")
        item.preferred_browser_path = data.get("preferred_browser_path", "")
        item.preferred_browser_args = data.get("preferred_browser_args", "")
        item.command = data.get("command", "")
        item.command_type = data.get("command_type", "cmd")
        item.trigger_mode = data.get("trigger_mode", "immediate")
        item.icon_path = data.get("icon_path", "")
        item.icon_data = data.get("icon_data", "")
        item.alias = data.get("alias", "")
        item.icon_invert_with_theme = data.get("icon_invert_with_theme", False)
        item.icon_invert_current = data.get("icon_invert_current", False)
        item.icon_invert_theme_when_set = data.get("icon_invert_theme_when_set", "")
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
        item.chain_steps = cls._normalize_chain_steps(data.get("chain_steps", []))
        item.chain_canvas = cls._normalize_chain_canvas(data.get("chain_canvas", {}), item.chain_steps)
        crw = str(data.get("chain_result_window", "medium") or "medium").lower()
        item.chain_result_window = crw if crw in ("none", "small", "medium", "large") else "medium"
        item.module_id = str(data.get("module_id") or "")
        item.module_version = str(data.get("module_version") or "")
        if item.type == ShortcutType.CHAIN:
            item.module_id = item.module_id or ACTION_CHAIN_MODULE_ID
            item.module_version = item.module_version or ACTION_CHAIN_MODULE_VERSION
        elif item.type == ShortcutType.BATCH_LAUNCH:
            item.module_id = item.module_id or BATCH_LAUNCH_MODULE_ID
            item.module_version = item.module_version or BATCH_LAUNCH_MODULE_VERSION
        try:
            schema_version = int(data.get("chain_schema_version", data.get("schema_version", ACTION_CHAIN_SCHEMA_VERSION)))
        except (TypeError, ValueError):
            schema_version = ACTION_CHAIN_SCHEMA_VERSION
        item.chain_schema_version = max(1, schema_version)
        item.chain_ref = str(data.get("chain_ref") or "")
        item.chain_data = chain_data
        item.batch_launch_steps = cls._normalize_chain_steps(data.get("batch_launch_steps", []))
        item.raw_mode = bool(data.get("raw_mode", False))
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
            node_type = str(step.get("node_type") or "shortcut").strip().lower()
            if node_type not in ("shortcut", "processor"):
                node_type = "shortcut"
            shortcut_id = str(step.get("shortcut_id") or "").strip()
            processor_id = str(step.get("processor_id") or "").strip()
            if node_type == "shortcut" and not shortcut_id:
                continue
            if node_type == "processor" and not processor_id:
                continue
            delay_ms = normalize_chain_step_delay_ms(step.get("delay_ms", 0))
            args = step.get("args", {})
            if not isinstance(args, dict):
                args = {}
            param_bindings = step.get("param_bindings", {})
            if not isinstance(param_bindings, dict):
                param_bindings = {}
            input_binding_raw = step.get("input_binding", "")
            input_binding = _normalize_binding_value(input_binding_raw)
            normalized_args = {str(k).strip(): str(v) for k, v in args.items() if str(k).strip()}
            normalized_bindings = {
                str(k).strip(): _normalize_binding_value(v)
                for k, v in param_bindings.items()
                if str(k).strip() and _normalize_binding_value(v)
            }
            normalized.append(
                {
                    "id": str(step.get("id") or uuid.uuid4()),
                    "node_type": node_type,
                    "shortcut_id": shortcut_id,
                    "processor_id": processor_id,
                    "source": str(step.get("source") or ""),
                    "enabled": bool(step.get("enabled", True)),
                    "stop_on_error": bool(step.get("stop_on_error", True)),
                    "delay_ms": delay_ms,
                    "use_previous_output": bool(step.get("use_previous_output", False)),
                    "input_binding": input_binding,
                    "param_bindings": normalized_bindings,
                    "args": normalized_args,
                }
            )
        return normalized

    @staticmethod
    def _normalize_chain_canvas(canvas, steps: list[dict] | None = None) -> dict:
        if not isinstance(canvas, dict) or not canvas.get("nodes"):
            return ShortcutItem._chain_canvas_from_steps(steps or [])
        nodes = []
        node_ids = set()
        for index, raw in enumerate(list(canvas.get("nodes") or [])):
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or uuid.uuid4())
            node_ids.add(node_id)
            node_type = str(raw.get("node_type") or "shortcut").strip().lower()
            if node_type not in ("shortcut", "processor"):
                node_type = "shortcut"
            try:
                x = float(raw.get("x", index * 240))
            except (TypeError, ValueError):
                x = float(index * 240)
            try:
                y = float(raw.get("y", 80))
            except (TypeError, ValueError):
                y = 80.0
            try:
                order = int(raw.get("order", index + 1))
            except (TypeError, ValueError):
                order = index + 1
            args = raw.get("args", {})
            if not isinstance(args, dict):
                args = {}
            source = str(raw.get("source") or "")
            nodes.append(
                {
                    "id": node_id,
                    "node_type": node_type,
                    "shortcut_id": str(raw.get("shortcut_id") or "").strip(),
                    "processor_id": str(raw.get("processor_id") or "").strip(),
                    "source": source,
                    "title": str(raw.get("title") or "").strip(),
                    "x": x,
                    "y": y,
                    "order": max(1, order),
                    "enabled": bool(raw.get("enabled", True)),
                    "stop_on_error": bool(raw.get("stop_on_error", True)),
                    "delay_ms": normalize_chain_step_delay_ms(raw.get("delay_ms", 0)),
                    "args": {str(k).strip(): str(v) for k, v in args.items() if str(k).strip()},
                }
            )
        connections = []
        for raw in list(canvas.get("connections") or []):
            if not isinstance(raw, dict):
                continue
            source_node = str(raw.get("source_node") or "").strip()
            target_node = str(raw.get("target_node") or "").strip()
            source_port = str(raw.get("source_port") or "").strip()
            target_port = str(raw.get("target_port") or "").strip()
            if source_node in node_ids and target_node in node_ids and source_port and target_port:
                connections.append(
                    {
                        "id": str(raw.get("id") or uuid.uuid4()),
                        "source_node": source_node,
                        "source_port": source_port,
                        "target_node": target_node,
                        "target_port": target_port,
                    }
                )
        return {"version": 1, "nodes": nodes, "connections": connections}

    @staticmethod
    def _chain_canvas_from_steps(steps: list[dict]) -> dict:
        normalized_steps = ShortcutItem._normalize_chain_steps(steps)
        nodes = []
        connections = []
        step_id_by_index: dict[int, str] = {}
        for index, step in enumerate(normalized_steps, start=1):
            node_id = str(step.get("id") or uuid.uuid4())
            step_id_by_index[index] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "node_type": str(step.get("node_type") or "shortcut"),
                    "shortcut_id": str(step.get("shortcut_id") or ""),
                    "processor_id": str(step.get("processor_id") or ""),
                    "source": str(step.get("source") or ""),
                    "title": "",
                    "x": float((index - 1) * 240),
                    "y": 80.0,
                    "order": index,
                    "enabled": bool(step.get("enabled", True)),
                    "stop_on_error": bool(step.get("stop_on_error", True)),
                    "delay_ms": normalize_chain_step_delay_ms(step.get("delay_ms", 0)),
                    "args": dict(step.get("args") or {}),
                }
            )
        for index, step in enumerate(normalized_steps, start=1):
            target_node = step_id_by_index.get(index)
            if not target_node:
                continue
            input_binding = step.get("input_binding", "")
            if input_binding:
                for binding in _binding_value_items(input_binding):
                    source = ShortcutItem._chain_binding_to_canvas_source(binding, index, step_id_by_index)
                    if source:
                        connections.append(
                            {
                                "id": str(uuid.uuid4()),
                                "source_node": source[0],
                                "source_port": source[1],
                                "target_node": target_node,
                                "target_port": "input",
                            }
                        )
            for target_port, binding in dict(step.get("param_bindings") or {}).items():
                for binding_item in _binding_value_items(binding):
                    source = ShortcutItem._chain_binding_to_canvas_source(str(binding_item), index, step_id_by_index)
                    if source:
                        connections.append(
                            {
                                "id": str(uuid.uuid4()),
                                "source_node": source[0],
                                "source_port": source[1],
                                "target_node": target_node,
                                "target_port": str(target_port),
                            }
                        )
        return {"version": 1, "nodes": nodes, "connections": connections}

    @staticmethod
    def _chain_binding_to_canvas_source(
        binding: str, current_index: int, step_id_by_index: dict[int, str]
    ) -> tuple[str, str] | None:
        binding = str(binding or "").strip()
        if not binding:
            return None
        if binding.startswith("prev."):
            source_index = current_index - 1
            port = binding[5:]
        elif "." in binding:
            raw_index, port = binding.split(".", 1)
            try:
                source_index = int(raw_index)
            except (TypeError, ValueError):
                return None
        else:
            return None
        if source_index < 1:
            return None
        source_node = step_id_by_index.get(source_index)
        if not source_node:
            return None
        if port.startswith("outputs."):
            port = port[8:]
        return source_node, port

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
    linked_path: str = ""  # 绑定的物理文件夹路径
    auto_sync: bool = False  # 是否启用自动同步
    last_sync_time: float = 0.0  # 最后同步时间戳

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
    def from_dict(cls, data: dict) -> "Folder":
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


# 默认特殊应用列表（需要Ctrl+中键触发的软件）
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
    dock_height_mode: int = 1  # 1=单行, 2=双行, 3=三行
    popup_max_rows: int = 3  # 中键弹窗每列最大行数

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
    bg_mode: str = "theme"  # theme, image, color
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

    # 边缘与阴影效果
    shadow_size: int = 0  # 模糊大小 (阴影/发光大小)
    shadow_distance: int = 0  # 模糊距离 (阴影偏移)
    edge_highlight_color: str = "#ffffff"
    edge_highlight_opacity: float = 0.0  # Shared/Default, keeping for compatibility or fallback

    custom_bg_path: str = ""

    special_apps: list[str] = field(default_factory=lambda: DEFAULT_SPECIAL_APPS.copy())

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
            "popup_trigger_mode": self.popup_trigger_mode,
            "popup_trigger_keys": self.popup_trigger_keys,
            "popup_trigger_button": self.popup_trigger_button,
            "popup_trigger_modifiers": self.popup_trigger_modifiers,
            "popup_special_trigger_mode": self.popup_special_trigger_mode,
            "popup_special_trigger_keys": self.popup_special_trigger_keys,
            "popup_special_trigger_button": self.popup_special_trigger_button,
            "popup_special_trigger_modifiers": self.popup_special_trigger_modifiers,
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
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
        if not hasattr(settings, 'popup_trigger_button'):
            settings.popup_trigger_button = "middle"
        if not hasattr(settings, 'popup_trigger_modifiers'):
            settings.popup_trigger_modifiers = []
        if not hasattr(settings, 'popup_special_trigger_button'):
            settings.popup_special_trigger_button = "middle"
        if not hasattr(settings, 'popup_special_trigger_modifiers'):
            settings.popup_special_trigger_modifiers = ["ctrl"]

        # 向后兼容：确保新触发模式字段有默认值
        if not hasattr(settings, 'popup_trigger_mode'):
            settings.popup_trigger_mode = "mouse"
        if not hasattr(settings, 'popup_trigger_keys'):
            settings.popup_trigger_keys = []
        if not hasattr(settings, 'popup_special_trigger_mode'):
            settings.popup_special_trigger_mode = "mouse"
        if not hasattr(settings, 'popup_special_trigger_keys'):
            settings.popup_special_trigger_keys = []

        return settings


@dataclass
class AppData:
    """应用数据"""

    version: str = "2.5"
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
            "settings": self.settings.to_dict(),
            "folders": [folder.to_dict() for folder in self.folders],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppData":
        app_data = cls.__new__(cls)
        app_data.version = data.get("version", "1.0")
        app_data.settings = AppSettings.from_dict(data.get("settings", {}))
        app_data.folders = [Folder.from_dict(f) for f in data.get("folders", [])]
        if not app_data.folders:
            app_data._create_default_folders()
        return app_data
