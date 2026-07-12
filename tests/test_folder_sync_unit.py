"""Tests for folder_sync.py helper functions and sync logic."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


class TestGetFolderSyncStatus:
    def test_empty_initially(self):
        from core.folder_sync import _last_sync_status, get_folder_sync_status

        _last_sync_status.clear()
        result = get_folder_sync_status()
        assert result == {}

    def test_specific_folder_missing(self):
        from core.folder_sync import _last_sync_status, get_folder_sync_status

        _last_sync_status.clear()
        result = get_folder_sync_status("nonexistent")
        assert result == {}

    def test_returns_copy(self):
        from core.folder_sync import _last_sync_status, get_folder_sync_status

        _last_sync_status.clear()
        _last_sync_status["f1"] = {"ok": True, "added": 5, "timestamp": time.time()}
        result = get_folder_sync_status("f1")
        assert result["ok"] is True
        assert result["added"] == 5
        # Modifying the returned dict shouldn't affect the internal state
        result["ok"] = False
        assert _last_sync_status["f1"]["ok"] is True

    def test_all_folders(self):
        from core.folder_sync import _last_sync_status, get_folder_sync_status

        _last_sync_status.clear()
        _last_sync_status["f1"] = {"ok": True, "timestamp": time.time()}
        _last_sync_status["f2"] = {"ok": False, "timestamp": time.time()}
        result = get_folder_sync_status()
        assert "f1" in result
        assert "f2" in result


class TestSetSyncStatus:
    def test_creates_entry(self):
        from core.folder_sync import _last_sync_status, _set_sync_status

        _last_sync_status.clear()
        _set_sync_status("folder1", ok=True, added=3, removed=0)
        assert "folder1" in _last_sync_status
        assert _last_sync_status["folder1"]["ok"] is True
        assert _last_sync_status["folder1"]["added"] == 3
        assert "timestamp" in _last_sync_status["folder1"]

    def test_updates_existing(self):
        from core.folder_sync import _last_sync_status, _set_sync_status

        _last_sync_status.clear()
        _set_sync_status("folder1", ok=True, added=3)
        _set_sync_status("folder1", ok=False, reason="error")
        assert _last_sync_status["folder1"]["ok"] is False
        assert _last_sync_status["folder1"]["reason"] == "error"
        # 'added' from previous call should still be there (update, not replace)
        assert _last_sync_status["folder1"]["added"] == 3


class TestSyncFolder:
    def _make_data_manager(self, folder=None):
        dm = MagicMock()
        dm.data.get_folder_by_id.return_value = folder
        dm.batch_update.return_value.__enter__ = MagicMock()
        dm.batch_update.return_value.__exit__ = MagicMock(return_value=False)
        return dm

    def test_folder_not_found(self):
        from core.folder_sync import _last_sync_status, sync_folder

        _last_sync_status.clear()
        dm = self._make_data_manager(folder=None)
        added, removed = sync_folder(dm, "nonexistent")
        assert added == 0
        assert removed == 0
        assert _last_sync_status["nonexistent"]["reason"] == "folder_not_linked"

    def test_folder_no_linked_path(self):
        from core.folder_sync import _last_sync_status, sync_folder

        _last_sync_status.clear()
        folder = MagicMock()
        folder.linked_path = None
        dm = self._make_data_manager(folder=folder)
        added, removed = sync_folder(dm, "f1")
        assert added == 0
        assert removed == 0

    def test_linked_path_not_directory(self, tmp_path):
        from core.folder_sync import _last_sync_status, sync_folder

        _last_sync_status.clear()
        fake_path = tmp_path / "nonexistent_dir"
        folder = MagicMock()
        folder.linked_path = str(fake_path)
        dm = self._make_data_manager(folder=folder)
        added, removed = sync_folder(dm, "f1")
        assert added == 0
        assert removed == 0
        assert _last_sync_status["f1"]["reason"] == "linked_path_missing"

    def test_scan_adds_new_items(self, tmp_path):
        from core.data_models import ShortcutItem, ShortcutType
        from core.folder_sync import _last_sync_status, sync_folder

        _last_sync_status.clear()

        # Create actual files in tmp_path
        (tmp_path / "app.exe").write_text("x")

        folder = MagicMock()
        folder.linked_path = str(tmp_path)
        folder.items = []  # No existing items
        folder.last_sync_time = 0.0

        dm = self._make_data_manager(folder=folder)

        with patch("core.folder_sync.FolderScanner") as mock_scanner:
            sc = ShortcutItem()
            sc.id = "1"
            sc.name = "app"
            sc.target_path = str(tmp_path / "app.exe")
            sc.type = ShortcutType.FILE
            mock_scanner.scan_folder.return_value = [sc]

            added, removed = sync_folder(dm, "f1")

        assert added == 1
        assert removed == 0
        dm.add_shortcuts.assert_called_once()
        dm.save.assert_called_once()

    def test_scan_removes_missing_items(self, tmp_path):
        from core.data_models import ShortcutItem, ShortcutType
        from core.folder_sync import _last_sync_status, sync_folder

        _last_sync_status.clear()

        existing = ShortcutItem()
        existing.id = "old1"
        existing.name = "old"
        existing.target_path = str(tmp_path / "old.exe")
        existing.type = ShortcutType.FILE

        folder = MagicMock()
        folder.linked_path = str(tmp_path)
        folder.items = [existing]
        folder.last_sync_time = 0.0

        dm = self._make_data_manager(folder=folder)

        with patch("core.folder_sync.FolderScanner") as mock_scanner:
            mock_scanner.scan_folder.return_value = []  # Empty scan
            added, removed = sync_folder(dm, "f1")

        assert added == 0
        assert removed == 1
        dm.delete_shortcut.assert_called_once_with("f1", "old1")
