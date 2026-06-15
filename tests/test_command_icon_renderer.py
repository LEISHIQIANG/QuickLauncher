import pytest

from core.builtin_command_catalog import build_builtin_command_definitions
from core.command_icon_catalog import (
    BUILTIN_COMMAND_ICON_IDS,
    builtin_command_icon_path,
    builtin_command_id_from_icon_path,
)
from core.slash_commands import SLASH_COMMANDS
from ui.command_icon_renderer import render_builtin_command_icon

pytestmark = pytest.mark.ui


def test_icon_catalog_assigns_known_system_commands_only():
    assert builtin_command_icon_path("json") == "builtin-command:json"
    assert builtin_command_icon_path("hosts") == "builtin-command:hosts"
    assert builtin_command_id_from_icon_path("builtin-command:json") == "json"
    assert builtin_command_id_from_icon_path("builtin-command:hosts") == "hosts"
    assert builtin_command_icon_path("plugin.example") == ""
    assert builtin_command_id_from_icon_path("builtin-command:plugin.example") == ""


def test_icon_catalog_covers_all_registered_system_commands():
    command_ids = {command.id for command in build_builtin_command_definitions()}
    command_ids.update(command.canonical for command in SLASH_COMMANDS)
    command_ids.update({"pin_on", "pin_off"})

    assert command_ids == set(BUILTIN_COMMAND_ICON_IDS)


def test_all_system_icons_render_in_both_themes(qapp):
    for command_id in BUILTIN_COMMAND_ICON_IDS:
        for size in (16, 22, 32):
            dark = render_builtin_command_icon(command_id, size, "dark")
            light = render_builtin_command_icon(command_id, size, "light")

            assert dark is not None and not dark.isNull()
            assert light is not None and not light.isNull()
            assert dark.toImage() != light.toImage()
