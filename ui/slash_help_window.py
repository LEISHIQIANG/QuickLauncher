"""Slash command help dialog."""

from __future__ import annotations

from core.i18n import tr
from core.slash_commands import SLASH_COMMANDS
from qt_compat import QApplication, QFont, QHBoxLayout, QPlainTextEdit, QPushButton
from ui.themed_tool_window import ThemedToolWindow
from ui.utils.ui_scale import font_px, sp


class SlashHelpWindow(ThemedToolWindow):
    """Log-style help window for slash commands."""

    def __init__(self, data_manager, parent=None):
        self.data_manager = data_manager
        theme = getattr(data_manager.get_settings(), "theme", "light")
        super().__init__(tr("斜杠命令帮助"), theme=theme, parent=parent)
        self.resize(sp(560), sp(520))
        self._setup_ui()
        self._apply_content_theme()
        self.refresh()

    def _setup_ui(self):
        self.set_subtitle(tr("输入 / 进入命令模式，继续输入英文或中文可筛选"))

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        font = QFont("Microsoft YaHei UI", font_px(9))
        if not font.exactMatch():
            font = QFont("Segoe UI", font_px(9))
        self.text.setFont(font)
        self.content_layout.addWidget(self.text)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_btn)

        self.copy_btn = QPushButton(tr("复制列表"))
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        buttons.addWidget(self.copy_btn)

        self.close_btn = QPushButton(tr("关闭"))
        self.close_btn.clicked.connect(self.close)
        buttons.addWidget(self.close_btn)

        buttons.addStretch()
        self.button_layout.addLayout(buttons)

    def _apply_content_theme(self):
        if hasattr(self, "text"):
            self.style_plain_text(self.text)
        buttons = [
            getattr(self, "refresh_btn", None),
            getattr(self, "copy_btn", None),
            getattr(self, "close_btn", None),
        ]
        self.style_buttons(*(button for button in buttons if button is not None))

    def refresh(self):
        self.text.setPlainText(self._format_commands())

    def _format_commands(self) -> str:
        groups = [
            (tr("应用"), "system"),
            (tr("项目内部"), "internal"),
            (tr("开发者工具"), "developer"),
            (tr("网络工具"), "network"),
            (tr("窗口"), "window"),
            (tr("Windows 系统"), "windows"),
            (tr("帮助"), "help"),
        ]
        lines = []
        for title, category in groups:
            commands = [cmd for cmd in SLASH_COMMANDS if cmd.category == category]
            if not commands:
                continue
            if lines:
                lines.append("")
            lines.append(title)
            lines.append("-" * 24)
            for cmd in commands:
                display = cmd.display_name or cmd.canonical
                aliases = " / ".join(cmd.aliases[:4])
                lines.append(f"{display}    /{cmd.canonical}")
                lines.append(f"  {cmd.description}")
                lines.append(f"  {tr('别名')}: {aliases}")
        return "\n".join(lines)
