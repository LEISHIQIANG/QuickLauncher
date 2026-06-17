"""Theme-aware highlighting for ``{{variable}}`` template tokens."""

from __future__ import annotations

import re

from qt_compat import QColor, QFont, QPlainTextEdit, QSyntaxHighlighter, Qt, QtCompat, QTextCharFormat

_VARIABLE_TOKEN_RE = re.compile(r"(?<!\{)\{\{[^{}\r\n]+\}\}(?!\})")


def template_variable_color(theme: str) -> QColor:
    """Return a readable variable color for the active editor theme."""
    return QColor("#64D2FF" if theme == "dark" else "#005FB8")


class TemplateVariableHighlighter(QSyntaxHighlighter):
    """Highlight template-shaped tokens without changing their content."""

    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self._theme = ""
        self._format = QTextCharFormat()
        self.set_theme(theme)

    @property
    def theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str) -> None:
        normalized = "light" if theme == "light" else "dark"
        if normalized == self._theme:
            return
        self._theme = normalized
        self._format = QTextCharFormat()
        self._format.setForeground(template_variable_color(normalized))
        self._format.setFontWeight(QFont.DemiBold)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # type: ignore[unused-ignore, override]  # noqa: N802 - Qt API name
        for match in _VARIABLE_TOKEN_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self._format)


def install_template_variable_highlighter(editor: QPlainTextEdit, theme: str = "dark") -> TemplateVariableHighlighter:
    highlighter = TemplateVariableHighlighter(editor.document(), theme)
    editor._template_variable_highlighter = highlighter
    return highlighter


class TemplateLineEdit(QPlainTextEdit):
    """Single-line editor with QLineEdit-compatible text helpers."""

    def __init__(self, parent=None, *, theme: str = "dark"):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self._template_variable_highlighter = install_template_variable_highlighter(self, theme)

    def set_template_theme(self, theme: str) -> None:
        self._template_variable_highlighter.set_theme(theme)

    def text(self) -> str:
        return str(self.toPlainText())

    def setText(self, text: str) -> None:  # noqa: N802 - QLineEdit-compatible API
        self.setPlainText(text)
        self.setCursorPosition(len(self.text()))

    def setPlainText(self, text: str) -> None:  # type: ignore[unused-ignore, override]  # noqa: N802 - Qt API name
        super().setPlainText(self._single_line(text))

    def insertPlainText(self, text: str) -> None:  # type: ignore[unused-ignore, override]  # noqa: N802 - Qt API name
        super().insertPlainText(self._single_line(text))

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - Qt API name
        if source and source.hasText():
            self.insertPlainText(source.text())
            return
        super().insertFromMimeData(source)

    def cursorPosition(self) -> int:  # noqa: N802 - QLineEdit-compatible API
        return int(self.textCursor().position())

    def setCursorPosition(self, position: int) -> None:  # noqa: N802 - QLineEdit-compatible API
        cursor = self.textCursor()
        cursor.setPosition(max(0, min(int(position), len(self.text()))))
        self.setTextCursor(cursor)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):  # type: ignore[unused-ignore, attr-defined]
            self.focusNextChild()
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _single_line(text: str) -> str:
        return str(text or "").replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
