"""Equivalence tests for QLcrypto native hashing DLL.

Validates that QLcrypto.dll produces identical results to Python's hashlib
across algorithms, file sizes, and edge cases.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from core.native_services import hash_file

_SKIP_REASON = "QLcrypto.dll not available (requires Windows + built DLL)"


def _dll_available() -> bool:
    try:
        from bootstrap.native_loader import QLcrypto

        QLcrypto()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _dll_available(), reason=_SKIP_REASON)

ALGORITHMS = ["md5", "sha1", "sha256"]
TEST_SIZES = [0, 1, 256, 1024, 4096, 65536, 1024 * 1024, 4 * 1024 * 1024 + 17]


def _make_file(tmp_path: Path, size: int, name: str = "test.bin") -> Path:
    """Create a temp file with deterministic content."""
    p = tmp_path / name
    data = bytes((i * 7 + 13) & 0xFF for i in range(size))
    p.write_bytes(data)
    return p


@pytest.mark.parametrize("algo", ALGORITHMS)
@pytest.mark.parametrize("size", TEST_SIZES)
def test_hash_equivalence(tmp_path: Path, algo: str, size: int):
    """Native hash must match hashlib exactly."""
    p = _make_file(tmp_path, size)
    expected = hashlib.new(algo, p.read_bytes()).hexdigest()
    actual = hash_file(p, algo)
    assert actual == expected, f"{algo} mismatch for size {size}"


def test_hash_unicode_path(tmp_path: Path):
    """Paths with CJK characters and spaces must work."""
    p = tmp_path / "测试 文件.txt"
    p.write_bytes(b"unicode path content")
    expected = hashlib.sha256(b"unicode path content").hexdigest()
    assert hash_file(p, "sha256") == expected


def test_hash_long_path(tmp_path: Path):
    """Paths longer than MAX_PATH should still work via long-path prefix."""
    long_name = "a" * 200 + ".dat"
    deep_dir = tmp_path
    for i in range(5):
        deep_dir = deep_dir / f"subdir_{i}_{long_name[:30]}"
    deep_dir.mkdir(parents=True, exist_ok=True)
    p = deep_dir / long_name
    p.write_bytes(b"long path test data")
    expected = hashlib.sha256(b"long path test data").hexdigest()
    assert hash_file(p, "sha256") == expected


def test_hash_max_bytes_truncation(tmp_path: Path):
    """max_bytes must truncate the input consistently with Python."""
    p = _make_file(tmp_path, 1024)
    data = p.read_bytes()
    native = hash_file(p, "sha256", max_bytes=100)
    expected = hashlib.sha256(data[:100]).hexdigest()
    assert native == expected


def test_hash_max_bytes_zero_means_all(tmp_path: Path):
    """max_bytes=0 means unlimited — must hash the entire file."""
    p = _make_file(tmp_path, 2048)
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    assert hash_file(p, "sha256", max_bytes=0) == expected


def test_hash_invalid_algorithm(tmp_path: Path):
    """Unsupported algorithm must raise ValueError."""
    p = _make_file(tmp_path, 16)
    with pytest.raises(ValueError, match="不支持"):
        hash_file(p, "blake2b")


def test_hash_nonexistent_file(tmp_path: Path):
    """Missing file must raise OSError."""
    p = tmp_path / "does_not_exist.bin"
    with pytest.raises(OSError):
        hash_file(p, "sha256")


def test_hash_empty_file(tmp_path: Path):
    """Empty file must produce the known empty-file digests."""
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    assert hash_file(p, "md5") == hashlib.md5(b"").hexdigest()
    assert hash_file(p, "sha256") == hashlib.sha256(b"").hexdigest()


@pytest.mark.slow
def test_hash_large_file_performance(tmp_path: Path):
    """Benchmark: native should be faster than Python for a 10 MiB file."""
    size = 10 * 1024 * 1024
    p = tmp_path / "large.bin"
    p.write_bytes(os.urandom(size))

    t0 = time.perf_counter()
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    py_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    actual = hash_file(p, "sha256")
    native_time = time.perf_counter() - t0

    assert actual == expected
    print(f"\nPython: {py_time*1000:.1f}ms  Native: {native_time*1000:.1f}ms  Speedup: {py_time/native_time:.1f}x")
