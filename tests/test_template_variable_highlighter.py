from qt_compat import QPlainTextEdit
from ui.config_window.template_variable_highlighter import (
    TemplateLineEdit,
    install_template_variable_highlighter,
    template_variable_color,
)


def _format_colors(editor):
    editor._template_variable_highlighter.rehighlight()
    block = editor.document().firstBlock()
    return [entry.format.foreground().color() for entry in block.layout().formats()]


def test_plain_text_highlighter_colors_template_tokens(qapp):
    editor = QPlainTextEdit()
    install_template_variable_highlighter(editor, "dark")
    editor.setPlainText("echo {{selected_file:q}} plain")
    qapp.processEvents()

    assert template_variable_color("dark") in _format_colors(editor)


def test_template_line_edit_keeps_single_line_api_and_light_theme(qapp):
    editor = TemplateLineEdit(theme="dark")
    editor.setText("https://x.test/{{selected_files}}\nnext")
    editor.set_template_theme("light")
    qapp.processEvents()

    assert editor.text() == "https://x.test/{{selected_files}} next"
    assert editor.cursorPosition() == len(editor.text())
    assert template_variable_color("light") in _format_colors(editor)
