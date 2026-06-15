"""Clipboard content classifiers — detect URL, JSON, JWT, color, path, IP, etc.

Priority rules:
  1. Explicit reject (empty) > structural signature (JWT/JSON) > content match (URL/Email/IP) > fuzzy (path/color/code)
  2. Confidence threshold >= 0.8 for acceptance; below threshold → unknown
  3. Same-level tie → highest confidence wins → shortest matching string wins
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .clipboard_service import ClipboardClassification, ClipboardSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ── Constants ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_CONFIDENCE_THRESHOLD = 0.8

# URLs
_URL_RE = re.compile(
    r"^https?://[^\s/$.?#].[^\s]*$",
    re.IGNORECASE,
)

# IPv4
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# Email
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Domain (simple)
_DOMAIN_RE = re.compile(r"^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")

# Hex color (#RGB, #RRGGBB, #RRGGBBAA)
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# RGB/RGBA color
_RGB_COLOR_RE = re.compile(
    r"^rgba?\s*\(\s*\d{1,3}\s*(,\s*\d{1,3}\s*){2,3}\)$",
    re.IGNORECASE,
)

# HSL color
_HSL_COLOR_RE = re.compile(
    r"^hsla?\s*\(\s*\d{1,3}\s*(,\s*\d{1,3}%?\s*){2,3}\)$",
    re.IGNORECASE,
)

# Windows absolute path
_WIN_PATH_RE = re.compile(r"^[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*$")

# Unix absolute path
_UNIX_PATH_RE = re.compile(r"^/(?:[^/\0]+/)*[^/\0]*$")

# JWT (three base64url segments)
_JWT_RE = re.compile(r"^eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$")

# OpenAI API key
_OPENAI_KEY_RE = re.compile(r"^sk-[a-zA-Z0-9]{20,}$")

# Detect if text looks like code (has common keywords/syntax)
_CODE_INDICATORS = {
    "def ",
    "class ",
    "import ",
    "return ",
    "if __name__",
    "function ",
    "const ",
    "let ",
    "var ",
    "=>",
    "::",
    "pub fn",
    "impl ",
    "#include",
    "int main",
    "void ",
    "SELECT ",
    "FROM ",
    "WHERE ",
}

# Known plain text indicators (short, no special structure)
_MAX_CLASSIFY_TEXT_LENGTH = 100 * 1024  # 100 KB


# ---------------------------------------------------------------------------
# ── Classifier helpers ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _is_json(text: str) -> tuple[bool, float]:
    """Check if text is valid JSON."""
    stripped = text.strip()
    if not stripped:
        return False, 0.0
    if stripped[0] not in ("{", "["):
        return False, 0.0
    try:
        json.loads(stripped)
        return True, 0.98
    except (json.JSONDecodeError, ValueError):
        return False, 0.0


def _is_url(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _URL_RE.match(stripped):
        # Check for common URL patterns to adjust confidence
        if stripped.startswith("https://"):
            return True, 0.98
        return True, 0.95
    return False, 0.0


def _is_jwt(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _JWT_RE.match(stripped):
        return True, 0.97
    return False, 0.0


def _is_color(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _HEX_COLOR_RE.match(stripped):
        return True, 0.95
    if _RGB_COLOR_RE.match(stripped):
        return True, 0.90
    if _HSL_COLOR_RE.match(stripped):
        return True, 0.85
    return False, 0.0


def _is_path(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _WIN_PATH_RE.match(stripped):
        exists = os.path.exists(stripped)
        return True, 0.95 if exists else 0.80
    if _UNIX_PATH_RE.match(stripped):
        exists = os.path.exists(stripped)
        return True, 0.90 if exists else 0.80
    return False, 0.0


def _is_ip(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _IP_RE.match(stripped):
        parts = stripped.split(".")
        valid = all(0 <= int(p) <= 255 for p in parts if p.isdigit())
        if valid:
            return True, 0.95
    return False, 0.0


def _is_email(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _EMAIL_RE.match(stripped):
        return True, 0.90
    return False, 0.0


def _is_domain(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _DOMAIN_RE.match(stripped):
        return True, 0.85
    return False, 0.0


def _is_code(text: str) -> tuple[bool, float]:
    """Check if text looks like source code."""
    stripped = text.strip()
    if len(stripped) < 30:
        return False, 0.0
    lines = stripped.splitlines()
    if len(lines) < 3:
        return False, 0.0
    indicator_count = sum(1 for ind in _CODE_INDICATORS if ind in stripped)
    if indicator_count >= 2:
        return True, 0.85
    return False, 0.0


def _is_api_key(text: str) -> tuple[bool, float]:
    stripped = text.strip()
    if _OPENAI_KEY_RE.match(stripped):
        return True, 0.98
    return False, 0.0


# ---------------------------------------------------------------------------
# ── Priority-ordered classifiers ─────────────────────────────────────────
# ---------------------------------------------------------------------------

# Each entry: (name, classifier_fn, priority_group)
# Priority groups: 0=explicit reject, 1=structural signature, 2=content match, 3=fuzzy
_CLASSIFIERS = [
    # Group 0: explicit reject
    ("empty", lambda t: (not t.strip(), 1.0), 0),
    # Group 1: structural signature
    ("jwt", _is_jwt, 1),
    ("json", _is_json, 1),
    # Group 2: content match
    ("api_key", _is_api_key, 2),
    ("url", _is_url, 2),
    ("email", _is_email, 2),
    ("ip", _is_ip, 2),
    ("domain", _is_domain, 2),
    # Group 3: fuzzy
    ("color", _is_color, 3),
    ("path", _is_path, 3),
    ("code", _is_code, 3),
]


def classify_text(text: str) -> tuple[str, float, str]:
    """Classify a text string.

    Returns:
        tuple of (kind, confidence, summary)
    """
    if not text:
        return "empty", 1.0, ""

    if len(text) > _MAX_CLASSIFY_TEXT_LENGTH:
        text = text[:_MAX_CLASSIFY_TEXT_LENGTH]

    best_kind = "unknown"
    best_confidence = 0.0
    best_priority = 999

    for name, classifier_fn, priority in _CLASSIFIERS:
        is_match, confidence = classifier_fn(text)
        if not is_match:
            continue

        # Priority-based selection
        if priority < best_priority:
            best_kind = name
            best_confidence = confidence
            best_priority = priority
        elif priority == best_priority and confidence > best_confidence:
            best_kind = name
            best_confidence = confidence
            best_priority = priority

    if best_confidence < _CONFIDENCE_THRESHOLD:
        best_kind = "unknown"
        best_confidence = 0.0

    summary = _make_summary(text, best_kind)
    return best_kind, best_confidence, summary


def _make_summary(text: str, kind: str) -> str:
    """Generate a short summary for the classified content."""
    if not text:
        return ""
    text = text.strip()

    if kind in ("url", "email", "ip", "domain"):
        return text[:200]
    elif kind == "json":
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                keys = list(parsed.keys())
                return f"JSON object: {', '.join(keys[:5])}{'...' if len(keys) > 5 else ''}"
            elif isinstance(parsed, list):
                return f"JSON array: {len(parsed)} items"
        except Exception:
            logger.debug("解析JSON内容失败", exc_info=True)
        return f"JSON: {len(text)} chars"
    elif kind == "jwt":
        parts = text.split(".")
        try:
            import base64

            padding = 4 - len(parts[0]) % 4
            if padding != 4:
                padded = parts[0] + "=" * padding
            else:
                padded = parts[0]
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
            header = json.loads(decoded)
            return f"JWT: alg={header.get('alg', '?')}, typ={header.get('typ', '?')}"
        except Exception:
            logger.debug("JWT header parse failed, using fallback label", exc_info=True)
            return f"JWT: {len(text)} chars"
    elif kind == "color":
        return text[:50]
    elif kind == "path":
        return text[:200]
    elif kind == "code":
        lines = text.strip().splitlines()
        return f"Code: {len(lines)} lines"
    elif kind == "api_key":
        return f"API key: {text[:8]}...{text[-4:]}"
    elif kind == "empty":
        return ""
    else:
        # Plain text — first 100 chars
        return text[:100].replace("\n", " ").strip()


def classify_clipboard(snapshot: ClipboardSnapshot) -> ClipboardClassification:
    """Classify clipboard content from a snapshot."""
    from .clipboard_service import ClipboardClassification

    # Priority: file_list > image > html > text
    if snapshot.file_paths:
        return ClipboardClassification(
            kind="file_list",
            confidence=0.95,
            summary=f"{len(snapshot.file_paths)} files: {snapshot.file_paths[0]}",
            actions=["copy_path", "hash"],
        )

    if snapshot.has_image:
        info = snapshot.image_info
        return ClipboardClassification(
            kind="image",
            confidence=0.95,
            summary=f"Image: {info.get('width', '?')}x{info.get('height', '?')}",
            actions=["save", "ocr"],
        )

    if snapshot.html:
        return ClipboardClassification(
            kind="html",
            confidence=0.90,
            summary=f"HTML: {len(snapshot.html)} chars",
            actions=["copy_plain"],
        )

    text = snapshot.text
    if not text:
        return ClipboardClassification(
            kind="empty",
            confidence=1.0,
            summary="",
            actions=[],
        )

    kind, confidence, summary = classify_text(text)
    actions = _suggest_actions(kind)
    return ClipboardClassification(
        kind=kind,
        confidence=confidence,
        summary=summary,
        actions=actions,
    )


def _suggest_actions(kind: str) -> list[str]:
    """Suggest actions based on clipboard kind."""
    action_map = {
        "url": ["open_url", "copy_domain", "qr_code"],
        "json": ["format_json", "compress_json"],
        "jwt": ["decode_jwt", "copy_payload"],
        "color": ["preview_color", "convert_color"],
        "path": ["copy_path", "open_location"],
        "ip": ["ping", "whois"],
        "email": ["compose_email"],
        "domain": ["ping", "whois"],
        "code": ["format_code", "copy_as_markdown"],
        "api_key": ["copy_redacted"],
        "file_list": ["copy_path", "hash"],
        "image": ["save", "ocr"],
        "html": ["copy_plain"],
    }
    return action_map.get(kind, [])


def classify_text_safe(text: str) -> dict:
    """Safe classification returning a dict instead of dataclass."""
    kind, confidence, summary = classify_text(text)
    return {
        "kind": kind,
        "confidence": confidence,
        "summary": summary,
        "actions": _suggest_actions(kind),
    }
