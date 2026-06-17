"""Chain-dialog risk-analysis mixin.

Extracted from :mod:`ui.config_window.chain_dialog` as part of the
P1-06 file-split pass.  The :class:`ChainDialogRiskMixin` renders
the human-readable risk summary into the dialog's ``result_view``.
"""

from __future__ import annotations

from core import ShortcutType
from core.chain_processors import processor_definition
from core.i18n import tr


class ChainDialogRiskMixin:
    """Risk-analysis helpers for the chain editor.

    The host class is expected to expose:

    * :pyattr:`_steps` — current list of step dicts
    * :pyattr:`_shortcut_map` — returns a ``dict[str, ShortcutItem]``
    * :pyattr:`result_view` — ``QPlainTextEdit`` for the output
    """

    def _refresh_risk_analysis(self):
        risks = self._analyze_risks()
        if risks:
            lines = [tr("⚠ 风险分析"), ""]
            lines.extend(risks)
            lines.append("")
            lines.append(tr("共 {n} 个步骤", n=len(self._steps)))
        elif self._steps:
            lines = [tr("✓ 未发现明显风险"), "", tr("共 {n} 个步骤", n=len(self._steps))]
        else:
            lines = [tr("暂无步骤。"), "", tr("点击「添加」将已有快捷方式加入动作链。")]
        self.result_view.setPlainText("\n".join(lines))

    def _analyze_risks(self) -> list[str]:
        smap = self._shortcut_map()  # type: ignore[attr-defined]
        risks = []
        for i, step in enumerate(self._steps):  # type: ignore[attr-defined]
            if str(step.get("node_type") or "shortcut") == "processor":
                risks.extend(self._processor_risks(i + 1, str(step.get("processor_id") or "")))
                continue
            sid = step.get("shortcut_id", "")
            target = smap.get(sid)
            num = i + 1
            if target is None:
                risks.append(tr("  步骤 {n}: 引用的快捷方式不存在", n=num))
                continue
            if getattr(target, "run_as_admin", False):
                risks.append(tr("  步骤 {n}: 将以管理员权限运行", n=num))
            if target.type == ShortcutType.HOTKEY:
                risks.append(tr("  步骤 {n}: 快捷键操作，可能产生冲突", n=num))
            if target.type == ShortcutType.COMMAND:
                risks.append(tr("  步骤 {n}: 将执行命令", n=num))
        return risks

    def _processor_risks(self, step_num: int, processor_id: str) -> list[str]:
        legacy_processor_ids = {
            "file_write": "file_write_text",
        }
        processor_id = legacy_processor_ids.get(str(processor_id or ""), str(processor_id or ""))
        definition = processor_definition(processor_id)
        if definition is None:
            return [tr("  步骤 {n}: 处理节点定义不存在", n=step_num)]
        safety = definition.safety
        risks = []
        if safety.level == "dangerous":
            risks.append(tr("  步骤 {n}: 高风险处理节点 - {name}", n=step_num, name=definition.title))
        elif safety.level == "caution":
            risks.append(tr("  步骤 {n}: 需要注意的处理节点 - {name}", n=step_num, name=definition.title))
        if safety.executes_code:
            risks.append(tr("  步骤 {n}: 将执行脚本代码", n=step_num))
        if safety.network:
            risks.append(tr("  步骤 {n}: 将访问网络", n=step_num))
        if safety.reads_files:
            risks.append(tr("  步骤 {n}: 将读取本地文件", n=step_num))
        if safety.writes_files:
            risks.append(tr("  步骤 {n}: 将写入本地文件", n=step_num))
        if safety.requires_confirmation:
            risks.append(tr("  步骤 {n}: 建议运行前二次确认", n=step_num))
        return risks


__all__ = ["ChainDialogRiskMixin"]
