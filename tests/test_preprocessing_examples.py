"""Tests for preprocessing/examples.py - exercise example functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestExampleBasic:
    def test_runs_without_error(self):
        from core.preprocessing.pipeline import PreprocessingContext, PreprocessingPipeline

        pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
        context = PreprocessingContext(command="echo hello world", command_type="cmd")
        result = pipeline.process(context)
        assert result.success is True


class TestExampleCommandInjection:
    def test_runs_without_error(self):
        from core.preprocessing.pipeline import PreprocessingContext, PreprocessingPipeline

        pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
        context = PreprocessingContext(command="echo hello; rm -rf /", command_type="cmd")
        result = pipeline.process(context)
        assert len(result.warnings) > 0


class TestExampleRawMode:
    def test_runs_without_error(self):
        from core.preprocessing.pipeline import PreprocessingContext, PreprocessingPipeline

        pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)
        context = PreprocessingContext(
            command='powershell -Command "Get-Process | Where-Object {$_.CPU -gt 100}"',
            command_type="cmd",
            raw_mode=True,
        )
        result = pipeline.process(context)
        assert result.metadata.get("raw_mode") is True


class TestExampleFromSettings:
    def test_runs_without_error(self):
        from core.data_models import AppSettings
        from core.preprocessing.pipeline import PreprocessingContext, create_pipeline_from_settings

        settings = AppSettings()
        settings.preprocessing_enabled = True
        settings.preprocessing_strict_mode = False
        settings.security_block_dangerous_patterns = True
        pipeline = create_pipeline_from_settings(settings)
        context = PreprocessingContext(command="format C:", command_type="cmd")
        result = pipeline.process(context)
        assert result.should_block is True


class TestExampleUserControls:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_user_controls

        result = example_user_controls()
        assert result is None
