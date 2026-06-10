from core.data_models import ShortcutItem, ShortcutType
from qt_compat import QColor, QWidget


def test_url_icon_fetch_task_forces_refresh(monkeypatch, qapp):
    import core.favicon_cache as favicon_cache
    from ui.config_window.url_dialog import run_url_icon_fetch

    captured = {}

    def fake_fetch_favicon(url, force_refresh=False):
        captured["url"] = url
        captured["force_refresh"] = force_refresh
        return "C:/tmp/icon.png"

    monkeypatch.setattr(favicon_cache, "fetch_favicon", fake_fetch_favicon)

    result = run_url_icon_fetch("https://example.test")

    assert captured == {"url": "https://example.test", "force_refresh": True}
    assert result["icon_path"] == "C:/tmp/icon.png"


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


def test_url_dialog_keeps_base_dialog_window_border_colors(qapp):
    from ui.config_window.url_dialog import UrlDialog

    dialog = UrlDialog(shortcut=ShortcutItem(type=ShortcutType.URL))
    try:
        dialog._apply_theme()

        assert isinstance(dialog.bg_color, QColor)
        assert isinstance(dialog.border_color, QColor)
        assert dialog.border_color.isValid()
    finally:
        dialog.deleteLater()


def test_url_dialog_light_theme_border_matches_base_dialog(qapp):
    from ui.config_window.url_dialog import UrlDialog

    parent = QWidget()
    parent.theme = "light"
    dialog = UrlDialog(parent=parent, shortcut=ShortcutItem(type=ShortcutType.URL))
    try:
        assert dialog.theme == "light"
        assert isinstance(dialog.bg_color, QColor)
        assert isinstance(dialog.border_color, QColor)
        assert dialog.bg_color == QColor(242, 242, 247, 160)
        assert dialog.border_color == QColor(229, 229, 234, 150)
    finally:
        dialog.deleteLater()
        parent.deleteLater()
