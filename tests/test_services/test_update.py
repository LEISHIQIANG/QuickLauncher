import hashlib
import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import pytest

from services.update.checker import UpdateChecker
from services.update.config import UpdateConfig
from services.update.downloader import UpdateDownloader
from services.update.installer import UpdateInstaller
from services.update.session import mark_latest_session_first_start_confirmed, write_session_state

TEST_TMP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist", "pytest-tmp"))


def make_temp_dir():
    os.makedirs(TEST_TMP_ROOT, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT)


def make_temp_file(*, suffix: str, delete: bool = True):
    os.makedirs(TEST_TMP_ROOT, exist_ok=True)
    return tempfile.NamedTemporaryFile(suffix=suffix, dir=TEST_TMP_ROOT, delete=delete)


class TestUpdateConfig:
    def test_defaults_use_github_releases(self):
        cfg = UpdateConfig()
        assert cfg.update_source == "github"
        assert cfg.github_repo == "LEISHIQIANG/QuickLauncher"
        assert "api.github.com/repos/LEISHIQIANG/QuickLauncher/releases/latest" in cfg.check_url
        assert cfg.check_interval_hours == 24
        assert cfg.verify_ssl is True

    def test_custom(self):
        cfg = UpdateConfig(update_source="api", check_url="http://localhost", check_interval_hours=6)
        assert cfg.check_url == "http://localhost"
        assert cfg.check_interval_hours == 6


class TestUpdateChecker:
    def test_create(self):
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost:18080"))
        assert checker._config.check_url == "http://localhost:18080"

    @patch("services.update.checker.ApiClient.get")
    def test_check_now_no_update_api(self, mock_get):
        mock_get.return_value = {"has_update": False}
        checker = UpdateChecker(
            UpdateConfig(
                update_source="api",
                check_url="http://localhost",
                allowed_download_hosts=("update.quicklauncher.app",),
            )
        )
        result = checker.check_now()
        assert result is not None
        assert not result.has_update

    @patch("services.update.checker.ApiClient.get")
    def test_check_now_has_update_api(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "9.9.9.9",
            "release_date": "2026-06-15",
            "changelog": {"zh": "新功能"},
            "download_url": "https://update.quicklauncher.app/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
            "mandatory": False,
        }
        events = []
        checker = UpdateChecker(
            UpdateConfig(
                update_source="api",
                check_url="http://localhost",
                allowed_download_hosts=("update.quicklauncher.app",),
            )
        )
        checker.add_listener(lambda event, data: events.append((event, data)))

        result = checker.check_now()

        assert result is not None
        assert result.has_update
        assert result.version == "9.9.9.9"
        assert [event for event, _ in events].count("update_available") == 1

    @patch("services.update.checker.ApiClient.get")
    def test_github_release_update(self, mock_get):
        mock_get.return_value = {
            "tag_name": "v9.9.9.9",
            "published_at": "2026-06-15T00:00:00Z",
            "body": "sha256:" + "b" * 64,
            "assets": [
                {
                    "name": "QuickLauncher_Setup_9.9.9.9.exe",
                    "browser_download_url": "https://github.com/LEISHIQIANG/QuickLauncher/releases/download/v9.9.9.9/QuickLauncher_Setup.exe",
                    "size": 1000000,
                }
            ],
        }
        cfg = UpdateConfig(allowed_download_hosts=("github.com",))
        checker = UpdateChecker(cfg)

        result = checker.check_now()

        assert result is not None
        assert result.has_update
        assert result.version == "9.9.9.9"
        assert result.file_hash == "sha256:" + "b" * 64

    @patch("services.update.checker.ApiClient.get")
    def test_github_release_uses_asset_digest(self, mock_get):
        mock_get.return_value = {
            "tag_name": "v9.9.9.9",
            "assets": [
                {
                    "name": "QuickLauncher_Setup.exe",
                    "browser_download_url": "https://github.com/LEISHIQIANG/QuickLauncher/releases/download/v9.9.9.9/QuickLauncher_Setup.exe",
                    "size": 1000000,
                    "digest": "sha256:" + "c" * 64,
                }
            ],
        }
        checker = UpdateChecker(UpdateConfig(allowed_download_hosts=("github.com",)))

        result = checker.check_now()

        assert result is not None
        assert result.file_hash == "sha256:" + "c" * 64

    def test_default_config_allows_github_release_redirect_hosts(self):
        checker = UpdateChecker(UpdateConfig())

        assert checker._is_allowed_download_host("github.com")
        assert checker._is_allowed_download_host("objects.githubusercontent.com")

    @patch("services.update.checker.ApiClient.get")
    def test_check_now_rejects_missing_hash(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "9.9.9.9",
            "download_url": "https://update.quicklauncher.app/update.exe",
            "file_hash": "",
            "file_size": 1000000,
        }
        events = []
        checker = UpdateChecker(
            UpdateConfig(
                update_source="api",
                check_url="http://localhost",
                allowed_download_hosts=("update.quicklauncher.app",),
            )
        )
        checker.add_listener(lambda event, data: events.append((event, data)))

        assert checker.check_now() is None
        assert any(event == "check_failed" and "sha256" in str(data) for event, data in events)

    @patch("services.update.checker.ApiClient.get")
    def test_check_now_rejects_untrusted_host(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "9.9.9.9",
            "download_url": "https://evil.example/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
        }
        events = []
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost"))
        checker.add_listener(lambda event, data: events.append((event, data)))

        assert checker.check_now() is None
        assert any(event == "check_failed" and "不受信任" in str(data) for event, data in events)

    def test_skip_version(self):
        checker = UpdateChecker(UpdateConfig(check_interval_hours=0))
        state = {}
        checker._load_state = lambda: state
        checker._save_state = lambda data: state.update(data)

        checker.skip_version("9.9.9.9")

        assert checker.is_version_skipped("9.9.9.9")

    @patch("services.update.checker.ApiClient.get")
    def test_check_failure_records_state_for_diagnostics(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")
        state = {}
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost"))
        checker._load_state = lambda: dict(state)
        checker._save_state = lambda data: state.update(data)

        assert checker.check_now() is None

        assert state["last_check_status"] == "failed"
        assert "network down" in state["last_check_error"]

    @patch("services.update.checker.ApiClient.get")
    def test_check_network_error_has_specific_event(self, mock_get):
        from services.api.base_client import ApiError

        mock_get.side_effect = ApiError("Network error: offline")
        events = []
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost"))
        checker.add_listener(lambda event, data: events.append((event, data)))

        assert checker.check_now() is None

        event_names = [event for event, _ in events]
        assert "check_network_error" in event_names
        assert "check_failed" in event_names

    def test_auto_check_timer_stop_sets_cancel_event(self):
        checker = UpdateChecker(UpdateConfig(check_interval_hours=0, check_on_startup=False, repeat_auto_check=True))
        checker._running = True

        checker._schedule_next()
        cancel_event = checker._timer_cancel_event
        timer_thread = checker._timer

        checker.stop()

        assert cancel_event is not None
        assert cancel_event.is_set()
        assert timer_thread is not None
        timer_thread.join(timeout=1.0)
        assert not timer_thread.is_alive()

    @patch("services.update.checker.ApiClient.get")
    def test_check_parse_error_has_specific_event(self, mock_get):
        mock_get.return_value = {"has_update": True, "version": "9.9.9.9", "changelog": []}
        events = []
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost"))
        checker.add_listener(lambda event, data: events.append((event, data)))

        assert checker.check_now() is None

        assert any(event == "check_parse_error" for event, _ in events)

    @patch("services.update.checker.ApiClient.get")
    def test_check_validation_error_has_specific_event(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "9.9.9.9",
            "download_url": "https://evil.example/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
        }
        events = []
        checker = UpdateChecker(UpdateConfig(update_source="api", check_url="http://localhost"))
        checker.add_listener(lambda event, data: events.append((event, data)))

        assert checker.check_now() is None

        assert any(event == "check_validation_error" for event, _ in events)

    def test_state_file_uses_config_root_and_reads_legacy_path(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        legacy_dir = config_root / "config"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / ".update_state.json"
        legacy_file.write_text('{"skipped_version": "9.9.9.9"}', encoding="utf-8")

        with patch("services.update.checker.config_dir", return_value=config_root):
            checker = UpdateChecker(UpdateConfig(check_interval_hours=0))
            assert checker._get_state_file() == os.path.join(config_root, ".update_state.json")
            state = checker._load_state()

        assert state["skipped_version"] == "9.9.9.9"
        assert (config_root / ".update_state.json").exists()


class TestUpdateDownloader:
    def test_cancel(self):
        downloader = UpdateDownloader()
        downloader.cancel()
        assert downloader._cancel_flag

    @patch("services.update.downloader.safe_urlopen")
    def test_download_success(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "11"}
        mock_resp.read.side_effect = [b"hello world", b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        downloader = UpdateDownloader()
        events = []
        downloader.add_listener(lambda event, data: events.append((event, data)))

        with (
            patch("builtins.open", mock_open()),
            patch("services.update.downloader.os.replace") as mock_replace,
            patch("services.update.downloader.os.path.exists", return_value=False),
        ):
            downloader._do_download(
                "http://localhost/test.exe",
                str(tmp_path),
                "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
                expected_size=11,
                max_bytes=100,
                allowed_hosts=("localhost",),
                version="9.9.9.9",
            )
        finished = [(event, data) for event, data in events if event == "finished"]
        failed = [(event, data) for event, data in events if event == "failed"]
        if failed:
            pytest.fail(f"download failed: {failed[0][1]}")
        assert len(finished) == 1
        assert finished[0][1].endswith("test.exe")
        assert os.path.dirname(finished[0][1]) != str(tmp_path)
        session = json.loads((next(tmp_path.glob("*/update_session.json"))).read_text(encoding="utf-8"))
        assert session["version"] == "9.9.9.9"
        assert session["status"] == "downloaded"
        mock_replace.assert_called_once()

    @patch("services.update.downloader.safe_urlopen")
    def test_download_hash_mismatch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "5"}
        mock_resp.read.side_effect = [b"hello", b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        downloader = UpdateDownloader()
        events = []
        downloader.add_listener(lambda event, data: events.append((event, data)))

        with (
            patch("builtins.open", mock_open()),
            patch("services.update.downloader.os.makedirs"),
            patch("services.update.downloader.os.path.exists", return_value=False),
            patch("services.update.session.write_session_state"),
        ):
            downloader._do_download(
                "http://localhost/test.exe",
                "G:/updates",
                "sha256:" + "f" * 64,
                allowed_hosts=("localhost",),
            )

        assert any(event == "failed" and "哈希校验失败" in str(data) for event, data in events)

    @patch("services.update.downloader.safe_urlopen")
    def test_download_rejects_insecure_non_localhost_by_default(self, mock_urlopen, tmp_path):
        downloader = UpdateDownloader()
        events = []
        downloader.add_listener(lambda event, data: events.append((event, data)))

        downloader._do_download(
            "http://update.quicklauncher.app/test.exe",
            str(tmp_path),
            None,
            allowed_hosts=("update.quicklauncher.app",),
        )

        mock_urlopen.assert_not_called()
        assert any(event == "failed" and "HTTPS" in str(data) for event, data in events)

    @patch("services.update.downloader.safe_urlopen")
    def test_download_allows_insecure_http_when_explicitly_configured(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "4"}
        mock_resp.read.side_effect = [b"data", b""]
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        downloader = UpdateDownloader()
        events = []
        downloader.add_listener(lambda event, data: events.append((event, data)))

        downloader._do_download(
            "http://update.quicklauncher.app/test.exe",
            str(tmp_path),
            None,
            max_bytes=10,
            allowed_hosts=("update.quicklauncher.app",),
            allow_insecure_http=True,
        )

        finished = [(event, data) for event, data in events if event == "finished"]
        assert len(finished) == 1
        assert os.path.isfile(finished[0][1])
        with open(finished[0][1], "rb") as handle:
            assert handle.read() == b"data"

    @patch("services.update.downloader._is_allowed_host", side_effect=[True, False])
    @patch("services.update.downloader.safe_urlopen")
    def test_download_rejects_redirect_to_untrusted_host(self, mock_urlopen, _mock_allowed):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "5"}
        mock_resp.geturl.return_value = "https://evil.example/test.exe"
        mock_resp.read.return_value = b""

        class _UrlOpenCtx:
            """Plain context manager that doesn't suppress exceptions (unlike MagicMock whose
            __exit__ may return truthy by default)."""

            def __init__(self, resp):
                self._resp = resp

            def __enter__(self):
                return self._resp

            def __exit__(self, *args):
                return False

        mock_urlopen.return_value = _UrlOpenCtx(mock_resp)
        downloader = UpdateDownloader()
        with (
            patch.object(downloader, "_notify") as mock_notify,
            patch("services.update.downloader.os.makedirs"),
            patch("builtins.open", mock_open()),
            patch("services.update.session.write_session_state"),
        ):
            downloader._do_download(
                "https://github.com/test.exe",
                "G:/updates",
                "sha256:" + "f" * 64,
                allowed_hosts=("github.com",),
            )
            failed_calls = [c for c in mock_notify.call_args_list if c[0][0] == "failed"]
            assert failed_calls, f"_notify('failed', ...) never called. All calls: {mock_notify.call_args_list}"
            assert any("最终下载域名不受信任" in str(c[0][1]) for c in failed_calls)


class TestUpdateInstaller:
    def test_install_file_not_found(self):
        installer = UpdateInstaller()
        events = []
        installer.add_listener(lambda event, data: events.append((event, data)))

        installer.install("C:/nonexistent/installer.exe")

        assert any(event == "failed" and "不存在" in str(data) for event, data in events)

    def test_install_rejects_non_exe(self):
        installer = UpdateInstaller()
        events = []
        installer.add_listener(lambda event, data: events.append((event, data)))

        with make_temp_file(suffix=".txt") as handle:
            installer.install(handle.name)

        assert any(event == "failed" and "类型" in str(data) for event, data in events)

    @patch("services.update.installer.sys.exit")
    @patch("services.update.installer.subprocess.Popen")
    def test_install_requires_matching_hash_before_popen(self, mock_popen, mock_exit):
        content = b"installer"
        expected_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        installer = UpdateInstaller()

        path = "G:/updates/QuickLauncher_Setup.exe"
        with (
            patch("services.update.installer.os.path.isfile", return_value=True),
            patch("builtins.open", mock_open(read_data=content)),
        ):
            installer.install(path, expected_hash=expected_hash)

        mock_popen.assert_called_once()
        popen_kwargs = mock_popen.call_args.kwargs
        assert popen_kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert popen_kwargs["creationflags"] & subprocess.DETACHED_PROCESS
        assert popen_kwargs["creationflags"] & 0x01000000
        assert popen_kwargs["close_fds"] is True
        mock_exit.assert_called_once_with(0)

    @patch("services.update.installer.sys.exit")
    @patch("services.update.installer.subprocess.Popen")
    def test_install_records_session_and_creates_preinstall_backup(self, mock_popen, mock_exit, tmp_path):
        session_dir = tmp_path / "downloads" / "updates" / "session-1"
        session_dir.mkdir(parents=True)
        installer_path = session_dir / "QuickLauncher_Setup.exe"
        content = b"installer"
        installer_path.write_bytes(content)
        write_session_state(
            session_dir,
            {
                "schema": 1,
                "session_id": "session-1",
                "status": "downloaded",
                "install": {"status": "pending"},
                "first_start": {"confirmed": False},
            },
        )
        expected_hash = "sha256:" + hashlib.sha256(content).hexdigest()

        class Manager:
            def backup_full_config(self, save_path):
                assert save_path.endswith("pre_install_config_backup.zip")
                return True

        installer = UpdateInstaller()
        installer.install(
            str(installer_path),
            expected_hash=expected_hash,
            trusted_dir=str(tmp_path / "downloads" / "updates"),
            data_manager=Manager(),
        )

        mock_popen.assert_called_once()
        mock_exit.assert_called_once_with(0)
        session = json.loads((session_dir / "update_session.json").read_text(encoding="utf-8"))
        assert session["status"] == "installing"
        assert session["install"]["status"] == "started"
        assert session["install"]["pre_install_backup"].endswith("pre_install_config_backup.zip")
        assert session["install"]["log_path"].endswith("update_install.log")

    def test_mark_latest_session_first_start_confirmed(self, tmp_path):
        session_dir = tmp_path / "session-1"
        session_dir.mkdir()
        write_session_state(
            session_dir,
            {
                "schema": 1,
                "session_id": "session-1",
                "status": "installing",
                "install": {"status": "started"},
                "first_start": {"confirmed": False},
            },
        )

        state = mark_latest_session_first_start_confirmed(tmp_path)

        assert state["status"] == "first_start_confirmed"
        assert state["first_start"]["confirmed"] is True

    @patch("services.update.installer.subprocess.Popen")
    def test_install_rejects_hash_mismatch(self, mock_popen):
        installer = UpdateInstaller()
        events = []
        installer.add_listener(lambda event, data: events.append((event, data)))
        path = "G:/updates/QuickLauncher_Setup.exe"
        with (
            patch("services.update.installer.os.path.isfile", return_value=True),
            patch("builtins.open", mock_open(read_data=b"installer")),
        ):
            installer.install(path, expected_hash="sha256:" + "f" * 64)

        mock_popen.assert_not_called()
        assert any(event == "failed" and "哈希" in str(data) for event, data in events)

    @patch("services.update.installer.subprocess.Popen")
    def test_install_rejects_untrusted_directory(self, mock_popen, tmp_path):
        installer = UpdateInstaller()
        events = []
        installer.add_listener(lambda event, data: events.append((event, data)))
        trusted = tmp_path / "downloads"
        outside = tmp_path / "outside"
        trusted.mkdir()
        outside.mkdir()
        path = outside / "QuickLauncher_Setup.exe"
        path.write_bytes(b"installer")

        installer.install(str(path), trusted_dir=str(trusted))

        mock_popen.assert_not_called()
        assert any(event == "failed" and "可信下载目录" in str(data) for event, data in events)

    @patch("services.update.installer.subprocess.Popen")
    def test_install_rejects_symlink_installer(self, mock_popen, tmp_path):
        installer = UpdateInstaller()
        events = []
        installer.add_listener(lambda event, data: events.append((event, data)))
        link = tmp_path / "link.exe"

        with (
            patch("services.update.installer.os.path.isfile", return_value=True),
            patch("services.update.installer.os.path.islink", return_value=True),
        ):
            installer.install(str(link))

        mock_popen.assert_not_called()
        assert any(event == "failed" and "symlink" in str(data) for event, data in events)
