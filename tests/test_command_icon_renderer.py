import pytest

from core.command_icon_catalog import (
    BUILTIN_COMMAND_ICON_IDS,
    builtin_command_icon_path,
    builtin_command_id_from_icon_path,
)
from ui.command_icon_renderer import render_builtin_command_icon

pytestmark = pytest.mark.ui


def test_icon_catalog_only_assigns_selected_commands():
    assert builtin_command_icon_path("json") == "builtin-command:json"
    assert builtin_command_icon_path("hosts") == ""
    assert builtin_command_id_from_icon_path("builtin-command:json") == "json"
    assert builtin_command_id_from_icon_path("builtin-command:hosts") == ""


def test_all_selected_icons_render_in_both_themes(qapp):
    for command_id in BUILTIN_COMMAND_ICON_IDS:
        dark = render_builtin_command_icon(command_id, 32, "dark")
        light = render_builtin_command_icon(command_id, 32, "light")

        assert dark is not None and not dark.isNull()
        assert light is not None and not light.isNull()
        assert dark.toImage() != light.toImage()
