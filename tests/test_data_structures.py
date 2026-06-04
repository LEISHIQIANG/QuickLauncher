"""Tests for action chain data structures."""

import pytest

from core.chain.data_structures import (
    AlignmentStrategy,
    DataType,
    Item,
    List,
    Tree,
    align_data,
    cross_reference_operation,
    cross_reference_trees,
    cycle_list_operation,
    ensure_list,
    ensure_tree,
    flatten_tree,
    get_data_type,
    graft_tree,
    longest_list_operation,
    shortest_list_operation,
    simplify_tree,
    zip_trees,
)


class TestItem:
    """Test Item data structure."""

    def test_create_item(self):
        """Test creating an item."""
        item = Item(value=42)
        assert item.value == 42
        assert item.data_type == "any"

    def test_create_item_with_type(self):
        """Test creating an item with type."""
        item = Item(value="hello", data_type="text")
        assert item.value == "hello"
        assert item.data_type == "text"

    def test_item_str(self):
        """Test item string representation."""
        item = Item(value=42)
        assert str(item) == "42"

    def test_item_eq(self):
        """Test item equality."""
        item1 = Item(value=42)
        item2 = Item(value=42)
        item3 = Item(value=43)
        assert item1 == item2
        assert item1 != item3
        assert item1 == 42

    def test_item_hash(self):
        """Test item hashing."""
        item = Item(value=42)
        assert hash(item) == hash(42)

    def test_item_from_any(self):
        """Test creating item from any value."""
        item = Item.from_any(42)
        assert item.value == 42
        assert item.data_type == "any"

    def test_item_from_item(self):
        """Test creating item from item."""
        original = Item(value=42, data_type="number")
        copy = Item.from_any(original)
        assert copy is original

    def test_item_to_dict(self):
        """Test item to dictionary."""
        item = Item(value=42, data_type="number")
        d = item.to_dict()
        assert d["value"] == 42
        assert d["data_type"] == "number"

    def test_item_from_dict(self):
        """Test creating item from dictionary."""
        d = {"value": 42, "data_type": "number"}
        item = Item.from_dict(d)
        assert item.value == 42
        assert item.data_type == "number"


class TestList:
    """Test List data structure."""

    def test_create_list(self):
        """Test creating a list."""
        lst = List.from_values([1, 2, 3])
        assert len(lst) == 3
        assert lst[0].value == 1
        assert lst[1].value == 2
        assert lst[2].value == 3

    def test_create_empty_list(self):
        """Test creating an empty list."""
        lst = List.empty()
        assert len(lst) == 0
        assert lst.is_empty

    def test_list_length(self):
        """Test list length."""
        lst = List.from_values([1, 2, 3])
        assert lst.length == 3

    def test_list_first_last(self):
        """Test list first and last."""
        lst = List.from_values([1, 2, 3])
        assert lst.first.value == 1
        assert lst.last.value == 3

    def test_list_append(self):
        """Test list append."""
        lst = List.empty()
        lst.append(1)
        lst.append(2)
        assert len(lst) == 2
        assert lst[0].value == 1
        assert lst[1].value == 2

    def test_list_extend(self):
        """Test list extend."""
        lst1 = List.from_values([1, 2])
        lst2 = List.from_values([3, 4])
        lst1.extend(lst2)
        assert len(lst1) == 4

    def test_list_contains(self):
        """Test list contains."""
        lst = List.from_values([1, 2, 3])
        assert 2 in lst
        assert 4 not in lst

    def test_list_reverse(self):
        """Test list reverse."""
        lst = List.from_values([1, 2, 3])
        reversed_lst = lst.reverse()
        assert reversed_lst.to_values() == [3, 2, 1]

    def test_list_sort(self):
        """Test list sort."""
        lst = List.from_values([3, 1, 2])
        sorted_lst = lst.sort()
        assert sorted_lst.to_values() == [1, 2, 3]

    def test_list_unique(self):
        """Test list unique."""
        lst = List.from_values([1, 2, 2, 3, 3, 3])
        unique_lst = lst.unique()
        assert unique_lst.to_values() == [1, 2, 3]

    def test_list_slice(self):
        """Test list slice."""
        lst = List.from_values([1, 2, 3, 4, 5])
        sliced = lst.slice(1, 4)
        assert sliced.to_values() == [2, 3, 4]

    def test_list_map(self):
        """Test list map."""
        lst = List.from_values([1, 2, 3])
        mapped = lst.map(lambda x: x * 2)
        assert mapped.to_values() == [2, 4, 6]

    def test_list_filter(self):
        """Test list filter."""
        lst = List.from_values([1, 2, 3, 4, 5])
        filtered = lst.filter(lambda x: x > 3)
        assert filtered.to_values() == [4, 5]

    def test_list_reduce(self):
        """Test list reduce."""
        lst = List.from_values([1, 2, 3, 4])
        result = lst.reduce(lambda a, b: a + b)
        assert result == 10

    def test_list_add(self):
        """Test list concatenation."""
        lst1 = List.from_values([1, 2])
        lst2 = List.from_values([3, 4])
        result = lst1 + lst2
        assert result.to_values() == [1, 2, 3, 4]

    def test_list_mul(self):
        """Test list repetition."""
        lst = List.from_values([1, 2])
        result = lst * 3
        assert result.to_values() == [1, 2, 1, 2, 1, 2]

    def test_list_to_dict(self):
        """Test list to dictionary."""
        lst = List.from_values([1, 2, 3])
        d = lst.to_dict()
        assert len(d["items"]) == 3

    def test_list_from_dict(self):
        """Test list from dictionary."""
        d = {
            "items": [
                {"value": 1, "data_type": "any"},
                {"value": 2, "data_type": "any"},
            ]
        }
        lst = List.from_dict(d)
        assert len(lst) == 2
        assert lst[0].value == 1


class TestTree:
    """Test Tree data structure."""

    def test_create_tree(self):
        """Test creating a tree."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        assert tree.branch_count == 2
        assert tree.total_items == 4

    def test_create_empty_tree(self):
        """Test creating an empty tree."""
        tree = Tree.empty()
        assert tree.branch_count == 0
        assert tree.is_empty

    def test_tree_paths(self):
        """Test tree paths."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        paths = tree.paths
        assert (0,) in paths
        assert (1,) in paths

    def test_tree_get_branch(self):
        """Test getting tree branch."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        branch = tree.get_branch((0,))
        assert branch.to_values() == [1, 2]

    def test_tree_set_branch(self):
        """Test setting tree branch."""
        tree = Tree.empty()
        tree.set_branch((0,), List.from_values([1, 2]))
        assert tree.branch_count == 1

    def test_tree_add_branch(self):
        """Test adding tree branch."""
        tree = Tree.empty()
        tree.add_branch((0,), [1, 2])
        tree.add_branch((1,), [3, 4])
        assert tree.branch_count == 2

    def test_tree_remove_branch(self):
        """Test removing tree branch."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        tree.remove_branch((0,))
        assert tree.branch_count == 1

    def test_tree_to_flat_list(self):
        """Test tree to flat list."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        flat = tree.to_flat_list()
        assert flat.to_values() == [1, 2, 3, 4]

    def test_tree_depth(self):
        """Test tree depth."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        assert tree.depth == 1

    def test_tree_max_branch_length(self):
        """Test max branch length."""
        tree = Tree.from_values([[1, 2, 3], [4, 5]])
        assert tree.get_max_branch_length() == 3

    def test_tree_min_branch_length(self):
        """Test min branch length."""
        tree = Tree.from_values([[1, 2, 3], [4, 5]])
        assert tree.get_min_branch_length() == 2

    def test_tree_to_dict(self):
        """Test tree to dictionary."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        d = tree.to_dict()
        assert len(d["branches"]) == 2

    def test_tree_from_dict(self):
        """Test tree from dictionary."""
        d = {
            "branches": {
                "[0]": {"items": [{"value": 1}, {"value": 2}]},
                "[1]": {"items": [{"value": 3}, {"value": 4}]},
            }
        }
        tree = Tree.from_dict(d)
        assert tree.branch_count == 2

    def test_tree_from_list(self):
        """Test tree from list."""
        lst = List.from_values([1, 2, 3])
        tree = Tree.from_list(lst)
        assert tree.branch_count == 1
        assert tree.get_branch((0,)).to_values() == [1, 2, 3]


class TestTreeOperations:
    """Test tree operations."""

    def test_graft_tree(self):
        """Test grafting tree."""
        tree = Tree.from_values([[1, 2, 3]])
        grafted = graft_tree(tree)
        assert grafted.branch_count == 3
        assert grafted.get_branch((0, 0)).to_values() == [1]
        assert grafted.get_branch((0, 1)).to_values() == [2]
        assert grafted.get_branch((0, 2)).to_values() == [3]

    def test_flatten_tree(self):
        """Test flattening tree."""
        # Tree with single level should remain unchanged
        tree = Tree.from_values([[1, 2], [3, 4]])
        flat = flatten_tree(tree)
        assert flat.branch_count == 2
        assert flat.get_branch((0,)).to_values() == [1, 2]
        assert flat.get_branch((1,)).to_values() == [3, 4]

    def test_simplify_tree(self):
        """Test simplifying tree."""
        tree = Tree.from_values([[1, 2], [1, 2]])
        simplified = simplify_tree(tree)
        assert simplified.branch_count == 1

    def test_zip_trees(self):
        """Test zipping trees."""
        tree1 = Tree.from_values([[1, 2, 3]])
        tree2 = Tree.from_values([["a", "b", "c"]])
        zipped = zip_trees(tree1, tree2)
        branch = zipped.get_branch((0,))
        assert branch[0].value == (1, "a")
        assert branch[1].value == (2, "b")
        assert branch[2].value == (3, "c")

    def test_cross_reference_trees(self):
        """Test cross referencing trees."""
        tree1 = Tree.from_values([["A", "B"]])
        tree2 = Tree.from_values([[1, 2]])
        ref1, ref2 = cross_reference_trees(tree1, tree2)
        # Cross reference creates all combinations in a single branch
        assert ref1.branch_count == 1
        assert ref2.branch_count == 1
        assert ref1.get_branch((0,)).to_values() == ["A", "A", "B", "B"]
        assert ref2.get_branch((0,)).to_values() == [1, 2, 1, 2]


class TestListOperations:
    """Test list operations."""

    def test_longest_list_operation(self):
        """Test longest list operation."""
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values(["a", "b"])
        result = longest_list_operation([lst1, lst2])
        assert result[0].to_values() == [1, 2, 3]
        assert result[1].to_values() == ["a", "b", "b"]

    def test_shortest_list_operation(self):
        """Test shortest list operation."""
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values(["a", "b"])
        result = shortest_list_operation([lst1, lst2])
        assert result[0].to_values() == [1, 2]
        assert result[1].to_values() == ["a", "b"]

    def test_cycle_list_operation(self):
        """Test cycle list operation."""
        lst = List.from_values([1, 2])
        result = cycle_list_operation([lst], 5)
        assert result[0].to_values() == [1, 2, 1, 2, 1]

    def test_cross_reference_operation(self):
        """Test cross reference operation."""
        lst1 = List.from_values(["A", "B"])
        lst2 = List.from_values([1, 2])
        result = cross_reference_operation([lst1, lst2])
        # Cross reference: each item repeated for each combination
        assert result[0].to_values() == ["A", "A", "B", "B"]
        assert result[1].to_values() == [1, 1, 2, 2]


class TestAlignment:
    """Test data alignment."""

    def test_align_longest(self):
        """Test longest alignment."""
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values(["a", "b"])
        result = align_data(lst1, lst2, strategy=AlignmentStrategy.LONGEST)
        assert result[0].to_values() == [1, 2, 3]
        assert result[1].to_values() == ["a", "b", "b"]

    def test_align_shortest(self):
        """Test shortest alignment."""
        lst1 = List.from_values([1, 2, 3])
        lst2 = List.from_values(["a", "b"])
        result = align_data(lst1, lst2, strategy=AlignmentStrategy.SHORTEST)
        assert result[0].to_values() == [1, 2]
        assert result[1].to_values() == ["a", "b"]

    def test_align_cycle(self):
        """Test cycle alignment."""
        lst1 = List.from_values([1, 2])
        lst2 = List.from_values(["a", "b", "c"])
        result = align_data(lst1, lst2, strategy=AlignmentStrategy.CYCLE)
        assert result[0].to_values() == [1, 2, 1]
        assert result[1].to_values() == ["a", "b", "c"]

    def test_align_cross(self):
        """Test cross alignment."""
        lst1 = List.from_values(["A", "B"])
        lst2 = List.from_values([1, 2])
        result = align_data(lst1, lst2, strategy=AlignmentStrategy.CROSS)
        # Cross alignment: each item repeated for each combination
        assert result[0].to_values() == ["A", "A", "B", "B"]
        assert result[1].to_values() == [1, 1, 2, 2]


class TestUtilityFunctions:
    """Test utility functions."""

    def test_ensure_list_from_item(self):
        """Test ensure list from item."""
        item = Item(value=42)
        lst = ensure_list(item)
        assert len(lst) == 1
        assert lst[0].value == 42

    def test_ensure_list_from_tree(self):
        """Test ensure list from tree."""
        tree = Tree.from_values([[1, 2], [3, 4]])
        lst = ensure_list(tree)
        assert lst.to_values() == [1, 2, 3, 4]

    def test_ensure_tree_from_item(self):
        """Test ensure tree from item."""
        item = Item(value=42)
        tree = ensure_tree(item)
        assert tree.branch_count == 1
        assert tree.get_branch((0,)).to_values() == [42]

    def test_ensure_tree_from_list(self):
        """Test ensure tree from list."""
        lst = List.from_values([1, 2, 3])
        tree = ensure_tree(lst)
        assert tree.branch_count == 1
        assert tree.get_branch((0,)).to_values() == [1, 2, 3]

    def test_get_data_type(self):
        """Test get data type."""
        assert get_data_type(Item(value=42)) == DataType.ITEM
        assert get_data_type(List.from_values([1, 2])) == DataType.LIST
        assert get_data_type(Tree.from_values([[1, 2]])) == DataType.TREE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
