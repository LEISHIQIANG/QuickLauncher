import pytest

from core.data_models import ShortcutType

pytestmark = pytest.mark.ui


def test_create_shortcut_from_lnk_to_folder_uses_folder_type(monkeypatch, tmp_path):
    from ui.config_window.icon_grid import IconGrid

    target = tmp_path / "Docs"
    target.mkdir()
    lnk = tmp_path / "docs.lnk"
    lnk.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(
        "core.shortcut_parser.ShortcutParser.parse",
        staticmethod(lambda _path: {"target": str(target), "args": "", "working_dir": ""}),
    )

    shortcut = IconGrid._create_shortcut_from_file(None, str(lnk))

    assert shortcut.target_path == str(target)
    assert shortcut.type == ShortcutType.FOLDER
