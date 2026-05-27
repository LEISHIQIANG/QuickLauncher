from core.data_models import ShortcutItem, ShortcutType


def test_url_icon_fetch_thread_forces_refresh(monkeypatch, qapp):
    import core.favicon_cache as favicon_cache
    from ui.config_window.url_dialog import UrlIconFetchThread

    captured = {}

    def fake_fetch_favicon(url, force_refresh=False):
        captured["url"] = url
        captured["force_refresh"] = force_refresh
        return "C:/tmp/icon.png"

    monkeypatch.setattr(favicon_cache, "fetch_favicon", fake_fetch_favicon)
    thread = UrlIconFetchThread("https://example.test")
    results = []
    thread.finished_signal.connect(results.append)

    thread.run()

    assert captured == {"url": "https://example.test", "force_refresh": True}
    assert results[-1]["icon_path"] == "C:/tmp/icon.png"


def test_url_dialog_ok_does_not_fetch_icon_without_click(monkeypatch, qapp):
    import core.favicon_cache as favicon_cache
    from ui.config_window.url_dialog import UrlDialog

    def fail_fetch(*args, **kwargs):
        raise AssertionError("fetch_favicon should only run after clicking 自动获取")

    monkeypatch.setattr(favicon_cache, "fetch_favicon", fail_fetch)
    dialog = UrlDialog(shortcut=ShortcutItem(type=ShortcutType.URL))
    try:
        dialog.name_edit.setText("测试")
        dialog.url_edit.setText("https://example.test")

        dialog._on_ok()

        assert dialog.result() == dialog.Accepted
        assert dialog._custom_icon_path == ""
    finally:
        dialog.deleteLater()


def test_url_dialog_exposes_ip_variable_buttons(qapp):
    from ui.config_window.url_dialog import UrlDialog

    dialog = UrlDialog(shortcut=ShortcutItem(type=ShortcutType.URL))
    try:
        buttons = {button.text(): button for button in dialog._url_var_buttons}
        assert "内网 IP" in buttons
        assert "公网 IP" in buttons

        buttons["内网 IP"].click()
        assert dialog.url_edit.text() == "{{LAN_IP}}"
        buttons["公网 IP"].click()
        assert dialog.url_edit.text() == "{{LAN_IP}}{{WAN_IP}}"
    finally:
        dialog.deleteLater()
