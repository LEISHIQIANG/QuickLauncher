from pathlib import Path

import core.shortcut_icon_helpers as icon_helpers
from core.data_models import ShortcutType
from core.shortcut_icon_helpers import (
    _resolve_lnk_target,
    default_folder_icon_path,
    shortcut_target_points_to_folder,
    shortcut_type_for_target,
    shortcut_uses_folder_icon,
)


def test_lnk_target_folder_uses_folder_icon(monkeypatch, tmp_path):
    folder = tmp_path / "Docs"
    folder.mkdir()
    lnk = tmp_path / "docs.lnk"
    lnk.write_text("stub", encoding="utf-8")

    _resolve_lnk_target.cache_clear()
    monkeypatch.setattr(
        "core.shortcut_parser.ShortcutParser.parse",
        staticmethod(lambda _path: {"target": str(folder)}),
    )

    assert shortcut_target_points_to_folder(str(lnk)) is True
    assert shortcut_uses_folder_icon(ShortcutType.FILE, str(lnk)) is True
    assert shortcut_type_for_target(str(lnk)) == ShortcutType.FOLDER


def test_lnk_resolution_can_be_skipped_for_paint_paths(monkeypatch, tmp_path):
    folder = tmp_path / "Docs"
    folder.mkdir()
    lnk = tmp_path / "docs.lnk"
    lnk.write_text("stub", encoding="utf-8")

    _resolve_lnk_target.cache_clear()
    monkeypatch.setattr(
        "core.shortcut_parser.ShortcutParser.parse",
        staticmethod(lambda _path: {"target": str(folder)}),
    )

    assert shortcut_target_points_to_folder(str(lnk), resolve_lnk=False) is False


def test_default_folder_icon_path_uses_module_relative_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_helpers, "app_root", lambda: tmp_path / "missing-app-root")
    monkeypatch.setattr(icon_helpers.sys, "argv", [str(tmp_path / "missing-main.py")])

    path = default_folder_icon_path()

    assert path is not None
    assert Path(path).name == "Folder.ico"
