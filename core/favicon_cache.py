"""Favicon and page-logo cache for URL shortcuts."""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.request
import warnings
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import unquote_to_bytes, urljoin, urlparse

from core.network_security import UnsafeUrlError, safe_urlopen

_CACHE_SIZE = 512
_MAX_ICON_BYTES = 5 * 1024 * 1024
_MAX_HTML_BYTES = 1024 * 1024
_MAX_MANIFEST_BYTES = 512 * 1024
_MAX_SVG_BYTES = 512 * 1024
_MAX_IMAGE_PIXELS = 16 * 1024 * 1024
_MAX_REDIRECTS = 5
_HTML_TIMEOUT = 4.0
_ICON_TIMEOUT = 5.0
_HTML_RETRIES = 2
_HTML_RETRY_DELAY = 0.35
_TRANSIENT_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) QuickLauncher/1.0 Safari/537.36"
)
_HTML_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_MANIFEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/manifest+json,application/json,text/json,*/*;q=0.5",
}
_ICON_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "image/png,image/svg+xml,image/webp,image/gif,image/x-icon,image/vnd.microsoft.icon,image/*;q=0.8,*/*;q=0.5",
}
_COMMON_ICON_PATHS = (
    "/favicon.svg",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/images/favicons/apple-touch-icon.png",
    "/images/favicons/favicon.png",
    "/images/favicons/favicon.ico",
    "/favicon.ico",
)
_COMMON_MANIFEST_PATHS = (
    "/site.webmanifest",
    "/manifest.webmanifest",
    "/manifest.json",
)
logger = logging.getLogger(__name__)
_PILLOW_DECODER_WARNING_LOGGED = False
_SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
_VIEWBOX_RE = re.compile(
    r"\bviewBox\s*=\s*['\"]\s*([-+0-9.eE]+)[,\s]+([-+0-9.eE]+)[,\s]+([-+0-9.eE]+)[,\s]+([-+0-9.eE]+)\s*['\"]",
    re.IGNORECASE,
)
_SIZE_ATTR_RE = re.compile(r"\b(width|height)\s*=\s*['\"]\s*([-+0-9.eE]+)", re.IGNORECASE)
_GRAPHIC_ELEMENT_RE = re.compile(
    r"<(?:path|rect|circle|ellipse|polygon|polyline)\b[^>]*(?:/>|>.*?</(?:path|rect|circle|ellipse|polygon|polyline)>)",
    re.IGNORECASE | re.DOTALL,
)
_VUE_SCOPED_ATTR_RE = re.compile(r"\sdata-v-[\w-]+(?=[\s>/])", re.IGNORECASE)
_SVG_UNSAFE_RE = re.compile(
    r"<\s*(?:script|foreignObject)\b|(?:href|xlink:href)\s*=\s*['\"]\s*(?:https?:)?//|<\s*image\b",
    re.IGNORECASE,
)


class UnsafeFaviconUrlError(ValueError):
    pass


class _IconLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.icon_links: list[tuple[int, str]] = []
        self.manifest_links: list[str] = []
        self.meta_icon_links: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs):
        tag_name = tag.lower()
        if tag_name == "link":
            self._handle_link(attrs)
            return
        if tag_name != "meta":
            return

        data = {str(k).lower(): str(v or "") for k, v in attrs}
        content = data.get("content", "").strip()
        name = data.get("name", "").lower()
        prop = data.get("property", "").lower()
        if not content:
            return
        if name in {"msapplication-tileimage", "msapplication-square150x150logo", "msapplication-square310x310logo"}:
            self.meta_icon_links.append((18, content))
        elif prop == "og:image":
            self.meta_icon_links.append((1, content))

    def _handle_link(self, attrs):
        data = {str(k).lower(): str(v or "") for k, v in attrs}
        href = data.get("href", "").strip()
        rel = data.get("rel", "").lower()
        if href and "manifest" in rel:
            self.manifest_links.append(href)

        if not href or "icon" not in rel:
            return

        sizes = data.get("sizes", "")
        type_hint = data.get("type", "").lower()
        score = 10
        if "apple-touch-icon" in rel:
            score += 20
        if "mask-icon" in rel:
            score -= 12
        if "svg" in type_hint or href.lower().endswith(".svg"):
            score += 18
        if "png" in type_hint or href.lower().endswith(".png"):
            score += 12
        if "webp" in type_hint or href.lower().endswith(".webp"):
            score += 10
        if "ico" in type_hint or href.lower().endswith(".ico"):
            score += 3
        for width, height in re.findall(r"(\d+)\s*x\s*(\d+)", sizes):
            score += min(int(width), int(height)) // 16

        self.icon_links.append((score, href))


def fetch_favicon(url: str, force_refresh: bool = False) -> str:
    """Fetch a URL icon and cache it as a 512x512 PNG.

    The fetcher prefers explicit page icon links and common favicon locations.
    Inline SVG logos are only used as a fallback. Wide inline SVG logos are
    cropped to their left square region so sites like foxcode.rjj.cc produce an
    app-style icon.
    """
    try:
        from .shortcut_url_exec import UrlExecutionMixin

        normalized, error = UrlExecutionMixin._prepare_url(url, {})
        if error:
            logger.warning("图标获取失败：URL 无效 url=%r error=%s", url, error)
            return ""
        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            logger.warning("图标获取失败：URL 协议或域名无效 url=%r normalized=%r", url, normalized)
            return ""

        logger.info("开始获取网址图标: url=%s force_refresh=%s", normalized, force_refresh)
        cache_dir = _cache_dir()
        target = os.path.join(cache_dir, f"{_cache_key(normalized)}.png")
        has_cached_icon = _is_usable_png(target)
        if not force_refresh and has_cached_icon:
            logger.info("使用已缓存的网址图标: url=%s path=%s", normalized, target)
            return target

        try:
            html, final_url = _fetch_html(normalized)
            if html:
                logger.debug(
                    "图标获取：页面 HTML 已读取 url=%s final_url=%s bytes=%s", normalized, final_url, len(html)
                )
            else:
                logger.debug("图标获取：页面不是 HTML 或内容为空 url=%s final_url=%s", normalized, final_url)
        except Exception as e:
            logger.warning(
                "图标获取：页面读取失败，继续尝试常见 favicon 路径 url=%s error=%s", normalized, e, exc_info=True
            )
            html, final_url = "", normalized
        if html:
            icon_links = _extract_icon_links(html, final_url)
            ok, icon_url = _fetch_icon_candidates(icon_links, target)
            if ok:
                logger.info("图标获取成功：使用页面声明图标 url=%s icon_url=%s path=%s", normalized, icon_url, target)
                return target

            manifest_links = _extract_manifest_links(html, final_url)
            manifest_icon_links = _fetch_manifest_icon_links(manifest_links)
            logger.debug("图标获取：manifest 图标数量=%d url=%s", len(manifest_icon_links), normalized)
            ok, icon_url = _fetch_icon_candidates(manifest_icon_links, target)
            if ok:
                logger.info("图标获取成功：使用 manifest 图标 url=%s icon_url=%s path=%s", normalized, icon_url, target)
                return target

        origin = f"{parsed.scheme}://{parsed.netloc}"
        if _fetch_first_icon(
            (urljoin(origin, path) for path in _COMMON_ICON_PATHS),
            target,
        ):
            logger.info("图标获取成功：使用常见 favicon 路径 url=%s path=%s", normalized, target)
            return target

        common_manifest_icon_links = _fetch_manifest_icon_links(
            urljoin(origin, path) for path in _COMMON_MANIFEST_PATHS
        )
        ok, icon_url = _fetch_icon_candidates(common_manifest_icon_links, target)
        if ok:
            logger.info("图标获取成功：使用常见 manifest 图标 url=%s icon_url=%s path=%s", normalized, icon_url, target)
            return target

        if html:
            if _render_inline_svg_candidates(_extract_inline_svgs(html), target):
                logger.info("图标获取成功：使用页面内联 SVG url=%s path=%s", normalized, target)
                return target

        if has_cached_icon and _is_usable_png(target):
            logger.warning("图标获取刷新失败，回退到旧缓存: url=%s path=%s", normalized, target)
            return target
        logger.warning("图标获取失败：未找到可用图标 url=%s cache_target=%s", normalized, target)
        return ""
    except Exception as e:
        logger.warning("图标获取失败：发生未处理异常 url=%r error=%s", url, e, exc_info=True)
        return ""


def get_favicon_cache_stats(data=None) -> dict:
    """Return usage stats for cached URL shortcut icons."""
    cache_dir = _cache_dir()
    used_paths = _collect_used_favicon_paths(data)
    stats = {
        "cache_dir": cache_dir,
        "total_files": 0,
        "total_size_mb": 0,
        "used_files": 0,
        "used_size_mb": 0,
        "unused_files": 0,
        "unused_size_mb": 0,
    }

    if not os.path.isdir(cache_dir):
        return stats

    for entry in os.scandir(cache_dir):
        if not entry.is_file():
            continue
        try:
            file_size = entry.stat().st_size
        except Exception:
            continue

        is_used = _normalize_path(entry.path) in used_paths
        size_mb = file_size / (1024 * 1024)
        stats["total_files"] += 1
        stats["total_size_mb"] += size_mb
        if is_used:
            stats["used_files"] += 1
            stats["used_size_mb"] += size_mb
        else:
            stats["unused_files"] += 1
            stats["unused_size_mb"] += size_mb

    _round_cache_stats(stats)
    return stats


def clean_unused_favicon_cache(data, dry_run: bool = False) -> dict:
    """Delete cached favicons that are no longer referenced by shortcuts."""
    cache_dir = _cache_dir()
    used_paths = _collect_used_favicon_paths(data)
    stats = {
        "cache_dir": cache_dir,
        "files_removed": 0,
        "size_freed_mb": 0,
        "total_removed": 0,
        "total_size_freed_mb": 0,
        "failed": 0,
        "dry_run": dry_run,
    }

    if not os.path.isdir(cache_dir):
        return stats

    for entry in os.scandir(cache_dir):
        if not entry.is_file():
            continue
        normalized = _normalize_path(entry.path)
        if normalized in used_paths:
            continue
        try:
            file_size = entry.stat().st_size
        except Exception:
            continue

        size_mb = file_size / (1024 * 1024)
        if not dry_run:
            try:
                os.remove(entry.path)
            except Exception:
                stats["failed"] += 1
                continue

        stats["files_removed"] += 1
        stats["size_freed_mb"] += size_mb
        stats["total_removed"] += 1
        stats["total_size_freed_mb"] += size_mb

    _round_cache_stats(stats)
    return stats


def _cache_dir() -> str:
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_icons", "favicons")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _cache_key(url: str) -> str:
    return hashlib.sha1(("v5:" + url.strip().lower()).encode("utf-8")).hexdigest()[:16]


def _collect_used_favicon_paths(data) -> set[str]:
    if data is None:
        return set()

    used_paths = set()
    for folder in getattr(data, "folders", []) or []:
        for item in getattr(folder, "items", []) or []:
            icon_path = _split_icon_location(getattr(item, "icon_path", ""))
            if icon_path:
                used_paths.add(_normalize_path(icon_path))
    return used_paths


def _split_icon_location(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    if "," in raw:
        return raw.rsplit(",", 1)[0].strip()
    return raw


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path or ""))))


def _round_cache_stats(stats: dict):
    for key, value in list(stats.items()):
        if isinstance(value, float):
            stats[key] = round(value, 2)


def _is_usable_png(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        return False
    try:
        _ensure_pillow_decoders()
        from PIL import Image

        with Image.open(path) as image:
            return image.size == (_CACHE_SIZE, _CACHE_SIZE) and _has_visible_pixels(image.convert("RGBA"))
    except Exception:
        return False


def _fetch_icon_candidates(icon_urls, target: str) -> tuple[bool, str]:
    urls = _dedupe_icon_urls(icon_urls)
    if not urls:
        return False, ""

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ql_favicon_seq_", dir=os.path.dirname(target)) as tmp_dir:
        for index, icon_url in enumerate(urls):
            candidate = os.path.join(tmp_dir, f"{index}.png")
            if _fetch_and_save_icon(icon_url, candidate) and _replace_cached_icon(candidate, target):
                return True, icon_url
    return False, ""


def _dedupe_icon_urls(icon_urls) -> list[str]:
    urls = []
    seen = set()
    for icon_url in icon_urls or ():
        normalized = _normalize_icon_candidate_url(str(icon_url or "").strip())
        if normalized and normalized not in seen:
            urls.append(normalized)
            seen.add(normalized)
    return urls


def _normalize_icon_candidate_url(icon_url: str) -> str:
    if not icon_url:
        return ""
    parsed = urlparse(icon_url)
    if parsed.scheme in ("http", "https"):
        return icon_url
    if icon_url.lower().startswith("data:image/"):
        return icon_url
    logger.debug("图标获取：跳过不支持的候选图标协议 icon_url=%s", icon_url)
    return ""


def _replace_cached_icon(candidate: str, target: str) -> bool:
    if not _is_usable_png(candidate):
        return False

    target_dir = os.path.dirname(target)
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_target = tempfile.mkstemp(
        prefix=f".{os.path.basename(target)}.",
        suffix=".tmp",
        dir=target_dir,
    )
    os.close(fd)
    try:
        shutil.copyfile(candidate, temp_target)
        if not _is_usable_png(temp_target):
            return False
        os.replace(temp_target, target)
        return _is_usable_png(target)
    finally:
        try:
            if os.path.exists(temp_target):
                os.remove(temp_target)
        except Exception:
            logger.debug("清理favicon临时文件失败", exc_info=True)


def _render_inline_svg_candidates(svgs: list[str], target: str) -> bool:
    if not svgs:
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ql_favicon_svg_", dir=os.path.dirname(target)) as tmp_dir:
        for index, svg in enumerate(svgs):
            candidate = os.path.join(tmp_dir, f"{index}.png")
            if _render_svg_to_png(_crop_wide_svg(svg), candidate) and _replace_cached_icon(candidate, target):
                return True
    return False


def _fetch_html(url: str) -> tuple[str, str]:
    for attempt in range(_HTML_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers=_HTML_HEADERS)
            with safe_urlopen(request, timeout=_HTML_TIMEOUT, max_redirects=_MAX_REDIRECTS) as response:
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower():
                    logger.debug("图标获取：页面响应不是 HTML url=%s content_type=%s", url, content_type)
                    return "", response.geturl()
                data = response.read(_MAX_HTML_BYTES + 1)
                if len(data) > _MAX_HTML_BYTES:
                    data = data[:_MAX_HTML_BYTES]
                charset = response.headers.get_content_charset() or "utf-8"
                final_url = response.geturl()
            return data.decode(charset, errors="replace"), final_url
        except urllib.error.HTTPError as e:
            if e.code not in _TRANSIENT_HTTP_STATUS_CODES or attempt >= _HTML_RETRIES:
                raise
            _sleep_before_html_retry(url, attempt, f"HTTP {e.code}")
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", None)
            if not isinstance(reason, TimeoutError | socket.timeout) or attempt >= _HTML_RETRIES:
                raise
            _sleep_before_html_retry(url, attempt, "timeout")
        except TimeoutError:
            if attempt >= _HTML_RETRIES:
                raise
            _sleep_before_html_retry(url, attempt, "timeout")
        except UnsafeUrlError as exc:
            raise UnsafeFaviconUrlError(str(exc)) from exc
    return "", url


def _sleep_before_html_retry(url: str, attempt: int, reason: str):
    logger.info(
        "图标获取：页面读取暂时失败，将重试 url=%s reason=%s attempt=%d/%d",
        url,
        reason,
        attempt + 2,
        _HTML_RETRIES + 1,
    )
    time.sleep(_HTML_RETRY_DELAY * (attempt + 1))


def _extract_icon_links(html: str, base_url: str) -> list[str]:
    parser = _IconLinkParser()
    parser.feed(html)
    ordered = sorted(parser.icon_links, key=lambda item: item[0], reverse=True)
    seen = set()
    result = []
    for _, href in ordered:
        icon_url = urljoin(base_url, href)
        if icon_url not in seen:
            seen.add(icon_url)
            result.append(icon_url)
    return result


def _extract_manifest_links(html: str, base_url: str) -> list[str]:
    parser = _IconLinkParser()
    parser.feed(html)
    seen = set()
    result = []
    for href in parser.manifest_links:
        manifest_url = urljoin(base_url, href)
        if manifest_url not in seen:
            seen.add(manifest_url)
            result.append(manifest_url)
    return result


def _fetch_manifest_icon_links(manifest_urls) -> list[str]:
    scored_icons: list[tuple[int, str]] = []
    for manifest_url in _dedupe_icon_urls(manifest_urls):
        if urlparse(manifest_url).scheme not in ("http", "https"):
            continue
        try:
            manifest, final_url = _fetch_manifest(manifest_url)
        except Exception as e:
            logger.debug("图标获取：manifest 读取失败 manifest_url=%s error=%s", manifest_url, e, exc_info=True)
            continue

        icons = manifest.get("icons", [])
        if not isinstance(icons, list):
            continue
        for icon in icons:
            if not isinstance(icon, dict):
                continue
            src = str(icon.get("src") or "").strip()
            if not src:
                continue
            purpose = str(icon.get("purpose") or "").lower()
            if "monochrome" in purpose:
                continue
            type_hint = str(icon.get("type") or "").lower()
            sizes = str(icon.get("sizes") or "")
            score = _score_manifest_icon(src, sizes, type_hint, purpose)
            scored_icons.append((score, urljoin(final_url, src)))

    ordered = sorted(scored_icons, key=lambda item: item[0], reverse=True)
    seen = set()
    result = []
    for _, icon_url in ordered:
        normalized = _normalize_icon_candidate_url(icon_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _fetch_manifest(manifest_url: str) -> tuple[dict, str]:
    request = urllib.request.Request(manifest_url, headers=_MANIFEST_HEADERS)
    try:
        with safe_urlopen(request, timeout=_HTML_TIMEOUT, max_redirects=_MAX_REDIRECTS) as response:
            data = response.read(_MAX_MANIFEST_BYTES + 1)
            if len(data) > _MAX_MANIFEST_BYTES:
                raise ValueError("manifest too large")
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
    except UnsafeUrlError as exc:
        raise UnsafeFaviconUrlError(str(exc)) from exc
    manifest = json.loads(data.decode(charset, errors="replace"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest root is not an object")
    return manifest, final_url


def _score_manifest_icon(src: str, sizes: str, type_hint: str, purpose: str) -> int:
    score = 10
    lower_src = src.lower().split("?", 1)[0]
    if "maskable" in purpose:
        score += 8
    if "svg" in type_hint or lower_src.endswith(".svg"):
        score += 18
    elif "png" in type_hint or lower_src.endswith(".png"):
        score += 14
    elif "webp" in type_hint or lower_src.endswith(".webp"):
        score += 10
    elif "ico" in type_hint or lower_src.endswith(".ico"):
        score += 3

    dimensions = [min(int(width), int(height)) for width, height in re.findall(r"(\d+)\s*x\s*(\d+)", sizes)]
    if dimensions:
        best = max(dimensions)
        score += min(best, 512) // 16
        if best > 1024:
            score -= 8
    elif sizes.strip().lower() == "any":
        score += 18
    return score


def _extract_inline_svgs(html: str) -> list[str]:
    scored = []
    for match in _SVG_RE.finditer(html):
        svg = match.group(0)
        lower = svg.lower()
        score = 0
        if "logo" in lower:
            score += 20
        if "icon" in lower:
            score += 12
        if "<path" in lower:
            score += 8
        if "viewbox" in lower:
            score += 8
        viewbox = _parse_viewbox(svg)
        if viewbox:
            _, _, width, height = viewbox
            if width > 0 and height > 0:
                ratio = width / height
                if 0.75 <= ratio <= 1.35:
                    score += 14
                elif ratio > 1.35:
                    score += 30
        score += max(0, lower.count("<path") - 1) * 4
        scored.append((score, svg))
    return [svg for _, svg in sorted(scored, key=lambda item: item[0], reverse=True)]


def _fetch_and_save_icon(icon_url: str, target: str) -> bool:
    try:
        logger.debug("图标获取：尝试候选图标 icon_url=%s", icon_url)
        if icon_url.lower().startswith("data:image/"):
            data, content_type = _decode_data_url_bytes(icon_url.encode("utf-8"), "")
            return _save_icon_bytes(data, content_type, target, icon_url)
        request = urllib.request.Request(icon_url, headers=_ICON_HEADERS)
        with safe_urlopen(request, timeout=_ICON_TIMEOUT, max_redirects=_MAX_REDIRECTS) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" in content_type:
                logger.debug("图标获取：跳过 HTML 响应 icon_url=%s content_type=%s", icon_url, content_type)
                return False
            data = response.read(_MAX_ICON_BYTES + 1)
        if not data or len(data) > _MAX_ICON_BYTES:
            logger.debug("图标获取：候选图标为空或过大 icon_url=%s bytes=%d", icon_url, len(data or b""))
            return False
        return _save_icon_bytes(data, content_type, target, icon_url)
    except urllib.error.HTTPError as e:
        logger.debug("图标获取：候选图标 HTTP 失败 icon_url=%s status=%s error=%s", icon_url, e.code, e, exc_info=True)
        return False
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        if isinstance(reason, TimeoutError | socket.timeout):
            logger.warning(
                "图标获取：候选图标请求超时 icon_url=%s timeout=%.1fs", icon_url, _ICON_TIMEOUT, exc_info=True
            )
        else:
            logger.debug("图标获取：候选图标请求失败 icon_url=%s error=%s", icon_url, e, exc_info=True)
        return False
    except TimeoutError as e:
        logger.warning(
            "图标获取：候选图标请求超时 icon_url=%s timeout=%.1fs error=%s", icon_url, _ICON_TIMEOUT, e, exc_info=True
        )
        return False
    except UnsafeUrlError as e:
        raise UnsafeFaviconUrlError(str(e)) from e


def _save_icon_bytes(data: bytes, content_type: str, target: str, source: str) -> bool:
    data, content_type = _decode_data_url_bytes(data, content_type)
    if not data:
        logger.debug("图标获取：候选图标数据为空 source=%s", source)
        return False
    stripped = data.lstrip()[:64].lower()
    if stripped.startswith((b"<!doctype html", b"<html")):
        logger.debug("图标获取：跳过 HTML 内容 source=%s", source)
        return False
    if "svg" in content_type or source.lower().split("?", 1)[0].endswith(".svg") or data.lstrip().startswith(b"<svg"):
        if len(data) > _MAX_SVG_BYTES:
            logger.debug("SVG icon too large: source=%s bytes=%d", source, len(data))
            return False
        return _render_svg_to_png(data.decode("utf-8", errors="replace"), target)
    return _raster_to_png(data, target, source)


def _fetch_first_icon(icon_urls, target: str) -> bool:
    """Fetch common icon locations in parallel and keep the first usable result."""
    urls = []
    seen = set()
    for icon_url in icon_urls:
        if icon_url and icon_url not in seen:
            urls.append(icon_url)
            seen.add(icon_url)
    if not urls:
        return False

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ql_favicon_", dir=os.path.dirname(target)) as tmp_dir:
        workers = min(8, len(urls))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for index, icon_url in enumerate(urls):
                candidate = os.path.join(tmp_dir, f"{index}.png")
                futures[executor.submit(_fetch_and_save_icon, icon_url, candidate)] = (index, candidate)

            successes = {}
            for future in concurrent.futures.as_completed(futures):
                index, candidate = futures[future]
                try:
                    ok = future.result()
                except Exception as e:
                    logger.debug("图标获取：候选图标线程异常 error=%s", e, exc_info=True)
                    ok = False
                if ok and _is_usable_png(candidate):
                    successes[index] = candidate
            if successes:
                candidate = successes[min(successes)]
                return _replace_cached_icon(candidate, target)
    return False


def _decode_data_url_bytes(data: bytes, content_type: str) -> tuple[bytes, str]:
    prefix = b"data:image/"
    if not data.lower().startswith(prefix):
        return data, content_type
    if len(data) > _MAX_ICON_BYTES * 2:
        return b"", content_type
    try:
        header, payload = data.split(b",", 1)
        new_type = header[5:].split(b";", 1)[0].decode("ascii", errors="ignore")
        if b";base64" in header.lower():
            decoded = base64.b64decode(payload)
        else:
            decoded = unquote_to_bytes(payload.decode("ascii", errors="ignore"))
        if len(decoded) > _MAX_ICON_BYTES:
            return b"", new_type
        return decoded, new_type
    except Exception:
        return b"", content_type


def _raster_to_png(data: bytes, target: str, source: str = "") -> bool:
    try:
        _ensure_pillow_decoders()
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > _MAX_IMAGE_PIXELS:
                logger.warning("图标获取：图片像素过大 source=%s size=%s", source, image.size)
                return False
            image = image.convert("RGBA")
            if min(image.size) <= 2 or not _has_visible_pixels(image):
                logger.warning(
                    "图标获取：图片不可用或全透明 source=%s size=%s target=%s",
                    source,
                    getattr(image, "size", None),
                    target,
                )
                return False
            scale = min(_CACHE_SIZE / image.width, _CACHE_SIZE / image.height)
            scaled_size = (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            )
            image = image.resize(scaled_size, Image.LANCZOS)
            canvas = Image.new("RGBA", (_CACHE_SIZE, _CACHE_SIZE), (0, 0, 0, 0))
            x = (_CACHE_SIZE - image.width) // 2
            y = (_CACHE_SIZE - image.height) // 2
            canvas.alpha_composite(image, (x, y))
            canvas.save(target, "PNG")
        return _is_usable_png(target)
    except Exception as e:
        logger.warning(
            "图标获取：Pillow 图片解码或保存失败，尝试 Qt 解码兜底 source=%s target=%s bytes=%d head=%s error=%s",
            source,
            target,
            len(data or b""),
            (data or b"")[:16].hex(),
            e,
            exc_info=True,
        )
        return _qt_raster_to_png(data, target, source)


def _qt_raster_to_png(data: bytes, target: str, source: str = "") -> bool:
    try:
        from qt_compat import QByteArray, QGuiApplication, QImage, QPainter, Qt

        app = QGuiApplication.instance()
        if app is None:
            app = QGuiApplication([])

        image = QImage()
        if not image.loadFromData(QByteArray(data)):
            logger.warning(
                "图标获取：Qt 也无法解码图片 source=%s target=%s bytes=%d head=%s",
                source,
                target,
                len(data or b""),
                (data or b"")[:16].hex(),
            )
            return False
        if image.width() * image.height() > _MAX_IMAGE_PIXELS:
            logger.warning("图标获取：Qt 图片像素过大 source=%s size=%sx%s", source, image.width(), image.height())
            return False
        image = image.convertToFormat(QImage.Format_ARGB32)
        if min(image.width(), image.height()) <= 2 or not _qimage_has_visible_pixels(image):
            logger.warning(
                "图标获取：Qt 解码结果不可用或全透明 source=%s size=%sx%s target=%s",
                source,
                image.width(),
                image.height(),
                target,
            )
            return False

        scale = min(_CACHE_SIZE / image.width(), _CACHE_SIZE / image.height())
        scaled = image.scaled(
            max(1, int(round(image.width() * scale))),
            max(1, int(round(image.height() * scale))),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        canvas = QImage(_CACHE_SIZE, _CACHE_SIZE, QImage.Format_ARGB32)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.drawImage((_CACHE_SIZE - scaled.width()) // 2, (_CACHE_SIZE - scaled.height()) // 2, scaled)
        painter.end()
        if not canvas.save(target, "PNG"):
            logger.warning("图标获取：Qt PNG 保存失败 source=%s target=%s", source, target)
            return False
        return _is_usable_png(target)
    except Exception as e:
        logger.warning("图标获取：Qt 图片解码兜底失败 source=%s target=%s error=%s", source, target, e, exc_info=True)
        return False


def _ensure_pillow_decoders():
    """Keep image decoders visible to frozen builds.

    Some sites serve favicons through misleading extensions, for example
    ipleak.net returns a GIF image from /favicon.ico. Pillow discovers these
    decoders through plugin imports, so make the common web formats explicit for
    Nuitka/PyInstaller instead of relying on dynamic discovery.
    """
    global _PILLOW_DECODER_WARNING_LOGGED
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            from PIL import (  # noqa: F401
                BmpImagePlugin,
                GifImagePlugin,
                IcoImagePlugin,
                Image,
                JpegImagePlugin,
                PngImagePlugin,
                WebPImagePlugin,
            )

            Image.init()
        except Exception as e:
            if not _PILLOW_DECODER_WARNING_LOGGED:
                _PILLOW_DECODER_WARNING_LOGGED = True
                logger.warning("图标获取：Pillow 图片解码器加载失败，将依赖 Qt 兜底 error=%s", e, exc_info=True)


def _render_svg_to_png(svg: str, target: str) -> bool:
    try:
        from qt_compat import QByteArray, QGuiApplication, QImage, QPainter, QRectF, QSvgRenderer, Qt

        if QSvgRenderer is None:
            logger.warning("QSvgRenderer 不可用，SVG 渲染跳过 target=%s", target)
            return False

        svg = _sanitize_svg_for_qt(svg)
        app = QGuiApplication.instance()
        if app is None:
            app = QGuiApplication([])

        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if not renderer.isValid():
            logger.warning("图标获取：SVG 渲染器无法识别图标 target=%s", target)
            return False

        image = QImage(_CACHE_SIZE, _CACHE_SIZE, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, _CACHE_SIZE, _CACHE_SIZE))
        painter.end()

        if not _qimage_has_visible_pixels(image):
            logger.warning("图标获取：SVG 渲染结果为空或全透明 target=%s", target)
            return False
        if not image.save(target, "PNG"):
            logger.warning("图标获取：SVG PNG 保存失败 target=%s", target)
            return False
        return _is_usable_png(target)
    except Exception as e:
        logger.warning("图标获取：SVG 渲染失败 target=%s error=%s", target, e, exc_info=True)
        return False


def _sanitize_svg_for_qt(svg: str) -> str:
    if len(svg.encode("utf-8", errors="ignore")) > _MAX_SVG_BYTES:
        return ""
    if _SVG_UNSAFE_RE.search(svg):
        return ""
    return _VUE_SCOPED_ATTR_RE.sub("", svg)


def _crop_wide_svg(svg: str) -> str:
    viewbox = _parse_viewbox(svg)
    if not viewbox:
        width, height = _parse_svg_size(svg)
        if not width or not height:
            return svg
        viewbox = (0.0, 0.0, width, height)

    x, y, width, height = viewbox
    if width <= 0 or height <= 0 or width <= height * 1.35:
        return svg

    square = min(width, height)
    first_graphic = _first_graphic_element(svg)
    if first_graphic:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {square:g} {square:g}" '
            f'fill="currentColor">{first_graphic}</svg>'
        )
    return _replace_or_add_viewbox(svg, x, y, square, square)


def _first_graphic_element(svg: str) -> str:
    match = _GRAPHIC_ELEMENT_RE.search(svg)
    return match.group(0) if match else ""


def _parse_viewbox(svg: str) -> tuple[float, float, float, float] | None:
    match = _VIEWBOX_RE.search(svg)
    if not match:
        return None
    try:
        return tuple(float(part) for part in match.groups())
    except Exception:
        return None


def _parse_svg_size(svg: str) -> tuple[float | None, float | None]:
    values = {name.lower(): float(value) for name, value in _SIZE_ATTR_RE.findall(svg)}
    return values.get("width"), values.get("height")


def _replace_or_add_viewbox(svg: str, x: float, y: float, width: float, height: float) -> str:
    value = f'viewBox="{x:g} {y:g} {width:g} {height:g}"'
    if _VIEWBOX_RE.search(svg):
        return _VIEWBOX_RE.sub(value, svg, count=1)
    return re.sub(r"<svg\b", f"<svg {value}", svg, count=1, flags=re.IGNORECASE)


def _has_visible_pixels(image) -> bool:
    try:
        return image.getchannel("A").getbbox() is not None
    except Exception:
        return False


def _qimage_has_visible_pixels(image) -> bool:
    width = image.width()
    height = image.height()
    step = max(1, min(width, height) // 128)
    for y in range(0, height, step):
        for x in range(0, width, step):
            if image.pixelColor(x, y).alpha() > 2:
                return True
    return False
