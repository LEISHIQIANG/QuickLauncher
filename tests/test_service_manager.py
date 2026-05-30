"""Tests for core/service_manager.py autostart compatibility facade."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch

import core.service_manager as sm

# ---------------------------------------------------------------------------
# enable_service_autostart
# ---------------------------------------------------------------------------


class TestEnableServiceAutostart:
    def test_success_returns_true_with_method(self):
        with patch("core.auto_start_manager.enable_auto_start", return_value=(True, "task_scheduler")) as mock_en:
            ok, msg = sm.enable_service_autostart()
        assert ok is True
        assert "task_scheduler" in msg
        assert "自启动已启用" in msg
        mock_en.assert_called_once()

    def test_failure_returns_false(self):
        with patch("core.auto_start_manager.enable_auto_start", return_value=(False, "registry")) as mock_en:
            ok, msg = sm.enable_service_autostart()
        assert ok is False
        assert msg == "自启动启用失败"
        mock_en.assert_called_once()

    def test_exception_returns_false_with_detail(self):
        with patch("core.auto_start_manager.enable_auto_start", side_effect=OSError("disk full")):
            ok, msg = sm.enable_service_autostart()
        assert ok is False
        assert "启用失败" in msg
        assert "disk full" in msg


# ---------------------------------------------------------------------------
# disable_service_autostart
# ---------------------------------------------------------------------------


class TestDisableServiceAutostart:
    def test_success_with_legacy_cleanup(self):
        with (
            patch("core.auto_start_manager.disable_auto_start") as mock_dis,
            patch("core.windows_service.is_service_installed", return_value=True),
            patch("core.windows_service.stop_service") as mock_stop,
            patch("core.windows_service.uninstall_service") as mock_uninst,
        ):
            ok, msg = sm.disable_service_autostart()
        assert ok is True
        assert "自启动已禁用" in msg
        mock_dis.assert_called_once()
        mock_stop.assert_called_once()
        mock_uninst.assert_called_once()

    def test_success_without_legacy_service(self):
        with (
            patch("core.auto_start_manager.disable_auto_start") as mock_dis,
            patch("core.windows_service.is_service_installed", return_value=False),
        ):
            ok, msg = sm.disable_service_autostart()
        assert ok is True
        mock_dis.assert_called_once()

    def test_exception_returns_false_with_detail(self):
        with patch("core.auto_start_manager.disable_auto_start", side_effect=RuntimeError("oops")):
            ok, msg = sm.disable_service_autostart()
        assert ok is False
        assert "禁用失败" in msg
        assert "oops" in msg


# ---------------------------------------------------------------------------
# is_service_enabled
# ---------------------------------------------------------------------------


class TestIsServiceEnabled:
    def test_returns_true(self):
        with patch("core.auto_start_manager.is_auto_start_enabled", return_value=True):
            assert sm.is_service_enabled() is True

    def test_returns_false(self):
        with patch("core.auto_start_manager.is_auto_start_enabled", return_value=False):
            assert sm.is_service_enabled() is False

    def test_exception_returns_false(self):
        with patch("core.auto_start_manager.is_auto_start_enabled", side_effect=ImportError("no module")):
            assert sm.is_service_enabled() is False


# ---------------------------------------------------------------------------
# get_autostart_status
# ---------------------------------------------------------------------------


class TestGetAutostartStatus:
    def _full_mock_context(self):
        """Return a stacked patch context for the happy path."""
        import contextlib

        @contextlib.contextmanager
        def ctx():
            with (
                patch(
                    "core.auto_start_manager.get_task_scheduler_check_result", return_value=(True, "task_ok")
                ) as m_task,
                patch("core.auto_start_manager.is_auto_start_enabled", return_value=True) as m_enabled,
                patch("core.auto_start_manager.get_auto_start_method", return_value="task_scheduler") as m_method,
                patch("core.auto_start_manager._read_registry_value", return_value="some_value") as m_reg,
                patch("core.windows_service.is_service_installed", return_value=False) as m_svc_inst,
                patch("core.windows_service.is_service_running", return_value=False) as m_svc_run,
            ):
                yield (m_task, m_enabled, m_method, m_reg, m_svc_inst, m_svc_run)

        return ctx()

    def test_full_success(self):
        with self._full_mock_context():
            status = sm.get_autostart_status()

        assert status["enabled"] is True
        assert status["method"] == "task_scheduler"
        assert status["task_scheduler_enabled"] is True
        assert status["task_scheduler_reason"] == "task_ok"
        assert status["registry_enabled"] is True
        assert status["service_installed"] is False
        assert status["service_running"] is False

    def test_auto_start_manager_failure_graceful(self):
        """When auto_start_manager imports fail, defaults are kept."""
        with patch("core.auto_start_manager.get_task_scheduler_check_result", side_effect=ImportError("no module")):
            status = sm.get_autostart_status()

        assert status["enabled"] is False
        assert status["method"] == "none"
        assert status["task_scheduler_enabled"] is False
        assert status["task_scheduler_reason"] == "not_checked"
        assert status["registry_enabled"] is False

    def test_windows_service_failure_graceful(self):
        """When windows_service imports fail, service fields stay False."""
        with (
            patch("core.auto_start_manager.get_task_scheduler_check_result", return_value=(False, "task_missing")),
            patch("core.auto_start_manager.is_auto_start_enabled", return_value=False),
            patch("core.auto_start_manager.get_auto_start_method", return_value="none"),
            patch("core.auto_start_manager._read_registry_value", return_value=None),
            patch("core.windows_service.is_service_installed", side_effect=ImportError("gone")),
        ):
            status = sm.get_autostart_status()

        assert status["service_installed"] is False
        assert status["service_running"] is False

    def test_with_legacy_service_present(self):
        with (
            patch("core.auto_start_manager.get_task_scheduler_check_result", return_value=(False, "not_configured")),
            patch("core.auto_start_manager.is_auto_start_enabled", return_value=False),
            patch("core.auto_start_manager.get_auto_start_method", return_value="none"),
            patch("core.auto_start_manager._read_registry_value", return_value=None),
            patch("core.windows_service.is_service_installed", return_value=True),
            patch("core.windows_service.is_service_running", return_value=True),
        ):
            status = sm.get_autostart_status()

        assert status["service_installed"] is True
        assert status["service_running"] is True
        assert status["enabled"] is False

    def test_registry_not_set(self):
        with (
            patch("core.auto_start_manager.get_task_scheduler_check_result", return_value=(True, "ok")),
            patch("core.auto_start_manager.is_auto_start_enabled", return_value=True),
            patch("core.auto_start_manager.get_auto_start_method", return_value="task_scheduler"),
            patch("core.auto_start_manager._read_registry_value", return_value=None),
            patch("core.windows_service.is_service_installed", return_value=False),
            patch("core.windows_service.is_service_running", return_value=False),
        ):
            status = sm.get_autostart_status()

        assert status["registry_enabled"] is False
        assert status["enabled"] is True


# ---------------------------------------------------------------------------
# _cleanup_legacy_service
# ---------------------------------------------------------------------------


class TestCleanupLegacyService:
    def test_service_exists_cleans_up(self):
        with (
            patch("core.windows_service.is_service_installed", return_value=True) as m_inst,
            patch("core.windows_service.stop_service") as m_stop,
            patch("core.windows_service.uninstall_service") as m_uninst,
        ):
            sm._cleanup_legacy_service()

        m_inst.assert_called_once()
        m_stop.assert_called_once()
        m_uninst.assert_called_once()

    def test_service_not_installed_noop(self):
        with (
            patch("core.windows_service.is_service_installed", return_value=False) as m_inst,
            patch("core.windows_service.stop_service") as m_stop,
            patch("core.windows_service.uninstall_service") as m_uninst,
        ):
            sm._cleanup_legacy_service()

        m_inst.assert_called_once()
        m_stop.assert_not_called()
        m_uninst.assert_not_called()

    def test_import_failure_graceful(self):
        with patch("core.windows_service.is_service_installed", side_effect=ImportError("no module")):
            # Should not raise
            sm._cleanup_legacy_service()

    def test_stop_service_raises_graceful(self):
        with (
            patch("core.windows_service.is_service_installed", return_value=True),
            patch("core.windows_service.stop_service", side_effect=RuntimeError("access denied")),
        ):
            # Should not raise
            sm._cleanup_legacy_service()
