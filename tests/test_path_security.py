import pytest

from core.path_security import UnsafePathError, resolve_under, safe_rmtree_child


def test_resolve_under_accepts_child(tmp_path):
    child = tmp_path / "child" / "file.txt"

    assert resolve_under(tmp_path, child) == child.resolve(strict=False)


def test_resolve_under_rejects_parent_escape(tmp_path):
    with pytest.raises(UnsafePathError):
        resolve_under(tmp_path / "root", tmp_path / "outside")


def test_safe_rmtree_child_refuses_root(tmp_path):
    with pytest.raises(UnsafePathError):
        safe_rmtree_child(tmp_path, tmp_path)


def test_safe_rmtree_child_removes_directory(tmp_path):
    target = tmp_path / "cache"
    target.mkdir()
    (target / "x.txt").write_text("x", encoding="utf-8")

    safe_rmtree_child(tmp_path, target)

    assert not target.exists()


def test_safe_rmtree_child_refuses_symlink_even_when_target_is_inside_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available on this system")

    with pytest.raises(UnsafePathError):
        safe_rmtree_child(tmp_path, link)

    assert link.exists()
    assert real.exists()
