"""List operations for action chains.

This module provides comprehensive list operations inspired by Grasshopper's
data structure handling. It supports:
- Element-wise operations between lists
- Broadcasting (list + scalar)
- Aggregation operations
- List transformations
- List combinations
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Union

from .data_structures import (
    Item,
    List,
    Tree,
    DataType,
    get_data_type,
    ensure_list,
    align_data,
    AlignmentStrategy,
)

__all__ = [
    # Element-wise operations
    "add_lists",
    "sub_lists",
    "mul_lists",
    "div_lists",
    "mod_lists",
    "pow_lists",
    
    # Comparison operations
    "eq_lists",
    "ne_lists",
    "gt_lists",
    "lt_lists",
    "ge_lists",
    "le_lists",
    
    # Logical operations
    "and_lists",
    "or_lists",
    "xor_lists",
    "not_list",
    
    # Broadcasting (list + scalar)
    "add_scalar",
    "sub_scalar",
    "mul_scalar",
    "div_scalar",
    "mod_scalar",
    "pow_scalar",
    
    # Aggregation
    "sum_list",
    "min_list",
    "max_list",
    "average_list",
    "median_list",
    "std_list",
    "count_list",
    "join_list",
    
    # Transformations
    "reverse_list",
    "sort_list",
    "shuffle_list",
    "unique_list",
    "flatten_list",
    "compact_list",
    "map_list",
    "filter_list",
    "reduce_list",
    
    # List combinations
    "zip_lists",
    "cross_lists",
    "concat_lists",
    "interleave_lists",
    "difference_lists",
    "intersection_lists",
    
    # List slicing
    "slice_list",
    "take_list",
    "skip_list",
    "first_list",
    "last_list",
    "rest_list",
    "init_list",
    
    # List generation
    "range_list",
    "repeat_list",
    "generate_list",
    
    # Utility
    "is_empty",
    "contains",
    "index_of",
    "find_index",
    "replace_item",
    "insert_item",
    "remove_item",
]


# ── Element-wise Operations ────────────────────────────────────────────────


def _element_wise_op(list1: List, list2: List, op: Callable) -> List:
    """Apply element-wise operation between two lists with alignment."""
    aligned1, aligned2 = align_data(list1, list2, strategy=AlignmentStrategy.LONGEST)
    result = []
    for item1, item2 in zip(aligned1, aligned2):
        try:
            value = op(item1.value, item2.value)
            result.append(Item.from_any(value))
        except Exception:
            result.append(Item.from_any(None))
    return List(items=result)


def add_lists(list1: List, list2: List) -> List:
    """Add two lists element-wise: [1,2] + [3,4] = [4,6]"""
    return _element_wise_op(list1, list2, lambda a, b: a + b)


def sub_lists(list1: List, list2: List) -> List:
    """Subtract two lists element-wise: [5,6] - [1,2] = [4,4]"""
    return _element_wise_op(list1, list2, lambda a, b: a - b)


def mul_lists(list1: List, list2: List) -> List:
    """Multiply two lists element-wise: [2,3] * [4,5] = [8,15]"""
    return _element_wise_op(list1, list2, lambda a, b: a * b)


def div_lists(list1: List, list2: List) -> List:
    """Divide two lists element-wise: [10,20] / [2,4] = [5,5]"""
    def safe_div(a, b):
        if b == 0:
            return None
        return a / b
    return _element_wise_op(list1, list2, safe_div)


def mod_lists(list1: List, list2: List) -> List:
    """Modulo two lists element-wise: [10,11] % [3,3] = [1,2]"""
    def safe_mod(a, b):
        if b == 0:
            return None
        return a % b
    return _element_wise_op(list1, list2, safe_mod)


def pow_lists(list1: List, list2: List) -> List:
    """Power of two lists element-wise: [2,3] ^ [2,2] = [4,9]"""
    return _element_wise_op(list1, list2, lambda a, b: a ** b)


# ── Comparison Operations ──────────────────────────────────────────────────


def eq_lists(list1: List, list2: List) -> List:
    """Check equality element-wise: [1,2] == [1,3] = [True,False]"""
    return _element_wise_op(list1, list2, lambda a, b: a == b)


def ne_lists(list1: List, list2: List) -> List:
    """Check inequality element-wise: [1,2] != [1,3] = [False,True]"""
    return _element_wise_op(list1, list2, lambda a, b: a != b)


def gt_lists(list1: List, list2: List) -> List:
    """Check greater than element-wise: [3,1] > [2,2] = [True,False]"""
    return _element_wise_op(list1, list2, lambda a, b: a > b)


def lt_lists(list1: List, list2: List) -> List:
    """Check less than element-wise: [1,3] < [2,2] = [True,False]"""
    return _element_wise_op(list1, list2, lambda a, b: a < b)


def ge_lists(list1: List, list2: List) -> List:
    """Check greater or equal element-wise: [2,1] >= [2,2] = [True,False]"""
    return _element_wise_op(list1, list2, lambda a, b: a >= b)


def le_lists(list1: List, list2: List) -> List:
    """Check less or equal element-wise: [1,3] <= [2,2] = [True,False]"""
    return _element_wise_op(list1, list2, lambda a, b: a <= b)


# ── Logical Operations ─────────────────────────────────────────────────────


def and_lists(list1: List, list2: List) -> List:
    """Logical AND element-wise"""
    return _element_wise_op(list1, list2, lambda a, b: bool(a) and bool(b))


def or_lists(list1: List, list2: List) -> List:
    """Logical OR element-wise"""
    return _element_wise_op(list1, list2, lambda a, b: bool(a) or bool(b))


def xor_lists(list1: List, list2: List) -> List:
    """Logical XOR element-wise"""
    return _element_wise_op(list1, list2, lambda a, b: bool(a) != bool(b))


def not_list(lst: List) -> List:
    """Logical NOT for each element"""
    return lst.map(lambda x: not bool(x))


# ── Broadcasting (List + Scalar) ───────────────────────────────────────────


def _broadcast_op(lst: List, scalar: Any, op: Callable) -> List:
    """Apply operation between list and scalar."""
    result = []
    for item in lst.items:
        try:
            value = op(item.value, scalar)
            result.append(Item.from_any(value))
        except Exception:
            result.append(Item.from_any(None))
    return List(items=result)


def add_scalar(lst: List, scalar: Any) -> List:
    """Add scalar to each element: [1,2,3] + 5 = [6,7,8]"""
    return _broadcast_op(lst, scalar, lambda a, b: a + b)


def sub_scalar(lst: List, scalar: Any) -> List:
    """Subtract scalar from each element: [10,20,30] - 5 = [5,15,25]"""
    return _broadcast_op(lst, scalar, lambda a, b: a - b)


def mul_scalar(lst: List, scalar: Any) -> List:
    """Multiply each element by scalar: [1,2,3] * 2 = [2,4,6]"""
    return _broadcast_op(lst, scalar, lambda a, b: a * b)


def div_scalar(lst: List, scalar: Any) -> List:
    """Divide each element by scalar: [10,20,30] / 10 = [1,2,3]"""
    def safe_div(a, b):
        if b == 0:
            return None
        return a / b
    return _broadcast_op(lst, scalar, safe_div)


def mod_scalar(lst: List, scalar: Any) -> List:
    """Modulo each element by scalar: [10,11,12] % 3 = [1,2,0]"""
    def safe_mod(a, b):
        if b == 0:
            return None
        return a % b
    return _broadcast_op(lst, scalar, safe_mod)


def pow_scalar(lst: List, scalar: Any) -> List:
    """Raise each element to power of scalar: [2,3,4] ^ 2 = [4,9,16]"""
    return _broadcast_op(lst, scalar, lambda a, b: a ** b)


# ── Aggregation Operations ─────────────────────────────────────────────────


def sum_list(lst: List) -> Any:
    """Sum all elements: [1,2,3] -> 6"""
    values = [item.value for item in lst.items if item.value is not None]
    if not values:
        return 0
    return sum(values)


def min_list(lst: List) -> Any:
    """Find minimum element: [3,1,2] -> 1"""
    values = [item.value for item in lst.items if item.value is not None]
    if not values:
        return None
    return min(values)


def max_list(lst: List) -> Any:
    """Find maximum element: [3,1,2] -> 3"""
    values = [item.value for item in lst.items if item.value is not None]
    if not values:
        return None
    return max(values)


def average_list(lst: List) -> float | None:
    """Calculate average: [1,2,3] -> 2.0"""
    values = [item.value for item in lst.items if item.value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def median_list(lst: List) -> float | None:
    """Calculate median: [1,3,2] -> 2.0"""
    values = sorted([item.value for item in lst.items if item.value is not None])
    if not values:
        return None
    n = len(values)
    if n % 2 == 0:
        return (values[n//2 - 1] + values[n//2]) / 2
    return values[n//2]


def std_list(lst: List) -> float | None:
    """Calculate standard deviation"""
    values = [item.value for item in lst.items if item.value is not None]
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def count_list(lst: List) -> int:
    """Count elements: [1,2,3] -> 3"""
    return len(lst)


def join_list(lst: List, delimiter: str = ",") -> str:
    """Join elements to string: [1,2,3] -> '1,2,3'"""
    return delimiter.join(str(item.value) for item in lst.items)


# ── Transformations ────────────────────────────────────────────────────────


def reverse_list(lst: List) -> List:
    """Reverse list: [1,2,3] -> [3,2,1]"""
    return lst.reverse()


def sort_list(lst: List, key: Callable = None, reverse: bool = False) -> List:
    """Sort list: [3,1,2] -> [1,2,3]"""
    if key is None:
        key = lambda x: x.value
    sorted_items = sorted(lst.items, key=key, reverse=reverse)
    return List(items=sorted_items)


def shuffle_list(lst: List) -> List:
    """Shuffle list randomly"""
    import random
    items = list(lst.items)
    random.shuffle(items)
    return List(items=items)


def unique_list(lst: List) -> List:
    """Remove duplicates: [1,2,2,3,3] -> [1,2,3]"""
    return lst.unique()


def flatten_list(lst: List) -> List:
    """Flatten nested lists: [[1,2],[3,[4,5]]] -> [1,2,3,4,5]"""
    result = []
    for item in lst.items:
        if isinstance(item.value, list):
            for sub_item in item.value:
                result.append(Item.from_any(sub_item))
        elif isinstance(item.value, List):
            for sub_item in item.value.items:
                result.append(sub_item)
        else:
            result.append(item)
    return List(items=result)


def compact_list(lst: List) -> List:
    """Remove None/empty values: [1,None,2,"",3] -> [1,2,3]"""
    return lst.filter(lambda x: x is not None and x != "" and x != 0)


def map_list(lst: List, func: Callable) -> List:
    """Apply function to each element"""
    return lst.map(func)


def filter_list(lst: List, predicate: Callable) -> List:
    """Filter elements by predicate"""
    return lst.filter(predicate)


def reduce_list(lst: List, func: Callable, initial: Any = None) -> Any:
    """Reduce list to single value"""
    return lst.reduce(func, initial)


# ── List Combinations ──────────────────────────────────────────────────────


def zip_lists(list1: List, list2: List) -> List:
    """Zip two lists: [1,2] + ["a","b"] -> [(1,"a"),(2,"b")]"""
    aligned1, aligned2 = align_data(list1, list2, strategy=AlignmentStrategy.SHORTEST)
    result = []
    for item1, item2 in zip(aligned1, aligned2):
        result.append(Item.from_any((item1.value, item2.value)))
    return List(items=result)


def cross_lists(list1: List, list2: List) -> tuple[List, List]:
    """Cross product: [1,2] x ["a","b"] -> ([1,1,2,2], ["a","b","a","b"])"""
    result1 = []
    result2 = []
    for item1 in list1.items:
        for item2 in list2.items:
            result1.append(item1)
            result2.append(item2)
    return List(items=result1), List(items=result2)


def concat_lists(list1: List, list2: List) -> List:
    """Concatenate lists: [1,2] + [3,4] -> [1,2,3,4]"""
    return list1 + list2


def interleave_lists(list1: List, list2: List) -> List:
    """Interleave lists: [1,3] + [2,4] -> [1,2,3,4]"""
    result = []
    for item1, item2 in zip(list1.items, list2.items):
        result.append(item1)
        result.append(item2)
    return List(items=result)


def difference_lists(list1: List, list2: List) -> List:
    """Set difference: [1,2,3,4] - [2,4] -> [1,3]"""
    values2 = {item.value for item in list2.items}
    result = [item for item in list1.items if item.value not in values2]
    return List(items=result)


def intersection_lists(list1: List, list2: List) -> List:
    """Set intersection: [1,2,3] ∩ [2,3,4] -> [2,3]"""
    values2 = {item.value for item in list2.items}
    result = [item for item in list1.items if item.value in values2]
    return List(items=result)


# ── List Slicing ───────────────────────────────────────────────────────────


def slice_list(lst: List, start: int = None, end: int = None, step: int = None) -> List:
    """Slice list: [1,2,3,4,5][1:3] -> [2,3]"""
    return lst.slice(start, end, step)


def take_list(lst: List, count: int) -> List:
    """Take first N elements: [1,2,3,4,5] take 3 -> [1,2,3]"""
    return lst.slice(0, count)


def skip_list(lst: List, count: int) -> List:
    """Skip first N elements: [1,2,3,4,5] skip 2 -> [3,4,5]"""
    return lst.slice(count)


def first_list(lst: List) -> Item | None:
    """Get first element"""
    return lst.first


def last_list(lst: List) -> Item | None:
    """Get last element"""
    return lst.last


def rest_list(lst: List) -> List:
    """Get all except first: [1,2,3] -> [2,3]"""
    return lst.slice(1)


def init_list(lst: List) -> List:
    """Get all except last: [1,2,3] -> [1,2]"""
    return lst.slice(0, -1)


# ── List Generation ────────────────────────────────────────────────────────


def range_list(start: int, end: int, step: int = 1) -> List:
    """Generate range: range(1,5) -> [1,2,3,4]"""
    values = list(range(start, end, step))
    return List.from_values(values)


def repeat_list(item: Any, count: int) -> List:
    """Repeat item N times: repeat("a", 3) -> ["a","a","a"]"""
    return List.from_values([item] * count)


def generate_list(func: Callable, count: int) -> List:
    """Generate list using function: generate(lambda i: i*2, 3) -> [0,2,4]"""
    values = [func(i) for i in range(count)]
    return List.from_values(values)


# ── Utility Functions ──────────────────────────────────────────────────────


def is_empty(lst: List) -> bool:
    """Check if list is empty"""
    return lst.is_empty


def contains(lst: List, value: Any) -> bool:
    """Check if list contains value"""
    return value in lst


def index_of(lst: List, value: Any) -> int:
    """Find index of value (-1 if not found)"""
    for i, item in enumerate(lst.items):
        if item.value == value:
            return i
    return -1


def find_index(lst: List, predicate: Callable) -> int:
    """Find index of first matching element (-1 if not found)"""
    for i, item in enumerate(lst.items):
        if predicate(item.value):
            return i
    return -1


def replace_item(lst: List, old_value: Any, new_value: Any) -> List:
    """Replace all occurrences of old_value with new_value"""
    result = []
    for item in lst.items:
        if item.value == old_value:
            result.append(Item.from_any(new_value))
        else:
            result.append(item)
    return List(items=result)


def insert_item(lst: List, index: int, value: Any) -> List:
    """Insert value at index"""
    items = list(lst.items)
    items.insert(index, Item.from_any(value))
    return List(items=items)


def remove_item(lst: List, value: Any) -> List:
    """Remove first occurrence of value"""
    result = []
    removed = False
    for item in lst.items:
        if not removed and item.value == value:
            removed = True
            continue
        result.append(item)
    return List(items=result)


# ── Tree Operations ────────────────────────────────────────────────────────


def tree_add(tree1: Tree, tree2: Tree) -> Tree:
    """Add two trees branch-wise"""
    return _tree_operation(tree1, tree2, add_lists)


def tree_sub(tree1: Tree, tree2: Tree) -> Tree:
    """Subtract two trees branch-wise"""
    return _tree_operation(tree1, tree2, sub_lists)


def tree_mul(tree1: Tree, tree2: Tree) -> Tree:
    """Multiply two trees branch-wise"""
    return _tree_operation(tree1, tree2, mul_lists)


def tree_div(tree1: Tree, tree2: Tree) -> Tree:
    """Divide two trees branch-wise"""
    return _tree_operation(tree1, tree2, div_lists)


def tree_broadcast_scalar(tree: Tree, scalar: Any, operation: str) -> Tree:
    """Broadcast scalar to all branches of tree"""
    op_func = _get_operation_func(operation)
    new_branches = {}
    for path, branch in tree.branches.items():
        new_branches[path] = op_func(branch, scalar)
    return Tree(branches=new_branches)


def _tree_operation(tree1: Tree, tree2: Tree, op: Callable) -> Tree:
    """Apply operation between two trees"""
    new_branches = {}
    common_paths = set(tree1.paths) & set(tree2.paths)
    
    for path in sorted(common_paths):
        branch1 = tree1[path]
        branch2 = tree2[path]
        new_branches[path] = op(branch1, branch2)
    
    return Tree(branches=new_branches)


def _get_operation_func(operation: str) -> Callable:
    """Get operation function by name"""
    ops = {
        'add': add_scalar,
        'sub': sub_scalar,
        'mul': mul_scalar,
        'div': div_scalar,
        'mod': mod_scalar,
        'pow': pow_scalar,
    }
    return ops.get(operation, add_scalar)
