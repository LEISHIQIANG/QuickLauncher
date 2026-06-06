"""Update package trust helpers.

The updater already verifies package hashes.  This module adds an asymmetric
trust root so release metadata can be verified independently from the download
channel.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_BASE_POINT_BYTES = bytes.fromhex("5866666666666666666666666666666666666666666666666666666666666666")
DEFAULT_UPDATE_SIGNATURE_PUBLIC_KEYS: tuple[str, ...] = ()


class UpdateSignatureError(ValueError):
    """Raised when update signature data is malformed or invalid."""


def update_signature_payload(info: Any) -> bytes:
    """Return canonical bytes signed by the release process."""
    data = {
        "download_url": str(getattr(info, "download_url", "") or ""),
        "file_hash": str(getattr(info, "file_hash", "") or ""),
        "file_size": int(getattr(info, "file_size", 0) or 0),
        "version": str(getattr(info, "version", "") or ""),
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_update_signature(payload: bytes | str, signature: str, public_keys: tuple[str, ...] = ()) -> bool:
    """Verify an Ed25519 signature against any configured public key."""
    signature_bytes = _decode_key_material(signature, expected=64, label="signature")
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload or b"")
    keys = tuple(public_keys or DEFAULT_UPDATE_SIGNATURE_PUBLIC_KEYS)
    if not keys:
        raise UpdateSignatureError("no update signature public keys configured")
    for public_key in keys:
        try:
            if _verify_ed25519(payload_bytes, signature_bytes, _decode_key_material(public_key, expected=32, label="public key")):
                return True
        except UpdateSignatureError:
            raise
        except Exception:
            continue
    return False


def _decode_key_material(value: str, *, expected: int, label: str) -> bytes:
    text = str(value or "").strip()
    if ":" in text:
        _prefix, text = text.split(":", 1)
        text = text.strip()
    try:
        if len(text) == expected * 2 and all(ch in "0123456789abcdefABCDEF" for ch in text):
            raw = bytes.fromhex(text)
        else:
            raw = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise UpdateSignatureError(f"invalid {label}") from exc
    if len(raw) != expected:
        raise UpdateSignatureError(f"invalid {label} length")
    return raw


def _verify_ed25519(message: bytes, signature: bytes, public_key: bytes) -> bool:
    if len(signature) != 64 or len(public_key) != 32:
        return False
    r_bytes = signature[:32]
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    try:
        a = _decode_point(public_key)
        r = _decode_point(r_bytes)
    except UpdateSignatureError:
        return False
    h = int.from_bytes(hashlib.sha512(r_bytes + public_key + message).digest(), "little") % _Q
    return _scalar_mult(s, _decode_point(_BASE_POINT_BYTES)) == _point_add(r, _scalar_mult(h, a))


def _decode_point(data: bytes) -> tuple[int, int]:
    if len(data) != 32:
        raise UpdateSignatureError("invalid point length")
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    sign = data[31] >> 7
    if y >= _P:
        raise UpdateSignatureError("invalid point")
    x = _recover_x(y, sign)
    point = (x, y)
    if not _is_on_curve(point):
        raise UpdateSignatureError("point is not on curve")
    return point


def _recover_x(y: int, sign: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if (x * x - xx) % _P != 0:
        raise UpdateSignatureError("invalid x coordinate")
    if (x & 1) != sign:
        x = _P - x
    return x


def _is_on_curve(point: tuple[int, int]) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _P == 0


def _point_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    x_num = (x1 * y2 + x2 * y1) % _P
    x_den = pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P)
    y_num = (y1 * y2 + x1 * x2) % _P
    y_den = pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P)
    return (x_num * x_den % _P, y_num * y_den % _P)


def _scalar_mult(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result
