"""Extended processor implementations for action chain.

This module provides comprehensive processor implementations covering:
- Date/Time operations
- Encoding/Decoding (Base64, URL, HTML, Unicode)
- System information
- Network utilities
- Data validation
- Encryption/Hashing
- Color processing
- Set/Dictionary operations
- String formatting
- Data compression
- System commands
- Environment variables
"""

from __future__ import annotations

import base64
import hashlib
import html
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import uuid
import zlib
from datetime import datetime, timedelta
from typing import Any

__all__ = [
    # Date/Time processors
    "datetime_now",
    "datetime_format",
    "datetime_parse",
    "datetime_add",
    "datetime_diff",
    "datetime_part",
    "timestamp_now",
    "timestamp_to_datetime",
    "datetime_to_timestamp",

    # Encoding/Decoding processors
    "base64_encode",
    "base64_decode",
    "url_encode",
    "url_decode",
    "html_encode",
    "html_decode",
    "unicode_encode",
    "unicode_decode",
    "hex_encode",
    "hex_decode",

    # System info processors
    "sys_platform",
    "sys_version",
    "sys_architecture",
    "sys_hostname",
    "sys_username",
    "sys_cpu_count",
    "sys_memory_info",
    "sys_disk_info",
    "sys_current_dir",
    "sys_home_dir",
    "sys_temp_dir",
    "sys_env_vars",

    # Network processors
    "net_hostname",
    "net_ip_address",
    "net_ping",
    "net_port_check",
    "net_url_parse",
    "net_url_build",
    "net_mac_address",

    # Validation processors
    "validate_email",
    "validate_url",
    "validate_ip",
    "validate_phone",
    "validate_id_card",
    "validate_credit_card",
    "validate_regex",
    "validate_range",
    "validate_length",

    # Hash processors
    "hash_md5",
    "hash_sha1",
    "hash_sha256",
    "hash_sha512",
    "hash_crc32",
    "hash_hmac",
    "hash_uuid",
    "hash_uuid5",

    # Color processors
    "color_hex_to_rgb",
    "color_rgb_to_hex",
    "color_hsl_to_rgb",
    "color_rgb_to_hsl",
    "color_brightness",
    "color_contrast",
    "color_complementary",
    "color_random",

    # Set operations
    "set_union",
    "set_intersection",
    "set_difference",
    "set_symmetric_difference",
    "set_is_subset",
    "set_is_superset",
    "set_unique",

    # Dictionary operations
    "dict_keys",
    "dict_values",
    "dict_items",
    "dict_merge",
    "dict_get",
    "dict_set",
    "dict_delete",
    "dict_filter",
    "dict_map",

    # String formatting
    "str_format",
    "str_template",
    "str_pad_left",
    "str_pad_right",
    "str_pad_center",
    "str_truncate",
    "str_repeat",
    "str_replace_multiple",

    # Compression processors
    "compress_gzip",
    "decompress_gzip",
    "compress_zlib",
    "decompress_zlib",
    "compress_deflate",
    "decompress_deflate",

    # Environment processors
    "env_get",
    "env_set",
    "env_list",
    "env_path",
    "env_expand",

    # Math extended
    "math_sin",
    "math_cos",
    "math_tan",
    "math_sqrt",
    "math_log",
    "math_log10",
    "math_exp",
    "math_pow",
    "math_factorial",
    "math_gcd",
    "math_lcm",
    "math_fibonacci",
]


# ── Date/Time Processors ─────────────────────────────────────────────────────

def datetime_now(format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get current datetime formatted."""
    return datetime.now().strftime(format_str)


def datetime_format(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime string."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime(format_str)
    except ValueError:
        # Try common formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"]:
            try:
                dt = datetime.strptime(dt_str, fmt)
                return dt.strftime(format_str)
            except ValueError:
                continue
        raise ValueError(f"无法解析日期时间: {dt_str}") from None


def datetime_parse(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> dict[str, Any]:
    """Parse a datetime string to components."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.strptime(dt_str, format_str)

    return {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
        "weekday": dt.weekday(),
        "weekday_name": dt.strftime("%A"),
        "month_name": dt.strftime("%B"),
        "iso": dt.isoformat(),
        "timestamp": dt.timestamp(),
    }


def datetime_add(dt_str: str, days: int = 0, hours: int = 0, minutes: int = 0,
                 seconds: int = 0, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Add time to datetime."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.strptime(dt_str, format_str)

    dt += timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return dt.strftime(format_str)


def datetime_diff(dt1_str: str, dt2_str: str, unit: str = "seconds") -> float:
    """Calculate difference between two datetimes."""
    try:
        dt1 = datetime.fromisoformat(dt1_str.replace('Z', '+00:00'))
    except ValueError:
        dt1 = datetime.strptime(dt1_str, "%Y-%m-%d %H:%M:%S")

    try:
        dt2 = datetime.fromisoformat(dt2_str.replace('Z', '+00:00'))
    except ValueError:
        dt2 = datetime.strptime(dt2_str, "%Y-%m-%d %H:%M:%S")

    diff = dt1 - dt2
    total_seconds = diff.total_seconds()

    unit = unit.lower()
    if unit == "seconds":
        return total_seconds
    elif unit == "minutes":
        return total_seconds / 60
    elif unit == "hours":
        return total_seconds / 3600
    elif unit == "days":
        return total_seconds / 86400
    elif unit == "weeks":
        return total_seconds / 604800
    else:
        return total_seconds


def datetime_part(dt_str: str, part: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> int:
    """Extract a part from datetime."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.strptime(dt_str, format_str)

    part = part.lower()
    part_map = {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
        "weekday": dt.weekday(),
        "yearday": dt.timetuple().tm_yday,
        "week": dt.isocalendar()[1],
    }

    return part_map.get(part, 0)


def timestamp_now() -> float:
    """Get current timestamp."""
    return time.time()


def timestamp_to_datetime(timestamp: float, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Convert timestamp to datetime string."""
    return datetime.fromtimestamp(timestamp).strftime(format_str)


def datetime_to_timestamp(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> float:
    """Convert datetime string to timestamp."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.strptime(dt_str, format_str)
    return dt.timestamp()


# ── Encoding/Decoding Processors ─────────────────────────────────────────────

def base64_encode(text: str, encoding: str = "utf-8") -> str:
    """Encode text to Base64."""
    return base64.b64encode(text.encode(encoding)).decode("ascii")


def base64_decode(encoded: str, encoding: str = "utf-8") -> str:
    """Decode Base64 to text."""
    return base64.b64decode(encoded).decode(encoding)


def url_encode(text: str) -> str:
    """URL encode text."""
    return urllib.parse.quote(text, safe="")


def url_decode(encoded: str) -> str:
    """URL decode text."""
    return urllib.parse.unquote(encoded)


def html_encode(text: str) -> str:
    """HTML encode text."""
    return html.escape(text)


def html_decode(encoded: str) -> str:
    """HTML decode text."""
    return html.unescape(encoded)


def unicode_encode(text: str) -> str:
    """Encode text to Unicode escape sequences."""
    return text.encode("unicode_escape").decode("ascii")


def unicode_decode(encoded: str) -> str:
    """Decode Unicode escape sequences to text."""
    return encoded.encode("ascii").decode("unicode_escape")


def hex_encode(text: str, encoding: str = "utf-8") -> str:
    """Encode text to hexadecimal."""
    return text.encode(encoding).hex()


def hex_decode(hex_str: str, encoding: str = "utf-8") -> str:
    """Decode hexadecimal to text."""
    return bytes.fromhex(hex_str).decode(encoding)


# ── System Info Processors ────────────────────────────────────────────────────

def sys_platform() -> str:
    """Get operating system platform."""
    return sys.platform


def sys_version() -> str:
    """Get Python version."""
    return sys.version


def sys_architecture() -> str:
    """Get system architecture."""
    return platform.machine()


def sys_hostname() -> str:
    """Get system hostname."""
    return socket.gethostname()


def sys_username() -> str:
    """Get current username."""
    import getpass
    return getpass.getuser()


def sys_cpu_count() -> int:
    """Get number of CPUs."""
    return os.cpu_count() or 0


def sys_memory_info() -> dict[str, Any]:
    """Get memory information."""
    import psutil
    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent,
    }


def sys_disk_info(path: str = "/") -> dict[str, Any]:
    """Get disk information."""
    import psutil
    disk = psutil.disk_usage(path)
    return {
        "total": disk.total,
        "used": disk.used,
        "free": disk.free,
        "percent": disk.percent,
    }


def sys_current_dir() -> str:
    """Get current working directory."""
    return os.getcwd()


def sys_home_dir() -> str:
    """Get home directory."""
    return os.path.expanduser("~")


def sys_temp_dir() -> str:
    """Get temporary directory."""
    import tempfile
    return tempfile.gettempdir()


def sys_env_vars() -> dict[str, str]:
    """Get all environment variables."""
    return dict(os.environ)


# ── Network Processors ───────────────────────────────────────────────────────

def net_hostname() -> str:
    """Get local hostname."""
    return socket.gethostname()


def net_ip_address(hostname: str = "") -> str:
    """Get IP address for hostname."""
    if not hostname:
        hostname = socket.gethostname()
    return socket.gethostbyname(hostname)


def net_ping(host: str, timeout: float = 3.0) -> bool:
    """Ping a host."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host],
                capture_output=True, timeout=timeout + 1
            )
        else:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout)), host],
                capture_output=True, timeout=timeout + 1
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def net_port_check(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def net_url_parse(url: str) -> dict[str, str]:
    """Parse a URL into components."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return {
        "scheme": parsed.scheme,
        "netloc": parsed.netloc,
        "path": parsed.path,
        "params": parsed.params,
        "query": parsed.query,
        "fragment": parsed.fragment,
        "hostname": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "username": parsed.username or "",
        "password": parsed.password or "",
        "params_dict": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
    }


def net_url_build(scheme: str = "https", host: str = "", path: str = "",
                  params: dict = None, port: int = 0) -> str:
    """Build a URL from components."""
    netloc = host
    if port:
        netloc = f"{host}:{port}"

    query = ""
    if params:
        query = urllib.parse.urlencode(params)

    return urllib.parse.urlunparse((scheme, netloc, path, "", query, ""))


def net_mac_address() -> str:
    """Get MAC address."""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))


# ── Validation Processors ────────────────────────────────────────────────────

def validate_email(email: str) -> bool:
    """Validate email address."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """Validate URL."""
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def validate_ip(ip: str) -> bool:
    """Validate IP address (IPv4 or IPv6)."""
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except OSError:
        try:
            socket.inet_pton(socket.AF_INET6, ip)
            return True
        except OSError:
            return False


def validate_phone(phone: str, country: str = "CN") -> bool:
    """Validate phone number."""
    # Remove spaces and dashes
    phone = re.sub(r'[\s-]', '', phone)

    if country == "CN":
        # Chinese phone numbers
        pattern = r'^(\+86)?1[3-9]\d{9}$'
    elif country == "US":
        # US phone numbers
        pattern = r'^(\+1)?[2-9]\d{2}[2-9]\d{6}$'
    else:
        # Generic pattern
        pattern = r'^\+?[\d\s-]{7,15}$'

    return bool(re.match(pattern, phone))


def validate_id_card(id_card: str, country: str = "CN") -> bool:
    """Validate ID card number."""
    if country == "CN":
        # Chinese ID card (18 digits)
        if len(id_card) != 18:
            return False
        pattern = r'^\d{17}[\dXx]$'
        if not re.match(pattern, id_card):
            return False
        # Validate checksum
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = '10X98765432'
        total = sum(int(id_card[i]) * weights[i] for i in range(17))
        return check_codes[total % 11] == id_card[17].upper()
    return True


def validate_credit_card(number: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    number = number.replace(' ', '').replace('-', '')
    if not number.isdigit():
        return False

    total = 0
    for i, digit in enumerate(reversed(number)):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


def validate_regex(text: str, pattern: str) -> bool:
    """Validate text against regex pattern."""
    try:
        return bool(re.match(pattern, text))
    except re.error:
        return False


def validate_range(value: float, min_val: float, max_val: float) -> bool:
    """Validate value is within range."""
    return min_val <= value <= max_val


def validate_length(text: str, min_len: int = 0, max_len: int = 0) -> bool:
    """Validate text length."""
    length = len(text)
    if min_len > 0 and length < min_len:
        return False
    if max_len > 0 and length > max_len:
        return False
    return True


# ── Hash Processors ──────────────────────────────────────────────────────────

def hash_md5(text: str, encoding: str = "utf-8") -> str:
    """Calculate MD5 hash."""
    return hashlib.md5(text.encode(encoding)).hexdigest()


def hash_sha1(text: str, encoding: str = "utf-8") -> str:
    """Calculate SHA1 hash."""
    return hashlib.sha1(text.encode(encoding)).hexdigest()


def hash_sha256(text: str, encoding: str = "utf-8") -> str:
    """Calculate SHA256 hash."""
    return hashlib.sha256(text.encode(encoding)).hexdigest()


def hash_sha512(text: str, encoding: str = "utf-8") -> str:
    """Calculate SHA512 hash."""
    return hashlib.sha512(text.encode(encoding)).hexdigest()


def hash_crc32(text: str, encoding: str = "utf-8") -> str:
    """Calculate CRC32 hash."""
    return format(zlib.crc32(text.encode(encoding)) & 0xffffffff, '08x')


def hash_hmac(text: str, key: str, algorithm: str = "sha256", encoding: str = "utf-8") -> str:
    """Calculate HMAC hash."""
    import hmac
    return hmac.new(
        key.encode(encoding),
        text.encode(encoding),
        getattr(hashlib, algorithm)
    ).hexdigest()


def hash_uuid(namespace: str = "", name: str = "") -> str:
    """Generate UUID."""
    if namespace and name:
        # UUID5 (name-based)
        ns_uuid = uuid.UUID(namespace)
        return str(uuid.uuid5(ns_uuid, name))
    return str(uuid.uuid4())


def hash_uuid5(namespace: str, name: str) -> str:
    """Generate UUID5 (name-based)."""
    ns_uuid = uuid.UUID(namespace)
    return str(uuid.uuid5(ns_uuid, name))


# ── Color Processors ─────────────────────────────────────────────────────────

def color_hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def color_rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB to hex color."""
    return f'#{r:02x}{g:02x}{b:02x}'


def color_hsl_to_rgb(h: float, s: float, lightness: float) -> tuple[int, int, int]:
    """Convert HSL to RGB."""
    h = h / 360
    s = s / 100
    lightness = lightness / 100

    if s == 0:
        r = g = b = lightness
    else:
        def hue2rgb(p, q, t):
            if t < 0:
                t += 1
            if t > 1:
                t -= 1
            if t < 1/6:
                return p + (q - p) * 6 * t
            if t < 1/2:
                return q
            if t < 2/3:
                return p + (q - p) * (2/3 - t) * 6
            return p

        q = lightness * (1 + s) if lightness < 0.5 else lightness + s - lightness * s
        p = 2 * lightness - q
        r = hue2rgb(p, q, h + 1/3)
        g = hue2rgb(p, q, h)
        b = hue2rgb(p, q, h - 1/3)

    return (int(r * 255), int(g * 255), int(b * 255))


def color_rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to HSL."""
    r, g, b = r / 255, g / 255, b / 255
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    h = s = lightness = (max_val + min_val) / 2

    if max_val == min_val:
        h = s = 0
    else:
        d = max_val - min_val
        s = d / (2 - max_val - min_val) if lightness > 0.5 else d / (max_val + min_val)
        if max_val == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif max_val == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h /= 6

    return (h * 360, s * 100, lightness * 100)


def color_brightness(hex_color: str) -> float:
    """Calculate brightness of a color (0-100)."""
    r, g, b = color_hex_to_rgb(hex_color)
    return (r * 299 + g * 587 + b * 114) / 1000 / 255 * 100


def color_contrast(hex_color: str) -> str:
    """Get contrasting text color (black or white)."""
    brightness = color_brightness(hex_color)
    return "#000000" if brightness > 50 else "#ffffff"


def color_complementary(hex_color: str) -> str:
    """Get complementary color."""
    r, g, b = color_hex_to_rgb(hex_color)
    return color_rgb_to_hex(255 - r, 255 - g, 255 - b)


def color_random() -> str:
    """Generate random color."""
    import random
    return f'#{random.randint(0, 0xffffff):06x}'


# ── Set Operations ───────────────────────────────────────────────────────────

def set_union(set1: list, set2: list) -> list:
    """Union of two sets."""
    return list(set(set1) | set(set2))


def set_intersection(set1: list, set2: list) -> list:
    """Intersection of two sets."""
    return list(set(set1) & set(set2))


def set_difference(set1: list, set2: list) -> list:
    """Difference of two sets."""
    return list(set(set1) - set(set2))


def set_symmetric_difference(set1: list, set2: list) -> list:
    """Symmetric difference of two sets."""
    return list(set(set1) ^ set(set2))


def set_is_subset(set1: list, set2: list) -> bool:
    """Check if set1 is subset of set2."""
    return set(set1).issubset(set(set2))


def set_is_superset(set1: list, set2: list) -> bool:
    """Check if set1 is superset of set2."""
    return set(set1).issuperset(set(set2))


def set_unique(items: list) -> list:
    """Remove duplicates from list."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ── Dictionary Operations ────────────────────────────────────────────────────

def dict_keys(data: dict) -> list:
    """Get dictionary keys."""
    return list(data.keys())


def dict_values(data: dict) -> list:
    """Get dictionary values."""
    return list(data.values())


def dict_items(data: dict) -> list:
    """Get dictionary items as list of [key, value] pairs."""
    return [[k, v] for k, v in data.items()]


def dict_merge(*dicts: dict) -> dict:
    """Merge multiple dictionaries."""
    result = {}
    for d in dicts:
        if isinstance(d, dict):
            result.update(d)
    return result


def dict_get(data: dict, key: str, default: Any = None) -> Any:
    """Get value from dictionary."""
    return data.get(key, default)


def dict_set(data: dict, key: str, value: Any) -> dict:
    """Set value in dictionary."""
    result = dict(data)
    result[key] = value
    return result


def dict_delete(data: dict, key: str) -> dict:
    """Delete key from dictionary."""
    result = dict(data)
    result.pop(key, None)
    return result


def dict_filter(data: dict, keys: list) -> dict:
    """Filter dictionary by keys."""
    return {k: v for k, v in data.items() if k in keys}


def dict_map(data: dict, func) -> dict:
    """Map function over dictionary values."""
    return {k: func(v) for k, v in data.items()}


# ── String Formatting ────────────────────────────────────────────────────────

def str_format(template: str, **kwargs) -> str:
    """Format string with named parameters."""
    return template.format(**kwargs)


def str_template(template: str, **kwargs) -> str:
    """Format string template with $variables."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f'${{{key}}}', str(value))
    return result


def str_pad_left(text: str, width: int, fillchar: str = " ") -> str:
    """Pad string on the left."""
    return text.rjust(width, fillchar)


def str_pad_right(text: str, width: int, fillchar: str = " ") -> str:
    """Pad string on the right."""
    return text.ljust(width, fillchar)


def str_pad_center(text: str, width: int, fillchar: str = " ") -> str:
    """Pad string in center."""
    return text.center(width, fillchar)


def str_truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def str_repeat(text: str, count: int) -> str:
    """Repeat string."""
    return text * count


def str_replace_multiple(text: str, replacements: dict) -> str:
    """Replace multiple patterns."""
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


# ── Compression Processors ───────────────────────────────────────────────────

def compress_gzip(data: str, encoding: str = "utf-8") -> bytes:
    """Compress data with gzip."""
    import gzip
    return gzip.compress(data.encode(encoding))


def decompress_gzip(data: bytes, encoding: str = "utf-8") -> str:
    """Decompress gzip data."""
    import gzip
    return gzip.decompress(data).decode(encoding)


def compress_zlib(data: str, encoding: str = "utf-8") -> bytes:
    """Compress data with zlib."""
    return zlib.compress(data.encode(encoding))


def decompress_zlib(data: bytes, encoding: str = "utf-8") -> str:
    """Decompress zlib data."""
    return zlib.decompress(data).decode(encoding)


def compress_deflate(data: str, encoding: str = "utf-8") -> bytes:
    """Compress data with deflate."""
    return zlib.compress(data.encode(encoding), zlib.Z_BEST_COMPRESSION)


def decompress_deflate(data: bytes, encoding: str = "utf-8") -> str:
    """Decompress deflate data."""
    return zlib.decompress(data).decode(encoding)


# ── Environment Processors ───────────────────────────────────────────────────

def env_get(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.environ.get(key, default)


def env_set(key: str, value: str) -> None:
    """Set environment variable."""
    os.environ[key] = value


def env_list() -> dict[str, str]:
    """List all environment variables."""
    return dict(os.environ)


def env_path() -> list[str]:
    """Get PATH directories."""
    path = os.environ.get("PATH", "")
    separator = ";" if sys.platform == "win32" else ":"
    return path.split(separator)


def env_expand(text: str) -> str:
    """Expand environment variables in text."""
    return os.path.expandvars(text)


# ── Math Extended ────────────────────────────────────────────────────────────

def math_sin(x: float) -> float:
    """Calculate sine."""
    import math
    return math.sin(x)


def math_cos(x: float) -> float:
    """Calculate cosine."""
    import math
    return math.cos(x)


def math_tan(x: float) -> float:
    """Calculate tangent."""
    import math
    return math.tan(x)


def math_sqrt(x: float) -> float:
    """Calculate square root."""
    import math
    return math.sqrt(x)


def math_log(x: float, base: float = 2.718281828459045) -> float:
    """Calculate logarithm."""
    import math
    if base == 2.718281828459045:
        return math.log(x)
    return math.log(x, base)


def math_log10(x: float) -> float:
    """Calculate base-10 logarithm."""
    import math
    return math.log10(x)


def math_exp(x: float) -> float:
    """Calculate e^x."""
    import math
    return math.exp(x)


def math_pow(base: float, exp: float) -> float:
    """Calculate base^exp."""
    return base ** exp


def math_factorial(n: int) -> int:
    """Calculate factorial."""
    import math
    return math.factorial(n)


def math_gcd(a: int, b: int) -> int:
    """Calculate greatest common divisor."""
    import math
    return math.gcd(a, b)


def math_lcm(a: int, b: int) -> int:
    """Calculate least common multiple."""
    import math
    return abs(a * b) // math.gcd(a, b)


def math_fibonacci(n: int) -> list[int]:
    """Generate Fibonacci sequence."""
    if n <= 0:
        return []
    if n == 1:
        return [0]

    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return fib
