"""Deprecated update manifest trust compatibility helpers.

Runtime update checks use :mod:`services.update.trust`.  This legacy manifest
verifier is kept for old imports only, and it fails closed when no source-tree
public key is pinned.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ed25519 public key (base64url-encoded, 32 bytes).
# This is the pinned trust root for all official release artifacts.
# In CI, the corresponding private key signs every release manifest.
_PINNED_PUBLIC_KEY_B64: str = ""

# Allowed signature schemes.
_KNOWN_SCHEMES = frozenset({"ed25519"})


class SignatureVerificationError(ValueError):
    """Raised when a release manifest signature is missing, malformed, or invalid."""


def verify_manifest_signature(manifest_path: str | Path) -> bool:
    """Verify the Ed25519 signature on a release manifest JSON file.

    The manifest must contain:
      - ``signature``: dict with ``scheme``, ``value`` (base64url-encoded)
      - All other fields are covered by the signature.

    Returns True if the signature is valid.
    Raises ``SignatureVerificationError`` with a descriptive message on failure.
    """
    if not _PINNED_PUBLIC_KEY_B64:
        raise SignatureVerificationError("no update signature public key pinned; use services.update.trust")

    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise SignatureVerificationError(f"manifest not found: {manifest_path}")

    try:
        raw = manifest_path.read_bytes()
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        raise SignatureVerificationError(f"invalid manifest JSON: {exc}") from exc

    signature = data.pop("signature", None)
    if not isinstance(signature, dict):
        raise SignatureVerificationError("manifest missing 'signature' field")

    scheme = str(signature.get("scheme") or "").lower()
    if scheme not in _KNOWN_SCHEMES:
        raise SignatureVerificationError(f"unsupported signature scheme: {scheme}")

    sig_bytes = _decode_sig_value(signature.get("value"))
    if sig_bytes is None:
        raise SignatureVerificationError("invalid signature value")

    pub_key = _load_public_key()
    if pub_key is None:
        raise SignatureVerificationError("failed to load public key")

    canonical = _canonical_json(data).encode("utf-8")

    if scheme == "ed25519":
        return _verify_ed25519(pub_key, canonical, sig_bytes)

    raise SignatureVerificationError(f"unsupported signature scheme: {scheme}")


def verify_installer_hash(installer_path: str | Path, expected_sha256: str) -> bool:
    """Verify that *installer_path* matches the expected SHA-256 hex digest."""
    h = hashlib.sha256()
    with open(installer_path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    actual = h.hexdigest().lower()
    expected = expected_sha256.strip().lower()
    return actual == expected


def _canonical_json(data: dict) -> str:
    """Produce a stable JSON string for signing, with sorted keys and no extra whitespace."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _decode_sig_value(value: object) -> bytes | None:
    if isinstance(value, str):
        try:
            return base64.urlsafe_b64decode(value)
        except Exception:
            return None
    if isinstance(value, list):
        try:
            return bytes(value)
        except Exception:
            return None
    return None


def _load_public_key() -> bytes | None:
    if not _PINNED_PUBLIC_KEY_B64:
        return None
    try:
        return base64.urlsafe_b64decode(_PINNED_PUBLIC_KEY_B64)
    except Exception as exc:
        logger.error("failed to decode pinned public key: %s", exc)
        return None


def _verify_ed25519(pub_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        verify_key = Ed25519PublicKey.from_public_bytes(pub_key)
        verify_key.verify(signature, message)
        return True
    except ImportError:
        raise SignatureVerificationError(
            "cryptography library not available for legacy manifest verification"
        ) from None
    except InvalidSignature:
        raise SignatureVerificationError("Ed25519 signature does not match manifest content") from None
    except Exception as exc:
        raise SignatureVerificationError(f"signature verification error: {exc}") from exc
