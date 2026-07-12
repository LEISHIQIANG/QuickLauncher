"""Tests for clipboard classifiers."""

from core.clipboard_classifiers import classify_text, classify_text_safe


class TestClassifyText:
    def test_classify_empty(self):
        kind, confidence, summary = classify_text("")
        assert kind == "empty"
        assert confidence == 1.0

    def test_classify_url_http(self):
        kind, confidence, summary = classify_text("http://example.com/path?q=1")
        assert kind == "url"
        assert confidence >= 0.95

    def test_classify_url_https(self):
        kind, confidence, summary = classify_text("https://www.google.com")
        assert kind == "url"
        assert confidence >= 0.95

    def test_classify_json_obj(self):
        kind, confidence, summary = classify_text('{"a": 1, "b": "test"}')
        assert kind == "json"
        assert confidence >= 0.95

    def test_classify_json_arr(self):
        kind, confidence, summary = classify_text("[1, 2, 3]")
        assert kind == "json"
        assert confidence >= 0.95

    def test_classify_jwt(self):
        kind, confidence, summary = classify_text(
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNqPmBpQvP3gTRVr0E"
        )
        assert kind == "jwt"
        assert confidence >= 0.95

    def test_classify_color_hex(self):
        kind, confidence, summary = classify_text("#ff00ff")
        assert kind == "color"
        assert confidence >= 0.90

    def test_classify_color_rgb(self):
        kind, confidence, summary = classify_text("rgb(255, 0, 255)")
        assert kind == "color"
        assert confidence >= 0.85

    def test_classify_ip(self):
        kind, confidence, summary = classify_text("192.168.1.1")
        assert kind == "ip"
        assert confidence >= 0.90

    def test_classify_email(self):
        kind, confidence, summary = classify_text("user@example.com")
        assert kind == "email"
        assert confidence >= 0.85

    def test_classify_domain(self):
        kind, confidence, summary = classify_text("example.com")
        assert kind == "domain"
        assert confidence >= 0.80

    def test_classify_path_win(self):
        kind, confidence, summary = classify_text(r"C:\Users\test\file.txt")
        assert kind == "path"

    def test_classify_unknown_text(self):
        kind, confidence, summary = classify_text("The quick brown fox jumps over the lazy dog")
        assert kind == "unknown"

    def test_classify_api_key(self):
        kind, confidence, summary = classify_text("sk-" + "a" * 30)
        assert kind == "api_key"

    def test_classify_invalid_ip(self):
        kind, confidence, summary = classify_text("999.999.999.999")
        assert kind != "ip"  # Should not match as IP


class TestClassifyTextSafe:
    def test_returns_dict(self):
        result = classify_text_safe("https://example.com")
        assert isinstance(result, dict)
        assert result["kind"] == "url"
        assert "actions" in result

    def test_empty_returns_unknown(self):
        result = classify_text_safe("")
        assert result["kind"] == "empty"

    def test_json_has_actions(self):
        result = classify_text_safe('{"key": "value"}')
        assert result["kind"] == "json"
        assert "format_json" in result["actions"]


# ── Extended tests ─────────────────────────────────────────────────────────


def test_classify_python_code():
    text = "def hello():\n    import os\n    return os.getcwd()\n\nif __name__ == '__main__':\n    print(hello())"
    kind, confidence, summary = classify_text(text)
    assert kind == "code"
    assert confidence >= 0.80


def test_classify_js_code():
    text = "const x = 42;\nfunction foo() {\n    return x * 2;\n}\nconst result = foo();"
    kind, confidence, summary = classify_text(text)
    assert kind == "code"
    assert confidence >= 0.80


def test_classify_sql_code():
    text = "SELECT name, age, email\nFROM users\nWHERE age > 18\nORDER BY name"
    kind, confidence, summary = classify_text(text)
    assert kind == "code"
    assert confidence >= 0.80


def test_classify_domain_without_protocol():
    kind, confidence, summary = classify_text("sub.example.com")
    assert kind == "domain"
    assert confidence >= 0.80


def test_classify_ip_with_port():
    # IP:port should not match the IP regex (strict 4-octet format)
    kind, confidence, summary = classify_text("192.168.1.1:8080")
    assert kind != "ip"


def test_classify_ipv6():
    kind, confidence, summary = classify_text("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    # IPv6 is not handled by the IPv4 regex
    assert kind != "ip"


def test_classify_json_nested_objects():
    text = '{"user": {"name": "Alice", "age": 30}, "status": "ok"}'
    kind, confidence, summary = classify_text(text)
    assert kind == "json"
    assert confidence >= 0.95
    assert "user" in summary
    assert "status" in summary


def test_classify_json_array_of_objects():
    text = '[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]'
    kind, confidence, summary = classify_text(text)
    assert kind == "json"
    assert confidence >= 0.95
    assert "2 items" in summary


def test_classify_invalid_json():
    # Starts with { but not valid JSON
    kind, confidence, summary = classify_text("{broken json here")
    assert kind == "unknown"


def test_classify_jwt_valid():
    kind, confidence, summary = classify_text("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNqPmBpQvP3gTRVr0E")
    assert kind == "jwt"
    assert confidence >= 0.95
    assert "JWT" in summary


def test_classify_jwt_two_parts():
    # Only 2 parts — not a valid JWT
    kind, confidence, summary = classify_text("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0")
    assert kind != "jwt"


def test_classify_jwt_four_parts():
    # 4 parts — not a valid JWT
    kind, confidence, summary = classify_text(
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNqPmBpQvP3gTRVr0E.extra"
    )
    assert kind != "jwt"


def test_classify_color_hex_3char():
    kind, confidence, summary = classify_text("#f00")
    assert kind == "color"
    assert confidence >= 0.90


def test_classify_color_hex_8char():
    kind, confidence, summary = classify_text("#ff00ff80")
    assert kind == "color"
    assert confidence >= 0.90


def test_classify_color_hsl():
    kind, confidence, summary = classify_text("hsl(120, 100%, 50%)")
    assert kind == "color"
    assert confidence >= 0.85


def test_classify_unix_path():
    kind, confidence, summary = classify_text("/usr/bin/test")
    # Unix path matches _UNIX_PATH_RE; confidence depends on existence
    assert kind == "path"


def test_classify_relative_path():
    # Relative path (no leading / or drive letter) should not match path patterns
    kind, confidence, summary = classify_text("./some/relative/path.txt")
    assert kind != "path"


def test_classify_api_key_short():
    kind, confidence, summary = classify_text("sk-" + "x" * 20)
    assert kind == "api_key"
    assert confidence >= 0.95
    assert "API key" in summary


def test_classify_api_key_long():
    kind, confidence, summary = classify_text("sk-" + "abcdef1234567890abcdef1234567890")
    assert kind == "api_key"
    assert confidence >= 0.95


def test_classify_email_with_subdomain():
    kind, confidence, summary = classify_text("user@sub.example.com")
    assert kind == "email"
    assert confidence >= 0.85


def test_classify_very_long_text():
    # Very long text with no structure should be unknown
    text = "hello world " * 1000
    kind, confidence, summary = classify_text(text)
    assert kind == "unknown"


def test_classify_unicode_text():
    kind, confidence, summary = classify_text("这是一段中文测试文本")
    assert kind == "unknown"


def test_classify_mixed_url_in_text():
    # URL embedded in regular text — the full string is not a clean URL
    kind, confidence, summary = classify_text("check this https://example.com for info")
    assert kind == "unknown"


def test_classify_text_safe_code():
    text = "def main():\n    import sys\n    return sys.exit()"
    result = classify_text_safe(text)
    assert result["kind"] == "code"
    assert "format_code" in result["actions"]
    assert "copy_as_markdown" in result["actions"]


def test_classify_text_safe_ip():
    result = classify_text_safe("192.168.1.1")
    assert result["kind"] == "ip"
    assert "ping" in result["actions"]
    assert "whois" in result["actions"]


def test_classify_text_safe_email():
    result = classify_text_safe("admin@example.org")
    assert result["kind"] == "email"
    assert "compose_email" in result["actions"]


def test_classify_text_safe_color():
    result = classify_text_safe("#00ff00")
    assert result["kind"] == "color"
    assert "preview_color" in result["actions"]
    assert "convert_color" in result["actions"]


def test_classify_text_safe_path():
    result = classify_text_safe(r"C:\Windows\System32")
    assert result["kind"] == "path"
    assert "copy_path" in result["actions"]
    assert "open_location" in result["actions"]


def test_classify_text_safe_jwt():
    result = classify_text_safe("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNqPmBpQvP3gTRVr0E")
    assert result["kind"] == "jwt"
    assert "decode_jwt" in result["actions"]
    assert "copy_payload" in result["actions"]


def test_classify_text_safe_unknown():
    result = classify_text_safe("just some random text here")
    assert result["kind"] == "unknown"
    assert result["actions"] == []


def test_classify_text_safe_domain():
    result = classify_text_safe("example.org")
    assert result["kind"] == "domain"
    assert "ping" in result["actions"]
    assert "whois" in result["actions"]


def test_classify_text_safe_api_key():
    result = classify_text_safe("sk-" + "a" * 30)
    assert result["kind"] == "api_key"
    assert "copy_redacted" in result["actions"]


def test_classify_color_name_is_not_color():
    # Plain color name like "red" should not match as color (no hex/rgb/hsl format)
    kind, confidence, summary = classify_text("red")
    assert kind == "unknown"
