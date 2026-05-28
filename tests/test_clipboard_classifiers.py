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
