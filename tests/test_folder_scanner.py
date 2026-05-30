import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from unittest.mock import patch

import pytest

from core.data_models import ShortcutItem, ShortcutType
from core.folder_scanner import FolderScanner

# ---------------------------------------------------------------------------
# _should_exclude
# ---------------------------------------------------------------------------


class TestShouldExclude:
    """Tests for FolderScanner._should_exclude"""

    @pytest.mark.parametrize(
        "filename",
        [
            "uninstall.exe",
            "UninstallTool.exe",
            "uninstaller.lnk",
            "uninst01.exe",
            "setup.exe",
            "my_setup.exe",
            "install.exe",
            "InstallHelper.exe",
        ],
    )
    def test_excluded_patterns(self, filename):
        assert FolderScanner._should_exclude(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "notepad.exe",
            "chrome.lnk",
            "myapp.exe",
            "folder",
            "readme.txt",
        ],
    )
    def test_not_excluded(self, filename):
        assert FolderScanner._should_exclude(filename) is False

    def test_case_insensitive(self):
        assert FolderScanner._should_exclude("UNINSTALL.exe") is True
        assert FolderScanner._should_exclude("Setup.exe") is True
        assert FolderScanner._should_exclude("INSTALL.lnk") is True
        assert FolderScanner._should_exclude("UnInst.exe") is True

    def test_partial_match(self):
        """Pattern appears anywhere in the filename."""
        assert FolderScanner._should_exclude("MyUninstallTool.exe") is True
        assert FolderScanner._should_exclude("app_setup_v2.exe") is True

    def test_empty_string(self):
        assert FolderScanner._should_exclude("") is False


# ---------------------------------------------------------------------------
# _create_folder_shortcut
# ---------------------------------------------------------------------------


class TestCreateFolderShortcut:
    """Tests for FolderScanner._create_folder_shortcut"""

    def test_basic_folder(self, tmp_path):
        target = tmp_path / "MyFolder"
        target.mkdir()

        result = FolderScanner._create_folder_shortcut(target)

        assert isinstance(result, ShortcutItem)
        assert result.name == "MyFolder"
        assert result.target_path == str(target)
        assert result.type == ShortcutType.FOLDER
        assert result.id  # non-empty UUID

    def test_unique_ids(self, tmp_path):
        folder = tmp_path / "dup"
        folder.mkdir()

        s1 = FolderScanner._create_folder_shortcut(folder)
        s2 = FolderScanner._create_folder_shortcut(folder)

        assert s1.id != s2.id

    def test_folder_with_unicode_name(self, tmp_path):
        target = tmp_path / "文档"
        target.mkdir()

        result = FolderScanner._create_folder_shortcut(target)

        assert result.name == "文档"
        assert result.target_path == str(target)


# ---------------------------------------------------------------------------
# _create_shortcut
# ---------------------------------------------------------------------------


class TestCreateShortcut:
    """Tests for FolderScanner._create_shortcut"""

    def test_exe_file(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_text("binary", encoding="utf-8")

        result = FolderScanner._create_shortcut(exe)

        assert isinstance(result, ShortcutItem)
        assert result.name == "app"
        assert result.target_path == str(exe)
        assert result.type == ShortcutType.FILE

    def test_lnk_file_parsed(self, tmp_path):
        lnk = tmp_path / "editor.lnk"
        lnk.write_text("stub", encoding="utf-8")

        fake_parsed = {
            "target": r"C:\Apps\editor.exe",
            "args": "--verbose",
            "working_dir": r"C:\Apps",
        }
        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = fake_parsed
            result = FolderScanner._create_shortcut(lnk)

        assert result.name == "editor"
        assert result.target_path == r"C:\Apps\editor.exe"
        assert result.target_args == "--verbose"
        assert result.working_dir == r"C:\Apps"
        assert result.type == ShortcutType.FILE

    def test_lnk_parser_returns_none(self, tmp_path):
        lnk = tmp_path / "broken.lnk"
        lnk.write_text("stub", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = None
            result = FolderScanner._create_shortcut(lnk)

        assert result.name == "broken"
        assert result.target_path == str(lnk)  # falls back to lnk path
        assert result.target_args == ""
        assert result.working_dir == ""

    def test_lnk_parser_raises(self, tmp_path):
        lnk = tmp_path / "corrupt.lnk"
        lnk.write_text("stub", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.side_effect = Exception("parse error")
            result = FolderScanner._create_shortcut(lnk)

        assert result.name == "corrupt"
        assert result.target_path == str(lnk)

    def test_unique_ids_for_each_call(self, tmp_path):
        f = tmp_path / "tool.exe"
        f.write_text("x", encoding="utf-8")

        s1 = FolderScanner._create_shortcut(f)
        s2 = FolderScanner._create_shortcut(f)

        assert s1.id != s2.id


# ---------------------------------------------------------------------------
# scan_folder - basic scenarios
# ---------------------------------------------------------------------------


class TestScanFolderBasic:
    """Tests for FolderScanner.scan_folder basic scenarios."""

    def test_nonexistent_folder(self):
        result = FolderScanner.scan_folder(r"C:\nonexistent_path_xyz")
        assert result == []

    def test_empty_folder(self, tmp_path):
        result = FolderScanner.scan_folder(str(tmp_path))
        assert result == []

    def test_folder_with_exe_files(self, tmp_path):
        (tmp_path / "notepad.exe").write_text("x", encoding="utf-8")
        (tmp_path / "chrome.exe").write_text("x", encoding="utf-8")

        result = FolderScanner.scan_folder(str(tmp_path))

        names = {s.name for s in result}
        assert names == {"notepad", "chrome"}
        for s in result:
            assert s.type == ShortcutType.FILE

    def test_folder_with_subdirectories(self, tmp_path):
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Docs").mkdir()

        result = FolderScanner.scan_folder(str(tmp_path))

        folder_names = {s.name for s in result if s.type == ShortcutType.FOLDER}
        assert folder_names == {"Projects", "Docs"}

    def test_subdirectories_have_folder_type(self, tmp_path):
        (tmp_path / "SubDir").mkdir()

        result = FolderScanner.scan_folder(str(tmp_path))

        assert len(result) == 1
        assert result[0].type == ShortcutType.FOLDER
        assert result[0].target_path == str(tmp_path / "SubDir")

    def test_mixed_content(self, tmp_path):
        (tmp_path / "app.exe").write_text("x", encoding="utf-8")
        (tmp_path / "link.lnk").write_text("stub", encoding="utf-8")
        (tmp_path / "SubFolder").mkdir()
        (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = None
            result = FolderScanner.scan_folder(str(tmp_path))

        types = {s.type for s in result}
        assert ShortcutType.FILE in types
        assert ShortcutType.FOLDER in types
        # readme.txt should be ignored
        assert all(s.name != "readme" for s in result)

    def test_lnk_files_scanned(self, tmp_path):
        lnk = tmp_path / "mylink.lnk"
        lnk.write_text("stub", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = {"target": r"C:\app.exe", "args": "", "working_dir": ""}
            result = FolderScanner.scan_folder(str(tmp_path))

        assert len(result) == 1
        assert result[0].name == "mylink"
        assert result[0].target_path == r"C:\app.exe"

    def test_unsupported_extensions_skipped(self, tmp_path):
        (tmp_path / "doc.pdf").write_text("x", encoding="utf-8")
        (tmp_path / "image.png").write_text("x", encoding="utf-8")
        (tmp_path / "script.py").write_text("x", encoding="utf-8")

        result = FolderScanner.scan_folder(str(tmp_path))
        assert result == []


# ---------------------------------------------------------------------------
# scan_folder - exclusion patterns
# ---------------------------------------------------------------------------


class TestScanFolderExclusions:
    """Excluded file patterns should not appear in results."""

    @pytest.mark.parametrize(
        "filename",
        [
            "uninstall.exe",
            "uninst.exe",
            "setup.exe",
            "install.exe",
            "MyUninstall.exe",
            "App_Uninstaller.lnk",
        ],
    )
    def test_excluded_files_not_in_results(self, tmp_path, filename):
        (tmp_path / filename).write_text("x", encoding="utf-8")

        result = FolderScanner.scan_folder(str(tmp_path))

        assert result == [], f"Expected {filename} to be excluded"

    def test_excluded_case_insensitive_in_scan(self, tmp_path):
        (tmp_path / "UNINSTALL.exe").write_text("x", encoding="utf-8")
        (tmp_path / "Setup.exe").write_text("x", encoding="utf-8")
        (tmp_path / "normal.exe").write_text("x", encoding="utf-8")

        result = FolderScanner.scan_folder(str(tmp_path))

        names = {s.name for s in result}
        assert names == {"normal"}

    def test_excluded_and_valid_files_coexist(self, tmp_path):
        (tmp_path / "good.exe").write_text("x", encoding="utf-8")
        (tmp_path / "setup.exe").write_text("x", encoding="utf-8")
        (tmp_path / "install_helper.lnk").write_text("x", encoding="utf-8")
        (tmp_path / "app.lnk").write_text("x", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = None
            result = FolderScanner.scan_folder(str(tmp_path))

        names = {s.name for s in result}
        assert names == {"good", "app"}


# ---------------------------------------------------------------------------
# scan_folder - INCLUDE_FOLDERS toggle
# ---------------------------------------------------------------------------


class TestScanFolderIncludeFolders:
    """Verify INCLUDE_FOLDERS flag controls folder inclusion."""

    def test_folders_excluded_when_flag_off(self, tmp_path):
        (tmp_path / "SubDir").mkdir()
        (tmp_path / "app.exe").write_text("x", encoding="utf-8")

        with patch.object(FolderScanner, "INCLUDE_FOLDERS", False):
            result = FolderScanner.scan_folder(str(tmp_path))

        types = {s.type for s in result}
        assert ShortcutType.FOLDER not in types
        names = {s.name for s in result}
        assert "SubDir" not in names


# ---------------------------------------------------------------------------
# scan_folder - error handling
# ---------------------------------------------------------------------------


class TestScanFolderErrorHandling:
    """Graceful handling of filesystem errors."""

    def test_permission_denied_returns_empty(self, tmp_path):
        """iterdir raising PermissionError should be caught and return []."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()

        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            result = FolderScanner.scan_folder(str(restricted))

        assert result == []

    def test_os_error_returns_empty(self, tmp_path):
        with patch.object(Path, "iterdir", side_effect=OSError("disk error")):
            result = FolderScanner.scan_folder(str(tmp_path))

        assert result == []


# ---------------------------------------------------------------------------
# Integration-style: real files with no mocks
# ---------------------------------------------------------------------------


class TestScanFolderIntegration:
    """End-to-end with real filesystem, only mocking ShortcutParser for .lnk."""

    def test_full_folder_scan(self, tmp_path):
        # Real exe files
        (tmp_path / "browser.exe").write_text("x", encoding="utf-8")
        (tmp_path / "editor.exe").write_text("x", encoding="utf-8")

        # Real lnk file
        lnk = tmp_path / "docs.lnk"
        lnk.write_text("stub", encoding="utf-8")

        # Real subdirectory
        sub = tmp_path / "Tools"
        sub.mkdir()

        # Excluded file
        (tmp_path / "uninstall.exe").write_text("x", encoding="utf-8")

        # Unsupported file
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

        with patch("core.folder_scanner.ShortcutParser") as mock_parser:
            mock_parser.parse.return_value = {
                "target": r"C:\Docs\viewer.exe",
                "args": "",
                "working_dir": r"C:\Docs",
            }
            result = FolderScanner.scan_folder(str(tmp_path))

        assert len(result) == 4  # 2 exe + 1 lnk + 1 folder

        by_name = {s.name: s for s in result}

        # exe shortcuts
        assert by_name["browser"].type == ShortcutType.FILE
        assert by_name["browser"].target_path == str(tmp_path / "browser.exe")

        assert by_name["editor"].type == ShortcutType.FILE

        # lnk shortcut
        assert by_name["docs"].type == ShortcutType.FILE
        assert by_name["docs"].target_path == r"C:\Docs\viewer.exe"

        # folder
        assert by_name["Tools"].type == ShortcutType.FOLDER
        assert by_name["Tools"].target_path == str(sub)

        # excluded and unsupported must not appear
        assert "uninstall" not in by_name
        assert "notes" not in by_name

    def test_nested_subdirectories_not_scanned(self, tmp_path):
        """scan_folder only iterates top-level; nested dirs appear as folders."""
        outer = tmp_path / "Outer"
        inner = outer / "Inner"
        inner.mkdir(parents=True)
        (outer / "deep.exe").write_text("x", encoding="utf-8")

        result = FolderScanner.scan_folder(str(tmp_path))

        # Only "Outer" folder should appear; Inner and deep.exe are inside Outer
        assert len(result) == 1
        assert result[0].name == "Outer"
        assert result[0].type == ShortcutType.FOLDER
