"""Tests for list operations."""

import pytest

from core.chain.data_structures import List
from core.chain.list_operations import (
    add_lists,
    add_scalar,
    average_list,
    concat_lists,
    contains,
    cross_lists,
    div_lists,
    div_scalar,
    eq_lists,
    gt_lists,
    index_of,
    lt_lists,
    max_list,
    min_list,
    mul_lists,
    mul_scalar,
    range_list,
    repeat_list,
    reverse_list,
    sort_list,
    sub_lists,
    sub_scalar,
    sum_list,
    unique_list,
    zip_lists,
)


class TestElementWiseOperations:
    """Test element-wise operations between lists."""

    def test_add_lists(self):
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values([4, 5, 6])
        result = add_lists(lst1, lst2)
        assert result.to_values() == [5, 7, 9]

    def test_sub_lists(self):
        lst1 = List.from_values([10, 20, 30])
        lst2 = List.from_values([1, 2, 3])
        result = sub_lists(lst1, lst2)
        assert result.to_values() == [9, 18, 27]

    def test_mul_lists(self):
        lst1 = List.from_values([2, 3, 4])
        lst2 = List.from_values([5, 6, 7])
        result = mul_lists(lst1, lst2)
        assert result.to_values() == [10, 18, 28]

    def test_div_lists(self):
        lst1 = List.from_values([10, 20, 30])
        lst2 = List.from_values([2, 4, 5])
        result = div_lists(lst1, lst2)
        assert result.to_values() == [5.0, 5.0, 6.0]

    def test_different_lengths(self):
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values([10, 20])
        result = add_lists(lst1, lst2)
        assert result.to_values() == [11, 22, 23]


class TestComparisonOperations:
    """Test comparison operations."""

    def test_eq_lists(self):
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values([1, 2, 4])
        result = eq_lists(lst1, lst2)
        assert result.to_values() == [True, True, False]

    def test_gt_lists(self):
        lst1 = List.from_values([3, 1, 5])
        lst2 = List.from_values([2, 2, 2])
        result = gt_lists(lst1, lst2)
        assert result.to_values() == [True, False, True]

    def test_lt_lists(self):
        lst1 = List.from_values([1, 3, 5])
        lst2 = List.from_values([2, 2, 2])
        result = lt_lists(lst1, lst2)
        assert result.to_values() == [True, False, False]


class TestBroadcasting:
    """Test broadcasting operations (list + scalar)."""

    def test_add_scalar(self):
        lst = List.from_values([1, 2, 3])
        result = add_scalar(lst, 10)
        assert result.to_values() == [11, 12, 13]

    def test_sub_scalar(self):
        lst = List.from_values([10, 20, 30])
        result = sub_scalar(lst, 5)
        assert result.to_values() == [5, 15, 25]

    def test_mul_scalar(self):
        lst = List.from_values([1, 2, 3])
        result = mul_scalar(lst, 2)
        assert result.to_values() == [2, 4, 6]

    def test_div_scalar(self):
        lst = List.from_values([10, 20, 30])
        result = div_scalar(lst, 10)
        assert result.to_values() == [1.0, 2.0, 3.0]


class TestAggregation:
    """Test aggregation operations."""

    def test_sum_list(self):
        lst = List.from_values([1, 2, 3, 4, 5])
        assert sum_list(lst) == 15

    def test_min_list(self):
        lst = List.from_values([3, 1, 4, 1, 5])
        assert min_list(lst) == 1

    def test_max_list(self):
        lst = List.from_values([3, 1, 4, 1, 5])
        assert max_list(lst) == 5

    def test_average_list(self):
        lst = List.from_values([1, 2, 3, 4, 5])
        assert average_list(lst) == 3.0


class TestTransformations:
    """Test transformation operations."""

    def test_reverse_list(self):
        lst = List.from_values([1, 2, 3])
        result = reverse_list(lst)
        assert result.to_values() == [3, 2, 1]

    def test_sort_list(self):
        lst = List.from_values([3, 1, 4, 1, 5])
        result = sort_list(lst)
        assert result.to_values() == [1, 1, 3, 4, 5]

    def test_unique_list(self):
        lst = List.from_values([1, 2, 2, 3, 3, 3])
        result = unique_list(lst)
        assert result.to_values() == [1, 2, 3]


class TestListCombinations:
    """Test list combination operations."""

    def test_zip_lists(self):
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values(["a", "b", "c"])
        result = zip_lists(lst1, lst2)
        assert result[0].value == (1, "a")
        assert result[1].value == (2, "b")

    def test_cross_lists(self):
        lst1 = List.from_values([1, 2])
        lst2 = List.from_values(["a", "b"])
        result1, result2 = cross_lists(lst1, lst2)
        assert result1.to_values() == [1, 1, 2, 2]
        assert result2.to_values() == ["a", "b", "a", "b"]

    def test_concat_lists(self):
        lst1 = List.from_values([1, 2])
        lst2 = List.from_values([3, 4])
        result = concat_lists(lst1, lst2)
        assert result.to_values() == [1, 2, 3, 4]


class TestListGeneration:
    """Test list generation operations."""

    def test_range_list(self):
        result = range_list(1, 5)
        assert result.to_values() == [1, 2, 3, 4]

    def test_repeat_list(self):
        result = repeat_list("a", 3)
        assert result.to_values() == ["a", "a", "a"]


class TestUtility:
    """Test utility functions."""

    def test_contains(self):
        lst = List.from_values([1, 2, 3])
        assert contains(lst, 2) is True
        assert contains(lst, 4) is False

    def test_index_of(self):
        lst = List.from_values([1, 2, 3])
        assert index_of(lst, 2) == 1
        assert index_of(lst, 4) == -1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
