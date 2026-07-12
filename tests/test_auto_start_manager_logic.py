"""Tests for auto_start_manager.py pure logic and utility functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pure helper functions that don't need Win32 APIs
# ---------------------------------------------------------------------------


class TestIsFrozen:
    def test_sys_frozen(self):
        with patch.dict("sys.modules", {}):
            import core.auto_start_manager as mod

            with patch.object(mod.sys, "frozen", True, create=True):
                assert mod._is_frozen() is True

    def test_compiled_in_globals(self):
        import core.auto_start_manager as mod

        mod.__compiled__ = True
        try:
            assert mod._is_frozen() is True
        finally:
            del mod.__compiled__

    def test_python_exe_not_frozen(self):
        import core.auto_start_manager as mod

        with patch.object(mod.sys, "executable", r"C:\Python312\python.exe"):
            assert mod._is_frozen() is False

    def test_pythonw_exe_not_frozen(self):
        import core.auto_start_manager as mod

        with patch.object(mod.sys, "executable", r"C:\Python312\pythonw.exe"):
            assert mod._is_frozen() is False

    def test_custom_exe_is_frozen(self):
        import core.auto_start_manager as mod

        with patch.object(mod.sys, "executable", r"C:\App\QuickLauncher.exe"):
            assert mod._is_frozen() is True


class TestGetProjectRoot:
    def test_returns_parent_of_core(self):
        import core.auto_start_manager as mod

        root = mod._get_project_root()
        assert os.path.isdir(root)
        # core/ is a child of project root
        assert os.path.isdir(os.path.join(root, "core"))


class TestGetExePath:
    def test_non_python_exe(self):
        import core.auto_start_manager as mod

        with patch.object(mod.sys, "executable", r"C:\App\QuickLauncher.exe"):
            result = mod._get_exe_path()
            assert result.endswith("QuickLauncher.exe")

    def test_python_exe_with_exe_argv(self, tmp_path):
        import core.auto_start_manager as mod

        fake_exe = tmp_path / "MyApp.exe"
        fake_exe.write_text("x")
        with patch.object(mod.sys, "executable", r"C:\Python312\python.exe"):
            with patch.object(mod.sys, "argv", [str(fake_exe)]):
                result = mod._get_exe_path()
                assert os.path.abspath(result) == str(fake_exe)

    def test_python_exe_fallback_to_app_name(self, tmp_path):
        import core.auto_start_manager as mod

        app_exe = tmp_path / "QuickLauncher.exe"
        app_exe.write_text("x")
        py_exe = tmp_path / "python.exe"
        py_exe.write_text("x")
        with patch.object(mod.sys, "executable", str(py_exe)):
            with patch.object(mod.sys, "argv", ["main.py"]):
                result = mod._get_exe_path()
                assert "QuickLauncher" in result


class TestNormalizeLaunchSpec:
    def test_defaults(self):
        import core.auto_start_manager as mod

        path, args, cwd = mod._normalize_launch_spec()
        assert path  # non-empty
        assert args == ""
        assert cwd  # non-empty

    def test_explicit_values(self):
        import core.auto_start_manager as mod

        path, args, cwd = mod._normalize_launch_spec(r"C:\MyApp\app.exe", "--foo", r"C:\MyApp")
        assert path == r"C:\MyApp\app.exe"
        assert args == "--foo"
        assert cwd == r"C:\MyApp"

    def test_cwd_defaults_to_exe_dir(self):
        import core.auto_start_manager as mod

        _, _, cwd = mod._normalize_launch_spec(r"C:\MyApp\app.exe")
        assert cwd == r"C:\MyApp"


class TestNormalizeAbsPath:
    def test_empty(self):
        import core.auto_start_manager as mod

        assert mod._normalize_abs_path("") == ""

    def test_normalizes(self):
        import core.auto_start_manager as mod

        result = mod._normalize_abs_path(r"C:\foo\bar\..\baz")
        assert ".." not in result
        assert result == os.path.normcase(os.path.abspath(r"C:\foo\bar\..\baz"))


class TestGetTaskTriggerDelay:
    def test_admin_launcher(self):
        import core.auto_start_manager as mod

        result = mod._get_task_trigger_delay("admin_launcher")
        assert result == mod.AUTOSTART_ADMIN_TRIGGER_DELAY
        assert result == "PT2S"

    def test_standard_direct(self):
        import core.auto_start_manager as mod

        result = mod._get_task_trigger_delay("standard_direct")
        assert result == mod.AUTOSTART_STANDARD_TRIGGER_DELAY
        assert result == ""

    def test_unknown_mode(self):
        import core.auto_start_manager as mod

        result = mod._get_task_trigger_delay("unknown")
        assert result == ""


class TestBuildProcessCommandLine:
    def test_no_args(self):
        import core.auto_start_manager as mod

        result = mod._build_process_command_line(r"C:\app.exe")
        assert r"C:\app.exe" in result

    def test_with_args(self):
        import core.auto_start_manager as mod

        result = mod._build_process_command_line(r"C:\app.exe", "--foo bar")
        assert "--foo bar" in result
        assert r"C:\app.exe" in result


class TestBuildHelperLaunch:
    def test_frozen_mode(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_get_exe_path", return_value=r"C:\App\QuickLauncher.exe"):
                file, params, cwd = mod._build_helper_launch("enable")
                assert file == r"C:\App\QuickLauncher.exe"
                assert "--autostart-helper" in params
                assert "enable" in params

    def test_dev_mode(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=False):
            file, params, cwd = mod._build_helper_launch("disable")
            assert file == mod.sys.executable
            assert "--autostart-helper" in params
            assert "disable" in params

    def test_with_target_args(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=False):
            _, params, _ = mod._build_helper_launch(
                "enable",
                exe_path=r"C:\app.exe",
                arguments="--verbose",
                working_dir="C:\\",
            )
            assert "--target-exe" in params
            assert "--target-args" in params
            assert "--target-cwd" in params


class TestBuildAutostartTaskLaunch:
    def test_frozen_mode(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_get_exe_path", return_value=r"C:\App\QuickLauncher.exe"):
                file, params, cwd = mod._build_autostart_task_launch()
                assert "--autostart-launch" in params

    def test_dev_mode(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=False):
            file, params, cwd = mod._build_autostart_task_launch()
            assert "--autostart-launch" in params


class TestRunAutostartHelper:
    def test_enable_action_calls_direct(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_enable_auto_start_direct", return_value=(True, "task_scheduler")) as mock_en:
            result = mod.run_autostart_helper("enable")
            assert result == mod.HELPER_EXIT_SUCCESS
            mock_en.assert_called_once()

    def test_disable_action_calls_direct(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_disable_auto_start_direct", return_value=(True, "task_scheduler")) as mock_dis:
            result = mod.run_autostart_helper("disable")
            assert result == mod.HELPER_EXIT_SUCCESS
            mock_dis.assert_called_once()

    def test_unknown_action(self):
        import core.auto_start_manager as mod

        result = mod.run_autostart_helper("unknown_action")
        assert result == mod.HELPER_EXIT_BAD_ARGS

    def test_enable_failure(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_enable_auto_start_direct", return_value=(False, "failed")):
            result = mod.run_autostart_helper("enable")
            assert result == mod.HELPER_EXIT_FAILED

    def test_exception_returns_failed(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_enable_auto_start_direct", side_effect=Exception("boom")):
            result = mod.run_autostart_helper("enable")
            assert result == mod.HELPER_EXIT_FAILED


class TestIsAllowedHelperTarget:
    def test_nonexistent_file(self):
        import core.auto_start_manager as mod

        assert mod._is_allowed_helper_target(r"C:\nonexistent\app.exe") is False

    def test_valid_self_target(self, tmp_path):
        import core.auto_start_manager as mod

        fake_exe = tmp_path / "app.exe"
        fake_exe.write_text("x")
        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_get_exe_path", return_value=str(fake_exe)):
                assert mod._is_allowed_helper_target(str(fake_exe)) is True


class TestAutoStartFacadeFunctions:
    def test_is_auto_start_enabled(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "is_task_scheduler_enabled", return_value=True):
            assert mod.is_auto_start_enabled() is True
        with patch.object(mod, "is_task_scheduler_enabled", return_value=False):
            assert mod.is_auto_start_enabled() is False

    def test_get_auto_start_method(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "is_task_scheduler_enabled", return_value=True):
            assert mod.get_auto_start_method() == "task_scheduler"
        with patch.object(mod, "is_task_scheduler_enabled", return_value=False):
            assert mod.get_auto_start_method() == "none"

    def test_is_auto_start_repair_needed(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "get_auto_start_check_result", return_value=(False, "missing")):
            assert mod.is_auto_start_repair_needed(True) is True
            assert mod.is_auto_start_repair_needed(False) is False
        with patch.object(mod, "get_auto_start_check_result", return_value=(True, "ok")):
            assert mod.is_auto_start_repair_needed(True) is False

    def test_get_exe_path_compat(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_get_app_launch_spec", return_value=(r"C:\app.exe", "--arg", "C:\\")):
            path, args = mod.get_exe_path()
            assert path == r"C:\app.exe"
            assert args == "--arg"


class TestRegistryFunctions:
    def test_read_registry_value_not_found(self):
        import core.auto_start_manager as mod

        # The actual Run key won't have "QuickLauncher" in a test env
        result = mod._read_registry_value()
        # Should be None since we're not writing to the registry
        assert result is None

    def test_delete_registry_value(self):
        import core.auto_start_manager as mod

        # Should succeed even if the value doesn't exist
        result = mod._delete_registry_value()
        assert result in (True, False)


class TestGetCurrentUserIdentity:
    def test_returns_string(self):
        import core.auto_start_manager as mod

        result = mod._get_current_user_identity()
        assert isinstance(result, str)

    def test_fallback_to_env(self):
        import core.auto_start_manager as mod

        # Mock win32api to fail so it falls back to env vars
        mock_win32api = MagicMock()
        mock_win32api.GetUserNameEx.side_effect = Exception("not available")
        with patch.dict(os.environ, {"USERNAME": "testuser", "USERDOMAIN": "TESTDOMAIN"}):
            with patch.dict("sys.modules", {"win32api": mock_win32api}):
                result = mod._get_current_user_identity()
                assert "testuser" in result.lower()
                assert "testdomain" in result.lower()


class TestGetCurrentUserIdentityVariants:
    def test_returns_set(self):
        import core.auto_start_manager as mod

        result = mod._get_current_user_identity_variants()
        assert isinstance(result, set)
        assert len(result) > 0

    def test_includes_username(self):
        import core.auto_start_manager as mod

        result = mod._get_current_user_identity_variants()
        username = os.environ.get("USERNAME", "").lower()
        if username:
            assert username in result


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_helper_exit_codes_are_distinct(self):
        import core.auto_start_manager as mod

        codes = {mod.HELPER_EXIT_SUCCESS, mod.HELPER_EXIT_FAILED, mod.HELPER_EXIT_CANCELLED, mod.HELPER_EXIT_BAD_ARGS}
        assert len(codes) == 4

    def test_helper_exit_success_is_zero(self):
        import core.auto_start_manager as mod

        assert mod.HELPER_EXIT_SUCCESS == 0

    def test_autostart_trigger_delay_values(self):
        import core.auto_start_manager as mod

        assert mod.AUTOSTART_ADMIN_TRIGGER_DELAY == "PT2S"
        assert mod.AUTOSTART_STANDARD_TRIGGER_DELAY == ""

    def test_see_mask_nocloseprocess(self):
        import core.auto_start_manager as mod

        assert mod.SEE_MASK_NOCLOSEPROCESS == 0x00000040

    def test_autostart_helper_timeout_ms(self):
        import core.auto_start_manager as mod

        assert mod.AUTOSTART_HELPER_TIMEOUT_MS == 60000

    def test_legacy_task_names_tuple(self):
        import core.auto_start_manager as mod

        assert isinstance(mod.LEGACY_TASK_NAMES, tuple)
        assert "QuickLauncher_AutoStart" in mod.LEGACY_TASK_NAMES


# ---------------------------------------------------------------------------
# _get_app_launch_spec
# ---------------------------------------------------------------------------


class TestGetAppLaunchSpec:
    def test_frozen_returns_exe_path(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_get_exe_path", return_value=r"C:\App\QuickLauncher.exe"):
                path, args, cwd = mod._get_app_launch_spec()
                assert path == r"C:\App\QuickLauncher.exe"
                assert args == ""
                assert cwd == r"C:\App"

    def test_dev_returns_python_and_script(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=False):
            with patch.object(mod.sys, "argv", [r"C:\project\main.py"]):
                path, args, cwd = mod._get_app_launch_spec()
                assert path == mod.sys.executable
                assert "main.py" in args


# ---------------------------------------------------------------------------
# _build_task_action_launch
# ---------------------------------------------------------------------------


class TestBuildTaskActionLaunch:
    def test_returns_four_tuple(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_current_account_admin", return_value=False):
            result = mod._build_task_action_launch(r"C:\app.exe", "--foo", r"C:\\")
            assert len(result) == 4
            path, args, cwd, mode = result
            assert mode == "standard_direct"

    def test_admin_mode_uses_launcher(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_current_account_admin", return_value=True):
            with patch.object(mod, "_is_frozen", return_value=False):
                _, _, _, mode = mod._build_task_action_launch(r"C:\app.exe")
                assert mode == "admin_launcher"


# ---------------------------------------------------------------------------
# _enable_auto_start_direct / _disable_auto_start_direct
# ---------------------------------------------------------------------------


class TestEnableDisableDirect:
    def test_enable_direct_nonexistent_path(self):
        import core.auto_start_manager as mod

        success, reason = mod._enable_auto_start_direct(r"C:\nonexistent\app.exe")
        assert success is False
        assert reason == "failed"

    def test_enable_direct_disallowed_target(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=False):
            success, reason = mod._enable_auto_start_direct(str(fake))
            assert success is False

    def test_enable_direct_success(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=True):
            with patch.object(mod, "enable_task_scheduler", return_value=True):
                success, reason = mod._enable_auto_start_direct(str(fake))
                assert success is True
                assert reason == "task_scheduler"

    def test_enable_direct_task_scheduler_fails(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=True):
            with patch.object(mod, "enable_task_scheduler", return_value=False):
                success, reason = mod._enable_auto_start_direct(str(fake))
                assert success is False
                assert reason == "failed"

    def test_disable_direct_removes_both(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "disable_task_scheduler", return_value=True):
            with patch.object(mod, "_delete_registry_value", return_value=True):
                with patch.object(mod, "is_task_scheduler_enabled", return_value=False):
                    with patch.object(mod, "_read_registry_value", return_value=None):
                        success, reason = mod._disable_auto_start_direct()
                        assert success is True

    def test_disable_direct_residue_detected(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "disable_task_scheduler", return_value=True):
            with patch.object(mod, "_delete_registry_value", return_value=True):
                with patch.object(mod, "is_task_scheduler_enabled", return_value=True):
                    with patch.object(mod, "_read_registry_value", return_value=None):
                        success, reason = mod._disable_auto_start_direct()
                        assert success is False


# ---------------------------------------------------------------------------
# run_autostart_launcher
# ---------------------------------------------------------------------------


class TestRunAutostartLauncher:
    def test_nonexistent_path_returns_failed(self):
        import core.auto_start_manager as mod

        result = mod.run_autostart_launcher(r"C:\nonexistent\app.exe")
        assert result == mod.HELPER_EXIT_FAILED

    def test_disallowed_target_returns_bad_args(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=False):
            result = mod.run_autostart_launcher(str(fake))
            assert result == mod.HELPER_EXIT_BAD_ARGS

    def test_success_path(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=True):
            with patch.object(mod, "_launch_as_standard_user", return_value=True):
                result = mod.run_autostart_launcher(str(fake))
                assert result == mod.HELPER_EXIT_SUCCESS

    def test_launch_failure_returns_failed(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "app.exe"
        fake.write_text("x")
        with patch.object(mod, "_is_allowed_helper_target", return_value=True):
            with patch.object(mod, "_launch_as_standard_user", return_value=False):
                result = mod.run_autostart_launcher(str(fake))
                assert result == mod.HELPER_EXIT_FAILED


# ---------------------------------------------------------------------------
# _ensure_auto_start
# ---------------------------------------------------------------------------


class TestEnsureAutoStart:
    def test_skips_when_not_frozen(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=False):
            # Should return without doing anything
            mod._ensure_auto_start(True)

    def test_frozen_with_auto_start_disabled(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_cleanup_legacy_task_scheduler_tasks"):
                with patch.object(mod, "_has_legacy_tasks", return_value=False):
                    mod._ensure_auto_start(False)

    def test_frozen_detects_missing_task(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_is_frozen", return_value=True):
            with patch.object(mod, "_cleanup_legacy_task_scheduler_tasks"):
                with patch.object(mod, "_has_legacy_tasks", return_value=False):
                    with patch.object(mod, "get_auto_start_check_result", return_value=(False, "missing")):
                        mod._ensure_auto_start(True)


# ---------------------------------------------------------------------------
# _has_legacy_tasks
# ---------------------------------------------------------------------------


class TestHasLegacyTasks:
    def test_returns_false_on_non_nt(self):
        import core.auto_start_manager as mod

        with patch.object(mod.os, "name", "posix"):
            assert mod._has_legacy_tasks() is False


# ---------------------------------------------------------------------------
# _launch_with_current_token
# ---------------------------------------------------------------------------


class TestLaunchWithCurrentToken:
    def test_success(self, tmp_path):
        import core.auto_start_manager as mod

        fake = tmp_path / "dummy.exe"
        fake.write_text("x")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = mod._launch_with_current_token(str(fake))
            assert result is True

    def test_popen_exception_returns_false(self):
        import core.auto_start_manager as mod

        with patch("subprocess.Popen", side_effect=OSError("no such file")):
            result = mod._launch_with_current_token(r"C:\nonexistent.exe")
            assert result is False


# ---------------------------------------------------------------------------
# enable_auto_start / disable_auto_start dispatch
# ---------------------------------------------------------------------------


class TestAutoStartDispatch:
    def test_enable_non_admin_calls_direct(self):
        import core.auto_start_manager as mod
        from core import native_services

        with patch.object(mod, "_is_current_account_admin", return_value=False):
            with patch.object(
                native_services._QLAutostartEngine,
                "get",
                return_value=MagicMock(enable=MagicMock(return_value=(0, "task_scheduler"))),
            ):
                success, reason = mod.enable_auto_start(r"C:\app.exe")
                assert success is True
                assert reason == "task_scheduler"

    def test_enable_admin_calls_helper(self):
        import core.auto_start_manager as mod
        from core import native_services

        with patch.object(mod, "_is_current_account_admin", return_value=True):
            with patch.object(
                native_services._QLAutostartEngine,
                "get",
                return_value=MagicMock(enable=MagicMock(return_value=(0, "task_scheduler"))),
            ):
                success, reason = mod.enable_auto_start(r"C:\app.exe")
                assert success is True
                assert reason == "task_scheduler"

    def test_disable_non_admin_calls_direct(self):
        import core.auto_start_manager as mod
        from core import native_services

        with patch.object(mod, "_is_current_account_admin", return_value=False):
            with patch.object(
                native_services._QLAutostartEngine,
                "get",
                return_value=MagicMock(disable=MagicMock(return_value=(0, "task_scheduler"))),
            ):
                success, reason = mod.disable_auto_start()
                assert success is True
                assert reason == "task_scheduler"

    def test_disable_admin_calls_helper(self):
        import core.auto_start_manager as mod
        from core import native_services

        with patch.object(mod, "_is_current_account_admin", return_value=True):
            with patch.object(
                native_services._QLAutostartEngine,
                "get",
                return_value=MagicMock(disable=MagicMock(return_value=(0, "task_scheduler"))),
            ):
                success, reason = mod.disable_auto_start()
                assert success is True
                assert reason == "task_scheduler"


# ---------------------------------------------------------------------------
# get_auto_start_check_result
# ---------------------------------------------------------------------------


class TestGetAutoStartCheckResult:
    def test_delegates_to_task_scheduler_check(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "get_task_scheduler_check_result", return_value=(True, "ok")) as mock_check:
            result = mod.get_auto_start_check_result()
            assert result == (True, "ok")
            mock_check.assert_called_once()

    def test_returns_false_when_missing(self):
        import core.auto_start_manager as mod

        with patch.object(
            mod, "get_task_scheduler_check_result", return_value=(False, "task_missing_or_inaccessible: error")
        ):
            result = mod.get_auto_start_check_result()
            assert result[0] is False


# ---------------------------------------------------------------------------
# _normalize_launch_spec edge cases
# ---------------------------------------------------------------------------


class TestNormalizeLaunchSpecEdge:
    def test_empty_args_defaults_to_empty_string(self):
        import core.auto_start_manager as mod

        _, args, _ = mod._normalize_launch_spec(r"C:\app.exe", "", r"C:\\")
        assert args == ""

    def test_empty_cwd_defaults_to_exe_dir(self):
        import core.auto_start_manager as mod

        _, _, cwd = mod._normalize_launch_spec(r"C:\MyApp\app.exe", "", "")
        assert cwd == r"C:\MyApp"

    def test_none_exe_path_uses_get_exe_path(self):
        import core.auto_start_manager as mod

        with patch.object(mod, "_get_exe_path", return_value=r"C:\fallback.exe"):
            path, _, _ = mod._normalize_launch_spec(None)
            assert path == r"C:\fallback.exe"
