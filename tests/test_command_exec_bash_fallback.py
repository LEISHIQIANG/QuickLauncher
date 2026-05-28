import threading

from core.command_exec.bash_fallback import (
    bash_path,
    build_bash_fallback_wrapper,
    quote_bash_path,
    read_bash_fallback_exit_code,
    wait_for_bash_fallback_completion,
)


def test_bash_path_helpers_normalize_windows_paths():
    assert bash_path(r"C:\Temp\out file.txt") == "C:/Temp/out file.txt"
    assert quote_bash_path(r'C:\Temp\a"b.txt') == 'C:/Temp/a\\"b.txt'


def test_build_bash_fallback_wrapper_for_temp_script_uses_marker_content():
    wrapper = build_bash_fallback_wrapper(
        "ignored",
        tmp_path=r"C:\Temp\script.sh",
        stdout_path=r"C:\Temp\stdout.out",
        stderr_path=r"C:\Temp\stderr.err",
        marker_path=r"C:\Temp\done.marker",
    )

    assert '"C:/Temp/script.sh" >"C:/Temp/stdout.out" 2>"C:/Temp/stderr.err"' in wrapper
    assert 'echo "EXIT:$?" >>"C:/Temp/done.marker"' in wrapper


def test_build_bash_fallback_wrapper_for_inline_command_quotes_single_quotes():
    wrapper = build_bash_fallback_wrapper(
        "echo 'hello'",
        tmp_path=None,
        stdout_path="stdout.out",
        stderr_path="stderr.err",
        marker_path="done.marker",
    )

    assert "echo 'echo '\\''hello'\\'''" in wrapper
    assert "bash --noprofile --norc" in wrapper


def test_read_bash_fallback_exit_code_reads_content_not_existence(tmp_path):
    marker = tmp_path / "done.marker"

    assert read_bash_fallback_exit_code(str(marker)) is None
    marker.write_text("", encoding="utf-8")
    assert read_bash_fallback_exit_code(str(marker)) is None
    marker.write_text("noise\nEXIT:-15\n", encoding="utf-8")
    assert read_bash_fallback_exit_code(str(marker)) == -15


def test_wait_for_bash_fallback_completion_returns_completed(tmp_path):
    marker = tmp_path / "done.marker"
    marker.write_text("EXIT:0\n", encoding="utf-8")

    assert (
        wait_for_bash_fallback_completion(
            process=object(),
            marker_path=str(marker),
            timeout_value=1.0,
            sleep=lambda _: None,
        )
        == "completed"
    )


def test_wait_for_bash_fallback_completion_times_out(tmp_path):
    marker = tmp_path / "missing.marker"
    terminated = []
    times = iter([10.0, 10.2])

    state = wait_for_bash_fallback_completion(
        process="proc",
        marker_path=str(marker),
        timeout_value=0.1,
        terminate_process_tree=lambda process: terminated.append(process),
        sleep=lambda _: None,
        clock=lambda: next(times),
    )

    assert state == "timed_out"
    assert terminated == ["proc"]


def test_wait_for_bash_fallback_completion_cancels(tmp_path):
    cancel_event = threading.Event()
    cancel_event.set()
    terminated = []

    state = wait_for_bash_fallback_completion(
        process="proc",
        marker_path=str(tmp_path / "missing.marker"),
        timeout_value=10.0,
        cancel_event=cancel_event,
        terminate_process_tree=lambda process: terminated.append(process),
        sleep=lambda _: None,
    )

    assert state == "cancelled"
    assert terminated == ["proc"]
