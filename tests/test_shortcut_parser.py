import importlib
import sys
import types

import core.shortcut_parser as shortcut_parser
from core.shortcut_parser import ShortcutParser


def test_shortcut_parser_lnk_falls_back_without_win32com(monkeypatch, tmp_path):
    lnk = tmp_path / "sample.lnk"
    lnk.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(shortcut_parser, "HAS_WIN32COM", False)
    monkeypatch.setattr(ShortcutParser, "_parse_lnk_with_win32com", staticmethod(lambda file_path: None))

    captured = {}

    def fake_run(cmd, capture_output, text, check, encoding, errors):
        captured["cmd"] = cmd
        return types.SimpleNamespace(
            returncode=0,
            stdout=(
                "C:/Target/App.exe\n"
                "___QL_SPLIT___\n"
                "--flag\n"
                "___QL_SPLIT___\n"
                "C:/Target\n"
                "___QL_SPLIT___\n"
                "C:/Icons/app.ico,3\n"
            ),
        )

    monkeypatch.setattr(shortcut_parser.subprocess, "run", fake_run)

    result = ShortcutParser.parse(str(lnk))

    assert result["target"] == "C:/Target/App.exe"
    assert result["args"] == "--flag"
    assert result["working_dir"] == "C:/Target"
    assert result["icon_location"] == "C:/Icons/app.ico"
    assert result["icon_index"] == 3
    assert captured["cmd"][0] == "powershell"


def test_shortcut_parser_import_without_win32com_does_not_warn(monkeypatch, caplog):
    module_name = "core.shortcut_parser"
    saved_module = sys.modules.pop(module_name, None)
    core_package = sys.modules.get("core")
    saved_attr = getattr(core_package, "shortcut_parser", None) if core_package else None

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "win32com.client":
            raise ImportError("no win32com")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    caplog.clear()

    try:
        module = importlib.import_module(module_name)

        assert not any("win32com" in record.message for record in caplog.records)
        assert module.HAS_WIN32COM is False
    finally:
        sys.modules.pop(module_name, None)
        if saved_module is not None:
            sys.modules[module_name] = saved_module
        if core_package is not None and saved_attr is not None:
            setattr(core_package, "shortcut_parser", saved_attr)
