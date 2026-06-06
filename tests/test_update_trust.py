from types import SimpleNamespace

from services.update.config import UpdateConfig, UpdateInfo
from services.update.trust import update_signature_payload, verify_update_signature

RFC8032_PUBLIC_KEY = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC8032_EMPTY_SIGNATURE = (
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555"
    "fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def test_verify_update_signature_ed25519_rfc8032_vector():
    assert verify_update_signature(b"", RFC8032_EMPTY_SIGNATURE, (RFC8032_PUBLIC_KEY,)) is True
    assert verify_update_signature(b"tampered", RFC8032_EMPTY_SIGNATURE, (RFC8032_PUBLIC_KEY,)) is False


def test_update_config_requires_signature_by_default():
    assert UpdateConfig().require_signature is True


def test_update_signature_payload_is_canonical():
    left = UpdateInfo(version="1.2.3", download_url="https://example.com/a.exe", file_hash="sha256:" + "a" * 64, file_size=123)
    right = SimpleNamespace(file_size=123, file_hash="sha256:" + "a" * 64, download_url="https://example.com/a.exe", version="1.2.3")

    assert update_signature_payload(left) == update_signature_payload(right)


def test_update_checker_requires_signature_when_configured(monkeypatch):
    from services.update.checker import UpdateChecker

    checker = UpdateChecker(
        UpdateConfig(
            require_signature=True,
            signature_public_keys=(RFC8032_PUBLIC_KEY,),
            allowed_download_hosts=("example.com",),
        )
    )
    info = UpdateInfo(
        has_update=True,
        version="1.2.3",
        download_url="https://example.com/a.exe",
        file_hash="sha256:" + "a" * 64,
        file_size=123,
    )

    assert "发布签名" in checker._validate_update_info(info)

    monkeypatch.setattr("services.update.checker.update_signature_payload", lambda _info: b"")
    info.file_signature = "ed25519:" + RFC8032_EMPTY_SIGNATURE

    assert checker._validate_update_info(info) == ""
