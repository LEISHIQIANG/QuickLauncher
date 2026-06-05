import subprocess
import sys
import textwrap


def test_core_import_keeps_nonessential_services_lazy():
    code = textwrap.dedent(
        """
        import json
        import sys

        import core

        names = [
            "core.clipboard_service",
            "core.interaction_context",
            "core.selected_text_service",
            "core.icon_extractor",
            "core.shortcut_executor",
            "core.window_manager",
        ]
        print(json.dumps({name: name in sys.modules for name in names}, sort_keys=True))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == (
        '{"core.clipboard_service": false, "core.icon_extractor": false, '
        '"core.interaction_context": false, "core.selected_text_service": false, '
        '"core.shortcut_executor": false, "core.window_manager": false}'
    )


def test_core_lazy_export_loads_on_access():
    code = textwrap.dedent(
        """
        import json
        import sys

        import core

        before = "core.selected_text_service" in sys.modules
        _ = core.SelectedTextResult
        after = "core.selected_text_service" in sys.modules
        print(json.dumps({"before": before, "after": after}, sort_keys=True))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == '{"after": true, "before": false}'
