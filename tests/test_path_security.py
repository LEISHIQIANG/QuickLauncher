import os
import subprocess
import tempfile

import pytest

from core.path_security import (
    UnsafePathError,
    assert_safe_user_path,
    is_link_or_reparse_point,
    resolve_under,
    safe_rmtree_child,
)

pytestmark = pytest.mark.integration


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


def test_safe_rmtree_child_refuses_link_even_when_target_is_inside_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(real)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
    else:
        link.symlink_to(real, target_is_directory=True)

    assert is_link_or_reparse_point(link) is True

    with pytest.raises(UnsafePathError):
        safe_rmtree_child(tmp_path, link)

    assert link.exists()
    assert real.exists()


def test_assert_safe_user_path_refuses_temp_root():
    with pytest.raises(UnsafePathError):
        assert_safe_user_path(tempfile.gettempdir(), operation="delete")


def test_assert_safe_user_path_allows_temp_child():
    child = os.path.join(tempfile.gettempdir(), "quicklauncher-safe-child", "item.txt")

    assert assert_safe_user_path(child, operation="write file") == resolve_under(tempfile.gettempdir(), child)


# ── Additional coverage tests ──────────────────────────────────────────────


def test_is_safe_child_valid(tmp_path):
    from core.path_security import is_safe_child

    child = tmp_path / "child" / "file.txt"
    assert is_safe_child(tmp_path, child) is True


def test_is_safe_child_invalid_outside(tmp_path):
    from core.path_security import is_safe_child

    outside = tmp_path / "outside"
    assert is_safe_child(tmp_path / "root", outside) is False


def test_is_safe_child_same_as_root(tmp_path):
    from core.path_security import is_safe_child

    assert is_safe_child(tmp_path, tmp_path, allow_root=False) is False
    assert is_safe_child(tmp_path, tmp_path, allow_root=True) is True


def test_is_safe_child_exception_returns_false():
    from core.path_security import is_safe_child

    # Passing None to trigger TypeError/Exception
    assert is_safe_child(None, "child") is False


def test_resolve_under_allow_root(tmp_path):
    from core.path_security import resolve_under

    assert resolve_under(tmp_path, tmp_path, allow_root=True) == tmp_path.resolve(strict=False)


def test_safe_rmtree_child_missing_ok(tmp_path):
    from core.path_security import safe_rmtree_child

    non_existent = tmp_path / "nonexistent"
    # Should not raise since missing_ok is True
    safe_rmtree_child(tmp_path, non_existent, missing_ok=True)


def test_safe_rmtree_child_missing_raises_file_not_found(tmp_path):
    from core.path_security import safe_rmtree_child

    non_existent = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError):
        safe_rmtree_child(tmp_path, non_existent, missing_ok=False)


def test_safe_rmtree_child_unlinks_single_file(tmp_path):
    from core.path_security import safe_rmtree_child

    f = tmp_path / "file.txt"
    f.write_text("hello", encoding="utf-8")
    assert f.exists()

    safe_rmtree_child(tmp_path, f)
    assert not f.exists()
