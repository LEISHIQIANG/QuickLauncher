"""Tests for preprocessing pipeline."""

from core.preprocessing.pipeline import PreprocessingContext, PreprocessingPipeline, create_pipeline_from_settings


def test_pipeline_empty_command():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="", command_type="cmd")
    result = pipeline.process(context)
    assert not result.success
    assert len(result.errors) > 0


def test_pipeline_command_too_long():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="x" * 20000, command_type="cmd")
    result = pipeline.process(context)
    assert not result.success
    assert any("过长" in e.message for e in result.errors)


def test_pipeline_invalid_working_dir():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello", working_dir="/nonexistent/path/12345", command_type="cmd")
    result = pipeline.process(context)
    assert not result.success
    assert any("工作目录" in e.message or "不存在" in e.message for e in result.errors)


def test_pipeline_command_injection_warning():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello; rm -rf /", command_type="cmd")
    result = pipeline.process(context)
    assert len(result.warnings) > 0
    assert any("危险字符" in w.description for w in result.warnings)


def test_pipeline_dangerous_pattern_warning():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="format C:", command_type="cmd")
    result = pipeline.process(context)
    assert len(result.warnings) > 0
    assert any("危险操作" in w.description for w in result.warnings)


def test_pipeline_raw_mode():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo {test}", command_type="cmd", raw_mode=True)
    result = pipeline.process(context)
    assert result.metadata.get("raw_mode") is True


def test_pipeline_clean_command():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello world", command_type="cmd")
    result = pipeline.process(context)
    assert result.success
    assert len(result.errors) == 0


def test_pipeline_unsupported_command_type():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello", command_type="wscript")
    result = pipeline.process(context)
    assert not result.success
    assert any(e.error_code == "unsupported_command_type" for e in result.errors)


def test_pipeline_non_strict_allows_shell_operators_as_warnings():
    pipeline = PreprocessingPipeline(enabled=True, strict_mode=False, rate_limiting=False)
    context = PreprocessingContext(command="echo hello | findstr hello", command_type="cmd")
    result = pipeline.process(context)
    assert result.success
    assert not result.should_block
    assert result.warnings


def test_pipeline_strict_blocks_shell_operators():
    pipeline = PreprocessingPipeline(enabled=True, strict_mode=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello & echo world", command_type="cmd")
    result = pipeline.process(context)
    assert result.should_block


def test_pipeline_disabled():
    pipeline = PreprocessingPipeline(enabled=False)
    context = PreprocessingContext(command="", command_type="cmd")
    result = pipeline.process(context)
    assert result.success
    assert len(result.errors) == 0


def test_pipeline_rate_limiting():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=True)
    context = PreprocessingContext(shortcut_id="test-123", command="echo hello", command_type="cmd")

    for i in range(15):
        result = pipeline.process(context)
        if i < 10:
            assert result.success
        else:
            assert not result.success
            assert any("速率限制" in e.message for e in result.errors)
            break


# ── Bash 支持测试 ────────────────────────────────────────────────────


def test_pipeline_bash_valid():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello", command_type="bash")
    result = pipeline.process(context)
    assert result.success


def test_pipeline_bash_alias_is_normalized():
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
    context = PreprocessingContext(command="echo hello", command_type="git-bash")
    result = pipeline.process(context)
    assert result.success
    assert context.command_type == "bash"


def test_create_from_settings_blocks_dangerous_by_default():
    """create_pipeline_from_settings should default to blocking dangerous patterns."""
    settings = type("Settings", (), {})()
    pipeline = create_pipeline_from_settings(settings)
    assert pipeline.block_dangerous_patterns is True


def test_create_from_settings_can_override_block_dangerous():
    settings = type("Settings", (), {"security_block_dangerous_patterns": False})()
    pipeline = create_pipeline_from_settings(settings)
    assert pipeline.block_dangerous_patterns is False
