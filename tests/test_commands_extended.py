"""Extended tests for core/commands.py — targeting uncovered branches and helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import base64
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

import core

core.data_manager = MagicMock()
mock_settings = MagicMock()
mock_settings.favorite_commands = []
mock_settings.preprocessing_enabled = False
core.data_manager.get_settings.return_value = mock_settings
core.data_manager.data.folders = []

from core.command_registry import CommandContext  # noqa: E402
from core.commands import (  # noqa: E402
    _decode_base64url_json,
    _format_cert_subject,
    _get_primary_local_ip,
    _hash_file,
    _hex_to_rgb,
    _normalize_host_input,
    _normalize_tls_target,
    _parse_ping_summary,
    _qr_get_local_ip,
    _text_from_args_or_clipboard,
    cmd_base64,
    cmd_cidr,
    cmd_clip,
    cmd_color,
    cmd_conflict,
    cmd_copy_path,
    cmd_dns,
    cmd_hash,
    cmd_ip,
    cmd_json,
    cmd_jwt,
    cmd_netdiag,
    cmd_path_audit,
    cmd_port,
    cmd_selected,
    cmd_timestamp,
    cmd_tls,
    cmd_urlencode,
    cmd_wifi,
    stop_qr_file_server,
)
from core.selected_text_service import SelectedTextResult  # noqa: E402

# ===========================================================================
# ── _hex_to_rgb ────────────────────────────────────────────────────────────
# ===========================================================================


class TestHexToRgb:
    def test_six_digit_hex(self):
        assert _hex_to_rgb("#ff8800") == (255, 136, 0, None)

    def test_six_digit_no_hash(self):
        assert _hex_to_rgb("ff8800") == (255, 136, 0, None)

    def test_three_digit_hex(self):
        assert _hex_to_rgb("#f80") == (255, 136, 0, None)

    def test_eight_digit_hex_with_alpha(self):
        assert _hex_to_rgb("#ff88007f") == (255, 136, 0, 127)

    def test_four_digit_hex_with_alpha(self):
        assert _hex_to_rgb("#f80f") == (255, 136, 0, 255)

    def test_uppercase_hex(self):
        assert _hex_to_rgb("#FF8800") == (255, 136, 0, None)

    def test_invalid_hex_chars(self):
        assert _hex_to_rgb("#gggggg") is None

    def test_invalid_hex_8_chars(self):
        assert _hex_to_rgb("#gggggggg") is None

    def test_wrong_length(self):
        assert _hex_to_rgb("#ff") is None
        assert _hex_to_rgb("#ffff") == (255, 255, 255, 255)  # 4 chars handled as alpha, and is valid
        assert _hex_to_rgb("#fffff") is None
        assert _hex_to_rgb("#fffffff") is None

    def test_empty_string(self):
        assert _hex_to_rgb("") is None

    def test_whitespace_around_hex(self):
        assert _hex_to_rgb("  #ff8800  ") == (255, 136, 0, None)

    def test_all_zeros(self):
        assert _hex_to_rgb("#000000") == (0, 0, 0, None)

    def test_all_fs(self):
        assert _hex_to_rgb("#ffffff") == (255, 255, 255, None)

    def test_8digit_all_zeros(self):
        assert _hex_to_rgb("#00000000") == (0, 0, 0, 0)

    def test_8digit_all_fs(self):
        assert _hex_to_rgb("#ffffffff") == (255, 255, 255, 255)


# ===========================================================================
# ── _hash_file ─────────────────────────────────────────────────────────────
# ===========================================================================


class TestHashFile:
    def test_md5(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = _hash_file(str(f), "md5")
        assert result == hashlib.md5(b"hello").hexdigest()

    def test_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = _hash_file(str(f), "sha256")
        assert result == hashlib.sha256(b"hello").hexdigest()

    def test_sha1(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = _hash_file(str(f), "sha1")
        assert result == hashlib.sha1(b"hello").hexdigest()

    def test_large_file_chunked_read(self, tmp_path):
        f = tmp_path / "big.bin"
        data = b"x" * 200000
        f.write_bytes(data)
        result = _hash_file(str(f), "md5")
        assert result == hashlib.md5(data).hexdigest()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = _hash_file(str(f), "md5")
        assert result == hashlib.md5(b"").hexdigest()


# ===========================================================================
# ── _qr_get_local_ip ───────────────────────────────────────────────────────
# ===========================================================================


class TestQrGetLocalIp:
    def test_returns_string(self):
        ip = _qr_get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    @patch("core.commands.socket.getaddrinfo")
    def test_prefers_enumerated_non_loopback_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("127.0.0.1", 0)),
            (None, None, None, None, ("192.168.1.20", 0)),
        ]

        ip = _qr_get_local_ip()

        assert ip == "192.168.1.20"

    @patch("core.commands_utils.socket.getaddrinfo")
    @patch("core.commands_utils.socket.socket")
    def test_fallback_on_exception(self, mock_socket_cls, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = Exception("no addresses")
        mock_socket_cls.side_effect = Exception("no network")
        ip = _qr_get_local_ip()
        assert ip == "127.0.0.1"


# ===========================================================================
# ── _text_from_args_or_clipboard ───────────────────────────────────────────
# ===========================================================================


class TestTextFromArgsOrClipboard:
    def test_uses_args_text(self):
        ctx = CommandContext(args_text="hello", clipboard_text="world")
        assert _text_from_args_or_clipboard(ctx) == "hello"

    def test_falls_back_to_clipboard(self):
        ctx = CommandContext(args_text="", clipboard_text="world")
        assert _text_from_args_or_clipboard(ctx) == "world"

    def test_both_empty(self):
        ctx = CommandContext(args_text="", clipboard_text="")
        assert _text_from_args_or_clipboard(ctx) == ""

    def test_explicit_args_text_override(self):
        ctx = CommandContext(args_text="original", clipboard_text="world")
        assert _text_from_args_or_clipboard(ctx, "override") == "override"

    def test_strips_whitespace(self):
        ctx = CommandContext(args_text="  hello  ")
        assert _text_from_args_or_clipboard(ctx) == "hello"


# ===========================================================================
# ── _decode_base64url_json ─────────────────────────────────────────────────
# ===========================================================================


class TestDecodeBase64urlJson:
    def test_valid_json_object(self):
        raw = json.dumps({"alg": "HS256"}).encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        result = _decode_base64url_json(encoded)
        assert result == {"alg": "HS256"}

    def test_padding_added(self):
        raw = json.dumps({"k": "v"}).encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        result = _decode_base64url_json(encoded)
        assert result == {"k": "v"}

    def test_non_dict_raises(self):
        raw = json.dumps([1, 2, 3]).encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        with pytest.raises(ValueError, match="JWT 片段不是 JSON 对象"):
            _decode_base64url_json(encoded)

    def test_invalid_base64_raises(self):
        with pytest.raises((ValueError, TypeError, base64.binascii.Error)):
            _decode_base64url_json("!!!invalid!!!")


# ===========================================================================
# ── _normalize_host_input ──────────────────────────────────────────────────
# ===========================================================================


class TestNormalizeHostInput:
    def test_plain_host(self):
        host, port = _normalize_host_input("example.com")
        assert host == "example.com"
        assert port is None

    def test_host_with_port(self):
        host, port = _normalize_host_input("example.com:8080")
        assert host == "example.com"
        assert port == 8080

    def test_with_scheme(self):
        host, port = _normalize_host_input("https://example.com:443/path")
        assert host == "example.com"
        assert port == 443

    def test_ip_address(self):
        host, port = _normalize_host_input("192.168.1.1")
        assert host == "192.168.1.1"
        assert port is None

    def test_ipv6_brackets_stripped(self):
        host, port = _normalize_host_input("[::1]:8080")
        assert host == "::1"
        assert port == 8080

    def test_empty_input(self):
        host, port = _normalize_host_input("")
        assert host == ""
        assert port is None

    def test_whitespace_only(self):
        host, port = _normalize_host_input("   ")
        assert host == ""
        assert port is None


# ===========================================================================
# ── _parse_ping_summary ────────────────────────────────────────────────────
# ===========================================================================


class TestParsePingSummary:
    def test_windows_style(self):
        output = "Minimum = 10ms, Maximum = 20ms, Average = 15ms"
        result = _parse_ping_summary(output)
        assert "15ms" in result

    def test_unix_style(self):
        output = "rtt min/avg/max/mdev = 10.5/15.2/20.1/2.3 ms"
        result = _parse_ping_summary(output)
        assert "15.2" in result

    def test_chinese_style(self):
        output = "最短 = 10ms，最长 = 20ms，平均 = 12ms"
        result = _parse_ping_summary(output)
        assert "12ms" in result

    def test_no_match(self):
        output = "some random output with no ping stats"
        result = _parse_ping_summary(output)
        assert result == "未解析到平均延迟"

    def test_empty_output(self):
        result = _parse_ping_summary("")
        assert result == "未解析到平均延迟"

    def test_less_than_symbol(self):
        output = "Minimum = 1ms, Maximum = 5ms, Average = <1ms"
        result = _parse_ping_summary(output)
        assert result == "平均延迟: <1ms"


# ===========================================================================
# ── _normalize_tls_target ──────────────────────────────────────────────────
# ===========================================================================


class TestNormalizeTlsTarget:
    def test_plain_host(self):
        ascii_host, port, display = _normalize_tls_target("example.com")
        assert ascii_host == "example.com"
        assert port == 443
        assert display == "example.com"

    def test_with_scheme(self):
        ascii_host, port, display = _normalize_tls_target("https://example.com:8443")
        assert ascii_host == "example.com"
        assert port == 8443

    def test_host_with_extra_port(self):
        ascii_host, port, display = _normalize_tls_target("example.com 8443")
        assert ascii_host == "example.com"
        assert port == 8443

    def test_empty_input(self):
        ascii_host, port, display = _normalize_tls_target("")
        assert ascii_host == ""
        assert port == 443

    def test_trailing_punctuation_stripped(self):
        ascii_host, port, display = _normalize_tls_target("example.com.")
        assert ascii_host == "example.com"

    def test_trailing_comma_semicolon(self):
        ascii_host, port, display = _normalize_tls_target("example.com,;")
        assert ascii_host == "example.com"


# ===========================================================================
# ── _format_cert_subject ───────────────────────────────────────────────────
# ===========================================================================


class TestFormatCertSubject:
    def test_normal_subject(self):
        value = ((("commonName", "example.com"), ("organizationName", "Example Inc"), ("countryName", "US")),)
        result = _format_cert_subject(value)
        assert "commonName=example.com" in result
        assert "organizationName=Example Inc" in result
        assert "countryName=US" in result

    def test_empty_subject(self):
        assert _format_cert_subject(None) == "-"
        assert _format_cert_subject([]) == "-"

    def test_unknown_keys_ignored(self):
        value = ((("stateOrProvinceName", "CA"), ("localityName", "SF")),)
        result = _format_cert_subject(value)
        assert result == "-"

    def test_mixed_known_unknown(self):
        value = ((("commonName", "example.com"), ("stateOrProvinceName", "CA")),)
        result = _format_cert_subject(value)
        assert result == "commonName=example.com"


# ===========================================================================
# ── cmd_urlencode edge cases ───────────────────────────────────────────────
# ===========================================================================


class TestCmdUrlencodeEdgeCases:
    def test_decode_mode_via_args(self):
        ctx = CommandContext(args_text="", args={"mode": "decode"})
        ctx.args_text = "%E4%BD%A0%E5%A5%BD"
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "你好"

    def test_decode_short_alias_d(self):
        ctx = CommandContext(args_text="d hello%20world")
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "hello world"

    def test_encode_short_alias_e(self):
        ctx = CommandContext(args_text="e hello world")
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "hello%20world"

    def test_chinese_alias_decode(self):
        ctx = CommandContext(args_text="解码 hello%20world")
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "hello world"

    def test_chinese_alias_encode(self):
        ctx = CommandContext(args_text="编码 hello world")
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "hello%20world"

    def test_empty_input_no_clipboard(self):
        ctx = CommandContext(args_text="")
        res = cmd_urlencode(ctx)
        assert res.success is False
        assert "缺少输入" in res.error

    def test_clipboard_fallback_for_decode(self):
        ctx = CommandContext(args_text="decode", clipboard_text="hello%20world")
        res = cmd_urlencode(ctx)
        assert res.success is True
        assert res.message == "hello world"

    def test_encode_result_has_copy_action(self):
        ctx = CommandContext(args_text="test")
        res = cmd_urlencode(ctx)
        assert len(res.actions) == 1
        assert res.actions[0].type == "copy"
        assert res.actions[0].value == "test"

    def test_decode_result_has_copy_action(self):
        ctx = CommandContext(args_text="decode test%20data")
        res = cmd_urlencode(ctx)
        assert len(res.actions) == 1
        assert res.actions[0].type == "copy"
        assert res.actions[0].value == "test data"


# ===========================================================================
# ── cmd_color edge cases ───────────────────────────────────────────────────
# ===========================================================================


class TestCmdColorEdgeCases:
    def test_empty_input_no_clipboard(self):
        ctx = CommandContext(args_text="")
        res = cmd_color(ctx)
        assert res.success is False
        assert "缺少输入" in res.error

    def test_uses_clipboard(self):
        ctx = CommandContext(args_text="", clipboard_text="#00ff00")
        res = cmd_color(ctx)
        assert res.success is True
        assert "0, 255, 0" in res.message

    def test_invalid_color(self):
        ctx = CommandContext(args_text="not-a-color")
        res = cmd_color(ctx)
        assert res.success is False
        assert "格式错误" in res.error

    def test_rgba_payload_has_alpha(self):
        ctx = CommandContext(args_text="#ff880080")
        res = cmd_color(ctx)
        assert res.success is True
        assert res.payload["a"] == 128
        assert "RGBA" in res.message

    def test_rgb_payload_alpha_is_none(self):
        ctx = CommandContext(args_text="#ff8800")
        res = cmd_color(ctx)
        assert res.success is True
        assert res.payload["a"] is None
        assert "RGB" in res.message

    def test_copy_actions_present(self):
        ctx = CommandContext(args_text="#ff0000")
        res = cmd_color(ctx)
        assert len(res.actions) == 2
        labels = {a.label for a in res.actions}
        assert "复制 HEX" in labels
        assert "复制 RGB" in labels

    def test_rgba_copy_actions(self):
        ctx = CommandContext(args_text="#ff000080")
        res = cmd_color(ctx)
        labels = {a.label for a in res.actions}
        assert "复制 HEX" in labels
        assert "复制 RGBA" in labels


# ===========================================================================
# ── cmd_ip edge cases ──────────────────────────────────────────────────────
# ===========================================================================


class TestCmdIpEdgeCases:
    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_public_only_mode(self, mock_primary, mock_local, mock_public):
        mock_public.return_value = ("203.0.113.1", "")
        ctx = CommandContext(args_text="public")
        res = cmd_ip(ctx)
        assert res.success is True
        assert "203.0.113.1" in res.message
        mock_primary.assert_not_called()

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_local_only_mode(self, mock_primary, mock_local, mock_public):
        mock_primary.return_value = "192.168.1.1"
        mock_local.return_value = [("192.168.1.1", "eth0")]
        ctx = CommandContext(args_text="local")
        res = cmd_ip(ctx)
        assert res.success is True
        assert "192.168.1.1" in res.message
        mock_public.assert_not_called()

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_chinese_public_mode(self, mock_primary, mock_local, mock_public):
        mock_public.return_value = ("1.2.3.4", "")
        ctx = CommandContext(args_text="公网")
        res = cmd_ip(ctx)
        assert res.success is True
        mock_primary.assert_not_called()

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_chinese_local_mode(self, mock_primary, mock_local, mock_public):
        mock_primary.return_value = "10.0.0.1"
        mock_local.return_value = [("10.0.0.1", "lo")]
        ctx = CommandContext(args_text="内网")
        res = cmd_ip(ctx)
        assert res.success is True
        mock_public.assert_not_called()

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_local_failure_when_not_wanting_public(self, mock_primary, mock_local, mock_public):
        mock_primary.side_effect = Exception("no network")
        ctx = CommandContext(args_text="local")
        res = cmd_ip(ctx)
        assert res.success is False
        assert "无法获取内网 IP" in res.message

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_public_only_failure(self, mock_primary, mock_local, mock_public):
        mock_public.return_value = ("", "timeout")
        ctx = CommandContext(args_text="public")
        res = cmd_ip(ctx)
        assert res.success is False

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_primary_ip_marked_as_current_exit(self, mock_primary, mock_local, mock_public):
        mock_primary.return_value = "192.168.1.100"
        mock_local.return_value = [("192.168.1.100", "Wi-Fi"), ("10.0.0.1", "VPN")]
        mock_public.return_value = ("", "")
        ctx = CommandContext()
        res = cmd_ip(ctx)
        assert "[当前出口]" in res.message

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_local_no_entries_but_has_primary(self, mock_primary, mock_local, mock_public):
        mock_primary.return_value = "192.168.1.50"
        mock_local.return_value = []
        mock_public.return_value = ("", "")
        ctx = CommandContext()
        res = cmd_ip(ctx)
        assert res.success is True
        assert "192.168.1.50" in res.message

    @patch("core.commands_network._fetch_public_ip")
    @patch("core.commands_network._get_local_ipv4_addresses")
    @patch("core.commands_network._get_primary_local_ip")
    def test_copy_actions_for_local_ips(self, mock_primary, mock_local, mock_public):
        mock_primary.return_value = "192.168.1.1"
        mock_local.return_value = [("192.168.1.1", "eth0"), ("10.0.0.1", "tun0")]
        mock_public.return_value = ("", "")
        ctx = CommandContext()
        res = cmd_ip(ctx)
        copy_actions = [a for a in res.actions if a.type == "copy"]
        assert any("192.168.1.1" in a.value for a in copy_actions)


# ===========================================================================
# ── cmd_copy_path edge cases ───────────────────────────────────────────────
# ===========================================================================


class TestCmdCopyPathEdgeCases:
    def test_dir_mode_chinese(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="目录")
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.message == "C:\\test"

    def test_folder_mode(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="folder")
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.message == "C:\\test"

    def test_name_mode_chinese(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="文件名")
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.message == "file.txt"

    def test_unknown_mode_label(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="something")
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.actions[0].label == "复制"

    def test_multiple_files(self):
        ctx = CommandContext(selected_files=["C:\\a.txt", "D:\\b.txt", "E:\\c.txt"])
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.message.count("\n") == 2

    def test_mode_from_args_dict(self):
        ctx = CommandContext(
            selected_files=["C:\\test\\file.txt"],
            args={"mode": "name"},
        )
        res = cmd_copy_path(ctx)
        assert res.success is True
        assert res.message == "file.txt"

    def test_name_mode_label(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="name")
        res = cmd_copy_path(ctx)
        assert res.actions[0].label == "复制文件名"

    def test_dir_mode_label(self):
        ctx = CommandContext(selected_files=["C:\\test\\file.txt"], args_text="dir")
        res = cmd_copy_path(ctx)
        assert res.actions[0].label == "复制目录"


# ===========================================================================
# ── cmd_hash edge cases ────────────────────────────────────────────────────
# ===========================================================================


class TestCmdHashEdgeCases:
    def test_algo_at_end(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"data")
        ctx = CommandContext(args_text=f"{f} sha1")
        res = cmd_hash(ctx)
        assert res.success is True
        assert hashlib.sha1(b"data").hexdigest() in res.message.lower()

    def test_no_input_no_selection(self):
        ctx = CommandContext(args_text="")
        res = cmd_hash(ctx)
        assert res.success is False
        assert "缺少输入" in res.error

    def test_file_not_found(self):
        ctx = CommandContext(args_text="nonexistent_file_12345.txt")
        res = cmd_hash(ctx)
        assert res.success is False
        assert "不存在" in res.message

    def test_algo_first_then_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        ctx = CommandContext(args_text=f"sha256 {f}")
        res = cmd_hash(ctx)
        assert res.success is True
        expected = hashlib.sha256(b"hello").hexdigest()
        assert expected in res.message.lower()

    def test_quotes_stripped(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"data")
        ctx = CommandContext(args_text=f'"{f}"')
        res = cmd_hash(ctx)
        assert res.success is True

    def test_copy_action(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        ctx = CommandContext(args_text=str(f))
        res = cmd_hash(ctx)
        assert len(res.actions) == 1
        assert res.actions[0].type == "copy"
        assert res.actions[0].value == hashlib.md5(b"hello").hexdigest()


# ===========================================================================
# ── cmd_timestamp edge cases ───────────────────────────────────────────────
# ===========================================================================


class TestCmdTimestampEdgeCases:
    def test_returns_copy_action(self):
        res = cmd_timestamp(CommandContext())
        assert res.success is True
        assert len(res.actions) == 1
        assert res.actions[0].type == "copy"
        assert res.actions[0].label == "复制时间戳"

    def test_specific_timestamp_has_copy_action(self):
        ctx = CommandContext(args_text="1684789200")
        res = cmd_timestamp(ctx)
        assert res.success is True
        assert res.actions[0].label == "复制日期"

    def test_negative_timestamp(self):
        ctx = CommandContext(args_text="-1")
        res = cmd_timestamp(ctx)
        # Negative timestamps may work on some platforms, just ensure no crash
        assert isinstance(res.success, bool)

    def test_zero_timestamp(self):
        ctx = CommandContext(args_text="0")
        res = cmd_timestamp(ctx)
        assert res.success is True
        assert "1970" in res.message

    def test_invalid_string(self):
        ctx = CommandContext(args_text="not_a_number")
        res = cmd_timestamp(ctx)
        assert res.success is False
        assert "无效" in res.message


# ===========================================================================
# ── cmd_base64 edge cases ──────────────────────────────────────────────────
# ===========================================================================


class TestCmdBase64EdgeCases:
    def test_decode_mode_via_args(self):
        ctx = CommandContext(args_text="aGVsbG8=", args={"mode": "decode"})
        res = cmd_base64(ctx)
        assert res.success is True
        assert res.message == "hello"

    def test_encode_short_alias_e(self):
        ctx = CommandContext(args_text="e hello")
        res = cmd_base64(ctx)
        assert res.success is True
        assert res.message == "aGVsbG8="

    def test_decode_short_alias_d(self):
        ctx = CommandContext(args_text="d aGVsbG8=")
        res = cmd_base64(ctx)
        assert res.success is True
        assert res.message == "hello"

    def test_chinese_alias(self):
        ctx = CommandContext(args_text="编码 hello")
        res = cmd_base64(ctx)
        assert res.success is True
        assert res.message == "aGVsbG8="

    def test_chinese_decode_alias(self):
        ctx = CommandContext(args_text="解码 aGVsbG8=")
        res = cmd_base64(ctx)
        assert res.success is True
        assert res.message == "hello"

    def test_empty_no_clipboard(self):
        ctx = CommandContext(args_text="")
        res = cmd_base64(ctx)
        assert res.success is False
        assert "缺少输入" in res.error

    def test_invalid_base64_decode(self):
        ctx = CommandContext(args_text="decode !!!not-base64!!!")
        res = cmd_base64(ctx)
        assert res.success is False
        assert "解码失败" in res.error

    def test_display_type_is_text(self):
        ctx = CommandContext(args_text="hello")
        res = cmd_base64(ctx)
        assert res.display_type == "text"

    def test_copy_action_present(self):
        ctx = CommandContext(args_text="hello")
        res = cmd_base64(ctx)
        assert len(res.actions) == 1
        assert res.actions[0].type == "copy"


# ===========================================================================
# ── cmd_json edge cases ────────────────────────────────────────────────────
# ===========================================================================


class TestCmdJsonEdgeCases:
    def test_validate_object(self):
        res = cmd_json(CommandContext(args_text='validate {"a": 1}'))
        assert res.success is True
        assert "对象" in res.message
        assert "1 个键" in res.message

    def test_validate_array(self):
        res = cmd_json(CommandContext(args_text="validate [1, 2, 3]"))
        assert res.success is True
        assert "数组" in res.message
        assert "3 项" in res.message

    def test_validate_scalar(self):
        res = cmd_json(CommandContext(args_text="validate 42"))
        assert res.success is True
        assert "int" in res.message

    def test_compact_mode(self):
        res = cmd_json(CommandContext(args_text='compact {"a": 1, "b": 2}'))
        assert res.success is True
        assert "\n" not in res.message

    def test_minify_alias(self):
        res = cmd_json(CommandContext(args_text='minify {"a": 1}'))
        assert res.success is True
        assert res.message == '{"a":1}'

    def test_format_mode(self):
        res = cmd_json(CommandContext(args_text='format {"a":1}'))
        assert res.success is True
        assert "\n" in res.message

    def test_fmt_alias(self):
        res = cmd_json(CommandContext(args_text='fmt {"a":1}'))
        assert res.success is True
        assert "\n" in res.message

    def test_empty_input_no_clipboard(self):
        res = cmd_json(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少输入" in res.error

    def test_clipboard_fallback(self):
        res = cmd_json(CommandContext(args_text="", clipboard_text='{"a":1}'))
        assert res.success is True

    def test_invalid_json_error_detail(self):
        res = cmd_json(CommandContext(args_text='{"a": invalid}'))
        assert res.success is False
        assert "JSON 无效" in res.message
        assert "JSON 解析失败" in res.error

    def test_copy_action_present(self):
        res = cmd_json(CommandContext(args_text='{"a":1}'))
        assert len(res.actions) == 1
        assert res.actions[0].label == "复制 JSON"


# ===========================================================================
# ── cmd_jwt edge cases ─────────────────────────────────────────────────────
# ===========================================================================


class TestCmdJwtEdgeCases:
    def test_empty_input(self):
        res = cmd_jwt(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少输入" in res.error

    def test_too_few_parts(self):
        res = cmd_jwt(CommandContext(args_text="onlyonepart"))
        assert res.success is False
        assert "格式错误" in res.error

    def test_with_signature(self):
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(b'{"sub":"u1"}').decode().rstrip("=")
        sig = "dummysig"
        res = cmd_jwt(CommandContext(args_text=f"{header}.{payload}.{sig}"))
        assert res.success is True
        assert "有签名段，未验证签名" in res.message

    def test_without_signature(self):
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(b'{"sub":"u1"}').decode().rstrip("=")
        res = cmd_jwt(CommandContext(args_text=f"{header}.{payload}"))
        assert res.success is True
        assert "无签名段" in res.message

    def test_copy_actions(self):
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(b'{"sub":"u1"}').decode().rstrip("=")
        res = cmd_jwt(CommandContext(args_text=f"{header}.{payload}"))
        assert len(res.actions) == 2
        labels = {a.label for a in res.actions}
        assert "复制 Payload" in labels
        assert "复制完整解码" in labels

    def test_clipboard_fallback(self):
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(b'{"sub":"u1"}').decode().rstrip("=")
        res = cmd_jwt(CommandContext(args_text="", clipboard_text=f"{header}.{payload}"))
        assert res.success is True

    def test_invalid_base64_in_jwt(self):
        res = cmd_jwt(CommandContext(args_text="!!!.###.???"))
        assert res.success is False
        assert "解码失败" in res.error


# ===========================================================================
# ── cmd_cidr edge cases ────────────────────────────────────────────────────
# ===========================================================================


class TestCmdCidrEdgeCases:
    def test_empty_input(self):
        res = cmd_cidr(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少输入" in res.error

    def test_clipboard_fallback(self):
        res = cmd_cidr(CommandContext(args_text="", clipboard_text="10.0.0.1/8"))
        assert res.success is True
        assert "10.0.0.0/8" in res.message

    def test_single_host_32(self):
        res = cmd_cidr(CommandContext(args_text="192.168.1.1/32"))
        assert res.success is True
        assert "可用主机数: 1" in res.message

    def test_slash_31(self):
        res = cmd_cidr(CommandContext(args_text="192.168.1.0/31"))
        assert res.success is True
        assert "可用主机数: 2" in res.message

    def test_copy_actions(self):
        res = cmd_cidr(CommandContext(args_text="192.168.1.0/24"))
        assert len(res.actions) == 2
        labels = {a.label for a in res.actions}
        assert "复制网络" in labels
        assert "复制报告" in labels

    def test_ipv6(self):
        res = cmd_cidr(CommandContext(args_text="2001:db8::1/64"))
        assert res.success is True
        assert "2001:db8::/64" in res.message

    def test_invalid_cidr(self):
        res = cmd_cidr(CommandContext(args_text="not-a-cidr"))
        assert res.success is False
        assert "格式错误" in res.error


# ===========================================================================
# ── cmd_netdiag edge cases ─────────────────────────────────────────────────
# ===========================================================================


class TestCmdNetdiagEdgeCases:
    def test_empty_input(self):
        res = cmd_netdiag(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少目标" in res.error

    def test_clipboard_fallback(self):
        with (
            patch("socket.getaddrinfo") as mock_dns,
            patch("socket.create_connection") as mock_conn,
            patch("core.commands_network._run_cmd") as mock_run,
        ):
            mock_dns.return_value = [(None, None, None, None, ("1.2.3.4", 80))]
            mock_conn.return_value.__enter__.return_value = object()
            mock_run.return_value = (True, "Average = 10ms")
            res = cmd_netdiag(CommandContext(args_text="", clipboard_text="example.com"))
            assert res.success is True

    @patch("core.commands_network._run_cmd")
    @patch("socket.create_connection")
    @patch("socket.getaddrinfo")
    def test_dns_failure(self, mock_dns, mock_conn, mock_run):
        mock_dns.side_effect = Exception("DNS failed")
        mock_run.return_value = (False, "")
        res = cmd_netdiag(CommandContext(args_text="example.com"))
        assert res.success is True
        assert "解析失败" in res.message

    @patch("core.commands_network._run_cmd")
    @patch("socket.create_connection")
    @patch("socket.getaddrinfo")
    def test_tcp_connection_failure(self, mock_dns, mock_conn, mock_run):
        mock_dns.return_value = [(None, None, None, None, ("1.2.3.4", 443))]
        mock_conn.side_effect = Exception("refused")
        mock_run.return_value = (False, "timeout")
        res = cmd_netdiag(CommandContext(args_text="example.com"))
        assert res.success is True
        assert "失败" in res.message

    @patch("core.commands_network._run_cmd")
    @patch("socket.create_connection")
    @patch("socket.getaddrinfo")
    def test_custom_port(self, mock_dns, mock_conn, mock_run):
        mock_dns.return_value = [(None, None, None, None, ("1.2.3.4", 8080))]
        mock_conn.return_value.__enter__.return_value = object()
        mock_run.return_value = (True, "")
        res = cmd_netdiag(CommandContext(args_text="example.com:8080"))
        assert res.success is True
        assert "TCP 8080" in res.message

    @patch("core.commands_network._run_cmd")
    @patch("socket.create_connection")
    @patch("socket.getaddrinfo")
    def test_suggestion_shown_when_dns_ok(self, mock_dns, mock_conn, mock_run):
        mock_dns.return_value = [(None, None, None, None, ("1.2.3.4", 443))]
        mock_conn.side_effect = Exception("refused")
        mock_run.return_value = (False, "")
        res = cmd_netdiag(CommandContext(args_text="example.com"))
        assert "建议" in res.message

    @patch("core.commands_network._run_cmd")
    @patch("socket.create_connection")
    @patch("socket.getaddrinfo")
    def test_copy_action(self, mock_dns, mock_conn, mock_run):
        mock_dns.return_value = [(None, None, None, None, ("1.2.3.4", 443))]
        mock_conn.return_value.__enter__.return_value = object()
        mock_run.return_value = (True, "Average = 10ms")
        res = cmd_netdiag(CommandContext(args_text="example.com"))
        assert len(res.actions) == 1
        assert res.actions[0].label == "复制诊断报告"


# ===========================================================================
# ── cmd_tls edge cases ─────────────────────────────────────────────────────
# ===========================================================================


class TestCmdTlsEdgeCases:
    def test_empty_input(self):
        res = cmd_tls(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少目标" in res.error

    def test_host_with_spaces_rejected(self):
        res = cmd_tls(CommandContext(args_text="bad domain"))
        assert res.success is False
        assert "格式错误" in res.error

    @patch("core.commands.socket.create_connection")
    @patch("core.commands.ssl.create_default_context")
    def test_timeout_error(self, mock_ssl, mock_conn):
        mock_conn.side_effect = TimeoutError("timed out")
        res = cmd_tls(CommandContext(args_text="example.com"))
        assert res.success is False
        assert "超时" in res.message

    @patch("core.commands.socket.create_connection")
    @patch("core.commands.ssl.create_default_context")
    def test_ssl_cert_error(self, mock_ssl, mock_conn):
        import ssl

        mock_conn.side_effect = ssl.SSLCertVerificationError("cert bad")
        res = cmd_tls(CommandContext(args_text="example.com"))
        assert res.success is False
        assert "证书校验失败" in res.error

    @patch("core.commands.socket.create_connection")
    @patch("core.commands.ssl.create_default_context")
    def test_ssl_error(self, mock_ssl, mock_conn):
        import ssl

        mock_conn.side_effect = ssl.SSLError("handshake failed")
        res = cmd_tls(CommandContext(args_text="example.com"))
        assert res.success is False
        assert "TLS 握手失败" in res.error

    @patch("core.commands.socket.create_connection")
    @patch("core.commands.ssl.create_default_context")
    def test_clipboard_fallback(self, mock_ssl, mock_conn):
        raw_sock = MagicMock()
        raw_sock.__enter__.return_value = object()
        raw_sock.__exit__.return_value = None
        mock_conn.return_value = raw_sock
        tls_sock = MagicMock()
        tls_sock.__enter__.return_value = tls_sock
        tls_sock.__exit__.return_value = None
        tls_sock.getpeercert.return_value = {
            "subject": ((("commonName", "example.com"),),),
            "issuer": ((("organizationName", "CA"),),),
            "notBefore": "Jan 01 00:00:00 2026 GMT",
            "notAfter": "Jan 01 00:00:00 2027 GMT",
            "subjectAltName": (("DNS", "example.com"),),
        }
        tls_sock.cipher.return_value = ("AES", "TLSv1.2", 128)
        tls_sock.version.return_value = "TLSv1.2"
        ctx = MagicMock()
        ctx.wrap_socket.return_value = tls_sock
        mock_ssl.return_value = ctx
        res = cmd_tls(CommandContext(args_text="", clipboard_text="example.com"))
        assert res.success is True

    @patch("core.commands.socket.create_connection")
    @patch("core.commands.ssl.create_default_context")
    def test_many_sans_are_fully_displayed(self, mock_ssl, mock_conn):
        raw_sock = MagicMock()
        raw_sock.__enter__.return_value = object()
        raw_sock.__exit__.return_value = None
        mock_conn.return_value = raw_sock
        sans = [("DNS", f"s{i}.example.com") for i in range(12)]
        tls_sock = MagicMock()
        tls_sock.__enter__.return_value = tls_sock
        tls_sock.__exit__.return_value = None
        tls_sock.getpeercert.return_value = {
            "subject": (),
            "issuer": (),
            "notBefore": "Jan 01 00:00:00 2026 GMT",
            "notAfter": "Jan 01 00:00:00 2027 GMT",
            "subjectAltName": sans,
        }
        tls_sock.cipher.return_value = ("AES", "TLSv1.2", 128)
        tls_sock.version.return_value = "TLSv1.2"
        ctx = MagicMock()
        ctx.wrap_socket.return_value = tls_sock
        mock_ssl.return_value = ctx
        res = cmd_tls(CommandContext(args_text="example.com"))
        assert res.success is True
        assert "s0.example.com" in res.message
        assert "s11.example.com" in res.message
        assert "(+" not in res.message


# ===========================================================================
# ── cmd_path_audit edge cases ──────────────────────────────────────────────
# ===========================================================================


class TestCmdPathAuditEdgeCases:
    def test_empty_path_env(self):
        with patch.dict(os.environ, {"PATH": ""}, clear=False):
            # Provide explicit empty args to avoid reading real PATH
            res = cmd_path_audit(CommandContext(args_text=""))
            # Either fails with "未检测到" or succeeds with empty PATH
            assert isinstance(res.success, bool)

    def test_clean_path_no_issues(self, tmp_path):
        d = tmp_path / "bin"
        d.mkdir()
        res = cmd_path_audit(CommandContext(args_text=str(d)))
        assert res.success is True
        assert "未发现" in res.message

    def test_copy_action(self, tmp_path):
        d = tmp_path / "bin"
        d.mkdir()
        res = cmd_path_audit(CommandContext(args_text=str(d)))
        assert len(res.actions) == 1
        assert res.actions[0].label == "复制报告"


# ===========================================================================
# ── cmd_selected ───────────────────────────────────────────────────────────
# ===========================================================================


class TestCmdSelected:
    def test_no_selected_text(self):
        with patch(
            "core.selected_text_service.selected_text_service.get_selected_text",
            return_value=SelectedTextResult(text="", success=False, method="none"),
        ):
            res = cmd_selected(CommandContext())
            assert res.success is False
            assert "未检测到" in res.message or "empty" in res.error

    def test_with_selected_text(self):
        ctx = CommandContext(selected_text="hello world", selected_text_method="clipboard")
        res = cmd_selected(ctx)
        assert res.success is True
        assert "hello world" in res.message
        assert "clipboard" in res.message

    def test_long_text_truncated(self):
        long_text = "a" * 300
        ctx = CommandContext(selected_text=long_text, selected_text_method="uia")
        res = cmd_selected(ctx)
        assert res.success is True
        assert "共 300 字" in res.message
        assert len(res.message.split("选中文字: ")[1].split("\n")[0]) == 200

    def test_copy_actions(self):
        ctx = CommandContext(selected_text="test", selected_text_method="cb")
        res = cmd_selected(ctx)
        assert len(res.actions) == 2
        labels = {a.label for a in res.actions}
        assert "复制选中文字" in labels
        assert "复制选中文字(URL编码)" in labels


# ===========================================================================
# ── cmd_clip ───────────────────────────────────────────────────────────────
# ===========================================================================


class TestCmdClip:
    def test_empty_clipboard(self):
        ctx = CommandContext(clipboard_text="", clipboard_kind="")
        mock_snapshot = MagicMock()
        mock_snapshot.text = ""
        mock_snapshot.is_empty = True
        mock_svc = MagicMock()
        mock_svc.read_snapshot.return_value = mock_snapshot

        mock_classification = MagicMock()
        mock_classification.kind = ""

        with (
            patch("core.clipboard_service.clipboard_service", mock_svc),
            patch("core.clipboard_classifiers.classify_clipboard", return_value=mock_classification),
        ):
            res = cmd_clip(ctx)
            assert res.success is False
            assert "剪贴板为空" in res.message

    def test_text_clipboard(self):
        ctx = CommandContext(clipboard_text="hello world", clipboard_kind="text")
        res = cmd_clip(ctx)
        assert res.success is True
        assert "text" in res.message
        assert "hello world" in res.message

    def test_file_list_clipboard(self):
        ctx = CommandContext(
            clipboard_text="file1.txt\nfile2.txt",
            clipboard_kind="file_list",
            clipboard_files=["C:\\file1.txt", "D:\\file2.txt"],
        )
        res = cmd_clip(ctx)
        assert res.success is True
        assert "文件: 2 个" in res.message
        assert "file1.txt" in res.message

    def test_file_list_truncated_at_5(self):
        files = [f"C:\\file{i}.txt" for i in range(8)]
        ctx = CommandContext(
            clipboard_text="\n".join(files),
            clipboard_kind="file_list",
            clipboard_files=files,
        )
        res = cmd_clip(ctx)
        assert res.success is True
        assert "还有 3 个文件" in res.message

    def test_long_text_truncated(self):
        long_text = "x" * 300
        ctx = CommandContext(clipboard_text=long_text, clipboard_kind="text")
        res = cmd_clip(ctx)
        assert "共 300 字" in res.message

    def test_copy_action(self):
        ctx = CommandContext(clipboard_text="data", clipboard_kind="text")
        res = cmd_clip(ctx)
        assert len(res.actions) == 1
        assert res.actions[0].value == "data"


# ===========================================================================
# ── stop_qr_file_server ────────────────────────────────────────────────────
# ===========================================================================


class TestStopQrFileServer:
    def test_stop_nonexistent_port(self):
        # Should not raise
        stop_qr_file_server(99999)


# ===========================================================================
# ── _get_primary_local_ip ──────────────────────────────────────────────────
# ===========================================================================


class TestGetPrimaryLocalIp:
    def test_returns_valid_ip(self):
        ip = _get_primary_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    @patch("core.commands.socket.socket")
    def test_fallback_to_hostname(self, mock_socket_cls):
        mock_socket_cls.side_effect = Exception("no network")
        with (
            patch("core.commands.socket.gethostname", return_value="myhost"),
            patch("core.commands.socket.gethostbyname", return_value="127.0.0.1"),
        ):
            ip = _get_primary_local_ip()
            assert ip == "127.0.0.1"


# ===========================================================================
# ── cmd_dns ────────────────────────────────────────────────────────────────
# ===========================================================================


class TestCmdDns:
    @patch("core.commands_network._run_cmd")
    def test_flush_success(self, mock_run):
        mock_run.return_value = (True, "Successfully flushed")
        res = cmd_dns(CommandContext())
        assert res.success is True
        assert "成功" in res.message

    @patch("core.commands_network._run_cmd")
    def test_flush_failure(self, mock_run):
        mock_run.return_value = (False, "Access denied")
        res = cmd_dns(CommandContext())
        assert res.success is False
        assert "失败" in res.message


# ===========================================================================
# ── cmd_port argument parsing ──────────────────────────────────────────────
# ===========================================================================


class TestCmdPortParsing:
    def test_no_args(self):
        res = cmd_port(CommandContext(args_text=""))
        assert res.success is False
        assert "缺少参数" in res.error

    def test_non_numeric_port(self):
        res = cmd_port(CommandContext(args_text="abc"))
        assert res.success is False
        assert "格式错误" in res.error


# ===========================================================================
# ── cmd_wifi argument parsing ──────────────────────────────────────────────
# ===========================================================================


class TestCmdWifiParsing:
    @patch("core.commands_network._run_cmd")
    def test_list_profiles_parses_output(self, mock_run):
        mock_run.return_value = (
            True,
            "All User Profile     : MyWiFi\nAll User Profile     : Guest\n",
        )
        res = cmd_wifi(CommandContext(args_text=""))
        assert res.success is True
        assert "MyWiFi" in res.message
        assert "Guest" in res.message

    @patch("core.commands_network._run_cmd")
    def test_list_profiles_empty(self, mock_run):
        mock_run.return_value = (True, "No profiles found")
        res = cmd_wifi(CommandContext(args_text=""))
        assert res.success is True
        assert "未找到" in res.message

    @patch("core.commands_network._run_cmd")
    def test_list_profiles_failure_wlansvc(self, mock_run):
        mock_run.return_value = (False, "The wlansvc service is not running")
        res = cmd_wifi(CommandContext(args_text=""))
        assert res.success is False
        assert "wlansvc" in res.message.lower() or "提示" in res.message

    @patch("core.commands_network._run_cmd")
    def test_list_profiles_failure_no_wireless(self, mock_run):
        mock_run.return_value = (False, "No wireless interface")
        res = cmd_wifi(CommandContext(args_text=""))
        assert res.success is False
        assert "无线" in res.message or "提示" in res.message

    @patch("core.commands_network._run_cmd")
    def test_query_password_found(self, mock_run):
        mock_run.return_value = (
            True,
            "Key Content : mypassword123\n",
        )
        res = cmd_wifi(CommandContext(args_text="MyWiFi"))
        assert res.success is True
        assert "mypassword123" in res.message

    @patch("core.commands_network._run_cmd")
    def test_query_password_not_found(self, mock_run):
        mock_run.return_value = (False, "Not found")
        res = cmd_wifi(CommandContext(args_text="UnknownWiFi"))
        assert res.success is False

    @patch("core.commands_network._run_cmd")
    def test_query_no_password(self, mock_run):
        mock_run.return_value = (True, "Some output without key content")
        res = cmd_wifi(CommandContext(args_text="OpenWiFi"))
        assert res.success is True
        assert "无密码" in res.message or "开放网络" in res.message

    @patch("core.commands_network._run_cmd")
    def test_chinese_profile_parsing(self, mock_run):
        mock_run.return_value = (True, "所有用户配置文件     : 我的WiFi\n")
        res = cmd_wifi(CommandContext(args_text=""))
        assert res.success is True
        assert "我的WiFi" in res.message


# ===========================================================================
# ── cmd_conflict ───────────────────────────────────────────────────────────
# ===========================================================================


class TestCmdConflict:
    def test_no_data_manager(self):
        with patch.dict("core.__dict__", {"data_manager": None}):
            res = cmd_conflict(CommandContext())
            assert res.success is False

    def test_no_items(self):
        fake_dm = MagicMock()
        fake_dm.data.folders = []
        with patch.dict("core.__dict__", {"data_manager": fake_dm}):
            res = cmd_conflict(CommandContext())
            assert res.success is True
            assert "没有" in res.message
