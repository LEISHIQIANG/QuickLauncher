"""Tests for preprocessing/examples.py - exercise example functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestExampleBasic:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_basic

        # Should not raise
        example_basic()


class TestExampleCommandInjection:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_command_injection

        example_command_injection()


class TestExampleRawMode:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_raw_mode

        example_raw_mode()


class TestExampleFromSettings:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_from_settings

        example_from_settings()


class TestExampleUserControls:
    def test_runs_without_error(self):
        from core.preprocessing.examples import example_user_controls

        # This is just a docstring function (pass body)
        example_user_controls()
