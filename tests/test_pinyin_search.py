from core.pinyin_search import pinyin_variants


def test_pinyin_match_chinese():
    variants = pinyin_variants("微信")
    assert "weixin" in variants
    assert "wx" in variants


def test_pinyin_prefix_match():
    variants = pinyin_variants("支付宝")
    assert "zfb" in variants
    assert "zhifubao" in variants


def test_no_pinyin_for_english():
    assert pinyin_variants("Notepad") == []
    assert pinyin_variants("Chrome") == []
    assert pinyin_variants("hello world") == []


def test_empty_query():
    assert pinyin_variants("") == []


def test_cache_works():
    results = [pinyin_variants("微信") for _ in range(10)]
    first = results[0]
    assert all(r == first for r in results)


def test_special_characters():
    variants = pinyin_variants("微信@#$%")
    assert "weixin" in variants
    assert "wx" in variants


def test_long_query():
    long_text = "微信" * 500
    variants = pinyin_variants(long_text)
    assert isinstance(variants, list)
    assert len(variants) > 0


def test_pinyin_fallback_initials():
    # "蓝牙" is not in _PINYIN dict, but both characters are in GB2312 level-1.
    # So "蓝牙" should be mapped to initials "ly".
    variants = pinyin_variants("蓝牙")
    assert "ly" in variants

    # "连接" has "连" (expanded in _PINYIN) and "接" (already in _PINYIN).
    # It should have both full "lianjie" and initials "lj"
    variants_lianjie = pinyin_variants("连接")
    assert "lianjie" in variants_lianjie
    assert "lj" in variants_lianjie
