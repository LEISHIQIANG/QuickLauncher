import pytest
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from core.command_registry import CommandDefinition
from core.data_models import AppSettings
from ui.config_window.settings_commands_page import SettingsCommandsPageMixin


class FakeSettingsPage(QWidget):
    def __init__(self):
        super().__init__()

    def add_group(self, title):
        group = QGroupBox(title, self)
        layout = QVBoxLayout(group)
        return layout, group


class DummySettingsPanel(QWidget, SettingsCommandsPageMixin):
    def __init__(self):
        super().__init__()
        self.current_theme = "dark"
        self._setup_ui()

    def _setup_ui(self):
        # We need self.fav_list_widget, etc.
        # Let's call _setup_commands_page
        self.page = FakeSettingsPage()
        self.page.setParent(self)
        self._setup_commands_page(self.page)

    def _get_desc_color(self):
        return "white"


@pytest.mark.ui
def test_commands_page_buttons(qapp, monkeypatch, tmp_path):
    # Mock data manager and registry
    settings = AppSettings()
    settings.favorite_commands = []
    settings.disabled_builtin_commands = []

    class FakeDataManager:
        @staticmethod
        def get_settings():
            return settings

        @staticmethod
        def save():
            pass

        @staticmethod
        def update_settings(**kwargs):
            for key, value in kwargs.items():
                setattr(settings, key, value)
            return True

    class FakeRegistry:
        @staticmethod
        def list():
            return [
                CommandDefinition(
                    id="cmd_test1",
                    title="Test 1",
                    aliases=[],
                    source="builtin",
                    description="Desc 1",
                    category="developer",
                    handler=None,
                ),
                CommandDefinition(
                    id="cmd_test2",
                    title="Test 2",
                    aliases=[],
                    source="builtin",
                    description="Desc 2",
                    category="developer",
                    handler=None,
                ),
            ]

        @staticmethod
        def get(fid):
            if fid == "cmd_test1":
                return CommandDefinition(
                    id="cmd_test1",
                    title="Test 1",
                    aliases=[],
                    source="builtin",
                    description="Desc 1",
                    category="developer",
                    handler=None,
                )
            return None

    import core

    core.data_manager = FakeDataManager()
    monkeypatch.setattr("core.registry.list", FakeRegistry.list)
    monkeypatch.setattr("core.registry.get", FakeRegistry.get)

    panel = DummySettingsPanel()

    # Check initially there are widgets
    assert "cmd_test1" in panel._builtin_widgets
    assert "cmd_test2" in panel._builtin_widgets

    fav_btn1 = panel._builtin_widgets["cmd_test1"]["fav_btn"]
    toggle_btn1 = panel._builtin_widgets["cmd_test1"]["toggle_btn"]

    assert fav_btn1.text() == "收藏"
    assert toggle_btn1.text() == "禁用"

    # Click favorite button
    fav_btn1.click()
    # Check if settings updated
    assert "cmd_test1" in settings.favorite_commands
    # Check if button text changed in builtin list
    assert fav_btn1.text() == "取消收藏"
    # Check if fav_list_widget count changed
    assert panel.fav_list_widget.count() == 1

    # Click disable button
    toggle_btn1.click()
    assert "cmd_test1" in settings.disabled_builtin_commands
    assert toggle_btn1.text() == "启用"
