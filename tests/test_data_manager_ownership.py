from __future__ import annotations

from core.data_manager import DataManager


def test_data_manager_is_not_a_process_singleton():
    first = object.__new__(DataManager)
    second = object.__new__(DataManager)

    assert first is not second
