import pytest
from PIL import Image

pytest.skip(allow_module_level=True, reason="requires network; times out on CI without Docker DNS")


def _png_bytes(color, size=(32, 32)):
    from io import BytesIO

    data = BytesIO()
    Image.new("RGBA", size, color).save(data, "PNG")
    return data.getvalue()


@pytest.mark.slow
def test_fetch_favicon_crops_wide_inline_svg_to_square_png(monkeypatch, tmp_path, qapp):
    from core import favicon_cache

    html = """
    <html><body>
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 40">
        <rect x="0" y="0" width="40" height="40" fill="#d97757"/>
        <rect x="64" y="0" width="120" height="40" fill="#000000"/>
      </svg>
    </body></html>
    """

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))

    icon_path = favicon_cache.fetch_favicon("https://foxcode.example")

    assert icon_path
    assert icon_path.endswith(".png")
    with Image.open(icon_path) as image:
        assert image.size == (512, 512)
        assert image.convert("RGBA").getpixel((500, 256))[:3] == (217, 119, 87)


def test_fetch_favicon_prefers_declared_icon_before_inline_svg(monkeypatch, tmp_path):
    from core import favicon_cache

    html = """
    <html><head><link rel="icon" href="/site-icon.png"></head><body>
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">
        <rect x="0" y="0" width="40" height="40" fill="#d97757"/>
      </svg>
    </body></html>
    """
    calls = []

    def fake_fetch_and_save(icon_url, target):
        calls.append(icon_url)
        Image.new("RGBA", (512, 512), (1, 2, 3, 255)).save(target, "PNG")
        return True

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, "https://example.test/page"))
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    icon_path = favicon_cache.fetch_favicon("https://example.test/page")

    assert icon_path
    assert calls == ["https://example.test/site-icon.png"]
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (1, 2, 3, 255)


def test_fetch_favicon_accepts_data_url_icon(monkeypatch, tmp_path):
    import base64

    from core import favicon_cache

    payload = base64.b64encode(_png_bytes((2, 4, 6, 255))).decode("ascii")
    html = f'<html><head><link rel="icon" href="data:image/png;base64,{payload}"></head></html>'

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))

    icon_path = favicon_cache.fetch_favicon("https://data-icon.example")

    assert icon_path
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (2, 4, 6, 255)


def test_fetch_favicon_uses_manifest_icons(monkeypatch, tmp_path):
    from core import favicon_cache

    html = '<html><head><link rel="manifest" href="/site.webmanifest"></head></html>'
    calls = []

    def fake_manifest(manifest_url):
        assert manifest_url == "https://manifest.example/site.webmanifest"
        return (
            {
                "icons": [
                    {"src": "/small.png", "sizes": "48x48", "type": "image/png"},
                    {"src": "/large.png", "sizes": "192x192", "type": "image/png"},
                ]
            },
            manifest_url,
        )

    def fake_fetch_and_save(icon_url, target):
        calls.append(icon_url)
        Image.new("RGBA", (512, 512), (8, 10, 12, 255)).save(target, "PNG")
        return True

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, "https://manifest.example/page"))
    monkeypatch.setattr(favicon_cache, "_fetch_manifest", fake_manifest)
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    icon_path = favicon_cache.fetch_favicon("https://manifest.example/page")

    assert icon_path
    assert calls == ["https://manifest.example/large.png"]
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (8, 10, 12, 255)


def test_fetch_favicon_tries_common_favicon_before_inline_svg(monkeypatch, tmp_path):
    from core import favicon_cache

    html = """
    <html><body>
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">
        <rect x="0" y="0" width="40" height="40" fill="#d97757"/>
      </svg>
    </body></html>
    """
    calls = []

    def fake_fetch_and_save(icon_url, target):
        calls.append(icon_url)
        if icon_url.endswith("/favicon.png"):
            Image.new("RGBA", (512, 512), (4, 5, 6, 255)).save(target, "PNG")
            return True
        return False

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    icon_path = favicon_cache.fetch_favicon("https://example.test/page")

    assert icon_path
    assert set(calls) == {
        "https://example.test/favicon.svg",
        "https://example.test/favicon.png",
        "https://example.test/apple-touch-icon.png",
        "https://example.test/apple-touch-icon-precomposed.png",
        "https://example.test/images/favicons/apple-touch-icon.png",
        "https://example.test/images/favicons/favicon.png",
        "https://example.test/images/favicons/favicon.ico",
        "https://example.test/favicon.ico",
    }
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (4, 5, 6, 255)


def test_fetch_favicon_tries_nested_favicon_paths_after_html_failure(monkeypatch, tmp_path):
    import urllib.error

    from core import favicon_cache

    calls = []

    def fail_fetch_html(url):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)

    def fake_fetch_and_save(icon_url, target):
        calls.append(icon_url)
        if icon_url.endswith("/images/favicons/apple-touch-icon.png"):
            Image.new("RGBA", (512, 512), (12, 34, 56, 255)).save(target, "PNG")
            return True
        return False

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", fail_fetch_html)
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    icon_path = favicon_cache.fetch_favicon("https://icon-icons.example")

    assert icon_path
    assert "https://icon-icons.example/images/favicons/apple-touch-icon.png" in calls
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (12, 34, 56, 255)


def test_fetch_first_icon_keeps_priority_order(monkeypatch, tmp_path):
    from core import favicon_cache

    target = tmp_path / "target.png"
    colors = {
        "https://priority.example/first.png": (31, 32, 33, 255),
        "https://priority.example/second.png": (41, 42, 43, 255),
    }

    def fake_fetch_and_save(icon_url, candidate):
        Image.new("RGBA", (512, 512), colors[icon_url]).save(candidate, "PNG")
        return True

    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    assert favicon_cache._fetch_first_icon(colors.keys(), str(target))
    with Image.open(target) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == colors["https://priority.example/first.png"]


def test_fetch_favicon_refresh_failure_preserves_old_cache(monkeypatch, tmp_path):
    from core import favicon_cache

    html = '<html><head><link rel="icon" href="/broken.png"></head></html>'
    old_target = tmp_path / f"{favicon_cache._cache_key('https://cache.example')}.png"
    Image.new("RGBA", (512, 512), (51, 52, 53, 255)).save(old_target, "PNG")

    def fake_fetch_and_save(icon_url, candidate):
        with open(candidate, "wb") as handle:
            handle.write(b"not a png")
        return True

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    icon_path = favicon_cache.fetch_favicon("https://cache.example", force_refresh=True)

    assert icon_path == str(old_target)
    with Image.open(icon_path) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (51, 52, 53, 255)


def test_fetch_favicon_upscales_small_raster_icon(monkeypatch, tmp_path):
    from io import BytesIO

    from core import favicon_cache

    html = '<html><head><link rel="icon" href="/small.png"></head></html>'
    small = Image.new("RGBA", (32, 32), (7, 8, 9, 255))
    data = BytesIO()
    small.save(data, "PNG")

    class FakeResponse:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return data.getvalue()

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))
    monkeypatch.setattr(favicon_cache.urllib.request, "urlopen", lambda request, timeout=0: FakeResponse())

    icon_path = favicon_cache.fetch_favicon("https://small-icon.example")

    assert icon_path
    with Image.open(icon_path) as image:
        rgba = image.convert("RGBA")
        assert rgba.size == (512, 512)
        assert rgba.getchannel("A").getbbox() == (0, 0, 512, 512)
        assert rgba.getpixel((256, 256)) == (7, 8, 9, 255)


def test_fetch_favicon_accepts_gif_served_from_ico_path(monkeypatch, tmp_path):
    from io import BytesIO

    from core import favicon_cache

    gif = Image.new("RGBA", (16, 16), (11, 22, 33, 255))
    data = BytesIO()
    gif.save(data, "GIF")

    class FakeResponse:
        def __init__(self, content_type, payload):
            self.headers = {"Content-Type": content_type}
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return self._payload

    def fake_urlopen(request, timeout=0):
        if request.full_url.endswith("/favicon.ico"):
            return FakeResponse("image/x-icon", data.getvalue())
        return FakeResponse("text/html; charset=UTF-8", b"<html></html>")

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: ("", url))
    monkeypatch.setattr(favicon_cache.urllib.request, "urlopen", fake_urlopen)

    icon_path = favicon_cache.fetch_favicon("https://ipleak.example")

    assert icon_path
    with Image.open(icon_path) as image:
        rgba = image.convert("RGBA")
        assert rgba.size == (512, 512)
        assert rgba.getpixel((256, 256)) == (11, 22, 33, 255)


@pytest.mark.slow
def test_qt_raster_fallback_accepts_gif_data(tmp_path, qapp):
    from io import BytesIO

    from core import favicon_cache

    gif = Image.new("RGBA", (16, 16), (21, 32, 43, 255))
    data = BytesIO()
    gif.save(data, "GIF")
    target = tmp_path / "qt-fallback.png"

    assert favicon_cache._qt_raster_to_png(data.getvalue(), str(target), "https://gif.example/favicon.ico")
    with Image.open(target) as image:
        rgba = image.convert("RGBA")
        assert rgba.size == (512, 512)
        assert rgba.getpixel((256, 256)) == (21, 32, 43, 255)


def test_fetch_favicon_force_refresh_bypasses_cached_png(monkeypatch, tmp_path):
    from core import favicon_cache

    html = '<html><head><link rel="icon" href="/site-icon.png"></head></html>'
    colors = iter([(10, 20, 30, 255), (40, 50, 60, 255)])
    calls = []

    def fake_fetch_and_save(icon_url, target):
        calls.append(icon_url)
        Image.new("RGBA", (512, 512), next(colors)).save(target, "PNG")
        return True

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))
    monkeypatch.setattr(favicon_cache, "_fetch_and_save_icon", fake_fetch_and_save)

    first = favicon_cache.fetch_favicon("https://refresh.example")
    second = favicon_cache.fetch_favicon("https://refresh.example")
    refreshed = favicon_cache.fetch_favicon("https://refresh.example", force_refresh=True)

    assert first == second == refreshed
    assert len(calls) == 2
    with Image.open(refreshed) as image:
        assert image.convert("RGBA").getpixel((256, 256)) == (40, 50, 60, 255)


@pytest.mark.slow
def test_fetch_favicon_accepts_html_scoped_inline_svg(monkeypatch, tmp_path, qapp):
    from core import favicon_cache

    html = """
    <html><body>
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 40" data-v-test>
        <path data-v-test fill="#d97757" d="M0 0h40v40H0z"></path>
        <path data-v-test fill="#000000" d="M64 0h120v40H64z"></path>
      </svg>
    </body></html>
    """

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: (html, url))

    icon_path = favicon_cache.fetch_favicon("https://scoped-svg.example")

    assert icon_path
    with Image.open(icon_path) as image:
        assert image.size == (512, 512)
        assert image.convert("RGBA").getpixel((500, 256))[:3] == (217, 119, 87)


def test_clean_unused_favicon_cache_keeps_referenced_icons(monkeypatch, tmp_path):
    from core import favicon_cache
    from core.data_models import AppData, Folder, ShortcutItem, ShortcutType

    used_icon = tmp_path / "used.png"
    unused_icon = tmp_path / "unused.png"
    used_icon.write_bytes(b"used")
    unused_icon.write_bytes(b"unused")

    shortcut = ShortcutItem(id="url", name="URL", type=ShortcutType.URL, icon_path=str(used_icon))
    data = AppData(folders=[Folder(id="f", name="Folder", items=[shortcut])])

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))

    before = favicon_cache.get_favicon_cache_stats(data)
    result = favicon_cache.clean_unused_favicon_cache(data)
    after = favicon_cache.get_favicon_cache_stats(data)

    assert before["total_files"] == 2
    assert before["unused_files"] == 1
    assert result["files_removed"] == 1
    assert used_icon.exists()
    assert not unused_icon.exists()
    assert after["total_files"] == 1
    assert after["unused_files"] == 0


def test_clean_unused_favicon_cache_dry_run_does_not_delete(monkeypatch, tmp_path):
    from core import favicon_cache
    from core.data_models import AppData

    unused_icon = tmp_path / "unused.png"
    unused_icon.write_bytes(b"unused")

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))

    result = favicon_cache.clean_unused_favicon_cache(AppData(), dry_run=True)

    assert result["files_removed"] == 1
    assert unused_icon.exists()


def test_fetch_favicon_logs_final_failure(monkeypatch, tmp_path, caplog):
    import logging

    from core import favicon_cache

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_fetch_html", lambda url: ("", url))
    monkeypatch.setattr(favicon_cache, "_fetch_first_icon", lambda icon_urls, target: False)

    caplog.set_level(logging.WARNING, logger=favicon_cache.__name__)

    icon_path = favicon_cache.fetch_favicon("https://missing-icon.example")

    assert icon_path == ""
    assert "图标获取失败" in caplog.text
    assert "https://missing-icon.example" in caplog.text


def test_fetch_favicon_blocks_loopback_without_request(monkeypatch, tmp_path):
    from core import favicon_cache

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("private URL must be blocked before request")

    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache.urllib.request, "urlopen", fail_urlopen)

    assert favicon_cache.fetch_favicon("http://127.0.0.1/favicon.ico") == ""
    assert favicon_cache.fetch_favicon("http://localhost/favicon.ico") == ""


def test_fetch_favicon_blocks_redirect_to_loopback(monkeypatch, tmp_path):
    import urllib.error
    from email.message import Message

    from core import favicon_cache

    class RedirectResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return b""

        def geturl(self):
            return "https://public.example/favicon.ico"

        def close(self):
            pass

    def fake_open(request, timeout=0):
        headers = Message()
        headers["Location"] = "http://127.0.0.1/secret.ico"
        raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, RedirectResponse())

    opener = type("O", (), {"open": staticmethod(fake_open)})()
    monkeypatch.setattr(favicon_cache, "_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(favicon_cache, "_is_urlopen_patched", lambda: False)
    monkeypatch.setattr(favicon_cache.urllib.request, "build_opener", lambda *args, **kwargs: opener)
    monkeypatch.setattr(
        favicon_cache.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))]
    )

    assert favicon_cache.fetch_favicon("https://public.example") == ""


@pytest.mark.slow
def test_render_svg_rejects_external_references(tmp_path, qapp):
    from core import favicon_cache

    target = tmp_path / "icon.png"
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/a.png"/></svg>'

    assert not favicon_cache._render_svg_to_png(svg, str(target))
    assert not target.exists()
