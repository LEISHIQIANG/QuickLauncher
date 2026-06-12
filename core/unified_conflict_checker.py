"""统一冲突检测器 - 集中管理所有快捷键冲突检测逻辑"""

from dataclasses import dataclass, field

from .hotkey_conflict_checker import check_conflict, normalize_hotkey
from .trigger_config import normalize_trigger_config, trigger_config_to_hotkey


@dataclass
class Conflict:
    """单个冲突信息"""

    type: str  # "system", "internal", "external", "partial"
    source: str  # 冲突源描述
    details: str  # 详细说明


@dataclass
class ConflictReport:
    """冲突检测报告"""

    has_conflict: bool
    severity: str  # "error", "warning", "info"
    conflicts: list[Conflict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class UnifiedConflictChecker:
    """统一冲突检测器"""

    def __init__(self):
        pass

    def check_hotkey(self, hotkey_str: str, context: dict = None) -> ConflictReport:
        """检查快捷键冲突

        Args:
            hotkey_str: 快捷键字符串，如 "Ctrl+A"
            context: 上下文信息（shortcuts, exclude_id, settings等）

        Returns:
            ConflictReport: 包含冲突类型、严重级别、建议等
        """
        if context is None:
            context = {}

        conflicts = []

        # 1. 检查系统热键冲突
        system_conflict = self._check_system_conflict(hotkey_str)
        if system_conflict:
            conflicts.append(system_conflict)

        # 2. 检查内部快捷键重复
        if "shortcuts" in context:
            shortcuts = context["shortcuts"]
            exclude_id = context.get("exclude_id")
            internal_conflicts = self._check_internal_hotkey_duplicates(hotkey_str, shortcuts, exclude_id)
            conflicts.extend(internal_conflicts)

        # 3. 检查与弹窗触发冲突
        if "settings" in context:
            trigger_conflicts = self._check_hotkey_vs_popup_trigger(hotkey_str, context["settings"])
            conflicts.extend(trigger_conflicts)

        # 确定严重级别
        severity = "info"
        if conflicts:
            severity = "error" if any(c.type == "system" for c in conflicts) else "warning"

        return ConflictReport(has_conflict=len(conflicts) > 0, severity=severity, conflicts=conflicts)

    def _check_system_conflict(self, hotkey_str: str) -> Conflict | None:
        """检查系统热键冲突"""
        is_conflict, msg = check_conflict(hotkey_str)
        if is_conflict:
            return Conflict(type="system", source="Windows系统/常用软件", details=msg)
        return None

    def _check_internal_hotkey_duplicates(
        self, hotkey_str: str, shortcuts: list, exclude_id: str = None
    ) -> list[Conflict]:
        """检查快捷键是否与其他快捷方式重复"""
        conflicts = []
        normalized = normalize_hotkey(hotkey_str)

        for sc in shortcuts:
            if sc.id != exclude_id and hasattr(sc, "hotkey") and sc.hotkey:
                if normalize_hotkey(sc.hotkey) == normalized:
                    conflicts.append(Conflict(type="internal", source=f"快捷方式: {sc.name}", details="快捷键完全相同"))

        return conflicts

    def _check_hotkey_vs_popup_trigger(self, hotkey_str: str, settings) -> list[Conflict]:
        """检查快捷键是否与弹窗触发冲突"""
        conflicts = []
        normalized = normalize_hotkey(hotkey_str)

        # 检查普通触发（keyboard模式）
        normal = normalize_trigger_config(
            getattr(settings, "popup_trigger_mode", "mouse"),
            getattr(settings, "popup_trigger_keys", []),
            getattr(settings, "popup_trigger_button", ""),
            getattr(settings, "popup_trigger_modifiers", []),
        )
        if normal.mode == "keyboard":
            trigger_str = trigger_config_to_hotkey(normal.mode, normal.keys, normal.modifiers)
            if trigger_str:
                if normalize_hotkey(trigger_str) == normalized:
                    conflicts.append(Conflict(type="internal", source="弹窗普通触发", details="与弹窗触发快捷键相同"))

        # 检查特殊触发（keyboard模式）
        special = normalize_trigger_config(
            getattr(settings, "popup_special_trigger_mode", "mouse"),
            getattr(settings, "popup_special_trigger_keys", []),
            getattr(settings, "popup_special_trigger_button", ""),
            getattr(settings, "popup_special_trigger_modifiers", []),
        )
        if special.mode == "keyboard":
            trigger_str = trigger_config_to_hotkey(special.mode, special.keys, special.modifiers)
            if trigger_str:
                if normalize_hotkey(trigger_str) == normalized:
                    conflicts.append(Conflict(type="internal", source="弹窗特殊触发", details="与特殊触发快捷键相同"))

        return conflicts

    @staticmethod
    def _build_trigger_string(keys: list[str], modifiers: list[str]) -> str:
        """构建触发快捷键字符串"""
        parts = list(modifiers) + list(keys)
        return "+".join(parts) if parts else ""

    def check_trigger_config(self, mode: str, keys: list[str], button: str, modifiers: list[str]) -> ConflictReport:
        """检查触发配置冲突

        Args:
            mode: 触发模式 keyboard/mouse/hybrid
            keys: 键盘按键列表
            button: 鼠标按键
            modifiers: 修饰键列表

        Returns:
            ConflictReport: 冲突检测报告
        """
        conflicts = []
        config = normalize_trigger_config(mode, keys, button, modifiers)
        mode, keys, button, modifiers = config.mode, config.keys, config.button, config.modifiers

        # keyboard 模式验证
        if mode == "keyboard":
            if not keys:
                conflicts.append(Conflict(type="validation", source="触发配置", details="键盘模式必须指定至少一个按键"))
            else:
                # 检查系统热键冲突
                hotkey_str = trigger_config_to_hotkey(mode, keys, modifiers)
                system_conflict = self._check_system_conflict(hotkey_str)
                if system_conflict:
                    conflicts.append(system_conflict)

                # 必须有修饰键
                if not modifiers:
                    conflicts.append(
                        Conflict(
                            type="validation", source="触发配置", details="键盘触发必须配合修饰键（Ctrl/Shift/Win）"
                        )
                    )

        # hybrid 模式验证
        elif mode == "hybrid":
            if not keys or not button:
                conflicts.append(
                    Conflict(type="validation", source="触发配置", details="混合模式必须同时指定键盘按键和鼠标按键")
                )

        # mouse 模式验证（基本检查）
        elif mode == "mouse":
            if button in ("left", "right") and not modifiers:
                conflicts.append(
                    Conflict(
                        type="validation",
                        source="触发配置",
                        details=f"「{self._button_name(button)}」必须配合修饰键使用",
                    )
                )

        severity = "error" if conflicts else "info"
        return ConflictReport(has_conflict=len(conflicts) > 0, severity=severity, conflicts=conflicts)

    @staticmethod
    def _button_name(button: str) -> str:
        """按键显示名称"""
        mapping = {"left": "左键", "right": "右键", "middle": "中键", "x1": "侧键后", "x2": "侧键前"}
        return mapping.get(button, button)
