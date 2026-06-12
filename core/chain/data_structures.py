"""Core data structures for action chains.

This module implements a Grasshopper-inspired data structure system with
three levels: Item, List, and Tree. This provides a clear and powerful
data model for action chain operations.

Grasshopper Data Structure Overview:
- Item: A single data value
- List: A flat collection of items (1D)
- Tree: A collection of branches, where each branch is a list (2D+)

Key concepts:
- Path: A tuple of integers that identifies a branch in a tree
- Branch: A list of items at a specific path in a tree
- Grafting: Converting a list to a tree (each item becomes a branch)
- Flattening: Converting a tree to a list (all branches merged)
- Simplifying: Removing unnecessary path indices
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "Item",
    "List",
    "Tree",
    "Path",
    "DataType",
    "AlignmentStrategy",
    "align_data",
    "graft_tree",
    "flatten_tree",
    "simplify_tree",
    "cross_reference_trees",
    "zip_trees",
    "longest_list_operation",
    "shortest_list_operation",
]


class DataType(str, Enum):
    """Data structure type enumeration."""

    ITEM = "item"
    LIST = "list"
    TREE = "tree"


class AlignmentStrategy(str, Enum):
    """Strategy for aligning lists of different lengths."""

    SHORTEST = "shortest"  # Stop at shortest list length
    LONGEST = "longest"  # Continue to longest list length (repeat last)
    CYCLE = "cycle"  # Cycle through shorter lists
    CROSS = "cross"  # Cross reference (all combinations)


# Type alias for path
Path = tuple[int, ...]

# Empty path constant
EMPTY_PATH: Path = ()


@dataclass
class Item:
    """A single data value with metadata.

    Item is the atomic unit of data in the system.
    It wraps a value with type information and metadata.
    """

    value: Any
    data_type: str = "any"  # SmartType or ChainValueKind
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Item({self.value!r}, type={self.data_type})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Item):
            return self.value == other.value
        return self.value == other

    def __hash__(self) -> int:
        return hash(self.value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "value": self.value,
            "data_type": self.data_type,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Item:
        """Create from dictionary."""
        return cls(
            value=data.get("value"),
            data_type=str(data.get("data_type") or "any"),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def from_any(cls, value: Any, data_type: str = "any") -> Item:
        """Create from any value."""
        if isinstance(value, Item):
            return value
        return cls(value=value, data_type=data_type)


@dataclass
class List:
    """A flat collection of items (1D data structure).

    List is an ordered collection of Items. It supports standard
    collection operations and list-specific operations.
    """

    items: list[Item] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        # Ensure all items are Item instances
        normalized = []
        for item in self.items:
            if isinstance(item, Item):
                normalized.append(item)
            else:
                normalized.append(Item.from_any(item))
        object.__setattr__(self, "items", normalized)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> Item:
        return self.items[index]

    def __setitem__(self, index: int, value: Any):
        if isinstance(value, Item):
            self.items[index] = value
        else:
            self.items[index] = Item.from_any(value)

    def __iter__(self) -> Iterator[Item]:
        return iter(self.items)

    def __contains__(self, value: Any) -> bool:
        if isinstance(value, Item):
            return value in self.items
        return any(item.value == value for item in self.items)

    def __str__(self) -> str:
        return f"List([{', '.join(str(item) for item in self.items)}])"

    def __repr__(self) -> str:
        return f"List(items={self.items!r})"

    def __add__(self, other: List) -> List:
        """Concatenate two lists."""
        return List(items=self.items + other.items)

    def __mul__(self, count: int) -> List:
        """Repeat list."""
        return List(items=self.items * count)

    @property
    def length(self) -> int:
        """Get list length."""
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        """Check if list is empty."""
        return len(self.items) == 0

    @property
    def first(self) -> Item | None:
        """Get first item."""
        return self.items[0] if self.items else None

    @property
    def last(self) -> Item | None:
        """Get last item."""
        return self.items[-1] if self.items else None

    def append(self, value: Any) -> None:
        """Add item to end."""
        if isinstance(value, Item):
            self.items.append(value)
        else:
            self.items.append(Item.from_any(value))

    def extend(self, other: List) -> None:
        """Add all items from another list."""
        self.items.extend(other.items)

    def insert(self, index: int, value: Any) -> None:
        """Insert item at index."""
        if isinstance(value, Item):
            self.items.insert(index, value)
        else:
            self.items.insert(index, Item.from_any(value))

    def remove(self, value: Any) -> None:
        """Remove first occurrence of value."""
        for i, item in enumerate(self.items):
            if item.value == value:
                self.items.pop(i)
                return

    def pop(self, index: int = -1) -> Item:
        """Remove and return item at index."""
        return self.items.pop(index)

    def clear(self) -> None:
        """Remove all items."""
        self.items.clear()

    def reverse(self) -> List:
        """Return reversed list."""
        return List(items=list(reversed(self.items)), metadata=dict(self.metadata))

    def sort(self, key=None, reverse=False) -> List:
        """Return sorted list."""
        if key is None:
            sorted_items = sorted(self.items, key=lambda x: x.value, reverse=reverse)
        else:
            sorted_items = sorted(self.items, key=key, reverse=reverse)
        return List(items=sorted_items, metadata=dict(self.metadata))

    def unique(self) -> List:
        """Return list with unique values."""
        seen = set()
        unique_items = []
        for item in self.items:
            if item.value not in seen:
                seen.add(item.value)
                unique_items.append(item)
        return List(items=unique_items, metadata=dict(self.metadata))

    def slice(self, start: int = None, end: int = None, step: int = None) -> List:
        """Return sliced list."""
        return List(items=self.items[start:end:step], metadata=dict(self.metadata))

    def map(self, func) -> List:
        """Apply function to each item."""
        return List(items=[Item.from_any(func(item.value)) for item in self.items])

    def filter(self, func) -> List:
        """Filter items by predicate."""
        return List(items=[item for item in self.items if func(item.value)])

    def reduce(self, func, initial=None):
        """Reduce items to single value."""
        from functools import reduce

        values = [item.value for item in self.items]
        if not values:
            return initial
        if initial is None:
            return reduce(func, values)
        return reduce(func, values, initial)

    def to_values(self) -> list[Any]:
        """Extract raw values."""
        return [item.value for item in self.items]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "items": [item.to_dict() for item in self.items],
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> List:
        """Create from dictionary."""
        items = [Item.from_dict(item) for item in data.get("items", [])]
        return cls(items=items, metadata=dict(data.get("metadata") or {}))

    @classmethod
    def from_values(cls, values: list[Any], data_type: str = "any") -> List:
        """Create from raw values."""
        return cls(items=[Item.from_any(v, data_type) for v in values])

    @classmethod
    def empty(cls) -> List:
        """Create empty list."""
        return cls(items=[])


@dataclass
class Tree:
    """A collection of branches, where each branch is a list (2D+ data structure).

    Tree is the most complex data structure in the system. It represents
    a collection of named branches, where each branch contains a list of items.

    Branches are identified by Path, which is a tuple of integers.
    For example:
    - (0,) is the first branch
    - (1,) is the second branch
    - (0, 0) is the first sub-branch of the first branch
    """

    branches: dict[Path, List] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if self.branches is None:
            object.__setattr__(self, "branches", {})

    def __len__(self) -> int:
        """Get number of branches."""
        return len(self.branches)

    def __getitem__(self, path: Path) -> List:
        """Get branch at path."""
        return self.branches[path]

    def __setitem__(self, path: Path, value: List):
        """Set branch at path."""
        self.branches[path] = value

    def __contains__(self, path: Path) -> bool:
        """Check if path exists."""
        return path in self.branches

    def __iter__(self) -> Iterator[Path]:
        """Iterate over paths."""
        return iter(self.branches.keys())

    def __str__(self) -> str:
        return f"Tree({len(self.branches)} branches)"

    def __repr__(self) -> str:
        return f"Tree(branches={self.branches!r})"

    @property
    def branch_count(self) -> int:
        """Get number of branches."""
        return len(self.branches)

    @property
    def total_items(self) -> int:
        """Get total number of items across all branches."""
        return sum(len(branch) for branch in self.branches.values())

    @property
    def paths(self) -> list[Path]:
        """Get all paths sorted."""
        return sorted(self.branches.keys())

    @property
    def is_empty(self) -> bool:
        """Check if tree is empty."""
        return len(self.branches) == 0

    @property
    def depth(self) -> int:
        """Get maximum path depth."""
        if not self.branches:
            return 0
        return max(len(path) for path in self.branches.keys())

    def get_branch(self, path: Path) -> List | None:
        """Get branch at path, or None if not found."""
        return self.branches.get(path)

    def set_branch(self, path: Path, branch: List) -> None:
        """Set branch at path."""
        self.branches[path] = branch

    def add_branch(self, path: Path, items: list[Any] = None) -> None:
        """Add a new branch."""
        if items is None:
            items = []
        self.branches[path] = List.from_values(items)

    def remove_branch(self, path: Path) -> None:
        """Remove branch at path."""
        if path in self.branches:
            del self.branches[path]

    def has_path(self, path: Path) -> bool:
        """Check if path exists."""
        return path in self.branches

    def get_item(self, path: Path, index: int) -> Item | None:
        """Get item at specific path and index."""
        branch = self.get_branch(path)
        if branch is None or index >= len(branch):
            return None
        return branch[index]

    def set_item(self, path: Path, index: int, value: Any) -> None:
        """Set item at specific path and index."""
        if path not in self.branches:
            self.branches[path] = List.empty()
        branch = self.branches[path]
        if index < len(branch):
            branch[index] = Item.from_any(value)
        else:
            branch.append(value)

    def to_flat_list(self) -> List:
        """Convert tree to flat list (flatten)."""
        all_items = []
        for path in self.paths:
            all_items.extend(self.branches[path].items)
        return List(items=all_items)

    def to_list(self) -> List:
        """Alias for to_flat_list."""
        return self.to_flat_list()

    def get_branch_lengths(self) -> dict[Path, int]:
        """Get length of each branch."""
        return {path: len(branch) for path, branch in self.branches.items()}

    def get_max_branch_length(self) -> int:
        """Get maximum branch length."""
        if not self.branches:
            return 0
        return max(len(branch) for branch in self.branches.values())

    def get_min_branch_length(self) -> int:
        """Get minimum branch length."""
        if not self.branches:
            return 0
        return min(len(branch) for branch in self.branches.values())

    def simplify(self) -> Tree:
        """Simplify tree by removing unnecessary path indices."""
        return simplify_tree(self)

    def graft(self) -> Tree:
        """Graft: each item becomes its own branch."""
        return graft_tree(self)

    def flatten(self, depth: int = -1) -> Tree:
        """Flatten tree structure."""
        return flatten_tree(self, depth)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "branches": {str(list(path)): branch.to_dict() for path, branch in self.branches.items()},
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tree:
        """Create from dictionary."""
        branches = {}
        for path_str, branch_data in data.get("branches", {}).items():
            # Parse path string like "[0, 1]" to tuple (0, 1)
            path = tuple(int(x) for x in path_str.strip("[]").split(",") if x.strip())
            branches[path] = List.from_dict(branch_data)
        return cls(branches=branches, metadata=dict(data.get("metadata") or {}))

    @classmethod
    def from_list(cls, lst: List) -> Tree:
        """Create tree from single list (single branch at path (0,))."""
        return cls(branches={(0,): lst})

    @classmethod
    def from_lists(cls, lists: list[List]) -> Tree:
        """Create tree from multiple lists."""
        branches = {}
        for i, lst in enumerate(lists):
            branches[(i,)] = lst
        return cls(branches=branches)

    @classmethod
    def from_values(cls, values: list[list[Any]]) -> Tree:
        """Create tree from nested values."""
        branches = {}
        for i, branch_values in enumerate(values):
            branches[(i,)] = List.from_values(branch_values)
        return cls(branches=branches)

    @classmethod
    def empty(cls) -> Tree:
        """Create empty tree."""
        return cls(branches={})


# ── Data Structure Operations ──────────────────────────────────────────────


def graft_tree(tree: Tree) -> Tree:
    """Graft a tree: each item becomes its own branch.

    Example:
        Tree with branch (0,): [1, 2, 3]
        After grafting:
            (0, 0): [1]
            (0, 1): [2]
            (0, 2): [3]
    """
    new_branches = {}
    for path, branch in tree.branches.items():
        for i, item in enumerate(branch):
            new_path = path + (i,)
            new_branches[new_path] = List.from_values([item.value])
    return Tree(branches=new_branches, metadata=dict(tree.metadata))


def flatten_tree(tree: Tree, depth: int = -1) -> Tree:
    """Flatten a tree structure.

    Args:
        tree: The tree to flatten
        depth: How many levels to flatten (-1 for all)

    Example:
        Tree with branches:
            (0, 0): [1, 2]
            (0, 1): [3, 4]
            (1, 0): [5, 6]
        After flattening (depth=1):
            (0,): [1, 2, 3, 4]
            (1,): [5, 6]
    """
    if depth == 0:
        return tree

    # Check if tree has any nested paths (depth > 1)
    has_nested = any(len(path) > 1 for path in tree.branches.keys())
    if not has_nested:
        return tree

    # Group branches by their first index
    groups: dict[int, list[tuple[Path, List]]] = defaultdict(list)
    for path, branch in tree.branches.items():
        first_idx = path[0]
        rest = path[1:] if len(path) > 1 else ()
        groups[first_idx].append((rest, branch))

    new_branches = {}
    for first_idx, items in groups.items():
        if all(rest == () for rest, _ in items):
            # All items are at this level, just merge
            all_items = []
            for _, branch in items:
                all_items.extend(branch.items)
            new_branches[(first_idx,)] = List(items=all_items)
        else:
            # Collect all items from sub-branches
            all_items = []
            for _, branch in items:
                all_items.extend(branch.items)
            new_branches[(first_idx,)] = List(items=all_items)

    result = Tree(branches=new_branches, metadata=dict(tree.metadata))

    # Continue flattening if needed
    if depth == -1 or depth > 1:
        next_depth = depth - 1 if depth > 0 else -1
        # Check if we made progress
        if len(result.branches) < len(tree.branches):
            return flatten_tree(result, next_depth)

    return result


def simplify_tree(tree: Tree) -> Tree:
    """Simplify tree by removing unnecessary path indices.

    If all branches have the same content, merge them.
    """
    if not tree.branches:
        return tree

    # Check if all branches are identical
    branches = list(tree.branches.values())
    if all(b == branches[0] for b in branches):
        return Tree(branches={(0,): branches[0]}, metadata=dict(tree.metadata))

    return tree


def cross_reference_trees(tree1: Tree, tree2: Tree) -> tuple[Tree, Tree]:
    """Cross reference two trees: create all combinations.

    Example:
        Tree1: (0,): [A, B]
        Tree2: (0,): [1, 2]
        Result:
            Tree1: (0,): [A, A, B, B]
            Tree2: (0,): [1, 2, 1, 2]
    """
    # Flatten both trees
    flat1 = tree1.to_flat_list()
    flat2 = tree2.to_flat_list()

    # Cross reference the lists
    result1_items = []
    result2_items = []

    for item1 in flat1:
        for item2 in flat2:
            result1_items.append(item1)
            result2_items.append(item2)

    result1 = Tree.from_list(List(items=result1_items))
    result2 = Tree.from_list(List(items=result2_items))

    return result1, result2


def zip_trees(tree1: Tree, tree2: Tree) -> Tree:
    """Zip two trees together.

    Example:
        Tree1: (0,): [A, B, C]
        Tree2: (0,): [1, 2, 3]
        Result: (0,): [(A,1), (B,2), (C,3)]
    """
    new_branches = {}

    # Get common paths
    common_paths = set(tree1.paths) & set(tree2.paths)

    for path in sorted(common_paths):
        branch1 = tree1[path]
        branch2 = tree2[path]

        # Zip items
        zipped_items = []
        for item1, item2 in zip(branch1, branch2):
            zipped_items.append(Item.from_any((item1.value, item2.value)))

        new_branches[path] = List(items=zipped_items)

    return Tree(branches=new_branches)


def longest_list_operation(lists: list[List]) -> list[List]:
    """Align lists to the longest length (repeat last item).

    Example:
        [1, 2, 3] and [A, B]
        Result: [1, 2, 3] and [A, B, B]
    """
    if not lists:
        return []

    max_len = max(len(lst) for lst in lists)

    result = []
    for lst in lists:
        if len(lst) == 0:
            result.append(lst)
            continue

        # Repeat last item to match max length
        items = list(lst.items)
        while len(items) < max_len:
            items.append(items[-1])
        result.append(List(items=items))

    return result


def shortest_list_operation(lists: list[List]) -> list[List]:
    """Align lists to the shortest length (truncate).

    Example:
        [1, 2, 3] and [A, B]
        Result: [1, 2] and [A, B]
    """
    if not lists:
        return []

    min_len = min(len(lst) for lst in lists)

    return [lst.slice(0, min_len) for lst in lists]


def cycle_list_operation(lists: list[List], target_length: int) -> list[List]:
    """Cycle lists to reach target length.

    Example:
        [1, 2] cycled to length 5
        Result: [1, 2, 1, 2, 1]
    """
    result = []
    for lst in lists:
        if len(lst) == 0:
            result.append(lst)
            continue

        items = []
        for i in range(target_length):
            items.append(lst.items[i % len(lst)])
        result.append(List(items=items))

    return result


def cross_reference_operation(lists: list[List]) -> list[List]:
    """Cross reference: create all combinations.

    Example:
        [A, B] and [1, 2]
        Result: [A, A, B, B] and [1, 2, 1, 2]
    """
    if len(lists) < 2:
        return lists

    # Calculate total combinations
    total = 1
    for lst in lists:
        total *= len(lst)

    result = []
    for lst in lists:
        # Build pattern: repeat each item for the number of combinations of remaining lists
        items = []
        for item in lst.items:
            # Calculate how many times to repeat this item
            repeat_count = total // len(lst)
            items.extend([item] * repeat_count)
        result.append(List(items=items))

    return result


# ── Scalar Operations (List + Item) ────────────────────────────────────────


def broadcast_operation(lst: List, item: Item, operation: str) -> List:
    """Apply operation between a list and a scalar item.

    This broadcasts the item to match the list length, then applies
    the operation element-wise.

    Args:
        lst: The list
        item: The scalar item
        operation: Operation type ('add', 'sub', 'mul', 'div', 'mod', 'pow',
                   'eq', 'ne', 'gt', 'lt', 'ge', 'le', 'and', 'or')

    Returns:
        New list with operation results

    Examples:
        [1, 2, 3] + 5 = [6, 7, 8]
        [10, 20, 30] / 10 = [1.0, 2.0, 3.0]
        [1, 2, 3] > 2 = [False, False, True]
    """
    result_items = []
    for list_item in lst.items:
        result_value = _apply_operation(list_item.value, item.value, operation)
        result_items.append(Item.from_any(result_value))
    return List(items=result_items)


def broadcast_operation_reverse(item: Item, lst: List, operation: str) -> List:
    """Apply operation between a scalar item and a list.

    Args:
        item: The scalar item
        lst: The list
        operation: Operation type

    Returns:
        New list with operation results

    Examples:
        10 - [1, 2, 3] = [9, 8, 7]
    """
    result_items = []
    for list_item in lst.items:
        result_value = _apply_operation(item.value, list_item.value, operation)
        result_items.append(Item.from_any(result_value))
    return List(items=result_items)


def list_element_operation(lst: List, operation: str) -> List:
    """Apply unary operation to each element in the list.

    Args:
        lst: The list
        operation: Operation type ('abs', 'neg', 'sqrt', 'floor', 'ceil', 'round', 'str', 'int', 'float')

    Returns:
        New list with operation results
    """
    result_items = []
    for item in lst.items:
        result_value = _apply_unary_operation(item.value, operation)
        result_items.append(Item.from_any(result_value))
    return List(items=result_items)


def _apply_operation(a: Any, b: Any, operation: str) -> Any:
    """Apply binary operation between two values."""
    try:
        if operation == "add":
            return a + b
        elif operation == "sub":
            return a - b
        elif operation == "mul":
            return a * b
        elif operation == "div":
            if b == 0:
                return None  # Division by zero
            return a / b
        elif operation == "mod":
            if b == 0:
                return None
            return a % b
        elif operation == "pow":
            return a**b
        elif operation == "eq":
            return a == b
        elif operation == "ne":
            return a != b
        elif operation == "gt":
            return a > b
        elif operation == "lt":
            return a < b
        elif operation == "ge":
            return a >= b
        elif operation == "le":
            return a <= b
        elif operation == "and":
            return bool(a) and bool(b)
        elif operation == "or":
            return bool(a) or bool(b)
        elif operation == "xor":
            return bool(a) != bool(b)
        else:
            return None
    except Exception:
        return None


def _apply_unary_operation(value: Any, operation: str) -> Any:
    """Apply unary operation to a value."""
    try:
        if operation == "abs":
            return abs(value)
        elif operation == "neg":
            return -value
        elif operation == "sqrt":
            import math

            return math.sqrt(value)
        elif operation == "floor":
            import math

            return math.floor(value)
        elif operation == "ceil":
            import math

            return math.ceil(value)
        elif operation == "round":
            return round(value)
        elif operation == "str":
            return str(value)
        elif operation == "int":
            return int(value)
        elif operation == "float":
            return float(value)
        elif operation == "bool":
            return bool(value)
        elif operation == "not":
            return not bool(value)
        elif operation == "len":
            return len(value)
        else:
            return value
    except Exception:
        return value


# ── Arithmetic Operations on Data Structures ───────────────────────────────


def add_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Add two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "add")


def sub_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Subtract two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "sub")


def mul_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Multiply two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "mul")


def div_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Divide two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "div")


def mod_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Modulo two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "mod")


def pow_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Power of two data structures (supports broadcasting)."""
    return _binary_data_operation(a, b, "pow")


def eq_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check equality of two data structures."""
    return _binary_data_operation(a, b, "eq")


def ne_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check inequality of two data structures."""
    return _binary_data_operation(a, b, "ne")


def gt_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check greater than."""
    return _binary_data_operation(a, b, "gt")


def lt_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check less than."""
    return _binary_data_operation(a, b, "lt")


def ge_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check greater or equal."""
    return _binary_data_operation(a, b, "ge")


def le_data(a: Item | List | Tree, b: Item | List | Tree) -> Item | List | Tree:
    """Check less or equal."""
    return _binary_data_operation(a, b, "le")


def _binary_data_operation(a: Item | List | Tree, b: Item | List | Tree, operation: str) -> Item | List | Tree:
    """Apply binary operation between two data structures with broadcasting."""

    # Get data types
    type_a = get_data_type(a)
    type_b = get_data_type(b)

    # Case 1: Both are Items
    if type_a == DataType.ITEM and type_b == DataType.ITEM:
        result_value = _apply_operation(a.value, b.value, operation)
        return Item.from_any(result_value)

    # Case 2: Item and List (broadcast item to list)
    if type_a == DataType.ITEM and type_b == DataType.LIST:
        return broadcast_operation(b, a, operation)

    # Case 3: List and Item (broadcast item to list)
    if type_a == DataType.LIST and type_b == DataType.ITEM:
        return broadcast_operation(a, b, operation)

    # Case 4: Both are Lists
    if type_a == DataType.LIST and type_b == DataType.LIST:
        return _list_list_operation(a, b, operation)

    # Case 5: Item and Tree (broadcast item to tree)
    if type_a == DataType.ITEM and type_b == DataType.TREE:
        return _broadcast_item_to_tree(a, b, operation)

    # Case 6: Tree and Item (broadcast item to tree)
    if type_a == DataType.TREE and type_b == DataType.ITEM:
        return _broadcast_item_to_tree(b, a, operation, reverse=True)

    # Case 7: List and Tree (convert list to tree, then operate)
    if type_a == DataType.LIST and type_b == DataType.TREE:
        tree_a = Tree.from_list(a)
        return _tree_tree_operation(tree_a, b, operation)

    # Case 8: Tree and List (convert list to tree, then operate)
    if type_a == DataType.TREE and type_b == DataType.LIST:
        tree_b = Tree.from_list(b)
        return _tree_tree_operation(a, tree_b, operation)

    # Case 9: Both are Trees
    if type_a == DataType.TREE and type_b == DataType.TREE:
        return _tree_tree_operation(a, b, operation)

    # Fallback
    return a


def _list_list_operation(lst1: List, lst2: List, operation: str) -> List:
    """Apply operation between two lists (element-wise with alignment)."""
    # Align lists to same length
    aligned1, aligned2 = align_data(lst1, lst2, strategy=AlignmentStrategy.LONGEST)

    result_items = []
    for item1, item2 in zip(aligned1, aligned2):
        result_value = _apply_operation(item1.value, item2.value, operation)
        result_items.append(Item.from_any(result_value))

    return List(items=result_items)


def _broadcast_item_to_tree(item: Item, tree: Tree, operation: str, reverse: bool = False) -> Tree:
    """Broadcast an item to all branches of a tree."""
    new_branches = {}
    for path, branch in tree.branches.items():
        if reverse:
            new_branch = broadcast_operation_reverse(item, branch, operation)
        else:
            new_branch = broadcast_operation(branch, item, operation)
        new_branches[path] = new_branch

    return Tree(branches=new_branches, metadata=dict(tree.metadata))


def _tree_tree_operation(tree1: Tree, tree2: Tree, operation: str) -> Tree:
    """Apply operation between two trees."""
    new_branches = {}

    # Get common paths
    common_paths = set(tree1.paths) & set(tree2.paths)

    for path in sorted(common_paths):
        branch1 = tree1[path]
        branch2 = tree2[path]
        new_branch = _list_list_operation(branch1, branch2, operation)
        new_branches[path] = new_branch

    return Tree(branches=new_branches)


# ── Unary Operations ───────────────────────────────────────────────────────


def abs_data(data: Item | List | Tree) -> Item | List | Tree:
    """Absolute value."""
    return _unary_data_operation(data, "abs")


def neg_data(data: Item | List | Tree) -> Item | List | Tree:
    """Negate."""
    return _unary_data_operation(data, "neg")


def sqrt_data(data: Item | List | Tree) -> Item | List | Tree:
    """Square root."""
    return _unary_data_operation(data, "sqrt")


def _unary_data_operation(data: Item | List | Tree, operation: str) -> Item | List | Tree:
    """Apply unary operation to data structure."""
    data_type = get_data_type(data)

    if data_type == DataType.ITEM:
        result_value = _apply_unary_operation(data.value, operation)
        return Item.from_any(result_value)

    if data_type == DataType.LIST:
        return list_element_operation(data, operation)

    if data_type == DataType.TREE:
        new_branches = {}
        for path, branch in data.branches.items():
            new_branches[path] = list_element_operation(branch, operation)
        return Tree(branches=new_branches, metadata=dict(data.metadata))

    return data


# ── Alignment Functions ────────────────────────────────────────────────────


def align_data(*data: List | Tree, strategy: AlignmentStrategy = AlignmentStrategy.LONGEST) -> tuple[List | Tree, ...]:
    """Align multiple data structures using the specified strategy.

    Args:
        *data: Data structures to align
        strategy: Alignment strategy

    Returns:
        Aligned data structures
    """
    if not data:
        return ()

    # Convert all to lists for alignment
    lists = []
    for d in data:
        if isinstance(d, Tree):
            lists.append(d.to_flat_list())
        else:
            lists.append(d)

    # Apply strategy
    if strategy == AlignmentStrategy.SHORTEST:
        aligned = shortest_list_operation(lists)
    elif strategy == AlignmentStrategy.LONGEST:
        aligned = longest_list_operation(lists)
    elif strategy == AlignmentStrategy.CYCLE:
        max_len = max(len(lst) for lst in lists)
        aligned = cycle_list_operation(lists, max_len)
    elif strategy == AlignmentStrategy.CROSS:
        aligned = cross_reference_operation(lists)
    else:
        aligned = lists

    # Convert back to original types
    result = []
    for original, aligned_item in zip(data, aligned):
        if isinstance(original, Tree):
            result.append(Tree.from_list(aligned_item))
        else:
            result.append(aligned_item)

    return tuple(result)


# ── Utility Functions ──────────────────────────────────────────────────────


def item_to_list(item: Item) -> List:
    """Convert single item to list."""
    return List.from_values([item.value])


def list_to_tree(lst: List) -> Tree:
    """Convert list to tree (single branch)."""
    return Tree.from_list(lst)


def tree_to_list(tree: Tree) -> List:
    """Convert tree to flat list."""
    return tree.to_flat_list()


def ensure_list(data: Item | List | Tree) -> List:
    """Ensure data is a list."""
    if isinstance(data, Item):
        return item_to_list(data)
    elif isinstance(data, Tree):
        return tree_to_list(data)
    return data


def ensure_tree(data: Item | List | Tree) -> Tree:
    """Ensure data is a tree."""
    if isinstance(data, Item):
        return Tree.from_list(item_to_list(data))
    elif isinstance(data, List):
        return Tree.from_list(data)
    return data


def get_data_type(data: Item | List | Tree) -> DataType:
    """Get the data type of a data structure."""
    if isinstance(data, Item):
        return DataType.ITEM
    elif isinstance(data, List):
        return DataType.LIST
    elif isinstance(data, Tree):
        return DataType.TREE
    return DataType.ITEM
