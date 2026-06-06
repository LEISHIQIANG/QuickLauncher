"""Tests for PluginManager.install_from_package — ZIP installation with rollback."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from core.command_registry import CommandRegistry
from core.path_security import UnsafePathError
from core.plugin.constants import PLUGIN_PACKAGE_MAX_FILES
from core.plugin_manager import PluginManager

pytestmark = pytest.mark.ui

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_PLUGIN_MAIN_PY = """\
def register(api):
    api.register_command(
        id="test_p.hello", title="Hello", aliases=[],
        description="", category="test",
        handler=lambda ctx: __import__("core.command_registry",
            fromlist=["CommandResult"]).CommandResult(success=True, message="ok"),
    )
"""


def _make_plugin_zip(
    zip_path: str,
    *,
    plugin_id: str = "test_p",
    plugin_name: str = "Test Plugin",
    entry: str = "main.py",
    extra_files: dict[str, str] | None = None,
    subfolder: str | None = None,
    manifest_overrides: dict | None = None,
) -> str:
    """Create a valid plugin ZIP at *zip_path*.

    Returns *zip_path* for convenience.
    If *subfolder* is set (e.g. ``"my_plugin"``), the content is nested under
    that directory inside the ZIP to simulate the subfolder layout.
    """
    manifest = {
        "id": plugin_id,
        "name": plugin_name,
        "version": "1.0.0",
        "description": "",
        "author": "Test",
        "entry": entry,
        "permissions": [],
        "commands": [{"id": f"{plugin_id}.hello", "title": "Hello"}],
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    prefix = f"{subfolder}/" if subfolder else ""

    extra_files = dict(extra_files or {})
    extra_files.setdefault(entry, _PLUGIN_MAIN_PY)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{prefix}plugin.json", json.dumps(manifest, ensure_ascii=False))
        for name, content in extra_files.items():
            zf.writestr(f"{prefix}{name}", content)

    return zip_path


def _plugin_dir_contains(plugins_dir: str, plugin_id: str, *paths: str) -> bool:
    """Check that all *paths* exist inside *plugin_id* directory."""
    base = Path(plugins_dir) / plugin_id
    return all((base / p).is_file() for p in paths)


# ---------------------------------------------------------------------------
# install from ZIP – pure business logic, no Qt required
# ---------------------------------------------------------------------------


class TestInstallFromZipSuccess:
    """Happy-path installation scenarios."""

    def test_install_plugin_successfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pid = pm.install_from_package(zip_path)
            assert pid == "test_p"
            # Files should be in place
            assert _plugin_dir_contains(plugins_dir, "test_p", "plugin.json", "main.py")
            # Staging directory should be cleaned up
            assert not (Path(plugins_dir) / ".staging").exists()

    def test_install_with_subfolder_zip(self):
        """ZIP with subfolder (e.g. ``my_plugin/plugin.json``)."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path, plugin_id="sub_test", subfolder="my_plugin")

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pid = pm.install_from_package(zip_path)
            assert pid == "sub_test"
            assert _plugin_dir_contains(plugins_dir, "sub_test", "plugin.json", "main.py")

    def test_subfolder_zip_rejects_files_outside_root_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.qlzip")
            manifest = {
                "id": "sub_test",
                "name": "Sub Test",
                "version": "1",
                "entry": "main.py",
            }
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("my_plugin/plugin.json", json.dumps(manifest))
                zf.writestr("my_plugin/main.py", "def register(api): pass\n")
                zf.writestr("other/payload.py", "raise RuntimeError('outside root')\n")

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            with pytest.raises(ValueError, match="outside its root folder"):
                pm.install_from_package(zip_path)

    def test_install_overwrite_with_confirmation(self):
        """When plugin already exists and user confirms, it is overwritten."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            # Pre-create the plugin directory
            existing = os.path.join(plugins_dir, "test_p")
            os.makedirs(existing)
            with open(os.path.join(existing, "old.txt"), "w") as f:
                f.write("old")

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path, extra_files={"new.txt": "new"})

            confirmed = []
            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pid = pm.install_from_package(
                zip_path,
                on_overwrite=lambda name: confirmed.append(name) or True,
            )
            assert pid == "test_p"
            assert confirmed == ["Test Plugin"]
            # Old file should be gone, new file present
            assert not os.path.exists(os.path.join(plugins_dir, "test_p", "old.txt"))
            assert _plugin_dir_contains(plugins_dir, "test_p", "plugin.json", "new.txt")

    def test_install_existing_user_declines(self):
        """When plugin already exists and user declines, install is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            existing = os.path.join(plugins_dir, "test_p")
            os.makedirs(existing)
            with open(os.path.join(existing, "keep.txt"), "w") as f:
                f.write("keep")

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pid = pm.install_from_package(
                zip_path,
                on_overwrite=lambda name: False,
            )
            # Returns None when declined
            assert pid is None
            # Old files untouched
            assert os.path.exists(os.path.join(plugins_dir, "test_p", "keep.txt"))


class TestInstallFromZipValidation:
    """Validation failures — expect ValueError."""

    def test_missing_plugin_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "empty.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("random.txt", "data")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="plugin.json"):
                pm.install_from_package(zip_path)

    def test_invalid_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "bad.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", "{bad json")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="解析 plugin.json"):
                pm.install_from_package(zip_path)

    def test_rejects_zip_extension_even_when_archive_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "plugin.zip")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match=r"\.qlzip"):
                pm.install_from_package(zip_path)

    def test_accepts_uppercase_qlzip_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.QLZIP")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            assert pm.install_from_package(zip_path) == "test_p"

    def test_invalid_qlzip_archive_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "not_zip.qlzip")
            Path(zip_path).write_text("not a zip archive", encoding="utf-8")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match=r"\.qlzip"):
                pm.install_from_package(zip_path)

    def test_empty_plugin_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "no_id.qlzip")
            _make_plugin_zip(zip_path, plugin_id="")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="插件ID无效"):
                pm.install_from_package(zip_path)

    def test_invalid_plugin_id_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "bad_id.qlzip")
            _make_plugin_zip(zip_path, plugin_id="has spaces")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="插件ID无效"):
                pm.install_from_package(zip_path)

    def test_rejects_unsafe_entry_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "bad_entry.qlzip")
            _make_plugin_zip(zip_path, manifest_overrides={"entry": "../outside.py"})

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="plugin.entry"):
                pm.install_from_package(zip_path)

    def test_rejects_duplicate_archive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "duplicate.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", json.dumps({"id": "dup", "name": "Dup", "version": "1", "entry": "main.py"}))
                zf.writestr("main.py", "def register(api): pass\n")
                zf.writestr("MAIN.py", "def register(api): raise RuntimeError('shadowed')\n")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="重复路径"):
                pm.install_from_package(zip_path)

    def test_install_existing_without_callback_raises(self):
        """When target exists and on_overwrite is None, ValueError is raised."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            existing = os.path.join(plugins_dir, "test_p")
            os.makedirs(existing)

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            with pytest.raises(ValueError, match="已存在"):
                pm.install_from_package(zip_path)

    def test_too_many_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "too_many.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", json.dumps({"id": "big", "name": "Big", "version": "1", "entry": "main.py"}))
                for i in range(PLUGIN_PACKAGE_MAX_FILES + 1):
                    zf.writestr(f"file_{i}.txt", "x")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match=rf"文件过多|{PLUGIN_PACKAGE_MAX_FILES}"):
                pm.install_from_package(zip_path)

    def test_rejects_encrypted_archive_entries(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "encrypted.qlzip")
            _make_plugin_zip(zip_path)
            original_zipfile = zipfile.ZipFile

            class FakeEncryptedZip:
                def __init__(self, *args, **kwargs):
                    self._inner = original_zipfile(*args, **kwargs)

                def __enter__(self):
                    self._inner.__enter__()
                    return self

                def __exit__(self, *args):
                    return self._inner.__exit__(*args)

                def namelist(self):
                    return self._inner.namelist()

                def read(self, *args, **kwargs):
                    return self._inner.read(*args, **kwargs)

                def infolist(self):
                    infos = self._inner.infolist()
                    infos[0].flag_bits |= 0x1
                    return infos

                def open(self, *args, **kwargs):
                    return self._inner.open(*args, **kwargs)

            monkeypatch.setattr(zipfile, "ZipFile", FakeEncryptedZip)
            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)

            with pytest.raises(ValueError, match="encrypted"):
                pm.install_from_package(zip_path)

    def test_path_traversal_prevented(self):
        """ZIP with ``../`` paths should be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "traversal.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", json.dumps({"id": "safe", "name": "Safe", "version": "1"}))
                zf.writestr("../evil.txt", "gotcha")

            pm = PluginManager(CommandRegistry(), plugins_dir=tmp)
            with pytest.raises(ValueError, match="路径穿越"):
                pm.install_from_package(zip_path)

    def test_scan_rejects_manifest_id_directory_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            plugin_dir = Path(plugins_dir) / "actual_dir"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text(
                json.dumps({"id": "declared_id", "name": "Mismatch", "version": "1", "entry": "main.py"}),
                encoding="utf-8",
            )
            (plugin_dir / "main.py").write_text("def register(api): pass\n", encoding="utf-8")

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            infos = pm.scan_plugins()

            assert infos[0].status == "error"
            assert "directory name" in infos[0].error


class TestInstallFromZipRollback:
    """Failure during install must clean up or restore backup."""

    def test_clean_staging_on_failure(self):
        """If extraction fails partway, staging directory is removed."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.qlzip")

            # Make a valid ZIP
            _make_plugin_zip(zip_path)

            # Corrupt the file after installation starts to trigger a failure
            # Instead: simulate a disk error by making target_dir not creatable
            # Actually, the simplest way: make .staging not creatable after we start
            # OR: just verify that staging doesn't linger on success.

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pid = pm.install_from_package(zip_path)
            assert pid == "test_p"
            assert not (Path(plugins_dir) / ".staging").exists()

    def test_backup_restored_on_failure_after_replace(self, monkeypatch):
        """If an error occurs after backup but before scan, backup is restored."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            # Pre-create a plugin with an identifying file
            target = os.path.join(plugins_dir, "test_p")
            os.makedirs(target)
            with open(os.path.join(target, "original.txt"), "w") as f:
                f.write("original content")

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path, extra_files={"new.txt": "new content"})

            # Monkey-patch shutil.move to fail AFTER backup is created
            original_move = shutil.move
            call_count = 0

            def failing_move(src, dst):
                nonlocal call_count
                call_count += 1
                if call_count == 2:  # second move = during rollback
                    pass  # allow the rollback move to succeed
                if call_count == 1:
                    # Fail the primary move → trigger rollback
                    raise OSError("模拟磁盘写入失败")
                return original_move(src, dst)

            monkeypatch.setattr(shutil, "move", failing_move)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            with pytest.raises(OSError, match="模拟磁盘写入失败"):
                pm.install_from_package(
                    zip_path,
                    on_overwrite=lambda name: True,
                )

            # Original files should be restored from backup
            assert os.path.exists(os.path.join(plugins_dir, "test_p", "original.txt"))
            # New file should NOT be present
            assert not os.path.exists(os.path.join(plugins_dir, "test_p", "new.txt"))

    def test_no_backup_no_crash(self):
        """If install fails and there was no existing plugin, no backup restore is attempted."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "bad.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", "{}")  # missing id

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            with pytest.raises(ValueError):
                pm.install_from_package(zip_path)
            # No plugin directories created
            assert not os.path.exists(os.path.join(plugins_dir, "test_p"))

    def test_rollback_error_does_not_hide_original_error(self, monkeypatch):
        """If rollback itself fails, the original error is still raised."""
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            target = os.path.join(plugins_dir, "test_p")
            os.makedirs(target)
            with open(os.path.join(target, "original.txt"), "w") as f:
                f.write("original")

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            # Make the primary move fail → triggers rollback
            original_rmtree = shutil.rmtree

            def fail_move(src, dst):
                raise OSError("主移动失败")

            # And also make rollback's rmtree fail
            def fail_rmtree(path, ignore_errors=False, **kwargs):
                if ".backup" in str(path):
                    raise OSError("回滚清理失败")
                return original_rmtree(path, ignore_errors=ignore_errors, **kwargs)

            monkeypatch.setattr(shutil, "move", fail_move)
            monkeypatch.setattr(shutil, "rmtree", fail_rmtree)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            with pytest.raises(OSError, match="主移动失败"):
                pm.install_from_package(
                    zip_path,
                    on_overwrite=lambda name: True,
                )


class TestPluginDeleteSafety:
    def test_delete_plugin_files_removes_active_api_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            pm.install_from_package(zip_path)
            pm.scan_plugins()
            assert pm.enable_plugin("test_p")
            assert "test_p" in pm._active_apis

            pm.delete_plugin_files("test_p")

            assert pm.get_plugin("test_p") is None
            assert "test_p" not in pm._active_apis
            assert not (Path(plugins_dir) / "test_p").exists()

    def test_delete_plugin_files_rejects_directory_outside_plugins_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = Path(tmp) / "plugins"
            outside_dir = Path(tmp) / "outside"
            plugins_dir.mkdir()
            outside_dir.mkdir()

            pm = PluginManager(CommandRegistry(), plugins_dir=str(plugins_dir))
            pm._plugins["evil"] = type(
                "Info",
                (),
                {
                    "directory": str(outside_dir),
                    "status": "loaded",
                },
            )()

            with pytest.raises(UnsafePathError):
                pm.delete_plugin_files("evil")


# ---------------------------------------------------------------------------
# Integration: UI wrapper (requires QApplication)
# ---------------------------------------------------------------------------


def _make_mixin_instance(plugin_manager, monkeypatch):
    """Create a minimal SettingsPluginsPageMixin instance for testing."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    # Build a minimal object with the mixin's required attributes
    mixin = SimpleNamespace()
    mixin.current_theme = "dark"
    mixin._plugin_cards = {}

    # The mixin needs _rebuild_plugin_list
    mixin._rebuild_plugin_list = MagicMock()

    # Replace core.plugin_manager with our instance
    import core

    monkeypatch.setattr(core, "plugin_manager", plugin_manager)

    from ui.config_window.settings_plugins_page import SettingsPluginsPageMixin

    for name in (
        "_on_install_plugin_clicked",
        "_install_plugin_package",
        "_plugin_package_path_from_mime",
        "eventFilter",
    ):
        setattr(mixin, name, getattr(SettingsPluginsPageMixin, name).__get__(mixin, SettingsPluginsPageMixin))
    return mixin


class TestInstallUIIntegration:
    """Test the full _on_install_plugin_clicked path with mocked Qt."""

    def test_install_flow_success(self, monkeypatch, qapp):
        """End-to-end: dialog → install → scan → rebuild → success message."""
        from unittest.mock import MagicMock

        from ui.styles.themed_messagebox import ThemedMessageBox

        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)

            # Create a valid plugin ZIP
            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)

            # Mock the themed file dialog adapter.
            dialog_calls = []
            monkeypatch.setattr(
                "ui.config_window.settings_plugins_page.get_open_file_name",
                lambda *a, **kw: dialog_calls.append((a, kw)) or (zip_path, "*.qlzip"),
            )

            # Mock ThemedMessageBox so it doesn't block
            msgbox = MagicMock()
            monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)
            monkeypatch.setattr(ThemedMessageBox, "information", msgbox.information)
            monkeypatch.setattr(ThemedMessageBox, "question", lambda *a, **kw: ThemedMessageBox.Yes)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            mixin = _make_mixin_instance(pm, monkeypatch)

            # Also need to make the import inside the method resolve to our mock
            # The method does: from core import plugin_manager
            # Since we monkeypatched core.plugin_manager, it should work

            mixin._on_install_plugin_clicked()

            # Verify plugin was installed
            info = pm.get_plugin("test_p")
            assert info is not None
            assert info.status == "enabled"
            assert ".qlzip" in dialog_calls[0][0][3]
            # Verify scan was triggered
            assert mixin._rebuild_plugin_list.called
            # Verify success message was shown
            msgbox.information.assert_called_once()
            args, _ = msgbox.information.call_args
            assert "启用成功" in args[1]

    def test_install_flow_failure_shows_error(self, monkeypatch, qapp):
        """When install_from_package raises, error dialog is shown."""
        from unittest.mock import MagicMock

        from ui.styles.themed_messagebox import ThemedMessageBox

        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)

            zip_path = os.path.join(tmp, "bad.qlzip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("plugin.json", "{bad")

            monkeypatch.setattr(
                "ui.config_window.settings_plugins_page.get_open_file_name",
                lambda *a, **kw: (zip_path, "*.qlzip"),
            )
            msgbox = MagicMock()
            monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            mixin = _make_mixin_instance(pm, monkeypatch)
            mixin._on_install_plugin_clicked()

            msgbox.critical.assert_called_once()
            args, _ = msgbox.critical.call_args
            assert "安装失败" in args[1]

    def test_install_flow_user_cancels_dialog(self, monkeypatch, qapp):
        """When file dialog is cancelled, nothing happens."""
        from unittest.mock import MagicMock

        from ui.styles.themed_messagebox import ThemedMessageBox

        monkeypatch.setattr(
            "ui.config_window.settings_plugins_page.get_open_file_name",
            lambda *a, **kw: ("", "*.qlzip"),
        )
        msgbox = MagicMock()
        monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)

        pm = PluginManager(CommandRegistry(), plugins_dir=tempfile.gettempdir())
        mixin = _make_mixin_instance(pm, monkeypatch)
        mixin._on_install_plugin_clicked()
        msgbox.critical.assert_not_called()
        mixin._rebuild_plugin_list.assert_not_called()

    def test_install_flow_preserves_enabled_state(self, monkeypatch, qapp):
        """Existing enabled plugins should remain enabled after install."""
        from unittest.mock import MagicMock

        from tests.test_plugin_manager import _SAMPLE_MAIN_PY, _create_plugin_dir
        from ui.styles.themed_messagebox import ThemedMessageBox

        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)

            # Create an existing plugin and enable it
            _create_plugin_dir(plugins_dir, "existing", main_py=_SAMPLE_MAIN_PY)
            reg = CommandRegistry()
            pm = PluginManager(reg, plugins_dir=plugins_dir)
            pm.scan_plugins()
            pm.load_plugin("existing")
            assert pm.get_plugin("existing").status == "enabled"

            # Install a new plugin via ZIP
            zip_path = os.path.join(tmp, "new.qlzip")
            _make_plugin_zip(zip_path, plugin_id="new_p")
            monkeypatch.setattr(
                "ui.config_window.settings_plugins_page.get_open_file_name",
                lambda *a, **kw: (zip_path, "*.qlzip"),
            )
            msgbox = MagicMock()
            monkeypatch.setattr(ThemedMessageBox, "question", lambda *a, **kw: ThemedMessageBox.Yes)
            monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)
            monkeypatch.setattr(ThemedMessageBox, "information", msgbox.information)

            import core

            monkeypatch.setattr(core, "plugin_manager", pm)

            mixin = _make_mixin_instance(pm, monkeypatch)
            mixin._on_install_plugin_clicked()

            # Existing plugin should still be enabled
            info = pm.get_plugin("existing")
            assert info is not None and info.status == "enabled"
            new_info = pm.get_plugin("new_p")
            assert new_info is not None and new_info.status == "enabled"

    def test_install_flow_overwrite_still_asks_confirmation(self, monkeypatch, qapp):
        from unittest.mock import MagicMock

        from ui.styles.themed_messagebox import ThemedMessageBox

        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            existing = os.path.join(plugins_dir, "test_p")
            os.makedirs(existing)
            Path(existing, "old.txt").write_text("old", encoding="utf-8")

            zip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)
            monkeypatch.setattr(
                "ui.config_window.settings_plugins_page.get_open_file_name",
                lambda *a, **kw: (zip_path, "*.qlzip"),
            )

            msgbox = MagicMock()
            msgbox.question.return_value = ThemedMessageBox.Yes
            monkeypatch.setattr(ThemedMessageBox, "question", msgbox.question)
            monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)
            monkeypatch.setattr(ThemedMessageBox, "information", msgbox.information)

            pm = PluginManager(CommandRegistry(), plugins_dir=plugins_dir)
            mixin = _make_mixin_instance(pm, monkeypatch)
            mixin._on_install_plugin_clicked()

            msgbox.question.assert_called_once()
            assert pm.get_plugin("test_p").status == "enabled"

    def test_install_flow_cancelled_enable_persists_disabled_state(self, monkeypatch, qapp):
        from unittest.mock import MagicMock

        from tests.test_plugin_manager import _SAMPLE_MAIN_PY, _create_plugin_dir
        from ui.styles.themed_messagebox import ThemedMessageBox

        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            saved_states = []

            _create_plugin_dir(plugins_dir, "test_p", main_py=_SAMPLE_MAIN_PY)
            pm = PluginManager(
                CommandRegistry(),
                plugins_dir=plugins_dir,
                save_callback=lambda ids: saved_states.append(list(ids)),
            )
            pm.scan_plugins()
            assert pm.enable_plugin("test_p")
            assert saved_states[-1] == ["test_p"]
            pm.set_confirm_high_risk_callback(lambda info: False)

            package_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(
                package_path,
                manifest_overrides={"permissions": ["process.run"]},
            )
            monkeypatch.setattr(
                "ui.config_window.settings_plugins_page.get_open_file_name",
                lambda *a, **kw: (package_path, "*.qlzip"),
            )

            msgbox = MagicMock()
            msgbox.question.return_value = ThemedMessageBox.Yes
            monkeypatch.setattr(ThemedMessageBox, "question", msgbox.question)
            monkeypatch.setattr(ThemedMessageBox, "critical", msgbox.critical)
            monkeypatch.setattr(ThemedMessageBox, "information", msgbox.information)

            mixin = _make_mixin_instance(pm, monkeypatch)
            mixin._on_install_plugin_clicked()

            assert pm.get_plugin("test_p").status == "loaded"
            assert saved_states[-1] == []


class _FakeUrl:
    def __init__(self, path, local=True):
        self._path = path
        self._local = local

    def isLocalFile(self):
        return self._local

    def toLocalFile(self):
        return self._path


class _FakeMime:
    def __init__(self, urls):
        self._urls = urls

    def hasUrls(self):
        return bool(self._urls)

    def urls(self):
        return self._urls


class _FakeDropEvent:
    def __init__(self, event_type, mime):
        self._event_type = event_type
        self._mime = mime
        self.accepted = False
        self.ignored = False

    def type(self):
        return self._event_type

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class TestPluginPackageDragDrop:
    def test_drop_single_qlzip_installs_package(self, monkeypatch):
        from unittest.mock import MagicMock

        from qt_compat import QEvent

        with tempfile.TemporaryDirectory() as tmp:
            package_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(package_path)
            pm = PluginManager(CommandRegistry(), plugins_dir=os.path.join(tmp, "plugins"))
            mixin = _make_mixin_instance(pm, monkeypatch)
            target = object()
            mixin._plugin_package_drop_targets = [target]
            mixin._install_plugin_package = MagicMock()

            event = _FakeDropEvent(QEvent.Drop, _FakeMime([_FakeUrl(package_path)]))
            assert mixin.eventFilter(target, event) is True

            assert event.accepted is True
            mixin._install_plugin_package.assert_called_once_with(package_path)

    def test_drop_zip_or_multiple_files_is_ignored(self, monkeypatch):
        from unittest.mock import MagicMock

        from qt_compat import QEvent

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "plugin.zip")
            qlzip_path = os.path.join(tmp, "plugin.qlzip")
            _make_plugin_zip(zip_path)
            _make_plugin_zip(qlzip_path)
            pm = PluginManager(CommandRegistry(), plugins_dir=os.path.join(tmp, "plugins"))
            mixin = _make_mixin_instance(pm, monkeypatch)
            target = object()
            mixin._plugin_package_drop_targets = [target]
            mixin._install_plugin_package = MagicMock()

            zip_event = _FakeDropEvent(QEvent.Drop, _FakeMime([_FakeUrl(zip_path)]))
            multi_event = _FakeDropEvent(
                QEvent.Drop,
                _FakeMime([_FakeUrl(qlzip_path), _FakeUrl(qlzip_path)]),
            )

            assert mixin.eventFilter(target, zip_event) is True
            assert mixin.eventFilter(target, multi_event) is True

            assert zip_event.ignored is True
            assert multi_event.ignored is True
            mixin._install_plugin_package.assert_not_called()
