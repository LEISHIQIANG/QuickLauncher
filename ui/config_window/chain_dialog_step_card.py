"""Step card widget for the chain-editor dialog.

Extracted from :mod:`ui.config_window.chain_dialog` as part of the
P1-06 file-split effort.  :class:`StepCardWidget` is a thin
``QFrame`` that exposes inline parameter controls (delay,
``stop_on_error``, ``enabled``) for a single chain step and notifies
the parent dialog whenever the user changes one of them.

The card uses Qt signals rather than direct method calls so the
dialog can stay decoupled from the card's class — the
:pyattr:`context_menu_requested` signal replaces the legacy
"walk-up-to-ChainDialog" pattern that the inline implementation
used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core import ShortcutType
from core.i18n import tr
from qt_compat import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPoint,
    QSpinBox,
    Qt,
    pyqtSignal,
)
from ui.utils.ui_scale import scale_qss, sp

if TYPE_CHECKING:
    from ui.config_window.chain_dialog import ChainDialog


class StepCardWidget(QFrame):
    """Per-step card with inline delay / stop / enable controls."""

    clicked = pyqtSignal(int)
    step_changed = pyqtSignal(int)  # 参数变更通知
    context_menu_requested = pyqtSignal(int, QPoint)

    def __init__(
        self,
        index: int,
        step: dict,
        shortcut_name: str,
        shortcut_type: ShortcutType,
        icon=None,
        parent=None,
    ):
        super().__init__(parent)
        self.step_index = index
        self._selected = False
        self._checkbox_style = ""
        self._type_color = _TYPE_COLORS.get(shortcut_type, ("#999", "??"))[0]
        self._setup_ui(step, shortcut_name, shortcut_type, icon)

    def _setup_ui(self, step: dict, shortcut_name: str, shortcut_type: ShortcutType, icon):
        self.setMinimumHeight(sp(40))
        self.setCursor(Qt.PointingHandCursor)  # type: ignore[attr-defined]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp(6), sp(3), sp(6), sp(3))
        layout.setSpacing(sp(4))

        # 序号
        num_label = QLabel(f"{self.step_index + 1}")
        num_label.setFixedWidth(sp(18))
        num_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        num_label.setStyleSheet(
            scale_qss(
                "color: rgba(128,128,128,180); font-size: 11px; font-weight: 400; "
                "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;"
            )
        )
        layout.addWidget(num_label)

        # 快捷方式图标
        icon_label = QLabel()
        icon_label.setFixedSize(sp(24), sp(24))
        icon_label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        if icon is not None and not icon.isNull():
            icon_label.setPixmap(
                icon.scaled(
                    sp(24),
                    sp(24),
                    Qt.KeepAspectRatio,  # type: ignore[attr-defined]
                    Qt.SmoothTransformation,  # type: ignore[attr-defined]
                )
            )
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        # 名称
        display_name = shortcut_name or step.get("shortcut_id", "???")
        name_label = QLabel(display_name)
        name_label.setStyleSheet(
            scale_qss("font-size: 13px; font-weight: 400; font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;")
        )
        layout.addWidget(name_label, 1)

        # ── 内联参数控件 ──

        # 延迟 (QSpinBox，纯输入框，无加减按钮)
        delay_spin = QSpinBox()
        delay_spin.setButtonSymbols(QSpinBox.NoButtons)
        delay_spin.setRange(0, 60000)
        delay_spin.setValue(max(0, int(step.get("delay_ms", 0) or 0)))
        delay_spin.setSuffix("ms")
        delay_spin.setFixedWidth(sp(72))
        delay_spin.setToolTip(tr("执行前延迟"))
        delay_spin.setStyleSheet(
            scale_qss(
                "QSpinBox { font-size: 11px; font-weight: 400; "
                "font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; "
                "padding: 1px 3px; border-radius: 5px; }"
                "QSpinBox::up-button, QSpinBox::down-button { width: 14px; }"
            )
        )
        delay_spin.valueChanged.connect(self._on_delay_changed)
        layout.addWidget(delay_spin)
        self._delay_spin = delay_spin

        # 失败停止 (QCheckBox)
        stop_cb = QCheckBox(tr("失败停止"))
        stop_cb.setChecked(bool(step.get("stop_on_error", True)))
        stop_cb.setToolTip(tr("该步骤失败时停止后续步骤"))
        stop_cb.stateChanged.connect(self._on_stop_changed)
        layout.addWidget(stop_cb)
        self._stop_cb = stop_cb

        # 启用 (QCheckBox)
        enabled_cb = QCheckBox(tr("启用"))
        enabled_cb.setChecked(bool(step.get("enabled", True)))
        enabled_cb.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(enabled_cb)
        self._enabled_cb = enabled_cb

        self._update_style(selected=False)

    # 控件变更 → 同步到 _steps 并通知对话框
    def _on_delay_changed(self, value):
        self.step_changed.emit(self.step_index)

    def _on_stop_changed(self, _):
        self.step_changed.emit(self.step_index)

    def _on_enabled_changed(self, state):
        # 禁用时名称变灰
        self.step_changed.emit(self.step_index)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style(selected)

    def set_checkbox_style(self, style: str):
        self._checkbox_style = style
        self._stop_cb.setStyleSheet(style)
        self._enabled_cb.setStyleSheet(style)
        self._update_style(self._selected)

    def _find_dialog(self) -> ChainDialog | None:
        """Walk up the parent chain until we find the :class:`ChainDialog`.

        Kept for backward compatibility — older call sites pass the
        dialog as the parent widget.  Most consumers should connect
        to :pyattr:`context_menu_requested` instead.
        """
        parent = self.parent()
        while parent is not None:
            from ui.config_window.chain_dialog import ChainDialog

            if isinstance(parent, ChainDialog):
                return parent
            parent = parent.parent()
        return None

    def _update_style(self, selected: bool):
        c = self._type_color
        # 从父级对话框获取 QToolTip 规则，避免子级 setStyleSheet 阻断继承
        dialog = self._find_dialog()
        tip_rule = getattr(dialog, "_tip_stylesheet", "") if dialog else ""
        child_rules = self._checkbox_style + tip_rule
        if selected:
            self.setStyleSheet(
                scale_qss(
                    f"StepCardWidget {{"
                    f" background-color: rgba(0, 122, 255, 0.15);"
                    f" border-left: 3px solid {c};"
                    f" border-top: 1px solid rgba(0, 122, 255, 0.4);"
                    f" border-right: 1px solid rgba(0, 122, 255, 0.4);"
                    f" border-bottom: 1px solid rgba(0, 122, 255, 0.4);"
                    f" border-radius: 8px;"
                    f"}}"
                )
                + child_rules
            )
        else:
            self.setStyleSheet(
                scale_qss(
                    f"StepCardWidget {{"
                    f" background-color: rgba(128, 128, 128, 0.08);"
                    f" border-left: 3px solid {c};"
                    f" border-top: 1px solid rgba(128, 128, 128, 0.12);"
                    f" border-right: 1px solid rgba(128, 128, 128, 0.12);"
                    f" border-bottom: 1px solid rgba(128, 128, 128, 0.12);"
                    f" border-radius: 8px;"
                    f"}}"
                    f"StepCardWidget:hover {{"
                    f" background-color: rgba(128, 128, 128, 0.15);"
                    f"}}"
                )
                + child_rules
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.step_index)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        # 右键菜单由 ChainDialog 通过 ``context_menu_requested`` 信号接收
        self.context_menu_requested.emit(self.step_index, event.globalPos())


_TYPE_COLORS = {
    ShortcutType.FILE: ("#64B5F6", "FILE"),
    ShortcutType.FOLDER: ("#64B5F6", "DIR"),
    ShortcutType.URL: ("#4DB6AC", "URL"),
    ShortcutType.HOTKEY: ("#7986CB", "KEY"),
    ShortcutType.COMMAND: ("#81C784", "CMD"),
}


__all__ = ["StepCardWidget"]
