import core.shortcut_file_exec as file_exec
from core.data_models import ShortcutItem
from core.shortcut_file_exec import FileExecutionMixin


def test_launch_privilege_four_quadrants(monkeypatch):
    scenarios = [
        # current_elevated, run_as_admin, expected_path, expected_verb
        (False, False, "shell", "open"),
        (False, True, "shell", "runas"),
        (True, False, "downgrade", None),
        (True, True, "shell", "open"),
    ]

    for current_elevated, run_as_admin, expected_path, expected_verb in scenarios:
        calls = []

        class FakeExecutor(FileExecutionMixin):
            @staticmethod
            def _is_launch_context_elevated(curr_elevated=current_elevated):
                return curr_elevated

            @staticmethod
            def _launch_as_standard_user_direct(target, parameters="", directory="", show_cmd=1, _calls=calls):
                _calls.append(("downgrade", target, parameters, directory, show_cmd))
                return True, ""

            @staticmethod
            def _shell_execute_open_raw_result(
                target, parameters=None, directory=None, show_cmd=1, verb="open", _calls=calls
            ):
                _calls.append(("shell", target, parameters, directory, show_cmd, verb))
                return True, ""

        monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

        success, error = FileExecutionMixin._launch_with_privilege(
            r"C:\Tools\App.exe",
            "--flag",
            r"C:\Tools",
            run_as_admin=run_as_admin,
        )

        assert success is True
        assert error == ""
        assert calls[0][0] == expected_path
        if expected_verb is not None:
            assert calls[0][-1] == expected_verb


def test_privilege_route_selector_encodes_four_quadrants():
    assert FileExecutionMixin._select_privilege_launch_route(False, False) == "open"
    assert FileExecutionMixin._select_privilege_launch_route(False, True) == "runas"
    assert FileExecutionMixin._select_privilege_launch_route(True, False) == "downgrade"
    assert FileExecutionMixin._select_privilege_launch_route(True, True) == "open"


def test_non_elevated_context_non_admin_item_uses_open(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return False

        @staticmethod
        def _shell_execute_open_raw_result(target, parameters=None, directory=None, show_cmd=1, verb="open"):
            captured["verb"] = verb
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        run_as_admin=False,
    )

    assert success is True
    assert error == ""
    assert captured["verb"] == "open"


def test_non_elevated_context_admin_item_uses_runas(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return False

        @staticmethod
        def _shell_execute_open_raw_result(target, parameters=None, directory=None, show_cmd=1, verb="open"):
            captured["verb"] = verb
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        run_as_admin=True,
    )

    assert success is True
    assert error == ""
    assert captured["verb"] == "runas"


def test_elevated_context_non_admin_item_uses_standard_user_channel(monkeypatch):
    calls = []

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _launch_as_standard_user_direct(target, parameters="", directory="", show_cmd=1):
            calls.append(("channel", target, parameters, directory, show_cmd))
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        run_as_admin=False,
    )

    assert success is True
    assert error == ""
    assert calls == [("channel", r"C:\Tools\App.exe", "", "", 1)]


def test_elevated_context_non_admin_item_does_not_use_legacy_standard_user_fallback(monkeypatch):
    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _launch_as_standard_user_direct(target, parameters="", directory="", show_cmd=1):
            return False, "channel failed"

        @staticmethod
        def _execute_as_standard_user(*args, **kwargs):
            raise AssertionError("legacy downgrade fallback must not be used")

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        run_as_admin=False,
    )

    assert success is False
    assert "standard-user launch failed" in error


def test_elevated_context_non_admin_item_prefers_standard_user_channel(monkeypatch):
    calls = []

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _launch_as_standard_user_direct(target, parameters="", directory="", show_cmd=1):
            calls.append(("channel", target, parameters, directory, show_cmd))
            return True, ""

        @staticmethod
        def _execute_as_standard_user(*args, **kwargs):
            raise AssertionError("legacy fallback must not run after direct channel succeeds")

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        "--flag",
        r"C:\Tools",
        run_as_admin=False,
    )

    assert success is True
    assert error == ""
    assert calls == [("channel", r"C:\Tools\App.exe", "--flag", r"C:\Tools", 1)]


def test_elevated_context_admin_item_reuses_current_admin_token(monkeypatch):
    captured = {}

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _is_launch_context_elevated():
            return True

        @staticmethod
        def _shell_execute_open_raw_result(target, parameters=None, directory=None, show_cmd=1, verb="open"):
            captured["verb"] = verb
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    success, error = FileExecutionMixin._launch_with_privilege(
        r"C:\Tools\App.exe",
        run_as_admin=True,
    )

    assert success is True
    assert error == ""
    assert captured["verb"] == "open"


def test_admin_item_launch_skips_post_launch_activation(monkeypatch):
    calls = []

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _resolve_shortcut(path):
            return path

        @staticmethod
        def _launch_with_privilege(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            calls.append(("launch", target, run_as_admin))
            return True, ""

        @staticmethod
        def _activate_launched_app_async(exe_path):
            calls.append(("activate", exe_path))

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    shortcut = ShortcutItem(
        name="AdminApp",
        target_path=r"C:\Tools\AdminApp.exe",
        run_as_admin=True,
    )

    success, error = FileExecutionMixin._execute_file(shortcut, force_new=False)

    assert success is True
    assert error == ""
    assert calls == [("launch", r"C:\Tools\AdminApp.exe", True)]


def test_file_target_args_resolve_ip_variables(monkeypatch):
    captured = {}
    monkeypatch.setattr(file_exec, "HAS_WINDOW_MANAGER", False)
    monkeypatch.setattr("core.command_variables.get_default_lan_ipv4", lambda: "192.168.1.20")

    class FakeExecutor(FileExecutionMixin):
        @staticmethod
        def _resolve_shortcut(path):
            return path

        @staticmethod
        def _launch_with_privilege(target, parameters=None, directory=None, show_cmd=1, run_as_admin=False):
            captured["parameters"] = parameters
            return True, ""

    monkeypatch.setattr(file_exec, "ShortcutExecutor", FakeExecutor)

    shortcut = ShortcutItem(
        name="App",
        target_path=r"C:\Tools\App.exe",
        target_args="--bind {{LAN_IP}}",
    )

    success, error = FileExecutionMixin._execute_file(shortcut, force_new=True)

    assert success is True
    assert error == ""
    assert captured["parameters"] == "--bind 192.168.1.20"
