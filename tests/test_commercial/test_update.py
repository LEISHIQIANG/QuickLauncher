"""测试自动更新模块。"""

import os
import hashlib
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from commercial.update.config import UpdateConfig, UpdateInfo
from commercial.update.checker import UpdateChecker
from commercial.update.downloader import UpdateDownloader
from commercial.update.installer import UpdateInstaller


class TestUpdateConfig:
    def test_defaults(self):
        cfg = UpdateConfig()
        assert cfg.check_interval_hours == 24
        assert cfg.channel == "stable"
        assert not cfg.auto_download
        assert cfg.verify_ssl is True
        assert cfg.require_file_hash is True

    def test_custom(self):
        cfg = UpdateConfig(check_url="http://localhost", check_interval_hours=6)
        assert cfg.check_url == "http://localhost"
        assert cfg.check_interval_hours == 6


class TestUpdateInfo:
    def test_defaults(self):
        info = UpdateInfo()
        assert not info.has_update
        assert info.version == ""

    def test_with_update(self):
        info = UpdateInfo(
            has_update=True,
            version="1.6.0.0",
            download_url="https://example.com/setup.exe",
            file_hash="sha256:abc123",
            file_size=25165824,
            changelog_zh="新版本",
        )
        assert info.has_update
        assert info.version == "1.6.0.0"


class TestUpdateChecker:
    def test_create(self):
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost:18080"))
        assert checker is not None
        assert checker._config.check_url == "http://localhost:18080"

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_no_update(self, mock_get):
        mock_get.return_value = {"has_update": False}
        events = []
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        checker.add_listener(lambda e, d: events.append((e, d)))
        result = checker.check_now()
        assert result is not None
        assert not result.has_update

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_has_update(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "1.6.0.0",
            "release_date": "2026-06-15",
            "changelog": {"zh": "新功能"},
            "download_url": "https://update.quicklauncher.app/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
            "mandatory": False,
        }
        events = []
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        checker.add_listener(lambda e, d: events.append((e, d)))
        result = checker.check_now()
        assert result is not None
        assert result.has_update
        assert result.version == "1.6.0.0"
        update_events = [(e, d) for e, d in events if e == "update_available"]
        assert len(update_events) == 1

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_rejects_missing_hash(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "1.6.0.0",
            "download_url": "https://update.quicklauncher.app/update.exe",
            "file_hash": "",
            "file_size": 1000000,
        }
        events = []
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        checker.add_listener(lambda e, d: events.append((e, d)))

        assert checker.check_now() is None
        assert any(e == "check_failed" and "sha256" in str(d) for e, d in events)

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_rejects_untrusted_host(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "1.6.0.0",
            "download_url": "https://evil.example/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
        }
        events = []
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        checker.add_listener(lambda e, d: events.append((e, d)))

        assert checker.check_now() is None
        assert any(e == "check_failed" and "不受信任" in str(d) for e, d in events)

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_allows_explicit_dev_http(self, mock_get):
        mock_get.return_value = {
            "has_update": True,
            "version": "1.6.0.0",
            "download_url": "http://localhost/update.exe",
            "file_hash": "sha256:" + "a" * 64,
            "file_size": 1000000,
        }
        checker = UpdateChecker(UpdateConfig(
            check_url="http://localhost",
            allow_insecure_update_urls=True,
            allowed_download_hosts=("localhost",),
        ))

        result = checker.check_now()
        assert result is not None
        assert result.has_update

    @patch("commercial.update.checker.ApiClient.get")
    def test_check_now_network_error(self, mock_get):
        from commercial.api.base_client import ApiError
        mock_get.side_effect = ApiError("连接失败")
        events = []
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        checker.add_listener(lambda e, d: events.append((e, d)))
        result = checker.check_now()
        assert result is None
        assert any(e == "check_failed" for e, d in events)

    def test_should_check_no_state_file(self):
        checker = UpdateChecker(UpdateConfig(check_interval_hours=0))
        assert checker._should_check()

    def test_listener_notified(self):
        checker = UpdateChecker(UpdateConfig(check_url="http://localhost"))
        received = []
        checker.add_listener(lambda e, d: received.append((e, d)))
        checker._notify("test_event", {"key": "val"})
        assert len(received) == 1
        assert received[0] == ("test_event", {"key": "val"})


class TestUpdateDownloader:
    def test_create(self):
        dl = UpdateDownloader()
        assert dl is not None

    def test_cancel(self):
        dl = UpdateDownloader()
        dl._cancel_flag = False
        dl.cancel()
        assert dl._cancel_flag

    @patch("commercial.update.downloader.urlopen")
    def test_download_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "11"}
        mock_resp.read.side_effect = [b"hello world", b""]
        mock_urlopen.return_value = mock_resp

        dl = UpdateDownloader()
        events = []
        dl.add_listener(lambda e, d: events.append((e, d)))

        with tempfile.TemporaryDirectory() as tmpdir:
            dl._do_download(
                "http://localhost/test.exe",
                tmpdir,
                "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
                expected_size=11,
                max_bytes=100,
                allowed_hosts=("localhost",),
            )
            finished = [(e, d) for e, d in events if e == "finished"]
            failed = [(e, d) for e, d in events if e == "failed"]
            if failed:
                pytest.fail(f"下载失败: {failed[0][1]}")
            assert len(finished) == 1
            path = finished[0][1]
            assert os.path.isfile(path)
            with open(path, "rb") as f:
                assert f.read() == b"hello world"

    @patch("commercial.update.downloader.urlopen")
    def test_download_hash_mismatch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "5"}
        mock_resp.read.side_effect = [b"hello", b""]
        mock_urlopen.return_value = mock_resp

        dl = UpdateDownloader()
        events = []
        dl.add_listener(lambda e, d: events.append((e, d)))

        with tempfile.TemporaryDirectory() as tmpdir:
            dl._do_download(
                "http://localhost/test.exe", tmpdir,
                "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                allowed_hosts=("localhost",),
            )
            failed_events = [(e, d) for e, d in events if e == "failed"]
            assert len(failed_events) == 1
            assert "哈希校验失败" in str(failed_events[0][1])

    @patch("commercial.update.downloader.urlopen")
    def test_download_cancel(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "1000"}
        mock_resp.read.side_effect = [b"x" * 100, b""]
        mock_urlopen.return_value = mock_resp

        dl = UpdateDownloader()
        events = []
        dl.add_listener(lambda e, d: events.append((e, d)))

        with tempfile.TemporaryDirectory() as tmpdir:
            dl._cancel_flag = True
            dl._do_download("http://localhost/test.exe", tmpdir, None)
            cancelled = [(e, d) for e, d in events if e == "cancelled"]
            assert len(cancelled) == 1

    @patch("commercial.update.downloader.urlopen")
    def test_download_rejects_actual_size_over_limit(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "0"}
        mock_resp.read.side_effect = [b"x" * 101, b""]
        mock_urlopen.return_value = mock_resp

        dl = UpdateDownloader()
        events = []
        dl.add_listener(lambda e, d: events.append((e, d)))

        with tempfile.TemporaryDirectory() as tmpdir:
            dl._do_download(
                "http://localhost/test.exe",
                tmpdir,
                None,
                max_bytes=100,
                allowed_hosts=("localhost",),
            )
            assert any(e == "failed" and "大小" in str(d) for e, d in events)

    @patch("commercial.update.downloader.urlopen")
    def test_download_rejects_size_mismatch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "5"}
        mock_resp.read.side_effect = [b"hello", b""]
        mock_urlopen.return_value = mock_resp

        dl = UpdateDownloader()
        events = []
        dl.add_listener(lambda e, d: events.append((e, d)))

        with tempfile.TemporaryDirectory() as tmpdir:
            dl._do_download(
                "http://localhost/test.exe",
                tmpdir,
                None,
                expected_size=6,
                allowed_hosts=("localhost",),
            )
            assert any(e == "failed" and "大小校验" in str(d) for e, d in events)


class TestUpdateInstaller:
    def test_create(self):
        inst = UpdateInstaller()
        assert inst is not None

    def test_install_file_not_found(self):
        inst = UpdateInstaller()
        events = []
        inst.add_listener(lambda e, d: events.append((e, d)))
        inst.install("C:/nonexistent/installer.exe")
        failed = [(e, d) for e, d in events if e == "failed"]
        assert len(failed) == 1
        assert "不存在" in str(failed[0][1])

    def test_install_rejects_non_exe(self):
        inst = UpdateInstaller()
        events = []
        inst.add_listener(lambda e, d: events.append((e, d)))
        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
            inst.install(f.name)
        assert any(e == "failed" and "类型" in str(d) for e, d in events)

    @patch("commercial.update.installer.sys.exit")
    @patch("commercial.update.installer.subprocess.Popen")
    def test_install_requires_matching_hash_before_popen(self, mock_popen, mock_exit):
        content = b"installer"
        expected_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        inst = UpdateInstaller()

        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            inst.install(path, expected_hash=expected_hash)
        finally:
            os.remove(path)

        mock_popen.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("commercial.update.installer.subprocess.Popen")
    def test_install_rejects_hash_mismatch(self, mock_popen):
        inst = UpdateInstaller()
        events = []
        inst.add_listener(lambda e, d: events.append((e, d)))
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"installer")
            path = f.name
        try:
            inst.install(path, expected_hash="sha256:" + "f" * 64)
        finally:
            os.remove(path)

        mock_popen.assert_not_called()
        assert any(e == "failed" and "哈希" in str(d) for e, d in events)

    def test_listener(self):
        inst = UpdateInstaller()
        received = []
        inst.add_listener(lambda e, d: received.append((e, d)))
        inst._notify("started")
        assert received == [("started", None)]
