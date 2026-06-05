from services.update.config import UpdateInfo
from services.update.ui import UpdateDialog, _markdown_to_html


def test_markdown_to_html_escapes_and_formats_basic_blocks():
    rendered = _markdown_to_html("# Title\n\n- **Fix** `code` [link](https://example.com)", theme="light")

    assert "Title" in rendered
    assert "<table" in rendered
    assert "<strong>" not in rendered
    assert "Fix" in rendered
    assert "code" in rendered
    assert 'href="https://example.com"' in rendered


def test_markdown_to_html_escapes_raw_html():
    rendered = _markdown_to_html("<script>alert(1)</script>")

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_download_progress_text_handles_unknown_total():
    text = UpdateDialog.show_download_progress_text(5 * 1024 * 1024, 0)

    assert "5.0" in text
    assert "0%" in text


def test_show_download_failed_uses_critical_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "services.update.ui.ThemedMessageBox.critical",
        lambda parent, title, text: calls.append((parent, title, text)),
    )

    UpdateDialog.show_download_failed("network down", parent="parent")

    assert calls
    assert calls[0][0] == "parent"
    assert "network down" in calls[0][2]


def test_show_check_failed_uses_warning_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "services.update.ui.ThemedMessageBox.warning",
        lambda parent, title, text: calls.append((parent, title, text)),
    )

    UpdateDialog.show_check_failed("bad cert", parent="parent")

    assert calls
    assert "bad cert" in calls[0][2]


def test_show_up_to_date_uses_information_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "services.update.ui.ThemedMessageBox.information",
        lambda parent, title, text: calls.append((parent, title, text)),
    )

    UpdateDialog.show_up_to_date(parent="parent")

    assert calls
    assert calls[0][0] == "parent"


def test_show_download_finished_runs_install_callback_on_yes(monkeypatch):
    called = {"install": False}
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.Yes", 1)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.No", 2)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.Download", 4)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.question", lambda *args, **kwargs: 1)

    UpdateDialog.show_download_finished(on_install=lambda: called.__setitem__("install", True))

    assert called["install"] is True


def test_show_download_finished_ignores_install_callback_on_no(monkeypatch):
    called = {"install": False}
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.Yes", 1)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.No", 2)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.Download", 4)
    monkeypatch.setattr("services.update.ui.ThemedMessageBox.question", lambda *args, **kwargs: 2)

    UpdateDialog.show_download_finished(on_install=lambda: called.__setitem__("install", True))

    assert called["install"] is False


def test_show_update_available_invokes_download_callback(qapp, monkeypatch):
    from qt_compat import QDialog, QPushButton

    def fake_exec(dialog):
        for button in dialog.findChildren(QPushButton):
            if "下载" in button.text():
                button.click()
                break
        return 0

    monkeypatch.setattr(QDialog, "exec_", fake_exec)
    called = {"download": False}

    UpdateDialog.show_update_available(
        UpdateInfo(has_update=True, version="9.9.9", changelog_zh="- 修复问题"),
        on_download=lambda: called.__setitem__("download", True),
    )

    assert called["download"] is True
