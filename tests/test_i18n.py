"""Tests for core/i18n.py — internationalization system."""

import pytest

from core.i18n import (
    DEFAULT_LANGUAGE,
    get_language,
    is_chinese,
    normalize_language,
    set_language,
    tr,
    using_language,
)


@pytest.fixture(autouse=True)
def _restore_language():
    original = get_language()
    yield
    set_language(original)


class TestTranslate:
    def test_tr_returns_source_by_default(self):
        assert tr("确定") == "确定"

    def test_tr_returns_english_when_set(self):
        set_language("en_US")
        assert tr("确定") == "OK"

    def test_tr_fallback_to_source_when_missing(self):
        set_language("en_US")
        assert tr("不存在的字符串") == "不存在的字符串"

    def test_tr_with_format_args(self):
        result = tr("版本 {v}", v="1.0")
        assert result == "版本 1.0"

    def test_tr_preserves_braces_for_missing_keys(self):
        set_language("en_US")
        assert tr("{unknown}") == "{unknown}"


class TestSetLanguage:
    def test_set_language_normalizes_variants(self):
        set_language("en")
        assert get_language() == "en_US"
        set_language("ENGLISH")
        assert get_language() == "en_US"
        set_language("en_US")
        assert get_language() == "en_US"
        set_language("EN_US")
        assert get_language() == "en_US"

    def test_set_language_normalizes_chinese_variants(self):
        set_language("zh")
        assert get_language() == "zh_CN"
        set_language("CHINESE")
        assert get_language() == "zh_CN"
        set_language("zh_CN")
        assert get_language() == "zh_CN"
        set_language("zh_hans")
        assert get_language() == "zh_CN"

    def test_set_language_unknown_falls_back(self):
        set_language("fr_FR")
        assert get_language() == DEFAULT_LANGUAGE


class TestNormalizeLanguage:
    def test_normalize_language_empty(self):
        assert normalize_language("") == DEFAULT_LANGUAGE

    def test_normalize_language_none(self):
        assert normalize_language(None) == DEFAULT_LANGUAGE

    def test_normalize_language_whitespace(self):
        assert normalize_language("  ") == DEFAULT_LANGUAGE

    def test_normalize_language_invalid(self):
        assert normalize_language("invalid") == DEFAULT_LANGUAGE
        assert normalize_language("de_DE") == DEFAULT_LANGUAGE

    def test_normalize_language_en_variants(self):
        assert normalize_language("en") == "en_US"
        assert normalize_language("english") == "en_US"
        assert normalize_language("en-US") == "en_US"

    def test_normalize_language_zh_variants(self):
        assert normalize_language("zh") == "zh_CN"
        assert normalize_language("chinese") == "zh_CN"
        assert normalize_language("zh-CN") == "zh_CN"
        assert normalize_language("zh-Hans") == "zh_CN"


class TestGetLanguage:
    def test_get_language_initial(self):
        assert get_language() == "zh_CN"

    def test_current_language_not_none(self):
        assert get_language() is not None
        set_language("en_US")
        assert get_language() is not None
        set_language(None)
        assert get_language() is not None


class TestUsingLanguage:
    def test_using_language_contextmanager(self):
        original = get_language()
        with using_language("en_US"):
            assert get_language() == "en_US"
            assert tr("确定") == "OK"
        assert get_language() == original

    def test_using_language_restores_on_exception(self):
        original = get_language()
        try:
            with using_language("en_US"):
                raise ValueError("boom")
        except ValueError:  # noqa: S110 - expected path for context manager restoration
            pass
        assert get_language() == original

    def test_using_language_nested(self):
        with using_language("en_US"):
            assert get_language() == "en_US"
            with using_language("zh_CN"):
                assert get_language() == "zh_CN"
            assert get_language() == "en_US"


class TestIsChinese:
    def test_is_chinese_true_by_default(self):
        assert is_chinese() is True

    def test_is_chinese_false_when_english(self):
        set_language("en_US")
        assert is_chinese() is False

    def test_is_chinese_true_when_chinese(self):
        set_language("zh_CN")
        assert is_chinese() is True


class TestTranslationDict:
    def test_all_en_us_keys_have_nonempty_values(self):
        from core.i18n import _EN_US

        for key, value in _EN_US.items():
            assert value, f"Empty translation for key: {key!r}"

    def test_en_us_keys_match_self(self):
        from core.i18n import _EN_US

        for key, value in _EN_US.items():
            if len(key) <= 1:
                assert value, f"Empty translation for short key: {key!r}"
