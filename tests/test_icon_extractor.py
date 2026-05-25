import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows shell icons only")


@pytest.fixture(scope="module")
def qapp():
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    return app


def test_regular_file_target_cache_is_extension_scoped(tmp_path, qapp):
    from core.icon_extractor import IconExtractor

    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    other = tmp_path / "notes.txt"
    first.write_text("print('a')", encoding="utf-8")
    second.write_text("print('b')", encoding="utf-8")
    other.write_text("hello", encoding="utf-8")

    IconExtractor.clear_cache()
    IconExtractor.extract(str(first), str(first), 26)
    IconExtractor.extract(str(second), str(second), 26)
    assert list(IconExtractor._cache.keys()) == ["assoc:.py|26|0|1.0"]

    IconExtractor.extract(str(other), str(other), 26)
    assert sorted(IconExtractor._cache.keys()) == ["assoc:.py|26|0|1.0", "assoc:.txt|26|0|1.0"]


def test_exe_targets_use_path_scoped_cache_keys(qapp):
    from core.icon_extractor import IconExtractor

    first = r"C:\Windows\notepad.exe"
    second = r"C:\Windows\System32\cmd.exe"

    first_key = IconExtractor.get_target_cache_id(first, first, 26)
    second_key = IconExtractor.get_target_cache_id(second, second, 26)

    assert first_key != second_key
    assert not first_key.startswith("assoc:")
    assert not second_key.startswith("assoc:")


def test_exe_target_icon_is_not_default_placeholder(qapp):
    from core.icon_extractor import IconExtractor
    from qt_compat import QImage

    target = r"C:\Windows\notepad.exe"
    if not os.path.exists(target):
        pytest.skip("notepad.exe is not available")

    def image_digest(icon):
        image = icon if isinstance(icon, QImage) else icon.toImage()
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        return bytes(ptr)

    IconExtractor.clear_cache()
    default = IconExtractor._create_default_icon(26)
    image_icon = IconExtractor.extract(target, target, 26, return_image=True)
    pixmap_icon = IconExtractor.extract(target, target, 26, return_image=False)

    assert image_icon is not None
    assert not image_icon.isNull()
    assert (image_icon.width(), image_icon.height()) == (26, 26)
    assert pixmap_icon is not None
    assert not pixmap_icon.isNull()
    assert (pixmap_icon.width(), pixmap_icon.height()) == (26, 26)
    assert image_digest(image_icon) != image_digest(default)
    assert image_digest(pixmap_icon) != image_digest(default)


def test_exe_custom_icon_uses_default_resource(qapp):
    from core.icon_extractor import IconExtractor
    from qt_compat import QImage

    target = r"C:\Windows\notepad.exe"
    if not os.path.exists(target):
        pytest.skip("notepad.exe is not available")

    def image_digest(icon):
        image = icon if isinstance(icon, QImage) else icon.toImage()
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        return bytes(ptr)

    IconExtractor.clear_cache()
    default = IconExtractor._create_default_icon(26)
    icon = IconExtractor.from_file(target, 26)

    assert icon is not None
    assert not icon.isNull()
    assert (icon.width(), icon.height()) == (26, 26)
    assert image_digest(icon) != image_digest(default)
    assert list(IconExtractor._cache.keys()) == [f"from_file:{target}|26|0"]


def test_extract_without_default_does_not_cache_placeholder(qapp):
    from core.icon_extractor import IconExtractor

    target = r"Z:\definitely-missing\nope.exe"

    IconExtractor.clear_cache()
    icon = IconExtractor.extract(target, target, 26, fallback_to_default=False)

    assert icon is None
    assert IconExtractor._cache == {}


def test_exe_target_prefers_resource_icon(monkeypatch, qapp):
    from core.icon_extractor import IconExtractor
    from qt_compat import QColor, QPixmap

    target = r"C:\Windows\notepad.exe"
    if not os.path.exists(target):
        pytest.skip("notepad.exe is not available")

    calls = []

    def fake_resource(path, index, size, return_image=False):
        calls.append((path, index, size, return_image))
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(12, 34, 56))
        return pixmap.toImage() if return_image else pixmap

    monkeypatch.setattr(IconExtractor, "_extract_from_resource", fake_resource)
    IconExtractor.clear_cache()

    icon = IconExtractor.extract(target, target, 26)

    assert icon is not None
    assert not icon.isNull()
    assert calls == [(target, 0, 26, False)]


def test_pixmap_preferred_resource_detects_exe_and_dll(qapp):
    from core.icon_extractor import IconExtractor

    assert IconExtractor._is_pixmap_preferred_resource(r"C:\Windows\notepad.exe")
    assert IconExtractor._is_pixmap_preferred_resource(r"C:\Windows\System32\shell32.dll,3")
    assert not IconExtractor._is_pixmap_preferred_resource(r"C:\tmp\sample.png")


@pytest.mark.parametrize("size", [24, 26, 30, 40])
def test_target_icons_are_normalized_to_requested_size(tmp_path, qapp, size):
    from core.icon_extractor import IconExtractor

    target = tmp_path / "sample.py"
    target.write_text("print('sample')", encoding="utf-8")

    pixmap = IconExtractor.extract(str(target), str(target), size)

    assert pixmap is not None
    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (size, size)


def test_custom_image_icon_is_loaded_as_icon_asset(tmp_path, qapp):
    from core.icon_extractor import IconExtractor
    from qt_compat import QColor, QImage

    icon_path = tmp_path / "custom.png"
    image = QImage(10, 20, QImage.Format_ARGB32)
    image.fill(QColor(255, 0, 0))
    assert image.save(str(icon_path))

    IconExtractor.clear_cache()
    pixmap = IconExtractor.from_file(str(icon_path), 26)

    assert pixmap is not None
    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (26, 26)
    assert list(IconExtractor._cache.keys()) == [f"from_file:{icon_path}|26|0"]
