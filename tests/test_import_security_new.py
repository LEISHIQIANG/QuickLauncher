"""Tests for core.import_security module."""

import io
import zipfile

import pytest

from core.import_security import (
    UnsafeZipError,
    add_warning,
    build_safe_zip_index,
    has_report_warnings,
    has_zip_entry,
    is_allowed_background_path,
    is_allowed_icon_path,
    new_import_report,
    normalize_zip_name,
    read_zip_bytes,
    read_zip_text,
    set_imported_items,
    skip_file,
    skip_setting,
)

# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def test_new_import_report_structure():
    report = new_import_report()
    assert report["dry_run"] is False
    assert report["mode"] == ""
    assert report["skipped_files"] == []
    assert report["skipped_settings"] == []
    assert report["warnings"] == []
    assert report["imported_items"] == 0


def test_add_warning_with_valid_report():
    report = new_import_report()
    add_warning(report, "something wrong")
    assert "something wrong" in report["warnings"]


def test_add_warning_with_none_report():
    # Should not raise
    add_warning(None, "ignored")


def test_add_warning_empty_message():
    report = new_import_report()
    add_warning(report, "")
    assert report["warnings"] == []


def test_skip_file_with_valid_report():
    report = new_import_report()
    skip_file(report, "bad.txt", "corrupt")
    assert len(report["skipped_files"]) == 1
    assert report["skipped_files"][0] == {"name": "bad.txt", "reason": "corrupt"}
    assert len(report["warnings"]) == 1
    assert "bad.txt" in report["warnings"][0]


def test_skip_file_with_none_report():
    # Should not raise
    skip_file(None, "file.txt", "reason")


def test_skip_setting_with_valid_report():
    report = new_import_report()
    skip_setting(report, "theme", "invalid option")
    assert len(report["skipped_settings"]) == 1
    assert report["skipped_settings"][0] == {"name": "theme", "reason": "invalid option"}
    assert len(report["warnings"]) == 1


def test_skip_setting_with_none_report():
    skip_setting(None, "key", "reason")


def test_set_imported_items():
    report = new_import_report()
    set_imported_items(report, 42)
    assert report["imported_items"] == 42


def test_set_imported_items_none_report():
    set_imported_items(None, 10)


def test_has_report_warnings_empty():
    assert has_report_warnings(new_import_report()) is False


def test_has_report_warnings_none():
    assert has_report_warnings(None) is False


def test_has_report_warnings_with_warning():
    report = new_import_report()
    add_warning(report, "warn")
    assert has_report_warnings(report) is True


def test_has_report_warnings_with_skipped_file():
    report = new_import_report()
    report["skipped_files"].append({"name": "x", "reason": "y"})
    assert has_report_warnings(report) is True


def test_has_report_warnings_with_skipped_setting():
    report = new_import_report()
    report["skipped_settings"].append({"name": "x", "reason": "y"})
    assert has_report_warnings(report) is True


# ---------------------------------------------------------------------------
# UnsafeZipError
# ---------------------------------------------------------------------------


def test_unsafe_zip_error_is_value_error():
    with pytest.raises(UnsafeZipError):
        raise UnsafeZipError("test")


# ---------------------------------------------------------------------------
# normalize_zip_name
# ---------------------------------------------------------------------------


def test_normalize_empty_string():
    assert normalize_zip_name("") is None


def test_normalize_none_input():
    assert normalize_zip_name(None) is None


def test_normalize_whitespace_only():
    assert normalize_zip_name("   ") is None


def test_normalize_traversal_dotdot():
    assert normalize_zip_name("../etc/passwd") is None


def test_normalize_traversal_in_middle():
    assert normalize_zip_name("a/../b") is None


def test_normalize_absolute_path():
    assert normalize_zip_name("/etc/passwd") is None


def test_normalize_double_slash_absolute():
    assert normalize_zip_name("//server/share") is None


def test_normalize_drive_letter():
    assert normalize_zip_name("C:/windows/system32") is None


def test_normalize_null_byte():
    assert normalize_zip_name("file\x00name") is None


def test_normalize_backslash_path():
    result = normalize_zip_name("icons\\myicon.png")
    assert result == "icons/myicon.png"


def test_normalize_normal_path():
    result = normalize_zip_name("icons/test.png")
    assert result == "icons/test.png"


def test_normalize_strips_whitespace():
    result = normalize_zip_name("  data.json  ")
    assert result == "data.json"


def test_normalize_dot_component():
    assert normalize_zip_name("./file.txt") is None


def test_normalize_empty_part():
    # "a//b" has an empty part
    assert normalize_zip_name("a//b") is None


def test_normalize_single_filename():
    result = normalize_zip_name("config.json")
    assert result == "config.json"


# ---------------------------------------------------------------------------
# ZIP helpers (using in-memory zip)
# ---------------------------------------------------------------------------


def _make_zip(entries: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_build_safe_zip_index_basic():
    buf = _make_zip({"config.json": b"{}", "icons/app.png": b"\x89PNG"})
    with zipfile.ZipFile(buf) as zf:
        report = new_import_report()
        index = build_safe_zip_index(zf, report)
    assert "config.json" in index
    assert "icons/app.png" in index
    assert len(report["warnings"]) == 0


def test_build_safe_zip_index_too_many_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(2049):
            zf.writestr(f"file_{i}.txt", b"x")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        with pytest.raises(UnsafeZipError, match="too many entries"):
            build_safe_zip_index(zf)


def test_build_safe_zip_index_skips_traversal():
    buf = _make_zip({"../evil.txt": b"evil", "good.txt": b"good"})
    with zipfile.ZipFile(buf) as zf:
        report = new_import_report()
        index = build_safe_zip_index(zf, report)
    assert "good.txt" in index
    assert len([w for w in report["warnings"] if "evil" in w or "unsafe" in w]) > 0


def test_build_safe_zip_index_duplicate_case_insensitive():
    buf = _make_zip({"Config.json": b"1", "config.json": b"2"})
    with zipfile.ZipFile(buf) as zf:
        report = new_import_report()
        index = build_safe_zip_index(zf, report)
    # Only one should survive
    assert len(index) == 1
    assert len(report["warnings"]) > 0


def test_has_zip_entry_found():
    buf = _make_zip({"data.json": b"{}"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        assert has_zip_entry(index, "data.json") is True


def test_has_zip_entry_not_found():
    buf = _make_zip({"data.json": b"{}"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        assert has_zip_entry(index, "missing.json") is False


def test_has_zip_entry_traversal_name():
    buf = _make_zip({"data.json": b"{}"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        assert has_zip_entry(index, "../data.json") is False


def test_read_zip_bytes_success():
    buf = _make_zip({"data.bin": b"\x00\x01\x02"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        report = new_import_report()
        result = read_zip_bytes(zf, index, "data.bin", 1024, report)
    assert result == b"\x00\x01\x02"


def test_read_zip_bytes_missing():
    buf = _make_zip({"other.bin": b"x"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        result = read_zip_bytes(zf, index, "missing.bin", 1024)
    assert result is None


def test_read_zip_bytes_missing_required():
    buf = _make_zip({"other.bin": b"x"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        with pytest.raises(UnsafeZipError, match="Missing required"):
            read_zip_bytes(zf, index, "missing.bin", 1024, required=True)


def test_read_zip_bytes_exceeds_size():
    buf = _make_zip({"big.bin": b"x" * 100})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        report = new_import_report()
        result = read_zip_bytes(zf, index, "big.bin", 10, report)
    assert result is None
    assert has_report_warnings(report)


def test_read_zip_bytes_exceeds_size_required():
    buf = _make_zip({"big.bin": b"x" * 100})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        with pytest.raises(UnsafeZipError, match="size limit"):
            read_zip_bytes(zf, index, "big.bin", 10, required=True)


def test_read_zip_text_success():
    buf = _make_zip({"data.txt": b"hello world"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        result = read_zip_text(zf, index, "data.txt")
    assert result == "hello world"


def test_read_zip_text_missing():
    buf = _make_zip({"other.txt": b"x"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        result = read_zip_text(zf, index, "missing.txt")
    assert result is None


def test_read_zip_text_invalid_utf8():
    buf = _make_zip({"bad.txt": b"\xff\xfe"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        report = new_import_report()
        result = read_zip_text(zf, index, "bad.txt", report=report)
    assert result is None
    assert has_report_warnings(report)


def test_read_zip_text_invalid_utf8_required():
    buf = _make_zip({"bad.txt": b"\xff\xfe"})
    with zipfile.ZipFile(buf) as zf:
        index = build_safe_zip_index(zf)
        with pytest.raises(UnsafeZipError, match="UTF-8"):
            read_zip_text(zf, index, "bad.txt", required=True)


# ---------------------------------------------------------------------------
# Path validators
# ---------------------------------------------------------------------------


def test_is_allowed_icon_path_valid():
    assert is_allowed_icon_path("icons/app.png") is True
    assert is_allowed_icon_path("icons/app.ico") is True
    assert is_allowed_icon_path("icons/app.jpg") is True


def test_is_allowed_icon_path_wrong_extension():
    assert is_allowed_icon_path("icons/app.exe") is False
    assert is_allowed_icon_path("icons/app.svg") is False


def test_is_allowed_icon_path_not_in_icons_dir():
    assert is_allowed_icon_path("data/app.png") is False


def test_is_allowed_icon_path_directory():
    assert is_allowed_icon_path("icons/") is False


def test_is_allowed_icon_path_traversal():
    assert is_allowed_icon_path("../icons/app.png") is False


def test_is_allowed_background_path_valid():
    assert is_allowed_background_path("backgrounds/bg.png") is True
    assert is_allowed_background_path("bg.jpg") is True
    assert is_allowed_background_path("path/to/file.webp") is True


def test_is_allowed_background_path_wrong_extension():
    assert is_allowed_background_path("bg.exe") is False
    assert is_allowed_background_path("bg.ico") is False


def test_is_allowed_background_path_directory():
    assert is_allowed_background_path("backgrounds/") is False


def test_is_allowed_background_path_traversal():
    assert is_allowed_background_path("../bg.png") is False
